"""의견 수렴 도메인 도구 (네이티브 폼/투표 — SurveyJS 엔진).

``create_poll`` 로 폼을 만들면 응답 링크가 나오고, 팀원은 그 링크를 카톡으로 받아
브라우저에서 응답한다(AI·앱·로그인 불필요). 응답은 ``get_poll_results`` 로 집계한다.

AI는 우리 타입드 스키마(질문 타입)만 쓰고, 서버가 SurveyJS JSON으로 변환한다.
"""

from __future__ import annotations

from typing import Any, Literal

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import kakao_store, storage, task_sync
from ..config import settings
from .guards import require_form, require_room


class PollQuestion(BaseModel):
    """폼 질문 1개."""

    title: str = Field(description="질문 내용")
    type: Literal["single", "multi", "rank", "rating", "text"] = Field(
        default="single",
        description=(
            "single=객관식 단일선택, multi=복수선택, "
            "rank=선호 순위(드래그 정렬), rating=점수(1~N), text=주관식"
        ),
    )
    choices: list[str] = Field(
        default_factory=list, description="선택지 (single/multi/rank용; text/rating은 비움)"
    )
    rate_max: int = Field(default=5, description="rating 최대 점수 (rating 타입에서만)")


_SJS_TYPE = {
    "single": "radiogroup",
    "multi": "checkbox",
    "rank": "ranking",
    "rating": "rating",
    "text": "comment",
}


def _location_form_title(title: str | None) -> str:
    value = (title or "").strip()
    if not value or "출발" in value or "출발지" in value:
        return "약속 장소 후보를 적어주세요"
    return value


def _to_surveyjs(title: str, description: str | None, questions: list[PollQuestion]) -> dict[str, Any]:
    """우리 타입드 질문 → SurveyJS 폼 JSON."""
    elements = []
    for i, q in enumerate(questions):
        el: dict[str, Any] = {
            "type": _SJS_TYPE.get(q.type, "radiogroup"),
            "name": f"q{i + 1}",
            "title": q.title,
            "isRequired": True,
        }
        if q.type in ("single", "multi", "rank"):
            el["choices"] = q.choices
        elif q.type == "rating":
            el["rateMax"] = q.rate_max
        elements.append(el)
    schema: dict[str, Any] = {
        "title": title,
        "showQuestionNumbers": "off",
        "completeText": "제출",
        "elements": elements,
    }
    if description:
        schema["description"] = description
    return schema


def _send_form_followup(form: dict[str, Any]) -> dict[str, Any]:
    schema = form.get("schema_json") or {}
    workflow = schema.get("_workflow_kind")
    if any(e.get("type") == "ranking" and e.get("name") == "roles" for e in schema.get("elements", [])):
        workflow = "role_assignment"
    if any(e.get("type") == "matrixdropdown" and e.get("name") == "availability" for e in schema.get("elements", [])):
        workflow = "meeting_time"
    if workflow == "location":
        return {
            "next": "응답이 모이면 위치 후보를 읽고 정규화하세요. 카카오맵 MCP가 있으면 장소명·주소 확인에 보조적으로 쓰고, 없으면 제출된 후보만 본투표로 넘기세요.",
            "suggested_next_actions": [
                "응답이 모이면 결과 확인하기",
                "제출된 장소 후보를 같은 역·상권·동네 기준으로 정규화하기",
                "카카오맵 MCP가 있으면 장소명·주소 확인과 중복 정리에 보조적으로 사용하기",
                "카카오맵 MCP가 없으면 있으면 장소 확인이 더 정확해진다고 안내하기",
                "정리된 후보로 복수선택 본투표 만들기",
            ],
        }
    if workflow == "roadmap_decision":
        return {
            "next": "응답이 모이면 결과를 확인하고, 실행 항목 반영이나 우선순위 투표로 이어가세요.",
            "suggested_next_actions": [
                "응답이 모이면 결과 확인하기",
                "답변을 태스크·담당·마감·리스크 후보로 정규화하기",
                "여러 실행 항목은 로드맵에 반영하기",
                "의견이 갈리는 항목은 우선순위 투표로 정하기",
            ],
        }
    if workflow == "daily_checkin":
        return {
            "next": "응답이 모이면 완료 반영안을 확인하고, 팀 리포트를 만드세요.",
            "suggested_next_actions": [
                "응답이 모이면 완료 반영안(미리보기) 확인하기",
                "확정되면 todo 상태에 실제 반영하기",
                "팀 전체 상태·남은 밀린 일·메모 리포트 만들기",
                "필요하면 팀에 공지하거나 개인별 할일 공지하기",
            ],
        }
    if workflow == "role_assignment":
        return {
            "next": "역할 선호 응답이 모이면 결과를 확인하고 배정안을 계산하세요.",
            "suggested_next_actions": [
                "응답이 모이면 결과 확인하기",
                "난이도·필요 인원 기준으로 배정안 계산하기",
                "팀장 확인 후 역할 확정·저장하기",
            ],
        }
    if workflow == "meeting_time":
        return {
            "next": "응답이 모이면 가장 가능한 시간대를 보고 회의 시간을 확정하세요.",
            "suggested_next_actions": [
                "응답이 모이면 결과 확인하기",
                "가장 가능한 시간대 중에서 확정하기",
                "팀에 공지하기",
                "확정 시간을 전원 캘린더에 등록하기",
            ],
        }
    return {
        "next": "응답이 모이면 결과를 확인하고, 필요하면 공지하거나 후속 투표·로드맵 반영으로 이어가세요.",
        "suggested_next_actions": [
            "응답이 모이면 결과 확인하기",
            "결과 요약하기",
            "필요하면 팀에 공지하기",
            "의견이 갈리면 후속 투표 만들기",
        ],
    }


