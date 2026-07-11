"""자체 OAuth 2.0 인증서버 (카카오 중개 / passthrough).

PlayMCP 심사 요구사항: PlayMCP는 카카오 계정 서비스라, MCP 서버가 카카오 OAuth를
**직접** 가리키면(authorization_endpoint=kauth.kakao.com) 충돌한다. 그래서 우리가
**자체 OAuth 인증서버**를 제공해야 한다. 이 모듈이 그 역할을 한다.

흐름(Authorization Code + PKCE):
  PlayMCP ──/oauth/authorize──▶ (우리) ──▶ 카카오 로그인
          ◀─our code─ /oauth/kakao/callback ◀─kakao code─ 카카오
  PlayMCP ──/oauth/token(our code)──▶ (우리) ──▶ **카카오 access_token 그대로 반환**

핵심 설계 = **passthrough**: 우리가 발급하는 access_token은 카카오 access_token
그 자체다. 따라서 리소스 서버(KC)의 ``resolve_caller``(헤더의 카카오 토큰으로
``/v2/user/me`` 조회)가 **무수정으로** 동작하고, DO/KC 간 세션 공유가 필요 없다.

상태 비저장(stateless): authorize→callback 연계와 발급 코드는 모두 HMAC 서명 +
토큰 필드 암호화(crypto.encrypt_token)된 자족적 문자열로, 멀티워커/멀티호스트에서도
공유 저장소 없이 동작한다. 콜백 redirect_uri는 ``oauth_as_base_url`` 기준으로
고정(카카오 콘솔에 등록된 값과 일치해야 함).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import secrets
import time
from urllib.parse import urlencode

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import kakao, kakao_store, storage
from .config import settings
from .crypto import decrypt_token, encrypt_token

# 발급 코드 유효시간(짧게 — 교환은 즉시 일어난다).
_CODE_TTL = 120
# authorize→callback 연계 state 유효시간(사용자가 로그인하는 데 드는 시간).
_STATE_TTL = 600
# 우리 refresh_token 유효시간(카카오 refresh 만료보다 여유).
_REFRESH_TTL = 60 * 60 * 24 * 30


def _as_base() -> str:
    """자체 인증서버의 공개 베이스 URL (끝 슬래시 제거)."""
    return settings.oauth_as_base_url.rstrip("/")


def _callback_uri() -> str:
    """카카오가 우리에게 돌아오는 고정 redirect_uri(카카오 콘솔에 등록 필요)."""
    return f"{_as_base()}/oauth/kakao/callback"


def _secret() -> bytes:
    """서명 키(진짜 비밀에서만)."""
    raw = settings.invite_state_secret or settings.kakao_client_secret
    if not raw:
        raise RuntimeError(
            "OAuth 서명 키가 없습니다. INVITE_STATE_SECRET 또는 KAKAO_CLIENT_SECRET을 설정하세요."
        )
    return raw.encode("utf-8")


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(raw: str) -> bytes:
    pad = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode((raw + pad).encode("ascii"))


def _sign(payload: dict) -> str:
    """payload를 HMAC 서명해 ``body.sig`` 문자열로 만든다."""
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(_secret(), body, hashlib.sha256).digest()
    return f"{_b64e(body)}.{_b64e(sig)}"


def _verify(token: str) -> dict | None:
    """서명·만료(exp)를 확인하고 payload를 돌려준다. 실패 시 None."""
    try:
        body_part, sig_part = token.split(".", 1)
        body = _b64d(body_part)
        expected = hmac.new(_secret(), body, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64d(sig_part)):
            return None
        payload = json.loads(body.decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


def _pkce_ok(verifier: str, challenge: str) -> bool:
    """PKCE S256 검증: base64url(sha256(verifier)) == challenge."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return hmac.compare_digest(_b64e(digest), challenge)


def _err_page(message: str, status: int = 400) -> HTMLResponse:
    page = (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>인증 오류</title></head>"
        '<body style="font-family:system-ui;max-width:640px;margin:3rem auto;'
        'text-align:center;padding:0 1rem">'
        f"<h1>인증 오류</h1><p>{html.escape(message)}</p></body></html>"
    )
    return HTMLResponse(page, status_code=status)


def _redirect_err(redirect_uri: str, state: str, error: str, desc: str = "") -> RedirectResponse:
    """OAuth 오류를 클라이언트 redirect_uri로 되돌린다(RFC 6749 §4.1.2.1)."""
    params = {"error": error}
    if desc:
        params["error_description"] = desc
    if state:
        params["state"] = state
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{sep}{urlencode(params)}", status_code=302)


