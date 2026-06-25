"""카카오 OAuth 웹 라우트 (🅐 방식).

흐름:
  1. 도구(create_room/join_room)가 ``/auth/kakao/login?state=<intent>`` 링크 반환
  2. ``/auth/kakao/login`` → 카카오 인가 페이지로 redirect (state 보존)
  3. ``/auth/kakao/callback`` → 토큰 교환 → kakao_id/nickname 조회
       → state의 의도대로 방 생성/참여 → **토큰 저장**(알림용) → 결과 페이지
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from . import kakao, kakao_store, storage
from .config import settings
from .intents import decode_intent


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{title}</title></head>
        <body style="font-family:system-ui,-apple-system,sans-serif;max-width:600px;margin:3rem auto;padding:0 1rem;color:#222">
        {body}</body></html>""",
        status_code=status,
    )


async def login(request: Request) -> RedirectResponse:
    """카카오 인가 페이지로 redirect (state 그대로 전달)."""
    state = request.query_params.get("state") or None
    url = kakao.build_authorize_url(
        settings.kakao_rest_api_key,
        settings.kakao_redirect_uri,
        state=state,
    )
    return RedirectResponse(url)


async def callback(request: Request) -> HTMLResponse:
    """토큰 교환 + 의도(state) 수행 + 토큰 저장."""
    if err := request.query_params.get("error"):
        desc = request.query_params.get("error_description", "")
        return _page("로그인 실패", f"<h2>로그인 에러: {err}</h2><p>{desc}</p>", 400)

    code = request.query_params.get("code")
    if not code:
        return _page("오류", "<h2>인가 코드가 없습니다.</h2>", 400)

    tokens = await kakao.exchange_code_for_token(
        code,
        settings.kakao_rest_api_key,
        settings.kakao_redirect_uri,
        settings.kakao_client_secret,
    )
    if "access_token" not in tokens:
        return _page("토큰 실패", f"<h2>토큰 교환 실패</h2><pre>{tokens}</pre>", 400)

    kakao_id, nickname = await kakao.get_user_info(tokens["access_token"])

    intent: dict = {}
    if state := request.query_params.get("state"):
        try:
            intent = decode_intent(state)
        except Exception:
            intent = {}
    action = intent.get("a")

    if action == "create":
        result = storage.create_room(
            name=intent.get("name", "새 방"),
            owner_nickname=nickname,
            description=intent.get("desc"),
            owner_kakao_id=kakao_id,
        )
        room = result["room"]
        body = (
            f"<h2>✅ 방 생성 완료</h2>"
            f"<p><b>{room['name']}</b></p>"
            f"<p>초대 코드: <code style='font-size:1.3rem;background:#f2f2f2;padding:.2rem .5rem;border-radius:6px'>{room['invite_code']}</code></p>"
            f"<p>이 코드를 팀원에게 공유하세요. (팀원도 이 코드로 로그인 참여)</p>"
        )
    elif action == "join":
        result = storage.join_room(
            invite_code=intent.get("code", ""),
            nickname=nickname,
            kakao_id=kakao_id,
        )
        if result is None:
            body = "<h2>❌ 유효하지 않은 초대 코드</h2>"
        else:
            body = (
                f"<h2>✅ '{result['room']['name']}' 참여 완료</h2>"
                f"<p>{nickname}님, 이제 이 방의 카카오 알림을 받습니다.</p>"
            )
    elif action == "leave":
        result = storage.leave_room(invite_code=intent.get("code", ""), kakao_id=kakao_id)
        if result is None:
            body = "<h2>❌ 유효하지 않은 초대 코드</h2>"
        elif not result["left"]:
            body = "<h2>이미 이 방의 멤버가 아닙니다.</h2>"
        else:
            body = (
                f"<h2>✅ '{result['room']['name']}' 나가기 완료</h2>"
                f"<p>{nickname}님이 방에서 나갔습니다. (이 방 알림은 더 이상 받지 않음)</p>"
            )
    else:
        body = f"<h2>✅ 카카오 연결 완료</h2><p>{nickname}님 연결됨.</p>"

    # 알림용 토큰 저장 (위 create/join이 user(kakao_id)를 이미 만들어둠)
    kakao_store.set_kakao_token(
        kakao_id,
        tokens["access_token"],
        tokens.get("refresh_token"),
        tokens.get("expires_in"),
    )
    return _page("완료", body)


def register_auth_routes(mcp) -> None:
    """카카오 OAuth 라우트를 MCP 서버(Starlette)에 등록한다."""
    mcp.custom_route("/auth/kakao/login", methods=["GET"])(login)
    mcp.custom_route("/auth/kakao/callback", methods=["GET"])(callback)
