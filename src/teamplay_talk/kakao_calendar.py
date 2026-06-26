"""카카오 톡캘린더 — 일반 일정 CRUD 클라이언트.

broker가 헤더로 넘긴 사용자 access_token(scope: ``talk_calendar``)으로 카카오
톡캘린더 REST API(``kapi.kakao.com/v2/api/calendar``)를 호출한다. kakao.py 와
같은 형태의 순수 async 함수 모음.

시간 형식: ``start_at``/``end_at`` 는 **UTC RFC3339**(예: ``2026-07-01T03:00:00Z``).
KST는 UTC+9. ``time_zone`` 기본값 ``Asia/Seoul``.

카카오 콘솔 요구사항:
- 동의항목 "톡캘린더 및 일정 생성/조회/편집/삭제(talk_calendar)" 활성화
- 톡캘린더 API "사용 권한" 신청·승인 (없으면 앱 멤버만 호출 가능)
"""

from __future__ import annotations

import json
from typing import Any

import httpx

API = "https://kapi.kakao.com/v2/api/calendar"


def _auth(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _build_event(
    *,
    title: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    time_zone: str = "Asia/Seoul",
    all_day: bool = False,
    lunar: bool = False,
    rrule: str | None = None,
    description: str | None = None,
    location: dict[str, Any] | None = None,
    reminders: list[int] | None = None,
    color: str | None = None,
) -> dict[str, Any]:
    """일정 ``event`` 객체를 조립한다. (지정된 필드만 포함)"""
    event: dict[str, Any] = {}
    if title is not None:
        event["title"] = title
    if start_at is not None and end_at is not None:
        event["time"] = {
            "start_at": start_at,
            "end_at": end_at,
            "time_zone": time_zone,
            "all_day": all_day,
            "lunar": lunar,
        }
    if rrule is not None:
        event["rrule"] = rrule
    if description is not None:
        event["description"] = description
    if location is not None:
        event["location"] = location
    if reminders is not None:
        event["reminders"] = reminders
    if color is not None:
        event["color"] = color
    return event


async def create_event(
    access_token: str,
    *,
    title: str,
    start_at: str,
    end_at: str,
    calendar_id: str = "primary",
    time_zone: str = "Asia/Seoul",
    all_day: bool = False,
    lunar: bool = False,
    rrule: str | None = None,
    description: str | None = None,
    location: dict[str, Any] | None = None,
    reminders: list[int] | None = None,
    color: str | None = None,
) -> dict[str, Any]:
    """일반 일정을 생성한다. 성공 시 ``{"event_id": ...}``, 실패 시 카카오 에러 dict."""
    event = _build_event(
        title=title, start_at=start_at, end_at=end_at, time_zone=time_zone,
        all_day=all_day, lunar=lunar, rrule=rrule, description=description,
        location=location, reminders=reminders, color=color,
    )
    data = {"calendar_id": calendar_id, "event": json.dumps(event, ensure_ascii=False)}
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.post(f"{API}/create/event", headers=_auth(access_token), data=data)
    return resp.json()


async def list_events(
    access_token: str,
    *,
    calendar_id: str | None = None,
    from_at: str | None = None,
    to_at: str | None = None,
    preset: str | None = None,
    time_zone: str | None = None,
    limit: int | None = None,
    next_page_token: str | None = None,
) -> dict[str, Any]:
    """기간 내 일정 목록을 가져온다. ``{"events": [...], "has_next": ..., "after_url"?}``.

    ``from_at``/``to_at`` (UTC RFC3339, to는 from+31일 이내) 또는 ``preset``
    (TODAY/THIS_WEEK/THIS_MONTH) 중 하나를 줘야 한다.
    """
    params: dict[str, Any] = {}
    if calendar_id is not None:
        params["calendar_id"] = calendar_id
    if next_page_token is not None:
        params["next_page_token"] = next_page_token
    elif preset is not None:
        params["preset"] = preset
    else:
        if from_at is not None:
            params["from"] = from_at
        if to_at is not None:
            params["to"] = to_at
        if limit is not None:
            params["limit"] = limit
    if time_zone is not None:
        params["time_zone"] = time_zone
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(f"{API}/events", headers=_auth(access_token), params=params)
    return resp.json()


async def get_event(access_token: str, event_id: str) -> dict[str, Any]:
    """일정 상세를 조회한다. ``{"event": {...}}``."""
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            f"{API}/event", headers=_auth(access_token), params={"event_id": event_id}
        )
    return resp.json()


async def update_event(
    access_token: str,
    event_id: str,
    *,
    calendar_id: str | None = None,
    recur_update_type: str | None = None,
    title: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    time_zone: str = "Asia/Seoul",
    all_day: bool = False,
    lunar: bool = False,
    rrule: str | None = None,
    description: str | None = None,
    location: dict[str, Any] | None = None,
    reminders: list[int] | None = None,
    color: str | None = None,
) -> dict[str, Any]:
    """일반 일정을 수정한다(지정한 필드만). 성공 시 ``{"event_id": ...}`` (반복 일정은 본문 없음)."""
    event = _build_event(
        title=title, start_at=start_at, end_at=end_at, time_zone=time_zone,
        all_day=all_day, lunar=lunar, rrule=rrule, description=description,
        location=location, reminders=reminders, color=color,
    )
    data: dict[str, Any] = {"event_id": event_id}
    if calendar_id is not None:
        data["calendar_id"] = calendar_id
    if recur_update_type is not None:
        data["recur_update_type"] = recur_update_type
    if event:
        data["event"] = json.dumps(event, ensure_ascii=False)
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.post(
            f"{API}/update/event/host", headers=_auth(access_token), data=data
        )
    if not resp.content:
        return {"event_id": event_id}  # 반복 일정 수정은 본문 없이 200
    return resp.json()


async def delete_event(
    access_token: str,
    event_id: str,
    *,
    recur_update_type: str | None = None,
) -> dict[str, Any]:
    """일반 일정을 삭제한다. 성공 시 ``{"event_id": ...}``."""
    params: dict[str, Any] = {"event_id": event_id}
    if recur_update_type is not None:
        params["recur_update_type"] = recur_update_type
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.request(
            "DELETE", f"{API}/delete/event", headers=_auth(access_token), params=params
        )
    if not resp.content:
        return {"event_id": event_id}
    return resp.json()
