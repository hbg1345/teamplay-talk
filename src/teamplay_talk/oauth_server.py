"""우리 서버 = OAuth 2.1 인가 서버 (PlayMCP가 broker하는 제공자).

흐름:
  1. PlayMCP(클라이언트) → ``/oauth/authorize`` (client_id, redirect_uri, state, PKCE)
  2. 우리가 내부에서 **카카오 로그인**으로 사용자 인증 (고정 콜백 ``/oauth/kakao/callback``)
  3. 우리 **인가코드** 발급 → PlayMCP redirect_uri로 돌려보냄
  4. PlayMCP → ``/oauth/token`` (코드 교환) → 우리 **액세스 토큰** 발급
  5. 이후 PlayMCP가 매 호출 헤더에 그 토큰 → ``identity.resolve_caller`` 가 신원 인식

카카오 redirect URI가 우리 **고정 URL**이라 mcpId 변동/KOE006 문제가 없다.
(카카오 단일 인증 — 구글/Drive는 제거됨.)

저장은 단기 인메모리(단일 워커 가정). 운영 강화 시 DB로 이전.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from urllib.parse import parse_qs, urlencode

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import kakao, kakao_store, storage
from .config import settings
from .identity import issue_personal_token

# login_session_id -> {redirect_uri, state, code_challenge, method, exp}
_sessions: dict[str, dict] = {}
# auth_code -> {user_id, code_challenge, method, redirect_uri, exp}
_codes: dict[str, dict] = {}

_SESSION_TTL = 600  # 10분 (카카오 로그인 완료까지)
_CODE_TTL = 120     # 2분 (PlayMCP의 토큰 교환까지)


def _now() -> float:
    return time.time()


def _gc(store: dict) -> None:
    now = _now()
    for k in [k for k, v in store.items() if v["exp"] < now]:
        store.pop(k, None)


def _oauth_redirect_uri() -> str:
    """우리 OAuth 서버의 카카오 콜백(고정). 카카오 콘솔에 1회 등록 필요."""
    return f"{settings.public_base_url}/oauth/kakao/callback"


def _issue_code(playmcp: dict, user_id: int) -> RedirectResponse:
    """우리 인가코드를 발급하고 PlayMCP redirect_uri로 돌려보낸다."""
    auth_code = secrets.token_urlsafe(24)
    _codes[auth_code] = {
        "user_id": user_id,
        "code_challenge": playmcp.get("code_challenge"),
        "method": playmcp.get("method"),
        "redirect_uri": playmcp["redirect_uri"],
        "exp": _now() + _CODE_TTL,
    }
    params = {"code": auth_code}
    if playmcp.get("state"):
        params["state"] = playmcp["state"]
    return _redirect_back(playmcp["redirect_uri"], params)


def _redirect_back(redirect_uri: str, params: dict) -> RedirectResponse:
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{sep}{urlencode(params)}")


def _valid_redirect(uri: str | None) -> bool:
    """오픈 리다이렉트 방지 — PlayMCP 콜백만 허용."""
    return bool(uri) and uri.startswith("https://playmcp.kakao.com/")


async def authorize(request: Request):
    """OAuth 2.1 인가 요청 — 클라이언트 검증 후 카카오 로그인으로 보낸다."""
    p = request.query_params
    redirect_uri = p.get("redirect_uri")
    if not _valid_redirect(redirect_uri):
        return JSONResponse(
            {"error": "invalid_request", "error_description": "redirect_uri not allowed"}, 400
        )
    if p.get("response_type") != "code":
        return _redirect_back(redirect_uri, _with_state(p, {"error": "unsupported_response_type"}))
    if p.get("client_id") != settings.oauth_client_id:
        return _redirect_back(redirect_uri, _with_state(p, {"error": "unauthorized_client"}))

    sid = secrets.token_urlsafe(24)
    _sessions[sid] = {
        "redirect_uri": redirect_uri,
        "state": p.get("state"),
        "code_challenge": p.get("code_challenge"),
        "method": p.get("code_challenge_method"),
        "exp": _now() + _SESSION_TTL,
    }
    url = kakao.build_authorize_url(settings.kakao_rest_api_key, _oauth_redirect_uri(), state=sid)
    return RedirectResponse(url)


def _with_state(query, extra: dict) -> dict:
    out = dict(extra)
    if query.get("state"):
        out["state"] = query.get("state")
    return out


async def kakao_callback(request: Request):
    """카카오 콜백 — 사용자 인증 후 우리 인가코드 발급, PlayMCP로 리다이렉트."""
    _gc(_sessions)
    _gc(_codes)
    sid = request.query_params.get("state")
    sess = _sessions.pop(sid, None) if sid else None
    if sess is None:
        return HTMLResponse(
            "<h2>인증 세션이 만료되었거나 올바르지 않습니다. 처음부터 다시 시도해 주세요.</h2>", 400
        )

    if err := request.query_params.get("error"):
        return _redirect_back(sess["redirect_uri"], _err(sess, "access_denied", err))
    code_param = request.query_params.get("code")
    if not code_param:
        return _redirect_back(sess["redirect_uri"], _err(sess, "invalid_request", "no code"))

    tokens = await kakao.exchange_code_for_token(
        code_param, settings.kakao_rest_api_key, _oauth_redirect_uri(), settings.kakao_client_secret
    )
    if "access_token" not in tokens:
        return _redirect_back(sess["redirect_uri"], _err(sess, "server_error", "token exchange failed"))

    kakao_id, nickname = await kakao.get_user_info(tokens["access_token"])
    user = storage.upsert_user(kakao_id, nickname)
    kakao_store.set_kakao_token(
        kakao_id, tokens["access_token"], tokens.get("refresh_token"), tokens.get("expires_in")
    )

    return _issue_code(sess, user["id"])


def _err(sess: dict, error: str, desc: str) -> dict:
    out = {"error": error, "error_description": desc}
    if sess.get("state"):
        out["state"] = sess["state"]
    return out


def _client_creds(request: Request, form: dict) -> tuple[str | None, str | None]:
    """client_id/secret을 form 또는 HTTP Basic 헤더에서 꺼낸다."""
    cid, csec = form.get("client_id"), form.get("client_secret")
    auth = request.headers.get("authorization", "")
    if auth.startswith("Basic ") and not (cid and csec):
        try:
            decoded = base64.b64decode(auth[6:]).decode("utf-8")
            cid, _, csec = decoded.partition(":")
        except Exception:
            pass
    return cid, csec


async def token(request: Request):
    """토큰 교환 — 인가코드 → 우리 액세스 토큰."""
    _gc(_codes)
    raw = (await request.body()).decode("utf-8")
    form = {k: v[0] for k, v in parse_qs(raw).items()}

    if form.get("grant_type") != "authorization_code":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    cid, csec = _client_creds(request, form)
    if cid != settings.oauth_client_id:
        return JSONResponse({"error": "invalid_client"}, status_code=401)
    if settings.oauth_client_secret and csec != settings.oauth_client_secret:
        return JSONResponse({"error": "invalid_client"}, status_code=401)

    rec = _codes.pop(form.get("code", ""), None)
    if rec is None:
        return JSONResponse({"error": "invalid_grant", "error_description": "code invalid/expired"}, status_code=400)
    if rec["redirect_uri"] != form.get("redirect_uri"):
        return JSONResponse({"error": "invalid_grant", "error_description": "redirect_uri mismatch"}, status_code=400)

    # PKCE 검증 (challenge가 있으면 필수)
    if rec.get("code_challenge"):
        verifier = form.get("code_verifier", "")
        if rec.get("method") == "S256":
            digest = hashlib.sha256(verifier.encode("utf-8")).digest()
            computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        else:
            computed = verifier
        if computed != rec["code_challenge"]:
            return JSONResponse({"error": "invalid_grant", "error_description": "PKCE failed"}, status_code=400)

    access_token = issue_personal_token(rec["user_id"])
    return JSONResponse(
        {
            "access_token": access_token,
            "token_type": "Bearer",
            "scope": "talk_message profile_nickname",
        }
    )


def register_oauth_routes(mcp) -> None:
    """OAuth 2.1 인가 서버 라우트를 등록한다."""
    mcp.custom_route("/oauth/authorize", methods=["GET"])(authorize)
    mcp.custom_route("/oauth/kakao/callback", methods=["GET"])(kakao_callback)
    mcp.custom_route("/oauth/token", methods=["POST"])(token)
