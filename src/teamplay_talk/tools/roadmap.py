"""로드맵 도메인 도구 — 프로젝트 타임라인(태스크 그래프).

로드맵은 **방(현재 작업 방)의 태스크 그래프**다. 태스크(노드)들이 의존 엣지
(선행→후행)로 연결돼 프로젝트 전체 타임라인을 이룬다. 각 태스크엔 세부사항,
담당(팀원 또는 역할), 일정(start/end), 상태가 들어간다.

주제 분석은 호출 측 AI가 수행한다: AI가 주제를 보고 태스크/엣지를 생성해
``build_roadmap`` 으로 넘기면 서버는 저장한다(서버엔 LLM 없음).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import kakao_store, storage
from ..identity import resolve_caller
from .guards import require_room

_KST = timezone(timedelta(hours=9))

_NEED_AUTH = {
    "ok": False,
    "error": "카카오 인증 정보가 없습니다. PlayMCP에서 카카오 계정 연결을 먼저 진행해 주세요.",
}
_NO_ROOM = {
    "ok": False,
    "error": "현재 작업 중인 방이 없습니다. 방을 만들거나 참여(switch_room)한 뒤 다시 시도하세요.",
}


class TodoDraft(BaseModel):
    title: str = Field(description="실행 가능한 구체 todo 제목. 1~2일 안에 끝낼 수 있는 단위 권장.")
    details: str | None = Field(default=None, description="완료 기준, 산출물, 참고 맥락")
    assignee: str | None = Field(default=None, description="담당 팀원 닉네임 또는 확정된 역할명")
    parent_task_id: int | None = Field(default=None, description="상위 로드맵 milestone 태스크 ID")
    parent_title: str | None = Field(default=None, description="parent_task_id를 모르면 상위 milestone 제목")
    start_at: str | None = Field(default=None, description="시작 시각 UTC RFC3339")
    end_at: str | None = Field(default=None, description="마감 시각 UTC RFC3339")
    status: Literal["todo", "doing", "done"] = Field(default="todo", description="진행 상태")


def _iso(dt: Any) -> str | None:
    return dt.isoformat() if dt is not None and hasattr(dt, "isoformat") else dt


def _task_payload(t: dict[str, Any]) -> dict[str, Any]:
    assignee = t.get("assignee_nickname") or t.get("assignee_role")
    return {
        "id": t["id"],
        "title": t["title"],
        "details": t.get("details"),
        "assignee": assignee,
        "assignee_user_id": t.get("assignee_user_id"),
        "assignee_role": t.get("assignee_role"),
        "assignee_member_role": t.get("assignee_member_role"),
        "status": t["status"],
        "task_type": t.get("task_type") or "milestone",
        "parent_task_id": t.get("parent_task_id"),
        "parent_title": t.get("parent_title"),
        "start_at": _iso(t.get("start_at")),
        "end_at": _iso(t.get("end_at")),
    }


def _task_due_label(task: dict[str, Any]) -> str:
    end_at = task.get("end_at")
    start_at = task.get("start_at")
    if end_at:
        return f"마감 {end_at}"
    if start_at:
        return f"시작 {start_at}"
    return "일정 미정"


def _parse_task_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_KST)


def _task_date_bounds(task: dict[str, Any]) -> tuple[Any | None, Any | None]:
    start = _parse_task_dt(task.get("start_at"))
    end = _parse_task_dt(task.get("end_at"))
    start_day = start.date() if start else None
    end_day = end.date() if end else None
    if start_day is None and end_day is not None:
        start_day = end_day
    if end_day is None and start_day is not None:
        end_day = start_day
    return start_day, end_day


def _task_matches_window(
    task: dict[str, Any],
    window: str,
    today: Any,
    *,
    include_done: bool,
) -> bool:
    if not include_done and task.get("status") == "done":
        return False
    if window == "all":
        return True
    start_day, end_day = _task_date_bounds(task)
    if window == "no_date":
        return start_day is None and end_day is None
    if start_day is None or end_day is None:
        return False
    if window == "today":
        return start_day <= today <= end_day
    if window == "week":
        week_end = today + timedelta(days=7)
        return start_day <= week_end and end_day >= today
    if window == "overdue":
        return end_day < today and task.get("status") != "done"
    if window == "upcoming":
        return end_day >= today and task.get("status") != "done"
    return True


def _member_task_buckets(roadmap: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    buckets = {
        m["id"]: {
            "member_id": m["id"],
            "nickname": m["nickname"],
            "role": m.get("role"),
            "tasks": [],
            "progress": {"done": 0, "total": 0},
        }
        for m in roadmap.get("members", [])
    }
    unassigned: list[dict[str, Any]] = []
    for task in roadmap.get("tasks", []):
        payload = _task_payload(task)
        if payload.get("task_type") != "todo":
            continue
        member_id = task.get("assignee_user_id")
        if member_id in buckets:
            buckets[member_id]["tasks"].append(payload)
            buckets[member_id]["progress"]["total"] += 1
            if task.get("status") == "done":
                buckets[member_id]["progress"]["done"] += 1
        else:
            unassigned.append(payload)
    return list(buckets.values()), unassigned


def _resolve_parent_task_id(
    roadmap: dict[str, Any],
    *,
    parent_task_id: int | None,
    parent_title: str | None,
) -> int | None:
    tasks = roadmap.get("tasks", [])
    milestone_ids = {
        int(t["id"]) for t in tasks
        if (t.get("task_type") or "milestone") == "milestone"
    }
    if parent_task_id in milestone_ids:
        return parent_task_id
    title = (parent_title or "").strip().lower()
    if not title:
        return None
    exact = [
        t for t in tasks
        if (t.get("task_type") or "milestone") == "milestone"
        and str(t.get("title") or "").strip().lower() == title
    ]
    if len(exact) == 1:
        return int(exact[0]["id"])
    fuzzy = [
        t for t in tasks
        if (t.get("task_type") or "milestone") == "milestone"
        and (
            title in str(t.get("title") or "").strip().lower()
            or str(t.get("title") or "").strip().lower() in title
        )
    ]
    if len(fuzzy) == 1:
        return int(fuzzy[0]["id"])
    return None


def _member_digest_message(room_name: str, member: dict[str, Any], *, include_done: bool = False) -> str | None:
    tasks = [
        t for t in member.get("tasks", [])
        if include_done or t.get("status") != "done"
    ]
    if not tasks:
        return None
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    lines = [
        f"📌 팀플톡 오늘 할 일 · {room_name}",
        f"{member['nickname']}님 담당 태스크 ({today})",
        "",
    ]
    for t in tasks:
        status = {"todo": "대기", "doing": "진행중", "done": "완료"}.get(t.get("status"), t.get("status"))
        lines.append(f"· {t['title']} [{status}]")
        lines.append(f"  - {_task_due_label(t)}")
        if t.get("details"):
            lines.append(f"  - {t['details']}")
    lines.extend([
        "",
        "완료했으면 팀플톡에서 update_task로 상태를 done으로 바꾸면 돼요.",
    ])
    return "\n".join(lines)


def _format(roadmap: dict[str, Any]) -> dict[str, Any]:
    """저장 계층 결과를 출력용으로 정리(담당자·개인별 할일·진척률)."""
    tasks = roadmap["tasks"]
    todo_rows = [t for t in tasks if (t.get("task_type") or "milestone") == "todo"]
    milestone_rows = [t for t in tasks if (t.get("task_type") or "milestone") == "milestone"]
    done = sum(1 for t in todo_rows if t["status"] == "done")
    formatted_tasks = [_task_payload(t) for t in tasks]
    formatted_todos = [_task_payload(t) for t in todo_rows]
    formatted_milestones = [_task_payload(t) for t in milestone_rows]
    todos_by_parent: dict[int, list[dict[str, Any]]] = {}
    for todo in formatted_todos:
        parent_id = todo.get("parent_task_id")
        if parent_id is not None:
            todos_by_parent.setdefault(int(parent_id), []).append(todo)
    milestones = [
        {**m, "todos": todos_by_parent.get(int(m["id"]), [])}
        for m in formatted_milestones
    ]
    member_buckets = {
        m["id"]: {
            "member_id": m["id"],
            "nickname": m["nickname"],
            "role": m.get("role"),
            "tasks": [],
            "progress": {"done": 0, "total": 0},
        }
        for m in roadmap.get("members", [])
    }
    unassigned_tasks: list[dict[str, Any]] = []
    calendar_candidates: list[dict[str, Any]] = []
    role_only_tasks: list[dict[str, Any]] = []
    for t, payload in zip(tasks, formatted_tasks, strict=False):
        if payload.get("task_type") != "todo":
            continue
        member_id = t.get("assignee_user_id")
        if member_id in member_buckets:
            member_buckets[member_id]["tasks"].append(payload)
            member_buckets[member_id]["progress"]["total"] += 1
            if t["status"] == "done":
                member_buckets[member_id]["progress"]["done"] += 1
            if payload.get("start_at") or payload.get("end_at"):
                calendar_candidates.append({
                    "member_id": member_id,
                    "nickname": t.get("assignee_nickname"),
                    "task_id": t["id"],
                    "title": t["title"],
                    "start_at": payload.get("start_at"),
                    "end_at": payload.get("end_at"),
                })
        else:
            unassigned_tasks.append(payload)
            if payload.get("assignee_role"):
                role_only_tasks.append(payload)

    by_member = [
        bucket for bucket in member_buckets.values()
        if bucket["tasks"] or bucket.get("role")
    ]
    needs_todo_decomposition = bool(milestone_rows) and not bool(todo_rows)
    return {
        "tasks": formatted_tasks,
        "milestones": milestones,
        "todo_tasks": formatted_todos,
        "edges": [
            {"from": e["from_task_id"], "to": e["to_task_id"]} for e in roadmap["edges"]
        ],
        "progress": {"done": done, "total": len(todo_rows)},
        "task_layer_summary": {
            "milestones": len(milestone_rows),
            "todos": len(todo_rows),
            "assigned_todos": len(todo_rows) - len(unassigned_tasks),
            "role_only_todos": len(role_only_tasks),
            "unassigned_todos": len(unassigned_tasks),
            "needs_todo_decomposition": needs_todo_decomposition,
            "needs_role_assignment": bool(role_only_tasks),
        },
        "by_member": by_member,
        "unassigned_tasks": unassigned_tasks,
        "role_only_tasks": role_only_tasks,
        "calendar_candidates": calendar_candidates,
        "next": (
            "로드맵 단계와 실행 todo를 구분했습니다. todo가 비어 있으면 decompose_roadmap으로 "
            "각 milestone을 멤버별 실행 항목으로 쪼개세요."
        ),
        "suggested_next_actions": [
            "todo가 없으면 decompose_roadmap으로 milestone 아래 실행 todo 2~5개씩 생성",
            "role_only_todos가 있으면 set_roles로 역할을 확정하거나 sync가 되도록 역할명을 맞춘 뒤 member_tasks 확인",
            "역할분배가 필요하면 태스크명을 그대로 쓰지 말고 기획·PM/구현/연동/QA/문서·발표 같은 워크스트림 역할로 assign_roles",
            "notify_room으로 개인별 할일 요약 공지",
            "daily_task_digest로 담당자별 할일 개인 공지",
            "일정이 있는 태스크를 캘린더/리마인더 후보로 검토",
            "진행 상황이 바뀌면 update_task로 상태 갱신",
            "room_dashboard로 투표/로드맵 흐름 확인",
        ],
        "role_assignment_guidance": (
            "로드맵 단계명은 역할이 아닙니다. 역할분배를 할 때는 여러 태스크를 책임지는 "
            "역량/워크스트림 역할(예: 기획·PM, MCP 서버·도구 구현, 카카오 API·OAuth 연동, "
            "테스트·QA, 문서·데모·발표)을 만들어 assign_roles에 넣으세요."
        ),
    }


def register(mcp: FastMCP) -> None:
    """로드맵 도메인 도구를 등록한다."""

    @mcp.tool(
        name="build_roadmap",
        annotations={
            "title": "로드맵 생성",
            "readOnlyHint": False,
            "destructiveHint": True,  # 기존 로드맵을 교체한다
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def build_roadmap(
        tasks: list[dict[str, Any]],
        edges: list[dict[str, Any]] | None = None,
        topic: str | None = None,
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        """Builds the current room's project roadmap as a task graph in teamplay-talk(팀플톡).

        팀플톡(teamplay-talk) 현재 작업 방의 로드맵(프로젝트 타임라인)을 태스크
        그래프로 생성한다. 기존 로드맵이 있으면 기본적으로 교체하지 않는다.
        전체 교체가 명시적으로 필요할 때만 replace_existing=true를 넘긴다.
        호출 측 AI가 주제를 분석해 태스크와 의존 엣지를 만들어 넘긴다.
        여기서 tasks는 큰 단계/마일스톤이어야 한다. 개인별 실행 todo는 역할 확정 뒤
        decompose_roadmap으로 별도 생성한다.
        시간은 UTC RFC3339(예: 2026-07-01T00:00:00Z).

        Args:
            tasks: 태스크 목록. 각 항목은
                {"key": 임시ID, "title": 제목, "details": 세부(선택),
                 "assignee": 담당 팀원 닉네임 또는 set_roles로 확정된 역할명(선택),
                 "start_at": 시작(선택), "end_at": 종료(선택),
                 "status": "todo"|"doing"|"done"(선택, 기본 todo)}.
                assignee에 역할명을 넣으면 room_members.role을 보고 실제 담당자에 자동 연결한다.
                task_type은 보통 생략한다(기본 milestone).
                key는 edges에서 태스크를 가리키는 데 쓰는 임시 식별자.
            edges: 의존 엣지 목록 [{"from": key, "to": key}] (선행→후행, 선택)
            topic: 로드맵 주제 메모 (선택)
            replace_existing: 기존 로드맵 전체 교체 여부. 기본 false.
        """
        caller = await resolve_caller()
        if caller is None:
            return _NEED_AUTH
        room = storage.get_active_room(caller["id"])
        if room is None:
            return _NO_ROOM
        if not tasks:
            return {"ok": False, "error": "tasks가 비어 있습니다."}
        existing = storage.get_roadmap(room["id"])
        if existing["tasks"] and not replace_existing:
            return {
                "ok": False,
                "error": "이미 로드맵이 있습니다. build_roadmap은 전체 교체라 기본 실행을 막았습니다.",
                "existing_task_count": len(existing["tasks"]),
                "required_confirmation": "정말 전체 교체하려면 replace_existing=true로 다시 호출하세요.",
                "suggested_next_actions": [
                    "기존 로드맵 확인은 view_roadmap",
                    "일부 수정은 update_task",
                    "새 할일 추가는 add_task",
                    "역할 확정 뒤 담당자만 정리하려면 update_task의 assignee를 역할명/닉네임으로 수정",
                ],
            }
        roadmap = storage.set_roadmap(room["id"], tasks, edges or [])
        formatted = _format(roadmap)
        return {
            "ok": True,
            "room": room["name"],
            "topic": topic,
            "replaced_existing": bool(existing["tasks"]),
            **formatted,
        }

    @mcp.tool(
        name="view_roadmap",
        annotations={
            "title": "로드맵 조회",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def view_roadmap() -> dict[str, Any]:
        """Views the current room's roadmap (task graph + progress) in teamplay-talk(팀플톡).

        팀플톡(teamplay-talk) 현재 작업 방의 로드맵을 조회한다. 태스크(세부·담당·
        일정·상태)와 의존 엣지, 진척률(done/total)을 반환한다.
        """
        caller = await resolve_caller()
        if caller is None:
            return _NEED_AUTH
        room = storage.get_active_room(caller["id"])
        if room is None:
            return _NO_ROOM
        roadmap = storage.get_roadmap(room["id"])
        return {"ok": True, "room": room["name"], **_format(roadmap)}

    @mcp.tool(
        name="add_task",
        annotations={
            "title": "태스크 추가",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,  # 호출마다 새 태스크
            "openWorldHint": False,
        },
    )
    async def add_task(
        title: str,
        details: str | None = None,
        assignee: str | None = None,
        status: str = "todo",
        task_type: Literal["todo", "milestone"] = "todo",
        parent_task_id: int | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
        after_task_ids: list[int] | None = None,
        before_task_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Adds one task to the current room's roadmap in teamplay-talk(팀플톡), optionally linking it.

        팀플톡(teamplay-talk) 현재 작업 방의 로드맵에 태스크 1개를 추가한다.
        기본은 실행 todo(task_type='todo')다. 큰 로드맵 단계는 task_type='milestone'.
        여러 개인 todo 초안은 이 도구를 반복 호출하지 말고 decompose_roadmap을 사용한다.
        after_task_ids/before_task_ids 로 기존 태스크와 의존 엣지를 연결할 수 있다.

        Args:
            title: 태스크 제목
            details: 세부사항 (선택)
            assignee: 담당 (팀원 닉네임 또는 역할, 선택)
            status: 상태 "todo"|"doing"|"done" (기본 todo)
            task_type: todo=실행 할일, milestone=큰 로드맵 단계
            parent_task_id: todo가 속한 상위 milestone ID
            start_at: 시작 시각 UTC RFC3339 (선택)
            end_at: 종료 시각 UTC RFC3339 (선택)
            after_task_ids: 이 태스크의 **선행** 태스크 ID들(그것들 → 이 태스크, 선택)
            before_task_ids: 이 태스크의 **후행** 태스크 ID들(이 태스크 → 그것들, 선택)
        """
        caller = await resolve_caller()
        if caller is None:
            return _NEED_AUTH
        room = storage.get_active_room(caller["id"])
        if room is None:
            return _NO_ROOM
        task = storage.add_task(
            room["id"], title=title, details=details, assignee=assignee,
            status=status, task_type=task_type, parent_task_id=parent_task_id,
            start_at=start_at, end_at=end_at,
            after_ids=after_task_ids, before_ids=before_task_ids,
        )
        return {"ok": True, "task_id": task["id"], "title": task["title"], **_format(storage.get_roadmap(room["id"]))}

    @mcp.tool(
        name="delete_task",
        annotations={
            "title": "태스크 삭제",
            "readOnlyHint": False,
            "destructiveHint": True,  # 태스크와 연결 엣지를 삭제
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def delete_task(task_id: int) -> dict[str, Any]:
        """Deletes one task (and its edges) from the current room's roadmap in teamplay-talk(팀플톡).

        팀플톡(teamplay-talk) 현재 작업 방의 로드맵에서 태스크 1개를 삭제한다.
        연결된 의존 엣지도 함께 사라진다.

        Args:
            task_id: 삭제할 태스크 ID (view_roadmap에서 확인)
        """
        caller = await resolve_caller()
        if caller is None:
            return _NEED_AUTH
        room = storage.get_active_room(caller["id"])
        if room is None:
            return _NO_ROOM
        deleted = storage.delete_task(task_id, room["id"])
        if deleted is None:
            return {"ok": False, "error": "해당 태스크를 찾을 수 없습니다(이 방의 태스크가 아닐 수 있음)."}
        return {"ok": True, "deleted_task_id": deleted, **_format(storage.get_roadmap(room["id"]))}

    @mcp.tool(
        name="update_task",
        annotations={
            "title": "태스크 수정",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def update_task(
        task_id: int,
        title: str | None = None,
        details: str | None = None,
        assignee: str | None = None,
        status: str | None = None,
        task_type: Literal["todo", "milestone"] | None = None,
        parent_task_id: int | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
    ) -> dict[str, Any]:
        """Updates one roadmap task in teamplay-talk(팀플톡) (only given fields change).

        팀플톡(teamplay-talk) 로드맵의 태스크 하나를 수정한다. 상태 변경(진행/완료),
        담당 재지정, 일정 변경 등에 쓴다. 지정한 필드만 바뀐다.

        Args:
            task_id: 수정할 태스크 ID (view_roadmap에서 확인)
            title: 새 제목 (선택)
            details: 새 세부사항 (선택)
            assignee: 새 담당 (팀원 닉네임 또는 역할, 선택)
            status: 새 상태 "todo"|"doing"|"done" (선택)
            task_type: 새 타입 "todo"|"milestone" (선택)
            parent_task_id: 새 상위 milestone ID (선택)
            start_at: 새 시작 시각 UTC RFC3339 (선택)
            end_at: 새 종료 시각 UTC RFC3339 (선택)
        """
        caller = await resolve_caller()
        if caller is None:
            return _NEED_AUTH
        room = storage.get_active_room(caller["id"])
        if room is None:
            return _NO_ROOM
        updated = storage.update_task(
            task_id, room["id"], title=title, details=details, assignee=assignee,
            status=status, task_type=task_type, parent_task_id=parent_task_id,
            start_at=start_at, end_at=end_at,
        )
        if updated is None:
            return {"ok": False, "error": "해당 태스크를 찾을 수 없습니다."}
        return {
            "ok": True,
            "task_id": updated["id"],
            "title": updated["title"],
            "status": updated["status"],
            **_format(storage.get_roadmap(room["id"])),
        }

    @mcp.tool(
        name="decompose_roadmap",
        annotations={
            "title": "로드맵을 개인별 todo로 분해",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def decompose_roadmap(
        todos: list[TodoDraft],
        room_id: int | None = None,
    ) -> dict[str, Any]:
        """Adds executable todo items under roadmap milestones in teamplay-talk(팀플톡).

        로드맵의 큰 단계(milestone)를 멤버별 실행 todo로 분해해 저장한다.
        사용자가 "각자 할일 초안 만들어줘", "todo 리스트 짜줘"라고 하면 add_task를
        한 번만 쓰지 말고 이 도구로 여러 개를 한 번에 넣어라.

        AI 분해 규칙:
        - milestone 하나당 보통 2~5개 todo
        - todo는 1~2일 안에 끝낼 수 있는 산출물 단위
        - title은 동사형 실행 항목, details에는 완료 기준
        - assignee는 확정된 역할명 또는 멤버 닉네임
        - 팀원 의견 원문 1개를 그대로 한 줄 태스크로 저장하지 말고, 필요한 하위 작업으로 쪼갠다.

        Args:
            todos: 생성할 실행 todo 목록
            room_id: 대상 방 (생략 시 현재 작업 방)
        """
        _caller, room, error = await require_room(room_id)
        if error:
            return error
        room_id = room["id"]
        if not todos:
            return {"ok": False, "error": "todos가 비어 있습니다. 최소 1개 이상의 실행 todo를 넘겨주세요."}

        roadmap = storage.get_roadmap(room_id)
        if not roadmap["tasks"]:
            return {
                "ok": False,
                "error": "먼저 build_roadmap으로 큰 로드맵 milestone을 만들어야 합니다.",
            }

        created: list[dict[str, Any]] = []
        unresolved_parent: list[dict[str, Any]] = []
        for todo in todos:
            parent_id = _resolve_parent_task_id(
                roadmap,
                parent_task_id=todo.parent_task_id,
                parent_title=todo.parent_title,
            )
            if parent_id is None and (todo.parent_task_id or todo.parent_title):
                unresolved_parent.append({
                    "title": todo.title,
                    "parent_task_id": todo.parent_task_id,
                    "parent_title": todo.parent_title,
                })
            task = storage.add_task(
                room_id,
                title=todo.title,
                details=todo.details,
                assignee=todo.assignee,
                status=todo.status,
                task_type="todo",
                parent_task_id=parent_id,
                start_at=todo.start_at,
                end_at=todo.end_at,
            )
            created.append(_task_payload(task))

        synced = storage.sync_task_assignees_by_roles(room_id)
        formatted = _format(storage.get_roadmap(room_id))
        needs_role_assignment = bool(formatted["task_layer_summary"].get("needs_role_assignment"))
        return {
            "ok": True,
            "room_id": room_id,
            "room": room["name"],
            "created_todos": created,
            "created_count": len(created),
            "synced_todos": synced,
            "unresolved_parent": unresolved_parent,
            "needs_role_assignment": needs_role_assignment,
            "required_next_tool": "set_roles" if needs_role_assignment else "member_tasks",
            "next": (
                "todo 분해가 저장됐습니다. "
                + (
                    "다만 일부 todo가 역할명에만 묶여 있어 실제 팀원에게 아직 배정되지 않았습니다. set_roles로 역할을 확정한 뒤 member_tasks를 확인하세요."
                    if needs_role_assignment else
                    "member_tasks(member='all', window='week')로 조원별 실행 목록을 확인하고, 필요하면 daily_task_digest로 개인별 공지하세요."
                )
            ),
            "suggested_next_actions": [
                "role_only_todos가 있으면 set_roles로 역할 확정 또는 역할명 보정",
                "member_tasks(member='all', window='week')로 조원별 todo 확인",
                "누락/중복이 보이면 update_task/delete_task로 조정",
                "팀원 의견이 더 필요하면 gather_task_opinions(scope='todo')",
                "확정되면 daily_task_digest 또는 notify_room으로 공지",
            ],
            **formatted,
        }

    @mcp.tool(
        name="member_tasks",
        annotations={
            "title": "멤버별 할일 조회",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def member_tasks(
        member: str | None = None,
        window: Literal["all", "today", "week", "overdue", "upcoming", "no_date"] = "week",
        include_done: bool = False,
        room_id: int | None = None,
    ) -> dict[str, Any]:
        """Shows personal/team tasks from the current room roadmap in teamplay-talk(팀플톡).

        로드맵을 기준으로 멤버별 할일을 조회한다. 역할분배와 로드맵이 연결된 뒤
        "내 이번 주 할일", "전체 overdue", "세원 할일"처럼 확인하는 도구다.

        Args:
            member: 닉네임. 생략하면 호출자 본인, "all"/"전체"면 팀 전체.
            window: all/today/week/overdue/upcoming/no_date
            include_done: 완료 태스크 포함 여부
            room_id: 대상 방 (생략 시 현재 작업 방)
        """
        caller, room, error = await require_room(room_id)
        if error:
            return error
        room_id = room["id"]
        roadmap = storage.get_roadmap(room_id)
        all_members, unassigned = _member_task_buckets(roadmap)
        today = datetime.now(_KST).date()

        selector = (member or "").strip()
        show_all = selector.lower() in {"all", "team"} or selector in {"전체", "팀", "모두"}
        if not selector:
            selector = str(caller.get("nickname") or "")
        if selector in {"나", "내", "me", "my"}:
            selector = str(caller.get("nickname") or "")

        selected: list[dict[str, Any]]
        if show_all:
            selected = all_members
        else:
            needle = selector.lower()
            selected = [
                m for m in all_members
                if m["nickname"].lower() == needle or needle in m["nickname"].lower()
            ]
            if not selected:
                return {
                    "ok": False,
                    "error": f"'{selector}' 멤버를 찾을 수 없습니다. member='all'로 전체를 볼 수 있습니다.",
                    "members": [m["nickname"] for m in all_members],
                }

        filtered_members: list[dict[str, Any]] = []
        for bucket in selected:
            tasks = [
                task for task in bucket["tasks"]
                if _task_matches_window(task, window, today, include_done=include_done)
            ]
            done = sum(1 for task in tasks if task.get("status") == "done")
            filtered_members.append({
                **bucket,
                "tasks": tasks,
                "filtered_progress": {"done": done, "total": len(tasks)},
            })

        filtered_unassigned = [
            task for task in unassigned
            if _task_matches_window(task, window, today, include_done=include_done)
        ] if show_all else []
        total = sum(len(m["tasks"]) for m in filtered_members) + len(filtered_unassigned)
        layer = _format(roadmap)["task_layer_summary"]
        return {
            "ok": True,
            "room_id": room_id,
            "room": room["name"],
            "window": window,
            "today_kst": today.isoformat(),
            "include_done": include_done,
            "member_selector": "all" if show_all else selector,
            "total_tasks": total,
            "task_layer_summary": layer,
            "members": filtered_members,
            "unassigned_tasks": filtered_unassigned,
            "next": (
                "할일을 확인했습니다. 실행 todo가 비어 있으면 decompose_roadmap으로 "
                "로드맵 milestone을 개인별 todo로 먼저 분해하세요."
            ),
            "suggested_next_actions": [
                "todo가 없으면 decompose_roadmap으로 milestone 아래 실행 todo 2~5개씩 생성",
                "role_only_todos가 있으면 set_roles로 역할 확정 또는 역할명 보정",
                "비어 있는 담당/마감은 update_task로 보정",
                "할일 후보가 애매하면 gather_task_opinions(scope='todo')로 팀 의견수렴",
                "갈리는 항목은 create_poll로 우선순위/채택 여부 결정",
                "담당자에게 daily_task_digest로 개인별 할일 공지",
                "날짜 있는 태스크는 calendar_create_task_events로 개인 캘린더 등록",
            ],
        }

    @mcp.tool(
        name="daily_task_digest",
        annotations={
            "title": "개인별 할일 공지",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def daily_task_digest(
        room_id: int | None = None,
        include_done: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Sends each roadmap owner a personalized task digest via KakaoTalk.

        팀플톡(teamplay-talk) 로드맵을 사람별로 나누어 각 담당자에게 자기 할일만
        카카오톡으로 보낸다. 역할분배 → 로드맵 생성 뒤 매일/회의 전 확인용으로 쓴다.

        Args:
            room_id: 대상 방 ID (생략 시 현재 작업 방)
            include_done: 완료 태스크도 포함할지 여부
            dry_run: 실제 발송 없이 미리보기만 반환
        """
        caller = await resolve_caller()
        if caller is None:
            return _NEED_AUTH
        if room_id is None:
            room = storage.get_active_room(caller["id"])
            if room is None:
                return _NO_ROOM
            room_id = room["id"]
        elif not storage.is_room_member(room_id, caller["id"]):
            return {"ok": False, "error": "이 방의 멤버만 할일 공지를 보낼 수 있습니다."}
        else:
            room = storage.get_room(room_id)
            if room is None:
                return {"ok": False, "error": f"방 {room_id}를 찾을 수 없습니다."}

        roadmap = _format(storage.get_roadmap(room_id))
        layer = roadmap.get("task_layer_summary") or {}
        members_by_token = {m["id"]: m for m in kakao_store.list_members_with_tokens(room_id)}
        previews: list[dict[str, Any]] = []
        sent: list[str] = []
        failed: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for member in roadmap["by_member"]:
            message = _member_digest_message(room["name"], member, include_done=include_done)
            if message is None:
                skipped.append({"nickname": member["nickname"], "reason": "보낼 미완료 태스크가 없습니다."})
                continue
            previews.append({"nickname": member["nickname"], "message": message})
            token_member = members_by_token.get(member["member_id"])
            if token_member is None:
                failed.append({"nickname": member["nickname"], "error": "카카오 인증 토큰이 없습니다."})
                continue
            if dry_run:
                continue
            status = await kakao_store.send_with_refresh(token_member, message)
            if status == 200:
                sent.append(member["nickname"])
            else:
                failed.append({"nickname": member["nickname"], "error": f"카카오 발송 실패 HTTP {status}"})

        if not sent and not dry_run:
            reason = (
                "역할명으로만 묶인 todo가 있어 실제 팀원에게 아직 배정되지 않았습니다."
                if layer.get("role_only_todos") else
                "보낼 개인별 미완료 todo가 없거나, 담당자의 카카오 인증 토큰이 없습니다."
            )
            return {
                "ok": False,
                "room_id": room_id,
                "room": room["name"],
                "dry_run": dry_run,
                "sent_to": sent,
                "failed": failed,
                "skipped": skipped,
                "previews": previews,
                "task_layer_summary": layer,
                "error": reason,
                "next": (
                    "daily_task_digest는 분배 도구가 아니라 이미 배정된 개인 todo를 공지하는 도구입니다. "
                    "먼저 member_tasks(member='all')로 실제 배정 상태를 확인하세요."
                ),
                "suggested_next_actions": [
                    "role_only_todos가 있으면 set_roles로 역할 확정 또는 역할명 보정",
                    "todo가 없으면 decompose_roadmap으로 실행 todo 생성",
                    "담당자 토큰이 없으면 해당 팀원이 카카오 인증을 다시 진행",
                    "배정 상태 확인 후 daily_task_digest 재시도",
                ],
            }

        return {
            "ok": dry_run or bool(sent),
            "room_id": room_id,
            "room": room["name"],
            "dry_run": dry_run,
            "sent_to": sent,
            "failed": failed,
            "skipped": skipped,
            "previews": previews,
            "task_layer_summary": layer,
            "next": (
                "할일 공지를 보냈습니다. 날짜가 있는 태스크는 calendar_create_task_events로 "
                "담당자 개인 캘린더에도 등록할 수 있습니다."
            ),
            "suggested_next_actions": [
                "calendar_create_task_events로 날짜 있는 태스크 캘린더 등록",
                "room_dashboard로 개인별 진척 확인",
                "완료 보고가 들어오면 update_task(status='done')로 갱신",
            ],
        }
