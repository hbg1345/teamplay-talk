"""팀원·역할 도메인 도구.

팀원 역할을 분배하고, 랜덤 룰렛으로 역할/순서를 무작위 배정한다.

계획된 도구:
- ``assign_roles`` : 팀원에게 역할 분배
- ``spin_roulette``: 랜덤 룰렛으로 무작위 선택/배정
"""

from __future__ import annotations

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """팀원·역할 도메인 도구를 등록한다. (TODO: 구현 예정)"""
