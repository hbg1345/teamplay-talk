"""방(워크스페이스) 도메인 도구.

팀플 협업을 위한 워크스페이스를 만들고 참여한다.

이 모듈의 ``create_room`` 은 PlayMCP 규격을 따르는 **도구 작성 템플릿**이다.
다른 도메인 모듈도 이 형식(annotations 5종 모두 지정 + 영문/국문 병기
description + MCP명 포함)을 따른다.

계획된 도구:
- ``create_room``: 팀플 워크스페이스(방) 생성
- ``join_room``  : 초대 코드로 방 참여
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .. import storage


def register(mcp: FastMCP) -> None:
    """방 도메인 도구를 등록한다."""

    @mcp.tool(
        name="create_room",
        annotations={
            "title": "팀플 방 생성",
            "readOnlyHint": False,  # DB에 쓴다
            "destructiveHint": False,  # 기존 데이터를 지우지 않는다
            "idempotentHint": False,  # 호출할 때마다 새 방이 생긴다
            "openWorldHint": False,  # 외부 세계가 아닌 자체 DB만 다룬다
        },
    )
    def create_room(
        name: str, owner: str, description: str | None = None
    ) -> dict[str, Any]:
        """Creates a team-project workspace(room) in teamplay-talk(팀플톡) and returns its invite code.

        팀플톡(teamplay-talk)에서 팀 프로젝트용 워크스페이스(방)를 생성하고,
        팀원이 참여할 수 있는 초대 코드를 반환한다.

        Args:
            name: 방 이름 (예: "캡스톤 3조")
            owner: 방장(생성자) 닉네임
            description: 방 설명 (선택)
        """
        result = storage.create_room(
            name=name, owner_nickname=owner, description=description
        )
        room = result["room"]
        return {
            "room_id": room["id"],
            "name": room["name"],
            "invite_code": room["invite_code"],
            "owner": result["owner"]["nickname"],
        }

    @mcp.tool(
        name="join_room",
        annotations={
            "title": "팀플 방 참여",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,  # 같은 사람이 다시 참여해도 상태 동일
            "openWorldHint": False,
        },
    )
    def join_room(
        invite_code: str, nickname: str
    ) -> dict[str, Any]:
        """Joins an existing teamplay-talk(팀플톡) room using an invite code.

        팀플톡(teamplay-talk)에서 초대 코드로 기존 방에 참여한다.

        Args:
            invite_code: 방 생성 시 발급된 초대 코드
            nickname: 참여자 닉네임
        """
        result = storage.join_room(invite_code=invite_code, nickname=nickname)
        if result is None:
            return {"ok": False, "error": "유효하지 않은 초대 코드입니다."}
        room = result["room"]
        return {
            "ok": True,
            "room_id": room["id"],
            "name": room["name"],
            "joined_as": result["user"]["nickname"],
        }
