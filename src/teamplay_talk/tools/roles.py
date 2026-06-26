"""역할 분배 도구 (③ AI 결정형).

흐름: assign_roles(AI가 만든 역할+난이도) → 순위폼 → send_form 개인별 →
멤버 순위 → finalize_roles(전체 역할을 난이도 균형으로 배분) → 팀장 확인 → set_roles.

핵심:
- **전체집합 커버**: 모든 역할이 누군가에게 배정된다(멤버<역할이면 한 명이 여러 역할).
- **난이도 균형**: 각 멤버의 난이도 합이 비슷하게 (LPT 그리디).
- **선호 반영**: 동률일 때 그 역할을 더 선호한 멤버에게.
- 난이도 점수는 **멤버 폼엔 안 보이고**(균형 배분용), 매칭은 서버에서 결정적으로.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import kakao_store, storage
from ..identity import resolve_caller


class Role(BaseModel):
    """역할 1개 (이름 + 난이도)."""

    name: str = Field(description="역할 이름 (예: 기구설계)")
    difficulty: int = Field(
        default=5,
        ge=1,
        le=10,
        description="난이도·업무량 1~10. **멤버에겐 안 보이고** 균형 배분에만 쓰인다. 무거운 역할일수록 크게(기구설계 8, 문서 3 등).",
    )


class RoleAssignment(BaseModel):
    """역할 배정 1건 (set_roles용)."""

    nickname: str = Field(description="멤버 닉네임")
    role: str = Field(description="배정할 역할(여러 개면 ', '로 연결)")


def _balanced_assign(
    roles: list[str], difficulties: dict[str, int], prefs: dict[str, list[str]]
) -> tuple[dict[str, list[str]], dict[str, int]]:
    """모든 역할을 멤버에 배분(전체집합 커버) + 난이도 합 균형 + 선호 반영.

    무거운 역할부터(LPT) 가장 덜 일한 멤버에게 — 동률이면 그 역할을 더 선호한 멤버에게.
    return: ({멤버: [역할들]}, {멤버: 난이도합}). 멤버<역할이면 한 명이 여러 역할.
    """
    members = list(prefs.keys())
    loads = {m: 0 for m in members}
    assigned: dict[str, list[str]] = {m: [] for m in members}

    def pref_rank(member: str, role: str) -> int:
        try:
            return prefs[member].index(role)
        except ValueError:
            return len(roles)  # 선호 안 한 역할은 최하 순위

    for role in sorted(roles, key=lambda r: -difficulties.get(r, 5)):
        d = difficulties.get(role, 5)
        best = min(members, key=lambda m: (loads[m] + d, pref_rank(m, role)))
        assigned[best].append(role)
        loads[best] += d
    return assigned, loads


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
        roles: list[Role],
        room_id: int | None = None,
        close_minutes: int | None = 1440,
    ) -> dict[str, Any]:
        """Starts role assignment by creating a ranked-preference poll for the team.

        역할 분배 **시작**. **너(AI)가 PM처럼 과제를 분해해 역할+난이도를 직접 생성**해서
        넘겨라 (사용자에게 역할·팀원 이름 묻지 마 — 팀원은 room_info로 확인).

        ⚠️ **반드시 사용자가 말한 그 과제에 맞는 역할을 새로 생성**하라. 아래 설명에 나오는
        단어를 역할로 복사하지 말 것 (예: '카카오 MCP 공모전'이면 MCP서버 설계·도구 구현·
        카카오 연동·프롬프트 설계·문서/발표 등 *그 과제* 역할을 만들어야 함).

        역할 생성 = **PM 분해 4단계**:
        ① 산출물 파악 — 그 과제가 최종적으로 내야 할 결과물이 무엇인지
        ② 작업 분해 — 그 산출물을 만드는 데 필요한 작업을 **최대한 잘게** 나열
        ③ 역할화 — **비슷한 작업끼리 묶어** 응집성 있는 역할로. **역할 수 > 팀원 수 OK**
           (난이도 균형으로 한 명이 여러 역할). 순위 매기기 좋게 보통 팀원수~2배.
        ④ 난이도 — 역할별 업무량 1~10 (넓고 어려울수록 높게). **난이도는 균형 배분용 내부값 —
           사용자에게 점수를 보여주지 말고 역할 *이름*만 확인받을 것.**
        형식: roles=[{"name":"<과제에 맞는 역할명>","difficulty":<1~10 정수>}, ...]

        난이도(difficulty)는 **멤버에겐 안 보이고**, 일을 공평하게 나누는 균형 배분에만 쓰인다.
        역할 수는 팀원 수와 달라도 됨 — finalize_roles가 **모든 역할을 멤버에 골고루 채운다**
        (멤버가 적으면 한 명이 여러 역할). close_minutes 기본 1일, 전원 응답 시 자동 마감.

        생성 후 흐름: **(1) 역할 목록을 팀장에게 보여주고 '이대로?' 확인받기** →
        send_form(form_id) → 멤버 순위 → finalize_roles 매칭 → **(2) 결과 팀장 확인** →
        set_roles. ※ (1)(2) 확인 없이 send_form/set_roles 하지 말 것.

        Args:
            roles: **AI가 생성한** 역할+난이도 목록
            room_id: 대상 방 (생략 시 현재 작업 방)
            close_minutes: 마감까지 분 (기본 1440=1일; 전원 응답 시엔 더 일찍 자동 마감)
        """
        if len(roles) < 2:
            return {"ok": False, "error": "역할을 2개 이상 직접 생성해서 넘겨주세요(사용자에게 묻지 말 것)."}
        caller = await resolve_caller()
        if room_id is None:
            if caller is None:
                return {"ok": False, "error": "카카오 인증이 필요합니다."}
            active = storage.get_active_room(caller["id"])
            if active is None:
                return {"ok": False, "error": "현재 작업 방이 없습니다. create_room/switch_room 먼저."}
            room_id = active["id"]

        names = [r.name for r in roles]
        difficulties = {r.name: r.difficulty for r in roles}

        closes_at = None
        if close_minutes:
            from datetime import datetime, timedelta, timezone

            closes_at = datetime.now(timezone.utc) + timedelta(minutes=int(close_minutes))

        schema = {
            "title": "역할 선호도 조사",
            "description": "하고 싶은 역할을 위에서부터 끌어 **전부 정렬**해주세요 (위=1순위).",
            "completeText": "제출",
            "showQuestionNumbers": "off",
            "elements": [
                {
                    "type": "ranking",
                    "name": "roles",
                    "title": "역할을 선호 순서대로 정렬해주세요",
                    "choices": names,
                    "isRequired": True,
                },
                {
                    "type": "comment",
                    "name": "notes",
                    "title": "꼭 하고 싶은 / 절대 못 하는 역할, 참고사항이 있으면 적어주세요 (선택)",
                    "isRequired": False,
                },
            ],
            "_role_difficulty": difficulties,  # 멤버 폼엔 안 보임(SurveyJS 무시), finalize가 읽음
        }
        form = storage.create_form(
            room_id=room_id,
            title="역할 선호도 조사",
            schema_json=schema,
            anonymous=False,
            creator_user_id=caller["id"] if caller else None,
            closes_at=closes_at,
            close_on_all=True,
        )
        fid = form["id"]
        members = storage.list_members(room_id)
        storage.create_invites(fid, [m["id"] for m in members])
        return {
            "ok": True,
            "form_id": fid,
            "roles": names,  # 역할 이름만 — 난이도는 내부 균형값이라 노출 X
            "members": [m["nickname"] for m in members],
            "closes_in_minutes": close_minutes,
            "action_required": (
                "⚠️ 아직 보내지 마세요. 위 역할 **이름**을 사용자(팀장)에게 보여주고 "
                "'이대로 보낼까요? 바꿀 역할 있나요?'라고 물어 **명시적 확인**을 받으세요. "
                "(난이도 점수는 보여주지 마세요 — 내부 균형용입니다.) 동의한 뒤에만 "
                "send_form(form_id)을 호출하세요."
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
    def finalize_roles(form_id: int) -> dict[str, Any]:
        """Computes a balanced, full-coverage role assignment from a teamplay-talk(팀플톡) ranking poll.

        역할 순위 폼의 응답을 읽어 **모든 역할을 멤버에 배분**(전체집합 커버)하되 **난이도
        합을 균형**있게, **선호를 반영**해 계산한다(아직 기록·발송 X). 멤버가 역할보다 적으면
        한 명이 여러 역할을 받는다. 결과를 팀장에게 보여주고 set_roles로 확정한다.

        Args:
            form_id: 순위 선호 폼의 ID (assign_roles가 만든 것)
        """
        form = storage.get_form(form_id)
        if form is None:
            return {"ok": False, "error": "존재하지 않는 폼입니다."}
        schema = form.get("schema_json") or {}
        rank_el = next(
            (e for e in schema.get("elements", []) if e.get("type") == "ranking"), None
        )
        if rank_el is None:
            return {"ok": False, "error": "순위(rank) 질문이 있는 폼이 아닙니다."}
        roles = list(rank_el.get("choices", []))
        difficulties = {str(k): int(v) for k, v in (schema.get("_role_difficulty") or {}).items()}
        qname = rank_el.get("name")

        results = storage.get_results(form_id)
        responses = (results or {}).get("responses", [])
        prefs: dict[str, list[str]] = {}
        notes: dict[str, str] = {}
        for r in responses:
            ans = r.get("answers") or {}
            key = r.get("nickname") or f"user{r.get('member_id')}"
            ranking = ans.get(qname)
            if isinstance(ranking, list) and ranking:
                prefs[key] = [str(x) for x in ranking]
            if ans.get("notes"):
                notes[key] = str(ans["notes"]).strip()
        if not prefs:
            return {
                "ok": False,
                "error": "응답이 없습니다. (anonymous=False로 만들고 멤버가 순위를 제출해야 매칭 가능)",
            }

        assigned, loads = _balanced_assign(roles, difficulties, prefs)
        assignments = [
            {
                "nickname": m,
                "roles": assigned[m],
                "role": ", ".join(assigned[m]),
                "workload": loads[m],
                "note": notes.get(m, ""),  # 멤버 자유기입(제약/사정) — 리더가 확정 전에 볼 것
            }
            for m in prefs
        ]
        covered = {r for rs in assigned.values() for r in rs}
        return {
            "ok": True,
            "assignments": assignments,
            "all_roles_covered": set(roles) <= covered,
            "uncovered_roles": [r for r in roles if r not in covered],
            "member_notes": {m: notes[m] for m in notes},
            "note": (
                "모든 역할을 난이도 균형 배분(workload=난이도 합, 비슷할수록 공평) + 선호 반영. "
                "⚠️ **각 멤버의 note(자유기입: 못 하는 역할·사정)를 반드시 팀장에게 보여주고**, "
                "필요하면 조정한 뒤 set_roles로 확정. AI 단독 확정 X — 팀장이 note 보고 최종 판단."
            ),
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
        room_id: int | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        """Records role assignments and announces them to the teamplay-talk(팀플톡) team.

        역할 배정을 멤버에 **기록**하고 팀 전원에게 카카오로 **공지**한다. finalize_roles
        결과를 팀장이 확인·조정한 뒤 이걸로 확정한다. (확인 없이 호출하지 말 것)

        Args:
            assignments: [{"nickname": 멤버, "role": "역할(여러개면 ', '로 연결)"}]
            room_id: 대상 방 (생략 시 현재 작업 방)
            message: 공지 문구 (생략 시 기본 형식)
        """
        if room_id is None:
            caller = await resolve_caller()
            if caller is None:
                return {"ok": False, "error": "방을 지정하거나 카카오 인증이 필요합니다."}
            active = storage.get_active_room(caller["id"])
            if active is None:
                return {"ok": False, "error": "현재 작업 방이 없습니다. room_id를 지정하세요."}
            room_id = active["id"]

        written = []
        for a in assignments:
            if storage.set_member_role(room_id, a.nickname, a.role):
                written.append({"nickname": a.nickname, "role": a.role})

        lines = "\n".join(f"· {a['nickname']}: {a['role']}" for a in written)
        msg = message or f"🎭 역할 분배 결과\n{lines}"
        sent = []
        for m in kakao_store.list_members_with_tokens(room_id):
            if await kakao_store.send_with_refresh(m, msg) == 200:
                sent.append(m["nickname"])

        return {"ok": True, "assigned": written, "notified": sent, "count": len(written)}
