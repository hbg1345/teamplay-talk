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

from . import kakao, kakao_store, storage
from .config import settings

_POLL_INTERVAL = 30  # 초
_KST = timezone(timedelta(hours=9))


async def _send_kakao(user_id: int, message: str) -> None:
    """user_id의 저장된 카카오 토큰으로 발송 (401이면 refresh 후 1회 재시도)."""
    user = storage.get_user(user_id)
    if user is None or not user.get("kakao_access_token"):
        return
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
            await kakao.send_to_me(refreshed["access_token"], message)


async def process_closed_form(form_id: int) -> None:
    """폼을 마감 처리하고 생성자에게 nudge. (claim으로 1회만)"""
    claimed = storage.claim_form_for_nudge(form_id)
    if claimed is None or claimed.get("creator_user_id") is None:
        return
    msg = (
        f"📋 '{claimed['title']}' 폼이 마감됐어요.\n"
        f'팀플톡에서 "결과 정리해서 팀에 보내줘" 라고 하면 AI가 집계해 알려드려요.'
    )
    await _send_kakao(claimed["creator_user_id"], msg)


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
        for member in roadmap["by_member"]:
            message = _member_digest_message(room["name"], member, include_done=False)
            if message is None:
                continue
            token_member = members_by_token.get(member["member_id"])
            if token_member is None:
                continue
            if not storage.claim_task_digest(room["id"], member["member_id"], digest_date):
                continue
            await kakao_store.send_with_refresh(token_member, message)


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
        except Exception as e:  # noqa: BLE001
            print(f"[scheduler] error: {e}", flush=True)
        time.sleep(_POLL_INTERVAL)


def start_scheduler() -> None:
    """백그라운드 마감 감지 + 삭제 유예 만료 청소 스케줄러를 시작한다."""
    threading.Thread(target=_scheduler_loop, daemon=True, name="form-scheduler").start()
    print("[scheduler] form-close and room-purge watcher started", flush=True)
