"""호출자 신원 해석 — 매 호출 ``Authorization: Bearer`` 헤더의 토큰으로 식별.

두 종류의 토큰을 받는다 (우선순위 순):
1. **우리 개인 토큰** (PlayMCP Key/Token 인증) — 사용자가 ``/connect``에서
   카카오 로그인 후 발급받아 PlayMCP에 붙여넣은 값. sha256 해시로 users 조회.
   → broker 없이도 **매 호출 신원이 "붙는다".**
2. **카카오 access_token** (PlayMCP가 OAuth broker로 헤더에 실어줄 때) — /v2/user/me
   로 kakao_id 확인. broker가 작동하는 환경용 fallback.

둘 다 없으면 ``None`` → 도구는 로그인 링크 fallback.
"""

from __future__ import annotations

import hashlib
import secrets
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


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_personal_token(user_id: int) -> str:
    """사용자에게 개인 액세스 토큰을 발급한다(해시만 저장). 원문은 1회만 노출."""
    token = secrets.token_urlsafe(24)
    storage.set_user_token(user_id, _hash_token(token))
    return token


async def resolve_caller() -> dict[str, Any] | None:
    """헤더 토큰으로 호출자(users 행)를 식별한다. 없으면 None."""
    token = bearer_token()
    if token is None:
        return None

    # 1) 우리 개인 토큰? (PlayMCP Key/Token → 매 호출 신원, broker 불필요)
    user = storage.get_user_by_token_hash(_hash_token(token))
    if user is not None:
        return user

    # 2) 카카오 access_token? (broker가 헤더로 줄 때의 fallback)
    try:
        kakao_id, nickname = await kakao.get_user_info(token)
    except Exception:
        return None
    if not kakao_id or kakao_id == "unknown":
        return None
    user = storage.upsert_user(kakao_id, nickname)
    kakao_store.set_kakao_token(kakao_id, token, None, None)
    return user
