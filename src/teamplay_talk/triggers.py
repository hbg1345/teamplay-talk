"""폼 마감 트리거 — 마감(시간/전원) 감지 후 드라이버(생성자)에게 nudge.

서버는 LLM을 돌리지 않는다(키 없음). 마감을 감지해 **생성자에게만** 카카오로
"확인하세요"를 찌르고, 실제 분석·발송은 드라이버가 클라이언트 AI를 열어서 한다.

마감 경로 2가지 → 둘 다 ``process_closed_form`` (claim으로 중복 방지):
- 시간 마감: 백그라운드 스케줄러(데몬 스레드)가 주기적으로 감지
- 전원 응답: 응답 저장 시(submit_form) 즉시 감지
(수동 close_poll은 nudge 안 함 — 닫는 사람이 이미 보고 있으므로)
"""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from . import kakao, kakao_store, storage, task_sync
from .config import settings

_POLL_INTERVAL = 30  # 초
_KST = timezone(timedelta(hours=9))
_LOG_ONCE_KEYS: set[str] = set()


def _log(message: str) -> None:
    print(f"[scheduler] {message}", flush=True)


def _log_once(key: str, message: str) -> None:
    if key in _LOG_ONCE_KEYS:
        return
    _LOG_ONCE_KEYS.add(key)
    _log(message)


async def _send_kakao(user_id: int, message: str) -> int | None:
    """user_id의 저장된 카카오 토큰으로 발송 (401이면 refresh 후 1회 재시도)."""
    user = storage.get_user(user_id)
    if user is None or not user.get("kakao_access_token"):
        return None
    status, _ = await kakao.send_to_me(user["kakao_access_token"], message)
    if status == 401 and user.get("kakao_refresh_token"):
        refreshed = await kakao.refresh_access_token(
            user["kakao_refresh_token"],
            settings.kakao_rest_api_key,
            settings.kakao_client_secret,
        )
        if "access_token" in refreshed:
            kakao_store.set_kakao_token(
                user["kakao_id"],
                refreshed["access_token"],
                refreshed.get("refresh_token") or user["kakao_refresh_token"],
                refreshed.get("expires_in"),
            )
            status, _ = await kakao.send_to_me(refreshed["access_token"], message)
    return status


async def process_closed_form(form_id: int) -> None:
    """폼을 마감 처리하고 생성자에게 nudge. (claim으로 1회만)"""
    claimed = storage.claim_form_for_nudge(form_id)
    if claimed is None or claimed.get("creator_user_id") is None:
        return
    msg = (
        f"📋 '{claimed['title']}' 폼이 마감됐어요.\n"
        f'팀플톡에서 "결과 정리해서 팀에 보내줘" 라고 하면 AI가 집계해 알려드려요.'
    )
    status = await _send_kakao(claimed["creator_user_id"], msg)
    if status == 200:
        try:
            await task_sync.pend_form_review(
                claimed["room_id"],
                form_id,
                claimed["creator_user_id"],
                claimed["title"],
            )
        except Exception:
            pass


async def process_daily_task_digests() -> None:
    """옵션으로 켜는 개인별 로드맵 할일 digest. 기본은 비활성."""
    if not settings.daily_task_digest_enabled:
        return
    now = datetime.now(_KST)
    if now.hour != settings.daily_task_digest_hour_kst:
        return

    from .tools.roadmap import _format, _member_digest_message

    digest_date = now.date()
    for room in storage.list_active_rooms():
        roadmap = _format(storage.get_roadmap(room["id"]))
        members_by_token = {m["id"]: m for m in kakao_store.list_members_with_tokens(room["id"])}
        sent: list[str] = []
        failed: list[str] = []
        missing_token: list[str] = []
        skipped = 0
        already_claimed = 0
        for member in roadmap["by_member"]:
            message = _member_digest_message(room["name"], member, include_done=False)
            if message is None:
                skipped += 1
                continue
            token_member = members_by_token.get(member["member_id"])
            if token_member is None:
                missing_token.append(member["nickname"])
                continue
            if not storage.claim_task_digest(room["id"], member["member_id"], digest_date):
                already_claimed += 1
                continue
            status = await kakao_store.send_with_refresh(token_member, message)
            (sent if status == 200 else failed).append(member["nickname"])
        if sent or failed or missing_token:
            _log(
                "daily_task_digest "
                f"date={digest_date} room={room['id']} sent={len(sent)} "
                f"failed={len(failed)} missing_token={len(missing_token)} "
                f"skipped_no_tasks={skipped} already_claimed={already_claimed}"
            )
        elif skipped or already_claimed:
            _log_once(
                f"digest:{digest_date}:{room['id']}:quiet",
                "daily_task_digest "
                f"date={digest_date} room={room['id']} sent=0 failed=0 "
                f"skipped_no_tasks={skipped} already_claimed={already_claimed}",
            )


