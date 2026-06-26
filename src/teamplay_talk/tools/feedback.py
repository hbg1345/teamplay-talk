"""의견 수렴 도메인 도구 (네이티브 폼/투표 — SurveyJS 엔진).

``create_poll`` 로 폼을 만들면 응답 링크가 나오고, 팀원은 그 링크를 카톡으로 받아
브라우저에서 응답한다(AI·앱·로그인 불필요). 응답은 ``get_poll_results`` 로 집계한다.

AI는 우리 타입드 스키마(질문 타입)만 쓰고, 서버가 SurveyJS JSON으로 변환한다.
"""

from __future__ import annotations

from typing import Any, Literal

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import kakao_store, storage
from ..config import settings
from ..identity import resolve_caller


class PollQuestion(BaseModel):
    """폼 질문 1개."""

    title: str = Field(description="질문 내용")
    type: Literal["single", "multi", "rank", "rating", "text"] = Field(
        default="single",
        description=(
            "single=객관식 단일선택, multi=복수선택, "
            "rank=선호 순위(드래그 정렬), rating=점수(1~N), text=주관식"
        ),
    )
    choices: list[str] = Field(
        default_factory=list, description="선택지 (single/multi/rank용; text/rating은 비움)"
    )
    rate_max: int = Field(default=5, description="rating 최대 점수 (rating 타입에서만)")


_SJS_TYPE = {
    "single": "radiogroup",
    "multi": "checkbox",
    "rank": "ranking",
    "rating": "rating",
    "text": "comment",
}


