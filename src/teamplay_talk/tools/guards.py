"""공통 도구 권한 가드."""

from __future__ import annotations

from typing import Any

from .. import storage
from ..identity import resolve_caller


_NEED_AUTH = {
    "ok": False,
    "error": "카카오 인증 정보가 없습니다. PlayMCP에서 카카오 계정 연결을 먼저 진행해 주세요.",
}


async def require_room(room_id: int | None = None) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    """호출자와 대상 active room을 반환한다. 실패 시 error dict를 반환한다."""
    caller = await resolve_caller()
    if caller is None:
        return None, None, _NEED_AUTH

    if room_id is None:
        room = storage.get_active_room(caller["id"])
        if room is None:
            return caller, None, {
                "ok": False,
                "error": "현재 작업 방이 없습니다. create_room 또는 switch_room 먼저.",
            }
        return caller, room, None

    room = storage.get_room(room_id)
    if room is None:
        return caller, None, {"ok": False, "error": f"방 {room_id}를 찾을 수 없습니다."}
    if not storage.is_room_member(room_id, caller["id"]):
        return caller, None, {"ok": False, "error": "이 방의 멤버만 이 작업을 할 수 있습니다."}
    return caller, room, None


async def require_form(form_id: int) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    """호출자와 대상 active form을 반환한다. 실패 시 error dict를 반환한다."""
    caller = await resolve_caller()
    if caller is None:
        return None, None, _NEED_AUTH

    form = storage.get_form(form_id)
    if form is None:
        return caller, None, {"ok": False, "error": "존재하지 않는 폼입니다."}
    if not storage.is_form_member(form_id, caller["id"]):
        return caller, None, {"ok": False, "error": "이 폼이 속한 방의 멤버만 접근할 수 있습니다."}
    return caller, form, None
