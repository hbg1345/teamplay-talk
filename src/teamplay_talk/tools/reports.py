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


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else None)


def _workflow_label(schema: dict[str, Any]) -> str:
    workflow = str(schema.get("_workflow_kind") or "")
    scope = str(schema.get("_workflow_scope") or "")
    if workflow == "roadmap_decision":
        return {
            "roadmap": "로드맵 의견",
            "todo": "todo 의견",
            "blockers": "병목 의견",
            "scope": "스코프 의견",
        }.get(scope, "로드맵/todo 의견")
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
    kind = _workflow_label(schema)
    responses = int(form.get("total_responses") or 0)
    label = f"폼 #{form['id']} · {kind} · {form['title']} · {responses}응답"
    return {
        "form_id": form["id"],
        "label": label,
        "title": form["title"],
        "status": "closed" if form.get("closed") else "active",
        "kind": kind,
        "responses": responses,
        "created_at": _iso(form.get("created_at")),
        "closes_at": _iso(form.get("closes_at")),
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
        active_forms = [_form_summary(form) for form in forms if not form.get("closed")]
        recent_forms = [_form_summary(form) for form in forms[:8]]
        active_forms_text = [
            f"- 폼 #{form['form_id']} · {form['kind']} · {form['title']} · {form['responses']}응답 · {form['status']}"
            for form in active_forms
        ]
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
            "active_forms": active_forms,
            "active_forms_text": active_forms_text,
            "recent_forms": recent_forms,
            "active_form_count": len(active_forms),
            "total_responses": sum(int(f.get("total_responses") or 0) for f in forms),
            "latest_decisions": latest_decisions,
            "expires_in_hours": 24,
            "next": "진행중 폼은 active_forms에서 바로 확인하고, 전체 타임라인은 대시보드 링크에서 볼 수 있습니다.",
            "suggested_next_actions": [
                "미완료 todo가 많으면 밀린 할일 확인하기",
                "오늘 상태가 필요하면 데일리 리포트 만들기",
                "아직 응답 중인 폼이 있으면 마감 후 결과 확인하기",
            ],
            "chat_response_hint": (
                "진행중 폼이 있으면 active_forms_text를 그대로 사용해 폼 #ID, 제목, 종류, 응답 수를 먼저 요약하세요. "
                "대시보드 링크는 전체 타임라인을 볼 보조 링크로 덧붙이세요."
            ),
        }
