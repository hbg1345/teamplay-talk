"""데이터 저장 계층 (PostgreSQL).

``schema.sql`` 의 users / rooms / room_members 테이블에 대한 저장·조회 함수를
제공한다. 도구(tool) 모듈은 이 함수들만 호출하고 SQL을 직접 다루지 않는다.
"""

from __future__ import annotations

import re
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
            cur.execute(
                "SELECT * FROM rooms WHERE invite_code = %s AND status = 'active'",
                (invite_code,),
            )
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


def get_room(room_id: int, *, include_deleted: bool = False) -> dict[str, Any] | None:
    """방 단건 조회."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            if include_deleted:
                cur.execute("SELECT * FROM rooms WHERE id = %s", (room_id,))
            else:
                cur.execute("SELECT * FROM rooms WHERE id = %s AND status = 'active'", (room_id,))
            return cur.fetchone()


def is_room_member(room_id: int, user_id: int) -> bool:
    """사용자가 방 멤버인지 확인한다."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT 1 FROM room_members rm "
                "JOIN rooms r ON r.id = rm.room_id "
                "WHERE rm.room_id = %s AND rm.user_id = %s AND r.status = 'active'",
                (room_id, user_id),
            )
            return cur.fetchone() is not None


def list_members(room_id: int) -> list[dict[str, Any]]:
    """방의 멤버 목록(닉네임·역할·참여시각)을 반환한다."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT u.id, u.nickname, rm.role, rm.joined_at "
                "FROM room_members rm "
                "JOIN rooms r ON r.id = rm.room_id "
                "JOIN users u ON u.id = rm.user_id "
                "WHERE rm.room_id = %s AND r.status = 'active' ORDER BY rm.joined_at",
                (room_id,),
            )
            return cur.fetchall()


def is_form_member(form_id: int, user_id: int) -> bool:
    """사용자가 폼이 속한 active room의 멤버인지 확인한다."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT 1 FROM forms f "
                "JOIN rooms r ON r.id = f.room_id "
                "JOIN room_members rm ON rm.room_id = f.room_id AND rm.user_id = %s "
                "WHERE f.id = %s AND r.status = 'active'",
                (user_id, form_id),
            )
            return cur.fetchone() is not None


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
            cur.execute(
                "SELECT f.* FROM forms f JOIN rooms r ON r.id = f.room_id "
                "WHERE f.id = %s AND r.status = 'active'",
                (form_id,),
            )
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
                "JOIN rooms r ON r.id = f.room_id "
                "LEFT JOIN form_responses fr ON fr.form_id = f.id "
                "WHERE f.room_id = %s AND r.status = 'active' "
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
                "JOIN forms f ON f.id = fr.form_id "
                "JOIN rooms r ON r.id = f.room_id "
                "LEFT JOIN users u ON u.id = fr.member_id "
                "WHERE fr.form_id = %s AND r.status = 'active' ORDER BY fr.id",
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
                cur.execute(
                    "INSERT INTO form_responses (form_id, respondent, member_id, answers_json) "
                    "VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (form_id, member_id) WHERE member_id IS NOT NULL "
                    "DO UPDATE SET respondent = EXCLUDED.respondent, "
                    "answers_json = EXCLUDED.answers_json, submitted_at = now() "
                    "RETURNING id",
                    (form_id, respondent, member_id, Json(answers_json)),
                )
            else:
                cur.execute(
                    "INSERT INTO form_responses (form_id, respondent, member_id, answers_json) "
                    "VALUES (%s, %s, %s, %s) RETURNING id",
                    (form_id, respondent, member_id, Json(answers_json)),
                )
            response_id = cur.fetchone()["id"]
        c.commit()
    return response_id


