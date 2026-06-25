"""호출자 신원 해석 — 헤더(카카오-브로커) 우선, 없으면 None(로그인 fallback).

PlayMCP가 카카오 OAuth를 대행하면, 매 도구 호출의 ``Authorization: Bearer``
헤더에 호출자의 카카오 access_token이 실려온다. 이 모듈은 그 토큰으로
호출자가 누구인지(kakao_id) 알아내고 ``users`` 행을 확보한다.

- 헤더에 카카오 토큰이 있으면 → 신원 확정 → 도구는 **로그인 없이** 바로 동작
- 헤더가 없으면(브로커 미적용/웹 접근) → ``None`` → 도구는 기존 로그인 링크 fallback

덤으로, 식별과 동시에 그 토큰을 알림용으로 저장한다(멤버가 호출만 해도
notify 대상 토큰이 확보됨).
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
    """헤더의 카카오 토큰으로 호출자(users 행)를 식별한다. 없으면 None.

    식별에 성공하면 users 행을 upsert하고, 해당 토큰을 알림용으로 저장한다.
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
    # 알림용 토큰 저장 (브로커 토큰엔 refresh가 없을 수 있어 access만; store가 보존)
    kakao_store.set_kakao_token(kakao_id, token, None, None)
    return user
