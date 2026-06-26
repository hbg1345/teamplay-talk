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
    schema_json: dict[str, Any],
    *,
    description: str | None = None,
    anonymous: bool = True,
    creator_user_id: int | None = None,
    closes_at: Any | None = None,
    close_on_all: bool = False,
) -> dict[str, Any]:
    """폼(SurveyJS JSON 정의)을 생성하고 forms 행을 반환한다."""
    from psycopg.types.json import Json

    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "INSERT INTO forms (room_id, title, description, anonymous, "
                "schema_json, creator_user_id, closes_at, close_on_all) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                (room_id, title, description, anonymous, Json(schema_json),
                 creator_user_id, closes_at, close_on_all),
            )
            form = cur.fetchone()
        c.commit()
    return form


def get_form(form_id: int) -> dict[str, Any] | None:
    """폼 단건 조회 (schema_json 포함)."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM forms WHERE id = %s", (form_id,))
            return cur.fetchone()


def save_response(
    form_id: int,
    answers_json: dict[str, Any],
    *,
    member_id: int | None = None,
    respondent: str | None = None,
) -> int:
    """응답 1건(SurveyJS 결과 객체)을 저장한다. Returns response_id."""
    from psycopg.types.json import Json

    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "INSERT INTO form_responses (form_id, respondent, member_id, answers_json) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (form_id, respondent, member_id, Json(answers_json)),
            )
            response_id = cur.fetchone()["id"]
        c.commit()
    return response_id


def get_results(form_id: int) -> dict[str, Any] | None:
    """폼 응답을 SurveyJS element별로 집계한다.

    radiogroup/dropdown=선택지 카운트, checkbox=복수 카운트, ranking=순위점수(1위 높음),
    rating=평균, text/comment=답변 목록. identified 폼이면 멤버별 raw 응답도 포함(매칭용).
    """
    form = get_form(form_id)
    if form is None:
        return None
    schema = form.get("schema_json") or {}
    elements = schema.get("elements", [])

    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT fr.answers_json, fr.member_id, fr.respondent, u.nickname "
                "FROM form_responses fr LEFT JOIN users u ON u.id = fr.member_id "
                "WHERE fr.form_id = %s ORDER BY fr.id",
                (form_id,),
            )
            rows = cur.fetchall()

    responses = [r["answers_json"] or {} for r in rows]
    results = []
    for el in elements:
        name = el.get("name")
        qtype = el.get("type")
        title = el.get("title") or name
        vals = [r.get(name) for r in responses if r.get(name) is not None]
        if qtype in ("radiogroup", "dropdown", "boolean"):
            counts: dict[str, int] = {}
            for v in vals:
                counts[str(v)] = counts.get(str(v), 0) + 1
            results.append({"question": title, "type": qtype, "counts": counts})
        elif qtype == "checkbox":
            counts = {}
            for v in vals:
                for item in v if isinstance(v, list) else [v]:
                    counts[str(item)] = counts.get(str(item), 0) + 1
            results.append({"question": title, "type": qtype, "counts": counts})
        elif qtype == "ranking":
            scores: dict[str, int] = {str(ch): 0 for ch in el.get("choices", [])}
            for v in vals:
                if isinstance(v, list):
                    n = len(v)
                    for i, item in enumerate(v):
                        scores[str(item)] = scores.get(str(item), 0) + (n - i)
            results.append({"question": title, "type": qtype, "ranking_scores": scores})
        elif qtype == "rating":
            nums = [float(v) for v in vals if isinstance(v, (int, float))]
            results.append({
                "question": title, "type": qtype,
                "average": (sum(nums) / len(nums)) if nums else None,
                "values": nums,
            })
        else:  # text / comment
            results.append({"question": title, "type": qtype, "answers": [str(v) for v in vals]})

    out: dict[str, Any] = {
        "form_id": form["id"],
        "title": form["title"],
        "closed": form["closed"],
        "total_responses": len(rows),
        "results": results,
    }
    if not form["anonymous"]:
        out["responses"] = [
            {"member_id": r["member_id"], "nickname": r["nickname"], "answers": r["answers_json"] or {}}
            for r in rows
        ]
    return out


def create_invites(form_id: int, member_ids: list[int]) -> dict[int, str]:
    """멤버별 매직링크 토큰을 생성/갱신하고 {member_id: token} 반환."""
    import secrets

    out: dict[int, str] = {}
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            for mid in member_ids:
                cur.execute(
                    "INSERT INTO form_invites (form_id, member_id, token) VALUES (%s, %s, %s) "
                    "ON CONFLICT (form_id, member_id) DO UPDATE SET token = EXCLUDED.token "
                    "RETURNING token",
                    (form_id, mid, secrets.token_urlsafe(12)),
                )
                out[mid] = cur.fetchone()["token"]
        c.commit()
    return out


def get_invite(token: str) -> dict[str, Any] | None:
    """매직링크 토큰 → {form_id, member_id}."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT form_id, member_id FROM form_invites WHERE token = %s", (token,))
            return cur.fetchone()