def _ranked_counts(counts: dict[str, int]) -> list[dict[str, Any]]:
    return [
        {"choice": choice, "count": count}
        for choice, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _choice_outcome(counts: dict[str, int], *, multi: bool = False) -> dict[str, Any]:
    ranked = _ranked_counts(counts)
    total = sum(counts.values())
    if not ranked or ranked[0]["count"] <= 0:
        return {
            "kind": "no_responses",
            "winners": [],
            "is_tie": False,
            "needs_tiebreaker": False,
            "total_votes": total,
            "ranked": ranked,
        }
    top_count = ranked[0]["count"]
    winners = [r["choice"] for r in ranked if r["count"] == top_count]
    is_tie = len(winners) > 1
    return {
        "kind": "multi_choice_leaders" if multi else ("tie" if is_tie else "single_winner"),
        "winners": winners,
        "top_choices": ranked[:3],
        "is_tie": is_tie,
        "needs_tiebreaker": is_tie and not multi,
        "total_votes": total,
        "ranked": ranked,
    }


def _score_outcome(scores: dict[str, int]) -> dict[str, Any]:
    ranked = [
        {"choice": choice, "score": score}
        for choice, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    ]
    if not ranked or ranked[0]["score"] <= 0:
        return {
            "kind": "no_responses",
            "winners": [],
            "is_tie": False,
            "needs_tiebreaker": False,
            "ranked": ranked,
        }
    top_score = ranked[0]["score"]
    winners = [r["choice"] for r in ranked if r["score"] == top_score]
    is_tie = len(winners) > 1
    return {
        "kind": "ranking_tie" if is_tie else "ranking_winner",
        "winners": winners,
        "top_choices": ranked[:3],
        "is_tie": is_tie,
        "needs_tiebreaker": is_tie,
        "ranked": ranked,
    }


def _infer_workflow_kind(form: dict[str, Any], elements: list[dict[str, Any]]) -> str:
    schema = form.get("schema_json") or {}
    explicit = schema.get("_workflow_kind")
    if explicit:
        return str(explicit)
    if any(e.get("type") == "matrixdropdown" and e.get("name") == "availability" for e in elements):
        return "meeting_time"
    if any(e.get("type") == "ranking" and e.get("name") == "roles" for e in elements):
        return "role_assignment"
    text = " ".join(
        str(part or "")
        for part in [
            form.get("title"),
            form.get("description"),
            *[e.get("title") for e in elements],
        ]
    )
    lowered = text.lower()
    if any(k in text for k in ["장소", "위치", "역", "상권", "약속"]):
        return "location"
    if any(k in text for k in ["우선순위", "먼저", "기능", "범위", "스코프", "중요"]):
        return "priority"
    if any(k in text for k in ["회고", "만족", "분위기", "익명 피드백"]):
        return "retro"
    if any(k in lowered for k in ["roadmap", "task", "todo"]):
        return "roadmap_decision"
    return "general_decision"


def _primary_outcome(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    for result in results:
        outcome = result.get("outcome")
        if isinstance(outcome, dict):
            return outcome
    return None


def _suggest_next_actions(
    workflow_kind: str,
    results: list[dict[str, Any]],
    *,
    form_id: int,
) -> list[str]:
    outcome = _primary_outcome(results) or {}
    needs_tiebreaker = bool(outcome.get("needs_tiebreaker"))
    if workflow_kind == "role_assignment":
        return [
            f"finalize_roles(form_id={form_id})로 난이도 균형 역할 매칭 계산",
            "팀장에게 멤버별 note와 배정안을 보여주고 확인",
            "확정되면 set_roles로 방 멤버 역할 저장 및 공지",
            "build_roadmap에서 assignee에 역할명을 넣어 개인별 태스크 자동 연결",
        ]
    if workflow_kind == "meeting_time":
        return [
            "best_slots 중 팀장이 확정한 시간을 notify_room으로 공지",
            "확정 시간이 정해지면 calendar_create_room_event로 전원 톡캘린더 등록",
            "회의 전 daily_task_digest 또는 notify_room으로 준비물 리마인드",
        ]
    if workflow_kind == "location":
        return [
            "location_1~location_5와 기타 의견을 모아 같은 역·상권·동네를 정규화",
            "카카오맵 MCP가 있으면 장소명·역명·주소 확인과 중복 후보 정규화에만 보조적으로 사용",
            "카카오맵 MCP가 없으면 '카카오맵 MCP가 있으면 장소명/주소 확인이 더 정확해진다'고 말하고 제출 후보만 정리",
            "정규화 후보로 create_poll(복수선택) 본투표 생성",
            "본투표 결과가 나오면 선택된 장소를 notify_room으로 공지",
        ]
    if workflow_kind == "priority":
        actions = [
            "상위 항목을 build_roadmap 또는 add_task로 로드맵에 반영",
            "역할이 확정돼 있으면 태스크 assignee에 역할명을 넣어 담당자 자동 연결",
            "동점/범위 충돌이 있으면 create_poll로 결선 또는 스코프 축소 투표",
        ]
        if needs_tiebreaker:
            actions.insert(0, "동점 후보만 추려 create_poll로 결선 투표 생성")
        return actions
    if workflow_kind == "roadmap_decision":
        return [
            "주관식 답변을 AI가 태스크 후보/수정사항/리스크로 정규화",
            "여러 개인 실행 항목은 decompose_roadmap으로 milestone 아래 todo로 반영",
            "단건 수정/추가는 add_task 또는 update_task로 로드맵에 반영",
            "의견이 갈린 항목은 create_poll로 우선순위/채택 여부를 투표",
            "역할이 확정돼 있으면 태스크 assignee에 역할명이나 닉네임을 넣어 담당자 자동 연결",
            "member_tasks로 개인별 이번 주 할일을 확인하고 daily_task_digest로 공지",
        ]
    if workflow_kind == "daily_checkin":
        return [
            f"apply_daily_checkin(form_id={form_id}, dry_run=true)로 밀린 일/오늘 일/앞으로 예정된 일 완료 반영안 확인",
            f"확정되면 apply_daily_checkin(form_id={form_id}, dry_run=false)로 todo 상태 반영",
            "daily_report로 팀 전체 상태/남은 밀린 일/기타 메모 리포트 생성",
            "밀린 항목은 update_task로 일정/담당 조정",
        ]
    if workflow_kind == "retro":
        return [
            "주관식 답변을 요약해 개선 액션을 add_task로 등록",
            "팀 분위기/기여도 이슈가 있으면 익명 피드백 후속 폼 생성",
            "결과 요약을 notify_room으로 공유할지 팀장에게 확인",
        ]
    actions = [
        "결정 결과를 notify_room으로 팀에 공지",
        "결정된 항목이 작업이면 build_roadmap/add_task/update_task에 반영",
        "room_dashboard로 결정 기록 확인",
    ]
    if needs_tiebreaker:
        actions.insert(0, "동점 후보만 추려 create_poll로 결선 투표 생성")
    return actions


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
            results.append({
                "question": title,
                "type": qtype,
                "counts": counts,
                "outcome": _choice_outcome(counts),
            })
        elif qtype == "checkbox":
            counts = {}
            for v in vals:
                for item in v if isinstance(v, list) else [v]:
                    counts[str(item)] = counts.get(str(item), 0) + 1
            results.append({
                "question": title,
                "type": qtype,
                "counts": counts,
                "outcome": _choice_outcome(counts, multi=True),
            })
        elif qtype == "ranking":
            scores: dict[str, int] = {str(ch): 0 for ch in el.get("choices", [])}
            for v in vals:
                if isinstance(v, list):
                    n = len(v)
                    for i, item in enumerate(v):
                        scores[str(item)] = scores.get(str(item), 0) + (n - i)
            results.append({
                "question": title,
                "type": qtype,
                "ranking_scores": scores,
                "outcome": _score_outcome(scores),
            })
        elif qtype == "rating":
            nums = [float(v) for v in vals if isinstance(v, (int, float))]
            results.append({
                "question": title, "type": qtype,
                "average": (sum(nums) / len(nums)) if nums else None,
                "values": nums,
                "outcome": {
                    "kind": "rating_average",
                    "average": (sum(nums) / len(nums)) if nums else None,
                    "response_count": len(nums),
                },
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
                "outcome": {
                    "kind": "meeting_time",
                    "winners": best_slots,
                    "best_slot": best,
                    "is_tie": len(best_slots) > 1,
                    "needs_tiebreaker": False,
                    "best_O": best_score,
                },
                "note": (
                    "best_slots = X(절대 불가) 0명 중 O 최다인 모든 동점 시간. "
                    "best_slot은 그중 첫 번째 대표값입니다."
                ),
            })
        else:  # text / comment
            answers = [str(v) for v in vals]
            results.append({
                "question": title,
                "type": qtype,
                "answers": answers,
                "outcome": {
                    "kind": "free_text",
                    "answer_count": len(answers),
                    "needs_synthesis": True,
                },
            })

    workflow_kind = _infer_workflow_kind(form, elements)
    primary_outcome = _primary_outcome(results)
    out: dict[str, Any] = {
        "form_id": form["id"],
        "title": form["title"],
        "closed": form["closed"],
        "total_responses": len(rows),
        "results": results,
        "workflow_kind": workflow_kind,
        "outcome": primary_outcome,
        "suggested_next_actions": _suggest_next_actions(
            workflow_kind, results, form_id=form["id"]
        ),
    }
    if schema.get("_workflow_stage"):
        out["workflow_stage"] = schema.get("_workflow_stage")
    if schema.get("_workflow_scope"):
        out["workflow_scope"] = schema.get("_workflow_scope")
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
            cur.execute(
                "SELECT fi.form_id, fi.member_id FROM form_invites fi "
                "JOIN forms f ON f.id = fi.form_id "
                "JOIN rooms r ON r.id = f.room_id "
                "JOIN room_members rm ON rm.room_id = f.room_id AND rm.user_id = fi.member_id "
                "WHERE fi.token = %s AND r.status = 'active'",
                (token,),
            )
            return cur.fetchone()


def close_form(form_id: int) -> None:
    """폼을 마감한다(수동). nudge는 보내지 않는다 — 닫는 사람이 이미 보고 있으므로."""
    with conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "UPDATE forms f SET closed = true "
                "FROM rooms r WHERE r.id = f.room_id AND f.id = %s AND r.status = 'active'",
                (form_id,),
            )
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
                "SELECT f.id FROM forms f JOIN rooms r ON r.id = f.room_id "
                "WHERE f.closes_at IS NOT NULL AND f.closes_at < now() "
                "AND NOT f.closed AND NOT f.nudge_sent AND r.status = 'active'"
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
                "UPDATE room_members rm SET role = %s "
                "FROM rooms r WHERE r.id = rm.room_id AND rm.room_id = %s "
                "AND r.status = 'active' "
                "AND rm.user_id = (SELECT id FROM users WHERE nickname = %s ORDER BY id LIMIT 1)",
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
                "FROM form_invites fi "
                "JOIN forms f ON f.id = fi.form_id "
                "JOIN rooms r ON r.id = f.room_id "
                "JOIN room_members rm ON rm.room_id = f.room_id AND rm.user_id = fi.member_id "
                "JOIN users u ON u.id = fi.member_id "
                "WHERE fi.form_id = %s AND r.status = 'active' "
                "AND u.kakao_access_token IS NOT NULL",
                (form_id,),
            )
            return cur.fetchall()


