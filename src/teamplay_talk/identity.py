"""호출자 신원 해석 — ``Authorization: Bearer`` 헤더의 카카오 access_token으로 식별.

PlayMCP가 카카오 OAuth를 broker하면 매 호출 헤더에 카카오 토큰이 실려오고,
그러면 로그인 없이 바로 신원이 잡힌다(구글 Drive 때와 동일한 broker 방식).
헤더가 없으면 도구는 "카카오 연결 필요"를 반환한다.
"""

from __future__ import annotations

from typing import Any

from fastmcp.server.dependencies import get_http_headers

from . import kakao, kakao_store, storage


def bearer_token() -> str | None:
    """현재 MCP 요청의 Authorization 헤더에서 Bearer 토큰을 꺼낸다."""
    headers = get_http_headers(include=["authorization"])
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        return token or None
    return None


async def resolve_caller() -> dict[str, Any] | None:
    """헤더의 카카오 access_token으로 호출자(users 행)를 식별한다. 없으면 None.

    토큰으로 ``/v2/user/me`` 를 조회해 kakao_id/nickname 을 얻고, users 에
    upsert 한다. 알림용으로 토큰도 저장(브로커가 멤버별 토큰을 모으는 효과).
    """
    token = bearer_token()
    if token is None:
        return None
    try:
        kakao_id, nickname = await kakao.get_user_info(token)
    except Exception:
        return None
    if not kakao_id or kakao_id == "unknown":
        return None
    user = storage.upsert_user(kakao_id, nickname)
    kakao_store.set_kakao_token(kakao_id, token, None, None)
    return user
