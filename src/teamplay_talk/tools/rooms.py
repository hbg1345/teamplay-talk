"""방(워크스페이스) 도메인 도구 — 카카오 인증 연동(🅐).

방 생성/참여는 **카카오 로그인**을 거쳐 완료된다. 도구는 로그인 링크만
반환하고, 실제 생성/참여는 ``/auth/kakao/callback`` 에서 인증된 kakao_id로
수행된다(``auth_web``). 이렇게 하면 멤버의 알림 토큰이 자동으로 확보된다.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .. import storage
from ..config import settings
from ..intents import encode_intent


def _login_url(state: str) -> str:
    return f"{settings.public_base_url}/auth/kakao/login?state={state}"


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
    def create_room(name: str, description: str | None = None) -> dict[str, Any]:
        """Creates a team-project room in teamplay-talk(팀플톡). Returns a Kakao login link; the room is created after login.

        팀플톡(teamplay-talk)에서 팀 프로젝트용 방을 만든다. 카카오 로그인 링크를
        반환하며, 사용자가 로그인하면 그 사람이 방장이 되어 방이 생성되고
        초대 코드가 발급된다. (로그인으로 알림 토큰도 함께 확보)

        Args:
            name: 방 이름 (예: "캡스톤 3조")
            description: 방 설명 (선택)
        """
        url = _login_url(encode_intent({"a": "create", "name": name, "desc": description}))
        return {
            "need_login": True,
            "login_url": url,
            "message": f"카카오 로그인하면 '{name}' 방이 생성되고 초대 코드가 나옵니다 → {url}",
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
    def join_room(invite_code: str) -> dict[str, Any]:
        """Joins a teamplay-talk(팀플톡) room via invite code. Returns a Kakao login link; joining completes after login.

        팀플톡(teamplay-talk)에서 초대 코드로 방에 참여한다. 카카오 로그인 링크를
        반환하며, 로그인하면 그 사람이 방 멤버로 등록된다. (알림 토큰 함께 확보)

        Args:
            invite_code: 방 생성 시 발급된 초대 코드
        """
        url = _login_url(encode_intent({"a": "join", "code": invite_code}))
        return {
            "need_login": True,
            "login_url": url,
            "message": f"카카오 로그인하면 방에 참여됩니다 → {url}",
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
    def leave_room(invite_code: str) -> dict[str, Any]:
        """Leaves a teamplay-talk(팀플톡) room. Returns a Kakao login link; leaving completes after login (identity check).

        팀플톡(teamplay-talk) 방에서 나간다. 본인 확인을 위해 카카오 로그인 링크를
        반환하며, 로그인하면 그 사람이 방 멤버에서 제거된다.

        Args:
            invite_code: 나갈 방의 초대 코드
        """
        url = _login_url(encode_intent({"a": "leave", "code": invite_code}))
        return {
            "need_login": True,
            "login_url": url,
            "message": f"카카오 로그인하면 방에서 나갑니다 → {url}",
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
    def room_info(invite_code: str) -> dict[str, Any]:
        """Reads a teamplay-talk(팀플톡) room's name and member list by invite code. No login required.

        팀플톡(teamplay-talk) 방의 이름과 멤버 목록(닉네임·역할)을 초대 코드로
        조회한다. 로그인 없이 누구나(코드 소지자) 볼 수 있다.

        Args:
            invite_code: 조회할 방의 초대 코드
        """
        room = storage.get_room_by_invite_code(invite_code)
        if room is None:
            return {"ok": False, "error": "방을 찾을 수 없습니다."}
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
