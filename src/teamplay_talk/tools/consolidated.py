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
    if not allowed:
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
            "로드맵을 만들려면 큰 단계 목록이 필요합니다. 프로젝트 주제를 바탕으로 "
            "4~6개의 milestone을 직접 구성해 tasks에 넣어 다시 시도하세요."
        )
    if name == "assign_roles" and "roles" in missing:
        return "역할분배를 시작하려면 프로젝트에 필요한 역할 목록을 먼저 구성해 roles에 넣어 다시 시도하세요."
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
            "title": "Room Management",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def room_manage(
        action: Literal["create", "join", "switch", "list", "delete", "restore", "leave"],
        name: str | None = None,
        description: str | None = None,
        invite_code: str | None = None,
    ) -> dict[str, Any]:
        """Manage teamplay-talk(팀플톡) rooms: create, join, switch, list, delete, restore, or leave."""
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
            "title": "Form Follow-up",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def form_manage(
        action: Literal["send", "results", "close"],
        form_id: int,
        message: str | None = None,
    ) -> dict[str, Any]:
        """Send, read results, or close an existing teamplay-talk(팀플톡) form/poll."""
        target = {
            "send": "send_form",
            "results": "get_poll_results",
            "close": "close_poll",
        }[action]
        return await _run_legacy(legacy, target, {"form_id": form_id, "message": message})

    @mcp.tool(
        name="role_manage",
        annotations={
            "title": "Role Assignment Flow",
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
        """Run teamplay-talk(팀플톡) role assignment: start preference form, compute assignment, or save roles."""
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
            "title": "Roadmap and Member Tasks",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def roadmap_manage(
        action: Literal["build", "view", "decompose", "member_tasks", "digest"],
        tasks: list[dict[str, Any]] | None = None,
        edges: list[dict[str, Any]] | None = None,
        topic: str | None = None,
        replace_existing: bool = False,
        todos: list[dict[str, Any]] | None = None,
        member: str | None = None,
        window: Literal["all", "today", "week", "overdue", "upcoming", "no_date"] = "week",
        include_done: bool = False,
        dry_run: bool = False,
        room_id: int | None = None,
    ) -> dict[str, Any]:
        """Build/view/decompose a teamplay-talk(팀플톡) roadmap or inspect/notify member tasks."""
        target = {
            "build": "build_roadmap",
            "view": "view_roadmap",
            "decompose": "decompose_roadmap",
            "member_tasks": "member_tasks",
            "digest": "daily_task_digest",
        }[action]
        return await _run_legacy(legacy, target, {
            "tasks": tasks,
            "edges": edges,
            "topic": topic,
            "replace_existing": replace_existing,
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
            "title": "Roadmap Task Editing",
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
        """Add, update, or delete one teamplay-talk(팀플톡) roadmap task."""
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
            "title": "Daily Check-in and Report",
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
        """Create/apply daily check-ins or build a teamplay-talk(팀플톡) daily report."""
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
            "title": "Team Calendar Registration",
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
        """Register meeting or assigned roadmap task events to team members' KakaoTalk calendars."""
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
            "title": "Personal Calendar CRUD",
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
        """Create, list, get, update, or delete the caller's KakaoTalk calendar events."""
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
