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


def is_room_member(room_id: int, user_id: int) -> bool:
    """사용자가 방 멤버인지 확인한다."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT 1 FROM room_members WHERE room_id = %s AND user_id = %s",
                (room_id, user_id),
            )
            return cur.fetchone() is not None


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


def list_room_forms(room_id: int) -> list[dict[str, Any]]:
    """방에 속한 모든 폼과 응답 수를 최신순으로 반환한다."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT f.id, f.room_id, f.title, f.description, f.anonymous, f.closed, "
                "f.created_at, f.schema_json, f.creator_user_id, f.closes_at, "
                "f.close_on_all, f.nudge_sent, COUNT(fr.id)::int AS total_responses "
                "FROM forms f "
                "LEFT JOIN form_responses fr ON fr.form_id = f.id "
                "WHERE f.room_id = %s "
                "GROUP BY f.id "
                "ORDER BY f.created_at DESC",
                (room_id,),
            )
            return cur.fetchall()


def list_form_response_rows(form_id: int) -> list[dict[str, Any]]:
    """SurveyJS Dashboard에 넘길 폼 응답 원본 행을 반환한다."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT fr.answers_json, fr.member_id, fr.respondent, fr.submitted_at, "
                "u.nickname "
                "FROM form_responses fr "
                "LEFT JOIN users u ON u.id = fr.member_id "
                "WHERE fr.form_id = %s ORDER BY fr.id",
                (form_id,),
            )
            return cur.fetchall()


def save_response(
    form_id: int,
    answers_json: dict[str, Any],
    *,
    member_id: int | None = None,
    respondent: str | None = None,
) -> int:
    """응답 1건을 저장한다. **식별 응답(member_id 있음)은 멤버당 1개** — 재제출 시 교체.

    익명 응답(member_id None)은 신원이 없어 중복 제거 불가(여러 번 누적).
    """
    from psycopg.types.json import Json

    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            if member_id is not None:
                # 같은 멤버의 이전 응답 제거 → 1인 1응답(최신만 유지)
                cur.execute(
                    "DELETE FROM form_responses WHERE form_id = %s AND member_id = %s",
                    (form_id, member_id),
                )
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
        elif qtype == "matrixdropdown":  # 가용성 그리드(날짜×시간) — 셀별 O/X 집계
            o_counts: dict[str, int] = {}
            x_counts: dict[str, int] = {}
            for v in vals:
                if not isinstance(v, dict):
                    continue
                for row, cols in v.items():
                    if not isinstance(cols, dict):
                        continue
                    for col, ans in cols.items():
                        key = f"{col} {row}"
                        if ans == "O":
                            o_counts[key] = o_counts.get(key, 0) + 1
                        elif ans == "X":
                            x_counts[key] = x_counts.get(key, 0) + 1
            keys = set(o_counts) | set(x_counts)
            ranked = sorted(keys, key=lambda k: (x_counts.get(k, 0), -o_counts.get(k, 0)))
            best_candidates = [
                k for k in ranked if x_counts.get(k, 0) == 0 and o_counts.get(k, 0) > 0
            ]
            best_score = o_counts.get(best_candidates[0], 0) if best_candidates else 0
            best_slots = [k for k in best_candidates if o_counts.get(k, 0) == best_score]
            best = best_slots[0] if best_slots else None
            results.append({
                "question": title,
                "type": "grid",
                "slots": [
                    {"slot": k, "O": o_counts.get(k, 0), "X": x_counts.get(k, 0)} for k in ranked
                ],
                "best_slot": best,
                "best_slots": best_slots,
                "best_O": best_score,
                "note": (
                    "best_slots = X(절대 불가) 0명 중 O 최다인 모든 동점 시간. "
                    "best_slot은 그중 첫 번째 대표값입니다."
                ),
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


def set_member_role(room_id: int, nickname: str, role: str) -> int:
    """방 멤버(닉네임)의 역할을 기록한다. 갱신된 행 수 반환."""
    with conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "UPDATE room_members SET role = %s WHERE room_id = %s "
                "AND user_id = (SELECT id FROM users WHERE nickname = %s ORDER BY id LIMIT 1)",
                (role, room_id, nickname),
            )
            updated = cur.rowcount
        c.commit()
    return updated


def list_form_recipients(form_id: int) -> list[dict[str, Any]]:
    """식별 폼의 멤버별 (카카오 토큰 + 개인 링크 토큰). 카카오 로그인 한 멤버만."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT u.id, u.nickname, u.kakao_id, u.kakao_access_token, "
                "u.kakao_refresh_token, fi.token AS invite_token "
                "FROM form_invites fi JOIN users u ON u.id = fi.member_id "
                "WHERE fi.form_id = %s AND u.kakao_access_token IS NOT NULL",
                (form_id,),
            )
            return cur.fetchall()


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
# ── 로드맵 (태스크 그래프) ────────────────────────────────────────────────

