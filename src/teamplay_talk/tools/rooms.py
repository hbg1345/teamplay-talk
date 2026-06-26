"""방(워크스페이스) 도메인 도구 — 카카오 신원 + 현재 작업 방(active room).

호출자 신원은 ``identity.resolve_caller()`` 로 해석한다:
- 헤더에 카카오 토큰이 있으면(PlayMCP가 카카오 OAuth 대행) → **로그인 없이** 바로 동작
- 없으면 → 로그인 링크를 반환(🅐 fallback), 실제 액션은 ``/auth/kakao/callback`` 에서 수행

방은 다대다(한 사람이 여러 방). 그중 '현재 작업 방'(``active_room_id``) 하나를
가리키고, 방을 지정하지 않은 도구는 그 방에 작동한다.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .. import storage
from ..identity import resolve_caller


def _need_login(message: str) -> dict[str, Any]:
    """OAuth 신원이 없을 때 — PlayMCP에서 인증(카카오·구글 OAuth)을 먼저 하라고 안내."""
    return {
        "need_login": True,
        "message": f"{message} 먼저 PlayMCP에서 이 MCP의 인증(카카오·구글 OAuth)을 완료해 주세요.",
    }


def _match_rooms(rooms: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """사용자의 방 목록에서 query(초대코드/이름)에 맞는 방을 찾는다."""
    q = query.strip().lower()
    by_code = [r for r in rooms if r["invite_code"].lower() == q]
    if by_code:
        return by_code
    exact = [r for r in rooms if r["name"].lower() == q]
    if exact:
        return exact
    return [r for r in rooms if q in r["name"].lower()]


async def _resolve_room(invite_code: str | None) -> dict[str, Any] | None:
    """초대 코드가 있으면 그 방, 없으면 호출자의 현재 작업 방을 반환한다."""
    if invite_code:
        return storage.get_room_by_invite_code(invite_code)
    caller = await resolve_caller()
    if caller is None:
        return None
    return storage.get_active_room(caller["id"])


def register(mcp: FastMCP) -> None:
    """방 도메인 도구를 등록한다."""

    @mcp.tool(
        name="create_room",
        annotations={
            "title": "팀플 방 생성",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def create_room(name: str, description: str | None = None) -> dict[str, Any]:
        """Creates a team-project room in teamplay-talk(팀플톡) and makes it your current room.

        팀플톡(teamplay-talk)에서 팀 프로젝트용 방을 만든다. 인증돼 있으면 바로
        생성되고 **현재 작업 방**으로 설정되며 초대 코드가 나온다. 팀원은 우리 MCP를
        인증한 뒤 join_room에 그 코드를 넣어 참여한다.

        Args:
            name: 방 이름 (예: "캡스톤 3조")
            description: 방 설명 (선택)
        """
        caller = await resolve_caller()
        if caller is None:
            return _need_login(f"'{name}' 방을 만들려면")
        result = storage.create_room(
            name=name,
            owner_nickname=caller["nickname"],
            description=description,
            owner_kakao_id=caller["kakao_id"],
        )
        room = result["room"]
        storage.set_active_room(caller["id"], room["id"])
        return {
            "ok": True,
            "room_id": room["id"],
            "name": room["name"],
            "invite_code": room["invite_code"],
            "active": True,
            "message": (
                f"'{room['name']}' 방 생성 완료 — 현재 작업 방으로 설정됨. "
                f"초대 코드: {room['invite_code']} "
                f"(팀원이 우리 MCP 인증 후 join_room에 이 코드를 넣으면 참여됩니다)"
            ),
        }

    @mcp.tool(
        name="join_room",
        annotations={
            "title": "팀플 방 참여",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def join_room(invite_code: str) -> dict[str, Any]:
        """Joins a teamplay-talk(팀플톡) room by invite code and makes it your current room.

        팀플톡(teamplay-talk)에서 초대 코드로 방에 참여하고 **현재 작업 방**으로
        설정한다.

        Args:
            invite_code: 방 생성 시 발급된 초대 코드
        """
        caller = await resolve_caller()
        if caller is None:
            return _need_login("방에 참여하려면")
        result = storage.join_room(
            invite_code=invite_code,
            nickname=caller["nickname"],
            kakao_id=caller["kakao_id"],
        )
        if result is None:
            return {"ok": False, "error": "유효하지 않은 초대 코드입니다."}
        room = result["room"]
        storage.set_active_room(caller["id"], room["id"])
        return {
            "ok": True,
            "room_id": room["id"],
            "name": room["name"],
            "active": True,
            "message": f"'{room['name']}' 참여 완료 — 현재 작업 방으로 설정됨.",
        }

    @mcp.tool(
        name="switch_room",
        annotations={
            "title": "작업 방 전환",
            "readOnlyHint": False,
            "destructiveHint": False,  # 멤버십은 그대로, 포인터만 이동
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def switch_room(name: str) -> dict[str, Any]:
        """Switches your current working room in teamplay-talk(팀플톡). Membership stays.

        팀플톡(teamplay-talk)에서 **현재 작업 방**을 다른 방으로 옮긴다. 방에서
        나가는 게 아니라(멤버십 유지) '지금 작업하는 방' 포인터만 이동한다.
        이름이나 초대 코드로 지정한다.

        Args:
            name: 옮겨갈 방의 이름(또는 초대 코드)
        """
        caller = await resolve_caller()
        if caller is None:
            return _need_login("작업 방을 옮기려면")
        rooms = storage.list_user_rooms(caller["id"])
        matches = _match_rooms(rooms, name)
        if not matches:
            return {
                "ok": False,
                "error": f"'{name}'에 해당하는 방이 없습니다.",
                "your_rooms": [r["name"] for r in rooms],
            }
        if len(matches) > 1:
            return {
                "ok": False,
                "error": "여러 방이 일치합니다. 더 정확히 지정하세요.",
                "candidates": [r["name"] for r in matches],
            }
        target = matches[0]
        storage.set_active_room(caller["id"], target["id"])
        return {
            "ok": True,
            "active_room": target["name"],
            "message": f"현재 작업 방을 '{target['name']}'(으)로 옮겼습니다.",
        }

    @mcp.tool(
        name="my_rooms",
        annotations={
            "title": "내 방 목록",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def my_rooms() -> dict[str, Any]:
        """Lists the teamplay-talk(팀플톡) rooms you belong to, marking the current one.

        팀플톡(teamplay-talk)에서 내가 속한 방 목록(이름·역할·초대코드)과 현재
        작업 방을 보여준다.
        """
        caller = await resolve_caller()
        if caller is None:
            return _need_login("내 방 목록을 보려면")
        rooms = storage.list_user_rooms(caller["id"])
        return {
            "ok": True,
            "count": len(rooms),
            "active_room": next((r["name"] for r in rooms if r["is_active"]), None),
            "rooms": [
                {
                    "name": r["name"],
                    "role": r["role"],
                    "invite_code": r["invite_code"],
                    "active": r["is_active"],
                }
                for r in rooms
            ],
        }

    @mcp.tool(
        name="leave_room",
        annotations={
            "title": "팀플 방 나가기",
            "readOnlyHint": False,
            "destructiveHint": True,  # 멤버십을 제거한다
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def leave_room(invite_code: str | None = None) -> dict[str, Any]:
        """Leaves a teamplay-talk(팀플톡) room, removing your membership.

        팀플톡(teamplay-talk) 방에서 나간다(멤버십 삭제). 코드를 안 주면 **현재
        작업 방**에서 나간다.

        Args:
            invite_code: 나갈 방의 초대 코드 (생략 시 현재 작업 방)
        """
        caller = await resolve_caller()
        if caller is None:
            return _need_login("방에서 나가려면")
        code = invite_code
        if not code:
            active = storage.get_active_room(caller["id"])
            if active is None:
                return {
                    "ok": False,
                    "error": "현재 작업 중인 방이 없습니다. 나갈 방의 초대 코드를 지정하세요.",
                }
            code = active["invite_code"]
        result = storage.leave_room(code, caller["kakao_id"])
        if result is None:
            return {"ok": False, "error": "유효하지 않은 초대 코드입니다."}
        if not result["left"]:
            return {"ok": False, "error": "이미 이 방의 멤버가 아닙니다."}
        return {
            "ok": True,
            "name": result["room"]["name"],
            "message": f"'{result['room']['name']}' 나가기 완료.",
        }

    @mcp.tool(
        name="room_info",
        annotations={
            "title": "방 정보·멤버 조회",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def room_info(invite_code: str | None = None) -> dict[str, Any]:
        """Reads a teamplay-talk(팀플톡) room's name and member list.

        팀플톡(teamplay-talk) 방의 이름과 멤버 목록(닉네임·역할)을 조회한다.
        초대 코드를 주면 그 방을, 안 주면 **현재 작업 방**을 본다.

        Args:
            invite_code: 조회할 방의 초대 코드 (생략 시 현재 작업 방)
        """
        room = await _resolve_room(invite_code)
        if room is None:
            return {
                "ok": False,
                "error": "방을 찾을 수 없습니다. (초대 코드를 지정하거나 작업 방을 먼저 정하세요)",
            }
        members = storage.list_members(room["id"])
        return {
            "ok": True,
            "room_id": room["id"],
            "name": room["name"],
            "member_count": len(members),
            "members": [
                {"nickname": m["nickname"], "role": m["role"]} for m in members
            ],
        }

    @mcp.tool(
        name="get_invite_code",
        annotations={
            "title": "초대 코드 받기",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def get_invite_code(invite_code: str | None = None) -> dict[str, Any]:
        """Returns the invite code and how to join a teamplay-talk(팀플톡) room.

        팀플톡(teamplay-talk) 방의 **초대 코드**와 참여 방법을 반환한다. 팀원이
        우리 MCP를 연결·인증한 뒤 join_room에 이 코드를 넣으면 참여된다. 초대
        코드를 주면 그 방을, 안 주면 **현재 작업 방**의 코드를 준다.

        Args:
            invite_code: 방 초대 코드 (생략 시 현재 작업 방)
        """
        room = await _resolve_room(invite_code)
        if room is None:
            return {
                "ok": False,
                "error": "방을 찾을 수 없습니다. (초대 코드를 지정하거나 작업 방을 먼저 정하세요)",
            }
        return {
            "ok": True,
            "name": room["name"],
            "invite_code": room["invite_code"],
            "how_to_join": (
                f"팀원이 우리 MCP를 인증한 뒤 join_room('{room['invite_code']}') 하면 "
                f"'{room['name']}' 방에 참여됩니다."
            ),
        }
