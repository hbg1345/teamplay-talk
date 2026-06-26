"""도구(tool) 도메인 모듈 모음.

각 도메인 모듈은 ``register(mcp)`` 함수를 노출하며, 관련 기능을 1~2개의
MCP 도구로 묶어 등록한다. PlayMCP 가이드 권장(도구 3~10개, 최대 20개)에
맞추기 위해 기능을 도메인 단위로 그룹화한다.

일정·의견수렴·장소·회의록·자료·캘린더는 Google Forms / Google MCP가
담당하고, teamplay-talk는 그 산출물 링크를 방에 묶는 ``resources`` 모듈로
협업 허브 역할을 한다.
"""

from __future__ import annotations

from fastmcp import FastMCP

from . import (
    calendar,
    feedback,
    integrations,
    members,
    notifications,
    reports,
    resources,
    roadmap,
    rooms,
)


def register_all(mcp: FastMCP) -> None:
    """모든 도메인 모듈의 도구를 MCP 서버에 등록한다."""
    rooms.register(mcp)
    notifications.register(mcp)
    members.register(mcp)
    feedback.register(mcp)
    roadmap.register(mcp)
    resources.register(mcp)
    reports.register(mcp)
    integrations.register(mcp)
    calendar.register(mcp)
