"""툴 응답 크기 가드 미들웨어.

PlayMCP 네이티브 AI 채팅은 Tool response 텍스트가 24k를 초과하면 에러 처리될 수
있다. 큰 응답이 "too large content part"로 막히면 툴은 성공했는데 출력만 실패한
것처럼 보인다.

이 미들웨어는 **실제로 대용량을 뱉는 특정 툴(roadmap_manage decompose)에만**
적용한다 — content 텍스트가 안전선을 넘으면 큰 배열을 개수+샘플로 줄이고 대시보드
안내 힌트를 붙여 축소한다. 평소 응답은 그대로 두고, 정책 한도에 가까운 응답만
줄인다.
- 데이터(DB)엔 영향 없음 — 축소는 채팅 출력 텍스트만.
- 긴 대시보드 URL은 넣지 않는다. 대신 AI가 room_dashboard를 호출해 안내하도록
  힌트만 준다(응답 예산을 아끼기 위함).
- DB/네트워크 호출이 없어 지연시간 영향 없음.

임계값은 아래 상수로 튜닝한다.
"""

from __future__ import annotations

import json
from typing import Any

from fastmcp.server.middleware import Middleware
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

MAX_CHARS = 18_000    # PlayMCP 24k 정책 한도 전 안전선. 넘으면 축소.
ARRAY_SAMPLE = 8      # 이 개수를 넘는 배열은 샘플+개수로 줄인다.
STRING_CAP = 1_200    # 긴 문자열은 이 길이로 자른다.
HARD_CAP = 20_000     # 축소 결과도 이보다 크면 더 작은 폴백으로 줄인다.

_HINT = "결과가 커서 요약만 반환됨. 전체 상세는 room_dashboard 링크로 안내하세요."


# 압축을 우선 적용할 큰-출력 툴 (name, action).
_COMPACT_TARGETS: set[tuple[str, str | None]] = {
    ("roadmap_manage", "build"),
    ("roadmap_manage", "view"),
    ("roadmap_manage", "schedule"),
    ("roadmap_manage", "decompose"),
    ("roadmap_manage", "member_tasks"),
}


def _tool_key(context) -> tuple[str | None, str | None]:
    msg = getattr(context, "message", None)
    name = getattr(msg, "name", None)
    args = getattr(msg, "arguments", None) or {}
    action = args.get("action") if isinstance(args, dict) else None
    return name, action


def _should_prefer_compaction(context) -> bool:
    return _tool_key(context) in _COMPACT_TARGETS


def _text_len(result: ToolResult) -> int:
    for c in result.content or []:
        if isinstance(c, TextContent):
            return len(c.text or "")
    return 0


def _extract_dict(result: ToolResult) -> dict[str, Any]:
    data = result.structured_content
    if isinstance(data, dict):
        return data
    for c in result.content or []:
        if isinstance(c, TextContent):
            try:
                parsed = json.loads(c.text)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return {"result_text": (c.text or "")[:STRING_CAP]}
    return {"result": str(data)[:STRING_CAP] if data is not None else ""}


_DASH_NOTE = "전체 목록은 room_dashboard 링크로 안내하세요."


def _json_len(data: dict[str, Any]) -> int:
    return len(json.dumps(data, ensure_ascii=False))


def _sample_list(items: list[Any], limit: int = ARRAY_SAMPLE) -> dict[str, Any]:
    return {
        "_count": len(items),
        "items": items[:limit],
        "truncated": len(items) > limit,
    }


def _task_brief(task: Any) -> Any:
    if not isinstance(task, dict):
        return task
    return {
        key: task.get(key)
        for key in (
            "id",
            "title",
            "status",
            "assignee",
            "assignee_nickname",
            "assignee_role",
            "parent_task_id",
            "start_at",
            "end_at",
        )
        if task.get(key) is not None
    }


def _todo_group_brief(group: Any) -> Any:
    if not isinstance(group, dict):
        return group
    todos = [_task_brief(todo) for todo in group.get("todos", []) if isinstance(todo, dict)]
    return {
        key: value for key, value in {
            "milestone": group.get("milestone"),
            "assignee": group.get("assignee"),
            "todo_count": group.get("todo_count", len(todos)),
            "todos": todos[:5],
        }.items()
        if value is not None
    }


def _primary_result_brief(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    out: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"created_todos", "existing_todos"} and isinstance(item, list):
            out[key] = _sample_list([_task_brief(todo) for todo in item], 12)
        elif key in {"todos_by_milestone", "todos_by_assignee"} and isinstance(item, list):
            out[key] = _sample_list([_todo_group_brief(group) for group in item], 8)
        elif isinstance(item, str) and len(item) > STRING_CAP:
            out[key] = item[: STRING_CAP - 1] + "…"
        else:
            out[key] = item
    return out


