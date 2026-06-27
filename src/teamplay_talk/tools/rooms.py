"""방(워크스페이스) 도메인 도구 — 카카오 신원 + 현재 작업 방(active room).

호출자 신원은 ``identity.resolve_caller()`` 로 해석한다. PlayMCP가 카카오 OAuth를
broker 하면 매 호출 ``Authorization: Bearer`` 헤더에 카카오 토큰이 실려오고,
그걸로 **로그인 없이** 바로 신원이 잡힌다(구글 Drive 때와 동일한 broker 방식).
토큰이 없으면 "카카오 연결 필요" 안내를 반환한다.

방은 다대다(한 사람이 여러 방). 그중 '현재 작업 방'(``active_room_id``) 하나를
가리키고, 방을 지정하지 않은 도구는 그 방에 작동한다.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .. import storage
from ..identity import resolve_caller

_NEED_AUTH = {
    "ok": False,
    "error": "카카오 인증 정보가 없습니다. PlayMCP에서 카카오 계정 연결(권한 동의)을 먼저 진행해 주세요.",
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

        팀플톡(teamplay-talk)에서 팀 프로젝트용 방을 만들고 **현재 작업 방**으로
        설정한 뒤 초대 코드를 반환한다. 카카오 인증은 호스트(PlayMCP)가 전달한
        토큰으로 자동 처리된다.

        Args:
            name: 방 이름 (예: "캡스톤 3조")
            description: 방 설명 (선택)
        """
        caller = await resolve_caller()
        if caller is None:
            return _NEED_AUTH
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
            "message": f"'{room['name']}' 방 생성 완료 — 현재 작업 방으로 설정됨. 초대 코드: {room['invite_code']} (팀원이 join_room으로 참여)",
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
        설정한다. 카카오 인증은 호스트(PlayMCP) 토큰으로 자동 처리된다.

        Args:
            invite_code: 방 생성 시 발급된 초대 코드
        """
        caller = await resolve_caller()
        if caller is None:
            return _NEED_AUTH
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
            return _NEED_AUTH
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
        name="rooms",
        annotations={
            "title": "내 방 목록 / 방 정보",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def rooms(invite_code: str | None = None) -> dict[str, Any]:
        """Lists your teamplay-talk(팀플톡) rooms, or shows one room's details + members.

        팀플톡(teamplay-talk): **invite_code 없으면** 내가 속한 방 목록(이름·역할·초대코드·
        현재 작업 방), **있으면** 그 방의 상세(이름·초대코드·멤버 목록). 초대코드를 팀원에게
        공유하면 join_room으로 참여한다.

        Args:
            invite_code: 상세를 볼 방의 초대 코드 (생략 시 내 방 전체 목록)
        """
        caller = await resolve_caller()
        if caller is None:
            return _NEED_AUTH
        if invite_code:
            room = storage.get_room_by_invite_code(invite_code)
            if room is None:
                return {"ok": False, "error": "유효하지 않은 초대 코드입니다."}
            members = storage.list_members(room["id"])
            latest_decisions = {
                kind: _decision_payload(decision)
                for kind, decision in storage.latest_room_decisions(room["id"]).items()
            }
            return {
                "ok": True,
                "room_id": room["id"],
                "name": room["name"],
                "invite_code": room["invite_code"],
                "member_count": len(members),
                "members": [{"nickname": m["nickname"], "role": m["role"]} for m in members],
                "latest_decisions": latest_decisions,
            }
        my = storage.list_user_rooms(caller["id"])
        return {
            "ok": True,
            "count": len(my),
            "active_room": next((r["name"] for r in my if r["is_active"]), None),
            "rooms": [
                {
                    "name": r["name"],
                    "role": r["role"],
                    "invite_code": r["invite_code"],
                    "active": r["is_active"],
                }
                for r in my
            ],
        }

    @mcp.tool(
        name="delete_room",
        annotations={
            "title": "팀플 방 삭제 예약",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def delete_room(invite_code: str | None = None) -> dict[str, Any]:
        """Schedules a teamplay-talk(팀플톡) room for deletion with a 7-day recovery window.

        팀플톡(teamplay-talk) 방장이 방을 삭제 대기 상태로 전환한다. 즉시 데이터를
        지우지 않고 7일 동안 복구 가능하며, 그 뒤 백엔드가 방/폼/응답/로드맵을
        완전 삭제한다. 코드를 안 주면 현재 작업 방을 대상으로 한다.

        Args:
            invite_code: 삭제할 방의 초대 코드 (생략 시 현재 작업 방)
        """
        caller = await resolve_caller()
        if caller is None:
            return _NEED_AUTH
        code = invite_code
        if not code:
            active = storage.get_active_room(caller["id"])
            if active is None:
                return {
                    "ok": False,
                    "error": "현재 작업 중인 방이 없습니다. 삭제할 방의 초대 코드를 지정하세요.",
                }
            code = active["invite_code"]

        result = storage.delete_room(code, caller["id"])
        if result is None:
            return {"ok": False, "error": "유효하지 않은 초대 코드입니다."}
        if result.get("reason") == "not_owner":
            return {"ok": False, "error": "방장만 방을 삭제할 수 있습니다."}
        room = result["room"]
        if result.get("reason") == "already_deleting":
            return {
                "ok": True,
                "room_id": room["id"],
                "name": room["name"],
                "status": "deleting",
                "purge_after": room.get("purge_after"),
                "message": f"'{room['name']}' 방은 이미 삭제 대기 중입니다.",
            }
        return {
            "ok": True,
            "room_id": room["id"],
            "name": room["name"],
            "status": "deleting",
            "purge_after": room.get("purge_after"),
            "restore": "7일 안에 restore_room(invite_code)으로 복구할 수 있습니다.",
            "message": f"'{room['name']}' 방을 삭제 대기 상태로 전환했습니다. 7일 뒤 완전 삭제됩니다.",
        }

    @mcp.tool(
        name="restore_room",
        annotations={
            "title": "팀플 방 삭제 복구",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def restore_room(invite_code: str) -> dict[str, Any]:
        """Restores a teamplay-talk(팀플톡) room during its 7-day deletion grace period.

        팀플톡(teamplay-talk)에서 삭제 대기 중인 방을 방장이 복구한다. 복구되면
        다시 현재 작업 방으로 설정된다.

        Args:
            invite_code: 복구할 방의 초대 코드
        """
        caller = await resolve_caller()
        if caller is None:
            return _NEED_AUTH
        result = storage.restore_room(invite_code, caller["id"])
        if result is None:
            return {"ok": False, "error": "유효하지 않은 초대 코드입니다."}
        if result.get("reason") == "not_owner":
            return {"ok": False, "error": "방장만 방을 복구할 수 있습니다."}
        room = result["room"]
        if result.get("reason") == "already_active":
            return {
                "ok": True,
                "room_id": room["id"],
                "name": room["name"],
                "active": True,
                "message": f"'{room['name']}' 방은 이미 활성 상태입니다.",
            }
        if result.get("reason") == "expired":
            return {
                "ok": False,
                "error": "복구 유예 기간이 지났습니다. 곧 완전 삭제 대상입니다.",
                "purge_after": room.get("purge_after"),
            }
        return {
            "ok": True,
            "room_id": room["id"],
            "name": room["name"],
            "active": True,
            "message": f"'{room['name']}' 방을 복구했고 현재 작업 방으로 설정했습니다.",
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
            return _NEED_AUTH
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
            "room_scheduled_for_deletion": result.get("empty_scheduled", False),
            "purge_after": result.get("purge_after"),
            "message": (
                f"'{result['room']['name']}' 나가기 완료. 마지막 멤버가 나가서 7일 뒤 완전 삭제됩니다."
                if result.get("empty_scheduled")
                else f"'{result['room']['name']}' 나가기 완료."
            ),
        }

    # (room_info·get_invite_code 는 rooms 도구로 통합됨)