# ── 방 조회/나가기 (카카오 통합) ───────────────────────────────────────

def get_room_by_invite_code(invite_code: str) -> dict[str, Any] | None:
    """초대 코드로 방 단건 조회."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM rooms WHERE invite_code = %s AND status = 'active'",
                (invite_code,),
            )
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
            cur.execute(
                "SELECT * FROM rooms WHERE invite_code = %s AND status = 'active'",
                (invite_code,),
            )
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
                    "SELECT rm.room_id FROM room_members rm "
                    "JOIN rooms r ON r.id = rm.room_id "
                    "WHERE rm.user_id = %s AND r.status = 'active' "
                    "ORDER BY joined_at DESC LIMIT 1",
                    (user["id"],),
                )
                nxt = cur.fetchone()
                cur.execute(
                    "UPDATE users SET active_room_id = %s WHERE id = %s",
                    (nxt["room_id"] if nxt else None, user["id"]),
                )
            empty_scheduled = False
            purge_after = None
            if left:
                cur.execute("SELECT COUNT(*) AS n FROM room_members WHERE room_id = %s", (room["id"],))
                remaining = cur.fetchone()["n"]
                if remaining == 0:
                    cur.execute(
                        "UPDATE rooms SET status = 'deleting', deleted_at = now(), "
                        "purge_after = now() + interval '7 days', deleted_by_user_id = %s, "
                        "delete_reason = 'empty_room' "
                        "WHERE id = %s AND status = 'active' RETURNING purge_after",
                        (user["id"], room["id"]),
                    )
                    deleted = cur.fetchone()
                    empty_scheduled = deleted is not None
                    purge_after = deleted["purge_after"] if deleted else None
        c.commit()
    return {
        "room": room,
        "left": left,
        "empty_scheduled": empty_scheduled,
        "purge_after": purge_after,
    }


def delete_room(invite_code: str, user_id: int) -> dict[str, Any] | None:
    """방장이 방을 7일 삭제 대기 상태로 전환한다. 초대 코드가 틀리면 None."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM rooms WHERE invite_code = %s", (invite_code,))
            room = cur.fetchone()
            if room is None:
                return None
            if room["owner_id"] != user_id:
                return {"room": room, "deleted": False, "reason": "not_owner"}
            if room.get("status") == "deleting":
                return {"room": room, "deleted": False, "reason": "already_deleting"}

            cur.execute(
                "UPDATE rooms SET status = 'deleting', deleted_at = now(), "
                "purge_after = now() + interval '7 days', deleted_by_user_id = %s, "
                "delete_reason = 'owner_deleted' "
                "WHERE id = %s AND status = 'active' RETURNING *",
                (user_id, room["id"]),
            )
            deleted = cur.fetchone()
            cur.execute(
                "UPDATE users SET active_room_id = NULL WHERE active_room_id = %s",
                (room["id"],),
            )
        c.commit()
    return {"room": deleted or room, "deleted": deleted is not None}


