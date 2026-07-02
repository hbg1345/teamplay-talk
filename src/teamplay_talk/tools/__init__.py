"""도구(tool) 도메인 모듈 모음.

각 도메인 모듈은 기존 세부 기능을 등록하고, 마지막에 ``consolidated`` 모듈이
방/폼/역할/로드맵/task/데일리/캘린더 기능을 공개 domain hub 도구로 묶는다.
PlayMCP 가이드(최대 20개)를 맞추되, 생성형 의사결정 도구는 따로 남겨 라우팅
오류를 줄인다.
"""

from __future__ import annotations

from fastmcp import FastMCP

from . import (
    calendar,
    consolidated,
    daily,
    feedback,
    integrations,
    meeting,
    members,
    notifications,
    reports,
    resources,
    roadmap,
    roles,
    rooms,
)


def register_all(mcp: FastMCP) -> None:
    """모든 도메인 모듈의 도구를 MCP 서버에 등록한다."""
    rooms.register(mcp)
    notifications.register(mcp)
    members.register(mcp)
    feedback.register(mcp)
    roles.register(mcp)
    meeting.register(mcp)
    roadmap.register(mcp)
    daily.register(mcp)
    resources.register(mcp)
    reports.register(mcp)
    integrations.register(mcp)
    calendar.register(mcp)
    consolidated.install(mcp)