def _to_surveyjs(title: str, description: str | None, questions: list[PollQuestion]) -> dict[str, Any]:
    """우리 타입드 질문 → SurveyJS 폼 JSON."""
    elements = []
    for i, q in enumerate(questions):
        el: dict[str, Any] = {
            "type": _SJS_TYPE.get(q.type, "radiogroup"),
            "name": f"q{i + 1}",
            "title": q.title,
            "isRequired": True,
        }
        if q.type in ("single", "multi", "rank"):
            el["choices"] = q.choices
        elif q.type == "rating":
            el["rateMax"] = q.rate_max
        elements.append(el)
    schema: dict[str, Any] = {
        "title": title,
        "showQuestionNumbers": "off",
        "completeText": "제출",
        "elements": elements,
    }
    if description:
        schema["description"] = description
    return schema


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
    async def create_poll(
        title: str,
        questions: list[PollQuestion],
        room_id: int | None = None,
        description: str | None = None,
        anonymous: bool = True,
        close_minutes: int | None = None,
        close_on_all: bool = False,
    ) -> dict[str, Any]:
        """Creates a native poll/form in teamplay-talk(팀플톡) and returns a response link.

        팀플톡 자체 폼/투표를 만들고 응답 링크를 반환한다. 팀원은 이 링크를 카톡으로
        받아 브라우저에서 응답한다(AI·앱·로그인 불필요).

        질문 타입(type): single=단일선택, multi=복수선택, rank=선호 순위(드래그),
        rating=점수, text=주관식.

        **anonymous=True (기본)**: 공유 링크 1개·익명 → 의견수렴·여론조사 등 "전체 목소리
        모으기". (익명이라 **중복 제출은 막을 수 없음** — 한 사람이 여러 번 가능)
        **anonymous=False**: 응답을 *특정 멤버에 매칭* 하거나 **1인 1표(중복 방지)**가 필요할 때
        — 역할분배·진척체크·구속력 있는 투표. 멤버별 개인 링크, **재제출 시 교체(1인 1응답 보장)**.

        생성 후 배포는 **send_form(form_id)** 으로 한다(notify_room ❌). send_form이
        익명이면 한 메시지 브로드캐스트, 식별이면 각자에게 개인 링크를 보낸다.

        Args:
            title: 폼 제목 (예: "회식 날짜 투표")
            questions: 질문 목록
            room_id: 폼이 속한 방 ID (생략 시 **현재 작업 방**). ID 추측 금지 —
                     보통 생략하면 됨.
            description: 폼 설명 (선택)
            anonymous: 공유링크(True·기본) vs 멤버별 식별 링크(False·매칭 필요시만)
            close_minutes: N분 뒤 자동 마감 (선택)
            close_on_all: 전원 응답 시 자동 마감 (선택)
        """
        caller = await resolve_caller()
        if caller is None:
            return {"ok": False, "error": "인증이 필요합니다 — PlayMCP에서 이 MCP 인증을 먼저 해주세요."}
        if room_id is None:
            active = storage.get_active_room(caller["id"])
            if active is None:
                return {
                    "ok": False,
                    "error": "현재 작업 중인 방이 없습니다. create_room으로 방을 만들거나 switch_room으로 선택하세요.",
                }
            room_id = active["id"]
        elif storage.get_room(room_id) is None:
            return {"ok": False, "error": f"방 {room_id}를 찾을 수 없습니다. my_rooms로 방 목록을 확인하세요."}
        creator_id = caller["id"]

        closes_at = None
        if close_minutes:
            from datetime import datetime, timedelta, timezone

            closes_at = datetime.now(timezone.utc) + timedelta(minutes=int(close_minutes))

        form = storage.create_form(
            room_id=room_id,
            title=title,
            schema_json=_to_surveyjs(title, description, questions),
            description=description,
            anonymous=anonymous,
            creator_user_id=creator_id,
            closes_at=closes_at,
            close_on_all=close_on_all,
        )
        fid = form["id"]
        base = f"{settings.public_base_url}/form/{fid}"
        out: dict[str, Any] = {
            "ok": True,
            "form_id": fid,
            "title": title,
            "anonymous": anonymous,
            "question_count": len(questions),
            "next": "send_form(form_id)으로 팀에 발송하세요 (notify_room ❌).",
        }
        if anonymous:
            out["share_url"] = base
        else:
            members = storage.list_members(room_id)
            storage.create_invites(fid, [m["id"] for m in members])
            out["mode"] = "identified — send_form이 각 멤버에게 개인 링크를 발송"
        return out

    @mcp.tool(
        name="gather_opinions",
        annotations={
            "title": "의견수렴 시작(자유의견)",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def gather_opinions(
        question: str,
        room_id: int | None = None,
        anonymous: bool = True,
        close_minutes: int | None = 1440,
    ) -> dict[str, Any]:
        """Starts opinion gathering (stage 1 of 의견수렴형) — a free-text poll to the team.

        팀의 의사결정(**회의 시간·약속 장소·주제 등 '뭘로 할까'**)을 시작한다.
        **사용자에게 후보를 묻지 마라** — 이 도구로 팀원에게 자유의견을 모으는 게 시작이다.

        기본 2단계 흐름:
        (1) gather_opinions(question) → 팀원이 자유롭게 글로 의견 → send_form → [완료 nudge]
        (2) get_poll_results로 의견 읽고 **AI가 항목화** → create_poll(**복수선택** 본투표, 그
            항목들) → send_form → 결과 공지.

        약속 장소 정하기:
        (1) gather_opinions("각자 출발 위치(근처 역/동네)나 선호 장소를 적어주세요") →
            send_form → get_poll_results.
        (2) 팀원이 대충 쓴 장소를 AI가 정규화한다. 같은 역·상권·동네는 합치고
            (예: "강남", "강남역", "신논현 근처" → "강남역/신논현역 일대"),
            실제로 다를 수 있으면 억지로 합치지 말고 원문 의미를 보존한다.
        (3) 카카오맵 MCP가 사용 가능하면 위치 검색으로 중간 후보/주변 장소를 추가한다.
            사용 불가하면 새 장소를 만들지 말고 제출된 후보만 정규화한다.
        (4) 정규화한 후보로 create_poll(복수선택 본투표)을 만든다.

        예: "회의 일정 잡자" → gather_opinions("회의 가능한 날짜·시간을 자유롭게 적어주세요").

        Args:
            question: 팀원에게 물을 질문 (네가 맥락 보고 직접 작성)
            room_id: 대상 방 (생략 시 현재 작업 방)
            anonymous: 익명 여부 (기본 True)
            close_minutes: 마감까지 분 (기본 1일; 전원 응답 시 자동 마감)
        """
        caller = await resolve_caller()
        if room_id is None:
            if caller is None:
                return {"ok": False, "error": "카카오 인증이 필요합니다."}
            active = storage.get_active_room(caller["id"])
            if active is None:
                return {"ok": False, "error": "현재 작업 방이 없습니다."}
            room_id = active["id"]

        closes_at = None
        if close_minutes:
            from datetime import datetime, timedelta, timezone

            closes_at = datetime.now(timezone.utc) + timedelta(minutes=int(close_minutes))

        schema = {
            "title": question,
            "completeText": "제출",
            "showQuestionNumbers": "off",
            "elements": [
                {"type": "comment", "name": "opinion", "title": question, "isRequired": True}
            ],
        }
        form = storage.create_form(
            room_id=room_id,
            title=question,
            schema_json=schema,
            anonymous=anonymous,
            creator_user_id=caller["id"] if caller else None,
            closes_at=closes_at,
            close_on_all=True,
        )
        fid = form["id"]
        if not anonymous:
            storage.create_invites(fid, [m["id"] for m in storage.list_members(room_id)])
        return {
            "ok": True,
            "form_id": fid,
            "stage": "1/2 (의견수렴)",
            "next": (
                "send_form(form_id)으로 팀원에게 발송 → 응답 모이면(또는 마감 nudge) "
                "get_poll_results로 의견을 읽고 **항목화**한 뒤, create_poll(복수선택 본투표)로 "
                "2단계 투표를 만드세요. 약속 장소라면 같은 역·상권·동네를 정규화하고, "
                "카카오맵 MCP가 있으면 중간 후보/주변 장소를 추가하되 없으면 제출 후보만 쓰세요."
            ),
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

        폼 응답을 질문별로 집계해 반환한다. 객관식=선택지별 카운트, rank=순위점수,
        rating=평균, 주관식=답변 목록. 식별 폼이면 멤버별 raw 응답도 포함(역할 매칭용).

        Args:
            form_id: 결과를 조회할 폼 ID
        """
        results = storage.get_results(form_id)
        if results is None:
            return {"ok": False, "error": "존재하지 않는 폼입니다."}
        return {"ok": True, **results}

    @mcp.tool(
        name="close_poll",
        annotations={
            "title": "폼/투표 마감",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def close_poll(form_id: int) -> dict[str, Any]:
        """Closes a teamplay-talk(팀플톡) poll and returns final results.

        폼을 마감(추가 응답 차단)하고 최종 결과를 반환한다.

        Args:
            form_id: 마감할 폼 ID
        """
        results = storage.get_results(form_id)
        if results is None:
            return {"ok": False, "error": "존재하지 않는 폼입니다."}
        storage.close_form(form_id)
        return {"ok": True, "closed": True, **results}

    @mcp.tool(
        name="send_form",
        annotations={
            "title": "폼 링크 팀에 발송",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,  # 외부(카카오) 발송
        },
    )
    async def send_form(form_id: int, message: str | None = None) -> dict[str, Any]:
        """Sends a teamplay-talk(팀플톡) form link to the team via KakaoTalk.

        폼을 팀에 발송한다. **익명 폼이면 공유 링크 1개를 전원에게**, **식별 폼이면
        각 멤버에게 자기 개인 링크를** 보낸다. create_poll 뒤 배포는 이걸로 한다.
        (notify_room으로 폼 링크를 보내지 말 것 — 개인 링크가 섞인다.)

        Args:
            form_id: 발송할 폼 ID
            message: 안내 문구 (생략 시 기본). 링크는 자동으로 뒤에 붙는다.
        """
        form = storage.get_form(form_id)
        if form is None:
            return {"ok": False, "error": "존재하지 않는 폼입니다."}
        base = f"{settings.public_base_url}/form/{form_id}"
        prefix = (message or f"📋 '{form['title']}' 폼에 응답해주세요").rstrip()

        sent: list[str] = []
        failed: list[str] = []
        if form["anonymous"]:
            for m in kakao_store.list_members_with_tokens(form["room_id"]):
                status = await kakao_store.send_with_refresh(m, f"{prefix}\n{base}")
                (sent if status == 200 else failed).append(m["nickname"])
        else:
            for r in storage.list_form_recipients(form_id):
                status = await kakao_store.send_with_refresh(r, f"{prefix}\n{base}?t={r['invite_token']}")
                (sent if status == 200 else failed).append(r["nickname"])

        if not sent and not failed:
            return {"ok": False, "error": "발송 대상이 없습니다(멤버가 카카오 로그인을 마쳐야 함)."}
        return {"ok": True, "form_id": form_id, "sent_to": sent, "failed": failed, "count": len(sent)}