def restore_room(invite_code: str, user_id: int) -> dict[str, Any] | None:
    """방장이 삭제 유예 기간 안의 방을 복구한다. 초대 코드가 틀리면 None."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM rooms WHERE invite_code = %s", (invite_code,))
            room = cur.fetchone()
            if room is None:
                return None
            if room["owner_id"] != user_id:
                return {"room": room, "restored": False, "reason": "not_owner"}
            if room.get("status") == "active":
                return {"room": room, "restored": False, "reason": "already_active"}
            cur.execute(
                "SELECT 1 WHERE %s::timestamptz > now()",
                (room.get("purge_after"),),
            )
            if cur.fetchone() is None:
                return {"room": room, "restored": False, "reason": "expired"}

            cur.execute(
                "UPDATE rooms SET status = 'active', deleted_at = NULL, purge_after = NULL, "
                "deleted_by_user_id = NULL, delete_reason = NULL "
                "WHERE id = %s AND status = 'deleting' RETURNING *",
                (room["id"],),
            )
            restored = cur.fetchone()
            if restored and room.get("delete_reason") == "empty_room":
                cur.execute(
                    "INSERT INTO room_members (room_id, user_id, role) VALUES (%s, %s, %s) "
                    "ON CONFLICT (room_id, user_id) DO UPDATE SET role = EXCLUDED.role",
                    (room["id"], user_id, "방장"),
                )
            cur.execute("UPDATE users SET active_room_id = %s WHERE id = %s", (room["id"], user_id))
        c.commit()
    return {"room": restored or room, "restored": restored is not None}


def find_rooms_to_purge(limit: int = 100) -> list[dict[str, Any]]:
    """삭제 유예 기간이 지난 방 목록(스케줄러용)."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, name, invite_code FROM rooms "
                "WHERE status = 'deleting' AND purge_after IS NOT NULL AND purge_after <= now() "
                "ORDER BY purge_after LIMIT %s",
                (limit,),
            )
            return cur.fetchall()