def _resolve_assignee(
    cur: Any, room_id: int, assignee: str | None
) -> tuple[int | None, str | None]:
    """담당자 문자열을 (user_id, role)로 해석. 방 멤버 닉네임이면 user_id, 아니면 role."""
    name = (assignee or "").strip()
    if not name:
        return None, None
    cur.execute(
        "SELECT u.id FROM room_members rm JOIN users u ON u.id = rm.user_id "
        "WHERE rm.room_id = %s AND lower(u.nickname) = lower(%s) LIMIT 1",
        (room_id, name),
    )
    row = cur.fetchone()
    if row:
        return row["id"], None
    return None, name


def set_roadmap(
    room_id: int,
    tasks: list[dict[str, Any]],
    edges: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """방의 로드맵(태스크 그래프)을 통째로 생성/교체한다. (단일 트랜잭션)

    tasks: ``[{key, title, details?, assignee?, start_at?, end_at?, status?}]``
    edges: ``[{from: key, to: key}]`` (선행→후행)
    key는 호출 측 임시 식별자 → 실제 task id로 매핑해 엣지를 연결한다.
    Returns: ``get_roadmap(room_id)`` 결과.
    """
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            # 기존 로드맵 제거(task_deps는 FK CASCADE로 함께 삭제)
            cur.execute("DELETE FROM tasks WHERE room_id = %s", (room_id,))

            key_to_id: dict[str, int] = {}
            for pos, t in enumerate(tasks):
                user_id, role = _resolve_assignee(cur, room_id, t.get("assignee"))
                cur.execute(
                    "INSERT INTO tasks (room_id, title, details, assignee_user_id, "
                    "assignee_role, start_at, end_at, status, position) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (
                        room_id, t["title"], t.get("details"), user_id, role,
                        t.get("start_at"), t.get("end_at"),
                        t.get("status", "todo"), pos,
                    ),
                )
                key_to_id[str(t.get("key", t["title"]))] = cur.fetchone()["id"]

            for e in edges or []:
                f = key_to_id.get(str(e.get("from")))
                to = key_to_id.get(str(e.get("to")))
                if f and to and f != to:
                    cur.execute(
                        "INSERT INTO task_deps (room_id, from_task_id, to_task_id) "
                        "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (room_id, f, to),
                    )
        c.commit()
    return get_roadmap(room_id)


def get_roadmap(room_id: int) -> dict[str, Any]:
    """방의 로드맵을 반환한다: ``{"tasks": [...], "edges": [...]}``.

    각 task에 담당자 닉네임(assignee_nickname) 또는 역할(assignee_role)이 포함된다.
    """
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT t.id, t.title, t.details, t.status, t.start_at, t.end_at, "
                "t.position, t.assignee_role, u.nickname AS assignee_nickname "
                "FROM tasks t LEFT JOIN users u ON u.id = t.assignee_user_id "
                "WHERE t.room_id = %s ORDER BY t.position, t.id",
                (room_id,),
            )
            tasks = cur.fetchall()
            cur.execute(
                "SELECT from_task_id, to_task_id FROM task_deps WHERE room_id = %s",
                (room_id,),
            )
            edges = cur.fetchall()
    return {"tasks": tasks, "edges": edges}


