"""방별 투표/폼 결과 타임라인.

MCP 도구가 짧게 살아있는 서명 링크를 만들고, 이 라우트가 방에서 만든
폼/투표/일정조율 결과를 시간순 기록으로 보여준다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import time
from datetime import date, datetime
from typing import Any

from starlette.requests import Request
from starlette.responses import HTMLResponse

from . import storage
from .config import settings


_TOKEN_TTL_SECONDS = 60 * 60 * 24


def _secret() -> bytes:
    raw = settings.kakao_client_secret or settings.kakao_rest_api_key or settings.public_base_url
    return raw.encode("utf-8")


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(raw: str) -> bytes:
    pad = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode((raw + pad).encode("ascii"))


def create_dashboard_token(room_id: int, user_id: int, ttl_seconds: int = _TOKEN_TTL_SECONDS) -> str:
    """room_id/user_id/만료시각을 담은 HMAC 토큰을 만든다."""
    payload = {
        "room_id": int(room_id),
        "user_id": int(user_id),
        "exp": int(time.time()) + ttl_seconds,
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(_secret(), body, hashlib.sha256).digest()
    return f"{_b64e(body)}.{_b64e(sig)}"


def _verify_dashboard_token(token: str, room_id: int) -> dict[str, int] | None:
    try:
        body_part, sig_part = token.split(".", 1)
        body = _b64d(body_part)
        expected = hmac.new(_secret(), body, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64d(sig_part)):
            return None
        payload = json.loads(body.decode("utf-8"))
        if int(payload.get("room_id", -1)) != int(room_id):
            return None
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        user_id = int(payload.get("user_id", 0))
        if not storage.is_room_member(room_id, user_id):
            return None
        return {"room_id": int(room_id), "user_id": user_id, "exp": int(payload["exp"])}
    except Exception:
        return None


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def _schema_elements(schema: dict[str, Any]) -> list[dict[str, Any]]:
    elements = schema.get("elements")
    return elements if isinstance(elements, list) else []


def _form_kind(schema: dict[str, Any], title: str) -> str:
    elements = _schema_elements(schema)
    if any(el.get("type") == "matrixdropdown" and el.get("name") == "availability" for el in elements):
        return "schedule"
    if any(el.get("type") == "ranking" and el.get("name") == "roles" for el in elements):
        return "roles"
    if len(elements) == 1 and elements[0].get("type") == "comment":
        return "opinion"
    if "회고" in title:
        return "retro"
    return "survey"


def _dashboard_data(room_id: int) -> dict[str, Any] | None:
    room = storage.get_room(room_id)
    if room is None:
        return None
    from .tools.roadmap import _format as _format_roadmap

    members = storage.list_members(room_id)
    roadmap = _format_roadmap(storage.get_roadmap(room_id))
    latest_decisions = storage.latest_room_decisions(room_id)
    forms: list[dict[str, Any]] = []
    for form in storage.list_room_forms(room_id):
        schema = form.get("schema_json") or {"elements": []}
        result = storage.get_results(form["id"]) or {}
        forms.append(
            {
                "id": form["id"],
                "title": form["title"],
                "description": form.get("description"),
                "anonymous": form["anonymous"],
                "closed": form["closed"],
                "created_at": form["created_at"],
                "closes_at": form.get("closes_at"),
                "close_on_all": form.get("close_on_all"),
                "total_responses": form.get("total_responses", 0),
                "summary": result.get("results", []),
                "kind": _form_kind(schema, str(form["title"])),
            }
        )
    return {
        "room": {
            "id": room["id"],
            "name": room["name"],
            "description": room.get("description"),
            "invite_code": room["invite_code"],
        },
        "members": [
            {
                "id": m["id"],
                "nickname": m["nickname"],
                "role": m.get("role"),
                "joined_at": m.get("joined_at"),
            }
            for m in members
        ],
        "latest_decisions": latest_decisions,
        "roadmap": roadmap,
        "forms": forms,
    }


def _message(title: str, message: str, status: int = 200) -> HTMLResponse:
    page = (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)}</title></head>"
        '<body style="font-family:system-ui,-apple-system,sans-serif;max-width:680px;'
        'margin:4rem auto;padding:0 1rem;color:#1f2328;text-align:center">'
        f"<h1>{html.escape(title)}</h1><p>{html.escape(message)}</p></body></html>"
    )
    return HTMLResponse(page, status_code=status)


_PAGE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root{
    color-scheme:light;
    --ink:#18221d;
    --muted:#657069;
    --soft:#eef3ef;
    --paper:#f7f8f5;
    --panel:#fffffb;
    --line:#dfe5de;
    --accent:#23785a;
    --accent-soft:#e3f2eb;
    --amber:#9a650c;
    --amber-soft:#fff3d8;
    --red:#9b2f3b;
    --red-soft:#fde9eb;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--paper);color:var(--ink);font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
  .wrap{width:min(1120px,100%);margin:0 auto;padding:28px clamp(14px,3vw,38px) 56px}
  .mast{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:24px;align-items:start;margin-bottom:28px}
  .eyebrow{margin:0 0 8px;color:var(--accent);font-size:.78rem;font-weight:900;letter-spacing:.08em;text-transform:uppercase}
  h1{margin:0;font-size:clamp(2rem,4.2vw,4.5rem);line-height:.98;letter-spacing:0}
  .sub{margin:12px 0 0;color:var(--muted);line-height:1.55;max-width:680px}
  .stats{display:grid;grid-template-columns:repeat(4,92px);gap:8px}
  .stat{border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:12px}
  .stat strong{display:block;font-size:1.35rem;line-height:1;font-weight:950}
  .stat span{display:block;margin-top:7px;color:var(--muted);font-size:.78rem;font-weight:800}
  .members{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0 34px}
  .member{display:inline-flex;align-items:center;gap:7px;min-height:34px;border:1px solid var(--line);border-radius:999px;background:#fff;padding:0 11px;font-size:.88rem}
  .member b{font-weight:900}
  .member span{color:var(--muted);font-size:.8rem;font-weight:750}
  .roadmap-panel{border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:18px;margin:0 0 24px}
  .roadmap-head{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:14px;align-items:start;margin-bottom:16px}
  .roadmap-head h2{margin:0;font-size:1.25rem;line-height:1.25}
  .roadmap-head p{margin:6px 0 0;color:var(--muted);line-height:1.5}
  .progress-chip{display:inline-flex;align-items:center;min-height:34px;border-radius:999px;background:var(--accent);color:#fff;padding:0 12px;font-weight:950}
  .progress-line{height:10px;background:#e9eee9;border-radius:999px;overflow:hidden;margin:10px 0 18px}
  .progress-line span{display:block;height:100%;background:var(--accent);border-radius:999px}
  .member-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
  .member-card{border:1px solid var(--line);border-radius:8px;background:#fff;padding:13px}
  .member-card h3{margin:0;font-size:.98rem}
  .member-card .role{margin:4px 0 10px;color:var(--muted);font-size:.82rem;font-weight:800}
  .task-list{display:grid;gap:7px;margin:0;padding:0;list-style:none}
  .task-item{border:1px solid #e7ece6;border-radius:8px;padding:9px;background:#fbfdfb}
  .task-item.done{opacity:.72}
  .task-title{font-weight:900;line-height:1.35}
  .task-meta{margin-top:4px;color:var(--muted);font-size:.78rem;font-weight:800}
  .roadmap-note{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
  .timeline{position:relative;display:grid;gap:18px}
  .timeline:before{content:"";position:absolute;left:142px;top:0;bottom:0;width:2px;background:var(--line)}
  .event{position:relative;display:grid;grid-template-columns:120px minmax(0,1fr);gap:42px;align-items:start}
  .event:before{content:"";position:absolute;left:136px;top:22px;width:14px;height:14px;border:3px solid var(--accent);border-radius:50%;background:var(--paper);z-index:1}
  .when{padding-top:14px;text-align:right;color:var(--muted)}
  .when b{display:block;color:var(--ink);font-size:.92rem;font-weight:950}
  .when span{display:block;margin-top:5px;font-size:.78rem;font-weight:800}
  .card{border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:18px;box-shadow:0 1px 0 rgba(24,34,29,.03)}
  .card-head{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px;align-items:start;margin-bottom:14px}
  .kind{display:inline-flex;align-items:center;min-height:26px;border-radius:999px;background:var(--accent-soft);color:#195a43;padding:0 9px;font-size:.76rem;font-weight:900}
  .title{margin:8px 0 0;font-size:1.18rem;line-height:1.25;font-weight:950;word-break:keep-all}
  .meta{display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end}
  .badge{display:inline-flex;align-items:center;min-height:30px;border:1px solid var(--line);border-radius:999px;background:#fff;padding:0 10px;font-size:.8rem;font-weight:850;color:#3f4b43}
  .badge.open{background:var(--amber-soft);color:#714807;border-color:#eed29a}
  .badge.private{background:var(--red-soft);color:#7c2530;border-color:#f0bec5}
  .summary{display:grid;gap:13px}
  .block{border-top:1px solid var(--line);padding-top:13px}
  .block:first-child{border-top:0;padding-top:0}
  .block h3{margin:0 0 9px;font-size:.92rem;line-height:1.3}
  .block p{margin:0;color:var(--muted);line-height:1.5}
  .best-list{display:flex;flex-wrap:wrap;gap:8px;margin-top:9px}
  .best{display:inline-flex;align-items:center;border-radius:999px;background:var(--accent);color:#fff;padding:7px 10px;font-weight:950;font-size:.86rem}
  .bars{display:grid;gap:8px;margin-top:8px}
  .bar{display:grid;grid-template-columns:minmax(92px,1fr) 42px;gap:10px;align-items:center}
  .bar-label{font-size:.86rem;color:#364039;font-weight:850;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .bar-value{text-align:right;font-weight:950;color:var(--accent)}
  .track{height:8px;background:#e9eee9;border-radius:999px;overflow:hidden}
  .fill{height:100%;background:var(--accent);border-radius:999px}
  .answers{display:grid;gap:8px;margin:8px 0 0;padding:0;list-style:none}
  .answers li{padding:9px 10px;border:1px solid var(--line);border-radius:8px;background:#fff;line-height:1.45;word-break:break-word}
  .empty{border:1px dashed #bcc8bf;border-radius:8px;background:rgba(255,255,255,.55);padding:36px 22px;text-align:center;color:var(--muted)}
  @media (max-width:760px){
    .mast{display:block}
    .stats{grid-template-columns:repeat(2,minmax(0,1fr));margin-top:18px}
    .member-grid{grid-template-columns:1fr}
    .timeline:before{left:8px}
    .event{grid-template-columns:1fr;gap:8px;padding-left:28px}
    .event:before{left:1px}
    .when{text-align:left;padding-top:0;display:flex;gap:8px;align-items:center}
    .when span{margin-top:0}
    .card-head{display:block}
    .meta{justify-content:flex-start;margin-top:12px}
  }
  @media (max-width:480px){
    .wrap{padding-top:20px}
    .stats{grid-template-columns:1fr}
    .card{padding:15px}
    h1{font-size:2rem}
  }
</style>
</head>
<body>
<div class="wrap">
  <header class="mast">
    <div>
      <p class="eyebrow">Decision Timeline</p>
      <h1 id="roomName"></h1>
      <p class="sub" id="subtitle"></p>
    </div>
    <div class="stats">
      <div class="stat"><strong id="formCount">0</strong><span>기록</span></div>
      <div class="stat"><strong id="memberCount">0</strong><span>멤버</span></div>
      <div class="stat"><strong id="taskCount">0</strong><span>태스크</span></div>
      <div class="stat"><strong id="responseCount">0</strong><span>응답</span></div>
    </div>
  </header>
  <div class="members" id="members"></div>
  <section id="roadmapPanel"></section>
  <main class="timeline" id="timeline"></main>
</div>
<script>
const dashboard = __DATA__;
const forms = [...dashboard.forms].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
const roadmap = dashboard.roadmap || {progress:{done:0,total:0}, task_layer_summary:{milestones:0,todos:0}, by_member:[], unassigned_tasks:[], calendar_candidates:[]};

function escapeText(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[ch]);
}

function dt(value) {
  const date = value ? new Date(value) : null;
  if (!date || Number.isNaN(date.getTime())) return { day: "-", time: "" };
  return {
    day: date.toLocaleDateString("ko-KR", { month: "numeric", day: "numeric" }),
    time: date.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })
  };
}

function kindLabel(kind) {
  return {
    schedule: "회의 시간",
    roles: "역할 분배",
    opinion: "의견수렴",
    retro: "회고",
    survey: "투표"
  }[kind] || "투표";
}

function statusLabel(status) {
  return {todo: "대기", doing: "진행중", done: "완료"}[status] || status || "-";
}

function taskDate(task) {
  if (task.end_at) return `마감 ${escapeText(task.end_at.slice(0, 10))}`;
  if (task.start_at) return `시작 ${escapeText(task.start_at.slice(0, 10))}`;
  return "일정 미정";
}

function renderTask(task) {
  return `
    <li class="task-item ${task.status === "done" ? "done" : ""}">
      <div class="task-title">${escapeText(task.title)}</div>
      <div class="task-meta">${escapeText(statusLabel(task.status))} · ${taskDate(task)}</div>
    </li>
  `;
}

function renderRoadmap() {
  const total = Number((roadmap.progress && roadmap.progress.total) || 0);
  const layer = roadmap.task_layer_summary || {};
  const milestoneCount = Number(layer.milestones || 0);
  if (!total && !milestoneCount) return "";
  const done = Number((roadmap.progress && roadmap.progress.done) || 0);
  const pct = total ? Math.round(done / total * 100) : 0;
  const needsTodo = Boolean(layer.needs_todo_decomposition);
  const members = (roadmap.by_member || []).map((member) => {
    const tasks = (member.tasks || []).slice(0, 5);
    const more = (member.tasks || []).length > tasks.length ? `<li class="task-item"><div class="task-meta">외 ${(member.tasks || []).length - tasks.length}개</div></li>` : "";
    return `
      <section class="member-card">
        <h3>${escapeText(member.nickname)}</h3>
        <div class="role">${escapeText(member.role || "역할 미정")} · ${escapeText((member.progress && member.progress.done) || 0)}/${escapeText((member.progress && member.progress.total) || 0)} 완료</div>
        <ul class="task-list">${tasks.map(renderTask).join("") || `<li class="task-item"><div class="task-meta">아직 배정된 태스크가 없습니다.</div></li>`}${more}</ul>
      </section>
    `;
  }).join("");
  return `
    <section class="roadmap-panel">
      <div class="roadmap-head">
        <div>
          <h2>로드맵 진행</h2>
          <p>${needsTodo ? "로드맵 단계는 준비됐고, 이제 개인별 실행 todo로 분해해야 합니다." : "역할분배와 연결된 개인별 할일, 마감 후보, 미배정 태스크를 한곳에 모았습니다."}</p>
        </div>
        <span class="progress-chip">${done}/${total} 완료</span>
      </div>
      <div class="progress-line"><span style="width:${Math.max(2, pct)}%"></span></div>
      <div class="member-grid">${members}</div>
      <div class="roadmap-note">
        <span class="badge">${escapeText(milestoneCount)}개 단계</span>
        <span class="badge ${needsTodo ? "open" : ""}">${escapeText(total)}개 todo</span>
        <span class="badge">${escapeText((roadmap.calendar_candidates || []).length)}개 캘린더 후보</span>
        <span class="badge ${roadmap.unassigned_tasks && roadmap.unassigned_tasks.length ? "open" : ""}">${escapeText((roadmap.unassigned_tasks || []).length)}개 미배정</span>
      </div>
    </section>
  `;
}

function renderBars(scores) {
  const entries = Object.entries(scores || {}).sort((a, b) => Number(b[1]) - Number(a[1]));
  if (!entries.length) return "<p>아직 응답이 없습니다.</p>";
  const max = entries.reduce((m, [, value]) => Math.max(m, Number(value) || 0), 0) || 1;
  return `<div class="bars">${entries.map(([label, value]) => {
    const n = Number(value) || 0;
    const width = Math.max(4, n / max * 100);
    return `
      <div>
        <div class="bar"><div class="bar-label">${escapeText(label)}</div><div class="bar-value">${escapeText(value)}</div></div>
        <div class="track"><div class="fill" style="width:${width}%"></div></div>
      </div>
    `;
  }).join("")}</div>`;
}

function topCount(counts) {
  const entries = Object.entries(counts || {}).sort((a, b) => Number(b[1]) - Number(a[1]));
  return entries[0] || null;
}

function renderResult(result) {
  if (result.type === "grid") {
    const best = result.best_slots || (result.best_slot ? [result.best_slot] : []);
    const chips = best.length
      ? `<div class="best-list">${best.map((slot) => `<span class="best">${escapeText(slot)}</span>`).join("")}</div>`
      : "<p>아직 최적 시간이 없습니다.</p>";
    return `<section class="block"><h3>${escapeText(result.question)}</h3><p>최적 후보 ${best.length}개 · O ${escapeText(result.best_O || 0)}</p>${chips}</section>`;
  }
  if (result.counts) {
    const top = topCount(result.counts);
    const lead = top ? `현재 1위: ${escapeText(top[0])} · ${escapeText(top[1])}표` : "아직 응답이 없습니다.";
    return `<section class="block"><h3>${escapeText(result.question)}</h3><p>${lead}</p>${renderBars(result.counts)}</section>`;
  }
  if (result.ranking_scores) {
    return `<section class="block"><h3>${escapeText(result.question)}</h3>${renderBars(result.ranking_scores)}</section>`;
  }
  if (result.type === "rating") {
    const avg = result.average == null ? "없음" : Number(result.average).toFixed(1);
    return `<section class="block"><h3>${escapeText(result.question)}</h3><p>평균 ${avg} · ${result.values ? result.values.length : 0}건</p></section>`;
  }
  if (result.answers) {
    const answers = result.answers.slice(0, 10);
    const more = result.answers.length > answers.length ? `<li>외 ${result.answers.length - answers.length}건</li>` : "";
    const list = answers.map((answer) => `<li>${escapeText(answer)}</li>`).join("") + more;
    return `<section class="block"><h3>${escapeText(result.question)}</h3><ul class="answers">${list || "<li>응답 없음</li>"}</ul></section>`;
  }
  return `<section class="block"><h3>${escapeText(result.question || "질문")}</h3><p>요약할 응답이 없습니다.</p></section>`;
}

function renderEvent(form, index) {
  const when = dt(form.created_at);
  const badges = [
    form.closed ? "마감" : "진행중",
    form.anonymous ? "익명" : "식별",
    `${form.total_responses}응답`
  ];
  const summary = (form.summary || []).map(renderResult).join("") || "<section class='block'><p>아직 응답이 없습니다.</p></section>";
  return `
    <article class="event">
      <time class="when"><b>${escapeText(when.day)}</b><span>${escapeText(when.time)}</span></time>
      <section class="card">
        <div class="card-head">
          <div>
            <span class="kind">${index + 1}. ${escapeText(kindLabel(form.kind))}</span>
            <h2 class="title">${escapeText(form.title)}</h2>
          </div>
          <div class="meta">${badges.map((b) => `<span class="badge ${b === "진행중" ? "open" : b === "식별" ? "private" : ""}">${escapeText(b)}</span>`).join("")}</div>
        </div>
        <div class="summary">${summary}</div>
      </section>
    </article>
  `;
}

function render() {
  document.getElementById("roomName").textContent = dashboard.room.name;
  document.getElementById("subtitle").textContent = `초대 코드 ${dashboard.room.invite_code} · 방에서 만든 투표와 폼 결과를 최신순으로 모았습니다.`;
  document.getElementById("formCount").textContent = forms.length;
  document.getElementById("memberCount").textContent = dashboard.members.length;
  document.getElementById("taskCount").textContent = (roadmap.task_layer_summary && roadmap.task_layer_summary.todos) || (roadmap.progress && roadmap.progress.total) || 0;
  document.getElementById("responseCount").textContent = forms.reduce((sum, form) => sum + Number(form.total_responses || 0), 0);

  const members = document.getElementById("members");
  members.innerHTML = dashboard.members.map((member) => `<span class="member"><b>${escapeText(member.nickname)}</b><span>${escapeText(member.role || "역할 미정")}</span></span>`).join("");
  document.getElementById("roadmapPanel").innerHTML = renderRoadmap();

  const timeline = document.getElementById("timeline");
  timeline.innerHTML = forms.length
    ? forms.map(renderEvent).join("")
    : `<div class="empty"><h2>아직 기록이 없습니다</h2><p>투표나 일정 조율을 만들면 이곳에 시간순으로 쌓입니다.</p></div>`;
}

render();
</script>
</body>
</html>"""


async def view_room_dashboard(request: Request) -> HTMLResponse:
    try:
        room_id = int(request.path_params["room_id"])
    except (KeyError, ValueError):
        return _message("잘못된 요청", "방 ID가 올바르지 않습니다.", 400)
    token = request.query_params.get("token") or ""
    if _verify_dashboard_token(token, room_id) is None:
        return _message("권한이 없습니다", "대시보드 링크가 만료되었거나 올바르지 않습니다.", 403)
    data = _dashboard_data(room_id)
    if data is None:
        return _message("방을 찾을 수 없음", "존재하지 않는 방입니다.", 404)
    safe_data = json.dumps(_jsonable(data), ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(f"{data['room']['name']} 결과 타임라인")
    return HTMLResponse(_PAGE.replace("__TITLE__", title).replace("__DATA__", safe_data))


def register_dashboard_routes(mcp) -> None:
    """대시보드 웹 라우트를 MCP 서버(Starlette)에 등록한다."""
    mcp.custom_route("/dashboard/rooms/{room_id}", methods=["GET"])(view_room_dashboard)
