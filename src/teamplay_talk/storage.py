"""데이터 저장 계층 (PostgreSQL).

``schema.sql`` 의 users / rooms / room_members 테이블에 대한 저장·조회 함수를
제공한다. 도구(tool) 모듈은 이 함수들만 호출하고 SQL을 직접 다루지 않는다.
"""

from __future__ import annotations

import secrets
from typing import Any

from psycopg.rows import dict_row

from .db import conn


def _generate_invite_code() -> str:
    """추측하기 어려운 짧은 초대 코드를 생성한다."""
    return secrets.token_urlsafe(6)


def create_room(
    name: str,
    owner_nickname: str,
    description: str | None = None,
    owner_kakao_id: str | None = None,
) -> dict[str, Any]:
    """방을 생성하고 방장을 멤버(역할: 방장)로 등록한다. (단일 트랜잭션)

    Returns: ``{"room": <rooms row>, "owner": <users row>}``
    """
    code = _generate_invite_code()
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            # 방장 사용자 확보 (kakao_id 있으면 재사용, 없으면 신규)
            owner = None
            if owner_kakao_id:
                cur.execute("SELECT * FROM users WHERE kakao_id = %s", (owner_kakao_id,))
                owner = cur.fetchone()
            if owner is None:
                cur.execute(
                    "INSERT INTO users (kakao_id, nickname) VALUES (%s, %s) RETURNING *",
                    (owner_kakao_id, owner_nickname),
                )
                owner = cur.fetchone()

            # 방 생성
            cur.execute(
                "INSERT INTO rooms (name, owner_id, invite_code, description) "
                "VALUES (%s, %s, %s, %s) RETURNING *",
                (name, owner["id"], code, description),
            )
            room = cur.fetchone()

            # 방장을 멤버로 등록
            cur.execute(
                "INSERT INTO room_members (room_id, user_id, role) VALUES (%s, %s, %s)",
                (room["id"], owner["id"], "방장"),
            )
        c.commit()
    return {"room": room, "owner": owner}


def join_room(
    invite_code: str,
    nickname: str,
    kakao_id: str | None = None,
) -> dict[str, Any] | None:
    """초대 코드로 방에 참여한다.

    Returns: 성공 시 ``{"room": ..., "user": ...}``, 코드가 틀리면 ``None``.
    """
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM rooms WHERE invite_code = %s", (invite_code,))
            room = cur.fetchone()
            if room is None:
                return None

            user = None
            if kakao_id:
                cur.execute("SELECT * FROM users WHERE kakao_id = %s", (kakao_id,))
                user = cur.fetchone()
            if user is None:
                cur.execute(
                    "INSERT INTO users (kakao_id, nickname) VALUES (%s, %s) RETURNING *",
                    (kakao_id, nickname),
                )
                user = cur.fetchone()

            # 이미 참여한 경우 중복 추가하지 않음
            cur.execute(
                "INSERT INTO room_members (room_id, user_id) VALUES (%s, %s) "
                "ON CONFLICT (room_id, user_id) DO NOTHING",
                (room["id"], user["id"]),
            )
        c.commit()
    return {"room": room, "user": user}


def get_room(room_id: int) -> dict[str, Any] | None:
    """방 단건 조회."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM rooms WHERE id = %s", (room_id,))
            return cur.fetchone()


def list_members(room_id: int) -> list[dict[str, Any]]:
    """방의 멤버 목록(닉네임·역할·참여시각)을 반환한다."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT u.id, u.nickname, rm.role, rm.joined_at "
                "FROM room_members rm JOIN users u ON u.id = rm.user_id "
                "WHERE rm.room_id = %s ORDER BY rm.joined_at",
                (room_id,),
            )
            return cur.fetchall()