def purge_room(room_id: int) -> dict[str, Any] | None:
    """삭제 유예 기간이 지난 방을 완전 삭제한다. FK cascade로 하위 데이터도 제거된다."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "DELETE FROM rooms "
                "WHERE id = %s AND status = 'deleting' "
                "AND purge_after IS NOT NULL AND purge_after <= now() "
                "RETURNING id, name, invite_code",
                (room_id,),
            )
            row = cur.fetchone()
        c.commit()
    return row


def list_active_rooms() -> list[dict[str, Any]]:
    """스케줄러용 active room 목록."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, name, owner_id FROM rooms WHERE status = 'active' ORDER BY id")
            return cur.fetchall()


def claim_task_digest(room_id: int, user_id: int, digest_date: Any) -> bool:
    """room/user/date digest 발송권을 1회만 획득한다."""
    with conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "INSERT INTO task_digest_sends (room_id, user_id, digest_date) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (room_id, user_id, digest_date),
            )
            claimed = cur.rowcount > 0
        c.commit()
    return claimed


def get_daily_checkin_send(room_id: int, checkin_date: Any) -> dict[str, Any] | None:
    """room/date 체크인 폼 발송 기록을 조회한다."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT room_id, checkin_date, form_id, sent_at "
                "FROM daily_checkin_sends WHERE room_id = %s AND checkin_date = %s",
                (room_id, checkin_date),
            )
            return cur.fetchone()


def record_daily_checkin_send(room_id: int, checkin_date: Any, form_id: int) -> bool:
    """room/date 체크인 폼 생성/발송 기록을 1회만 남긴다."""
    with conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "INSERT INTO daily_checkin_sends (room_id, checkin_date, form_id) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (room_id, checkin_date, form_id),
            )
            created = cur.rowcount > 0
        c.commit()
    return created


def upsert_daily_report(
    room_id: int,
    *,
    report_date: Any,
    title: str,
    summary: str,
    payload: dict[str, Any],
    created_by_user_id: int | None = None,
) -> dict[str, Any]:
    """방의 일일 리포트를 저장/갱신한다."""
    from psycopg.types.json import Json

    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "INSERT INTO daily_reports "
                "(room_id, report_date, title, summary, payload, created_by_user_id) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (room_id, report_date) DO UPDATE SET "
                "title = EXCLUDED.title, summary = EXCLUDED.summary, "
                "payload = EXCLUDED.payload, created_by_user_id = EXCLUDED.created_by_user_id, "
                "created_at = now() "
                "RETURNING id, room_id, report_date, title, summary, payload, "
                "created_by_user_id, created_at",
                (room_id, report_date, title, summary, Json(payload), created_by_user_id),
            )
            row = cur.fetchone()
        c.commit()
    return row


def list_daily_reports(room_id: int, limit: int = 7) -> list[dict[str, Any]]:
    """방의 일일 리포트를 최신순으로 반환한다."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, room_id, report_date, title, summary, payload, "
                "created_by_user_id, created_at "
                "FROM daily_reports WHERE room_id = %s "
                "ORDER BY report_date DESC, created_at DESC LIMIT %s",
                (room_id, limit),
            )
            return cur.fetchall()


