"""리포트·대시보드 도메인 도구.

데일리 리포트를 생성하고, 팀 진척 현황을 대시보드로 요약한다.

계획된 도구:
- ``daily_report``: 데일리 리포트 생성
- ``dashboard``   : 팀 진척/현황 대시보드 요약
"""

from __future__ import annotations

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """리포트·대시보드 도메인 도구를 등록한다. (TODO: 구현 예정)"""
