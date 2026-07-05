"""Consolidated public MCP tools.

This module keeps the existing domain implementations intact, then exposes a
smaller, review-friendly surface by wrapping legacy tools behind domain hubs.
The wrapped tools are removed from the public MCP list but their registered
FunctionTool objects are reused internally.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from fastmcp import FastMCP

from .. import storage
from ..identity import resolve_caller
from .guards import require_room


LegacyTools = dict[str, Any]


NEXT_TOOL_MAP: dict[str, tuple[str, str]] = {
    "send_form": ("form_manage", "send"),
    "get_poll_results": ("form_manage", "results"),
    "close_poll": ("form_manage", "close"),
    "assign_roles": ("role_manage", "start"),
    "finalize_roles": ("role_manage", "finalize"),
    "set_roles": ("role_manage", "set"),
    "build_roadmap": ("roadmap_manage", "build"),
    "view_roadmap": ("roadmap_manage", "view"),
    "schedule_roadmap": ("roadmap_manage", "schedule"),
    "decompose_roadmap": ("roadmap_manage", "decompose"),
    "member_tasks": ("roadmap_manage", "member_tasks"),
    "daily_task_digest": ("roadmap_manage", "digest"),
    "add_task": ("task_manage", "add"),
    "update_task": ("task_manage", "update"),
    "delete_task": ("task_manage", "delete"),
    "create_daily_checkin": ("daily_manage", "create_checkin"),
    "apply_daily_checkin": ("daily_manage", "apply_checkin"),
    "daily_report": ("daily_manage", "report"),
    "calendar_create_room_event": ("calendar_team", "room_event"),
    "calendar_create_task_events": ("calendar_team", "task_events"),
    "calendar_create_event": ("calendar_personal", "create"),
    "calendar_list_events": ("calendar_personal", "list"),
    "calendar_get_event": ("calendar_personal", "get"),
    "calendar_update_event": ("calendar_personal", "update"),
    "calendar_delete_event": ("calendar_personal", "delete"),
}

NEXT_ARGUMENT_KEYS = (
    "send_form_arguments",
    "set_roles_arguments",
    "required_next_arguments",
)

CONSOLIDATED_GROUPS: dict[str, list[str]] = {
    "room_manage": [
        "create_room",
        "join_room",
        "switch_room",
        "rooms",
        "delete_room",
        "restore_room",
        "leave_room",
    ],
    "form_manage": ["send_form", "get_poll_results", "close_poll"],
    "role_manage": ["assign_roles", "finalize_roles", "set_roles"],
    "roadmap_manage": [
        "build_roadmap",
        "view_roadmap",
        "schedule_roadmap",
        "decompose_roadmap",
        "member_tasks",
        "daily_task_digest",
    ],
    "task_manage": ["add_task", "update_task", "delete_task"],
    "daily_manage": ["create_daily_checkin", "apply_daily_checkin", "daily_report"],
    "calendar_team": ["calendar_create_room_event", "calendar_create_task_events"],
    "calendar_personal": [
        "calendar_create_event",
        "calendar_list_events",
        "calendar_get_event",
        "calendar_update_event",
        "calendar_delete_event",
    ],
}


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else None)


def _clean_args(values: dict[str, Any]) -> dict[str, Any]:
    """Drop omitted optional arguments before invoking the wrapped tool."""
    return {key: value for key, value in values.items() if value is not None}


def _tool_arg_names(tool: Any) -> set[str]:
    parameters = getattr(tool, "parameters", None) or {}
    properties = parameters.get("properties") or {}
    return set(properties)


def _missing_required_args(tool: Any, args: dict[str, Any]) -> list[str]:
    parameters = getattr(tool, "parameters", None) or {}
    required = parameters.get("required") or []
    return [name for name in required if name not in args]


def _filter_args_for_tool(tool: Any, args: dict[str, Any]) -> dict[str, Any]:
    allowed = _tool_arg_names(tool)
    cleaned = _clean_args(args)
    parameters = getattr(tool, "parameters", None)
    if parameters is None:
        return cleaned
    return {key: value for key, value in cleaned.items() if key in allowed}


def _local_tools(mcp: FastMCP) -> LegacyTools:
    tools: LegacyTools = {}
    components = getattr(mcp, "_local_provider")._components
    for component in components.values():
        name = getattr(component, "name", None)
        if name:
            tools[name] = component
    return tools


def _remove_public_tools(mcp: FastMCP, names: list[str]) -> None:
    provider = getattr(mcp, "_local_provider")
    for name in names:
        try:
            provider.remove_tool(name)
        except KeyError:
            pass


def _publicize_next_tool(data: Any) -> Any:
    """Rewrite legacy next-tool hints to the consolidated public tools."""
    if not isinstance(data, dict):
        return data
    out = deepcopy(data)
    legacy_name = out.get("required_next_tool")
    if legacy_name not in NEXT_TOOL_MAP:
        return out

    public_tool, action = NEXT_TOOL_MAP[legacy_name]
    required_args: dict[str, Any] = {}
    for key in NEXT_ARGUMENT_KEYS:
        value = out.pop(key, None)
        if isinstance(value, dict):
            required_args.update(value)

    out["required_next_tool"] = public_tool
    out["required_next_action"] = action
    if required_args:
        out["required_next_arguments"] = required_args
    return out


def _workflow_label(schema: dict[str, Any]) -> str:
    workflow = str(schema.get("_workflow_kind") or "")
    scope = str(schema.get("_workflow_scope") or "")
    if workflow == "roadmap_decision":
        labels = {
            "roadmap": "로드맵 의견",
            "todo": "todo 의견",
            "blockers": "병목 의견",
            "scope": "스코프 의견",
        }
        return labels.get(scope, "로드맵/todo 의견")
    if workflow == "role_assignment":
        return "역할분배"
    if workflow == "meeting_time":
        return "회의 시간"
    if workflow == "location":
        return "약속 장소"
    if workflow == "daily_checkin":
        return "데일리 체크인"
    return "일반 폼/투표"


def _form_summary(form: dict[str, Any]) -> dict[str, Any]:
    schema = form.get("schema_json") or {}
    room_form_no = form.get("room_form_no") or form["id"]
    label = f"방내 #{room_form_no} · ID {form['id']} · {_workflow_label(schema)} · {form['title']} · {int(form.get('total_responses') or 0)}응답"
    return {
        "form_id": form["id"],
        "room_form_no": room_form_no,
        "label": label,
        "title": form["title"],
        "status": "closed" if form.get("closed") else "active",
        "kind": _workflow_label(schema),
        "workflow_kind": schema.get("_workflow_kind"),
        "workflow_scope": schema.get("_workflow_scope"),
        "responses": int(form.get("total_responses") or 0),
        "anonymous": bool(form.get("anonymous")),
        "created_at": _iso(form.get("created_at")),
        "closes_at": _iso(form.get("closes_at")),
    }


def _matches_form(form: dict[str, Any], query: str | None) -> bool:
    if not query:
        return True
    schema = form.get("schema_json") or {}
    haystack = " ".join(
        str(part or "")
        for part in [
            form.get("title"),
            form.get("description"),
            schema.get("title"),
            schema.get("description"),
            schema.get("_workflow_kind"),
            schema.get("_workflow_scope"),
            _workflow_label(schema),
        ]
    ).lower()
    return all(token in haystack for token in str(query).lower().split())


async def _list_forms(
    room_id: int | None,
    *,
    status: str = "active",
    query: str | None = None,
    limit: int = 12,
) -> dict[str, Any]:
    _caller, room, error = await require_room(room_id)
    if error:
        return error
    forms = [
        form for form in storage.list_room_forms(room["id"])
        if (status == "all" or (status == "closed") == bool(form.get("closed")))
        and _matches_form(form, query)
    ]
    summaries = [_form_summary(form) for form in forms[:limit]]
    active_count = sum(1 for form in storage.list_room_forms(room["id"]) if not form.get("closed"))
    forms_text = [
        f"- 방내 #{form['room_form_no']} · ID {form['form_id']} · {form['kind']} · {form['title']} · {form['responses']}응답 · {form['status']}"
        for form in summaries
    ]
    message = (
        "진행중인 폼/투표:\n" + "\n".join(forms_text)
        if forms_text
        else "조건에 맞는 진행중 폼/투표가 없습니다."
    )
    return {
        "ok": True,
        "room_id": room["id"],
        "room_name": room["name"],
        "message": message,
        "important": "사용자에게 답할 때 방내 번호와 내부 ID를 함께 포함하세요.",
        "status_filter": status,
        "query": query,
        "forms": summaries,
        "forms_text": forms_text,
        "count": len(summaries),
        "total_matching": len(forms),
        "active_count": active_count,
        "next": (
            "진행중인 폼을 확인했습니다. 닫거나 결과를 볼 폼은 제목 또는 ID로 지정하세요."
            if summaries
            else "조건에 맞는 폼이 없습니다."
        ),
        "suggested_next_actions": [
            "특정 폼 결과 확인하기",
            "응답이 끝난 폼 마감하기",
            "새 의견수렴 또는 역할분배 이어가기",
        ],
        "chat_response_hint": (
            "대시보드 링크로만 안내하지 말고 message 또는 forms_text를 그대로 사용해 방내 번호, 내부 ID, 제목, 상태, 응답 수를 바로 요약하세요. "
            "같은 문장을 반복하지 마세요. 마감/결과 확인이 필요하면 사용자가 제목이나 ID로 말해도 된다고 안내하세요."
        ),
    }


def _general_guide_payload(
    *,
    rooms: list[dict[str, Any]] | None = None,
    guide_topic: str | None = None,
) -> dict[str, Any]:
    rooms = rooms or []
    has_rooms = bool(rooms)
    active_room = next((room for room in rooms if room.get("is_active")), None)
    if not has_rooms:
        state = "no_room"
        next_actions = [
            "새 팀플방 만들기",
            "초대 코드를 받았다면 방에 참여하기",
            "방을 만든 뒤 프로젝트 주제로 로드맵 잡기",
        ]
        examples = [
            "카카오 MCP 대회방 만들어줘",
            "초대 코드 ABC123으로 참여할래",
            "teamplay-talk 어떻게 써?",
        ]
    elif active_room is None:
        state = "rooms_exist_no_active_room"
        next_actions = [
            "작업할 방을 현재 방으로 전환하기",
            "방 목록에서 초대 코드와 역할 확인하기",
            "현재 방을 정한 뒤 로드맵이나 진행상태 확인하기",
        ]
        examples = [
            f"{rooms[0]['name']} 방으로 전환해줘",
            "내가 속한 방 목록 보여줘",
            "지금 방에서 다음에 뭐 하면 돼?",
        ]
    else:
        state = "active_room_available"
        next_actions = ["현재 방 상태를 기준으로 다음 단계 확인하기"]
        examples = ["지금 우리 방에서 다음에 뭐 하면 돼?"]

    flow = [
        "방 만들기",
        "팀원 초대",
        "주제로 로드맵 만들기",
        "로드맵 검토와 수정",
        "역할 분배",
        "개인별 할 일 만들기",
        "투표·회의시간·장소 조율",
        "데일리 체크인과 아침 리포트",
    ]
    topic_notes = {
        "roadmap": "로드맵은 프로젝트 주제를 큰 단계로 나누고, 팀 의견을 받아 수정한 뒤 역할과 할 일의 기준으로 씁니다.",
        "roles": "역할분배는 로드맵을 기준으로 워크스트림 역할을 만들고, 팀원 선호도와 난이도를 함께 봐서 배정합니다.",
        "todo": "개인별 할 일은 확정된 로드맵과 역할을 1~2일 안에 끝낼 수 있는 실행 단위로 쪼개 관리합니다.",
        "forms": "투표와 의견수렴은 카카오톡으로 폼을 보내고, 응답이 모이면 AI가 결과와 다음 결정을 정리합니다.",
        "daily": "데일리는 밤 체크인으로 완료·막힘을 받고, 아침 리포트로 오늘 할 일과 지연 이슈를 정리합니다.",
        "calendar": "회의나 마감이 정해지면 팀원별 카카오톡 캘린더에 등록해 놓치지 않게 돕습니다.",
    }
    topic = (guide_topic or "").strip().lower()
    topic_note = topic_notes.get(topic)
    return {
        "ok": True,
        "guide_mode": "general",
        "guide_topic": guide_topic,
        "state": state,
        "active_room": active_room["name"] if active_room else None,
        "rooms": [
            {"name": room["name"], "invite_code": room["invite_code"], "active": room.get("is_active")}
            for room in rooms
        ],
        "workflow": flow,
        "topic_note": topic_note,
        "next": (
            topic_note
            if topic_note
            else "처음이라면 방을 만들고 팀원을 초대한 뒤, 프로젝트 주제로 로드맵을 먼저 잡으면 됩니다."
        ),
        "suggested_next_actions": next_actions,
        "user_prompt_examples": examples,
        "chat_response_hint": (
            "홈페이지 링크를 주지 말고 채팅 안에서 사용법을 설명하세요. "
            "처음 사용자는 방 만들기부터 안내하고, 이미 방이 있으면 현재 방 기준 다음 단계를 물어보게 하세요. "
            "도구명이나 action명은 말하지 말고 사용자가 그대로 말할 수 있는 자연어 예시를 보여주세요."
        ),
    }


async def _guide_room(room_id: int | None, guide_topic: str | None = None) -> dict[str, Any]:
    caller = await resolve_caller()
    if caller is None:
        return {"ok": False, "error": "카카오 인증 정보가 없습니다. PlayMCP에서 카카오 계정 연결을 먼저 진행해 주세요."}

    if room_id is None:
        room = storage.get_active_room(caller["id"])
        if room is None:
            return _general_guide_payload(
                rooms=storage.list_user_rooms(caller["id"]),
                guide_topic=guide_topic,
            )
    else:
        room = storage.get_room(room_id)
        if room is None:
            return {"ok": False, "error": f"방 {room_id}를 찾을 수 없습니다."}
        if not storage.is_room_member(room_id, caller["id"]):
            return {"ok": False, "error": "이 방의 멤버만 이 작업을 할 수 있습니다."}

    members = storage.list_members(room["id"])
    forms = storage.list_room_forms(room["id"])
    active_forms = [form for form in forms if not form.get("closed")]
    roadmap = storage.get_roadmap(room["id"])
    tasks = roadmap.get("tasks", [])
    milestones = [task for task in tasks if (task.get("task_type") or "milestone") == "milestone"]
    todos = [task for task in tasks if (task.get("task_type") or "milestone") == "todo"]
    roles_assigned = [member for member in members if member.get("role")]
    assigned_todos = [task for task in todos if task.get("assignee_user_id") or task.get("assignee_role")]
    done_todos = [task for task in todos if task.get("status") == "done"]
    latest_decisions = {
        kind: {
            "id": decision["id"],
            "title": decision["title"],
            "summary": decision["summary"],
            "created_at": _iso(decision.get("created_at")),
        }
        for kind, decision in storage.latest_room_decisions(room["id"]).items()
    }

    if not milestones:
        stage = "roadmap_missing"
        next_actions = [
            "프로젝트 주제로 로드맵 만들기",
            "팀원에게 로드맵에 들어갈 단계 의견 받기",
            "팀원 초대 문구 다시 확인하기",
        ]
        examples = [
            "이 주제로 로드맵 짜줘",
            "로드맵이 괜찮은지 팀원 의견 받아줘",
            "초대 문구 다시 보여줘",
        ]
    elif not roles_assigned:
        stage = "roles_missing"
        next_actions = [
            "로드맵 기준으로 역할 후보 만들기",
            "역할 선호도 폼 보내기",
            "로드맵이 맞는지 먼저 팀원 의견 받기",
        ]
        examples = [
            "로드맵 기준으로 역할 나눠줘",
            "역할 선호도 조사 보내줘",
            "로드맵 수정 의견 받아줘",
        ]
    elif not todos:
        stage = "todos_missing"
        next_actions = [
            "로드맵과 역할을 개인별 실행 할 일로 쪼개기",
            "팀원별 할 일 목록 확인하기",
            "날짜가 있는 할 일을 캘린더에 등록하기",
        ]
        examples = [
            "역할별로 개인 할 일 만들어줘",
            "팀원별 할 일 보여줘",
            "날짜 있는 할 일 캘린더에 넣어줘",
        ]
    elif active_forms:
        stage = "waiting_for_responses"
        next_actions = [
            "진행 중인 폼 응답 수 확인하기",
            "응답이 충분하면 결과 정리하기",
            "응답이 끝난 폼 마감하기",
        ]
        examples = [
            "진행 중인 폼 뭐가 있어?",
            "응답 결과 정리해줘",
            "이 투표 마감해줘",
        ]
    else:
        stage = "running"
        next_actions = [
            "오늘 할 일과 밀린 일 확인하기",
            "회의 시간이나 장소 조율하기",
            "데일리 체크인 또는 아침 리포트 만들기",
        ]
        examples = [
            "팀원별 오늘 할 일 보여줘",
            "이번 주 회의 시간 잡아줘",
            "오늘 팀 리포트 만들어줘",
        ]

    topic = (guide_topic or "").strip().lower()
    topic_guides = {
        "roadmap": ["로드맵은 큰 milestone부터 만들고, 필요하면 팀 의견을 받아 수정합니다.", "그 다음 역할분배와 개인별 할 일로 이어갑니다."],
        "roles": ["역할은 로드맵 태스크명이 아니라 여러 일을 책임지는 워크스트림으로 나눕니다.", "예: 기획·PM, 구현, 연동, QA, 문서·발표."],
        "todo": ["할 일은 milestone 아래에 1~2일 단위 실행 항목으로 쪼갭니다.", "역할이 확정돼 있으면 실제 팀원에게 자동으로 연결합니다."],
        "forms": ["폼은 만들기와 발송이 분리됩니다.", "만든 뒤 팀원에게 보낼지 확인하고, 응답이 모이면 결과를 정리합니다."],
        "daily": ["밤에는 체크인으로 완료·막힘을 받고, 아침에는 리포트로 오늘 할 일을 정리합니다."],
        "calendar": ["확정된 회의나 날짜가 있는 할 일은 팀원별 카카오톡 캘린더에 등록할 수 있습니다."],
    }
    topic_notes = topic_guides.get(topic)
    status_lines = [
        f"팀원 {len(members)}명",
        f"로드맵 {len(milestones)}개 단계",
        f"역할 확정 {len(roles_assigned)}명",
        f"개인 할 일 {len(todos)}개",
        f"완료 {len(done_todos)}개",
        f"진행 중인 폼 {len(active_forms)}개",
    ]
    return {
        "ok": True,
        "guide_mode": "room",
        "guide_topic": guide_topic,
        "room_id": room["id"],
        "room_name": room["name"],
        "workflow_stage": stage,
        "status_summary": status_lines,
        "metrics": {
            "members": len(members),
            "milestones": len(milestones),
            "roles_assigned": len(roles_assigned),
            "todos": len(todos),
            "assigned_todos": len(assigned_todos),
            "done_todos": len(done_todos),
            "active_forms": len(active_forms),
        },
        "members": [{"nickname": member["nickname"], "role": member.get("role")} for member in members],
        "active_forms": [_form_summary(form) for form in active_forms[:8]],
        "latest_decisions": latest_decisions,
        "topic_notes": topic_notes,
        "next": "현재 방 상태를 기준으로 다음 단계를 골랐습니다.",
        "suggested_next_actions": next_actions,
        "user_prompt_examples": examples,
        "chat_response_hint": (
            "현재 상태를 1~2문장으로 요약하고, suggested_next_actions를 질문 형태로 제안하세요. "
            "도구명/action명은 노출하지 말고 user_prompt_examples처럼 사용자가 그대로 말할 수 있는 예시를 보여주세요. "
            "guide_topic이 있으면 topic_notes를 먼저 반영하세요."
        ),
    }


async def _resolve_form_id(
    room_id: int | None,
    *,
    form_id: int | None,
    query: str | None,
    status: str,
    action: str,
) -> tuple[int | None, dict[str, Any] | None]:
    if form_id is not None:
        _caller, room, error = await require_room(room_id)
        if error is None:
            forms = storage.list_room_forms(room["id"])
            if any(int(form["id"]) == int(form_id) for form in forms):
                return form_id, None
            room_no_matches = [
                form for form in forms
                if int(form.get("room_form_no") or -1) == int(form_id)
                and (status == "all" or (status == "closed") == bool(form.get("closed")))
            ]
            if len(room_no_matches) == 1:
                return int(room_no_matches[0]["id"]), None
        return form_id, None
    _caller, room, error = await require_room(room_id)
    if error:
        return None, error
    forms = [
        form for form in storage.list_room_forms(room["id"])
        if (status == "all" or (status == "closed") == bool(form.get("closed")))
        and _matches_form(form, query)
    ]
    if len(forms) == 1:
        return int(forms[0]["id"]), None
    return None, {
        "ok": False,
        "error": "대상 폼을 하나로 특정할 수 없습니다." if forms else "조건에 맞는 폼이 없습니다.",
        "needs_form_selection": True,
        "action": action,
        "query": query,
        "forms": [_form_summary(form) for form in forms[:12]],
        "next": "아래 목록에서 form_id나 제목을 지정해 다시 요청하세요.",
        "chat_response_hint": "사용자에게 후보 폼 목록을 보여주고, 어떤 폼을 마감/조회할지 확인하세요.",
    }


async def _run_legacy(tools: LegacyTools, name: str, args: dict[str, Any]) -> Any:
    tool = tools[name]
    call_args = _filter_args_for_tool(tool, args)
    missing = _missing_required_args(tool, call_args)
    if missing:
        return {
            "ok": False,
            "error": "필수 입력이 부족합니다.",
            "missing_arguments": missing,
            "target": name,
            "next": _missing_next_hint(name, missing),
        }
    result = await tool.run(call_args)
    if result.structured_content is not None:
        return _publicize_next_tool(result.structured_content)
    return {
        "ok": not result.is_error,
        "content": [getattr(item, "text", str(item)) for item in result.content],
    }


def _missing_next_hint(name: str, missing: list[str]) -> str:
    if name == "build_roadmap" and "tasks" in missing:
        return (
            "프로젝트 주제만 받은 상태입니다. 사용자에게 단계 목록을 요구하지 말고, "
            "AI가 4~6개 큰 마일스톤 초안을 먼저 제안한 뒤 확인되면 그 초안으로 로드맵 생성을 이어가세요."
        )
    if name == "assign_roles" and "roles" in missing:
        return "현재 로드맵을 기준으로 워크스트림 역할 후보를 생성해 role_manage(action='start')로 다시 시도하세요."
    if name in {"send_form", "get_poll_results", "close_poll", "finalize_roles", "apply_daily_checkin"}:
        return "대상 form_id를 확인한 뒤 다시 시도하세요."
    return "빠진 값을 채운 뒤 다시 시도하세요."


def install(mcp: FastMCP) -> None:
    """Replace many small public tools with fewer domain-level tools."""
    legacy = _local_tools(mcp)
    for names in CONSOLIDATED_GROUPS.values():
        _remove_public_tools(mcp, names)

    @mcp.tool(
        name="room_manage",
        annotations={
            "title": "방 관리",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def room_manage(
        action: Literal["create", "join", "switch", "list", "delete", "restore", "leave", "guide"],
        name: str | None = None,
        description: str | None = None,
        invite_code: str | None = None,
        guide_topic: str | None = None,
    ) -> dict[str, Any]:
        """팀플톡 방을 만들고, 참여하고, 현재 작업 방과 다음 단계를 안내합니다."""
        if action == "guide":
            return await _guide_room(None, guide_topic=guide_topic)
        target = {
            "create": "create_room",
            "join": "join_room",
            "switch": "switch_room",
            "list": "rooms",
            "delete": "delete_room",
            "restore": "restore_room",
            "leave": "leave_room",
        }[action]
        return await _run_legacy(legacy, target, {
            "name": name,
            "description": description,
            "invite_code": invite_code,
        })

    @mcp.tool(
        name="form_manage",
        annotations={
            "title": "폼 관리",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def form_manage(
        action: Literal["list", "send", "results", "close", "cancel"],
        form_id: int | None = None,
        query: str | None = None,
        status: Literal["active", "closed", "all"] = "active",
        room_id: int | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        """팀플톡 폼과 투표를 찾고, 보내고, 결과를 확인하거나 마감합니다.

        진행 중인 폼 목록을 확인하고, 만든 폼을 팀원에게 보내거나 응답 결과를 정리할
        때 사용합니다. 제목 일부로 찾을 수 있지만, 여러 폼이 비슷하면 폼 번호를 함께
        확인하는 편이 안전합니다.
        """
        if action == "list":
            return await _list_forms(room_id, status=status, query=query)
        lookup_status = "all" if action == "results" and status == "active" else status
        resolved_form_id, resolve_error = await _resolve_form_id(
            room_id,
            form_id=form_id,
            query=query,
            status=lookup_status,
            action=action,
        )
        if resolve_error is not None:
            return resolve_error
        target = {
            "send": "send_form",
            "results": "get_poll_results",
            "close": "close_poll",
            "cancel": "close_poll",
        }[action]
        return await _run_legacy(legacy, target, {"form_id": resolved_form_id, "message": message})

    @mcp.tool(
        name="role_manage",
        annotations={
            "title": "역할 분배",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def role_manage(
        action: Literal["start", "finalize", "set"],
        roles: list[dict[str, Any]] | None = None,
        form_id: int | None = None,
        assignments: list[dict[str, Any]] | None = None,
        room_id: int | None = None,
        close_minutes: int | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        """팀플톡 역할 선호도를 받고, 균형 잡힌 배정안을 계산하거나 확정합니다."""
        target = {
            "start": "assign_roles",
            "finalize": "finalize_roles",
            "set": "set_roles",
        }[action]
        return await _run_legacy(legacy, target, {
            "roles": roles,
            "form_id": form_id,
            "assignments": assignments,
            "room_id": room_id,
            "close_minutes": close_minutes,
            "message": message,
        })

    @mcp.tool(
        name="roadmap_manage",
        annotations={
            "title": "로드맵과 팀원 할 일",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def roadmap_manage(
        action: Literal["build", "view", "schedule", "decompose", "member_tasks", "digest"],
        tasks: list[dict[str, Any]] | None = None,
        edges: list[dict[str, Any]] | None = None,
        topic: str | None = None,
        replace_existing: bool = False,
        start_date: str | None = None,
        final_date: str | None = None,
        final_milestone: str | None = None,
        todos: list[dict[str, Any]] | None = None,
        member: str | None = None,
        window: Literal["all", "today", "week", "overdue", "upcoming", "no_date"] = "week",
        include_done: bool = False,
        dry_run: bool = False,
        room_id: int | None = None,
    ) -> dict[str, Any]:
        """프로젝트 로드맵을 만들고, 일정과 팀원별 할 일로 이어갑니다."""
        target = {
            "build": "build_roadmap",
            "view": "view_roadmap",
            "schedule": "schedule_roadmap",
            "decompose": "decompose_roadmap",
            "member_tasks": "member_tasks",
            "digest": "daily_task_digest",
        }[action]
        return await _run_legacy(legacy, target, {
            "tasks": tasks,
            "edges": edges,
            "topic": topic,
            "replace_existing": replace_existing,
            "start_date": start_date,
            "final_date": final_date,
            "final_milestone": final_milestone,
            "todos": todos,
            "member": member,
            "window": window,
            "include_done": include_done,
            "dry_run": dry_run,
            "room_id": room_id,
        })

    @mcp.tool(
        name="task_manage",
        annotations={
            "title": "로드맵 태스크 편집",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def task_manage(
        action: Literal["add", "update", "delete"],
        task_id: int | None = None,
        title: str | None = None,
        details: str | None = None,
        assignee: str | None = None,
        status: str | None = None,
        task_type: Literal["todo", "milestone"] | None = None,
        parent_task_id: int | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
        after_task_ids: list[int] | None = None,
        before_task_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """로드맵의 개별 할 일을 추가하거나 수정하고 삭제합니다."""
        target = {"add": "add_task", "update": "update_task", "delete": "delete_task"}[action]
        return await _run_legacy(legacy, target, {
            "task_id": task_id,
            "title": title,
            "details": details,
            "assignee": assignee,
            "status": status,
            "task_type": task_type,
            "parent_task_id": parent_task_id,
            "start_at": start_at,
            "end_at": end_at,
            "after_task_ids": after_task_ids,
            "before_task_ids": before_task_ids,
        })

    @mcp.tool(
        name="daily_manage",
        annotations={
            "title": "데일리 체크인과 리포트",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def daily_manage(
        action: Literal["create_checkin", "apply_checkin", "report"],
        room_id: int | None = None,
        form_id: int | None = None,
        checkin_date: str | None = None,
        close_minutes: int | None = None,
        skip_existing: bool = True,
        dry_run: bool = True,
        report_date: str | None = None,
        checkin_form_id: int | None = None,
        apply_checkin: bool = True,
        publish: bool = False,
    ) -> dict[str, Any]:
        """데일리 체크인을 만들고, 응답을 할 일 상태와 팀 리포트에 반영합니다."""
        target = {
            "create_checkin": "create_daily_checkin",
            "apply_checkin": "apply_daily_checkin",
            "report": "daily_report",
        }[action]
        return await _run_legacy(legacy, target, {
            "room_id": room_id,
            "form_id": form_id,
            "checkin_date": checkin_date,
            "close_minutes": close_minutes,
            "skip_existing": skip_existing,
            "dry_run": dry_run,
            "report_date": report_date,
            "checkin_form_id": checkin_form_id,
            "apply_checkin": apply_checkin,
            "publish": publish,
        })

    @mcp.tool(
        name="calendar_team",
        annotations={
            "title": "팀 캘린더 등록",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def calendar_team(
        action: Literal["room_event", "task_events"],
        title: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
        room_id: int | None = None,
        all_day: bool = False,
        description: str | None = None,
        reminders: list[int] | None = None,
        color: str | None = None,
        time_zone: str = "Asia/Seoul",
        rrule: str | None = None,
        calendar_id: str = "primary",
        task_ids: list[int] | None = None,
        include_done: bool = False,
        default_minutes: int = 30,
    ) -> dict[str, Any]:
        """회의나 배정된 로드맵 할 일을 팀원들의 카카오톡 캘린더에 등록합니다."""
        target = {
            "room_event": "calendar_create_room_event",
            "task_events": "calendar_create_task_events",
        }[action]
        return await _run_legacy(legacy, target, {
            "title": title,
            "start_at": start_at,
            "end_at": end_at,
            "room_id": room_id,
            "all_day": all_day,
            "description": description,
            "reminders": reminders,
            "color": color,
            "time_zone": time_zone,
            "rrule": rrule,
            "calendar_id": calendar_id,
            "task_ids": task_ids,
            "include_done": include_done,
            "default_minutes": default_minutes,
        })

    @mcp.tool(
        name="calendar_personal",
        annotations={
            "title": "개인 캘린더 관리",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def calendar_personal(
        action: Literal["create", "list", "get", "update", "delete"],
        event_id: str | None = None,
        title: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
        all_day: bool = False,
        description: str | None = None,
        reminders: list[int] | None = None,
        color: str | None = None,
        time_zone: str = "Asia/Seoul",
        rrule: str | None = None,
        recur_update_type: str | None = None,
        calendar_id: str | None = None,
        from_at: str | None = None,
        to_at: str | None = None,
        preset: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """내 카카오톡 캘린더 일정을 만들고 확인하거나 수정, 삭제합니다."""
        target = {
            "create": "calendar_create_event",
            "list": "calendar_list_events",
            "get": "calendar_get_event",
            "update": "calendar_update_event",
            "delete": "calendar_delete_event",
        }[action]
        return await _run_legacy(legacy, target, {
            "event_id": event_id,
            "title": title,
            "start_at": start_at,
            "end_at": end_at,
            "all_day": all_day,
            "description": description,
            "reminders": reminders,
            "color": color,
            "time_zone": time_zone,
            "rrule": rrule,
            "recur_update_type": recur_update_type,
            "calendar_id": calendar_id,
            "from_at": from_at,
            "to_at": to_at,
            "preset": preset,
            "limit": limit,
        })