async def _send_identified_form(form_id: int, message: str) -> dict[str, Any]:
    """식별 폼의 개인 링크를 각 멤버에게 보낸다."""
    form = storage.get_form(form_id)
    if form is None:
        return {"sent_to": [], "failed": [], "count": 0, "error": "form not found"}
    from .tools.feedback import _form_feed_copy

    base = f"{settings.public_base_url}{storage.form_public_path(form_id)}"
    title, description = _form_feed_copy(form)
    room = storage.get_room(form["room_id"])
    items = [
        ("방", room["name"] if room else str(form["room_id"])),
        ("상태", "진행중" if not form.get("closed") else "마감"),
    ]
    sent: list[str] = []
    failed: list[str] = []
    for recipient in storage.list_form_recipients(form_id):
        url = f"{settings.public_base_url}{storage.form_public_path(form_id, recipient['invite_token'])}"
        status = await kakao_store.send_feed_with_refresh(
            recipient,
            title=title,
            description=description,
            link_url=url,
            button_title="내 링크 열기",
            items=items,
            fallback_text=f"{message.rstrip()}\n{description}\n{url}",
            reminder={"room_id": form["room_id"], "kind": "form", "ref_id": form_id, "track": False},
        )
        (sent if status == 200 else failed).append(recipient["nickname"])
    return {"sent_to": sent, "failed": failed, "count": len(sent)}


async def process_daily_checkins() -> None:
    """옵션으로 켜는 밤 9시 체크인 폼 발송. 기본은 비활성."""
    if not settings.daily_checkin_enabled:
        return
    now = datetime.now(_KST)
    if now.hour != settings.daily_checkin_hour_kst:
        return

    from .tools.daily import create_daily_checkin_form

    checkin_date = now.date()
    for room in storage.list_active_rooms():
        created = create_daily_checkin_form(
            room["id"],
            creator_user_id=room.get("owner_id"),
            checkin_date=checkin_date,
            close_minutes=720,
            skip_existing=True,
        )
        if created.get("ok") and created.get("status") == "created":
            send_result = await _send_identified_form(
                int(created["form_id"]),
                f"[팀플톡] '{created['title']}' 응답 요청",
            )
            _log(
                "daily_checkin "
                f"date={checkin_date} room={room['id']} form={created['form_id']} "
                f"sent={send_result['count']} failed={len(send_result['failed'])}"
            )
        elif created.get("ok"):
            _log_once(
                f"checkin:{checkin_date}:{room['id']}:existing",
                "daily_checkin "
                f"date={checkin_date} room={room['id']} status={created.get('status')} "
                f"form={created.get('form_id')}",
            )
        else:
            _log_once(
                f"checkin:{checkin_date}:{room['id']}:error",
                "daily_checkin "
                f"date={checkin_date} room={room['id']} skipped error={created.get('error')}",
            )


async def process_daily_reports() -> None:
    """옵션으로 켜는 아침 9시 팀 리포트 생성/공지. 기본은 비활성."""
    if not settings.daily_report_enabled:
        return
    now = datetime.now(_KST)
    if now.hour != settings.daily_report_hour_kst:
        return

    from .tools.daily import build_daily_report_for_room, send_daily_report

    report_date = now.date()
    for room in storage.list_active_rooms():
        if not storage.claim_daily_report_send(room["id"], report_date):
            continue
        report = build_daily_report_for_room(
            room["id"],
            report_date=report_date,
            checkin_date=report_date - timedelta(days=1),
            created_by_user_id=room.get("owner_id"),
            apply_checkin=True,
        )
        if report.get("ok"):
            send_result = await send_daily_report(room["id"], report["summary"])
            _log(
                "daily_report "
                f"date={report_date} room={room['id']} report={report['report']['id']} "
                f"sent={send_result['count']} failed={len(send_result['failed'])}"
            )
        else:
            _log(
                "daily_report "
                f"date={report_date} room={room['id']} skipped error={report.get('error')}"
            )


def _scheduler_loop() -> None:
    while True:
        try:
            for f in storage.find_due_forms():
                asyncio.run(process_closed_form(f["id"]))
            for room in storage.find_rooms_to_purge():
                purged = storage.purge_room(room["id"])
                if purged:
                    print(
                        f"[scheduler] purged room {purged['id']} ({purged['name']})",
                        flush=True,
                    )
            asyncio.run(process_daily_task_digests())
            asyncio.run(process_daily_checkins())
            asyncio.run(process_daily_reports())
        except Exception as e:  # noqa: BLE001
            print(f"[scheduler] error: {e}", flush=True)
        time.sleep(_POLL_INTERVAL)


def start_scheduler() -> None:
    """백그라운드 마감 감지 + 삭제 유예 만료 청소 스케줄러를 시작한다."""
    threading.Thread(target=_scheduler_loop, daemon=True, name="form-scheduler").start()
    print("[scheduler] form-close and room-purge watcher started", flush=True)