def _form_feed_copy(form: dict[str, Any]) -> tuple[str, str]:
    schema = form.get("schema_json") or {}
    workflow = schema.get("_workflow_kind")
    if any(e.get("type") == "ranking" and e.get("name") == "roles" for e in schema.get("elements", [])):
        workflow = "role_assignment"
    if any(e.get("type") == "matrixdropdown" and e.get("name") == "availability" for e in schema.get("elements", [])):
        workflow = "meeting_time"
    descriptions = {
        "role_assignment": "역할 선호도를 순서대로 골라주세요. 응답이 모이면 팀장이 확정합니다.",
        "meeting_time": "가능한 시간은 O, 절대 안 되는 시간은 X로 표시해주세요.",
        "location": "선호하는 약속 장소 후보만 한 칸에 하나씩 적어주세요.",
        "daily_checkin": "밀린 일과 오늘 끝낸 일을 체크하고, 필요한 메모만 남겨주세요.",
        "roadmap_decision": _compact_text(
            str(schema.get("_kakao_description") or schema.get("description") or "로드맵에 반영할 의견을 짧게 남겨주세요."),
            limit=220,
        ),
    }
    return str(form.get("title") or "팀플톡 폼"), descriptions.get(
        str(workflow), "팀 의사결정을 위해 짧게 응답해주세요."
    )


def _compact_text(value: str, *, limit: int = 160) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _format_date_range(task: dict[str, Any]) -> str:
    start = task.get("start_at")
    end = task.get("end_at")
    if not start and not end:
        return ""
    left = start.date().isoformat() if hasattr(start, "date") else str(start)[:10]
    right = end.date().isoformat() if hasattr(end, "date") else str(end)[:10]
    if left and right and left != right:
        return f" ({left}~{right})"
    return f" ({left or right})"


def _task_opinion_context(room_id: int, scope: str) -> tuple[str, str, list[str]]:
    roadmap = storage.get_roadmap(room_id)
    tasks = roadmap.get("tasks", [])
    milestones = [t for t in tasks if (t.get("task_type") or "milestone") == "milestone"]
    todos = [t for t in tasks if (t.get("task_type") or "milestone") == "todo"]
    milestone_lines = [
        f"{idx}. {str(t.get('title') or '').strip()}{_format_date_range(t)}"
        for idx, t in enumerate(milestones[:8], start=1)
        if str(t.get("title") or "").strip()
    ]
    if not milestone_lines:
        context = "아직 저장된 로드맵이 없습니다. 이번 프로젝트에 필요하다고 생각하는 큰 단계와 이유를 적어주세요."
        return context, "아직 저장된 로드맵이 없습니다. 필요한 큰 단계와 이유를 적어주세요.", []

    lead_by_scope = {
        "roadmap": "아래 현재 로드맵을 보고 추가/수정/삭제하면 좋을 단계를 적어주세요.",
        "todo": "아래 현재 로드맵을 보고 각 단계에서 실제로 해야 할 일을 적어주세요.",
        "blockers": "아래 현재 로드맵을 보고 막힌 점이나 도움이 필요한 부분을 적어주세요.",
        "scope": "아래 현재 로드맵을 보고 유지/줄임/추가할 범위를 적어주세요.",
    }
    lines = [lead_by_scope.get(scope, lead_by_scope["roadmap"]), "", "현재 로드맵:"]
    lines.extend(milestone_lines)
    if scope == "todo" and todos:
        lines.extend(["", "현재 실행 todo 일부:"])
        lines.extend(
            f"- {str(t.get('title') or '').strip()}{_format_date_range(t)}"
            for t in todos[:8]
            if str(t.get("title") or "").strip()
        )
    context = "\n".join(lines)
    kakao = "현재 로드맵: " + " · ".join(line.split(". ", 1)[-1] for line in milestone_lines[:5])
    return context, kakao, [line.split(". ", 1)[-1] for line in milestone_lines]


