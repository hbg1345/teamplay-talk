"""카카오 토큰 저장/조회 (users 테이블의 kakao_* 컬럼).

신원(kakao_id)은 친구의 storage.create_room/join_room이 이미 users에 넣는다.
이 모듈은 거기에 **알림용 토큰**을 얹고, 방 멤버의 토큰을 모아 조회한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg.rows import dict_row

from .db import conn


def set_kakao_token(
    kakao_id: str,
    access_token: str,
    refresh_token: str | None,
    expires_in: int | None = None,
) -> None:
    """이미 존재하는 user(kakao_id)에 카카오 토큰을 저장/갱신한다."""
    expires_at = None
    if expires_in:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
    with conn() as c:
        with c.cursor() as cur:
            # refresh_token이 None이면 기존 값을 보존한다(헤더-브로커 토큰엔
            # refresh_token이 없을 수 있어, 링크 로그인 때 받은 걸 지우지 않도록).
            cur.execute(
                "UPDATE users SET kakao_access_token = %s, "
                "kakao_refresh_token = COALESCE(%s, kakao_refresh_token), "
                "kakao_token_expires_at = %s WHERE kakao_id = %s",
                (access_token, refresh_token, expires_at, kakao_id),
            )
        c.commit()


def list_members_with_tokens(room_id: int) -> list[dict[str, Any]]:
    """방 멤버 중 카카오 토큰을 가진 사람들(알림 대상)을 반환한다."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT u.id, u.kakao_id, u.nickname, u.kakao_access_token, u.kakao_refresh_token "
                "FROM room_members rm JOIN users u ON u.id = rm.user_id "
                "WHERE rm.room_id = %s AND u.kakao_access_token IS NOT NULL "
                "ORDER BY rm.joined_at",
                (room_id,),
            )
            return cur.fetchall()
