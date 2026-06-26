"""회의 일정 조율 도구 — When2meet식 가용성 그리드(날짜 × 시간 매트릭스).

``schedule_meeting`` 이 **날짜(열, 기본 생성일부터 14일) × 시간(행, 시간 단위)** 그리드
폼을 만든다(SurveyJS ``matrixdropdown``). 각 셀은 **O(가능)/X(절대 불가)** 드롭다운이고,
그리드 아래에 **기타 건의사항** 자유기입 칸이 붙는다. 가로(날짜)는 폼에서 스크롤된다.

멤버 응답은 ``get_poll_results`` 가 셀별로 집계해 **X(절대 불가) 0명 중 O 최다** 칸을
best_slots로 모두 반환한다(AI 분석 불필요). best_slot은 대표값이다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastmcp import FastMCP

from .. import storage
from ..identity import resolve_caller

_KST = timezone(timedelta(hours=9))
_WD = ["월", "화", "수", "목", "금", "토", "일"]


def _date_labels(days: int, dates: list[str] | None) -> list[str]:
    """명시 dates가 있으면 그대로, 없으면 생성일(KST)부터 days일치 'M/D(요일)' 라벨."""
    if dates:
        return list(dates)
    today = datetime.now(_KST).date()
    out: list[str] = []
    for i in range(max(1, days)):
        d = today + timedelta(days=i)
        out.append(f"{d.month}/{d.day}({_WD[d.weekday()]})")
    return out


def _time_slots(start_hour: int, end_hour: int, slot_minutes: int) -> list[str]:
    """start_hour~end_hour 를 slot_minutes 간격의 'HH:MM' 라벨 목록으로 만든다."""
    step = slot_minutes if slot_minutes and slot_minutes > 0 else 60
    slots: list[str] = []
    t, end = start_hour * 60, end_hour * 60
    while t < end:
        slots.append(f"{t // 60:02d}:{t % 60:02d}")
        t += step
    return slots


def register(mcp: FastMCP) -> None:
    """회의 일정 조율 도구를 등록한다."""

    @mcp.tool(
        name="schedule_meeting",
        annotations={
            "title": "회의 가용성 그리드 생성",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def schedule_meeting(
        days: int = 14,
        dates: list[str] | None = None,
        start_hour: int = 9,
        end_hour: int = 22,
        slot_minutes: int = 60,
        room_id: int | None = None,
        close_minutes: int | None = 1440,
    ) -> dict[str, Any]:
        """Creates a When2meet-style availability grid (dates x time, O/X) for meetings.

        회의 일정 조율용 **가용성 그리드**를 만든다: **열=날짜**(기본 생성일부터 14일,
        가로 스크롤) × **행=시간**(시간 단위). 각 셀은 **O(가능)/X(절대 불가)** 드롭다운,
        그리드 아래 **기타 건의사항** 자유기입 칸.

        보통은 인자 없이 schedule_meeting() 만 호출하면 된다(오늘부터 14일 × 9~22시 1시간).
        특정 날짜만 보려면 dates에 직접 라벨을 넘긴다(예: ["6/30(월)", "7/1(화)"]).

        멤버가 셀에 O/X 표시 → get_poll_results가 **X 0명 중 O 최다** 칸을 best_slots로
        모두 반환(AI 분석 불필요; best_slot은 대표값). 생성 후 **팀장 확인받고** send_form.
        전원 응답 시 자동 마감.

        Args:
            days: 생성일부터 며칠치 (기본 14; dates 주면 무시)
            dates: 날짜 라벨 직접 지정 (선택; 주면 days 무시)
            start_hour: 시간 행 시작(시, 기본 9)
            end_hour: 시간 행 종료(시, 기본 22)
            slot_minutes: 시간 칸 간격(분, 기본 60)
            room_id: 대상 방 (생략 시 현재 작업 방)
            close_minutes: 마감까지 분 (기본 1일; 전원 응답 시 자동 마감)
        """
        date_cols = _date_labels(days, dates)
        slots = _time_slots(start_hour, end_hour, slot_minutes)
        if not slots:
            return {"ok": False, "error": "start_hour < end_hour 여야 합니다."}

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
            closes_at = datetime.now(timezone.utc) + timedelta(minutes=int(close_minutes))

        schema = {
            "title": "회의 가능 시간",
            "description": "각 칸에 **O(가능) / X(절대 불가)** 를 선택하세요. 비워두면 '보통'.",
            "completeText": "제출",
            "showQuestionNumbers": "off",
            "elements": [
                {
                    "type": "matrixdropdown",
                    "name": "availability",
                    "title": "가능한 시간 (← 날짜는 옆으로 스크롤)",
                    "cellType": "dropdown",
                    "isRequired": False,
                    "choices": [
                        {"value": "O", "text": "⭕ 가능"},
                        {"value": "X", "text": "❌ 절대 불가"},
                    ],
                    "columns": [{"name": d, "title": d} for d in date_cols],
                    "rows": slots,
                },
                {
                    "type": "comment",
                    "name": "note",
                    "title": "기타 건의사항 (선택)",
                    "isRequired": False,
                },
            ],
        }
        form = storage.create_form(
            room_id=room_id,
            title="회의 가능 시간",
            schema_json=schema,
            anonymous=False,
            creator_user_id=caller["id"] if caller else None,
            closes_at=closes_at,
            close_on_all=True,
        )
        fid = form["id"]
        members = storage.list_members(room_id)
        storage.create_invites(fid, [m["id"] for m in members])
        return {
            "ok": True,
            "form_id": fid,
            "date_count": len(date_cols),
            "dates": date_cols,
            "time_slots": slots,
            "members": [m["nickname"] for m in members],
            "action_required": (
                "⚠️ 아직 보내지 마세요. 그리드 범위(날짜·시간)를 팀장에게 보여주고 확인받은 "
                "뒤에만 send_form(form_id) 하세요. 응답 모이면 get_poll_results로 best_slots 확인."
            ),
        }
