"""역할 분배 도구 (③ AI 결정형).

흐름: assign_roles(AI가 만든 책임 카드+난이도) → 선호/회피 폼 → send_form 개인별 →
멤버 선호 → finalize_roles(전체 책임 카드를 난이도 균형으로 배분) → 팀장 확인 → set_roles.

핵심:
- **전체집합 커버**: 모든 책임 카드가 누군가에게 배정된다(멤버<카드면 한 명이 여러 책임).
- **난이도 균형**: 각 멤버의 난이도 합이 비슷하게 (LPT 그리디).
- **선호/회피 반영**: 동률일 때 그 책임을 선호한 멤버에게, 회피한 멤버는 뒤로.
- 난이도 점수는 **멤버 폼엔 안 보이고**(균형 배분용), 매칭은 서버에서 결정적으로.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import kakao_store, storage
from .guards import require_form, require_room

_BAD_GENERIC_ROLES = {
    "팀원",
    "담당자",
    "작업자",
    "참여자",
    "대회 주제 선정",
    "아이디어 브레인스토밍",
    "최종 제출",
}

_FINAL_ROLE_MARKERS = ("담당", "리드", "총괄", "매니저", "관리자")


def _norm_label(value: str) -> str:
    return "".join(ch for ch in value.strip().lower() if ch.isalnum())


def _is_task_like_role(name: str) -> bool:
    """역할이 아니라 로드맵 단계/할일처럼 보이는 이름을 잡는다."""
    stripped = name.strip()
    if stripped in _BAD_GENERIC_ROLES:
        return True
    task_like_phrases = {
        "주제 선정",
        "아이디어 브레인스토밍",
        "테스트 및 피드백",
        "최종 제출",
        "결과 제출",
        "중간 점검",
        "최종 점검",
    }
    return stripped in task_like_phrases


def _looks_like_final_role_bundle(name: str) -> bool:
    """책임 카드가 아니라 사람에게 붙일 최종 역할명처럼 보이는 이름을 잡는다."""
    stripped = name.strip()
    return any(stripped.endswith(marker) for marker in _FINAL_ROLE_MARKERS)


def _role_design_brief(
    roadmap: dict[str, Any],
    member_count: int,
) -> dict[str, Any]:
    """AI가 고정 역할명 없이 책임 카드를 설계하도록 넘기는 구조화된 지침."""
    tasks = roadmap.get("tasks", [])
    task_lines = [
        {
            "id": task.get("id"),
            "title": task.get("title"),
            "details": task.get("details"),
            "start_at": str(task.get("start_at") or ""),
            "end_at": str(task.get("end_at") or ""),
        }
        for task in tasks
        if (task.get("task_type") or "milestone") == "milestone"
    ]
    card_bounds = _responsibility_card_bounds(member_count)
    return {
        "principle": (
            "처음부터 큰 역할명을 정하지 않는다. 로드맵을 읽고, 최종 산출물을 만들기 위해 필요한 "
            "책임 카드를 MECE하게 분해한 뒤 난이도와 연관도를 붙인다. 최종 역할 묶음은 팀원 응답 후 배정 단계에서 만든다."
        ),
        "roadmap_milestones": task_lines,
        "team_size": member_count,
        "responsibility_card_count": card_bounds,
        "preference_limits_if_preferred_count": _preference_limits(card_bounds["preferred"]),
        "role_design_steps": [
            "1. 최종 산출물을 한 문장으로 정의한다.",
            "2. 각 마일스톤에서 빠지면 안 되는 책임 단위를 뽑는다.",
            "3. 책임 카드는 팀원 수의 1~2배 범위로 만든다. preferred 개수에 최대한 맞춘다.",
            "4. 너무 작은 할일은 합치고, 너무 큰 책임은 둘로 나눈다.",
            "5. 카드명은 2~14자 안팎의 명사구로 만들고, 로드맵 단계명과 똑같이 쓰지 않는다.",
            "6. 각 카드는 서로 겹치지 않게 만들고, 전체 로드맵 책임이 빠지지 않게 한다.",
            "7. slots는 호환 필드다. 특별히 공동 책임이 필요한 경우가 아니면 1로 둔다. 큰 일은 slots를 늘리기보다 책임 카드를 나눈다.",
            "8. 난이도 8 이상이거나 실습·제작·테스트처럼 혼자 하기 무거운 카드는 finalize 단계에서 helper가 붙을 수 있다.",
        ],
        "difficulty_rubric": {
            "base": 3,
            "effort": "작업량이 많거나 여러 마일스톤에 걸치면 +1~3",
            "ambiguity": "정답이 불명확하고 판단이 많이 필요하면 +1~2",
            "dependency": "다른 역할이 이 결과를 받아야 하면 +1~2",
            "deadline_risk": "마감 직전 품질을 좌우하면 +1~2",
            "communication": "팀 조율·외부 확인이 많으면 +1",
            "range": "최종 difficulty는 1~10 정수. 멤버에게 보여주지 않고 균형 배분에만 쓴다.",
        },
        "slot_rubric": (
            "slots는 과거 호환용이다. 책임 카드 방식에서는 기본 1. 병목이면 slots를 올리기보다 "
            "작업을 더 작은 책임 카드로 분리한다."
        ),
        "hard_rules": [
            "로드맵 단계명을 그대로 역할명으로 쓰지 않는다.",
            "방장·팀장·관리자 같은 운영 지위는 프로젝트 실행 역할로 보지 않는다.",
            "프로젝트 텍스트에 없는 기술명·직무명을 끼워 넣지 않는다.",
            "책임 카드 개수는 team_size의 1~2배 범위를 벗어나지 않는다.",
            "각 책임 카드는 난이도와 업무량이 너무 가볍거나 무겁지 않게 조정한다.",
            "'담당', '리드', '총괄' 같은 최종 역할명 표현을 카드명에 붙이지 않는다.",
            "책임 카드 목록을 만들면 곧바로 role_manage(action='start')에 roles로 다시 넣는다.",
        ],
        "output_schema": [
            {"name": "프로젝트 어휘로 만든 책임 카드명", "difficulty": "1~10", "slots": "대부분 1"}
        ],
    }


def _responsibility_card_bounds(member_count: int) -> dict[str, int]:
    """팀원 수의 1~2배 범위에서 책임 카드 목표치를 계산한다."""
    size = max(1, int(member_count or 1))
    min_count = max(2, size)
    max_count = max(min_count, min(12, size * 2))
    preferred = round(size * 1.5)
    preferred = min(max(preferred, min_count), max_count)
    return {"min": min_count, "max": max_count, "preferred": preferred}


def _preference_limits(card_count: int) -> dict[str, int]:
    """책임 카드 수에 맞춰 캐주얼한 선호/회피 선택 개수를 정한다."""
    count = max(1, int(card_count or 1))
    if count <= 2:
        want_max = 1
    elif count <= 4:
        want_max = 2
    elif count <= 8:
        want_max = 3
    else:
        want_max = 4
    avoid_max = 0 if count <= 1 else (1 if count <= 8 else 2)
    return {
        "want_max": min(want_max, count),
        "avoid_max": min(avoid_max, max(0, count - 1)),
    }


def _validate_role_names(
    names: list[str],
    roadmap: dict[str, Any],
    member_count: int,
) -> dict[str, Any] | None:
    task_titles = [str(t.get("title") or "") for t in roadmap.get("tasks", [])]
    normalized_task_titles = {_norm_label(title) for title in task_titles}
    exact_task_matches = [
        name for name in names
        if _norm_label(name) in normalized_task_titles and _norm_label(name)
    ]
    task_like = [name for name in names if _is_task_like_role(name)]
    final_role_like = [name for name in names if _looks_like_final_role_bundle(name)]
    bad = sorted(set(exact_task_matches + task_like + final_role_like), key=names.index)
    if not bad:
        return None
    return {
        "ok": False,
        "error": (
            "역할 후보가 로드맵 단계/할일명 또는 최종 역할명처럼 보입니다. 이 단계에서는 사람에게 붙일 "
            "역할 묶음이 아니라, 선호도 조사용 책임 카드를 만들어야 합니다."
        ),
        "invalid_roles": bad,
        "roadmap_task_titles": task_titles,
        "role_design_brief": _role_design_brief(roadmap, member_count),
        "role_design_rule": (
            "로드맵 단계명=할일, 책임 카드=선호도 조사용 작업 책임 단위, 최종 역할명=배정 후 사람별 묶음 이름. "
            "'담당/리드/총괄' 표현은 finalize 이후 배정 결과에 붙이고, 지금은 책임 카드명만 넣으세요."
        ),
    }


class Role(BaseModel):
    """책임 카드 1개 (이름 + 난이도)."""

    name: str = Field(description="프로젝트 산출물에서 직접 도출한 책임 카드 이름. 담당/리드/총괄 같은 최종 역할명은 쓰지 않는다.")
    difficulty: int = Field(
        default=5,
        ge=1,
        le=10,
        description=(
            "난이도·업무량 1~10. 멤버에겐 안 보이고 균형 배분에만 쓰인다. "
            "작업량, 불확실성, 의존도, 마감 리스크가 클수록 높게 준다."
        ),
    )
    slots: int = Field(
        default=1,
        ge=1,
        le=10,
        description=(
            "호환 필드. 책임 카드 방식에서는 기본 1. 병목이거나 함께 진행이 필요하면 2로 둘 수 있지만, "
            "서버는 owner 1명을 두고 helper를 별도로 제안한다."
        ),
    )


class RoleAssignment(BaseModel):
    """역할 배정 1건 (set_roles용)."""

    nickname: str = Field(description="멤버 닉네임")
    role: str = Field(description="배정할 역할(여러 개면 ', '로 연결)")


class RoleHelperAssignment(BaseModel):
    """무거운 책임 카드의 보조 배정 1건."""

    card: str = Field(description="함께 진행할 책임 카드명")
    owner: str = Field(description="메인 담당 멤버 닉네임")
    helper: str = Field(description="보조/함께 진행 멤버 닉네임")
    reason: str | None = Field(default=None, description="보조를 붙인 이유")


def _compact_roles(roles: list[str]) -> list[str]:
    out: list[str] = []
    for role in dict.fromkeys(roles):
        count = roles.count(role)
        out.append(f"{role} x{count}" if count > 1 else role)
    return out


def _balanced_assign(
    roles: list[str],
    difficulties: dict[str, int],
    prefs: dict[str, list[str]],
    avoids: dict[str, set[str]] | None = None,
    slots: dict[str, int] | None = None,
) -> tuple[dict[str, list[str]], dict[str, int]]:
    """모든 책임 카드를 멤버에 배분(전체집합 커버) + 난이도 합 균형 + 선호/회피 반영.

    slots가 2 이상인 카드는 여러 자리로 확장한다. 같은 카드는 가능하면 서로
    다른 멤버에게 먼저 퍼뜨리고, 멤버가 부족할 때만 한 사람이 같은 역할을 중복 담당한다.
    무거운 카드부터(LPT) 가장 덜 일한 멤버에게 — 동률이면 선호/회피를 반영한다.
    return: ({멤버: [역할들]}, {멤버: 난이도합}). 멤버<역할이면 한 명이 여러 역할.
    """
    members = list(prefs.keys())
    loads = {m: 0 for m in members}
    assigned: dict[str, list[str]] = {m: [] for m in members}
    slot_counts = {role: max(1, int((slots or {}).get(role, 1))) for role in roles}
    role_units = [
        role for role in roles for _ in range(slot_counts.get(role, 1))
    ]

    def pref_rank(member: str, role: str) -> int:
        try:
            return prefs[member].index(role)
        except ValueError:
            return len(roles)  # 선호 안 한 역할은 최하 순위

    avoid_sets = avoids or {}

    for role in sorted(role_units, key=lambda r: -difficulties.get(r, 5)):
        d = difficulties.get(role, 5)
        best = min(
            members,
            key=lambda m: (
                role in assigned[m],
                loads[m] + d,
                role in avoid_sets.get(m, set()),
                pref_rank(m, role),
                loads[m],
            ),
        )
        assigned[best].append(role)
        loads[best] += d
    return assigned, loads


def _helper_candidates(
    roles: list[str],
    difficulties: dict[str, int],
    prefs: dict[str, list[str]],
    avoids: dict[str, set[str]],
    assigned: dict[str, list[str]],
    loads: dict[str, int],
    slots: dict[str, int] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """무거운 책임 카드에 helper를 제안한다.

    저장 역할은 owner 카드만 유지하고, helper는 공지/결정기록용 제안으로만 둔다.
    이렇게 해야 todo의 역할명 매칭이 보조자에게 잘못 흘러가지 않는다.
    """
    members = list(assigned.keys())
    helper_loads = {member: 0 for member in members}
    if len(members) < 2:
        return [], helper_loads

    owner_by_role: dict[str, str] = {}
    for member, member_roles in assigned.items():
        for role in member_roles:
            owner_by_role.setdefault(role, member)

    def pref_rank(member: str, role: str) -> int:
        try:
            return prefs.get(member, []).index(role)
        except ValueError:
            return len(roles)

    helpers: list[dict[str, Any]] = []
    seen: set[str] = set()
    heavy_roles = [
        role for role in roles
        if difficulties.get(role, 5) >= 8 or max(1, int((slots or {}).get(role, 1))) > 1
    ]
    for role in sorted(heavy_roles, key=lambda r: -difficulties.get(r, 5)):
        if role in seen:
            continue
        seen.add(role)
        owner = owner_by_role.get(role)
        if not owner:
            continue
        candidates = [member for member in members if member != owner]
        if not candidates:
            continue
        helper = min(
            candidates,
            key=lambda member: (
                role in avoids.get(member, set()),
                loads.get(member, 0) + helper_loads.get(member, 0),
                pref_rank(member, role),
                len(assigned.get(member, [])),
            ),
        )
        helper_weight = max(1, round(difficulties.get(role, 5) * 0.4))
        helper_loads[helper] += helper_weight
        reason = "난이도 높은 책임이라 함께 진행을 권장합니다."
        if max(1, int((slots or {}).get(role, 1))) > 1:
            reason = "공동 진행이 필요한 책임으로 표시되어 helper를 붙였습니다."
        helpers.append({
            "card": role,
            "owner": owner,
            "helper": helper,
            "difficulty": difficulties.get(role, 5),
            "helper_weight": helper_weight,
            "reason": reason,
        })
    return helpers, helper_loads


def register(mcp: FastMCP) -> None:
    """역할 분배 도구를 등록한다."""

    @mcp.tool(
        name="assign_roles",
        annotations={
            "title": "역할분배 시작(순위폼 생성)",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def assign_roles(
        roles: list[Role] | None = None,
        room_id: int | None = None,
        close_minutes: int | None = 1440,
    ) -> dict[str, Any]:
        """Starts role assignment by creating a responsibility-card preference form for the team.

        역할 분배 **시작**. **너(AI)가 PM처럼 로드맵을 책임 카드+난이도로 직접 분해**해서
        넘겨라 (사용자에게 책임 카드·팀원 이름 묻지 마 — 팀원은 room_info로 확인).

        ⚠️ **고정 역할명 사전을 쓰지 말 것.** 개발 과제라고 항상 같은 기술 역할을 쓰거나,
        발표 과제라고 항상 같은 발표 역할을 쓰면 안 된다. 역할명은 로드맵의 실제 산출물,
        반복 작업, 의존관계에서 매번 새로 만든다.

        역할 생성 = **책임 카드 설계 7단계**:
        ① 최종 산출물 파악 — 이 팀이 마지막에 무엇을 제출/시연/완료해야 하는지 한 문장으로 정의
        ② 책임 분해 — 각 마일스톤에서 빠지면 안 되는 책임 단위를 추출
        ③ 개수 조절 — 책임 카드는 팀원 수의 1~2배, 되도록 1.5배 근처로 만들기
        ④ MECE 점검 — 책임끼리 겹치지 않고 전체 로드맵이 빠지지 않게 하기
        ⑤ 카드명 작성 — 프로젝트 어휘로 짧게 만들고 로드맵 단계명을 그대로 쓰지 않기
        ⑥ slots — 기본 1. 큰 책임은 slots를 늘리기보다 카드 자체를 나누기
        ⑦ 난이도(difficulty) — 작업량, 불확실성, 의존도, 마감 리스크, 커뮤니케이션 부담을 합쳐 1~10

        형식: roles=[{"name":"<프로젝트에서 도출한 책임 카드명>","difficulty":<1~10 정수>,"slots":1}, ...]

        난이도(difficulty)는 **멤버에겐 안 보이고**, 일을 공평하게 나누는 균형 배분에만 쓰인다.
        책임 카드 수는 팀원 수와 달라도 됨 — finalize_roles가 **모든 책임 카드를 멤버에 골고루 채운다**
        (멤버가 적으면 한 명이 여러 책임). close_minutes 기본 1일, 전원 응답 시 자동 마감.

        생성 후 흐름: **(1) 책임 카드 목록을 팀장에게 보여주고 '이대로?' 확인받기** →
        send_form(form_id) → 멤버 선호/회피 → finalize_roles 매칭 → **(2) 결과 팀장 확인** →
        set_roles. ※ (1)(2) 확인 없이 send_form/set_roles 하지 말 것.

        Args:
            roles: **AI가 생성한** 책임 카드+난이도 목록. 생략하면 폼을 만들지 않고 설계 브리프를 반환한다.
            room_id: 대상 방 (생략 시 현재 작업 방)
            close_minutes: 마감까지 분 (기본 1440=1일; 전원 응답 시엔 더 일찍 자동 마감)
        """
        caller, room, error = await require_room(room_id)
        if error:
            return error
        room_id = room["id"]
        roadmap = storage.get_roadmap(room_id)
        members = storage.list_members(room_id)
        generated_from_roadmap = False
        if not roles:
            return {
                "ok": True,
                "created": False,
                "needs_role_design": True,
                "role_design_brief": _role_design_brief(roadmap, len(members)),
                "required_next_tool": "role_manage",
                "required_next_action": "start",
                "required_next_arguments": {
                    "room_id": room_id,
                    "roles": "<generate from role_design_brief>",
                    "close_minutes": close_minutes,
                },
                "chat_response_hint": (
                    "사용자에게 역할명을 다시 묻지 마세요. role_design_brief를 기준으로 이 프로젝트에 맞는 "
                    "역할명, difficulty, slots를 직접 만든 뒤 즉시 role_manage(action='start')를 다시 호출하세요. "
                    "고정 예시 역할명은 쓰지 말고 로드맵의 실제 산출물 언어를 사용하세요."
                ),
            }
        if len(roles) < 2:
            return {
                "ok": False,
                "error": "책임 카드를 2개 이상 구성할 수 없습니다. 먼저 로드맵을 만들거나 프로젝트 주제를 더 구체화하세요.",
                "roadmap_task_titles": [t.get("title") for t in roadmap.get("tasks", [])],
            }

        names = [r.name for r in roles]
        difficulties = {r.name: r.difficulty for r in roles}
        slots = {r.name: r.slots for r in roles}
        invalid = _validate_role_names(names, roadmap, len(members))
        if invalid is not None:
            return invalid
        card_bounds = _responsibility_card_bounds(len(members))
        if len(names) < card_bounds["min"] or len(names) > card_bounds["max"]:
            return {
                "ok": False,
                "error": (
                    f"책임 카드 수가 팀원 수 기준 범위를 벗어났습니다. 현재 팀원 {len(members)}명 기준 "
                    f"{card_bounds['min']}~{card_bounds['max']}개가 적절하고, 추천은 {card_bounds['preferred']}개입니다."
                ),
                "responsibility_card_count": card_bounds,
                "received_count": len(names),
                "received_cards": names,
                "role_design_brief": _role_design_brief(roadmap, len(members)),
                "required_next_tool": "role_manage",
                "required_next_action": "start",
                "chat_response_hint": (
                    "사용자에게 카드 수 오류를 길게 설명하지 말고, 로드맵을 기준으로 책임 카드를 "
                    f"{card_bounds['preferred']}개 안팎으로 다시 묶어 role_manage(action='start')를 재호출하세요."
                ),
            }
        limits = _preference_limits(len(names))

        closes_at = None
        if close_minutes:
            from datetime import datetime, timedelta, timezone

            closes_at = datetime.now(timezone.utc) + timedelta(minutes=int(close_minutes))

        schema = {
            "title": "역할 선호도 조사",
            "description": (
                f"로드맵을 기준으로 나눈 책임 카드입니다. 맡고 싶은 카드는 최대 {limits['want_max']}개, "
                f"피하고 싶은 카드는 최대 {limits['avoid_max']}개만 골라주세요."
            ),
            "completeText": "제출",
            "showQuestionNumbers": "off",
            "elements": [
                {
                    "type": "checkbox",
                    "name": "role_wants",
                    "title": f"맡고 싶은 책임 카드를 골라주세요 (최대 {limits['want_max']}개)",
                    "choices": names,
                    "maxSelectedChoices": limits["want_max"],
                    "isRequired": True,
                },
            ],
            "_role_difficulty": difficulties,  # 멤버 폼엔 안 보임(SurveyJS 무시), finalize가 읽음
            "_role_slots": slots,
            "_role_cards": names,
            "_role_card_count": len(names),
            "_role_preference_limits": limits,
            "_role_assignment_mode": "responsibility_cards",
            "_workflow_kind": "role_assignment",
            "_workflow_stage": "role_preference_collection",
        }
        if limits["avoid_max"] > 0:
            schema["elements"].append(
                {
                    "type": "checkbox",
                    "name": "role_avoids",
                    "title": f"되도록 피하고 싶은 책임 카드가 있으면 골라주세요 (최대 {limits['avoid_max']}개)",
                    "description": "위에서 고른 카드와 겹치지 않게 골라주세요.",
                    "choices": names,
                    "maxSelectedChoices": limits["avoid_max"],
                    "isRequired": False,
                }
            )
        schema["elements"].append(
            {
                "type": "comment",
                "name": "notes",
                "title": "혹시 꼭 전하고 싶은 말이 있으면 적어주세요 (선택)",
                "isRequired": False,
            }
        )
        form = storage.create_form(
            room_id=room_id,
            title="역할 선호도 조사",
            schema_json=schema,
            anonymous=False,
            creator_user_id=caller["id"],
            closes_at=closes_at,
            close_on_all=True,
        )
        fid = form["id"]
        storage.create_invites(fid, [m["id"] for m in members])
        return {
            "ok": True,
            "form_id": fid,
            "roles": names,  # 공개 호환 필드: 실제 의미는 책임 카드
            "responsibility_cards": names,
            "role_slots": slots,
            "total_role_slots": sum(slots.values()),
            "responsibility_card_count": {
                **card_bounds,
                "actual": len(names),
            },
            "preference_limits": limits,
            "generated_from_roadmap": generated_from_roadmap,
            "roadmap_task_titles": [t.get("title") for t in roadmap.get("tasks", [])],
            "members": [m["nickname"] for m in members],
            "closes_in_minutes": close_minutes,
            "sent": False,
            "required_next_tool": "send_form",
            "send_form_arguments": {"form_id": fid},
            "do_not_claim_sent_before_send_form": True,
            "action_required": (
                "⚠️ 아직 보내지 마세요. 위 책임 카드 **이름**을 사용자(팀장)에게 보여주고 "
                "'이대로 선호도 조사를 보낼까요? 바꿀 책임 카드가 있나요?'라고 물어 **명시적 확인**을 받으세요. "
                "(난이도 점수는 보여주지 마세요 — 내부 균형용입니다.) 동의를 받은 뒤에만 역할 선호 폼을 발송하세요."
            ),
            "user_prompt_examples": [
                "이 역할 목록으로 팀원들에게 선호도 조사 보내줘",
                "응답이 모이면 역할 배정안 계산해줘",
                "이 배정안으로 역할 확정하고 공지해줘",
            ],
            "chat_response_hint": (
                "내부 도구명은 말하지 말고, 현재 로드맵을 참고해 만든 책임 카드 목록을 "
                f"팀장에게 보여준 뒤 '팀원은 맡고 싶은 것 최대 {limits['want_max']}개, "
                f"피하고 싶은 것 최대 {limits['avoid_max']}개만 고르면 됩니다. 이대로 보낼까요?'처럼 확인을 받으세요. "
                "로드맵 단계명을 그대로 쓰지 않고 책임 단위로 나눴다는 점을 짧게 설명하세요."
            ),
        }

    @mcp.tool(
        name="finalize_roles",
        annotations={
            "title": "역할 매칭(전체 배분·난이도 균형)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def finalize_roles(form_id: int) -> dict[str, Any]:
        """Computes a balanced, full-coverage role assignment from a teamplay-talk(팀플톡) preference form.

        역할 선호 폼의 응답을 읽어 **모든 책임 카드를 멤버에 배분**(전체집합 커버)하되 **난이도
        합을 균형**있게, **선호/회피를 반영**해 계산한다(아직 기록·발송 X). 멤버가 카드보다 적으면
        한 명이 여러 책임을 받는다. 결과를 팀장에게 보여주고 set_roles로 확정한다.

        Args:
            form_id: 역할 선호 폼의 ID (assign_roles가 만든 것)
        """
        _caller, form, error = await require_form(form_id)
        if error:
            return error
        schema = form.get("schema_json") or {}
        elements = schema.get("elements", [])
        rank_el = next(
            (e for e in schema.get("elements", []) if e.get("type") == "ranking"), None
        )
        want_el = next((e for e in elements if e.get("name") == "role_wants"), None)
        avoid_el = next((e for e in elements if e.get("name") == "role_avoids"), None)
        if rank_el is None and want_el is None:
            return {"ok": False, "error": "역할 선호 질문이 있는 폼이 아닙니다."}
        roles = list(
            schema.get("_role_cards")
            or (rank_el or want_el or {}).get("choices", [])
        )
        difficulties = {str(k): int(v) for k, v in (schema.get("_role_difficulty") or {}).items()}
        slots = {
            str(k): max(1, int(v))
            for k, v in (schema.get("_role_slots") or {}).items()
        }
        qname = rank_el.get("name") if rank_el else None

        results = storage.get_results(form_id)
        responses = (results or {}).get("responses", [])
        prefs: dict[str, list[str]] = {}
        avoids: dict[str, set[str]] = {}
        notes: dict[str, str] = {}
        preference_summary: dict[str, dict[str, Any]] = {}
        for r in responses:
            ans = r.get("answers") or {}
            key = r.get("nickname") or f"user{r.get('member_id')}"
            wants = ans.get("role_wants")
            avoided = ans.get("role_avoids")
            ranking = ans.get(qname) if qname else None
            if isinstance(ranking, list) and ranking:
                prefs[key] = [str(x) for x in ranking]
                avoids[key] = set()
            elif isinstance(wants, list) and wants:
                want_list = [str(x) for x in wants]
                avoid_set = {str(x) for x in avoided} if isinstance(avoided, list) else set()
                avoid_set.difference_update(want_list)
                prefs[key] = want_list
                avoids[key] = avoid_set
            if ans.get("notes"):
                notes[key] = str(ans["notes"]).strip()
            if key in prefs:
                preference_summary[key] = {
                    "wants": prefs.get(key, []),
                    "avoids": sorted(avoids.get(key, set())),
                    "note": notes.get(key, ""),
                }
        if not prefs:
            return {
                "ok": False,
                "error": "응답이 없습니다. (anonymous=False로 만들고 멤버가 선호 카드를 제출해야 매칭 가능)",
            }

        assignment_mode = schema.get("_role_assignment_mode") or ("ranking" if rank_el else "responsibility_cards")
        owner_slots = {role: 1 for role in roles} if assignment_mode == "responsibility_cards" else slots
        assigned, loads = _balanced_assign(roles, difficulties, prefs, avoids, owner_slots)
        helper_assignments, helper_loads = _helper_candidates(
            roles,
            difficulties,
            prefs,
            avoids,
            assigned,
            loads,
            slots,
        )
        helper_cards_by_member: dict[str, list[dict[str, Any]]] = {}
        for helper in helper_assignments:
            helper_cards_by_member.setdefault(str(helper["helper"]), []).append(helper)
        assignments = [
            {
                "nickname": m,
                "roles": _compact_roles(assigned[m]),
                "responsibility_cards": _compact_roles(assigned[m]),
                "raw_roles": assigned[m],
                "role": ", ".join(_compact_roles(assigned[m])),
                "workload": loads[m],
                "helper_workload": helper_loads.get(m, 0),
                "total_workload": loads[m] + helper_loads.get(m, 0),
                "helper_cards": helper_cards_by_member.get(m, []),
                "note": notes.get(m, ""),  # 멤버 자유기입(제약/사정) — 리더가 확정 전에 볼 것
                "wanted": prefs.get(m, []),
                "avoided": sorted(avoids.get(m, set())),
            }
            for m in prefs
        ]
        covered_counts = {
            role: sum(rs.count(role) for rs in assigned.values())
            for role in roles
        }
        required_slots = {role: max(1, owner_slots.get(role, 1)) for role in roles}
        return {
            "ok": True,
            "assignments": assignments,
            "helper_assignments": helper_assignments,
            "assignment_mode": assignment_mode,
            "preference_summary": preference_summary,
            "role_slots": required_slots,
            "covered_role_slots": covered_counts,
            "all_roles_covered": all(covered_counts.get(role, 0) >= required_slots[role] for role in roles),
            "uncovered_roles": [
                role for role in roles
                if covered_counts.get(role, 0) < required_slots[role]
            ],
            "member_notes": {m: notes[m] for m in notes},
            "persisted": False,
            "not_persisted": True,
            "required_next_tool": "set_roles",
            "set_roles_arguments": {
                "assignments": [
                    {"nickname": a["nickname"], "role": a["role"]} for a in assignments
                ],
                "helpers": [
                    {
                        "card": h["card"],
                        "owner": h["owner"],
                        "helper": h["helper"],
                        "reason": h.get("reason"),
                    }
                    for h in helper_assignments
                ],
            },
            "note": (
                "모든 책임 카드는 owner 1명에게 배정하고, 난이도 높은 카드는 helper를 별도로 제안합니다. "
                "workload는 owner 난이도 합, helper_workload는 함께 진행 부담입니다. "
                "⚠️ 각 멤버의 note가 있으면 팀장에게 보여주고, 필요하면 조정한 뒤 역할을 확정. "
                "AI 단독 확정 X — 팀장이 메모 보고 최종 판단."
            ),
            "next": "배정안은 아직 저장되지 않았습니다. 팀장에게 멤버 메모와 배정안을 보여주고, 확인되면 역할을 확정하세요.",
            "suggested_next_actions": [
                "팀장에게 배정안과 멤버 메모 확인받기",
                "helper가 붙은 무거운 책임 카드가 적절한지 확인하기",
                "조정이 필요하면 배정안 수정하기",
                "확정되면 역할 저장 및 공지하기",
                "저장 후 팀원별 할일 확인하거나 역할별 실행 todo로 연결하기",
            ],
            "chat_response_hint": "역할이 확정됐다고 말하지 마세요. 아직 '배정안'이며 확정·저장 전에는 반영되지 않았다고 분명히 말하세요.",
            "user_prompt_examples": [
                "이 배정안으로 확정해줘",
                "박세원 역할만 바꿔서 다시 보여줘",
                "확정 후 팀원들에게 공지해줘",
            ],
        }

    @mcp.tool(
        name="set_roles",
        annotations={
            "title": "역할 확정·공지",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,  # 외부(카카오) 공지
        },
    )
    async def set_roles(
        assignments: list[RoleAssignment],
        helpers: list[RoleHelperAssignment] | None = None,
        room_id: int | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        """Records role assignments and announces them to the teamplay-talk(팀플톡) team.

        역할 배정을 멤버에 **기록**하고 팀 전원에게 카카오로 **공지**한다. finalize_roles
        결과를 팀장이 확인·조정한 뒤 이걸로 확정한다. (확인 없이 호출하지 말 것)

        Args:
            assignments: [{"nickname": 멤버, "role": "역할(여러개면 ', '로 연결)"}]
            helpers: [{"card": 책임 카드, "owner": 메인 담당, "helper": 함께 진행 멤버}]
            room_id: 대상 방 (생략 시 현재 작업 방)
            message: 공지 문구 (생략 시 기본 형식)
        """
        _caller, room, error = await require_room(room_id)
        if error:
            return error
        room_id = room["id"]

        written = []
        for a in assignments:
            if storage.set_member_role(room_id, a.nickname, a.role):
                written.append({"nickname": a.nickname, "role": a.role})
        if not written:
            return {
                "ok": False,
                "assigned": [],
                "notified": [],
                "count": 0,
                "error": "저장된 역할이 없습니다. 닉네임이 방 멤버와 일치하는지 확인하세요.",
            }

        lines = "\n".join(f"· {a['nickname']}: {a['role']}" for a in written)
        helper_payload = [
            {
                "card": h.card,
                "owner": h.owner,
                "helper": h.helper,
                "reason": h.reason or "",
            }
            for h in (helpers or [])
        ]
        helper_lines = "\n".join(
            f"· {h['helper']}: {h['card']} 함께 진행 (메인 {h['owner']})"
            for h in helper_payload
        )
        msg = message or (
            f"[팀플톡] 역할 분배 결과\n{lines}"
            + (f"\n\n함께 진행\n{helper_lines}" if helper_lines else "")
        )
        sent = []
        from ..config import settings
        from ..dashboard_web import create_dashboard_token

        items = [(a["nickname"], a["role"]) for a in written[:5]]
        for m in kakao_store.list_members_with_tokens(room_id):
            token = create_dashboard_token(room_id, m["id"])
            link = f"{settings.public_base_url}/dashboard/rooms/{room_id}?token={token}"
            status = await kakao_store.send_feed_with_refresh(
                m,
                title="역할 분배가 확정됐습니다",
                description="팀원별 역할을 저장했습니다. 다음은 로드맵을 실행 todo로 쪼갤 차례입니다.",
                link_url=link,
                button_title="역할 보기",
                items=items,
                fallback_text=f"{msg}\n{link}",
            )
            if status == 200:
                sent.append(m["nickname"])
        if written:
            synced = storage.sync_task_assignees_by_roles(room_id)
            storage.record_room_decision(
                room_id,
                kind="roles",
                title="역할 분배 확정",
                summary="; ".join(f"{a['nickname']}: {a['role']}" for a in written),
                payload={"assignments": written, "helpers": helper_payload, "notified": sent},
                source="set_roles",
            )
        else:
            synced = {"mapped_count": 0, "unmatched_count": 0, "mapped": [], "unmatched": []}

        return {
            "ok": True,
            "assigned": written,
            "helpers": helper_payload,
            "notified": sent,
            "count": len(written),
            "synced_todos": synced,
            "next": (
                "역할이 확정됐습니다. 기존 역할명 todo가 있으면 실제 멤버에게 연결했습니다. "
                "다음은 로드맵 마일스톤을 실행 todo로 쪼개고, 팀원별 할 일을 확인하는 단계입니다."
            ),
            "suggested_next_actions": [
                "로드맵 기준 실행 todo 자동 생성하기",
                "생성된 todo를 팀원별로 확인하기",
                "todo 날짜를 배치하고 캘린더 등록하기",
                "개인별 오늘 할 일 공지하기",
            ],
            "chat_response_hint": (
                "역할 확정만으로 개인 할 일이 생긴 것은 아니라고 설명하세요. "
                "다음 단계는 로드맵 마일스톤 아래 실행 todo를 만들고 팀원별 목록을 확인하는 흐름으로 안내하세요."
            ),
        }