def _token_err(error: str, desc: str = "", status: int = 400) -> JSONResponse:
    body = {"error": error}
    if desc:
        body["error_description"] = desc
    return JSONResponse(body, status_code=status)


# ---------------------------------------------------------------------------
# 엔드포인트
# ---------------------------------------------------------------------------


async def authorization_server_metadata(request: Request) -> JSONResponse:
    """RFC 8414 — 우리 인증서버 메타데이터(authorize/token/register = 우리 것)."""
    base = _as_base()
    return JSONResponse(
        {
            "issuer": base,
            "authorization_endpoint": f"{base}/oauth/authorize",
            "token_endpoint": f"{base}/oauth/token",
            "registration_endpoint": f"{base}/oauth/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": [
                "none",
                "client_secret_post",
                "client_secret_basic",
            ],
            "scopes_supported": kakao.DEFAULT_SCOPE.split(","),
        }
    )


async def register(request: Request) -> JSONResponse:
    """RFC 7591 동적 클라이언트 등록(개방형). client_id를 발급해 돌려준다.

    PKCE 공개 클라이언트를 전제로, 상태를 저장하지 않는다. redirect_uri 검증은
    PKCE + 짧은 코드 수명으로 대체한다(프록시류 AS의 일반적 관행).
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    redirect_uris = body.get("redirect_uris") or []
    client_id = f"tpt_{secrets.token_urlsafe(16)}"
    return JSONResponse(
        {
            "client_id": client_id,
            "client_id_issued_at": int(time.time()),
            "redirect_uris": redirect_uris,
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        },
        status_code=201,
    )


async def authorize(request: Request) -> RedirectResponse | HTMLResponse:
    """GET /oauth/authorize — 클라 인가요청을 받아 카카오 로그인으로 중개한다."""
    q = request.query_params
    redirect_uri = q.get("redirect_uri", "")
    state = q.get("state", "")
    if not redirect_uri:
        return _err_page("redirect_uri가 필요합니다.")
    if q.get("response_type") != "code":
        return _redirect_err(redirect_uri, state, "unsupported_response_type")

    code_challenge = q.get("code_challenge", "")
    method = q.get("code_challenge_method", "")
    # PKCE가 오면 S256만 허용(우리 검증도 S256).
    if code_challenge and method and method != "S256":
        return _redirect_err(
            redirect_uri, state, "invalid_request", "code_challenge_method must be S256"
        )

    our_state = _sign(
        {
            "cid": q.get("client_id", ""),
            "ru": redirect_uri,
            "st": state,
            "cc": code_challenge,
            "res": q.get("resource", ""),
            "exp": int(time.time()) + _STATE_TTL,
        }
    )
    # 카카오 leg의 scope는 항상 카카오 scope(클라 요청 scope는 무시).
    kakao_url = kakao.build_authorize_url(
        settings.kakao_rest_api_key, _callback_uri(), state=our_state
    )
    return RedirectResponse(kakao_url, status_code=302)


async def kakao_callback(request: Request) -> RedirectResponse | HTMLResponse:
    """GET /oauth/kakao/callback — 카카오 code를 우리 code로 바꿔 클라에 되돌린다."""
    q = request.query_params
    if q.get("error"):
        return _err_page(
            f"카카오 인증이 취소되었거나 실패했습니다: {q.get('error_description') or q.get('error')}"
        )
    code = q.get("code", "")
    data = _verify(q.get("state", ""))
    if not code or data is None:
        return _err_page("인증 상태가 만료됐거나 올바르지 않습니다. 처음부터 다시 시도해 주세요.")

    redirect_uri = str(data.get("ru") or "")
    client_state = str(data.get("st") or "")
    if not redirect_uri:
        return _err_page("클라이언트 redirect_uri를 잃었습니다.")

    token_resp = await kakao.exchange_code_for_token(
        code, settings.kakao_rest_api_key, _callback_uri(), settings.kakao_client_secret
    )
    access_token = token_resp.get("access_token")
    if not access_token:
        return _redirect_err(
            redirect_uri, client_state, "access_denied", "kakao token exchange failed"
        )

    # 사용자 등록 + 토큰 저장(스케줄러/서버발신용). 실패해도 OAuth는 계속.
    try:
        kakao_id, nickname = await kakao.get_user_info(access_token)
        if kakao_id and kakao_id != "unknown":
            storage.upsert_user(kakao_id, nickname)
            kakao_store.set_kakao_token(
                kakao_id,
                access_token,
                token_resp.get("refresh_token"),
                token_resp.get("expires_in"),
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[oauth_server] user/token store failed: {type(exc).__name__}: {exc}")

    our_code = _sign(
        {
            "at": encrypt_token(access_token),
            "rt": encrypt_token(token_resp.get("refresh_token")),
            "ei": token_resp.get("expires_in"),
            "cc": str(data.get("cc") or ""),
            "ru": redirect_uri,
            "exp": int(time.time()) + _CODE_TTL,
        }
    )
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(
        f"{redirect_uri}{sep}{urlencode({'code': our_code, 'state': client_state})}",
        status_code=302,
    )


def _issue_refresh(kakao_refresh: str | None) -> str | None:
    """카카오 refresh_token을 담은 우리 refresh_token(서명+암호화)을 만든다."""
    if not kakao_refresh:
        return None
    return _sign({"rt": encrypt_token(kakao_refresh), "exp": int(time.time()) + _REFRESH_TTL})


async def token(request: Request) -> JSONResponse:
    """POST /oauth/token — 우리 code/refresh_token을 **카카오 access_token**으로 교환."""
    try:
        form = dict(await request.form())
    except Exception:
        form = {}
    grant = form.get("grant_type")

    if grant == "authorization_code":
        data = _verify(str(form.get("code", "")))
        if data is None:
            return _token_err("invalid_grant", "인가 코드가 만료됐거나 올바르지 않습니다.")
        req_ru = form.get("redirect_uri")
        if req_ru and req_ru != data.get("ru"):
            return _token_err("invalid_grant", "redirect_uri mismatch")
        challenge = str(data.get("cc") or "")
        if challenge:
            verifier = str(form.get("code_verifier", ""))
            if not verifier or not _pkce_ok(verifier, challenge):
                return _token_err("invalid_grant", "PKCE 검증 실패")
        access_token = decrypt_token(str(data.get("at") or "")) if data.get("at") else None
        if not access_token:
            return _token_err("invalid_grant", "토큰을 복구하지 못했습니다.")
        refresh_token = decrypt_token(str(data.get("rt") or "")) if data.get("rt") else None
        body: dict = {
            "access_token": access_token,
            "token_type": "Bearer",
            "scope": kakao.DEFAULT_SCOPE,
        }
        if data.get("ei"):
            body["expires_in"] = data["ei"]
        issued_refresh = _issue_refresh(refresh_token)
        if issued_refresh:
            body["refresh_token"] = issued_refresh
        return JSONResponse(body)

    if grant == "refresh_token":
        data = _verify(str(form.get("refresh_token", "")))
        if data is None:
            return _token_err("invalid_grant", "refresh_token이 만료됐거나 올바르지 않습니다.")
        kakao_refresh = decrypt_token(str(data.get("rt") or "")) if data.get("rt") else None
        if not kakao_refresh:
            return _token_err("invalid_grant", "refresh 토큰을 복구하지 못했습니다.")
        new_resp = await kakao.refresh_access_token(
            kakao_refresh, settings.kakao_rest_api_key, settings.kakao_client_secret
        )
        access_token = new_resp.get("access_token")
        if not access_token:
            return _token_err("invalid_grant", "카카오 토큰 갱신에 실패했습니다.")
        body = {
            "access_token": access_token,
            "token_type": "Bearer",
            "scope": kakao.DEFAULT_SCOPE,
        }
        if new_resp.get("expires_in"):
            body["expires_in"] = new_resp["expires_in"]
        # 카카오가 새 refresh를 주면 그걸로 회전, 아니면 기존 유지.
        issued_refresh = _issue_refresh(new_resp.get("refresh_token") or kakao_refresh)
        if issued_refresh:
            body["refresh_token"] = issued_refresh
        return JSONResponse(body)

    return _token_err("unsupported_grant_type", f"grant_type={grant}")


def register_oauth_server(mcp) -> None:
    """자체 OAuth 인증서버 라우트를 등록한다."""
    mcp.custom_route("/.well-known/oauth-authorization-server", methods=["GET"])(
        authorization_server_metadata
    )
    mcp.custom_route("/oauth/register", methods=["POST"])(register)
    mcp.custom_route("/oauth/authorize", methods=["GET"])(authorize)
    mcp.custom_route("/oauth/kakao/callback", methods=["GET"])(kakao_callback)
    mcp.custom_route("/oauth/token", methods=["POST"])(token)
