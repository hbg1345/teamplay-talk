"""리포트·대시보드 도메인 도구."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .. import storage
from ..config import settings
from ..dashboard_web import create_dashboard_token
from ..identity import resolve_caller


def _decision_payload(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": decision["id"],
        "kind": decision["kind"],
        "title": decision["title"],
        "summary": decision["summary"],
        "payload": decision.get("payload") or {},
        "source": decision.get("source"),
        "created_at": decision["created_at"].isoformat()
        if hasattr(decision.get("created_at"), "isoformat")
        else decision.get("created_at"),
    }


def register(mcp: FastMCP) -> None:
    """리포트·대시보드 도메인 도구를 등록한다."""

    @mcp.tool(
        name="room_dashboard",
        annotations={
            "title": "방별 결과 대시보드",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def room_dashboard(room_id: int | None = None) -> dict[str, Any]:
        """Returns a signed result timeline URL for a teamplay-talk(팀플톡) room.

        방에서 지금까지 만든 SurveyJS 폼/투표/일정조율 결과를 한 화면에서 보는
        타임라인 링크를 반환한다. 각 결과는 생성된 순서대로 요약되며,
        회의 일정은 teamplay-talk의 best_slots를 함께 보여준다.

        Args:
            room_id: 대상 방 ID. 생략하면 현재 작업 방을 사용한다.
        """
        caller = await resolve_caller()
        if caller is None:
            return {"ok": False, "error": "인증이 필요합니다 — PlayMCP에서 이 MCP 인증을 먼저 해주세요."}
        if room_id is None:
            active = storage.get_active_room(caller["id"])
            if active is None:
                return {"ok": False, "error": "현재 작업 방이 없습니다. create_room 또는 switch_room 먼저."}
            room_id = active["id"]
        room = storage.get_room(room_id)
        if room is None:
            return {"ok": False, "error": f"방 {room_id}를 찾을 수 없습니다."}
        if not storage.is_room_member(room_id, caller["id"]):
            return {"ok": False, "error": "이 방의 멤버만 대시보드를 볼 수 있습니다."}

        token = create_dashboard_token(room_id, caller["id"])
        forms = storage.list_room_forms(room_id)
        latest_decisions = {
            kind: _decision_payload(decision)
            for kind, decision in storage.latest_room_decisions(room_id).items()
        }
        url = f"{settings.public_base_url}/dashboard/rooms/{room_id}?token={token}"
        return {
            "ok": True,
            "room_id": room_id,
            "room_name": room["name"],
            "dashboard_url": url,
            "form_count": len(forms),
            "total_responses": sum(int(f.get("total_responses") or 0) for f in forms),
            "latest_decisions": latest_decisions,
            "expires_in_hours": 24,
        }
