"""알림 도메인 도구 — 카카오 "나와의 채팅방" self-push.

방 멤버 각자의 카카오 토큰으로, 각자의 '나와의 채팅방'에 알림을 보낸다.
호출자 신원은 필요 없다(방 멤버 토큰만 있으면 됨) → 다른 사람·cron이
트리거해도 전원이 받는다.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .. import kakao, kakao_store, storage
from ..config import settings
from ..identity import resolve_caller


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
        """Sends a KakaoTalk notification to every member of a teamplay-talk(팀플톡) room.

        팀플톡(teamplay-talk) 방의 모든 멤버에게 카카오톡 '나와의 채팅방'으로
        알림을 보낸다. 카카오 로그인을 마친 멤버에게만 전달된다. room_id를 안
        주면 **현재 작업 방**으로 보낸다.

        Args:
            message: 보낼 메시지 내용
            room_id: 알림을 보낼 방 ID (생략 시 현재 작업 방)
        """
        if room_id is None:
            caller = await resolve_caller()
            if caller is None:
                return {
                    "ok": False,
                    "error": "방을 지정하거나 카카오 연결이 필요합니다.",
                }
            active = storage.get_active_room(caller["id"])
            if active is None:
                return {
                    "ok": False,
                    "error": "현재 작업 중인 방이 없습니다. switch_room으로 방을 정하거나 room_id를 지정하세요.",
                }
            room_id = active["id"]

        members = kakao_store.list_members_with_tokens(room_id)
        if not members:
            return {
                "ok": False,
                "error": "알림 받을 멤버가 없습니다. (멤버가 카카오 로그인을 마쳐야 함)",
            }

        sent: list[str] = []
        failed: list[str] = []
        for m in members:
            status, _ = await kakao.send_to_me(m["kakao_access_token"], message)

            # access token 만료(401) 시 refresh 후 1회 재시도
            if status == 401 and m.get("kakao_refresh_token"):
                refreshed = await kakao.refresh_access_token(
                    m["kakao_refresh_token"],
                    settings.kakao_rest_api_key,
                    settings.kakao_client_secret,
                )
                if "access_token" in refreshed:
                    kakao_store.set_kakao_token(
                        m["kakao_id"],
                        refreshed["access_token"],
                        refreshed.get("refresh_token") or m["kakao_refresh_token"],
                        refreshed.get("expires_in"),
                    )
                    status, _ = await kakao.send_to_me(refreshed["access_token"], message)

            (sent if status == 200 else failed).append(m["nickname"])

        return {"ok": True, "sent_to": sent, "failed": failed, "count": len(sent)}
