"""회의 일정 조율 도구 — When2meet식 가용성 그리드(날짜 × 시간 매트릭스).

``schedule_meeting`` 이 **날짜(열) × 시간(행)** 그리드 폼을 만든다(SurveyJS
``matrixdropdown``, 각 셀 = boolean 체크박스). 멤버가 가능한 셀을 체크하면
``get_poll_results`` 가 셀별 가능 인원을 세서 가장 많이 되는 시간을 찾는다(결정적).
AI 분석 없이 카운트로 끝나므로 GPT-4.0이 틀릴 여지가 없다.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .. import storage
from ..identity import resolve_caller


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
        dates: list[str],
        start_hour: int = 9,
        end_hour: int = 18,
        slot_minutes: int = 60,
        room_id: int | None = None,
        close_minutes: int | None = 1440,
    ) -> dict[str, Any]:
        """Creates a When2meet-style availability grid (dates x time) for meeting scheduling.

        회의 일정 조율용 **가용성 그리드**(날짜=열 × 시간=행, 각 셀 체크) 폼을 만든다.
        **너(AI)가 후보 날짜를 직접 생성**해 dates로 넘겨라(현재 날짜 기준 구체적 라벨;
        사용자에게 떠넘기지 말 것). 시간 행은 start_hour~end_hour를 slot_minutes 간격으로
        자동 생성한다.

        멤버가 가능한 셀을 모두 체크 → get_poll_results가 셀별 가능 인원을 세서
        **best_slot**(가장 많이 되는 날짜+시간)을 결정적으로 반환한다(AI 분석 불필요).
        생성 후 **그리드를 팀장에게 보여주고 확인받은 뒤** send_form 한다. 전원 응답 시
        자동 마감.

        Args:
            dates: **AI가 생성한** 후보 날짜 라벨들 (예: ["6/30(월)", "7/1(화)", "7/2(수)"])
            start_hour: 그리드 시작 시각(시, 기본 9)
            end_hour: 그리드 종료 시각(시, 기본 18)
            slot_minutes: 시간 칸 간격(분, 기본 60)
            room_id: 대상 방 (생략 시 현재 작업 방)
            close_minutes: 마감까지 분 (기본 1일; 전원 응답 시 더 일찍 자동 마감)
        """
        if not dates:
            return {"ok": False, "error": "후보 날짜를 1개 이상 직접 생성해서 넘겨주세요."}
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
            from datetime import datetime, timedelta, timezone

            closes_at = datetime.now(timezone.utc) + timedelta(minutes=int(close_minutes))

        schema = {
            "title": "회의 가능 시간",
            "description": "참석 **가능한 시간을 모두** 체크해주세요.",
            "completeText": "제출",
            "showQuestionNumbers": "off",
            "elements": [
                {
                    "type": "matrixdropdown",
                    "name": "availability",
                    "title": "가능한 시간 (셀 체크)",
                    "cellType": "boolean",
                    "isRequired": False,
                    "columns": [{"name": d, "title": d} for d in dates],
                    "rows": slots,
                }
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
            "dates": list(dates),
            "time_slots": slots,
            "members": [m["nickname"] for m in members],
            "action_required": (
                "⚠️ 아직 보내지 마세요. 그리드(날짜×시간)를 팀장에게 보여주고 확인받은 뒤에만 "
                "send_form(form_id) 하세요. 응답 모이면 get_poll_results로 best_slot 확인."
            ),
        }
