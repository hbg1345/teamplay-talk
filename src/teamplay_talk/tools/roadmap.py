"""로드맵 도메인 도구.

주제를 분석해 로드맵을 형성하고, 이후 로드맵을 수정한다.

계획된 도구:
- ``build_roadmap`` : 주제 분석 → 로드맵 형성
- ``update_roadmap``: 로드맵 수정
"""

from __future__ import annotations

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """로드맵 도메인 도구를 등록한다. (TODO: 구현 예정)"""
