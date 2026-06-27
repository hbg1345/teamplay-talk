"""카카오 톡캘린더 일반 일정 CRUD 도구.

호출자의 카카오 access_token(broker가 헤더로 전달, scope ``talk_calendar``)으로
**본인 캘린더**의 일반 일정을 생성/조회/수정/삭제한다.

시간은 **UTC RFC3339**(예: ``2026-07-01T03:00:00Z``). KST는 UTC+9이므로 한국시간
정오(12:00)는 ``03:00:00Z``. ``time_zone`` 기본값 ``Asia/Seoul``.

요구사항(카카오 콘솔): 동의항목 ``talk_calendar`` 활성화 + 톡캘린더 API 사용 권한.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastmcp import FastMCP

from .. import kakao, kakao_calendar, kakao_store, storage
from ..config import settings
from ..identity import bearer_token, resolve_caller

_NEED_AUTH = {
    "ok": False,
    "error": "카카오 인증 정보가 없습니다. PlayMCP에서 카카오 계정 연결(talk_calendar 권한 동의)을 먼저 진행해 주세요.",
}


def _to_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _rfc3339(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _task_window(task: dict[str, Any], default_minutes: int) -> tuple[str, str] | None:
    start = _to_utc(task.get("start_at"))
    end = _to_utc(task.get("end_at"))
    duration = timedelta(minutes=max(5, int(default_minutes or 30)))
    if start is None and end is None:
        return None
    if start is None and end is not None:
        start = end - duration
    if end is None and start is not None:
        end = start + duration
    if start is None or end is None:
        return None
    if end <= start:
        end = start + duration
    return _rfc3339(start), _rfc3339(end)


def register(mcp: FastMCP) -> None:
    """톡캘린더 일정 도메인 도구를 등록한다."""

    @mcp.tool(
        name="calendar_create_room_event",
        annotations={
            "title": "방 멤버 일정 생성",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def calendar_create_room_event(
        title: str,
        start_at: str,
        end_at: str,
        room_id: int | None = None,
        all_day: bool = False,
        description: str | None = None,
        reminders: list[int] | None = None,
        color: str | None = None,
        time_zone: str = "Asia/Seoul",
        rrule: str | None = None,
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        """Creates the same KakaoTalk calendar event for every authenticated room member.

        팀플톡(teamplay-talk) 현재 작업 방의 카카오 인증 완료 멤버 각각의 톡캘린더에
        같은 일반 일정을 생성한다. 회의 시간 조율 후 **팀원 전원 캘린더 등록**이
        필요할 때 사용한다. 각 멤버가 ``talk_calendar`` 권한으로 인증되어 있어야 한다.

        Args:
            title: 일정 제목
            start_at: 시작 시각 (UTC RFC3339, 예: 2026-07-01T03:00:00Z)
            end_at: 종료 시각 (UTC RFC3339)
            room_id: 대상 방 ID (생략 시 현재 작업 방)
            all_day: 종일 일정 여부
            description: 일정 설명
            reminders: 미리 알림(분 단위, 최대 2개 권장)
            color: 일정 색상
            time_zone: 타임존 (기본 Asia/Seoul)
            rrule: 반복 규칙 RFC5545 RRULE
            calendar_id: 대상 캘린더 ID (기본 primary)
        """
        caller = await resolve_caller()
        if caller is None:
            return _NEED_AUTH
        if room_id is None:
            active = storage.get_active_room(caller["id"])
            if active is None:
                return {"ok": False, "error": "현재 작업 방이 없습니다. switch_room으로 방을 선택하세요."}
            room_id = active["id"]
        elif not storage.is_room_member(room_id, caller["id"]):
            return {"ok": False, "error": "이 방의 멤버만 방 캘린더 일정을 만들 수 있습니다."}

        members = kakao_store.list_members_with_tokens(room_id)
        all_members = storage.list_members(room_id)
        token_member_ids = {m["id"] for m in members}
        missing = [
            {"nickname": m["nickname"], "error": "카카오 인증 토큰이 없습니다."}
            for m in all_members
            if m["id"] not in token_member_ids
        ]
        if not members and not missing:
            return {
                "ok": False,
                "error": "방 멤버가 없습니다.",
            }

        created: list[dict[str, str]] = []
        failed: list[dict[str, Any]] = missing
        for member in members:
            res = await kakao_calendar.create_event(
                member["kakao_access_token"],
                title=title,
                start_at=start_at,
                end_at=end_at,
                all_day=all_day,
                description=description,
                reminders=reminders,
                color=color,
                time_zone=time_zone,
                rrule=rrule,
                calendar_id=calendar_id,
            )
            if "event_id" not in res and member.get("kakao_refresh_token"):
                refreshed = await kakao.refresh_access_token(
                    member["kakao_refresh_token"],
                    settings.kakao_rest_api_key,
                    settings.kakao_client_secret,
                )
                if "access_token" in refreshed:
                    kakao_store.set_kakao_token(
                        member["kakao_id"],
                        refreshed["access_token"],
                        refreshed.get("refresh_token") or member["kakao_refresh_token"],
                        refreshed.get("expires_in"),
                    )
                    res = await kakao_calendar.create_event(
                        refreshed["access_token"],
                        title=title,
                        start_at=start_at,
                        end_at=end_at,
                        all_day=all_day,
                        description=description,
                        reminders=reminders,
                        color=color,
                        time_zone=time_zone,
                        rrule=rrule,
                        calendar_id=calendar_id,
                    )
            if "event_id" in res:
                created.append({"nickname": member["nickname"], "event_id": res["event_id"]})
            else:
                failed.append({"nickname": member["nickname"], "error": res})

        recorded_decision = None
        if created:
            row = storage.record_room_decision(
                room_id,
                kind="meeting_time",
                title=title,
                summary=f"{title}: {start_at} ~ {end_at}",
                payload={
                    "title": title,
                    "start_at": start_at,
                    "end_at": end_at,
                    "all_day": all_day,
                    "description": description,
                    "time_zone": time_zone,
                    "calendar_id": calendar_id,
                    "created": created,
                    "failed": failed,
                },
                source="calendar_create_room_event",
            )
            recorded_decision = {
                "id": row["id"],
                "kind": row["kind"],
                "title": row["title"],
                "summary": row["summary"],
            }

        return {
            "ok": bool(created),
            "room_id": room_id,
            "title": title,
            "created": created,
            "failed": failed,
            "created_count": len(created),
            "failed_count": len(failed),
            "recorded_decision": recorded_decision,
            "note": "실패한 멤버는 카카오 talk_calendar 권한이 없거나 토큰이 만료됐을 수 있습니다.",
        }

    @mcp.tool(
        name="calendar_create_task_events",
        annotations={
            "title": "태스크 개인 캘린더 등록",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def calendar_create_task_events(
        room_id: int | None = None,
        task_ids: list[int] | None = None,
        include_done: bool = False,
        default_minutes: int = 30,
        reminders: list[int] | None = None,
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        """Creates personal KakaoTalk calendar events for assigned roadmap tasks.

        팀플톡(teamplay-talk) 로드맵에서 담당자와 날짜(start_at/end_at)가 있는 태스크를
        각 담당자의 톡캘린더에 등록한다. 역할분배 → 로드맵 → 개인 캘린더 연결용이다.

        Args:
            room_id: 대상 방 ID (생략 시 현재 작업 방)
            task_ids: 특정 태스크만 등록할 때 ID 목록
            include_done: 완료 태스크도 등록할지 여부
            default_minutes: start/end 중 하나만 있을 때 사용할 기본 길이
            reminders: 미리 알림(분 단위, 기본 [60])
            calendar_id: 대상 캘린더 ID
        """
        caller = await resolve_caller()
        if caller is None:
            return _NEED_AUTH
        if room_id is None:
            active = storage.get_active_room(caller["id"])
            if active is None:
                return {"ok": False, "error": "현재 작업 방이 없습니다. switch_room으로 방을 선택하세요."}
            room = active
            room_id = active["id"]
        elif not storage.is_room_member(room_id, caller["id"]):
            return {"ok": False, "error": "이 방의 멤버만 태스크 캘린더 등록을 할 수 있습니다."}
        else:
            room = storage.get_room(room_id)
            if room is None:
                return {"ok": False, "error": f"방 {room_id}를 찾을 수 없습니다."}

        selected = set(task_ids or [])
        created: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for task in storage.get_roadmap(room_id)["tasks"]:
            if selected and task["id"] not in selected:
                continue
            if (task.get("task_type") or "milestone") != "todo":
                skipped.append({"task_id": task["id"], "title": task["title"], "reason": "로드맵 milestone은 개인 todo 캘린더 대상이 아님"})
                continue
            if task.get("status") == "done" and not include_done:
                skipped.append({"task_id": task["id"], "title": task["title"], "reason": "완료 태스크"})
                continue
            if not task.get("assignee_user_id"):
                skipped.append({"task_id": task["id"], "title": task["title"], "reason": "담당자 없음"})
                continue
            window = _task_window(task, default_minutes)
            if window is None:
                skipped.append({"task_id": task["id"], "title": task["title"], "reason": "일정 없음"})
                continue

            user = storage.get_user(task["assignee_user_id"])
            if user is None or not user.get("kakao_access_token"):
                failed.append({
                    "task_id": task["id"],
                    "title": task["title"],
                    "nickname": task.get("assignee_nickname"),
                    "error": "담당자의 카카오 인증 토큰이 없습니다.",
                })
                continue

            start_at, end_at = window
            description = "\n".join(
                part for part in [
                    f"팀플톡 방: {room['name']}",
                    f"태스크 ID: {task['id']}",
                    f"담당 역할: {task.get('assignee_role') or task.get('assignee_member_role') or ''}",
                    f"상태: {task.get('status')}",
                    task.get("details") or "",
                ] if part
            )
            res = await kakao_calendar.create_event(
                user["kakao_access_token"],
                title=f"[팀플톡] {task['title']}",
                start_at=start_at,
                end_at=end_at,
                description=description,
                reminders=reminders if reminders is not None else [60],
                time_zone="Asia/Seoul",
                calendar_id=calendar_id,
            )
            if "event_id" not in res and user.get("kakao_refresh_token"):
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
                    res = await kakao_calendar.create_event(
                        refreshed["access_token"],
                        title=f"[팀플톡] {task['title']}",
                        start_at=start_at,
                        end_at=end_at,
                        description=description,
                        reminders=reminders if reminders is not None else [60],
                        time_zone="Asia/Seoul",
                        calendar_id=calendar_id,
                    )

            if "event_id" in res:
                created.append({
                    "task_id": task["id"],
                    "title": task["title"],
                    "nickname": task.get("assignee_nickname"),
                    "event_id": res["event_id"],
                    "start_at": start_at,
                    "end_at": end_at,
                })
            else:
                failed.append({
                    "task_id": task["id"],
                    "title": task["title"],
                    "nickname": task.get("assignee_nickname"),
                    "error": res,
                })

        return {
            "ok": bool(created),
            "room_id": room_id,
            "created": created,
            "failed": failed,
            "skipped": skipped,
            "created_count": len(created),
            "failed_count": len(failed),
            "next": "캘린더 등록 뒤에는 daily_task_digest로 담당자별 할일을 주기적으로 공지하면 좋습니다.",
        }

    @mcp.tool(
        name="calendar_create_event",
        annotations={
            "title": "일정 생성",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,  # 호출마다 새 일정
            "openWorldHint": True,  # 외부(카카오 톡캘린더) 호출
        },
    )
    async def calendar_create_event(
        title: str,
        start_at: str,
        end_at: str,
        all_day: bool = False,
        description: str | None = None,
        reminders: list[int] | None = None,
        color: str | None = None,
        time_zone: str = "Asia/Seoul",
        rrule: str | None = None,
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        """Creates an event in the caller's KakaoTalk calendar via teamplay-talk(팀플톡).

        팀플톡(teamplay-talk)에서 호출자의 카카오 톡캘린더 본인 캘린더에 일반 일정을
        생성한다. 시간은 UTC RFC3339(예: 2026-07-01T03:00:00Z, KST는 UTC+9).

        Args:
            title: 일정 제목 (최대 50자)
            start_at: 시작 시각 (UTC RFC3339, 예: 2026-07-01T03:00:00Z)
            end_at: 종료 시각 (UTC RFC3339)
            all_day: 종일 일정 여부 (기본 False)
            description: 일정 설명 (선택, 최대 5000자)
            reminders: 미리 알림(분 단위, 최대 2개, 5분 간격. 예: [15, 30])
            color: 일정 색상 (예: RED, BLUE 등, 선택)
            time_zone: 타임존 (기본 Asia/Seoul)
            rrule: 반복 규칙 RFC5545 RRULE (예: FREQ=DAILY;UNTIL=20261231T000000Z, 선택)
            calendar_id: 대상 캘린더 ID (기본 primary)
        """
        token = bearer_token()
        if not token:
            return _NEED_AUTH
        res = await kakao_calendar.create_event(
            token, title=title, start_at=start_at, end_at=end_at, all_day=all_day,
            description=description, reminders=reminders, color=color,
            time_zone=time_zone, rrule=rrule, calendar_id=calendar_id,
        )
        if "event_id" not in res:
            return {"ok": False, "error": res}
        return {"ok": True, "event_id": res["event_id"]}

    @mcp.tool(
        name="calendar_list_events",
        annotations={
            "title": "일정 목록 조회",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def calendar_list_events(
        from_at: str | None = None,
        to_at: str | None = None,
        preset: str | None = None,
        calendar_id: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Lists events in the caller's KakaoTalk calendar via teamplay-talk(팀플톡).

        팀플톡(teamplay-talk)에서 호출자의 카카오 톡캘린더 일정 목록을 조회한다.
        기간은 from_at/to_at(UTC RFC3339, to는 from+31일 이내) 또는 preset 중 하나.

        Args:
            from_at: 조회 시작 (UTC RFC3339, 예: 2026-07-01T00:00:00Z)
            to_at: 조회 종료 (UTC RFC3339, from+31일 이내)
            preset: TODAY | THIS_WEEK | THIS_MONTH (from/to 대신 사용)
            calendar_id: 특정 캘린더만 조회 (생략 시 전체)
            limit: 최대 일정 수 (기본 100, 최대 1000)
        """
        token = bearer_token()
        if not token:
            return _NEED_AUTH
        res = await kakao_calendar.list_events(
            token, from_at=from_at, to_at=to_at, preset=preset,
            calendar_id=calendar_id, limit=limit,
        )
        if "events" not in res:
            return {"ok": False, "error": res}
        return {
            "ok": True,
            "count": len(res["events"]),
            "events": res["events"],
            "has_next": res.get("has_next", False),
        }

    @mcp.tool(
        name="calendar_get_event",
        annotations={
            "title": "일정 상세 조회",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def calendar_get_event(event_id: str) -> dict[str, Any]:
        """Reads a single event's detail from the caller's KakaoTalk calendar via teamplay-talk(팀플톡).

        팀플톡(teamplay-talk)에서 event_id로 카카오 톡캘린더 일정 상세를 조회한다.

        Args:
            event_id: 조회할 일정 ID
        """
        token = bearer_token()
        if not token:
            return _NEED_AUTH
        res = await kakao_calendar.get_event(token, event_id)
        if "event" not in res:
            return {"ok": False, "error": res}
        return {"ok": True, "event": res["event"]}

    @mcp.tool(
        name="calendar_update_event",
        annotations={
            "title": "일정 수정",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def calendar_update_event(
        event_id: str,
        title: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
        all_day: bool = False,
        description: str | None = None,
        reminders: list[int] | None = None,
        color: str | None = None,
        time_zone: str = "Asia/Seoul",
        rrule: str | None = None,
        recur_update_type: str | None = None,
        calendar_id: str | None = None,
    ) -> dict[str, Any]:
        """Updates an event in the caller's KakaoTalk calendar via teamplay-talk(팀플톡).

        팀플톡(teamplay-talk)에서 일정을 수정한다(지정한 필드만 변경). 시간을 바꾸려면
        start_at·end_at 를 함께 줘야 한다. 반복 일정이면 recur_update_type 필수.

        Args:
            event_id: 수정할 일정 ID
            title: 새 제목 (선택)
            start_at: 새 시작 시각 (UTC RFC3339, end_at과 함께)
            end_at: 새 종료 시각 (UTC RFC3339, start_at과 함께)
            all_day: 종일 여부 (시간 변경 시 적용)
            description: 새 설명 (선택)
            reminders: 새 알림(분 리스트, 선택)
            color: 새 색상 (선택)
            time_zone: 타임존 (기본 Asia/Seoul)
            rrule: 새 반복 규칙 (선택)
            recur_update_type: 반복 일정 수정 범위 ALL | THIS | THIS_AND_FOLLOWING (반복 일정 필수)
            calendar_id: 캘린더 ID (선택)
        """
        token = bearer_token()
        if not token:
            return _NEED_AUTH
        res = await kakao_calendar.update_event(
            token, event_id, calendar_id=calendar_id, recur_update_type=recur_update_type,
            title=title, start_at=start_at, end_at=end_at, all_day=all_day,
            description=description, reminders=reminders, color=color,
            time_zone=time_zone, rrule=rrule,
        )
        if "event_id" not in res:
            return {"ok": False, "error": res}
        return {"ok": True, "event_id": res["event_id"]}

    @mcp.tool(
        name="calendar_delete_event",
        annotations={
            "title": "일정 삭제",
            "readOnlyHint": False,
            "destructiveHint": True,  # 일정을 삭제한다
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def calendar_delete_event(
        event_id: str, recur_update_type: str | None = None
    ) -> dict[str, Any]:
        """Deletes an event from the caller's KakaoTalk calendar via teamplay-talk(팀플톡).

        팀플톡(teamplay-talk)에서 event_id로 카카오 톡캘린더 일정을 삭제한다.
        반복 일정이면 recur_update_type 필수.

        Args:
            event_id: 삭제할 일정 ID
            recur_update_type: 반복 일정 삭제 범위 ALL | THIS | THIS_AND_FOLLOWING (반복 일정 필수)
        """
        token = bearer_token()
        if not token:
            return _NEED_AUTH
        res = await kakao_calendar.delete_event(
            token, event_id, recur_update_type=recur_update_type
        )
        if "event_id" not in res:
            return {"ok": False, "error": res}
        return {"ok": True, "event_id": res["event_id"]}
