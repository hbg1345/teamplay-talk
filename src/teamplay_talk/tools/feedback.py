"""의견 수렴 도메인 도구 (네이티브 폼/투표).

Google Forms 대신 teamplay-talk 자체 서버/DB로 폼을 제공한다.
``create_poll`` 로 폼을 만들면 공유 링크(`/form/<id>`)가 나오고, 누구나
그 링크로 응답하면 결과를 ``get_poll_results`` 로 집계해 읽는다.

계획된 도구:
- ``create_poll``       : 폼/투표 생성 → 공유 링크 반환
- ``get_poll_results``  : 폼 응답 집계 조회
"""

from __future__ import annotations

from typing import Any, Literal

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import storage
from ..config import settings


class PollQuestion(BaseModel):
    """폼 질문 1개."""

    text: str = Field(description="질문 내용")
    qtype: Literal["text", "single", "multi"] = Field(
        default="single",
        description="text=주관식, single=객관식 단일선택, multi=객관식 복수선택",
    )
    options: list[str] = Field(
        default_factory=list, description="객관식 선택지 (주관식이면 비움)"
    )


def register(mcp: FastMCP) -> None:
    """의견 수렴 도메인 도구를 등록한다."""

    @mcp.tool(
        name="create_poll",
        annotations={
            "title": "폼/투표 생성",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    def create_poll(
        room_id: int,
        title: str,
        questions: list[PollQuestion],
        description: str | None = None,
        anonymous: bool = True,
    ) -> dict[str, Any]:
        """Creates a native poll/form in teamplay-talk(팀플톡) and returns a shareable link.

        팀플톡(teamplay-talk)에서 자체 폼/투표를 생성하고, 누구나 응답할 수 있는
        공유 링크를 반환한다. (Google Forms 대체)

        Args:
            room_id: 폼이 속한 방 ID
            title: 폼 제목 (예: "회의 시간 투표")
            questions: 질문 목록 (text/single/multi 타입과 선택지)
            description: 폼 설명 (선택)
            anonymous: 익명 응답 여부 (기본 True)
        """
        result = storage.create_form(
            room_id=room_id,
            title=title,
            questions=[q.model_dump() for q in questions],
            description=description,
            anonymous=anonymous,
        )
        form_id = result["form"]["id"]
        return {
            "form_id": form_id,
            "title": result["form"]["title"],
            "share_url": f"{settings.public_base_url}/form/{form_id}",
            "question_count": len(result["questions"]),
        }

    @mcp.tool(
        name="get_poll_results",
        annotations={
            "title": "폼/투표 결과 조회",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def get_poll_results(form_id: int) -> dict[str, Any]:
        """Reads aggregated responses of a teamplay-talk(팀플톡) poll/form.

        팀플톡(teamplay-talk) 폼의 응답을 질문별로 집계해 반환한다.
        객관식은 선택지별 득표 수, 주관식은 답변 목록.

        Args:
            form_id: 결과를 조회할 폼 ID
        """
        results = storage.get_results(form_id)
        if results is None:
            return {"ok": False, "error": "존재하지 않는 폼입니다."}
        return {"ok": True, **results}
