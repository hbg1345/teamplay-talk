"""역할 분배 도구 (③ AI 결정형).

AI가 난이도 균형 역할을 생성 → create_poll(rank, anonymous=False)로 선호 순위 폼 →
send_form으로 각자 배포 → 멤버가 순위 → ``finalize_roles`` 가 선호 최대화 매칭(결정적)
→ 팀장 확인 → ``set_roles`` 가 기록·공지.

매칭은 서버에서 결정적으로(매번 동일·정확), 역할 생성·난이도 판단은 AI(클라 LLM)가.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import kakao_store, storage
from ..identity import resolve_caller


class RoleAssignment(BaseModel):
    """역할 배정 1건."""

    nickname: str = Field(description="멤버 닉네임")
    role: str = Field(description="배정할 역할")


def _greedy_match(roles: list[str], prefs: dict[str, list[str]]) -> dict[str, str]:
    """선호 최대화 그리디 1:1 매칭. prefs: {멤버: [선호순 역할]}. return {멤버: 역할}.

    전역 최고 선호(1순위)부터 채우고, 남은 멤버↔남은 역할을 이어붙여 전원 배정.
    """
    candidates: list[tuple[int, str, str]] = []
    for member, ranking in prefs.items():
        for idx, role in enumerate(ranking):
            if role in roles:
                candidates.append((idx, member, role))
    candidates.sort(key=lambda x: x[0])  # 1순위(idx 작은) 먼저

    matched: dict[str, str] = {}
    used: set[str] = set()
    for _idx, member, role in candidates:
        if member in matched or role in used:
            continue
        matched[member] = role
        used.add(role)

    # 남은 멤버 ↔ 남은 역할 채우기 (선호 다 소진된 경우)
    rem_members = [m for m in prefs if m not in matched]
    rem_roles = [r for r in roles if r not in used]
    for member, role in zip(rem_members, rem_roles):
        matched[member] = role
    return matched


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
        roles: list[str],
        room_id: int | None = None,
        close_minutes: int | None = None,
    ) -> dict[str, Any]:
        """Starts role assignment by creating a ranked-preference poll for the team.

        역할 분배를 **시작**한다. **너(AI)가 프로젝트 성격을 보고 역할 목록을 직접 생성**해서
        넘겨라 — 사용자에게 역할이나 팀원 이름을 묻지 마라. 팀원은 이미 방에 있고
        (room_info로 확인 가능), 역할은 프로젝트로 추론한다.
        예: 로봇 캡스톤 → ["기구설계", "회로/전자", "제어/SW", "문서/발표"]. 역할 수는 보통 팀원 수에 맞춘다.

        생성 후 흐름: **(1) 역할 목록을 팀장에게 보여주고 '이대로?' 확인받기** →
        send_form(form_id) → 각 팀원 순위폼 → 멤버 순위 → finalize_roles 매칭 →
        **(2) 매칭 결과를 팀장에게 확인받기** → set_roles 확정·공지.
        ※ (1)(2) 확인 없이 send_form/set_roles 하지 말 것.

        Args:
            roles: **AI가 생성한** 역할 목록 (팀원 수에 맞춰)
            room_id: 대상 방 (생략 시 현재 작업 방)
            close_minutes: N분 뒤 자동 마감 (선택; 전원 응답 시엔 자동 마감)
        """
        if len(roles) < 2:
            return {"ok": False, "error": "역할을 2개 이상 직접 생성해서 넘겨주세요 (사용자에게 묻지 말 것)."}
        caller = await resolve_caller()
        if room_id is None:
            if caller is None:
                return {"ok": False, "error": "카카오 인증이 필요합니다."}
            active = storage.get_active_room(caller["id"])
            if active is None:
                return {"ok": False, "error": "현재 작업 방이 없습니다. create_room/switch_room 먼저."}
            room_id = active["id"]

        closes_at = None
        if close_minutes:
            from datetime import datetime, timedelta, timezone

            closes_at = datetime.now(timezone.utc) + timedelta(minutes=int(close_minutes))

        schema = {
            "title": "역할 선호도 조사",
            "description": "하고 싶은 역할을 위에서부터 끌어 정렬하세요 (위=1순위).",
            "completeText": "제출",
            "showQuestionNumbers": "off",
            "elements": [
                {
                    "type": "ranking",
                    "name": "roles",
                    "title": "역할을 선호 순서대로 정렬해주세요",
                    "choices": list(roles),
                    "isRequired": True,
                }
            ],
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
            "roles": list(roles),
            "members": [m["nickname"] for m in members],
            "action_required": (
                "⚠️ 아직 보내지 마세요. 위 역할 목록을 사용자(팀장)에게 보여주고 "
                "'이대로 팀원들에게 보낼까요? 바꿀 역할 있나요?'라고 물어 **명시적 확인**을 "
                "받으세요. 사용자가 동의한 뒤에만 send_form(form_id)을 호출하세요. "
                "확인 없이 send_form 하지 마세요."
            ),
        }

    @mcp.tool(
        name="finalize_roles",
        annotations={
            "title": "역할 매칭(선호 기반)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def finalize_roles(form_id: int) -> dict[str, Any]:
        """Computes a preference-maximizing role assignment from a teamplay-talk(팀플톡) ranking poll.

        역할 선호 순위 폼(create_poll에서 type=rank, anonymous=False로 만든 것)의 응답을
        읽어, 선호를 최대화하는 역할 배정을 **계산만** 한다(아직 기록·발송 X). 결과를
        팀장에게 보여주고, 확정은 set_roles로 한다.

        Args:
            form_id: 순위 선호 폼의 ID
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
        qname = rank_el.get("name")

        results = storage.get_results(form_id)
        responses = (results or {}).get("responses", [])
        if not responses:
            return {
                "ok": False,
                "error": "식별 폼 응답이 없습니다. (anonymous=False로 만들고 멤버가 응답해야 매칭 가능)",
            }

        prefs: dict[str, list[str]] = {}
        for r in responses:
            ranking = (r.get("answers") or {}).get(qname)
            key = r.get("nickname") or f"user{r.get('member_id')}"
            if isinstance(ranking, list) and ranking:
                prefs[key] = [str(x) for x in ranking]

        if not prefs:
            return {"ok": False, "error": "유효한 순위 응답이 없습니다."}

        matched = _greedy_match(roles, prefs)
        assignments = []
        for member, role in matched.items():
            ranked = prefs.get(member, [])
            rank_got = ranked.index(role) + 1 if role in ranked else None
            assignments.append(
                {"nickname": member, "role": role, "preference_rank": rank_got}
            )
        return {
            "ok": True,
            "assignments": assignments,
            "unresponded": [n for n in roles if n],  # 정보용: 역할 목록
            "note": (
                "선호 최대화 그리디 매칭. preference_rank=받은 역할이 본인 몇 순위(낮을수록 좋음, "
                "None=선호 외 채움). 확정·공지는 set_roles 로."
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
        결과를 팀장이 확인·조정한 뒤 이걸로 확정한다.

        Args:
            assignments: [{"nickname": 멤버, "role": 역할}] 목록
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
