"""로드맵 도메인 도구 — 프로젝트 타임라인(태스크 그래프).

로드맵은 **방(현재 작업 방)의 태스크 그래프**다. 태스크(노드)들이 의존 엣지
(선행→후행)로 연결돼 프로젝트 전체 타임라인을 이룬다. 각 태스크엔 세부사항,
담당(팀원 또는 역할), 일정(start/end), 상태가 들어간다.

주제 분석은 호출 측 AI가 수행한다: AI가 주제를 보고 태스크/엣지를 생성해
``build_roadmap`` 으로 넘기면 서버는 저장한다(서버엔 LLM 없음).
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .. import storage
from ..identity import resolve_caller

_NEED_AUTH = {
    "ok": False,
    "error": "카카오 인증 정보가 없습니다. PlayMCP에서 카카오 계정 연결을 먼저 진행해 주세요.",
}
_NO_ROOM = {
    "ok": False,
    "error": "현재 작업 중인 방이 없습니다. 방을 만들거나 참여(switch_room)한 뒤 다시 시도하세요.",
}


def _iso(dt: Any) -> str | None:
    return dt.isoformat() if dt is not None and hasattr(dt, "isoformat") else dt


def _format(roadmap: dict[str, Any]) -> dict[str, Any]:
    """저장 계층 결과를 출력용으로 정리(담당자·일정 직렬화 + 진척률)."""
    tasks = roadmap["tasks"]
    done = sum(1 for t in tasks if t["status"] == "done")
    return {
        "tasks": [
            {
                "id": t["id"],
                "title": t["title"],
                "details": t.get("details"),
                "assignee": t.get("assignee_nickname") or t.get("assignee_role"),
                "status": t["status"],
                "start_at": _iso(t.get("start_at")),
                "end_at": _iso(t.get("end_at")),
            }
            for t in tasks
        ],
        "edges": [
            {"from": e["from_task_id"], "to": e["to_task_id"]} for e in roadmap["edges"]
        ],
        "progress": {"done": done, "total": len(tasks)},
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
    ) -> dict[str, Any]:
        """Builds (replaces) the current room's project roadmap as a task graph in teamplay-talk(팀플톡).

        팀플톡(teamplay-talk) 현재 작업 방의 로드맵(프로젝트 타임라인)을 태스크
        그래프로 생성/교체한다. 호출 측 AI가 주제를 분석해 태스크와 의존 엣지를
        만들어 넘긴다. 시간은 UTC RFC3339(예: 2026-07-01T00:00:00Z).

        Args:
            tasks: 태스크 목록. 각 항목은
                {"key": 임시ID, "title": 제목, "details": 세부(선택),
                 "assignee": 담당 팀원 닉네임 또는 역할(선택),
                 "start_at": 시작(선택), "end_at": 종료(선택),
                 "status": "todo"|"doing"|"done"(선택, 기본 todo)}.
                key는 edges에서 태스크를 가리키는 데 쓰는 임시 식별자.
            edges: 의존 엣지 목록 [{"from": key, "to": key}] (선행→후행, 선택)
            topic: 로드맵 주제 메모 (선택)
        """
        caller = await resolve_caller()
        if caller is None:
            return _NEED_AUTH
        room = storage.get_active_room(caller["id"])
        if room is None:
            return _NO_ROOM
        if not tasks:
            return {"ok": False, "error": "tasks가 비어 있습니다."}
        roadmap = storage.set_roadmap(room["id"], tasks, edges or [])
        return {"ok": True, "room": room["name"], "topic": topic, **_format(roadmap)}

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
            start_at: 새 시작 시각 UTC RFC3339 (선택)
            end_at: 새 종료 시각 UTC RFC3339 (선택)
        """
        caller = await resolve_caller()
        if caller is None:
            return _NEED_AUTH
        updated = storage.update_task(
            task_id, title=title, details=details, assignee=assignee,
            status=status, start_at=start_at, end_at=end_at,
        )
        if updated is None:
            return {"ok": False, "error": "해당 태스크를 찾을 수 없습니다."}
        return {
            "ok": True,
            "task_id": updated["id"],
            "title": updated["title"],
            "status": updated["status"],
        }