def update_task(
    task_id: int,
    *,
    title: str | None = None,
    details: str | None = None,
    assignee: str | None = None,
    start_at: Any | None = None,
    end_at: Any | None = None,
    status: str | None = None,
) -> dict[str, Any] | None:
    """태스크 1개를 수정한다(지정한 필드만). 없으면 None."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT room_id FROM tasks WHERE id = %s", (task_id,))
            row = cur.fetchone()
            if row is None:
                return None
            room_id = row["room_id"]

            sets: list[str] = []
            vals: list[Any] = []
            if title is not None:
                sets.append("title = %s"); vals.append(title)
            if details is not None:
                sets.append("details = %s"); vals.append(details)
            if start_at is not None:
                sets.append("start_at = %s"); vals.append(start_at)
            if end_at is not None:
                sets.append("end_at = %s"); vals.append(end_at)
            if status is not None:
                sets.append("status = %s"); vals.append(status)
            if assignee is not None:
                user_id, role = _resolve_assignee(cur, room_id, assignee)
                sets.append("assignee_user_id = %s"); vals.append(user_id)
                sets.append("assignee_role = %s"); vals.append(role)

            if not sets:
                cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
                return cur.fetchone()

            vals.append(task_id)
            cur.execute(
                f"UPDATE tasks SET {', '.join(sets)} WHERE id = %s RETURNING *", vals
            )
            updated = cur.fetchone()
        c.commit()
    return updated


def add_task(
    room_id: int,
    *,
    title: str,
    details: str | None = None,
    assignee: str | None = None,
    start_at: Any | None = None,
    end_at: Any | None = None,
    status: str = "todo",
    after_ids: list[int] | None = None,
    before_ids: list[int] | None = None,
) -> dict[str, Any]:
    """로드맵에 태스크 1개를 추가하고 (선택) 그래프에 연결한다.

    after_ids: 이 태스크의 **선행** 태스크들(각각 → 새 태스크 엣지)
    before_ids: 이 태스크의 **후행** 태스크들(새 태스크 → 각각 엣지)
    같은 방의 태스크 id만 연결된다. Returns: 생성된 task 행.
    """
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            user_id, role = _resolve_assignee(cur, room_id, assignee)
            cur.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 AS p FROM tasks WHERE room_id = %s",
                (room_id,),
            )
            pos = cur.fetchone()["p"]
            cur.execute(
                "INSERT INTO tasks (room_id, title, details, assignee_user_id, "
                "assignee_role, start_at, end_at, status, position) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                (room_id, title, details, user_id, role, start_at, end_at, status, pos),
            )
            task = cur.fetchone()
            new_id = task["id"]

            def _in_room(tid: int) -> bool:
                cur.execute(
                    "SELECT 1 FROM tasks WHERE id = %s AND room_id = %s", (tid, room_id)
                )
                return cur.fetchone() is not None

            for p in after_ids or []:
                if p != new_id and _in_room(p):
                    cur.execute(
                        "INSERT INTO task_deps (room_id, from_task_id, to_task_id) "
                        "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (room_id, p, new_id),
                    )
            for s in before_ids or []:
                if s != new_id and _in_room(s):
                    cur.execute(
                        "INSERT INTO task_deps (room_id, from_task_id, to_task_id) "
                        "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (room_id, new_id, s),
                    )
        c.commit()
    return task


def delete_task(task_id: int, room_id: int) -> int | None:
    """방의 태스크 1개를 삭제한다(연결 엣지는 FK CASCADE로 함께 삭제). 없으면 None."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "DELETE FROM tasks WHERE id = %s AND room_id = %s RETURNING id",
                (task_id, room_id),
            )
            row = cur.fetchone()
        c.commit()
    return row["id"] if row else None
