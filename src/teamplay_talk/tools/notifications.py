"""알림 도메인 도구 — 카카오 "나와의 채팅방" self-push.

방 멤버 각자의 카카오 토큰으로, 각자의 '나와의 채팅방'에 알림을 보낸다.
호출자 신원은 필요 없다(방 멤버 토큰만 있으면 됨) → 다른 사람·cron이
트리거해도 전원이 받는다.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .. import kakao_store, storage, task_sync
from ..config import settings
from ..dashboard_web import create_dashboard_token
from .guards import require_room


def _decision_kind_from_message(message: str) -> str | None:
    if any(token in message for token in ["회의 장소", "장소는", "장소가"]):
        return "meeting_location"
    if any(token in message for token in ["회의 일정", "회의 시간", "시간이", "시간은"]):
        return "meeting_time"
    if "확정" in message and any(token in message for token in ["투표", "결정", "선택"]):
        return "decision"
    return None


def register(mcp: FastMCP) -> None:
    """알림 도메인 도구를 등록한다."""

    @mcp.tool(
        name="notify_room",
        annotations={
            "title": "방 전체 카카오 알림",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,  # 외부(카카오)로 메시지 발송
        },
    )
    async def notify_room(message: str, room_id: int | None = None) -> dict[str, Any]:
        """팀플톡 방 멤버 전원에게 카카오톡 알림을 보냅니다.

        카카오 로그인을 마친 멤버의 '나와의 채팅방'으로 메시지를 발송한다.
        room_id를 생략하면 현재 작업 방을 대상으로 한다. 폼 링크 배포에는 이
        도구가 아니라 form_manage(action='send')를 사용한다.

        Args:
            message: 보낼 메시지 내용
            room_id: 알림을 보낼 방 ID (생략 시 현재 작업 방)
        """
        _caller, room, error = await require_room(room_id)
        if error:
            return error
        room_id = room["id"]

        members = kakao_store.list_members_with_tokens(room_id)
        if not members:
            return {
                "ok": False,
                "error": "알림 받을 멤버가 없습니다. (멤버가 카카오 로그인을 마쳐야 함)",
            }

        sent: list[str] = []
        failed: list[str] = []
        first_line = next((line.strip() for line in message.splitlines() if line.strip()), "팀 공지가 도착했습니다.")
        for m in members:
            token = create_dashboard_token(room_id, m["id"])
            link = f"{settings.public_base_url}/dashboard/rooms/{room_id}?token={token}"
            status = await kakao_store.send_feed_with_refresh(
                m,
                title=f"{room['name']} 공지",
                description=first_line,
                link_url=link,
                button_title="방 보기",
                items=[("방", room["name"])],
                fallback_text=f"{message}\n{link}",
            )

            (sent if status == 200 else failed).append(m["nickname"])

        if not sent:
            return {
                "ok": False,
                "sent_to": sent,
                "failed": failed,
                "count": 0,
                "error": "모든 공지 발송이 실패했습니다. 카카오 인증/토큰 상태를 확인해야 합니다.",
            }

        decision_kind = _decision_kind_from_message(message)
        decision = None
        if decision_kind:
            row = storage.record_room_decision(
                room_id,
                kind=decision_kind,
                title="방 공지 기반 결정",
                summary=message,
                payload={"message": message, "sent_to": sent, "failed": failed},
                source="notify_room",
            )
            decision = {
                "id": row["id"],
                "kind": row["kind"],
                "title": row["title"],
                "summary": row["summary"],
            }

        return {
            "ok": True,
            "sent_to": sent,
            "failed": failed,
            "count": len(sent),
            "status": "partial" if failed else "sent",
            "recorded_decision": decision,
            "next": (
                "공지 발송이 끝났습니다. 확정 결정이면 대시보드 타임라인에 기록됐는지 확인하고, "
                "후속 작업이 있으면 로드맵·todo나 캘린더에 반영하세요."
            ),
            "suggested_next_actions": [
                "공지·결정 기록을 대시보드에서 확인하기",
                "결정된 일이 작업이면 로드맵에 반영하기",
                "회의·마감 일정이면 전원 카카오 캘린더에 등록하기",
                "팀원별 실행 항목을 개인 공지하기",
            ],
            "chat_response_hint": "실제 발송 결과(sent_to·count)를 기준으로 공지 성공 여부를 말하고, 다음 행동은 대시보드 확인·로드맵 반영·캘린더 등록 중 필요한 것만 짧게 안내하세요.",
        }