def claim_daily_report_send(room_id: int, report_date: Any) -> bool:
    """room/date daily report 발송권을 1회만 획득한다."""
    with conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "INSERT INTO daily_report_sends (room_id, report_date) "
                "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (room_id, report_date),
            )
            claimed = cur.rowcount > 0
        c.commit()
    return claimed


def record_room_decision(
    room_id: int,
    *,
    kind: str,
    title: str,
    summary: str,
    payload: dict[str, Any] | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """방의 확정 결정을 기록한다."""
    from psycopg.types.json import Json

    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "INSERT INTO room_decisions (room_id, kind, title, summary, payload, source) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING *",
                (room_id, kind, title, summary, Json(payload or {}), source),
            )
            row = cur.fetchone()
        c.commit()
    return row


def list_room_decisions(room_id: int, limit: int = 20) -> list[dict[str, Any]]:
    """방의 결정 기록을 최신순으로 반환한다."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, room_id, kind, title, summary, payload, source, created_at "
                "FROM room_decisions WHERE room_id = %s "
                "ORDER BY created_at DESC, id DESC LIMIT %s",
                (room_id, limit),
            )
            return cur.fetchall()


def latest_room_decisions(room_id: int) -> dict[str, dict[str, Any]]:
    """kind별 최신 결정 기록."""
    out: dict[str, dict[str, Any]] = {}
    for decision in list_room_decisions(room_id, limit=50):
        out.setdefault(decision["kind"], decision)
    return out


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
                "JOIN users u ON u.active_room_id = r.id "
                "JOIN room_members rm ON rm.room_id = r.id AND rm.user_id = u.id "
                "WHERE u.id = %s AND r.status = 'active'",
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
                "WHERE rm.user_id = %s AND r.status = 'active' ORDER BY rm.joined_at",
                (user_id,),
            )
            return cur.fetchall()
# ── 로드맵 (태스크 그래프) ────────────────────────────────────────────────

def _normalize_assignee_label(value: str) -> str:
    """역할/닉네임 비교용 정규화. 공백·구분기호 차이를 줄인다."""
    return re.sub(r"[\s·ㆍ•\-_]+", "", value.strip().lower())


def _role_tokens(value: str | None) -> list[str]:
    """'백엔드, 발표' 같은 역할 문자열을 비교 가능한 토큰 목록으로 나눈다."""
    if not value:
        return []
    return [
        part.strip(" \t\r\n·ㆍ•-*")
        for part in re.split(r"[,/;|&\n]+", value)
        if part.strip(" \t\r\n·ㆍ•-*")
    ]


def _matching_role_member_ids(cur: Any, room_id: int, role_name: str) -> list[int]:
    """역할명에 매칭되는 방 멤버 id 목록을 반환한다."""
    normalized = _normalize_assignee_label(role_name)
    if not normalized:
        return []
    cur.execute(
        "SELECT u.id, rm.role FROM room_members rm JOIN users u ON u.id = rm.user_id "
        "WHERE rm.room_id = %s AND rm.role IS NOT NULL",
        (room_id,),
    )
    exact_matches: list[int] = []
    fuzzy_matches: list[int] = []
    for member in cur.fetchall():
        role = str(member.get("role") or "")
        tokens = _role_tokens(role)
        labels = tokens + [role]
        normalized_labels = [_normalize_assignee_label(label) for label in labels if label]
        if normalized in normalized_labels:
            exact_matches.append(member["id"])
            continue
        if any(normalized and (normalized in label or label in normalized) for label in normalized_labels):
            fuzzy_matches.append(member["id"])
    exact_unique = list(dict.fromkeys(exact_matches))
    if exact_unique:
        return exact_unique
    return list(dict.fromkeys(fuzzy_matches))


def _resolve_assignee(cur: Any, room_id: int, assignee: str | None) -> tuple[int | None, str | None]:
    """담당자 문자열을 (user_id, role)로 해석한다.

    우선 닉네임을 정확히 매칭하고, 실패하면 room_members.role에 저장된 역할 토큰과
    매칭한다. 역할로 1명만 식별되면 user_id와 원래 역할명을 같이 저장해
    "역할 기반으로 실제 담당자에 연결"되도록 한다.
    """
    name = (assignee or "").strip()
    if not name:
        return None, None
    normalized = _normalize_assignee_label(name)
    cur.execute(
        "SELECT u.id FROM room_members rm JOIN users u ON u.id = rm.user_id "
        "WHERE rm.room_id = %s AND lower(u.nickname) = lower(%s) LIMIT 1",
        (room_id, name),
    )
    row = cur.fetchone()
    if row:
        return row["id"], None

    matches = _matching_role_member_ids(cur, room_id, name)
    if len(matches) == 1:
        return matches[0], name
    return None, name


def sync_task_assignees_by_roles(room_id: int) -> dict[str, Any]:
    """역할명으로만 저장된 todo를 현재 room_members.role 기준으로 실제 멤버에 연결한다.

    같은 역할을 여러 명이 맡으면 현재 todo 수가 적은 멤버에게 순서대로 분배한다.
    """
    mapped: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT assignee_user_id, COUNT(*)::int AS n FROM tasks "
                "WHERE room_id = %s AND task_type = 'todo' AND assignee_user_id IS NOT NULL "
                "GROUP BY assignee_user_id",
                (room_id,),
            )
            loads = {row["assignee_user_id"]: row["n"] for row in cur.fetchall()}
            cur.execute(
                "SELECT id, title, assignee_role FROM tasks "
                "WHERE room_id = %s AND task_type = 'todo' "
                "AND assignee_user_id IS NULL AND assignee_role IS NOT NULL "
                "ORDER BY position, id",
                (room_id,),
            )
            rows = cur.fetchall()
            for task in rows:
                role = str(task.get("assignee_role") or "")
                candidates = _matching_role_member_ids(cur, room_id, role)
                if not candidates:
                    unmatched.append({
                        "task_id": task["id"],
                        "title": task["title"],
                        "assignee_role": role,
                        "reason": "이 역할을 가진 방 멤버가 아직 없습니다.",
                    })
                    continue
                chosen = min(candidates, key=lambda mid: (loads.get(mid, 0), mid))
                cur.execute(
                    "UPDATE tasks SET assignee_user_id = %s WHERE id = %s RETURNING id, title",
                    (chosen, task["id"]),
                )
                loads[chosen] = loads.get(chosen, 0) + 1
                cur.execute("SELECT nickname FROM users WHERE id = %s", (chosen,))
                user = cur.fetchone()
                mapped.append({
                    "task_id": task["id"],
                    "title": task["title"],
                    "assignee_role": role,
                    "assignee_user_id": chosen,
                    "nickname": user["nickname"] if user else None,
                    "candidate_count": len(candidates),
                })
        c.commit()
    return {
        "mapped_count": len(mapped),
        "unmatched_count": len(unmatched),
        "mapped": mapped,
        "unmatched": unmatched,
    }


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
                task_type = str(t.get("task_type") or t.get("kind") or "milestone")
                if task_type not in {"milestone", "todo"}:
                    task_type = "milestone"
                cur.execute(
                    "INSERT INTO tasks (room_id, title, details, assignee_user_id, "
                    "assignee_role, start_at, end_at, status, position, task_type) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (
                        room_id, t["title"], t.get("details"), user_id, role,
                        t.get("start_at"), t.get("end_at"),
                        t.get("status", "todo"), pos, task_type,
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
                "t.position, t.task_type, t.parent_task_id, "
                "t.assignee_user_id, t.assignee_role, "
                "u.nickname AS assignee_nickname, rm.role AS assignee_member_role, "
                "pt.title AS parent_title "
                "FROM tasks t "
                "LEFT JOIN tasks pt ON pt.id = t.parent_task_id "
                "LEFT JOIN users u ON u.id = t.assignee_user_id "
                "LEFT JOIN room_members rm ON rm.room_id = t.room_id "
                "AND rm.user_id = t.assignee_user_id "
                "WHERE t.room_id = %s ORDER BY t.position, t.id",
                (room_id,),
            )
            tasks = cur.fetchall()
            cur.execute(
                "SELECT from_task_id, to_task_id FROM task_deps WHERE room_id = %s",
                (room_id,),
            )
            edges = cur.fetchall()
            cur.execute(
                "SELECT u.id, u.nickname, rm.role "
                "FROM room_members rm JOIN users u ON u.id = rm.user_id "
                "WHERE rm.room_id = %s ORDER BY rm.joined_at",
                (room_id,),
            )
            members = cur.fetchall()
    return {"tasks": tasks, "edges": edges, "members": members}


def update_task(
    task_id: int,
    room_id: int,
    *,
    title: str | None = None,
    details: str | None = None,
    assignee: str | None = None,
    start_at: Any | None = None,
    end_at: Any | None = None,
    status: str | None = None,
    task_type: str | None = None,
    parent_task_id: int | None = None,
) -> dict[str, Any] | None:
    """태스크 1개를 수정한다(지정한 필드만). 없으면 None."""
    with conn() as c:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT room_id FROM tasks WHERE id = %s AND room_id = %s", (task_id, room_id))
            row = cur.fetchone()
            if row is None:
                return None

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
            if task_type is not None:
                normalized_type = task_type if task_type in {"milestone", "todo"} else "todo"
                sets.append("task_type = %s"); vals.append(normalized_type)
            if parent_task_id is not None:
                cur.execute(
                    "SELECT 1 FROM tasks WHERE id = %s AND room_id = %s",
                    (parent_task_id, room_id),
                )
                if cur.fetchone() is None:
                    return None
                sets.append("parent_task_id = %s"); vals.append(parent_task_id)
            if assignee is not None:
                user_id, role = _resolve_assignee(cur, room_id, assignee)
                sets.append("assignee_user_id = %s"); vals.append(user_id)
                sets.append("assignee_role = %s"); vals.append(role)

            if not sets:
                cur.execute("SELECT * FROM tasks WHERE id = %s AND room_id = %s", (task_id, room_id))
                return cur.fetchone()

            vals.extend([task_id, room_id])
            cur.execute(
                f"UPDATE tasks SET {', '.join(sets)} WHERE id = %s AND room_id = %s RETURNING *",
                vals,
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
    task_type: str = "todo",
    parent_task_id: int | None = None,
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
            normalized_type = task_type if task_type in {"milestone", "todo"} else "todo"
            if parent_task_id is not None:
                cur.execute(
                    "SELECT 1 FROM tasks WHERE id = %s AND room_id = %s",
                    (parent_task_id, room_id),
                )
                if cur.fetchone() is None:
                    parent_task_id = None
            cur.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 AS p FROM tasks WHERE room_id = %s",
                (room_id,),
            )
            pos = cur.fetchone()["p"]
            cur.execute(
                "INSERT INTO tasks (room_id, title, details, assignee_user_id, "
                "assignee_role, start_at, end_at, status, position, task_type, parent_task_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                (
                    room_id, title, details, user_id, role, start_at, end_at, status, pos,
                    normalized_type, parent_task_id,
                ),
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
