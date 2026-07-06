"""카카오 OAuth 초대-참여 링크 + 콜백.

아직 teamplay-talk를 연결하지 않은 친구를 방에 초대할 때 쓴다. 방 맥락(초대 코드)을
**서명해 담은** 카카오 로그인 링크를 보내면, 친구가 클릭 한 번으로
  카카오 로그인/동의 → 우리 콜백 → 방 참여 → 토큰(암호화) 저장
까지 끝난다. PlayMCP broker와 별개로, 우리가 앱 주인(client_id+secret)이므로
직접 code→token 교환을 한다.

신원 상관(correlation) 문제가 없다: "어느 방"은 링크의 서명 state에서, "누구"는
OAuth 콜백의 토큰에서 오므로 콜백 시점에 참여 처리가 완결된다(one-shot).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import time

from starlette.requests import Request
from starlette.responses import HTMLResponse

from . import kakao, kakao_store, storage
from .config import settings

# 초대 링크(state) 유효시간. 친구가 링크를 받고 로그인하는 데 충분한 시간.
_STATE_TTL_SECONDS = 60 * 60 * 24  # 24시간


def _secret() -> bytes:
    """state 서명 키. 진짜 비밀에서만 가져온다(공개 client id 폴백 없음)."""
    raw = settings.invite_state_secret or settings.kakao_client_secret
    if not raw:
        raise RuntimeError(
            "초대 링크 state 서명 키가 없습니다. INVITE_STATE_SECRET 또는 "
            "KAKAO_CLIENT_SECRET을 설정하세요."
        )
    return raw.encode("utf-8")


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(raw: str) -> bytes:
    pad = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode((raw + pad).encode("ascii"))


def _sign_state(payload: dict) -> str:
    """payload를 HMAC 서명해 ``body.sig`` 문자열로 만든다(위조 방지)."""
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(_secret(), body, hashlib.sha256).digest()
    return f"{_b64e(body)}.{_b64e(sig)}"


def _verify_state(token: str) -> dict | None:
    """서명·만료를 확인하고 payload를 돌려준다. 실패 시 None."""
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


def _redirect_uri() -> str:
    """authorize와 token 교환에 **동일하게** 쓰는 콜백 URL.

    이 값이 카카오 콘솔의 '허용된 리다이렉트 URI'에 등록돼 있어야 한다.
    """
    return f"{settings.public_base_url.rstrip('/')}/auth/kakao/callback"


def build_invite_oauth_url(invite_code: str) -> str | None:
    """친구가 클릭하면 인증+방 참여까지 되는 카카오 로그인 링크를 만든다.

    INVITE_OAUTH_ENABLED가 꺼져 있거나 서명 키가 없으면 None을 반환한다.
    """
    if not settings.invite_oauth_enabled:
        return None
    try:
        state = _sign_state(
            {"invite_code": invite_code, "exp": int(time.time()) + _STATE_TTL_SECONDS}
        )
    except RuntimeError:
        return None
    return kakao.build_authorize_url(
        settings.kakao_rest_api_key, _redirect_uri(), state=state
    )


def _page(title: str, message: str, status: int = 200) -> HTMLResponse:
    page = (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)}</title></head>"
        '<body style="font-family:system-ui;max-width:640px;margin:3rem auto;'
        'text-align:center;padding:0 1rem">'
        f"<h1>{html.escape(title)}</h1><p>{html.escape(message)}</p></body></html>"
    )
    return HTMLResponse(page, status_code=status)


async def kakao_callback(request: Request) -> HTMLResponse:
    """GET /auth/kakao/callback?code=..&state=.. — 인증 후 방 참여를 완결한다."""
    if not settings.invite_oauth_enabled:
        return _page("비활성화됨", "카카오 초대 링크 참여는 현재 사용하지 않습니다.", 404)

    code = request.query_params.get("code")
    state = request.query_params.get("state") or ""
    data = _verify_state(state)
    if not code or data is None:
        return _page("링크 오류", "초대 링크가 만료됐거나 올바르지 않습니다. 다시 초대를 받아 주세요.", 400)

    invite_code = str(data.get("invite_code") or "")
    if not invite_code:
        return _page("링크 오류", "초대 정보가 없습니다.", 400)

    # 우리가 직접 code→token 교환 (redirect_uri는 authorize와 동일해야 함)
    token_resp = await kakao.exchange_code_for_token(
        code,
        settings.kakao_rest_api_key,
        _redirect_uri(),
        settings.kakao_client_secret,
    )
    access_token = token_resp.get("access_token")
    if not access_token:
        return _page("인증 실패", "카카오 인증에 실패했습니다. 잠시 후 다시 시도해 주세요.", 400)

    kakao_id, nickname = await kakao.get_user_info(access_token)
    if not kakao_id or kakao_id == "unknown":
        return _page("인증 실패", "카카오 사용자 정보를 확인하지 못했습니다.", 400)

    # 참여 처리(유저 upsert + 방 참여). 방이 없거나 마감이면 None.
    result = storage.join_room(invite_code, nickname, kakao_id)
    if result is None:
        return _page("방을 찾을 수 없음", "초대된 방이 없거나 마감되었습니다.", 404)

    # 알림/캘린더용 토큰 저장(암호화). refresh_token/expires_in도 함께.
    kakao_store.set_kakao_token(
        kakao_id,
        access_token,
        token_resp.get("refresh_token"),
        token_resp.get("expires_in"),
    )

    room = result["room"]
    return _page(
        "참여 완료 🎉",
        f"'{room['name']}' 방에 참여했어요! 이제 카카오로 팀 알림을 받고, 폼에 응답할 수 있습니다. "
        "이 창은 닫아도 됩니다.",
    )


def register_auth_routes(mcp) -> None:
    """카카오 OAuth 초대 콜백 라우트를 등록한다."""
    mcp.custom_route("/auth/kakao/callback", methods=["GET"])(kakao_callback)
