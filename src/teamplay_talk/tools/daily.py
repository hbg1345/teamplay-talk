"""데일리 체크인/리포트 도구.

밤에는 체크인 폼으로 밀린 일/오늘 일/앞으로 예정된 일의 완료 여부만 가볍게 모으고,
아침에는 그 응답과 로드맵 상태를 합쳐 팀 리포트를 만든다. 서버는 LLM을 돌리지 않으므로
자유서술의 깊은 해석은 호출 측 AI가 하되, 체크박스로 받은 task 상태는 구조적으로
반영한다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastmcp import FastMCP

from .. import kakao_store, storage
from .guards import require_form, require_room
from .roadmap import _format as _format_roadmap
from .roadmap import _task_date_bounds
from .roadmap import _task_matches_window

_KST = timezone(timedelta(hours=9))


def _today() -> date:
    return datetime.now(_KST).date()


def _parse_day(value: str | date | None, default: date) -> date:
    if isinstance(value, date):
        return value
    if not value:
        return default
    return datetime.fromisoformat(str(value)).date()


def _task_choice(task: dict[str, Any]) -> dict[str, str]:
    assignee = task.get("assignee") or "담당 미정"
    due = (task.get("end_at") or task.get("start_at") or "일정 미정")
    if isinstance(due, str) and len(due) >= 10:
        due = due[:10]
    return {
        "value": str(task["id"]),
        "text": f"{task['title']} · {assignee} · {due}",
    }


def _unique_choices(tasks: list[dict[str, Any]]) -> list[dict[str, str]]:
    seen: set[int] = set()
    choices: list[dict[str, str]] = []
    for task in tasks:
        tid = int(task["id"])
        if tid in seen:
            continue
        seen.add(tid)
        choices.append(_task_choice(task))
    return choices


def _selected_ids(value: Any) -> list[int]:
    raw = value if isinstance(value, list) else ([value] if value else [])
    out: list[int] = []
    for item in raw:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def _task_map(room_id: int) -> dict[int, dict[str, Any]]:
    roadmap = _format_roadmap(storage.get_roadmap(room_id))
    return {int(t["id"]): t for t in roadmap.get("todo_tasks", [])}


def _find_daily_checkin_form(room_id: int, checkin_date: date) -> dict[str, Any] | None:
    sent = storage.get_daily_checkin_send(room_id, checkin_date)
    if sent and sent.get("form_id"):
        form = storage.get_form(int(sent["form_id"]))
        if form is not None:
            return form
    for form in storage.list_room_forms(room_id):
        schema = form.get("schema_json") or {}
        if (
            schema.get("_workflow_kind") == "daily_checkin"
            and schema.get("_checkin_date") == checkin_date.isoformat()
        ):
            return form
    return None


def create_daily_checkin_form(
    room_id: int,
    *,
    creator_user_id: int | None = None,
    checkin_date: date | None = None,
    close_minutes: int | None = 720,
    skip_existing: bool = True,
) -> dict[str, Any]:
    """동기 helper: daily check-in SurveyJS form을 생성한다."""
    day = checkin_date or _today()
    if skip_existing:
        existing = _find_daily_checkin_form(room_id, day)
        if existing is not None:
            return {
                "ok": True,
                "status": "existing",
                "form_id": existing["id"],
                "title": existing["title"],
                "checkin_date": day.isoformat(),
                "sent": False,
                "required_next_tool": "send_form",
                "send_form_arguments": {"form_id": existing["id"]},
            }

    room = storage.get_room(room_id)
    if room is None:
        return {"ok": False, "error": f"방 {room_id}를 찾을 수 없습니다."}

    roadmap = _format_roadmap(storage.get_roadmap(room_id))
    todo_tasks = [
        task for task in roadmap.get("todo_tasks", [])
        if task.get("status") != "done"
    ]
    today_tasks = [
        task for task in todo_tasks
        if _task_matches_window(task, "today", day, include_done=False)
    ]
    overdue_tasks = [
        task for task in todo_tasks
        if _task_matches_window(task, "overdue", day, include_done=False)
    ]
    future_tasks = _future_task_bucket(todo_tasks, day)
    if not todo_tasks:
        return {
            "ok": False,
            "error": "체크인할 미완료 todo가 없습니다.",
            "next": "먼저 로드맵을 개인별 실행 todo로 나누거나, 현재 배정 상태를 확인하세요.",
            "suggested_next_actions": [
                "현재 로드맵 확인하기",
                "todo가 없으면 개인별 실행 항목 만들기",
                "담당이 비어 있으면 역할·담당 배정 보정하기",
            ],
    }
    today_choices = _unique_choices(today_tasks)
    overdue_choices = _unique_choices(overdue_tasks)
    future_choices = _unique_choices(future_tasks)

    closes_at = None
    if close_minutes:
        closes_at = datetime.now(timezone.utc) + timedelta(minutes=int(close_minutes))

    title = f"데일리 체크인 · {day.isoformat()}"
    schema = {
        "title": title,
        "description": (
            "지금까지 밀린 일 중 처리한 것과 오늘 해야 했던 일 중 끝낸 것을 체크해주세요. "
            "앞으로 예정된 일도 이미 끝냈다면 체크할 수 있습니다. "
            "안 끝낸 오늘 일은 다음 체크인에서 밀린 일로 넘어갑니다."
        ),
        "completeText": "제출",
        "showQuestionNumbers": "off",
        "elements": [
            {
                "type": "checkbox",
                "name": "done_overdue",
                "title": "밀린 일 중 오늘 처리한 것",
                "description": "과거에 했어야 했지만 아직 완료되지 않은 일 중 오늘 끝낸 항목을 체크해주세요. 없으면 비워두세요.",
                "choices": overdue_choices,
                "isRequired": False,
            },
            {
                "type": "checkbox",
                "name": "done_today",
                "title": "오늘 해야 했던 일 중 끝낸 것",
                "description": "오늘 하기로 되어 있던 일 중 완료한 항목을 체크해주세요. 안 끝낸 항목은 내일부터 밀린 일로 잡힙니다.",
                "choices": today_choices,
                "isRequired": False,
            },
            {
                "type": "checkbox",
                "name": "done_future",
                "title": "앞으로 예정된 일 중 미리 끝낸 것",
                "description": "미래 날짜가 잡힌 todo 중 이미 완료한 항목이 있으면 체크해주세요.",
                "choices": future_choices,
                "isRequired": False,
            },
            {
                "type": "comment",
                "name": "daily_note",
                "title": "기타 메모",
                "description": "목록에 없는 완료 내용, 막힌 이유, 일정 변경 요청이 있으면 적어주세요.",
                "isRequired": False,
            },
        ],
        "_workflow_kind": "daily_checkin",
        "_workflow_stage": "daily_checkin_collection",
        "_checkin_date": day.isoformat(),
    }
    form = storage.create_form(
        room_id=room_id,
        title=title,
        description=schema["description"],
        schema_json=schema,
        anonymous=False,
        creator_user_id=creator_user_id,
        closes_at=closes_at,
        close_on_all=True,
    )
    storage.create_invites(form["id"], [m["id"] for m in storage.list_members(room_id)])
    storage.record_daily_checkin_send(room_id, day, form["id"])
    return {
        "ok": True,
        "status": "created",
        "form_id": form["id"],
        "title": title,
        "checkin_date": day.isoformat(),
        "task_choices": len(today_choices) + len(overdue_choices) + len(future_choices),
        "today_task_choices": len(today_choices),
        "overdue_task_choices": len(overdue_choices),
        "future_task_choices": len(future_choices),
        "sent": False,
        "required_next_tool": "send_form",
        "send_form_arguments": {"form_id": form["id"]},
        "do_not_claim_sent_before_send_form": True,
        "next": "팀원에게 개인 체크인 링크를 보낼 차례입니다. 응답이 모이면 완료 상태를 반영하고 아침 팀 리포트로 이어집니다.",
        "suggested_next_actions": [
            "밤 체크인 폼을 팀원에게 발송하기",
            "응답이 모이면 밀린 일·오늘 일·예정 일의 완료 상태 반영하기",
            "팀 전체 상태·남은 밀린 일·메모를 리포트로 저장·공지하기",
        ],
        "user_prompt_examples": [
            "이 체크인 폼 팀원들에게 보내줘",
            "응답이 모이면 완료 상태 반영해줘",
            "오늘 팀 리포트 만들어서 공지해줘",
        ],
        "chat_response_hint": (
            "내부 도구명은 말하지 말고, "
            "'이 체크인 폼을 팀원들에게 보내드릴까요?'처럼 자연어로 안내하세요."
        ),
    }


def apply_daily_checkin_to_tasks(form_id: int, *, dry_run: bool = True) -> dict[str, Any]:
    """체크인 응답의 checkbox를 task 상태 변경 제안/적용으로 변환한다."""
    form = storage.get_form(form_id)
    if form is None:
        return {"ok": False, "error": "존재하지 않는 폼입니다."}
    schema = form.get("schema_json") or {}
    if schema.get("_workflow_kind") != "daily_checkin":
        return {"ok": False, "error": "daily_checkin 폼이 아닙니다."}

    results = storage.get_results(form_id)
    if results is None:
        return {"ok": False, "error": "폼 결과를 읽을 수 없습니다."}
    tasks = _task_map(form["room_id"])
    responses = results.get("responses", [])
    desired: dict[int, str] = {}
    blockers: list[dict[str, Any]] = []
    tomorrow_focus: list[dict[str, Any]] = []
    notes: list[dict[str, str]] = []

    for response in responses:
        nickname = response.get("nickname") or "익명"
        answers = response.get("answers") or {}
        for task_id in _selected_ids(answers.get("worked_on")):
            if task_id in tasks and desired.get(task_id) != "done":
                desired[task_id] = "doing"
        done_ids = (
            set(_selected_ids(answers.get("done_overdue")))
            | set(_selected_ids(answers.get("done_today")))
            | set(_selected_ids(answers.get("done_future")))
        )
        for task_id in sorted(done_ids):
            if task_id in tasks:
                desired[task_id] = "done"
        for task_id in _selected_ids(answers.get("delayed")):
            if task_id in tasks and task_id not in done_ids:
                blockers.append({
                    "member": nickname,
                    "task_id": task_id,
                    "task_title": tasks[task_id]["title"],
                    "reason": answers.get("daily_note") or answers.get("blockers") or "지연/막힘으로 체크됨",
                })
        for task_id in _selected_ids(answers.get("tomorrow_focus")):
            if task_id in tasks:
                tomorrow_focus.append({
                    "member": nickname,
                    "task_id": task_id,
                    "task_title": tasks[task_id]["title"],
                })
        for key in ("daily_note", "other_done", "blockers", "tomorrow_note"):
            text = str(answers.get(key) or "").strip()
            if text:
                notes.append({"member": nickname, "field": key, "text": text})

    proposed: list[dict[str, Any]] = []
    applied: list[dict[str, Any]] = []
    for task_id, new_status in sorted(desired.items()):
        task = tasks[task_id]
        current = task.get("status")
        row = {
            "task_id": task_id,
            "title": task["title"],
            "from": current,
            "to": new_status,
            "assignee": task.get("assignee"),
        }
        if current != new_status:
            proposed.append(row)
            if not dry_run:
                updated = storage.update_task(task_id, form["room_id"], status=new_status)
                if updated is not None:
                    applied.append(row)

    return {
        "ok": True,
        "form_id": form_id,
        "room_id": form["room_id"],
        "checkin_date": schema.get("_checkin_date"),
        "dry_run": dry_run,
        "response_count": results.get("total_responses", 0),
        "proposed_updates": proposed,
        "applied_updates": applied,
        "blockers": blockers,
        "tomorrow_focus": tomorrow_focus,
        "notes": notes,
        "next": (
            "지금은 미리보기(변경안)입니다. 내용을 확인한 뒤 실제로 반영하세요. "
            "반영 후 아침 팀 리포트를 만들 수 있습니다."
            if dry_run else
            "체크인 응답을 todo 상태에 반영했습니다. 이제 팀 리포트를 만들 수 있습니다."
        ),
        "suggested_next_actions": [
            "변경안을 확인하고 실제로 반영하기",
            "지연·막힌 점이 있으면 해당 todo에 메모하거나 별도로 의견 수집하기",
            "팀 전체 상태와 개인별 오늘 할일 리포트 만들기",
        ],
    }


def _task_bucket(tasks: list[dict[str, Any]], window: str, today: date) -> list[dict[str, Any]]:
    return [
        task for task in tasks
        if _task_matches_window(task, window, today, include_done=False)
    ]


def _future_task_bucket(tasks: list[dict[str, Any]], today: date) -> list[dict[str, Any]]:
    future: list[dict[str, Any]] = []
    for task in tasks:
        if task.get("status") == "done":
            continue
        start_day, end_day = _task_date_bounds(task)
        if start_day is None or end_day is None:
            continue
        if start_day > today:
            future.append(task)
    return sorted(
        future,
        key=lambda task: (
            _task_date_bounds(task)[0] or date.max,
            int(task.get("id") or 0),
        ),
    )


def _task_date_label(task: dict[str, Any]) -> str:
    start_day, end_day = _task_date_bounds(task)
    target = end_day or start_day
    return target.isoformat() if target else "일정 미정"


def _report_summary(
    room_name: str,
    report_date: date,
    payload: dict[str, Any],
) -> str:
    progress = payload["progress"]
    counts = payload["status_counts"]
    lines = [
        f"📊 데일리 리포트 · {room_name} · {report_date.isoformat()}",
        f"전체 진행: {progress['done']}/{progress['total']} 완료 ({progress['percent']}%)",
        f"상태: 진행중 {counts['doing']} · 대기 {counts['todo']} · 기한초과 {counts['overdue']}",
        "",
        "오늘/밀린 일",
    ]
    any_current = False
    for member in payload["by_member"]:
        tasks = (member.get("overdue_tasks") or []) + (member.get("today_tasks") or [])
        if not tasks:
            continue
        any_current = True
        titles = ", ".join(t["title"] for t in tasks[:3])
        more = f" 외 {len(tasks) - 3}개" if len(tasks) > 3 else ""
        lines.append(f"- {member['nickname']}: {titles}{more}")
    if not any_current:
        lines.append("- 밀린 일이나 오늘 날짜에 걸린 미완료 todo가 없습니다.")

    any_future = False
    lines.append("")
    lines.append("앞으로 예정된 일")
    for member in payload["by_member"]:
        tasks = member.get("future_tasks") or []
        if not tasks:
            continue
        any_future = True
        titles = ", ".join(f"{_task_date_label(t)} {t['title']}" for t in tasks[:3])
        more = f" 외 {len(tasks) - 3}개" if len(tasks) > 3 else ""
        lines.append(f"- {member['nickname']}: {titles}{more}")
    if not any_future:
        lines.append("- 앞으로 예정된 미완료 todo가 없습니다.")

    blockers = payload.get("blockers") or []
    lines.append("")
    lines.append("막힌 점")
    if blockers:
        for item in blockers[:5]:
            lines.append(f"- {item['member']}: {item['task_title']} · {item.get('reason') or '내용 없음'}")
    else:
        lines.append("- 체크인 기준으로 등록된 막힌 점이 없습니다.")

    notes = payload.get("notes") or []
    if notes:
        lines.append("")
        lines.append("기타 메모")
        for item in notes[:5]:
            lines.append(f"- {item['member']}: {item['text']}")

    decisions = payload.get("latest_decisions") or []
    if decisions:
        lines.append("")
        lines.append("최근 결정")
        for decision in decisions[:3]:
            lines.append(f"- {decision['title']}: {decision['summary']}")

    lines.extend([
        "",
        "다음: 밀린 항목은 일정이나 담당을 조정하고, 오늘/예정 할 일은 개인별로 다시 공지할 수 있습니다.",
    ])
    return "\n".join(lines)


def build_daily_report_for_room(
    room_id: int,
    *,
    report_date: date | None = None,
    checkin_date: date | None = None,
    checkin_form_id: int | None = None,
    created_by_user_id: int | None = None,
    apply_checkin: bool = False,
) -> dict[str, Any]:
    """동기 helper: 리포트를 만들고 daily_reports에 저장한다."""
    room = storage.get_room(room_id)
    if room is None:
        return {"ok": False, "error": f"방 {room_id}를 찾을 수 없습니다."}
    day = report_date or _today()
    check_day = checkin_date or (day - timedelta(days=1))
    form = storage.get_form(checkin_form_id) if checkin_form_id else _find_daily_checkin_form(room_id, check_day)
    if form is not None and int(form["room_id"]) != int(room_id):
        return {"ok": False, "error": "지정한 체크인 폼이 이 방에 속하지 않습니다."}
    applied = None
    if form is not None and apply_checkin:
        applied = apply_daily_checkin_to_tasks(int(form["id"]), dry_run=False)

    roadmap = _format_roadmap(storage.get_roadmap(room_id))
    todo_tasks = roadmap.get("todo_tasks", [])
    done = sum(1 for task in todo_tasks if task.get("status") == "done")
    doing = sum(1 for task in todo_tasks if task.get("status") == "doing")
    todo = sum(1 for task in todo_tasks if task.get("status") == "todo")
    overdue = _task_bucket(todo_tasks, "overdue", day)
    due_today = _task_bucket(todo_tasks, "today", day)
    future = _future_task_bucket(todo_tasks, day)
    percent = round((done / len(todo_tasks) * 100), 1) if todo_tasks else 0

    checkin_result = storage.get_results(int(form["id"])) if form is not None else None
    checkin_apply_preview = (
        apply_daily_checkin_to_tasks(int(form["id"]), dry_run=True)
        if form is not None and not apply_checkin else applied
    )
    blockers = (checkin_apply_preview or {}).get("blockers", [])
    notes = (checkin_apply_preview or {}).get("notes", [])
    tomorrow_focus = (checkin_apply_preview or {}).get("tomorrow_focus", [])

    by_member: list[dict[str, Any]] = []
    for member in roadmap.get("by_member", []):
        tasks = member.get("tasks", [])
        by_member.append({
            "member_id": member["member_id"],
            "nickname": member["nickname"],
            "role": member.get("role"),
            "progress": member.get("progress"),
            "today_tasks": _task_bucket(tasks, "today", day),
            "overdue_tasks": _task_bucket(tasks, "overdue", day),
            "future_tasks": _future_task_bucket(tasks, day),
            "week_tasks": _task_bucket(tasks, "week", day),
        })

    latest_decisions = [
        {
            "id": row["id"],
            "kind": row["kind"],
            "title": row["title"],
            "summary": row["summary"],
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        }
        for row in storage.list_room_decisions(room_id, limit=5)
    ]
    payload = {
        "report_date": day.isoformat(),
        "checkin_date": check_day.isoformat(),
        "checkin_form_id": form["id"] if form is not None else None,
        "checkin_response_count": (checkin_result or {}).get("total_responses", 0),
        "applied_checkin": applied,
        "progress": {"done": done, "total": len(todo_tasks), "percent": percent},
        "status_counts": {
            "todo": todo,
            "doing": doing,
            "done": done,
            "overdue": len(overdue),
            "due_today": len(due_today),
            "future": len(future),
        },
        "by_member": by_member,
        "overdue_tasks": overdue,
        "due_today_tasks": due_today,
        "future_tasks": future,
        "blockers": blockers,
        "notes": notes,
        "tomorrow_focus": tomorrow_focus,
        "latest_decisions": latest_decisions,
    }
    title = f"데일리 리포트 · {day.isoformat()}"
    summary = _report_summary(room["name"], day, payload)
    report = storage.upsert_daily_report(
        room_id,
        report_date=day,
        title=title,
        summary=summary,
        payload=payload,
        created_by_user_id=created_by_user_id,
    )
    return {
        "ok": True,
        "room_id": room_id,
        "room": room["name"],
        "report": report,
        "summary": summary,
        "payload": payload,
        "next": "필요하면 팀에 공지하거나, 대시보드에서 리포트를 확인하세요.",
        "suggested_next_actions": [
            "메모·막힌 점이 있으면 담당자나 도와줄 사람에게 공지하기",
            "밀린 태스크는 일정·상태 조정하기",
            "오늘 할 일은 개인별로 카카오 공지하기",
            "다음 체크인은 밤에 발송하기",
        ],
    }


async def send_daily_report(room_id: int, message: str) -> dict[str, Any]:
    from ..config import settings
    from ..dashboard_web import create_dashboard_token

    room = storage.get_room(room_id)
    sent: list[str] = []
    failed: list[str] = []
    for member in kakao_store.list_members_with_tokens(room_id):
        token = create_dashboard_token(room_id, member["id"])
        link = f"{settings.public_base_url}/dashboard/rooms/{room_id}?token={token}"
        first_line = next((line.strip() for line in message.splitlines() if line.strip()), "팀 상태를 확인하세요.")
        status = await kakao_store.send_feed_with_refresh(
            member,
            title=f"데일리 리포트 · {room['name'] if room else room_id}",
            description=first_line,
            link_url=link,
            button_title="리포트 보기",
            items=[("방", room["name"] if room else str(room_id)), ("보기", "대시보드")],
            fallback_text=f"{message}\n\n{link}",
        )
        (sent if status == 200 else failed).append(member["nickname"])
    return {"sent_to": sent, "failed": failed, "count": len(sent)}


def register(mcp: FastMCP) -> None:
    """데일리 운영 루프 도구를 등록한다."""

    @mcp.tool(
        name="create_daily_checkin",
        annotations={
            "title": "데일리 체크인 폼 생성",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def create_daily_checkin(
        room_id: int | None = None,
        checkin_date: str | None = None,
        close_minutes: int | None = 720,
        skip_existing: bool = True,
    ) -> dict[str, Any]:
        """Creates a daily check-in form for roadmap todo progress in teamplay-talk(팀플톡).

        밤 9시 루프용 폼을 만든다. 팀원은 과거 todo 중 오늘 처리한 것,
        오늘 해야 했던 일 중 끝낸 것, 앞으로 예정됐지만 미리 끝낸 것을 체크하고,
        설명이 필요한 내용은 기타 메모에 적는다.
        생성 후 발송은 send_form으로 한다.

        Args:
            room_id: 대상 방. 생략 시 현재 작업 방
            checkin_date: 체크인 기준일 YYYY-MM-DD. 생략 시 오늘(KST)
            close_minutes: 자동 마감까지 분. 기본 12시간
            skip_existing: 같은 날짜 체크인 폼이 있으면 재사용
        """
        caller, room, error = await require_room(room_id)
        if error:
            return error
        try:
            day = _parse_day(checkin_date, _today())
        except ValueError:
            return {"ok": False, "error": "checkin_date는 YYYY-MM-DD 형식이어야 합니다."}
        return create_daily_checkin_form(
            room["id"],
            creator_user_id=caller["id"],
            checkin_date=day,
            close_minutes=close_minutes,
            skip_existing=skip_existing,
        )

    @mcp.tool(
        name="apply_daily_checkin",
        annotations={
            "title": "체크인 응답을 할일에 반영",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def apply_daily_checkin(
        form_id: int,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Applies daily check-in responses to roadmap todo statuses.

        체크박스 응답을 읽어 done_overdue/done_today/done_future 항목을 done으로 바꾼다.
        안 끝난 오늘 일은 다음 날부터 overdue로 잡혀 다음 체크인의 밀린 일 목록에 오른다.
        기본 dry_run=true라 먼저 변경안을 보여준다.

        Args:
            form_id: create_daily_checkin이 만든 폼 ID
            dry_run: true면 변경 제안만, false면 실제 update_task 반영
        """
        _caller, _form, error = await require_form(form_id)
        if error:
            return error
        return apply_daily_checkin_to_tasks(form_id, dry_run=dry_run)

    @mcp.tool(
        name="daily_report",
        annotations={
            "title": "데일리 팀 리포트",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def daily_report(
        room_id: int | None = None,
        report_date: str | None = None,
        checkin_date: str | None = None,
        checkin_form_id: int | None = None,
        apply_checkin: bool = True,
        publish: bool = False,
    ) -> dict[str, Any]:
        """Creates a daily team report from roadmap, check-in responses, and decisions.

        아침 9시 루프용 리포트다. 기본은 오늘 리포트를 만들고, 전날 체크인 폼을 찾아
        완료 상태, 남은 밀린 일, 기타 메모를 반영한 뒤 저장한다. publish=true면 팀원에게 카카오로 공지한다.

        Args:
            room_id: 대상 방. 생략 시 현재 작업 방
            report_date: 리포트 날짜 YYYY-MM-DD. 생략 시 오늘(KST)
            checkin_date: 참고할 체크인 날짜. 생략 시 report_date 전날
            checkin_form_id: 특정 체크인 폼을 직접 지정
            apply_checkin: 체크인 응답의 완료 상태와 기타 메모를 todo/report에 반영할지
            publish: 팀원에게 카카오톡 공지까지 보낼지
        """
        caller, room, error = await require_room(room_id)
        if error:
            return error
        try:
            day = _parse_day(report_date, _today())
            check_day = _parse_day(checkin_date, day - timedelta(days=1))
        except ValueError:
            return {"ok": False, "error": "report_date/checkin_date는 YYYY-MM-DD 형식이어야 합니다."}
        result = build_daily_report_for_room(
            room["id"],
            report_date=day,
            checkin_date=check_day,
            checkin_form_id=checkin_form_id,
            created_by_user_id=caller["id"],
            apply_checkin=apply_checkin,
        )
        if not result.get("ok") or not publish:
            return result
        publish_result = await send_daily_report(room["id"], result["summary"])
        result.update({
            "published": bool(publish_result["sent_to"]),
            **publish_result,
            "chat_response_hint": "리포트를 저장했습니다. 공지도 함께 했다면 실제 발송 결과(published·sent_to)를 확인해 공지 성공 여부를 말하세요.",
        })
        return result
