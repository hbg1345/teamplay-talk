"""로드맵 도메인 도구 — 프로젝트 타임라인(태스크 그래프).

로드맵은 **방(현재 작업 방)의 태스크 그래프**다. 태스크(노드)들이 의존 엣지
(선행→후행)로 연결돼 프로젝트 전체 타임라인을 이룬다. 각 태스크엔 세부사항,
담당(팀원 또는 역할), 일정(start/end), 상태가 들어간다.

주제 분석은 호출 측 AI가 수행한다: AI가 주제를 보고 태스크/엣지를 생성해
``build_roadmap`` 으로 넘기면 서버는 저장한다(서버엔 LLM 없음).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import kakao_store, storage
from ..identity import resolve_caller
from .guards import require_room

_KST = timezone(timedelta(hours=9))

_NEED_AUTH = {
    "ok": False,
    "error": "카카오 인증 정보가 없습니다. PlayMCP에서 카카오 계정 연결을 먼저 진행해 주세요.",
}
_NO_ROOM = {
    "ok": False,
    "error": "현재 작업 중인 방이 없습니다. 방을 만들거나 참여(switch_room)한 뒤 다시 시도하세요.",
}


class TodoDraft(BaseModel):
    title: str = Field(description="실행 가능한 구체 todo 제목. 1~2일 안에 끝낼 수 있는 단위 권장.")
    details: str | None = Field(default=None, description="완료 기준, 산출물, 참고 맥락")
    assignee: str | None = Field(default=None, description="담당 팀원 닉네임 또는 확정된 역할명")
    parent_task_id: int | None = Field(default=None, description="상위 로드맵 milestone 태스크 ID")
    parent_title: str | None = Field(default=None, description="parent_task_id를 모르면 상위 milestone 제목")
    start_at: str | None = Field(default=None, description="시작 시각 UTC RFC3339")
    end_at: str | None = Field(default=None, description="마감 시각 UTC RFC3339")
    status: Literal["todo", "doing", "done"] = Field(default="todo", description="진행 상태")


def _iso(dt: Any) -> str | None:
    return dt.isoformat() if dt is not None and hasattr(dt, "isoformat") else dt


def _compact_text(value: str) -> str:
    return "".join(ch for ch in value.strip().lower() if ch.isalnum())


def _task_payload(t: dict[str, Any]) -> dict[str, Any]:
    assignee = t.get("assignee_nickname") or t.get("assignee_role")
    return {
        "id": t["id"],
        "title": t["title"],
        "details": t.get("details"),
        "assignee": assignee,
        "assignee_user_id": t.get("assignee_user_id"),
        "assignee_role": t.get("assignee_role"),
        "assignee_member_role": t.get("assignee_member_role"),
        "status": t["status"],
        "task_type": t.get("task_type") or "milestone",
        "parent_task_id": t.get("parent_task_id"),
        "parent_title": t.get("parent_title"),
        "start_at": _iso(t.get("start_at")),
        "end_at": _iso(t.get("end_at")),
    }


def _task_due_label(task: dict[str, Any]) -> str:
    end_at = task.get("end_at")
    start_at = task.get("start_at")
    if end_at:
        return f"마감 {end_at}"
    if start_at:
        return f"시작 {start_at}"
    return "일정 미정"


def _parse_task_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_KST)


def _parse_schedule_date(value: str | None) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    today = datetime.now(_KST).date()
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    m = re.search(r"(?:(\d{4})\s*[./-]\s*)?(\d{1,2})\s*[./월]\s*(\d{1,2})", text)
    if not m:
        return None
    year = int(m.group(1) or today.year)
    month = int(m.group(2))
    day = int(m.group(3))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _day_start_utc(day: date) -> str:
    return datetime(day.year, day.month, day.day, 9, 0, tzinfo=_KST).astimezone(timezone.utc).isoformat()


def _day_end_utc(day: date) -> str:
    return datetime(day.year, day.month, day.day, 18, 0, tzinfo=_KST).astimezone(timezone.utc).isoformat()


def _milestone_weight(task: dict[str, Any]) -> int:
    text = f"{task.get('title') or ''} {task.get('details') or ''}"
    weight = 1
    if any(k in text for k in ["연구", "조사", "분석", "기획", "레시피"]):
        weight += 1
    if any(k in text for k in ["제작", "개발", "구현", "시제품", "프로토타입", "생산"]):
        weight += 2
    if any(k in text for k in ["피드백", "개선", "테스트", "검증"]):
        weight += 1
    if any(k in text for k in ["최종", "시현", "발표", "제출", "마무리"]):
        weight += 1
    return weight


def _allocate_milestone_days(milestones: list[dict[str, Any]], total_days: int) -> list[int]:
    if not milestones:
        return []
    durations = [1 for _ in milestones]
    if total_days <= len(milestones):
        return durations
    remaining = total_days - len(milestones)
    weights = [_milestone_weight(task) for task in milestones]
    order = sorted(range(len(milestones)), key=lambda idx: (-weights[idx], idx))
    while remaining > 0:
        for idx in order:
            if remaining <= 0:
                break
            durations[idx] += 1
            remaining -= 1
    return durations


def _split_task_days(parent: dict[str, Any], count: int) -> list[tuple[str | None, str | None]]:
    if count <= 0:
        return []
    start_day, end_day = _task_date_bounds(parent)
    if start_day is None or end_day is None:
        return [(None, None) for _ in range(count)]
    total_days = max(1, (end_day - start_day).days + 1)
    out: list[tuple[str | None, str | None]] = []
    for idx in range(count):
        start_offset = int(idx * total_days / count)
        end_offset = int((idx + 1) * total_days / count) - 1
        item_start = min(start_day + timedelta(days=start_offset), end_day)
        item_end = min(start_day + timedelta(days=max(start_offset, end_offset)), end_day)
        out.append((_day_start_utc(item_start), _day_end_utc(item_end)))
    return out


def _role_match_score(role: str, text: str) -> int:
    score = 0
    role_norm = _compact_text(role)
    text_norm = _compact_text(text)
    if role_norm and role_norm in text_norm:
        score += 6
    role_tokens = {token for token in re.split(r"[·,\s/]+", role) if token}
    stopwords = {"역할", "담당", "담당자", "관리", "운영", "준비", "작업", "팀", "프로젝트"}
    for token in role_tokens:
        if len(token) >= 2 and token not in stopwords and token in text:
            score += 2
    return score


def _assignee_for_auto_todo(roadmap: dict[str, Any], milestone: dict[str, Any], title: str) -> str | None:
    if milestone.get("assignee_nickname"):
        return str(milestone["assignee_nickname"])
    if milestone.get("assignee_role"):
        return str(milestone["assignee_role"])
    members = roadmap.get("members", [])
    text = f"{milestone.get('title') or ''} {milestone.get('details') or ''} {title}"
    best: tuple[int, str | None] = (0, None)
    for member in members:
        role = str(member.get("role") or "")
        if not role:
            continue
        score = _role_match_score(role, text)
        if score > best[0]:
            best = (score, str(member.get("nickname") or ""))
    if best[1]:
        return best[1]
    if len(members) == 1:
        return str(members[0].get("nickname") or "") or None
    return None


def _auto_todo_specs(milestone: dict[str, Any]) -> list[tuple[str, str]]:
    title = str(milestone.get("title") or "")
    details = str(milestone.get("details") or "")
    text = f"{title} {details}"
    is_presentation = any(k in text for k in ["책", "발표", "자료", "슬라이드", "대본", "리허설", "질의", "토론", "분석", "평가"])
    is_food = any(k in text for k in ["빵", "소보로", "레시피", "재료", "식품", "조리", "시제품", "포장", "생산", "양산", "제조"])
    if any(k in title for k in ["역할", "분배"]):
        return [
            ("필요 역할 후보 정리", "로드맵을 보고 필요한 책임영역과 역할 수를 정리합니다."),
            ("역할 선호도 수집", "팀원들이 원하는 역할과 어려운 역할을 조사합니다."),
            ("역할 확정 및 공지", "선호도와 업무량을 보고 역할을 확정해 팀에 공유합니다."),
        ]
    if is_presentation and any(k in title for k in ["책", "분석", "조사", "연구", "선정"]):
        return [
            ("발표 대상과 핵심 질문 정리", "다룰 책/범위와 발표에서 답할 핵심 질문을 정합니다."),
            ("핵심 내용·인용구 정리", "중요 개념, 인용구, 해석 포인트를 발표에 쓸 수 있게 정리합니다."),
            ("발표 논지 초안 만들기", "조사 내용을 바탕으로 발표의 주장과 흐름을 초안으로 만듭니다."),
        ]
    if is_presentation and any(k in title for k in ["자료", "슬라이드", "대본", "콘텐츠"]):
        return [
            ("발표 구조 잡기", "도입-핵심 내용-마무리 흐름과 각 장표의 역할을 정합니다."),
            ("슬라이드 초안 제작", "핵심 문장, 이미지/도표, 인용구를 넣어 발표 자료 초안을 만듭니다."),
            ("발표 대본·전환 멘트 작성", "팀원이 말할 순서와 장표 사이 연결 멘트를 작성합니다."),
        ]
    if is_presentation and any(k in title for k in ["리허설", "피드백", "평가"]):
        if "발표" in title and "평가" in title:
            return [
                ("발표 진행", "정해진 순서와 시간에 맞춰 발표를 진행합니다."),
                ("질의응답 대응", "발표 후 질문에 답하고 보충 설명이 필요한 부분을 정리합니다."),
                ("발표 후 회고 정리", "잘된 점, 아쉬운 점, 다음에 개선할 점을 팀과 정리합니다."),
            ]
        return [
            ("발표 리허설 진행", "정해진 시간 안에 발표를 끝낼 수 있는지 실제로 맞춰봅니다."),
            ("피드백 항목 정리", "내용 이해도, 장표 가독성, 발표 흐름에 대한 피드백을 모읍니다."),
            ("수정사항 반영", "피드백을 바탕으로 자료와 대본을 보완합니다."),
        ]
    if is_presentation and any(k in title for k in ["최종", "발표", "제출", "마무리"]):
        return [
            ("최종 발표 흐름 점검", "발표 순서, 시간 배분, 담당 파트를 마지막으로 확인합니다."),
            ("슬라이드·대본 최종 수정", "오탈자, 인용 출처, 빠진 장표와 말할 내용을 점검합니다."),
            ("예상 질문 준비", "발표 후 나올 수 있는 질문과 답변 방향을 정리합니다."),
        ]
    if any(k in title for k in ["최종", "시현", "발표", "제출", "마무리"]):
        return [
            ("최종 흐름 정리", "최종 결과를 보여줄 순서, 설명 포인트, 담당 순서를 정리합니다."),
            ("최종 결과물 점검", "결과물, 자료, 제출물, 기록물을 빠짐없이 확인합니다."),
            ("리허설 및 보완", "최종 공유 전 리허설을 진행하고 부족한 부분을 보완합니다."),
        ]
    if any(k in title for k in ["피드백", "개선", "테스트", "검증"]):
        return [
            ("피드백 수집", "팀원 또는 검토 대상에게 결과물에 대한 피드백을 받습니다."),
            ("개선안 정리", "반영할 개선점을 우선순위로 정리합니다."),
            ("보완 작업 반영", "개선안을 반영해 결과물과 진행 계획을 갱신합니다."),
        ]
    if is_food and any(k in title for k in ["시제품", "제작", "반죽", "토핑", "굽"]):
        return [
            ("반죽과 소보로 토핑 준비", "확정 레시피에 맞춰 반죽과 토핑을 준비합니다."),
            ("1차 시제품 제작", "굽기 시간과 온도를 기록하며 시제품을 만듭니다."),
            ("제작 결과 기록", "맛, 식감, 외형, 문제점을 사진/메모로 남깁니다."),
        ]
    if is_food and any(k in title for k in ["레시피", "연구", "조사"]):
        return [
            ("레시피 후보 조사", "참고 레시피 2~3개를 비교하고 재료·공정 차이를 정리합니다."),
            ("선정 기준 정리", "맛, 식감, 난이도, 준비물 기준으로 선택 기준을 정리합니다."),
            ("최종 레시피 초안 확정", "시제품 제작에 사용할 배합과 공정을 1안으로 확정합니다."),
        ]
    if is_food and any(k in title for k in ["재료", "구매", "준비"]):
        return [
            ("재료·도구 목록 작성", "필요 재료, 수량, 도구, 구매처 후보를 체크리스트로 정리합니다."),
            ("재료 구매 및 보관", "재료를 구매하고 시제품 제작 전까지 보관 상태를 확인합니다."),
        ]
    if any(k in text for k in ["최종", "시현", "발표", "제출", "마무리"]):
        return [
            ("최종 흐름 정리", "최종 결과를 보여줄 순서, 설명 포인트, 담당 순서를 정리합니다."),
            ("최종 결과물 점검", "결과물, 자료, 제출물, 기록물을 빠짐없이 확인합니다."),
            ("리허설 및 보완", "최종 공유 전 리허설을 진행하고 부족한 부분을 보완합니다."),
        ]
    if any(k in text for k in ["피드백", "개선", "테스트", "검증"]):
        return [
            ("피드백 수집", "팀원 또는 검토 대상에게 결과물에 대한 피드백을 받습니다."),
            ("개선안 정리", "반영할 개선점을 우선순위로 정리합니다."),
            ("보완 작업 반영", "개선안을 반영해 결과물과 진행 계획을 갱신합니다."),
        ]
    if is_food and any(k in text for k in ["시제품", "제작", "반죽", "토핑", "굽"]):
        return [
            ("반죽과 소보로 토핑 준비", "확정 레시피에 맞춰 반죽과 토핑을 준비합니다."),
            ("1차 시제품 제작", "굽기 시간과 온도를 기록하며 시제품을 만듭니다."),
            ("제작 결과 기록", "맛, 식감, 외형, 문제점을 사진/메모로 남깁니다."),
        ]
    if is_food and any(k in text for k in ["레시피", "연구", "조사"]):
        return [
            ("레시피 후보 조사", "참고 레시피 2~3개를 비교하고 재료·공정 차이를 정리합니다."),
            ("선정 기준 정리", "맛, 식감, 난이도, 준비물 기준으로 선택 기준을 정리합니다."),
            ("최종 레시피 초안 확정", "시제품 제작에 사용할 배합과 공정을 1안으로 확정합니다."),
        ]
    if is_food and any(k in text for k in ["재료", "구매", "준비"]):
        return [
            ("재료·도구 목록 작성", "필요 재료, 수량, 도구, 구매처 후보를 체크리스트로 정리합니다."),
            ("재료 구매 및 보관", "재료를 구매하고 시제품 제작 전까지 보관 상태를 확인합니다."),
        ]
    return [
        (f"{title} 완료 기준 정리", "이 단계가 끝났다고 판단할 산출물과 체크 기준을 정리합니다."),
        (f"{title} 실행", "정리한 기준에 맞춰 핵심 작업을 수행합니다."),
        (f"{title} 결과 공유", "결과물, 이슈, 다음 단계로 넘길 내용을 팀에 공유합니다."),
    ]


def _auto_generate_todos(roadmap: dict[str, Any]) -> list[TodoDraft]:
    tasks = roadmap.get("tasks", [])
    milestones = [task for task in tasks if (task.get("task_type") or "milestone") == "milestone"]
    existing_by_parent: dict[int, int] = {}
    for task in tasks:
        if (task.get("task_type") or "milestone") == "todo" and task.get("parent_task_id") is not None:
            existing_by_parent[int(task["parent_task_id"])] = existing_by_parent.get(int(task["parent_task_id"]), 0) + 1
    generated: list[TodoDraft] = []
    for milestone in milestones:
        parent_id = int(milestone["id"])
        if existing_by_parent.get(parent_id):
            continue
        specs = _auto_todo_specs(milestone)
        spans = _split_task_days(milestone, len(specs))
        for (title, details), (start_at, end_at) in zip(specs, spans, strict=False):
            generated.append(TodoDraft(
                title=title,
                details=details,
                assignee=_assignee_for_auto_todo(roadmap, milestone, title),
                parent_task_id=parent_id,
                start_at=start_at,
                end_at=end_at,
            ))
    return generated


def _task_date_bounds(task: dict[str, Any]) -> tuple[Any | None, Any | None]:
    start = _parse_task_dt(task.get("start_at"))
    end = _parse_task_dt(task.get("end_at"))
    start_day = start.date() if start else None
    end_day = end.date() if end else None
    if start_day is None and end_day is not None:
        start_day = end_day
    if end_day is None and start_day is not None:
        end_day = start_day
    return start_day, end_day


def _task_matches_window(
    task: dict[str, Any],
    window: str,
    today: Any,
    *,
    include_done: bool,
) -> bool:
    if not include_done and task.get("status") == "done":
        return False
    if window == "all":
        return True
    start_day, end_day = _task_date_bounds(task)
    if window == "no_date":
        return start_day is None and end_day is None
    if start_day is None or end_day is None:
        return False
    if window == "today":
        return start_day <= today <= end_day
    if window == "week":
        week_end = today + timedelta(days=7)
        return start_day <= week_end and end_day >= today
    if window == "overdue":
        return end_day < today and task.get("status") != "done"
    if window == "upcoming":
        return end_day >= today and task.get("status") != "done"
    return True


def _member_task_buckets(roadmap: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    buckets = {
        m["id"]: {
            "member_id": m["id"],
            "nickname": m["nickname"],
            "role": m.get("role"),
            "tasks": [],
            "progress": {"done": 0, "total": 0},
        }
        for m in roadmap.get("members", [])
    }
    unassigned: list[dict[str, Any]] = []
    for task in roadmap.get("tasks", []):
        payload = _task_payload(task)
        if payload.get("task_type") != "todo":
            continue
        member_id = task.get("assignee_user_id")
        if member_id in buckets:
            buckets[member_id]["tasks"].append(payload)
            buckets[member_id]["progress"]["total"] += 1
            if task.get("status") == "done":
                buckets[member_id]["progress"]["done"] += 1
        else:
            unassigned.append(payload)
    return list(buckets.values()), unassigned


def _is_project_role(role: Any) -> bool:
    text = str(role or "").strip()
    if not text:
        return False
    return text not in {"방장", "팀장", "관리자", "owner", "Owner", "admin", "Admin"}


def _resolve_parent_task_id(
    roadmap: dict[str, Any],
    *,
    parent_task_id: int | None,
    parent_title: str | None,
) -> int | None:
    tasks = roadmap.get("tasks", [])
    milestone_ids = {
        int(t["id"]) for t in tasks
        if (t.get("task_type") or "milestone") == "milestone"
    }
    if parent_task_id in milestone_ids:
        return parent_task_id
    title = (parent_title or "").strip().lower()
    if not title:
        return None
    exact = [
        t for t in tasks
        if (t.get("task_type") or "milestone") == "milestone"
        and str(t.get("title") or "").strip().lower() == title
    ]
    if len(exact) == 1:
        return int(exact[0]["id"])
    fuzzy = [
        t for t in tasks
        if (t.get("task_type") or "milestone") == "milestone"
        and (
            title in str(t.get("title") or "").strip().lower()
            or str(t.get("title") or "").strip().lower() in title
        )
    ]
    if len(fuzzy) == 1:
        return int(fuzzy[0]["id"])
    return None


def _member_digest_message(room_name: str, member: dict[str, Any], *, include_done: bool = False) -> str | None:
    tasks = [
        t for t in member.get("tasks", [])
        if include_done or t.get("status") != "done"
    ]
    if not tasks:
        return None
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    lines = [
        f"📌 팀플톡 오늘 할 일 · {room_name}",
        f"{member['nickname']}님 담당 태스크 ({today})",
        "",
    ]
    for t in tasks:
        status = {"todo": "대기", "doing": "진행중", "done": "완료"}.get(t.get("status"), t.get("status"))
        lines.append(f"· {t['title']} [{status}]")
        lines.append(f"  - {_task_due_label(t)}")
        if t.get("details"):
            lines.append(f"  - {t['details']}")
    lines.extend([
        "",
        "완료했으면 팀플톡에서 이 할일을 완료로 바꿔달라고 말하면 돼요.",
    ])
    return "\n".join(lines)


def _format(roadmap: dict[str, Any]) -> dict[str, Any]:
    """저장 계층 결과를 출력용으로 정리(담당자·개인별 할일·진척률)."""
    tasks = roadmap["tasks"]
    todo_rows = [t for t in tasks if (t.get("task_type") or "milestone") == "todo"]
    milestone_rows = [t for t in tasks if (t.get("task_type") or "milestone") == "milestone"]
    done = sum(1 for t in todo_rows if t["status"] == "done")
    formatted_tasks = [_task_payload(t) for t in tasks]
    formatted_todos = [_task_payload(t) for t in todo_rows]
    formatted_milestones = [_task_payload(t) for t in milestone_rows]
    todos_by_parent: dict[int, list[dict[str, Any]]] = {}
    for todo in formatted_todos:
        parent_id = todo.get("parent_task_id")
        if parent_id is not None:
            todos_by_parent.setdefault(int(parent_id), []).append(todo)
    milestones = [
        {**m, "todos": todos_by_parent.get(int(m["id"]), [])}
        for m in formatted_milestones
    ]
    milestone_titles = [
        str(m.get("title", "")).strip()
        for m in formatted_milestones
        if str(m.get("title", "")).strip()
    ]
    member_buckets = {
        m["id"]: {
            "member_id": m["id"],
            "nickname": m["nickname"],
            "role": m.get("role"),
            "tasks": [],
            "progress": {"done": 0, "total": 0},
        }
        for m in roadmap.get("members", [])
    }
    unassigned_tasks: list[dict[str, Any]] = []
    calendar_candidates: list[dict[str, Any]] = []
    role_only_tasks: list[dict[str, Any]] = []
    for t, payload in zip(tasks, formatted_tasks, strict=False):
        if payload.get("task_type") != "todo":
            continue
        member_id = t.get("assignee_user_id")
        if member_id in member_buckets:
            member_buckets[member_id]["tasks"].append(payload)
            member_buckets[member_id]["progress"]["total"] += 1
            if t["status"] == "done":
                member_buckets[member_id]["progress"]["done"] += 1
            if payload.get("start_at") or payload.get("end_at"):
                calendar_candidates.append({
                    "member_id": member_id,
                    "nickname": t.get("assignee_nickname"),
                    "task_id": t["id"],
                    "title": t["title"],
                    "start_at": payload.get("start_at"),
                    "end_at": payload.get("end_at"),
                })
        else:
            unassigned_tasks.append(payload)
            if payload.get("assignee_role"):
                role_only_tasks.append(payload)

    by_member = [
        bucket for bucket in member_buckets.values()
        if bucket["tasks"] or bucket.get("role")
    ]
    needs_todo_decomposition = bool(milestone_rows) and not bool(todo_rows)

    # 로드맵 이후 다음 행동 안내는 상태에 따라 갈린다.
    # 로드맵 직후에는 역할분배와 로드맵 의견수렴/수정을 먼저 드러내야
    # PlayMCP가 곧장 todo/캘린더로 건너뛰지 않는다.
    has_roles = any(_is_project_role(m.get("role")) for m in roadmap.get("members", []))
    if not has_roles:
        workflow_state = "roadmap_created_roles_missing"
        roadmap_next = (
            "로드맵 단계가 잡혔고 아직 확정된 프로젝트 역할은 없습니다. 다음은 이 로드맵이 맞는지 "
            "팀원 의견을 모으거나, 이 마일스톤을 기준으로 역할을 나누는 흐름이 자연스럽습니다."
        )
        roadmap_suggestions = [
            "로드맵이 맞는지 팀원 의견을 모아 수정·보완하기",
            "이 로드맵 기준으로 역할 책임 범위 나누기",
            "역할 선호도 조사를 팀원에게 보내기",
            "진행 흐름을 대시보드에서 확인하기",
        ]
        workflow_order_guidance = (
            "일반적으로는 로드맵을 먼저 만들고, 그 마일스톤을 보고 역할을 나눈 뒤, "
            "역할별 실행 todo로 분해합니다. 아직 프로젝트 역할이 없으므로 '현재 역할 기준'이나 "
            "'현재 역할 점검'이라고 말하지 마세요."
        )
        chat_hint = (
            "채팅 응답에서는 생성/조회된 마일스톤 제목을 먼저 bullet로 보여주세요. "
            "방장/팀장 같은 운영 역할만 있으면 프로젝트 역할은 아직 없는 상태입니다. "
            "todo를 바로 제안하지 말고, '이 로드맵 기준으로 역할을 나눌까요?'를 우선 제안하세요. "
            "보조 선택지로 로드맵 의견수렴/수정을 함께 보여주세요."
        )
    else:
        workflow_state = "roadmap_created_roles_present"
        roadmap_next = (
            "로드맵 단계가 잡혔고 역할 정보도 있습니다. 먼저 로드맵에 대한 팀 의견을 모아 수정할지, "
            "기존 역할이 이 마일스톤에 맞는지 점검한 뒤 각 단계의 실행 todo를 쪼갤지 정하면 좋습니다."
        )
        roadmap_suggestions = [
            "로드맵이 맞는지 팀원 의견을 모아 수정·보완하기",
            "현재 역할이 이 마일스톤에 맞는지 점검하고 필요하면 역할분배 다시 하기",
            "개별 실행 태스크를 정하는 의견 폼 만들기",
            (
                "일정이 잡힌 태스크를 전원 카카오 캘린더에 등록하기"
                if calendar_candidates
                else "태스크에 마감·일정을 정해 캘린더 등록 후보 만들기"
            ),
            "단계별 실행 todo가 아직 없으면 역할별·멤버별로 todo 쪼개기",
            "담당자별 오늘 할일을 개인 공지하기",
            "진행 상황이 바뀌면 태스크 상태 갱신하기",
            "진행 흐름을 대시보드에서 확인하기",
        ]
        workflow_order_guidance = (
            "역할분배를 먼저 해둔 팀이라면 기존 역할을 로드맵에 맞게 점검한 뒤 바로 실행 todo로 "
            "분해할 수 있습니다. 다만 역할이 마일스톤과 어긋나면 역할분배를 다시 제안하세요."
        )
        chat_hint = (
            "채팅 응답에서는 생성/조회된 마일스톤 제목을 먼저 bullet로 보여주세요. "
            "역할이 이미 있으므로 '기존 역할 점검'과 '역할 기준 실행 todo 분해'를 제안할 수 있습니다. "
            "그래도 로드맵 의견수렴/수정 선택지는 함께 보여주세요."
        )
    return {
        "tasks": formatted_tasks,
        "milestones": milestones,
        "milestone_titles": milestone_titles,
        "todo_tasks": formatted_todos,
        "edges": [
            {"from": e["from_task_id"], "to": e["to_task_id"]} for e in roadmap["edges"]
        ],
        "progress": {"done": done, "total": len(todo_rows)},
        "task_layer_summary": {
            "milestones": len(milestone_rows),
            "todos": len(todo_rows),
            "assigned_todos": len(todo_rows) - len(unassigned_tasks),
            "role_only_todos": len(role_only_tasks),
            "unassigned_todos": len(unassigned_tasks),
            "needs_todo_decomposition": needs_todo_decomposition,
            "needs_role_assignment": bool(role_only_tasks),
        },
        "by_member": by_member,
        "unassigned_tasks": unassigned_tasks,
        "role_only_tasks": role_only_tasks,
        "calendar_candidates": calendar_candidates,
        "workflow_state": workflow_state,
        "next": roadmap_next,
        "suggested_next_actions": roadmap_suggestions,
        "workflow_order_guidance": workflow_order_guidance,
        "roadmap_response_guidance": (
            "채팅 응답에서는 먼저 생성/조회된 마일스톤 제목을 bullet로 보여주세요. "
            "그 다음 로드맵 의견수렴/수정, 마일스톤 기반 역할분배, 역할 확정 후 todo 분해 순서로 제안하세요. "
            "역할이 아직 없으면 '현재 역할 기준'이라는 표현을 쓰지 마세요."
        ),
        "role_assignment_guidance": (
            "로드맵 단계명은 역할이 아닙니다. 역할을 나눌 때는 여러 태스크를 책임지는 "
            "책임 범위를 만들어야 합니다. 고정 역할명 사전에서 고르지 말고, 최종 산출물·반복 작업·의존관계에서 "
            "이 프로젝트만의 역할명을 직접 도출하세요. 역할별 difficulty는 작업량·불확실성·의존도·마감 리스크로 매기고, "
            "병목 역할은 slots를 2 이상으로 잡으세요."
        ),
        "chat_response_hint": chat_hint,
        "user_prompt_examples": [
            "이 로드맵 괜찮은지 팀원 의견 받아줘",
            "이 마일스톤 기준으로 역할분배 해줘",
            "역할별 실행 todo로 쪼개줘",
        ],
    }


def register(mcp: FastMCP) -> None:
    """로드맵 도메인 도구를 등록한다."""

    @mcp.tool(
        name="build_roadmap",
        annotations={
            "title": "로드맵 생성",
            "readOnlyHint": False,
            "destructiveHint": True,  # 기존 로드맵을 교체한다
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def build_roadmap(
        tasks: list[dict[str, Any]],
        edges: list[dict[str, Any]] | None = None,
        topic: str | None = None,
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        """Builds the current room's project roadmap as a task graph in teamplay-talk(팀플톡).

        팀플톡(teamplay-talk) 현재 작업 방의 로드맵(프로젝트 타임라인)을 태스크
        그래프로 생성한다. 기존 로드맵이 있으면 기본적으로 교체하지 않는다.
        전체 교체가 명시적으로 필요할 때만 replace_existing=true를 넘긴다.
        호출 측 AI가 주제를 분석해 태스크와 의존 엣지를 만들어 넘긴다.
        여기서 tasks는 큰 단계/마일스톤이어야 한다. 개인별 실행 todo는 역할 확정 뒤
        decompose_roadmap으로 별도 생성한다.
        시간은 UTC RFC3339(예: 2026-07-01T00:00:00Z).

        Args:
            tasks: 태스크 목록. 각 항목은
                {"key": 임시ID, "title": 제목, "details": 세부(선택),
                 "assignee": 담당 팀원 닉네임 또는 set_roles로 확정된 역할명(선택),
                 "start_at": 시작(선택), "end_at": 종료(선택),
                 "status": "todo"|"doing"|"done"(선택, 기본 todo)}.
                assignee에 역할명을 넣으면 room_members.role을 보고 실제 담당자에 자동 연결한다.
                task_type은 보통 생략한다(기본 milestone).
                key는 edges에서 태스크를 가리키는 데 쓰는 임시 식별자.
            edges: 의존 엣지 목록 [{"from": key, "to": key}] (선행→후행, 선택)
            topic: 로드맵 주제 메모 (선택)
            replace_existing: 기존 로드맵 전체 교체 여부. 기본 false.
        """
        caller = await resolve_caller()
        if caller is None:
            return _NEED_AUTH
        room = storage.get_active_room(caller["id"])
        if room is None:
            return _NO_ROOM
        if not tasks:
            return {"ok": False, "error": "tasks가 비어 있습니다."}
        existing = storage.get_roadmap(room["id"])
        if existing["tasks"] and not replace_existing:
            return {
                "ok": False,
                "error": "이미 로드맵이 있습니다. 새 로드맵 생성은 전체 교체라 기본 실행을 막았습니다.",
                "existing_task_count": len(existing["tasks"]),
                "required_confirmation": "정말 전체 교체하려면 교체를 확정해 다시 시도하세요(기존 로드맵은 사라집니다).",
                "suggested_next_actions": [
                    "기존 로드맵 확인하기",
                    "일부만 수정하기",
                    "새 할일 추가하기",
                    "역할 확정 뒤 담당자만 정리하려면 각 할일의 담당자를 역할명·닉네임으로 수정하기",
                ],
            }
        roadmap = storage.set_roadmap(room["id"], tasks, edges or [])
        formatted = _format(roadmap)
        return {
            "ok": True,
            "room": room["name"],
            "topic": topic,
            "replaced_existing": bool(existing["tasks"]),
            **formatted,
        }

    @mcp.tool(
        name="view_roadmap",
        annotations={
            "title": "로드맵 조회",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def view_roadmap() -> dict[str, Any]:
        """Views the current room's roadmap (task graph + progress) in teamplay-talk(팀플톡).

        팀플톡(teamplay-talk) 현재 작업 방의 로드맵을 조회한다. 태스크(세부·담당·
        일정·상태)와 의존 엣지, 진척률(done/total)을 반환한다.
        """
        caller = await resolve_caller()
        if caller is None:
            return _NEED_AUTH
        room = storage.get_active_room(caller["id"])
        if room is None:
            return _NO_ROOM
        roadmap = storage.get_roadmap(room["id"])
        return {"ok": True, "room": room["name"], **_format(roadmap)}

    @mcp.tool(
        name="add_task",
        annotations={
            "title": "태스크 추가",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,  # 호출마다 새 태스크
            "openWorldHint": False,
        },
    )
    async def add_task(
        title: str,
        details: str | None = None,
        assignee: str | None = None,
        status: str = "todo",
        task_type: Literal["todo", "milestone"] = "todo",
        parent_task_id: int | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
        after_task_ids: list[int] | None = None,
        before_task_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Adds one task to the current room's roadmap in teamplay-talk(팀플톡), optionally linking it.

        팀플톡(teamplay-talk) 현재 작업 방의 로드맵에 태스크 1개를 추가한다.
        기본은 실행 todo(task_type='todo')다. 큰 로드맵 단계는 task_type='milestone'.
        여러 개인 todo 초안은 이 도구를 반복 호출하지 말고 decompose_roadmap을 사용한다.
        after_task_ids/before_task_ids 로 기존 태스크와 의존 엣지를 연결할 수 있다.

        Args:
            title: 태스크 제목
            details: 세부사항 (선택)
            assignee: 담당 (팀원 닉네임 또는 역할, 선택)
            status: 상태 "todo"|"doing"|"done" (기본 todo)
            task_type: todo=실행 할일, milestone=큰 로드맵 단계
            parent_task_id: todo가 속한 상위 milestone ID
            start_at: 시작 시각 UTC RFC3339 (선택)
            end_at: 종료 시각 UTC RFC3339 (선택)
            after_task_ids: 이 태스크의 **선행** 태스크 ID들(그것들 → 이 태스크, 선택)
            before_task_ids: 이 태스크의 **후행** 태스크 ID들(이 태스크 → 그것들, 선택)
        """
        caller = await resolve_caller()
        if caller is None:
            return _NEED_AUTH
        room = storage.get_active_room(caller["id"])
        if room is None:
            return _NO_ROOM
        task = storage.add_task(
            room["id"], title=title, details=details, assignee=assignee,
            status=status, task_type=task_type, parent_task_id=parent_task_id,
            start_at=start_at, end_at=end_at,
            after_ids=after_task_ids, before_ids=before_task_ids,
        )
        return {"ok": True, "task_id": task["id"], "title": task["title"], **_format(storage.get_roadmap(room["id"]))}

    @mcp.tool(
        name="delete_task",
        annotations={
            "title": "태스크 삭제",
            "readOnlyHint": False,
            "destructiveHint": True,  # 태스크와 연결 엣지를 삭제
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def delete_task(task_id: int) -> dict[str, Any]:
        """Deletes one task (and its edges) from the current room's roadmap in teamplay-talk(팀플톡).

        팀플톡(teamplay-talk) 현재 작업 방의 로드맵에서 태스크 1개를 삭제한다.
        연결된 의존 엣지도 함께 사라진다.

        Args:
            task_id: 삭제할 태스크 ID (view_roadmap에서 확인)
        """
        caller = await resolve_caller()
        if caller is None:
            return _NEED_AUTH
        room = storage.get_active_room(caller["id"])
        if room is None:
            return _NO_ROOM
        deleted = storage.delete_task(task_id, room["id"])
        if deleted is None:
            return {"ok": False, "error": "해당 태스크를 찾을 수 없습니다(이 방의 태스크가 아닐 수 있음)."}
        return {"ok": True, "deleted_task_id": deleted, **_format(storage.get_roadmap(room["id"]))}

    @mcp.tool(
        name="update_task",
        annotations={
            "title": "태스크 수정",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def update_task(
        task_id: int,
        title: str | None = None,
        details: str | None = None,
        assignee: str | None = None,
        status: str | None = None,
        task_type: Literal["todo", "milestone"] | None = None,
        parent_task_id: int | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
    ) -> dict[str, Any]:
        """Updates one roadmap task in teamplay-talk(팀플톡) (only given fields change).

        팀플톡(teamplay-talk) 로드맵의 태스크 하나를 수정한다. 상태 변경(진행/완료),
        담당 재지정, 일정 변경 등에 쓴다. 지정한 필드만 바뀐다.

        Args:
            task_id: 수정할 태스크 ID (view_roadmap에서 확인)
            title: 새 제목 (선택)
            details: 새 세부사항 (선택)
            assignee: 새 담당 (팀원 닉네임 또는 역할, 선택)
            status: 새 상태 "todo"|"doing"|"done" (선택)
            task_type: 새 타입 "todo"|"milestone" (선택)
            parent_task_id: 새 상위 milestone ID (선택)
            start_at: 새 시작 시각 UTC RFC3339 (선택)
            end_at: 새 종료 시각 UTC RFC3339 (선택)
        """
        caller = await resolve_caller()
        if caller is None:
            return _NEED_AUTH
        room = storage.get_active_room(caller["id"])
        if room is None:
            return _NO_ROOM
        updated = storage.update_task(
            task_id, room["id"], title=title, details=details, assignee=assignee,
            status=status, task_type=task_type, parent_task_id=parent_task_id,
            start_at=start_at, end_at=end_at,
        )
        if updated is None:
            return {"ok": False, "error": "해당 태스크를 찾을 수 없습니다."}
        return {
            "ok": True,
            "task_id": updated["id"],
            "title": updated["title"],
            "status": updated["status"],
            **_format(storage.get_roadmap(room["id"])),
        }

    @mcp.tool(
        name="schedule_roadmap",
        annotations={
            "title": "로드맵 마일스톤 일정 배치",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def schedule_roadmap(
        final_date: str,
        start_date: str | None = None,
        final_milestone: str | None = None,
        room_id: int | None = None,
    ) -> dict[str, Any]:
        """Schedules existing roadmap milestones by distributing dates up to a final deadline.

        팀플톡(teamplay-talk) 현재 로드맵의 큰 단계(milestone)에 시작/종료 일정을 자동 배치한다.
        "7월 9일 최종 시현이니까 각 로드맵 일정 잡아줘"처럼 최종일이 주어졌을 때 사용한다.
        실행 todo를 생성하는 decompose_roadmap과 다르며, 기존 milestone의 start_at/end_at만 갱신한다.

        Args:
            final_date: 최종 마감일. YYYY-MM-DD 권장. "7월 9일", "7/9"도 현재 연도로 해석.
            start_date: 시작일. 생략하면 오늘(KST).
            final_milestone: 최종 마감과 연결되는 milestone 제목 힌트(선택). 순서는 기존 로드맵 순서를 따른다.
            room_id: 대상 방 (생략 시 현재 작업 방)
        """
        _caller, room, error = await require_room(room_id)
        if error:
            return error
        room_id = room["id"]
        final_day = _parse_schedule_date(final_date)
        if final_day is None:
            return {"ok": False, "error": "final_date를 날짜로 해석할 수 없습니다. 예: 2026-07-09"}
        start_day = _parse_schedule_date(start_date) or datetime.now(_KST).date()
        if start_day > final_day:
            return {
                "ok": False,
                "error": "시작일이 최종일보다 늦습니다.",
                "start_date": start_day.isoformat(),
                "final_date": final_day.isoformat(),
            }
        roadmap = storage.get_roadmap(room_id)
        milestones = [
            task for task in roadmap.get("tasks", [])
            if (task.get("task_type") or "milestone") == "milestone"
        ]
        if not milestones:
            return {
                "ok": False,
                "error": "일정을 배치할 로드맵 마일스톤이 없습니다. 먼저 로드맵을 만들어야 합니다.",
            }
        total_days = (final_day - start_day).days + 1
        durations = _allocate_milestone_days(milestones, total_days)
        scheduled: list[dict[str, Any]] = []
        all_tasks = roadmap.get("tasks", [])
        dated_todos = 0
        cursor = start_day
        for idx, (task, duration) in enumerate(zip(milestones, durations, strict=False)):
            if total_days >= len(milestones):
                end_day = min(cursor + timedelta(days=duration - 1), final_day)
                if idx == len(milestones) - 1:
                    end_day = final_day
                item_start = min(cursor, final_day)
            else:
                # 기간보다 마일스톤이 많으면 뒤쪽 단계들이 같은 날짜에 병렬 배치된다.
                item_start = min(start_day + timedelta(days=idx), final_day)
                end_day = item_start
            storage.update_task(
                int(task["id"]),
                room_id,
                start_at=_day_start_utc(item_start),
                end_at=_day_end_utc(end_day),
            )
            scheduled.append({
                "task_id": task["id"],
                "title": task["title"],
                "start_date": item_start.isoformat(),
                "end_date": end_day.isoformat(),
                "duration_days": (end_day - item_start).days + 1,
            })
            # 이 마일스톤 아래 실행 todo에도 날짜를 물려준다(날짜 없을 때만; 이미 있으면 존중).
            # 데일리 체크인이 날짜 있는 todo 기준으로 돌기 때문에, 마일스톤 일정이 잡히는
            # 순간 자식 todo 전부에 마감일(마일스톤 종료일)을 배정한다.
            mid = int(task["id"])
            ms_start = _day_start_utc(item_start)
            ms_end = _day_end_utc(end_day)
            for child in all_tasks:
                if (child.get("task_type") or "milestone") != "todo":
                    continue
                if int(child.get("parent_task_id") or 0) != mid:
                    continue
                if child.get("end_at"):
                    continue
                storage.update_task(
                    int(child["id"]),
                    room_id,
                    start_at=child.get("start_at") or ms_start,
                    end_at=ms_end,
                )
                dated_todos += 1
            cursor = end_day + timedelta(days=1)
        formatted = _format(storage.get_roadmap(room_id))
        return {
            "ok": True,
            "room_id": room_id,
            "room": room["name"],
            "start_date": start_day.isoformat(),
            "final_date": final_day.isoformat(),
            "final_milestone_hint": final_milestone,
            "scheduled_milestones": scheduled,
            "dated_todos": dated_todos,
            "next": (
                "로드맵 마일스톤 일정이 저장됐습니다. "
                + (
                    f"각 단계 아래 실행 todo {dated_todos}개에 마감일을 물려줬습니다 — 이제 데일리 체크인이 날짜별로 동작합니다. "
                    if dated_todos else ""
                )
                + "다음은 역할분배 또는 단계별 실행 todo 분해로 이어가면 됩니다."
            ),
            "suggested_next_actions": [
                "일정이 괜찮은지 팀장에게 확인하기",
                "마일스톤 기준 역할분배 시작하기",
                "역할이 정해진 뒤 단계별 실행 todo 만들기",
                "날짜가 있는 todo를 캘린더에 등록하기",
            ],
            "chat_response_hint": (
                "각 마일스톤의 날짜를 목록으로 보여주세요. decompose나 todo 생성이 아니라 기존 로드맵 일정 배치가 완료됐다고 말하세요. "
                "todo에 마감일이 물려졌으면 데일리 체크인이 날짜별로 가능해졌다고 덧붙이세요."
            ),
            **formatted,
        }

    @mcp.tool(
        name="decompose_roadmap",
        annotations={
            "title": "로드맵을 개인별 todo로 분해",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def decompose_roadmap(
        todos: list[TodoDraft] | None = None,
        room_id: int | None = None,
    ) -> dict[str, Any]:
        """Adds executable todo items under roadmap milestones in teamplay-talk(팀플톡).

        로드맵의 큰 단계(milestone)를 멤버별 실행 todo로 분해해 저장한다.
        사용자가 "각자 할일 초안 만들어줘", "todo 리스트 짜줘"라고 하면 add_task를
        한 번만 쓰지 말고 이 도구로 여러 개를 한 번에 넣어라.

        AI 분해 규칙:
        - milestone 하나당 보통 2~5개 todo
        - todo는 1~2일 안에 끝낼 수 있는 산출물 단위
        - title은 동사형 실행 항목, details에는 완료 기준
        - assignee는 확정된 역할명 또는 멤버 닉네임
        - 팀원 의견 원문 1개를 그대로 한 줄 태스크로 저장하지 말고, 필요한 하위 작업으로 쪼갠다.

        Args:
            todos: 생성할 실행 todo 목록. 생략하면 현재 로드맵/확정 역할/마일스톤 일정을 바탕으로 서버가 초안을 자동 생성한다.
            room_id: 대상 방 (생략 시 현재 작업 방)
        """
        _caller, room, error = await require_room(room_id)
        if error:
            return error
        room_id = room["id"]

        roadmap = storage.get_roadmap(room_id)
        if not roadmap["tasks"]:
            return {
                "ok": False,
                "error": "먼저 큰 로드맵 단계부터 만들어야 합니다.",
            }
        auto_generated = False
        if not todos:
            todos = _auto_generate_todos(roadmap)
            auto_generated = True
        if not todos:
            formatted = _format(roadmap)
            return {
                "ok": True,
                "room_id": room_id,
                "room": room["name"],
                "created_todos": [],
                "created_count": 0,
                "auto_generated": auto_generated,
                "already_decomposed": True,
                "next": "이미 각 마일스톤 아래 실행 todo가 있습니다. 팀원별 할일을 확인하거나 필요한 todo만 추가·수정하세요.",
                "suggested_next_actions": [
                    "팀원별 할일 확인하기",
                    "누락된 todo만 추가하기",
                    "날짜나 담당자 수정하기",
                    "개인별 할일을 카톡으로 공지하기",
                ],
                "chat_response_hint": "이미 생성된 todo가 있음을 말하고, 팀원별 할일을 확인하자고 제안하세요.",
                **formatted,
            }

        milestone_rows = [
            task for task in roadmap.get("tasks", [])
            if (task.get("task_type") or "milestone") == "milestone"
        ]
        if todos and milestone_rows:
            unlinked = [
                {"title": todo.title, "assignee": todo.assignee}
                for todo in todos
                if not todo.parent_task_id and not todo.parent_title
            ]
            if unlinked and len(milestone_rows) == 1:
                only_parent_id = int(milestone_rows[0]["id"])
                for todo in todos:
                    if not todo.parent_task_id and not todo.parent_title:
                        todo.parent_task_id = only_parent_id
            elif unlinked:
                formatted = _format(roadmap)
                return {
                    "ok": False,
                    "error": "실행 todo가 어느 로드맵 마일스톤 아래 작업인지 빠져 있습니다.",
                    "unlinked_todos": unlinked,
                    "available_milestones": [
                        {"id": task["id"], "title": task["title"]}
                        for task in milestone_rows
                    ],
                    "required_next_tool": "decompose_roadmap",
                    "next": (
                        "각 todo가 어느 로드맵 단계에 속하는지 표시해 다시 저장해야 합니다. "
                        "사용자가 세부 todo를 직접 요구한 것이 아니라면 자동 분해 흐름으로 다시 진행하세요."
                    ),
                    "suggested_next_actions": [
                        "현재 로드맵을 기준으로 todo를 자동 생성하기",
                        "직접 만든 todo에 상위 마일스톤 제목을 붙여 다시 저장하기",
                        "날짜 배치만 필요한 경우 로드맵 일정 배치를 먼저 하기",
                    ],
                    "chat_response_hint": (
                        "사용자에게 세부 todo 목록을 다시 요구하지 마세요. "
                        "현재 마일스톤을 기준으로 parent_title을 채워 다시 호출하거나, "
                        "todos 없이 자동 분해를 호출해 로드맵과 연결된 todo를 만드세요."
                    ),
                    **formatted,
                }

        resolved_todos: list[tuple[TodoDraft, int | None]] = []
        unresolved_parent: list[dict[str, Any]] = []
        for todo in todos:
            parent_id = _resolve_parent_task_id(
                roadmap,
                parent_task_id=todo.parent_task_id,
                parent_title=todo.parent_title,
            )
            if parent_id is None and (todo.parent_task_id or todo.parent_title):
                unresolved_parent.append({
                    "title": todo.title,
                    "parent_task_id": todo.parent_task_id,
                    "parent_title": todo.parent_title,
                })
                continue
            resolved_todos.append((todo, parent_id))
        if unresolved_parent:
            formatted = _format(roadmap)
            return {
                "ok": False,
                "error": "일부 todo의 상위 마일스톤을 찾지 못했습니다.",
                "unresolved_parent": unresolved_parent,
                "available_milestones": [
                    {"id": task["id"], "title": task["title"]}
                    for task in milestone_rows
                ],
                "required_next_tool": "decompose_roadmap",
                "next": "todo가 속한 로드맵 단계 이름을 현재 마일스톤 제목에 맞춰 다시 저장하세요.",
                "suggested_next_actions": [
                    "현재 로드맵 마일스톤 제목에 맞춰 상위 단계 이름 보정하기",
                    "현재 로드맵 기준으로 실행 todo 자동 생성하기",
                    "먼저 로드맵을 조회해 마일스톤 제목 확인하기",
                ],
                "chat_response_hint": (
                    "상위 마일스톤 매칭이 실패했다고 짧게 말하고, 사용자에게 새 todo를 요구하지 말고 "
                    "현재 available_milestones를 기준으로 parent_title을 보정해 다시 호출하세요."
                ),
                **formatted,
            }

        # 부모 마일스톤에 날짜가 있으면 todo가 물려받는다(todo가 자체 날짜를 안 준 경우만).
        # → build/schedule에서 마일스톤 날짜를 먼저 잡아두면 decompose가 자동 배정하므로
        #   나중에 날짜를 다시 유도할 필요가 없다.
        ms_dates = {
            int(t["id"]): (_iso(t.get("start_at")), _iso(t.get("end_at")))
            for t in milestone_rows
        }
        created: list[dict[str, Any]] = []
        for todo, parent_id in resolved_todos:
            inherit_start, inherit_end = (
                ms_dates.get(int(parent_id), (None, None)) if parent_id else (None, None)
            )
            task = storage.add_task(
                room_id,
                title=todo.title,
                details=todo.details,
                assignee=todo.assignee,
                status=todo.status,
                task_type="todo",
                parent_task_id=parent_id,
                start_at=todo.start_at or inherit_start,
                end_at=todo.end_at or inherit_end,
            )
            created.append(_task_payload(task))

        synced = storage.sync_task_assignees_by_roles(room_id)
        formatted = _format(storage.get_roadmap(room_id))
        needs_role_assignment = bool(formatted["task_layer_summary"].get("needs_role_assignment"))
        return {
            "ok": True,
            "room_id": room_id,
            "room": room["name"],
            "created_todos": created,
            "created_count": len(created),
            "auto_generated": auto_generated,
            "synced_todos": synced,
            "unresolved_parent": unresolved_parent,
            "needs_role_assignment": needs_role_assignment,
            "required_next_tool": "set_roles" if needs_role_assignment else "member_tasks",
            "next": (
                ("로드맵·역할·일정을 바탕으로 todo 초안을 자동 생성해 저장했습니다. " if auto_generated else "todo 분해가 저장됐습니다. ")
                + (
                    "다만 일부 todo가 역할명에만 묶여 있어 실제 팀원에게 아직 배정되지 않았습니다. 역할을 확정한 뒤 팀원별 할일을 확인하세요."
                    if needs_role_assignment else
                    "팀원별 이번 주 실행 목록을 확인하고, 필요하면 개인별로 공지하세요."
                )
            ),
            "suggested_next_actions": [
                "역할명에만 묶인 todo가 있으면 역할을 확정하거나 역할명 보정하기",
                "이번 주 팀원별 todo 확인하기",
                "누락·중복이 보이면 할일 조정·삭제하기",
                "마일스톤에 날짜(일정)를 잡으면 실행 todo에도 마감일이 붙어 데일리 체크인이 날짜별로 동작함 — 일정 배치 제안하기(선택)",
                "팀원 의견이 더 필요하면 개별 할일 의견 폼 만들기",
                "확정되면 개인별 또는 팀 전체에 공지하기",
            ],
            "chat_response_hint": (
                "생성된 todo를 팀원/역할별로 요약해서 보여주세요. "
                "auto_generated가 true면 사용자에게 세부 할일을 다시 요구하지 마세요. "
                "각 todo가 어느 마일스톤 아래에 붙었는지도 필요하면 함께 보여주세요. "
                "needs_role_assignment가 true면 실제 담당자 확정을 먼저 안내하고, false면 팀원별 할일 확인/공지로 이어가세요."
            ),
            **formatted,
        }

    @mcp.tool(
        name="member_tasks",
        annotations={
            "title": "멤버별 할일 조회",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def member_tasks(
        member: str | None = None,
        window: Literal["all", "today", "week", "overdue", "upcoming", "no_date"] = "week",
        include_done: bool = False,
        room_id: int | None = None,
    ) -> dict[str, Any]:
        """Shows personal/team tasks from the current room roadmap in teamplay-talk(팀플톡).

        로드맵을 기준으로 멤버별 할일을 조회한다. 역할분배와 로드맵이 연결된 뒤
        "내 이번 주 할일", "전체 overdue", "세원 할일"처럼 확인하는 도구다.

        Args:
            member: 닉네임. 생략하면 호출자 본인, "all"/"전체"면 팀 전체.
            window: all/today/week/overdue/upcoming/no_date
            include_done: 완료 태스크 포함 여부
            room_id: 대상 방 (생략 시 현재 작업 방)
        """
        caller, room, error = await require_room(room_id)
        if error:
            return error
        room_id = room["id"]
        roadmap = storage.get_roadmap(room_id)
        all_members, unassigned = _member_task_buckets(roadmap)
        today = datetime.now(_KST).date()

        selector = (member or "").strip()
        show_all = selector.lower() in {"all", "team"} or selector in {"전체", "팀", "모두"}
        if not selector:
            selector = str(caller.get("nickname") or "")
        if selector in {"나", "내", "me", "my"}:
            selector = str(caller.get("nickname") or "")

        selected: list[dict[str, Any]]
        if show_all:
            selected = all_members
        else:
            needle = selector.lower()
            selected = [
                m for m in all_members
                if m["nickname"].lower() == needle or needle in m["nickname"].lower()
            ]
            if not selected:
                return {
                    "ok": False,
                    "error": f"'{selector}' 멤버를 찾을 수 없습니다. member='all'로 전체를 볼 수 있습니다.",
                    "members": [m["nickname"] for m in all_members],
                }

        filtered_members: list[dict[str, Any]] = []
        for bucket in selected:
            tasks = [
                task for task in bucket["tasks"]
                if _task_matches_window(task, window, today, include_done=include_done)
            ]
            done = sum(1 for task in tasks if task.get("status") == "done")
            filtered_members.append({
                **bucket,
                "tasks": tasks,
                "filtered_progress": {"done": done, "total": len(tasks)},
            })

        filtered_unassigned = [
            task for task in unassigned
            if _task_matches_window(task, window, today, include_done=include_done)
        ] if show_all else []
        total = sum(len(m["tasks"]) for m in filtered_members) + len(filtered_unassigned)
        layer = _format(roadmap)["task_layer_summary"]
        return {
            "ok": True,
            "room_id": room_id,
            "room": room["name"],
            "window": window,
            "today_kst": today.isoformat(),
            "include_done": include_done,
            "member_selector": "all" if show_all else selector,
            "total_tasks": total,
            "task_layer_summary": layer,
            "members": filtered_members,
            "unassigned_tasks": filtered_unassigned,
            "next": (
                "할일을 확인했습니다. 실행 todo가 비어 있으면 로드맵 단계를 "
                "개인별 실행 todo로 먼저 분해하세요."
            ),
            "suggested_next_actions": [
                "todo가 없으면 각 단계 아래 실행 todo를 2~5개씩 만들기",
                "역할명에만 묶인 todo가 있으면 역할을 확정하거나 역할명 보정하기",
                "비어 있는 담당·마감 보정하기",
                "할일 후보가 애매하면 개별 할일 의견 폼으로 팀 의견 모으기",
                "의견이 갈리는 항목은 우선순위·채택 여부 투표로 정하기",
                "담당자에게 개인별 할일 공지하기",
                "날짜 있는 태스크는 담당자 개인 캘린더에 등록하기",
            ],
        }

    @mcp.tool(
        name="daily_task_digest",
        annotations={
            "title": "개인별 할일 공지",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def daily_task_digest(
        room_id: int | None = None,
        include_done: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Sends each roadmap owner a personalized task digest via KakaoTalk.

        팀플톡(teamplay-talk) 로드맵을 사람별로 나누어 각 담당자에게 자기 할일만
        카카오톡으로 보낸다. 역할분배 → 로드맵 생성 뒤 매일/회의 전 확인용으로 쓴다.

        Args:
            room_id: 대상 방 ID (생략 시 현재 작업 방)
            include_done: 완료 태스크도 포함할지 여부
            dry_run: 실제 발송 없이 미리보기만 반환
        """
        caller = await resolve_caller()
        if caller is None:
            return _NEED_AUTH
        if room_id is None:
            room = storage.get_active_room(caller["id"])
            if room is None:
                return _NO_ROOM
            room_id = room["id"]
        elif not storage.is_room_member(room_id, caller["id"]):
            return {"ok": False, "error": "이 방의 멤버만 할일 공지를 보낼 수 있습니다."}
        else:
            room = storage.get_room(room_id)
            if room is None:
                return {"ok": False, "error": f"방 {room_id}를 찾을 수 없습니다."}

        roadmap = _format(storage.get_roadmap(room_id))
        layer = roadmap.get("task_layer_summary") or {}
        members_by_token = {m["id"]: m for m in kakao_store.list_members_with_tokens(room_id)}
        from ..config import settings
        from ..dashboard_web import create_dashboard_token

        previews: list[dict[str, Any]] = []
        sent: list[str] = []
        failed: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for member in roadmap["by_member"]:
            message = _member_digest_message(room["name"], member, include_done=include_done)
            if message is None:
                skipped.append({"nickname": member["nickname"], "reason": "보낼 미완료 태스크가 없습니다."})
                continue
            previews.append({"nickname": member["nickname"], "message": message})
            token_member = members_by_token.get(member["member_id"])
            if token_member is None:
                failed.append({"nickname": member["nickname"], "error": "카카오 인증 토큰이 없습니다."})
                continue
            if dry_run:
                continue
            token = create_dashboard_token(room_id, token_member["id"])
            link = f"{settings.public_base_url}/dashboard/rooms/{room_id}?token={token}"
            status = await kakao_store.send_feed_with_refresh(
                token_member,
                title=f"{member['nickname']}님 할일",
                description="오늘 확인할 개인 todo를 정리했습니다. 전체 목록은 대시보드에서 볼 수 있습니다.",
                link_url=link,
                button_title="내 할일 보기",
                items=[("방", room["name"]), ("미완료", str((member.get("progress") or {}).get("total", 0) - (member.get("progress") or {}).get("done", 0)))],
                fallback_text=f"{message}\n{link}",
            )
            if status == 200:
                sent.append(member["nickname"])
            else:
                failed.append({"nickname": member["nickname"], "error": f"카카오 발송 실패 HTTP {status}"})

        if not sent and not dry_run:
            reason = (
                "역할명으로만 묶인 todo가 있어 실제 팀원에게 아직 배정되지 않았습니다."
                if layer.get("role_only_todos") else
                "보낼 개인별 미완료 todo가 없거나, 담당자의 카카오 인증 토큰이 없습니다."
            )
            return {
                "ok": False,
                "room_id": room_id,
                "room": room["name"],
                "dry_run": dry_run,
                "sent_to": sent,
                "failed": failed,
                "skipped": skipped,
                "previews": previews,
                "task_layer_summary": layer,
                "error": reason,
                "next": (
                    "이 도구는 분배 도구가 아니라 이미 배정된 개인 todo를 공지하는 도구입니다. "
                    "먼저 팀원별 실제 배정 상태를 확인하세요."
                ),
                "suggested_next_actions": [
                    "역할명에만 묶인 todo가 있으면 역할을 확정하거나 역할명 보정하기",
                    "todo가 없으면 실행 todo 만들기",
                    "담당자 토큰이 없으면 해당 팀원이 카카오 인증을 다시 진행하기",
                    "배정 상태 확인 후 다시 공지 시도하기",
                ],
            }

        return {
            "ok": dry_run or bool(sent),
            "room_id": room_id,
            "room": room["name"],
            "dry_run": dry_run,
            "sent_to": sent,
            "failed": failed,
            "skipped": skipped,
            "previews": previews,
            "task_layer_summary": layer,
            "next": (
                "할일 공지를 보냈습니다. 날짜가 있는 태스크는 담당자 개인 캘린더에도 "
                "등록할 수 있습니다."
            ),
            "suggested_next_actions": [
                "날짜 있는 태스크를 담당자 개인 캘린더에 등록하기",
                "개인별 진척을 대시보드에서 확인하기",
                "완료 보고가 들어오면 해당 할일을 완료로 갱신하기",
            ],
        }
