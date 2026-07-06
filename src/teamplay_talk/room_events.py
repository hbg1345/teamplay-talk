"""Room lifecycle side effects such as owner notifications."""

from __future__ import annotations

from typing import Any

from . import kakao_store, storage
from .config import settings
from .dashboard_web import create_dashboard_token


async def notify_owner_member_joined(
    room: dict[str, Any],
    user: dict[str, Any],
    *,
    joined: bool = True,
) -> dict[str, Any]:
    """Notify the room owner when a new member joins.

    Existing members re-running join should not notify the owner again.
    """
    if not joined:
        return {"sent": False, "reason": "already_member"}
    owner_id = room.get("owner_id")
    user_id = user.get("id")
    if owner_id is None or user_id == owner_id:
        return {"sent": False, "reason": "owner_or_missing_owner"}

    owner = storage.get_user(int(owner_id))
    if not owner or not owner.get("kakao_access_token"):
        return {"sent": False, "reason": "owner_has_no_kakao_token"}

    room_id = int(room["id"])
    token = create_dashboard_token(room_id, int(owner_id))
    link = f"{settings.public_base_url}/dashboard/rooms/{room_id}?token={token}"
    member_name = str(user.get("nickname") or "새 팀원")
    room_name = str(room.get("name") or "팀플톡 방")
    try:
        status = await kakao_store.send_feed_with_refresh(
            owner,
            title=f"{room_name} 새 팀원 참여",
            description=f"{member_name}님이 방에 참여했습니다.",
            link_url=link,
            button_title="방 보기",
            items=[("새 팀원", member_name), ("방", room_name)],
            fallback_text=f"[팀플톡] {room_name}\n{member_name}님이 방에 참여했습니다.\n{link}",
        )
    except Exception as exc:
        return {
            "sent": False,
            "reason": "send_failed",
            "error": type(exc).__name__,
            "owner": owner.get("nickname"),
        }
    return {
        "sent": status == 200,
        "status": status,
        "owner": owner.get("nickname"),
    }
