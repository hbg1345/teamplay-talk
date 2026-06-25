"""외부 연동 도메인 도구.

Git, 사용자 자신의 AI 등 외부 서비스와 연동한다.
(문서/자료/캘린더 등은 Google MCP가 담당하므로 여기서 제외)

계획된 도구:
- ``connect_git``: Git 저장소 연동
- ``connect_ai`` : 사용자 자신의 AI 연결
"""

from __future__ import annotations

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """외부 연동 도메인 도구를 등록한다. (TODO: 구현 예정)"""
