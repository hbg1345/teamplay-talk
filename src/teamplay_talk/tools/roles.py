"""역할 분배 도구 (③ AI 결정형).

흐름: assign_roles(AI가 만든 책임 카드) → 선호/회피 폼 → send_form 개인별 →
멤버 선호 → finalize_roles(전체 책임 카드를 균형 배분) → 팀장 확인 → set_roles.

핵심:
- **전체집합 커버**: 모든 책임 카드가 누군가에게 배정된다(멤버<카드면 한 명이 여러 책임).
- **공동 owner**: 멤버가 카드보다 많거나 책임이 큰 경우 한 책임 카드에 여러 멤버가 배정될 수 있다.
- **부담 균형**: 각 멤버에게 비슷한 부담이 가도록 배정한다.
- **선호/회피 반영**: 동률일 때 그 책임을 선호한 멤버에게, 회피한 멤버는 뒤로.
- 난이도 점수는 **멤버 폼엔 안 보이고**(균형 배분용), 매칭은 서버에서 결정적으로.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import kakao_store, storage
from .guards import require_form, require_room


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
    return {
        "principle": (
            "로드맵과 프로젝트 맥락을 읽고, 팀원이 선호도를 고를 수 있는 역할/책임 카드를 자유롭게 만든다. "
            "카드명은 프로젝트에 맞게 자연스럽게 정하고, 서버는 이름을 강하게 검열하지 않는다. "
            "이 단계에서는 사용자에게 초안을 설명하지 말고, 바로 role_manage(action='start')를 다시 호출한다."
        ),
        "roadmap_milestones": task_lines,
        "team_size": member_count,
        "responsibility_card_count": {
            "basis": "ai_discretion",
            "hard_limit": False,
        },
        "role_design_steps": [
            "1. 로드맵과 최종 산출물을 보고 팀원이 고를 역할/책임 카드를 만든다.",
            "2. 카드 개수와 이름은 프로젝트 성격에 맞게 자유롭게 정한다.",
            "3. 만든 카드 목록을 role_manage(action='start')에 roles로 다시 넣는다.",
            "4. 사용자가 보기 전까지 카드 초안을 채팅으로 설명하지 않는다.",
        ],
        "hard_rules": [
            "사용자에게 말할 때 difficulty, slots, 난이도, 필요 인원, 인원 수를 노출하지 않는다.",
            "책임 카드 목록을 만들면 곧바로 role_manage(action='start')에 roles로 다시 넣는다.",
        ],
        "output_schema": [
            {"name": "프로젝트 어휘로 만든 책임 카드명"}
        ],
    }


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
    """역할명은 AI 자율에 맡긴다. 난이도/slots 범위는 Pydantic이 검증한다."""
    return None


class Role(BaseModel):
    """책임 카드 1개 (이름 + 난이도)."""

    name: str = Field(description="팀원이 선호도를 고를 역할/책임 카드 이름")
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
            "공동 owner 자리 수. 기본 1. 같은 책임을 반드시 여러 명이 함께 맡아야 하면 2 이상으로 둔다. "
            "쪼갤 수 있는 큰 일은 slots를 늘리기보다 더 작은 책임 카드로 나누는 편이 좋다."
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


def _owner_slot_counts(
    roles: list[str],
    difficulties: dict[str, int],
    requested_slots: dict[str, int] | None,
    member_count: int,
) -> dict[str, int]:
    """카드별 owner 자리 수를 정한다.

    기본은 AI가 넣은 slots를 존중한다. 팀원이 카드보다 많으면 남는 멤버가 놀지 않도록
    난이도 높은 카드부터 공동 owner 자리를 늘린다.
    """
    counts = {
        role: max(1, int((requested_slots or {}).get(role, 1)))
        for role in roles
    }
    if not roles:
        return counts
    extra = max(0, int(member_count or 0) - sum(counts.values()))
    ordered = sorted(roles, key=lambda role: (-difficulties.get(role, 5), role))
    index = 0
    while extra > 0:
        role = ordered[index % len(ordered)]
        counts[role] += 1
        extra -= 1
        index += 1
    return counts


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
    owner_count_by_role: dict[str, int] = {}
    for member, member_roles in assigned.items():
        for role in member_roles:
            owner_by_role.setdefault(role, member)
            owner_count_by_role[role] = owner_count_by_role.get(role, 0) + 1

    def pref_rank(member: str, role: str) -> int:
        try:
            return prefs.get(member, []).index(role)
        except ValueError:
            return len(roles)

    helpers: list[dict[str, Any]] = []
    seen: set[str] = set()
    heavy_roles = [
        role for role in roles
        if difficulties.get(role, 5) >= 8 and owner_count_by_role.get(role, 0) < 2
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
        reason = "작업량이 큰 책임이라 함께 진행을 권장합니다."
        helpers.append({
            "card": role,
            "owner": owner,
            "helper": helper,
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

        역할 분배 **시작**. 너(AI)가 로드맵과 프로젝트 맥락을 보고 팀원이 선호도를 고를
        역할/책임 카드를 직접 만들어 넘겨라. 사용자에게 역할 목록 작성을 떠넘기지 마라.

        역할 생성:
        ① 로드맵과 최종 산출물을 확인
        ② 팀원이 고를 역할/책임 카드 생성
        ③ 각 카드에는 내부 균형값을 넣되, 사용자에게 숫자로 설명하지 않는다.
        ④ role_manage(action='start')에 roles로 다시 호출

        형식: roles=[{"name":"<프로젝트에서 도출한 책임 카드명>","difficulty":<내부값>,"slots":<내부값>}, ...]

        difficulty/slots는 **멤버에겐 안 보이고**, 일을 공평하게 나누는 균형 배분에만 쓰인다.
        역할/책임 카드 수는 팀원 수와 달라도 됨 — finalize_roles가 **모든 owner 자리를 멤버에 골고루 채운다**.
        멤버가 적으면 한 명이 여러 책임을 맡고, 멤버가 카드보다 많으면 난이도 높은 책임에 공동 owner가 붙을 수 있다.
        close_minutes 기본 1일, 전원 응답 시 자동 마감.

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
                "must_call_tool_now": True,
                "do_not_answer_user_yet": True,
                "chat_response_hint": (
                    "이 응답을 사용자에게 설명하지 마세요. role_design_brief를 기준으로 이 프로젝트에 맞는 "
                    "책임 카드 이름을 직접 만든 뒤 즉시 role_manage(action='start')를 다시 호출하세요. "
                    "고정 예시 역할명은 쓰지 말고 로드맵의 실제 산출물 언어를 사용하세요. "
                    "difficulty, slots, 난이도, 필요 인원은 말하지 마세요."
                ),
            }
        names = [r.name for r in roles]
        difficulties = {r.name: r.difficulty for r in roles}
        slots = {r.name: r.slots for r in roles}
        invalid = _validate_role_names(names, roadmap, len(members))
        if invalid is not None:
            return invalid
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
            "responsibility_card_count": {
                "actual": len(names),
                "basis": "ai_discretion",
                "hard_limit": False,
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
                "difficulty/slots/난이도/필요 인원은 내부 균형용이므로 말하지 마세요. 동의를 받은 뒤에만 역할 선호 폼을 발송하세요."
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
                "로드맵을 책임 단위로 나눴다는 점을 짧게 설명하세요. difficulty, slots, 난이도, 필요 인원은 말하지 마세요."
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
        owner_slots = (
            _owner_slot_counts(roles, difficulties, slots, len(prefs))
            if assignment_mode == "responsibility_cards"
            else slots
        )
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
                "모든 책임 카드가 누군가에게 배정되도록 계산했습니다. "
                "작업량이 큰 단독 책임에는 함께 진행할 helper를 별도로 제안할 수 있습니다. "
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
