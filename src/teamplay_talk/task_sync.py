"""talk_calendar_task 동기화 — 워크플로우 항목(체크인/폼)을 각 멤버의 톡캘린더
'할 일'로 만들고, 완료/처리되면 삭제한다.

설계:
- 전부 **best-effort / non-blocking**. 카카오 호출·필드가 틀려도 예외를 삼키므로
  기존 talk_message 흐름은 절대 안 깨진다. (할 일은 "확실한 네이티브 알림" 보강용)
- 폼/체크인 발송 알림은 기본적으로 일회성 할 일만 만든다. 제출 저장 경로에서
  카카오 할 일을 자동 삭제하지 않아 폼 제출 안정성을 우선한다.
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


def _yyyymmdd(value: Any) -> str | None:
    """date/datetime/ISO → KST 날짜 'yyyyMMdd' (카카오 할 일 due_date 형식)."""
    if value is None:
        return None
    try:
        if isinstance(value, datetime):
            d = (value.astimezone(KST) if value.tzinfo else value).date()
        elif isinstance(value, date):
            d = value
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            d = (dt.astimezone(KST) if dt.tzinfo else dt).date()
    except Exception:  # noqa: BLE001
        return None
    return d.strftime("%Y%m%d")


def _due_in(days: int = 0) -> str:
    """오늘(KST) + days → 'yyyyMMdd'."""
    return (datetime.now(KST).date() + timedelta(days=days)).strftime("%Y%m%d")


def _soon(minutes: int = 2) -> tuple[str, str]:
    """지금(KST)+minutes 를 5분 단위로 올림한 (due 'yyyyMMdd', alarm 'HHMM').

    카카오 톡캘린더 할 일 알림은 **5분 단위**만 허용 → 임의 분(예: 14:37)은 거부됨.
    """
    now = datetime.now(KST)
    t = now + timedelta(minutes=minutes)
    bump = (5 - t.minute % 5) % 5  # 5분 경계면 그대로 사용한다.
    t = (t + timedelta(minutes=bump)).replace(second=0, microsecond=0)
    if t <= now:
        t += timedelta(minutes=5)
    return t.strftime("%Y%m%d"), t.strftime("%H%M")


def _room_name(room_id: int) -> str:
    """방 이름(없으면 '팀플')."""
    try:
        room = storage.get_room(room_id)
        if room and room.get("name"):
            return str(room["name"])
    except Exception:  # noqa: BLE001
        pass
    return "팀플"


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
async def sync_checkin(room_id: int, day: Any) -> None:
    """밤 체크인 발송 시: 멤버별 '오늘 체크인' 할 일 생성(발송 직후 알림) + 링크 기록."""
    due, alarm = _soon(2)
    content = f"✅ [{_room_name(room_id)}] 오늘 체크인"[:100]
    for m in kakao_store.list_members_with_tokens(room_id):
        tid = await _create(m, content=content, due_date=due, alarm_time=alarm)
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
async def sync_form(room_id: int, form_id: int, title: str) -> None:
    """폼/투표 발송 시: 멤버별 '응답하기' 할 일 생성(발송 직후 알림) + 링크 기록."""
    due, alarm = _soon(2)
    content = f"🗳️ [{_room_name(room_id)}] 응답: {title}"[:100]
    for m in kakao_store.list_members_with_tokens(room_id):
        tid = await _create(m, content=content, due_date=due, alarm_time=alarm)
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


async def clear_form_pending(
    form: dict[str, Any] | None = None,
    *,
    form_id: int | None = None,
    user_id: int | None = None,
) -> None:
    """폼/체크인 응답 요청으로 만든 카카오 할 일을 삭제한다.

    일반 폼은 kind=form/ref_id=form_id, 데일리 체크인은
    kind=checkin/ref_id=_checkin_date 로 저장되므로 닫기/응답 경로에서 이
    함수를 쓰면 두 종류를 같은 방식으로 정리할 수 있다.
    """
    if form is None and form_id is not None:
        form = storage.get_form(form_id)
    if form is None:
        return
    room_id = form.get("room_id")
    if not room_id:
        return
    schema = form.get("schema_json") or {}
    if schema.get("_workflow_kind") == "daily_checkin":
        checkin_date = schema.get("_checkin_date")
        if checkin_date is not None:
            await clear_checkin(
                int(room_id),
                checkin_date,
                user_ids=[user_id] if user_id is not None else None,
            )
        return
    target_form_id = form.get("id") or form_id
    if target_form_id is not None:
        await clear_form(int(room_id), int(target_form_id), user_id=user_id)


async def pend_form_review(room_id: int, form_id: int, creator_user_id: int, title: str) -> None:
    """폼 마감 nudge 후 방장에게 '결과 확인' 할 일을 생성한다."""
    member = storage.get_user(creator_user_id)
    if member is None or not member.get("kakao_access_token"):
        return
    due, alarm = _soon(2)
    content = f"📋 [{_room_name(room_id)}] 결과 확인: {title}"[:100]
    await _create(member, content=content, due_date=due, alarm_time=alarm)


async def clear_form_review(room_id: int, form_id: int, *, user_id: int | None = None) -> None:
    """폼 결과를 확인하면 방장의 '결과 확인' 할 일을 삭제한다."""
    members = {m["id"]: m for m in kakao_store.list_members_with_tokens(room_id)}
    if user_id is not None and user_id not in members:
        user = storage.get_user(user_id)
        if user and user.get("kakao_access_token"):
            members[user_id] = user
    for link in storage.list_kakao_task_links(room_id=room_id, kind="form_review", ref_id=str(form_id)):
        if user_id and link["user_id"] != user_id:
            continue
        member = members.get(link["user_id"])
        if member:
            await _delete(member, link["kakao_task_id"])
        storage.delete_kakao_task_link(link["id"])


# ─────────────────────────── 개인 todo ───────────────────────────
async def sync_todos(room_id: int, *, alarm_time: str = "0900") -> None:
    """활성 개인 todo(배정됨·todo/doing)마다 '할 일' 생성. 이미 있으면 skip.

    체크인 발송 시 호출 → 팀원 톡캘린더에 '지금 할 것'만 뜬다. (전체 로드맵 아님)
    """
    try:
        tasks = (storage.get_roadmap(room_id) or {}).get("tasks", [])
    except Exception:  # noqa: BLE001
        return
    existing = {
        (l["ref_id"], l["user_id"])
        for l in storage.list_kakao_task_links(room_id=room_id, kind="todo")
    }
    members = {m["id"]: m for m in kakao_store.list_members_with_tokens(room_id)}
    for t in tasks:
        if (t.get("task_type") or "milestone") != "todo":
            continue
        if t.get("status") not in ("todo", "doing"):
            continue
        uid = t.get("assignee_user_id")
        member = members.get(uid)
        if member is None:
            continue
        if (str(t["id"]), uid) in existing:
            continue
        due = _yyyymmdd(t.get("end_at")) or _due_in(3)
        content = f"📌 [{_room_name(room_id)}] {t['title']}"[:100]
        tid = await _create(member, content=content, due_date=due, alarm_time=alarm_time)
        if tid:
            storage.record_kakao_task_link(room_id, "todo", str(t["id"]), uid, tid)


async def clear_todo(room_id: int, task_id: Any, *, user_id: int | None = None) -> None:
    """todo가 done 되면: 해당 개인 할 일 삭제."""
    members = {m["id"]: m for m in kakao_store.list_members_with_tokens(room_id)}
    for link in storage.list_kakao_task_links(room_id=room_id, kind="todo", ref_id=str(task_id)):
        if user_id and link["user_id"] != user_id:
            continue
        member = members.get(link["user_id"])
        if member is not None:
            await _delete(member, link["kakao_task_id"])
        storage.delete_kakao_task_link(link["id"])


# ─────────────────────────── 회의 ───────────────────────────
async def add_meeting(room_id: int, member: dict[str, Any], title: str, start_at: Any,
                      *, decision_id: Any = None, alarm_time: str = "0900") -> None:
    """회의 확정 시: 멤버별 '회의 참석' 할 일(due=회의시각) 생성."""
    due = _yyyymmdd(start_at)
    if not due:
        return
    tid = await _create(member, content=f"🗓️ [{_room_name(room_id)}] 회의: {title}"[:100], due_date=due, alarm_time=alarm_time)
    if tid:
        storage.record_kakao_task_link(
            room_id, "meeting", str(decision_id or start_at), member["id"], tid
        )


# ─────────────────────────── 공지 ───────────────────────────
async def sync_notice(room_id: int, title: str) -> None:
    """방장 공지(notify_room) 발송 시: 멤버별 '확인' 할 일 생성(발송 직후 알림).

    일회성이라 링크 기록/삭제 추적은 안 한다.
    """
    due, alarm = _soon(2)
    content = f"📢 [{_room_name(room_id)}] {title}"[:100]
    for m in kakao_store.list_members_with_tokens(room_id):
        await _create(m, content=content, due_date=due, alarm_time=alarm)


# ─────────────────────── 중앙 훅(메세지→할일) ───────────────────────
async def pend_from_message(member: dict[str, Any], *, title: str,
                            reminder: dict[str, Any] | None = None) -> None:
    """카톡 메세지 발송 직후 그 멤버에게 '할 일' 자동 생성(중앙 훅).

    send_feed_with_refresh 에서 호출 → 모든 폼·공지·미래 메세지가 자동으로 할 일이 됨.
    reminder={room_id, kind, ref_id} 를 주면 삭제 추적용 링크도 기록(폼/체크인 등).
    없으면(공지 등) 링크 없이 일회성.
    """
    reminder = reminder or {}
    room_id = reminder.get("room_id")
    prefix = f"[{_room_name(room_id)}] " if room_id else ""
    due, alarm = _soon(2)
    kind = reminder.get("kind")
    if kind == "form":
        content = f"🗳️ {prefix}응답: {title}"[:100]
    elif kind == "checkin":
        content = f"✅ {prefix}오늘 체크인"[:100]
    else:
        content = f"📌 {prefix}{title}"[:100]
    tid = await _create(member, content=content, due_date=due, alarm_time=alarm)
    should_track = bool(reminder.get("track", True))
    if tid and should_track and room_id and reminder.get("kind") and reminder.get("ref_id") is not None:
        storage.record_kakao_task_link(
            room_id, reminder["kind"], str(reminder["ref_id"]), member["id"], tid
        )
