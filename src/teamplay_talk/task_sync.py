"""talk_calendar_task 동기화 — 워크플로우 항목(체크인/폼)을 각 멤버의 톡캘린더
'할 일'로 만들고, 완료/처리되면 삭제한다.

설계:
- 전부 **best-effort / non-blocking**. 카카오 호출·필드가 틀려도 예외를 삼키므로
  기존 talk_message 흐름은 절대 안 깨진다. (할 일은 "확실한 네이티브 알림" 보강용)
- 링크 매핑(``kakao_task_links``)으로 "완료 시 삭제"를 추적한다.
- 토큰 만료 시 refresh 후 1회 재시도(기존 calendar.py 패턴 동일).
- 할 일엔 링크 필드가 없어 content(텍스트)만 — 실제 폼 링크는 기존 talk_message가 담당.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from . import kakao, kakao_calendar, kakao_store, storage
from .config import settings

log = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def _task_id(res: Any) -> str | None:
    """카카오 응답에서 할 일 ID 추출(필드명 라이브 확정 전 방어적으로)."""
    if not isinstance(res, dict):
        return None
    for key in ("task_id", "id"):
        if res.get(key):
            return str(res[key])
    return None


def _date_due(day: Any, hour: int = 23, minute: int = 59) -> str:
    """date/ISO 문자열 → 그날 KST hour:minute 의 UTC RFC3339."""
    if isinstance(day, str):
        day = date.fromisoformat(day[:10])
    elif isinstance(day, datetime):
        day = day.date()
    dt = datetime(day.year, day.month, day.day, hour, minute, tzinfo=KST)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


async def _refresh(member: dict[str, Any]) -> str | None:
    """멤버 access token 갱신 후 새 토큰 반환(실패 None). 저장까지 수행."""
    rt = member.get("kakao_refresh_token")
    if not rt:
        return None
    refreshed = await kakao.refresh_access_token(
        rt, settings.kakao_rest_api_key, settings.kakao_client_secret
    )
    if "access_token" in refreshed:
        kakao_store.set_kakao_token(
            member["kakao_id"],
            refreshed["access_token"],
            refreshed.get("refresh_token") or rt,
            refreshed.get("expires_in"),
        )
        member["kakao_access_token"] = refreshed["access_token"]
        return refreshed["access_token"]
    return None


async def _create(member: dict[str, Any], *, content: str, due_date: str,
                  alarm_time: str | None = None) -> str | None:
    """할 일 생성(만료 시 refresh 재시도). 성공 시 task_id, 실패 시 None."""
    tok = member.get("kakao_access_token")
    if not tok:
        return None
    try:
        res = await kakao_calendar.create_task(
            tok, content=content, due_date=due_date, alarm_time=alarm_time
        )
        tid = _task_id(res)
        if not tid:
            new = await _refresh(member)
            if new:
                res = await kakao_calendar.create_task(
                    new, content=content, due_date=due_date, alarm_time=alarm_time
                )
                tid = _task_id(res)
        return tid
    except Exception:  # noqa: BLE001 — 알림 보강은 실패해도 흐름 유지
        log.warning("kakao create_task failed", exc_info=True)
        return None


async def _delete(member: dict[str, Any], task_id: str) -> None:
    """할 일 삭제(만료 시 refresh 재시도). 실패해도 조용히 넘어간다."""
    tok = member.get("kakao_access_token")
    if not tok:
        return
    try:
        res = await kakao_calendar.delete_task(tok, task_id)
        if isinstance(res, dict) and res.get("code") in (-401, 401):
            new = await _refresh(member)
            if new:
                await kakao_calendar.delete_task(new, task_id)
    except Exception:  # noqa: BLE001
        log.warning("kakao delete_task failed", exc_info=True)


# ─────────────────────────── 체크인 ───────────────────────────
async def sync_checkin(room_id: int, day: Any, *, alarm_time: str = "2100") -> None:
    """밤 체크인 발송 시: 멤버별 '오늘 체크인' 할 일 생성 + 링크 기록."""
    try:
        due = _date_due(day)
    except Exception:  # noqa: BLE001
        due = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for m in kakao_store.list_members_with_tokens(room_id):
        tid = await _create(m, content="✅ 오늘 체크인", due_date=due, alarm_time=alarm_time)
        if tid:
            storage.record_kakao_task_link(room_id, "checkin", str(day), m["id"], tid)


async def clear_checkin(room_id: int, day: Any, *, user_ids: list[int] | None = None) -> None:
    """체크인 처리(apply) 시: 해당 '체크인' 할 일 삭제."""
    members = {m["id"]: m for m in kakao_store.list_members_with_tokens(room_id)}
    for link in storage.list_kakao_task_links(room_id=room_id, kind="checkin", ref_id=str(day)):
        if user_ids and link["user_id"] not in user_ids:
            continue
        m = members.get(link["user_id"])
        if m:
            await _delete(m, link["kakao_task_id"])
        storage.delete_kakao_task_link(link["id"])


# ─────────────────────────── 폼 / 투표 ───────────────────────────
async def sync_form(room_id: int, form_id: int, title: str, *,
                    due_date: str | None = None, alarm_time: str = "1000") -> None:
    """폼/투표 발송 시: 멤버별 '응답하기' 할 일 생성 + 링크 기록."""
    if not due_date:
        due_date = (datetime.now(KST) + timedelta(days=1)).astimezone(
            timezone.utc
        ).isoformat().replace("+00:00", "Z")
    content = f"🗳️ 응답하기 · {title}"[:100]
    for m in kakao_store.list_members_with_tokens(room_id):
        tid = await _create(m, content=content, due_date=due_date, alarm_time=alarm_time)
        if tid:
            storage.record_kakao_task_link(room_id, "form", str(form_id), m["id"], tid)


async def clear_form(room_id: int, form_id: int, *, user_id: int | None = None) -> None:
    """폼 응답/마감 시: 해당(또는 특정 유저) '응답하기' 할 일 삭제."""
    members = {m["id"]: m for m in kakao_store.list_members_with_tokens(room_id)}
    for link in storage.list_kakao_task_links(room_id=room_id, kind="form", ref_id=str(form_id)):
        if user_id and link["user_id"] != user_id:
            continue
        m = members.get(link["user_id"])
        if m:
            await _delete(m, link["kakao_task_id"])
        storage.delete_kakao_task_link(link["id"])