def _sync_summary(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    return {
        "mapped_count": value.get("mapped_count", 0),
        "unmatched_count": value.get("unmatched_count", 0),
    }


def _roadmap_overview(data: dict[str, Any]) -> dict[str, Any]:
    """Roadmap 결과는 AI가 다음 행동을 잡을 수 있게 상태와 샘플을 남긴다."""
    created = [_task_brief(task) for task in data.get("created_todos", []) if isinstance(task, dict)]
    todos = [_task_brief(task) for task in data.get("todo_tasks", []) if isinstance(task, dict)]
    milestones = [
        {
            "id": item.get("id"),
            "title": item.get("title"),
            "start_at": item.get("start_at"),
            "end_at": item.get("end_at"),
            "todo_count": len(item.get("todos") or []),
        }
        for item in data.get("milestones", [])
        if isinstance(item, dict)
    ]
    by_member = []
    for member in data.get("by_member", []):
        if not isinstance(member, dict):
            continue
        tasks = [_task_brief(task) for task in member.get("tasks", []) if isinstance(task, dict)]
        by_member.append({
            "nickname": member.get("nickname"),
            "role": member.get("role"),
            "task_count": len(tasks),
            "progress": member.get("progress") or member.get("filtered_progress"),
            "tasks": tasks[:5],
        })

    out: dict[str, Any] = {
        "ok": data.get("ok"),
        "error": data.get("error"),
        "room_id": data.get("room_id"),
        "room": data.get("room"),
        "topic": data.get("topic"),
        "primary_result": _primary_result_brief(data.get("primary_result")),
        "created_count": data.get("created_count"),
        "auto_generated": data.get("auto_generated"),
        "needs_role_assignment": data.get("needs_role_assignment"),
        "required_next_tool": data.get("required_next_tool"),
        "required_next_action": data.get("required_next_action"),
        "required_next_arguments": data.get("required_next_arguments"),
        "next": data.get("next"),
        "task_layer_summary": data.get("task_layer_summary"),
        "schedule_state": data.get("schedule_state"),
        "date_planning": data.get("date_planning"),
        "date_planning_prompt": data.get("date_planning_prompt"),
        "progress": data.get("progress"),
        "synced_todos": _sync_summary(data.get("synced_todos")),
        "milestone_titles": data.get("milestone_titles", [])[:12],
        "milestones": _sample_list(milestones, 8),
        "created_todos": _sample_list(created, 12) if created else None,
        "created_todos_by_milestone": _sample_list([
            _todo_group_brief(group) for group in data.get("created_todos_by_milestone", [])
            if isinstance(group, dict)
        ], 8) if data.get("created_todos_by_milestone") else None,
        "existing_todos_by_milestone": _sample_list([
            _todo_group_brief(group) for group in data.get("existing_todos_by_milestone", [])
            if isinstance(group, dict)
        ], 8) if data.get("existing_todos_by_milestone") else None,
        "todo_tasks": _sample_list(todos, 12) if todos else None,
        "by_member": _sample_list(by_member, 8) if by_member else None,
        "unassigned_tasks": {"_count": len(data.get("unassigned_tasks") or [])},
        "role_only_tasks": {"_count": len(data.get("role_only_tasks") or [])},
        "suggested_next_actions": (data.get("suggested_next_actions") or [])[:6],
        "chat_response_hint": data.get("chat_response_hint"),
        "_truncated": True,
    }
    return {key: value for key, value in out.items() if value is not None}


def _overview(data: dict[str, Any]) -> dict[str, Any]:
    """개요만 남긴다 — 큰 배열은 개수로 접고, 긴 문자열은 자르며, count·next·상태
    같은 스칼라 요약 필드는 유지한다. AI가 쓸모있는 요약을 하도록."""
    out: dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, list):
            out[k] = _sample_list(v) if len(v) > ARRAY_SAMPLE else v
        elif isinstance(v, str) and len(v) > STRING_CAP:
            out[k] = v[: STRING_CAP - 1] + "…"
        else:
            out[k] = v
    out["_truncated"] = True
    # 기존 chat_response_hint(툴 고유 안내)를 살리고 대시보드 안내만 덧붙인다.
    existing = out.get("chat_response_hint")
    out["chat_response_hint"] = (
        f"{existing} {_DASH_NOTE}" if isinstance(existing, str) else f"{_HINT}"
    )
    return out


def _minimal(data: dict[str, Any]) -> dict[str, Any]:
    """개요조차 큰 드문 경우 — 핵심 스칼라 + 힌트만."""
    keep: dict[str, Any] = {}
    for k in (
        "ok",
        "error",
        "status",
        "count",
        "created_count",
        "auto_generated",
        "needs_role_assignment",
        "required_next_tool",
        "required_next_action",
        "next",
        "task_layer_summary",
        "schedule_state",
        "date_planning",
        "date_planning_prompt",
        "primary_result",
    ):
        v = data.get(k)
        if k == "primary_result":
            v = _primary_result_brief(v)
        if isinstance(v, (bool, int, float, dict)) or (isinstance(v, str) and len(v) <= STRING_CAP):
            keep[k] = v
    keep["_truncated"] = True
    keep["chat_response_hint"] = _HINT
    return keep


def _shrink_to_fit(data: dict[str, Any], *, tool_key: tuple[str | None, str | None]) -> dict[str, Any]:
    overview = _roadmap_overview(data) if tool_key[0] == "roadmap_manage" else _overview(data)
    if _json_len(overview) <= HARD_CAP:
        return overview
    return _minimal(data)


class ResponseSizeGuard(Middleware):
    """content 텍스트가 MAX_CHARS를 넘으면 축소해 네이티브 한도 초과를 막는다."""

    async def on_call_tool(self, context, call_next):
        result = await call_next(context)
        try:
            text_len = _text_len(result)
            if text_len <= MAX_CHARS:
                return result
            tool_key = _tool_key(context)
            # Prefer compacting known large tools, but protect any tool call that would exceed
            # the PlayMCP policy limit.
            if not _should_prefer_compaction(context) and text_len <= HARD_CAP:
                return result
            compact = _shrink_to_fit(_extract_dict(result), tool_key=tool_key)
            text = json.dumps(compact, ensure_ascii=False)
            return ToolResult(
                content=[TextContent(type="text", text=text)],
                structured_content=compact,
                meta=getattr(result, "meta", None),
                is_error=getattr(result, "is_error", False),
            )
        except Exception:
            # 가드 실패가 툴 실패가 되면 안 된다.
            return result
