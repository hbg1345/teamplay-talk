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


# ────────────────────────── 할 일 (Task) API ──────────────────────────
# 톡캘린더 "할 일"(scope: talk_calendar_task). v1 엔드포인트.
# 일정(event)과 달리 due_info(마감일 + 알림시각)로 네이티브 리마인더를 태운다.
# create/task 는 검색으로 확인, update/delete/tasks 는 event 패턴 미러링 —
# ⚠️ 정확한 엔드포인트·필드명(특히 completed/id 필드)은 라이브 1회 호출로 확정할 것.
API_TASK = "https://kapi.kakao.com/v1/api/calendar"


def _build_task(
    *,
    content: str | None = None,
    due_date: str | None = None,
    time_zone: str = "Asia/Seoul",
    alarm_time: str | None = None,
    rrule: str | None = None,
    record_on: str | None = None,
    color: str | None = None,
) -> dict[str, Any]:
    """할 일 ``task`` 객체 조립.

    content:    할 일 내용(텍스트). 할 일엔 별도 링크 필드가 없으므로 URL은 여기 텍스트로.
    due_date:   마감일 (UTC RFC3339, 예: ``2026-07-10T00:00:00Z``).
    alarm_time: 마감일에 알림이 울릴 시각 ``"HHMM"`` (예: ``"0900"``, ``"2100"``).
    rrule:      반복 규칙(있으면 recur 로 감싼다).
    """
    task: dict[str, Any] = {}
    if content is not None:
        task["content"] = content
    due: dict[str, Any] = {}
    if due_date is not None:
        due["due_date"] = due_date
    if time_zone:
        due["time_zone"] = time_zone
    if alarm_time is not None:
        due["alarm_time"] = alarm_time
    if due:
        task["due_info"] = due
    if rrule is not None:
        recur: dict[str, Any] = {"rrule": rrule}
        if record_on is not None:
            recur["record_on"] = record_on
        task["recur"] = recur
    if color is not None:
        task["color"] = color
    return task


async def create_task(
    access_token: str,
    *,
    content: str,
    due_date: str,
    calendar_id: str = "primary",
    time_zone: str = "Asia/Seoul",
    alarm_time: str | None = None,
    rrule: str | None = None,
    record_on: str | None = None,
    color: str | None = None,
) -> dict[str, Any]:
    """할 일을 생성한다. 성공 시 생성된 할 일 ID 포함 dict(``task_id`` 추정 — 라이브 확정)."""
    task = _build_task(
        content=content, due_date=due_date, time_zone=time_zone,
        alarm_time=alarm_time, rrule=rrule, record_on=record_on, color=color,
    )
    data = {"calendar_id": calendar_id, "task": json.dumps(task, ensure_ascii=False)}
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.post(f"{API_TASK}/create/task", headers=_auth(access_token), data=data)
    return resp.json()


async def list_tasks(
    access_token: str,
    *,
    calendar_id: str | None = None,
    from_at: str | None = None,
    to_at: str | None = None,
    preset: str | None = None,
    time_zone: str | None = None,
) -> dict[str, Any]:
    """기간 내 할 일 목록. (엔드포인트/파라미터 event 미러링 — 라이브 검증)"""
    params: dict[str, Any] = {}
    if calendar_id is not None:
        params["calendar_id"] = calendar_id
    if preset is not None:
        params["preset"] = preset
    else:
        if from_at is not None:
            params["from"] = from_at
        if to_at is not None:
            params["to"] = to_at
    if time_zone is not None:
        params["time_zone"] = time_zone
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(f"{API_TASK}/tasks", headers=_auth(access_token), params=params)
    return resp.json()


async def update_task(
    access_token: str,
    task_id: str,
    *,
    content: str | None = None,
    due_date: str | None = None,
    time_zone: str = "Asia/Seoul",
    alarm_time: str | None = None,
    completed: bool | None = None,
    recur_update_type: str | None = None,
) -> dict[str, Any]:
    """할 일 수정(완료 토글·마감 변경 등). ``task_id`` + 변경 필드. (엔드포인트 라이브 검증)"""
    task = _build_task(
        content=content, due_date=due_date, time_zone=time_zone, alarm_time=alarm_time,
    )
    if completed is not None:
        task["completed"] = completed
    data: dict[str, Any] = {"task_id": task_id}
    if recur_update_type is not None:
        data["recur_update_type"] = recur_update_type
    if task:
        data["task"] = json.dumps(task, ensure_ascii=False)
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.post(f"{API_TASK}/update/task", headers=_auth(access_token), data=data)
    if not resp.content:
        return {"task_id": task_id}
    return resp.json()


async def delete_task(
    access_token: str,
    task_id: str,
    *,
    recur_update_type: str | None = None,
) -> dict[str, Any]:
    """할 일을 삭제한다(완료 시 정리용). 성공 시 ``{"task_id": ...}``. (엔드포인트 라이브 검증)"""
    params: dict[str, Any] = {"task_id": task_id}
    if recur_update_type is not None:
        params["recur_update_type"] = recur_update_type
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.request(
            "DELETE", f"{API_TASK}/delete/task", headers=_auth(access_token), params=params
        )
    if not resp.content:
        return {"task_id": task_id}
    return resp.json()
