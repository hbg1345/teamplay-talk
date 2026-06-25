"""리소스(외부 산출물 링크) 도메인 도구.

일정·의견수렴·장소정하기는 Google Forms, 회의록·자료·캘린더는
Google MCP(Docs/Drive/Calendar/Meet)가 담당한다. 이 모듈은 그 산출물들의
링크를 **방에 등록·조회**하여 teamplay-talk를 팀 협업 허브로 묶는다.

(Google MCP/Forms는 "생성"만, teamplay-talk는 "묶기"만 담당)

계획된 도구:
- ``attach_resource``: 방에 외부 산출물(폼/캘린더/문서/드라이브 등) 링크 등록
- ``list_resources`` : 방에 등록된 리소스 목록 조회
"""

from __future__ import annotations

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """리소스 도메인 도구를 등록한다. (TODO: 구현 예정)"""