def close_form(form_id: int) -> None:
    """폼을 마감한다(수동). nudge는 보내지 않는다 — 닫는 사람이 이미 보고 있으므로."""
    with conn() as c:
        with c.cursor() as cur:
            cur.execute("UPDATE forms SET closed = true WHERE id = %s", (form_id,))
        c.commit()


def get_user(user_id: int) -> dict[str, Any] | None:
    """사용자 단건 조회 (카카오 토큰 포함)."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            return cur.fetchone()


def find_due_forms() -> list[dict[str, Any]]:
    """마감 시각이 지났는데 아직 처리 안 된 폼(스케줄러용)."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id FROM forms WHERE closes_at IS NOT NULL AND closes_at < now() "
                "AND NOT closed AND NOT nudge_sent"
            )
            return cur.fetchall()


def claim_form_for_nudge(form_id: int) -> dict[str, Any] | None:
    """원자적으로 마감+nudge_sent 설정 후 생성자 정보 반환. 이미 처리됐으면 None(중복 방지)."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "UPDATE forms SET closed = true, nudge_sent = true "
                "WHERE id = %s AND NOT nudge_sent "
                "RETURNING creator_user_id, title, room_id",
                (form_id,),
            )
            row = cur.fetchone()
        c.commit()
    return row


def all_members_responded(form_id: int) -> bool:
    """방 멤버 전원이 응답했는지. (식별 폼=중복 멤버 제외, 익명=응답 수 기준)"""
    form = get_form(form_id)
    if form is None:
        return False
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT COUNT(*) AS n FROM room_members WHERE room_id = %s", (form["room_id"],))
            members = cur.fetchone()["n"]
            if form["anonymous"]:
                cur.execute("SELECT COUNT(*) AS n FROM form_responses WHERE form_id = %s", (form_id,))
            else:
                cur.execute(
                    "SELECT COUNT(DISTINCT member_id) AS n FROM form_responses "
                    "WHERE form_id = %s AND member_id IS NOT NULL",
                    (form_id,),
                )
            responded = cur.fetchone()["n"]
    return members > 0 and responded >= members


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


# ── 개인 액세스 토큰 (PlayMCP Key/Token 인증) ─────────────────────────────

def set_user_token(user_id: int, token_hash: str) -> None:
    """사용자의 개인 액세스 토큰(해시)을 저장/갱신한다."""
    with conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "UPDATE users SET token_hash = %s WHERE id = %s", (token_hash, user_id)
            )
        c.commit()


def get_user_by_token_hash(token_hash: str) -> dict[str, Any] | None:
    """개인 토큰 해시로 사용자를 조회한다. (매 호출 신원 해석용)"""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM users WHERE token_hash = %s", (token_hash,))
            return cur.fetchone()