def _infer_task_opinion_scope(text: str | None) -> str | None:
    haystack = str(text or "").lower()
    if any(token in haystack for token in ("막힌", "병목", "리스크", "blocker")):
        return "blockers"
    if any(token in haystack for token in ("스코프", "범위", "줄이", "빼도", "추가할")):
        return "scope"
    if any(token in haystack for token in ("todo", "to-do", "할일", "할 일", "태스크", "작업")):
        return "todo"
    if any(token in haystack for token in ("로드맵", "마일스톤", "milestone")):
        return "roadmap"
    return None


def _attach_task_opinion_context(schema: dict[str, Any], room_id: int, scope: str) -> str:
    context, kakao, milestones = _task_opinion_context(room_id, scope)
    schema["description"] = context
    schema["_workflow_kind"] = "roadmap_decision"
    schema["_workflow_scope"] = scope
    schema["_context_milestones"] = milestones
    schema["_kakao_description"] = kakao
    schema["_message_context"] = context
    return context


def register(mcp: FastMCP) -> None:
    """의견 수렴 도메인 도구를 등록한다."""

    @mcp.tool(
        name="create_poll",
        annotations={
            "title": "폼/투표 생성",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def create_poll(
        title: str,
        questions: list[PollQuestion],
        room_id: int | None = None,
        description: str | None = None,
        anonymous: bool = True,
        close_minutes: int | None = None,
        close_on_all: bool = False,
    ) -> dict[str, Any]:
        """Creates a native poll/form in teamplay-talk(팀플톡) and returns a response link.

        팀플톡 자체 폼/투표를 만들고 응답 링크를 반환한다. 팀원은 이 링크를 카톡으로
        받아 브라우저에서 응답한다(AI·앱·로그인 불필요).

        질문 타입(type): single=단일선택, multi=복수선택, rank=선호 순위(드래그),
        rating=점수, text=주관식.

        **anonymous=True (기본)**: 공유 링크 1개·익명 → 의견수렴·여론조사 등 "전체 목소리
        모으기". (익명이라 **중복 제출은 막을 수 없음** — 한 사람이 여러 번 가능)
        **anonymous=False**: 응답을 *특정 멤버에 매칭* 하거나 **1인 1표(중복 방지)**가 필요할 때
        — 역할분배·진척체크·구속력 있는 투표. 멤버별 개인 링크, **재제출 시 교체(1인 1응답 보장)**.

        생성 후 배포는 **send_form(form_id)** 으로 한다(notify_room ❌). send_form이
        익명이면 한 메시지 브로드캐스트, 식별이면 각자에게 개인 링크를 보낸다.

        Args:
            title: 폼 제목 (예: "회식 날짜 투표")
            questions: 질문 목록
            room_id: 폼이 속한 방 ID (생략 시 **현재 작업 방**). ID 추측 금지 —
                     보통 생략하면 됨.
            description: 폼 설명 (선택)
            anonymous: 공유링크(True·기본) vs 멤버별 식별 링크(False·매칭 필요시만)
            close_minutes: N분 뒤 자동 마감 (선택)
            close_on_all: 전원 응답 시 자동 마감 (선택)
        """
        caller, room, error = await require_room(room_id)
        if error:
            return error
        room_id = room["id"]
        title = _location_form_title(title)
        creator_id = caller["id"]

        closes_at = None
        if close_minutes:
            from datetime import datetime, timedelta, timezone

            closes_at = datetime.now(timezone.utc) + timedelta(minutes=int(close_minutes))

        inferred_scope = _infer_task_opinion_scope(
            " ".join([title, description or "", *[q.title for q in questions]])
        )
        schema = _to_surveyjs(title, description, questions)
        context_description = description
        if inferred_scope:
            context_description = _attach_task_opinion_context(schema, room_id, inferred_scope)

        form = storage.create_form(
            room_id=room_id,
            title=title,
            schema_json=schema,
            description=context_description,
            anonymous=anonymous,
            creator_user_id=creator_id,
            closes_at=closes_at,
            close_on_all=close_on_all,
        )
        fid = form["id"]
        base = f"{settings.public_base_url}{storage.form_public_path(fid)}"
        out: dict[str, Any] = {
            "ok": True,
            "form_id": fid,
            "title": title,
            "anonymous": anonymous,
            "question_count": len(questions),
            "context_attached": bool(inferred_scope),
            "workflow_scope": inferred_scope,
            "sent": False,
            "required_next_tool": "send_form",
            "send_form_arguments": {"form_id": fid},
            "do_not_claim_sent_before_send_form": True,
            "next": "이 폼을 팀에 발송할 차례입니다. (공지용 알림이 아니라 폼 발송으로 보내세요.)",
            "user_prompt_examples": [
                "이 폼 팀원들에게 보내줘",
                "응답이 모이면 결과 정리해줘",
                "마감되면 팀에 결과 공지해줘",
            ],
            "chat_response_hint": (
                "폼은 아직 발송되지 않았습니다. 내부 도구명은 말하지 말고, "
                "로드맵/todo 관련 폼이면 현재 로드맵 요약을 포함했다고 말하세요. "
                "'이 폼을 팀원들에게 보내드릴까요?'처럼 자연어로 다음 행동을 물어보세요."
            ),
        }
        if anonymous:
            out["share_url"] = base
        else:
            members = storage.list_members(room_id)
            storage.create_invites(fid, [m["id"] for m in members])
            out["mode"] = "식별 폼 — 팀원별 개인 링크로 발송됩니다."
        return out

    @mcp.tool(
        name="gather_opinions",
        annotations={
            "title": "의견수렴 시작(자유의견)",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def gather_opinions(
        question: str,
        room_id: int | None = None,
        anonymous: bool = True,
        close_minutes: int | None = 1440,
    ) -> dict[str, Any]:
        """Starts opinion gathering (stage 1 of 의견수렴형) — a free-text poll to the team.

        팀의 의사결정(**주제·아이디어 등 '뭘로 할까'**)을 시작한다.
        약속 장소 후보 수집은 긴 자유서술 대신 gather_locations를 우선 사용한다.
        **사용자에게 후보를 묻지 마라** — 이 도구로 팀원에게 자유의견을 모으는 게 시작이다.

        기본 2단계 흐름:
        (1) gather_opinions(question) → 팀원이 자유롭게 글로 의견 → send_form → [완료 nudge]
        (2) get_poll_results로 의견 읽고 **AI가 항목화** → create_poll(**복수선택** 본투표, 그
            항목들) → send_form → 결과 공지.

        약속 장소 정하기는 gather_locations → send_form → get_poll_results →
        정규화/카카오맵 MCP 장소명 확인 보조 → create_poll 본투표 흐름을 사용한다.

        예: "회의 일정 잡자" → gather_opinions("회의 가능한 날짜·시간을 자유롭게 적어주세요").

        Args:
            question: 팀원에게 물을 질문 (네가 맥락 보고 직접 작성)
            room_id: 대상 방 (생략 시 현재 작업 방)
            anonymous: 익명 여부 (기본 True)
            close_minutes: 마감까지 분 (기본 1일; 전원 응답 시 자동 마감)
        """
        caller, room, error = await require_room(room_id)
        if error:
            return error
        room_id = room["id"]

        closes_at = None
        if close_minutes:
            from datetime import datetime, timedelta, timezone

            closes_at = datetime.now(timezone.utc) + timedelta(minutes=int(close_minutes))

        schema = {
            "title": question,
            "completeText": "제출",
            "showQuestionNumbers": "off",
            "elements": [
                {"type": "comment", "name": "opinion", "title": question, "isRequired": True}
            ],
        }
        inferred_scope = _infer_task_opinion_scope(question)
        context_description = None
        if inferred_scope:
            context_description = _attach_task_opinion_context(schema, room_id, inferred_scope)
        form = storage.create_form(
            room_id=room_id,
            title=question,
            schema_json=schema,
            description=context_description,
            anonymous=anonymous,
            creator_user_id=caller["id"],
            closes_at=closes_at,
            close_on_all=True,
        )
        fid = form["id"]
        if not anonymous:
            storage.create_invites(fid, [m["id"] for m in storage.list_members(room_id)])
        return {
            "ok": True,
            "form_id": fid,
            "stage": "1/2 (의견수렴)",
            "context_attached": bool(inferred_scope),
            "workflow_scope": inferred_scope,
            "sent": False,
            "required_next_tool": "send_form",
            "send_form_arguments": {"form_id": fid},
            "do_not_claim_sent_before_send_form": True,
            "next": (
                "이 의견 폼을 팀원에게 보낼 차례입니다. 응답이 모이면(또는 마감 무렵) 의견을 읽어 "
                "항목으로 정리한 뒤, 복수선택 본투표로 2단계 투표를 만드세요. "
                "약속 장소는 장소 정하기 전용 흐름을 쓰세요."
            ),
            "user_prompt_examples": [
                "이 의견 폼 팀원들에게 보내줘",
                "응답이 모이면 후보로 정리해줘",
                "정리된 후보로 본투표 만들어줘",
            ],
            "chat_response_hint": (
                "내부 도구명은 말하지 말고, "
                "로드맵/todo 관련 의견 폼이면 현재 로드맵 요약이 포함되어 있다고 말하세요. "
                "'의견 폼을 만들었고 아직 발송 전입니다. 팀원들에게 보내드릴까요?'처럼 자연어로 안내하세요."
            ),
        }

    @mcp.tool(
        name="gather_locations",
        annotations={
            "title": "약속 장소 후보 수집",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def gather_locations(
        title: str = "약속 장소 후보를 적어주세요",
        room_id: int | None = None,
        anonymous: bool = False,
        close_minutes: int | None = 1440,
    ) -> dict[str, Any]:
        """Starts structured location gathering for meeting-place decisions.

        약속 장소를 정하기 위한 전용 수집 폼을 만든다. 긴 자유서술 1칸 대신
        짧은 위치 입력칸 5개와 기타 의견을 분리해 받아서 AI가 정규화하기 쉽게 한다.

        기본 흐름:
        gather_locations → send_form → get_poll_results →
        AI가 위치 후보 정규화 →
        카카오맵 MCP가 있으면 장소명/역명/주소 확인 보조 →
        없으면 카카오맵 MCP 연결 시 장소 확인이 더 정확해진다고 안내하고 제출 후보만 사용 →
        create_poll(복수선택 본투표) → send_form → get_poll_results → notify_room.

        Args:
            title: 폼 제목
            room_id: 대상 방 (생략 시 현재 작업 방)
            anonymous: 익명 여부. 기본 false(누가 어떤 후보를 냈는지 확인하기 쉬움)
            close_minutes: 마감까지 분 (기본 1일; 전원 응답 시 자동 마감)
        """
        caller, room, error = await require_room(room_id)
        if error:
            return error
        room_id = room["id"]

        closes_at = None
        if close_minutes:
            from datetime import datetime, timedelta, timezone

            closes_at = datetime.now(timezone.utc) + timedelta(minutes=int(close_minutes))

        elements: list[dict[str, Any]] = [
            {
                "type": "text",
                "name": "location_1",
                "title": "장소 후보 1",
                "description": "추천하고 싶은 약속 장소를 역/동네/상호명처럼 짧게 적어주세요.",
                "placeholder": "예: 강남역, 홍대입구역, 서초동, 카카오 판교아지트",
                "isRequired": True,
            }
        ]
        for i in range(2, 6):
            elements.append({
                "type": "text",
                "name": f"location_{i}",
                "title": f"장소 후보 {i}",
                "description": "추가 후보가 있으면 하나만 적어주세요.",
                "placeholder": "예: 신논현역",
                "isRequired": False,
            })
        elements.append({
            "type": "comment",
            "name": "location_note",
            "title": "기타 의견",
            "description": "이동수단, 피하고 싶은 지역, 시간 제약, 선호 분위기 등을 적어주세요.",
            "isRequired": False,
        })
        schema = {
            "title": title,
            "description": "선호하는 약속 장소 후보를 한 칸에 하나씩 짧게 적어주세요.",
            "completeText": "제출",
            "showQuestionNumbers": "off",
            "elements": elements,
            "_workflow_kind": "location",
            "_workflow_stage": "location_collection",
            "_workflow_scope": "meeting_place",
        }
        form = storage.create_form(
            room_id=room_id,
            title=title,
            description=schema["description"],
            schema_json=schema,
            anonymous=anonymous,
            creator_user_id=caller["id"],
            closes_at=closes_at,
            close_on_all=True,
        )
        fid = form["id"]
        if not anonymous:
            storage.create_invites(fid, [m["id"] for m in storage.list_members(room_id)])
        return {
            "ok": True,
            "form_id": fid,
            "anonymous": anonymous,
            "sent": False,
            "required_next_tool": "send_form",
            "send_form_arguments": {"form_id": fid},
            "do_not_claim_sent_before_send_form": True,
            "next": (
                "이 장소 후보 폼을 팀원에게 보낼 차례입니다. 응답이 모이면 위치 칸별 원문을 읽어 "
                "같은 역·상권·동네를 정규화하고, 카카오맵 MCP가 있으면 장소명·주소 확인에 "
                "보조적으로 쓰세요. 지도 도구가 없으면 제출된 후보만 복수선택 본투표로 진행하세요."
            ),
            "suggested_next_actions": [
                "팀원에게 위치 입력 폼 발송하기",
                "응답이 모이면 위치 칸별 원문 확인하기",
                "같은 장소 표현은 정규화하고 모호한 값은 원문 보존하기",
                "카카오맵 MCP가 있으면 장소명·주소 확인과 중복 정리에 보조적으로 사용하기",
                "카카오맵 MCP가 없으면 있으면 장소 확인이 더 정확하다고 안내한 뒤 제출 후보만 본투표하기",
                "정규화한 후보로 복수선택 본투표 만들기",
            ],
            "chat_response_hint": (
                "내부 도구명은 말하지 마세요. "
                "사용자에게는 '장소 후보 폼을 만들었고 아직 발송 전입니다. 팀원들에게 보내드릴까요?'처럼 말하세요. "
                "발송 성공 전에는 팀원에게 물어봤다고 말하지 마세요. "
                "응답이 모인 뒤에는 카카오맵 MCP가 보이면 장소명·주소 확인과 중복 정리에 보조적으로 쓸 수 있고, "
                "없으면 제출된 텍스트 기준으로 후보를 정리한다고 짧게 안내하세요."
            ),
            "user_prompt_examples": [
                "이 장소 후보 폼 팀원들에게 보내줘",
                "응답이 모이면 장소 후보 정리해줘",
                "정리된 장소로 본투표 만들어줘",
            ],
            "optional_integration": {
                "name": "카카오맵 MCP",
                "when_available": "장소명·역명·주소 확인, 중복 후보 정규화 보조",
                "fallback": "미설치/미사용이면 팀원이 제출한 후보만 정규화해서 본투표",
            },
        }

    @mcp.tool(
        name="gather_task_opinions",
        annotations={
            "title": "로드맵/할일 의견수렴",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def gather_task_opinions(
        scope: Literal["roadmap", "todo", "blockers", "scope"] = "roadmap",
        prompt: str | None = None,
        room_id: int | None = None,
        anonymous: bool = False,
        close_minutes: int | None = 1440,
    ) -> dict[str, Any]:
        """Starts a structured roadmap/todo opinion loop in teamplay-talk(팀플톡).

        로드맵 단계, 개인별 to-do, 병목/리스크, 스코프 조정을 정하기 전에 팀원 의견을
        구조적으로 모은다. 결과 조회 뒤 AI가 답변을 정규화해 add_task/update_task 또는
        create_poll 우선순위 투표로 이어가야 한다.

        기본 흐름:
        gather_task_opinions → send_form → get_poll_results →
        AI가 태스크 후보/수정사항/리스크로 정규화 →
        decompose_roadmap/add_task/update_task/create_poll → member_tasks/daily_task_digest.

        Args:
            scope: roadmap=로드맵 단계, todo=구체 할일, blockers=막힌 점, scope=범위 조정
            prompt: 팀원에게 보여줄 질문 제목. 생략하면 scope별 기본 질문.
            room_id: 대상 방 (생략 시 현재 작업 방)
            anonymous: 익명 여부. 기본 false(누가 어떤 할일/제약을 말했는지 반영하기 좋음)
            close_minutes: 마감까지 분 (기본 1일; 전원 응답 시 자동 마감)
        """
        caller, room, error = await require_room(room_id)
        if error:
            return error
        room_id = room["id"]

        closes_at = None
        if close_minutes:
            from datetime import datetime, timedelta, timezone

            closes_at = datetime.now(timezone.utc) + timedelta(minutes=int(close_minutes))

        titles = {
            "roadmap": "로드맵에서 빠진 단계나 수정할 단계가 있나요?",
            "todo": "이번 구간에 해야 할 구체적인 할일과 맡을 수 있는 일을 적어주세요.",
            "blockers": "지금 막힌 점과 도움이 필요한 부분을 적어주세요.",
            "scope": "이번 프로젝트 범위에서 유지/줄임/추가할 것을 적어주세요.",
        }
        title = prompt or titles[scope]
        context_text, kakao_description, context_milestones = _task_opinion_context(room_id, scope)
        elements_by_scope: dict[str, list[dict[str, Any]]] = {
            "roadmap": [
                {
                    "type": "comment",
                    "name": "roadmap_changes",
                    "title": "추가/수정/삭제하면 좋을 로드맵 단계",
                    "isRequired": True,
                },
                {
                    "type": "comment",
                    "name": "reason",
                    "title": "그렇게 생각한 이유나 기대 효과",
                    "isRequired": False,
                },
                {
                    "type": "comment",
                    "name": "risk",
                    "title": "걱정되는 리스크나 놓친 조건",
                    "isRequired": False,
                },
            ],
            "todo": [
                {
                    "type": "comment",
                    "name": "todo_suggestions",
                    "title": "이번 주/다음 회의 전까지 필요한 구체 할일",
                    "isRequired": True,
                },
                {
                    "type": "comment",
                    "name": "owner_hint",
                    "title": "본인이 맡을 수 있거나 도와줄 수 있는 일",
                    "isRequired": False,
                },
                {
                    "type": "comment",
                    "name": "due_hint",
                    "title": "가능한 마감일, 어려운 일정, 필요한 선행조건",
                    "isRequired": False,
                },
            ],
            "blockers": [
                {
                    "type": "comment",
                    "name": "blocker",
                    "title": "현재 막힌 점",
                    "isRequired": True,
                },
                {
                    "type": "comment",
                    "name": "help_needed",
                    "title": "누구의 어떤 도움이 필요한지",
                    "isRequired": False,
                },
            ],
            "scope": [
                {
                    "type": "comment",
                    "name": "keep",
                    "title": "유지해야 할 것",
                    "isRequired": False,
                },
                {
                    "type": "comment",
                    "name": "cut",
                    "title": "줄이거나 빼도 되는 것",
                    "isRequired": False,
                },
                {
                    "type": "comment",
                    "name": "add",
                    "title": "추가하면 좋은 것",
                    "isRequired": False,
                },
            ],
        }
        schema = {
            "title": title,
            "description": context_text,
            "completeText": "제출",
            "showQuestionNumbers": "off",
            "elements": elements_by_scope[scope],
            "_workflow_kind": "roadmap_decision",
            "_workflow_scope": scope,
            "_context_milestones": context_milestones,
            "_kakao_description": kakao_description,
            "_message_context": context_text,
        }
        form = storage.create_form(
            room_id=room_id,
            title=title,
            schema_json=schema,
            description=context_text,
            anonymous=anonymous,
            creator_user_id=caller["id"],
            closes_at=closes_at,
            close_on_all=True,
        )
        fid = form["id"]
        if not anonymous:
            storage.create_invites(fid, [m["id"] for m in storage.list_members(room_id)])
        return {
            "ok": True,
            "form_id": fid,
            "scope": scope,
            "context": context_text,
            "context_milestones": context_milestones,
            "anonymous": anonymous,
            "sent": False,
            "required_next_tool": "send_form",
            "send_form_arguments": {"form_id": fid},
            "do_not_claim_sent_before_send_form": True,
            "next": (
                "이 폼을 팀에 발송하세요. 응답이 모이면 원문 의견을 읽어 태스크 후보·수정사항·리스크로 "
                "정규화한 뒤 로드맵·할일에 반영하고, 의견이 갈리면 우선순위 투표로 정한 다음 "
                "개인별 할일을 확인하세요."
            ),
            "suggested_next_actions": [
                "팀원에게 폼 발송하기",
                "응답이 모이면 원문 의견 조회하기",
                "중복 표현을 합쳐 태스크·담당·마감·리스크 후보로 정리하기",
                "여러 실행 항목은 로드맵에 반영하고 단건 수정은 해당 할일에 반영하기",
                "의견이 갈리는 항목은 채택·우선순위 투표로 정하기",
            ],
            "user_prompt_examples": [
                "이 의견 폼 팀원들에게 보내줘",
                "응답이 모이면 할일 후보로 정리해줘",
                "정리한 항목을 로드맵에 반영해줘",
            ],
            "chat_response_hint": (
                "내부 도구명은 말하지 말고, 이 의견 폼에는 현재 로드맵 요약이 포함되어 있다고 짧게 말하세요. "
                "'로드맵을 같이 볼 수 있게 넣어둔 의견 폼을 팀원들에게 보내드릴까요?'처럼 자연어로 다음 행동을 물어보세요."
            ),
        }

    @mcp.tool(
        name="get_poll_results",
        annotations={
            "title": "폼/투표 결과 조회",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def get_poll_results(form_id: int) -> dict[str, Any]:
        """Reads aggregated responses of a teamplay-talk(팀플톡) poll/form.

        폼 응답을 질문별로 집계해 반환한다. 객관식=선택지별 카운트와 승자/동점,
        rank=순위점수와 상위 후보, rating=평균, 주관식=답변 목록. 식별 폼이면
        멤버별 raw 응답도 포함한다.

        결과에는 workflow_kind와 suggested_next_actions가 포함된다. 역할분배는 일반
        create_poll이 아니라 assign_roles가 만든 ranking 폼이며, 결과 조회 후
        finalize_roles → set_roles로 이어진다.

        Args:
            form_id: 결과를 조회할 폼 ID
        """
        _caller, _form, error = await require_form(form_id)
        if error:
            return error
        results = storage.get_results(form_id)
        if results is None:
            return {"ok": False, "error": "존재하지 않는 폼입니다."}
        return {"ok": True, **results}

    @mcp.tool(
        name="close_poll",
        annotations={
            "title": "폼/투표 마감",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def close_poll(form_id: int) -> dict[str, Any]:
        """Closes a teamplay-talk(팀플톡) poll and returns final results.

        폼을 마감(추가 응답 차단)하고 최종 결과를 반환한다.

        Args:
            form_id: 마감할 폼 ID
        """
        _caller, _form, error = await require_form(form_id)
        if error:
            return error
        results = storage.get_results(form_id)
        if results is None:
            return {"ok": False, "error": "존재하지 않는 폼입니다."}
        storage.close_form(form_id)
        return {"ok": True, "closed": True, **results}

    @mcp.tool(
        name="send_form",
        annotations={
            "title": "폼 링크 팀에 발송",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,  # 외부(카카오) 발송
        },
    )
    async def send_form(form_id: int, message: str | None = None) -> dict[str, Any]:
        """Sends a teamplay-talk(팀플톡) form link to the team via KakaoTalk.

        폼을 팀에 발송한다. **익명 폼이면 공유 링크 1개를 전원에게**, **식별 폼이면
        각 멤버에게 자기 개인 링크를** 보낸다. create_poll 뒤 배포는 이걸로 한다.
        (notify_room으로 폼 링크를 보내지 말 것 — 개인 링크가 섞인다.)

        Args:
            form_id: 발송할 폼 ID
            message: 안내 문구 (생략 시 기본). 링크는 자동으로 뒤에 붙는다.
        """
        _caller, form, error = await require_form(form_id)
        if error:
            return error
        base = f"{settings.public_base_url}{storage.form_public_path(form_id)}"
        title, description = _form_feed_copy(form)
        schema = form.get("schema_json") or {}
        fallback_description = str(schema.get("_message_context") or description)
        prefix = (message or f"[팀플톡] '{form['title']}' 응답 요청").rstrip()
        room = storage.get_room(form["room_id"])
        items = [
            ("방", room["name"] if room else str(form["room_id"])),
            ("상태", "진행중" if not form.get("closed") else "마감"),
        ]

        sent: list[str] = []
        failed: list[str] = []
        if form["anonymous"]:
            for m in kakao_store.list_members_with_tokens(form["room_id"]):
                status = await kakao_store.send_feed_with_refresh(
                    m,
                    title=title,
                    description=description,
                    link_url=base,
                    button_title="폼 열기",
                    items=items,
                    fallback_text=f"{prefix}\n{fallback_description}\n{base}",
                )
                (sent if status == 200 else failed).append(m["nickname"])
        else:
            for r in storage.list_form_recipients(form_id):
                url = f"{settings.public_base_url}{storage.form_public_path(form_id, r['invite_token'])}"
                status = await kakao_store.send_feed_with_refresh(
                    r,
                    title=title,
                    description=description,
                    link_url=url,
                    button_title="내 링크 열기",
                    items=items,
                    fallback_text=f"{prefix}\n{fallback_description}\n{url}",
                )
                (sent if status == 200 else failed).append(r["nickname"])

        if not sent and not failed:
            return {"ok": False, "error": "발송 대상이 없습니다(멤버가 카카오 로그인을 마쳐야 함)."}
        if not sent:
            return {
                "ok": False,
                "form_id": form_id,
                "sent_to": sent,
                "failed": failed,
                "count": 0,
                "error": "모든 발송이 실패했습니다. 카카오 인증/토큰 상태를 확인해야 합니다.",
            }
        try:  # 카카오 할 일(리마인더) — 발송 시 생성. 실패해도 기존 흐름 유지
            if schema.get("_workflow_kind") == "daily_checkin":
                await task_sync.sync_checkin(form["room_id"], schema.get("_checkin_date"))
            else:
                await task_sync.sync_form(form["room_id"], form_id, form["title"])
        except Exception:
            pass
        followup = _send_form_followup(form)
        return {
            "ok": True,
            "form_id": form_id,
            "sent_to": sent,
            "failed": failed,
            "count": len(sent),
            "status": "partial" if failed else "sent",
            **followup,
            "chat_response_hint": (
                "사용자에게 발송 성공 대상과 다음 행동을 함께 말하세요. 내부 도구명은 말하지 마세요. "
                "예: '박세원님에게 보냈고, 응답이 오면 결과를 확인한 뒤 본투표를 만들 수 있어요.'"
            ),
            "user_prompt_examples": [
                "응답 결과 정리해줘",
                "결과를 팀에 공지해줘",
                "필요하면 다음 투표까지 만들어줘",
            ],
        }
