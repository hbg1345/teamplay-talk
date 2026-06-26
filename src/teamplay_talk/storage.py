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


# ── 네이티브 폼/투표 ──────────────────────────────────────────────────

def create_form(
    room_id: int,
    title: str,
    questions: list[dict[str, Any]],
    description: str | None = None,
    anonymous: bool = True,
) -> dict[str, Any]:
    """폼과 질문들을 생성한다. (단일 트랜잭션)

    questions: ``[{"text": str, "qtype": "text"|"single"|"multi", "options": [str]}]``
    Returns: ``{"form": <forms row>, "questions": [<form_questions rows>]}``
    """
    from psycopg.types.json import Json

    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "INSERT INTO forms (room_id, title, description, anonymous) "
                "VALUES (%s, %s, %s, %s) RETURNING *",
                (room_id, title, description, anonymous),
            )
            form = cur.fetchone()

            created_questions = []
            for pos, q in enumerate(questions):
                opts = q.get("options") or None
                cur.execute(
                    "INSERT INTO form_questions (form_id, position, text, qtype, options) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING *",
                    (
                        form["id"],
                        pos,
                        q["text"],
                        q.get("qtype", "single"),
                        Json(opts) if opts is not None else None,
                    ),
                )
                created_questions.append(cur.fetchone())
        c.commit()
    return {"form": form, "questions": created_questions}


def get_form(form_id: int) -> dict[str, Any] | None:
    """폼 + 질문 목록을 반환한다. (폼 렌더링용)"""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM forms WHERE id = %s", (form_id,))
            form = cur.fetchone()
            if form is None:
                return None
            cur.execute(
                "SELECT * FROM form_questions WHERE form_id = %s ORDER BY position",
                (form_id,),
            )
            questions = cur.fetchall()
    return {"form": form, "questions": questions}


def save_response(
    form_id: int,
    answers: list[dict[str, Any]],
    respondent: str | None = None,
) -> int:
    """응답 1건을 저장한다.

    answers: ``[{"question_id": int, "value": str}]`` (복수선택은 같은 question_id로 여러 개)
    Returns: 생성된 response_id
    """
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "INSERT INTO form_responses (form_id, respondent) VALUES (%s, %s) RETURNING id",
                (form_id, respondent),
            )
            response_id = cur.fetchone()["id"]
            for a in answers:
                cur.execute(
                    "INSERT INTO form_answers (response_id, question_id, value) "
                    "VALUES (%s, %s, %s)",
                    (response_id, a["question_id"], a["value"]),
                )
        c.commit()
    return response_id


def get_results(form_id: int) -> dict[str, Any] | None:
    """폼 응답을 질문별로 집계한다.

    객관식: 선택지별 카운트 / 주관식: 답변 텍스트 목록.
    """
    data = get_form(form_id)
    if data is None:
        return None
    form, questions = data["form"], data["questions"]

    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM form_responses WHERE form_id = %s",
                (form_id,),
            )
            total = cur.fetchone()["n"]

            results = []
            for q in questions:
                if q["qtype"] == "text":
                    cur.execute(
                        "SELECT fa.value FROM form_answers fa "
                        "WHERE fa.question_id = %s ORDER BY fa.id",
                        (q["id"],),
                    )
                    answers = [r["value"] for r in cur.fetchall()]
                    results.append(
                        {"question": q["text"], "qtype": q["qtype"], "answers": answers}
                    )
                else:
                    cur.execute(
                        "SELECT fa.value, COUNT(*) AS n FROM form_answers fa "
                        "WHERE fa.question_id = %s GROUP BY fa.value ORDER BY n DESC",
                        (q["id"],),
                    )
                    counts = {r["value"]: r["n"] for r in cur.fetchall()}
                    results.append(
                        {"question": q["text"], "qtype": q["qtype"], "counts": counts}
                    )

    return {
        "form_id": form["id"],
        "title": form["title"],
        "total_responses": total,
        "results": results,
    }


# ── 방 조회/나가기 (카카오 통합) ───────────────────────────────────────

def get_room_by_invite_code(invite_code: str) -> dict[str, Any] | None:
    """초대 코드로 방 단건 조회."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM rooms WHERE invite_code = %s", (invite_code,))
            return cur.fetchone()


def leave_room(invite_code: str, kakao_id: str) -> dict[str, Any] | None:
    """카카오 인증된 사용자를 방에서 제거한다.

    나간 방이 그 사람의 '현재 작업 방'이면 → 남은 방 중 가장 최근 것으로
    포인터를 옮긴다(남은 방 없으면 NULL).

    Returns: 코드가 틀리면 ``None``,
             그 외 ``{"room": ..., "left": bool}`` (left=False면 원래 멤버 아님).
    """
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM rooms WHERE invite_code = %s", (invite_code,))
            room = cur.fetchone()
            if room is None:
                return None
            cur.execute(
                "SELECT id, active_room_id FROM users WHERE kakao_id = %s", (kakao_id,)
            )
            user = cur.fetchone()
            if user is None:
                return {"room": room, "left": False}
            cur.execute(
                "DELETE FROM room_members WHERE room_id = %s AND user_id = %s",
                (room["id"], user["id"]),
            )
            left = cur.rowcount > 0
            # 나간 방이 '현재 작업 방'이면 → 남은 방 중 최근 것으로(없으면 NULL)
            if left and user["active_room_id"] == room["id"]:
                cur.execute(
                    "SELECT room_id FROM room_members WHERE user_id = %s "
                    "ORDER BY joined_at DESC LIMIT 1",
                    (user["id"],),
                )
                nxt = cur.fetchone()
                cur.execute(
                    "UPDATE users SET active_room_id = %s WHERE id = %s",
                    (nxt["room_id"] if nxt else None, user["id"]),
                )
        c.commit()
    return {"room": room, "left": left}


# ── active room (현재 작업 중인 방) ────────────────────────────────────

def upsert_user(kakao_id: str, nickname: str) -> dict[str, Any]:
    """kakao_id로 사용자를 찾고 없으면 생성한다. (헤더 신원 해석용)"""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM users WHERE kakao_id = %s", (kakao_id,))
            user = cur.fetchone()
            if user is None:
                cur.execute(
                    "INSERT INTO users (kakao_id, nickname) VALUES (%s, %s) RETURNING *",
                    (kakao_id, nickname),
                )
                user = cur.fetchone()
        c.commit()
    return user


def set_active_room(user_id: int, room_id: int | None) -> None:
    """사용자의 '현재 작업 방' 포인터를 변경한다. (멤버십은 건드리지 않음)"""
    with conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "UPDATE users SET active_room_id = %s WHERE id = %s",
                (room_id, user_id),
            )
        c.commit()


def get_active_room(user_id: int) -> dict[str, Any] | None:
    """사용자의 현재 작업 방(rooms 행)을 반환한다. 없으면 None."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT r.* FROM rooms r "
                "JOIN users u ON u.active_room_id = r.id WHERE u.id = %s",
                (user_id,),
            )
            return cur.fetchone()


def list_user_rooms(user_id: int) -> list[dict[str, Any]]:
    """사용자가 속한 방 목록 + 역할 + 현재방 여부(is_active)."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT r.id, r.name, r.invite_code, rm.role, "
                "(r.id = u.active_room_id) AS is_active "
                "FROM room_members rm "
                "JOIN rooms r ON r.id = rm.room_id "
                "JOIN users u ON u.id = rm.user_id "
                "WHERE rm.user_id = %s ORDER BY rm.joined_at",
                (user_id,),
            )
            return cur.fetchall()
