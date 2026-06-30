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
from .ui_theme import (
    APP_FONT_LINKS,
    APP_LUCIDE_SCRIPT,
    APP_REACT_LIQUID_BOOTSTRAP,
    APP_REACT_LIQUID_IMPORTS,
    APP_THEME_CSS,
)


_TOKEN_TTL_SECONDS = 60 * 60 * 24


def _secret() -> bytes:
    # 서명 키는 진짜 비밀에서만 가져온다. public_base_url(공개값) 폴백을 두면
    # 두 키가 빈 배포에서 누구나 토큰을 위조할 수 있으므로 제거하고, 없으면
    # fail-closed 한다(대시보드 토큰 발급/검증 자체를 막음).
    raw = settings.kakao_client_secret or settings.kakao_rest_api_key
    if not raw:
        raise RuntimeError(
            "대시보드 토큰 서명 키가 없습니다. KAKAO_CLIENT_SECRET 또는 "
            "KAKAO_REST_API_KEY를 설정하세요."
        )
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
    explicit = schema.get("_workflow_kind")
    explicit_map = {
        "daily_checkin": "checkin",
        "location": "location",
        "roadmap_decision": "roadmap_input",
        "meeting_time": "schedule",
        "role_assignment": "roles",
    }
    if explicit in explicit_map:
        return explicit_map[str(explicit)]
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
                "responses": result.get("responses", []),
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
        "decisions": storage.list_room_decisions(room_id, limit=30),
        "roadmap": roadmap,
        "daily_reports": storage.list_daily_reports(room_id, limit=7),
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
__APP_FONT_LINKS__
__APP_REACT_LIQUID_IMPORTS__
__APP_LUCIDE_SCRIPT__
<style>
  __APP_THEME_CSS__
  .shell{position:relative;z-index:1;display:grid;grid-template-columns:260px minmax(0,1fr) 336px;gap:16px;width:min(1440px,100%);margin:0 auto;padding:16px clamp(12px,2vw,24px) 44px;align-items:start}
  .workspace{position:sticky;top:16px;min-height:calc(100vh - 32px);display:flex;flex-direction:column;padding:14px;background:linear-gradient(180deg,var(--workspace),var(--workspace-2));color:#fff8e8;box-shadow:inset 0 1px 0 rgba(255,255,255,.10),0 28px 80px rgba(37,33,29,.20)}
  .workspace__top{display:grid;gap:12px;padding:4px 4px 14px;border-bottom:1px solid rgba(255,255,255,.14)}
  .workspace__mark{display:grid;place-items:center;width:38px;height:38px;border-radius:8px;background:var(--kakao-yellow);color:var(--kakao-black);box-shadow:0 12px 30px rgba(254,229,0,.18);font-family:var(--font-display);font-weight:800}
  .eyebrow{margin:0;color:rgba(255,248,232,.62);font-size:.72rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase}
  h1{margin:2px 0 0;font-family:var(--font-display);font-size:1.55rem;line-height:1.12;letter-spacing:0;font-weight:800;color:#fff8e8}
  .workspace__sub{margin:7px 0 0;color:rgba(255,248,232,.66);line-height:1.45;font-size:.88rem}
  .workspace__nav{display:grid;gap:3px;margin:14px 0;padding:0;list-style:none}
  .nav-item{position:relative;display:grid;grid-template-columns:26px minmax(0,1fr) auto;align-items:center;gap:8px;width:100%;min-height:36px;border:0;border-radius:var(--radius);padding:0 8px;background:transparent;color:rgba(255,248,232,.78);font-weight:700;font-size:.9rem;text-align:left;overflow:hidden;transition:background .16s ease,color .16s ease,transform .16s cubic-bezier(.2,.8,.2,1)}
  .nav-item:before{content:"";position:absolute;inset:1px;border-radius:7px;background:linear-gradient(135deg,rgba(255,255,255,.15),transparent 48%,rgba(255,255,255,.06));opacity:0;pointer-events:none}
  .nav-item:hover{background:rgba(255,255,255,.08);color:#fff8e8;transform:translateY(-1px)}
  .nav-item:focus-visible{outline:2px solid var(--kakao-yellow);outline-offset:2px}
  .nav-item.is-active{background:rgba(255,255,255,.13);color:#fff8e8;box-shadow:inset 0 1px 0 rgba(255,255,255,.10)}
  .nav-item.is-active:before{opacity:1}
  .nav-item:disabled{cursor:not-allowed;opacity:.48}
  .nav-icon{display:grid;place-items:center;width:22px;height:22px;border-radius:6px;background:linear-gradient(180deg,rgba(255,255,255,.16),rgba(255,255,255,.07));color:rgba(255,248,232,.86);box-shadow:inset 0 1px 0 rgba(255,255,255,.18),inset 0 -1px 0 rgba(0,0,0,.14)}
  .nav-icon svg{display:block;width:14px;height:14px;stroke:currentColor;stroke-width:2.15;stroke-linecap:round;stroke-linejoin:round;fill:none}
  .nav-item b{font-variant-numeric:tabular-nums;font-size:.78rem;color:rgba(255,248,232,.68)}
  .side-section{padding:13px 4px 0;border-top:1px solid rgba(255,255,255,.12)}
  .side-label{margin:0 0 8px;color:rgba(255,248,232,.52);font-size:.72rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase}
  .members{display:grid;gap:7px;margin:0}
  .member{display:grid;grid-template-columns:26px minmax(0,1fr);gap:8px;align-items:center;min-height:38px;border-radius:var(--radius);padding:5px 7px;background:rgba(255,255,255,.08)}
  .member:before{content:attr(data-initial);display:grid;place-items:center;width:26px;height:26px;border-radius:7px;background:rgba(255,255,255,.16);color:#fff;font-weight:800;font-size:.76rem}
  .member b{display:block;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:760;color:#fff8e8}
  .member-copy{display:block;min-width:0}
  .member-role{display:block;min-width:0;color:rgba(255,248,232,.62);font-size:.76rem;font-weight:650;line-height:1.25;white-space:normal;overflow-wrap:anywhere}
  .conversation{min-width:0;display:grid;gap:12px}
  .channel-header{padding:16px 18px 14px}
  .channel-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:18px;align-items:start}
  .channel-kicker{margin:0 0 6px;color:var(--workspace);font-size:.76rem;font-weight:800;letter-spacing:.06em;text-transform:uppercase}
  .channel-header h2{margin:0;font-family:var(--font-display);font-size:1.9rem;line-height:1.1;font-weight:800}
  .sub{margin:8px 0 0;color:var(--muted);line-height:1.5;max-width:68ch}
  .stats{display:grid;grid-template-columns:repeat(4,82px);gap:6px}
  .stat{min-height:58px;border:1px solid rgba(33,24,8,.10);border-radius:var(--radius);background:rgba(255,252,244,.74);padding:9px 10px;box-shadow:inset 0 1px 0 rgba(255,255,255,.72)}
  .stat strong{display:block;font-size:1.08rem;line-height:1;font-weight:800;font-variant-numeric:tabular-nums;color:var(--ink)}
  .stat span{display:block;margin-top:6px;color:var(--muted);font-size:.72rem;font-weight:700}
  .project-rail{position:sticky;top:16px;min-width:0}
  #roadmapPanel[hidden]{display:none}
  .shell.is-feed-only{grid-template-columns:260px minmax(0,1fr)}
  .roadmap-panel{border:1px solid var(--glass-line);border-radius:var(--radius);background:linear-gradient(180deg,rgba(255,255,255,.76),rgba(255,250,237,.52));padding:15px;box-shadow:inset 0 1px 0 var(--glass-hi),var(--shadow-lg);backdrop-filter:blur(12px) saturate(1.12);-webkit-backdrop-filter:blur(12px) saturate(1.12);transition:box-shadow .18s ease,border-color .18s ease}
  .roadmap-panel.is-focused{border-color:rgba(254,229,0,.58);box-shadow:inset 0 1px 0 var(--glass-hi),0 0 0 3px rgba(254,229,0,.24),var(--shadow-lg)}
  .roadmap-head{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:14px;align-items:start;margin-bottom:16px}
  .roadmap-head h2{margin:0;font-size:1.12rem;line-height:1.25;font-weight:820}
  .roadmap-head p{margin:6px 0 0;color:var(--muted);line-height:1.5}
  .progress-chip{display:inline-flex;align-items:center;min-height:32px;border-radius:999px;background:var(--workspace);color:#fff8e8;padding:0 11px;font-weight:820;box-shadow:0 12px 28px rgba(37,33,29,.18);font-variant-numeric:tabular-nums}
  .progress-line{height:9px;background:rgba(255,255,255,.64);border:1px solid rgba(255,255,255,.62);border-radius:999px;overflow:hidden;margin:10px 0 16px}
  .progress-line span{display:block;height:100%;background:linear-gradient(90deg,var(--workspace),var(--warning));border-radius:999px}
  .member-grid{display:grid;grid-template-columns:1fr;gap:10px}
  .member-card{border-top:1px solid rgba(33,24,8,.12);padding:12px 0 0}
  .member-card:first-child{border-top:0;padding-top:0}
  .member-card h3{margin:0;font-size:.95rem;font-weight:820}
  .member-card .role{margin:4px 0 10px;color:var(--muted);font-size:.8rem;font-weight:720;line-height:1.35;white-space:normal;overflow-wrap:anywhere}
  .task-list{display:grid;gap:7px;margin:0;padding:0;list-style:none}
  .task-item{border:1px solid rgba(33,24,8,.10);border-radius:var(--radius);padding:9px;background:rgba(255,252,244,.72)}
  .task-item.done{opacity:.72}
  .task-title{font-weight:760;line-height:1.35}
  .task-meta{margin-top:4px;color:var(--muted);font-size:.78rem;font-weight:680}
  .roadmap-note{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
  .timeline{min-width:0;border:1px solid rgba(33,24,8,.10);border-radius:var(--radius);background:rgba(255,252,244,.88);box-shadow:var(--shadow-md);overflow:hidden}
  .event{position:relative;display:grid;grid-template-columns:42px minmax(0,1fr);gap:12px;padding:16px 18px}
  .event:after{content:"";position:absolute;left:72px;right:18px;bottom:0;height:1px;background:rgba(33,24,8,.10)}
  .event:last-child:after{display:none}
  .event-avatar{display:flex;align-items:center;justify-content:center;width:36px;height:36px;border:1px solid rgba(37,33,29,.13);border-radius:8px;background:linear-gradient(180deg,rgba(255,255,255,.78),rgba(255,250,240,.54));color:var(--workspace);box-shadow:inset 0 1px 0 rgba(255,255,255,.86),0 8px 20px rgba(45,36,18,.08);text-align:center}
  .event-avatar svg{display:block;width:18px;height:18px;stroke:currentColor;stroke-width:2.15;stroke-linecap:round;stroke-linejoin:round;fill:none}
  .event-avatar.schedule,.event-avatar.daily_report{background:linear-gradient(180deg,rgba(254,229,0,.22),rgba(255,250,240,.70));color:#5d4e00;border-color:rgba(254,229,0,.25)}
  .event-avatar.roles,.event-avatar.decision_roles{background:linear-gradient(180deg,rgba(37,33,29,.12),rgba(255,250,240,.62));color:var(--workspace)}
  .event-avatar.location,.event-avatar.roadmap_input,.event-avatar.decision_meeting_location{background:linear-gradient(180deg,rgba(18,100,163,.15),rgba(255,250,240,.64));color:var(--slack-blue);border-color:rgba(18,100,163,.18)}
  .event-avatar.retro,.event-avatar.opinion{background:linear-gradient(180deg,rgba(224,30,90,.14),rgba(255,250,240,.64));color:var(--slack-red);border-color:rgba(224,30,90,.18)}
  .event-avatar.liquid-react-mounted{background:rgba(255,251,241,.16)}
  .card{min-width:0;background:transparent;padding:0}
  .card-head{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px;align-items:start;margin-bottom:12px}
  .message-meta{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:5px}
  .when{display:inline-flex;gap:5px;align-items:center;color:var(--muted);font-size:.78rem;font-weight:680;font-variant-numeric:tabular-nums}
  .when b{display:inline;color:var(--muted);font-size:inherit;font-weight:760}
  .when span{display:inline;margin:0}
  .kind{position:relative;isolation:isolate;overflow:hidden;display:inline-flex;align-items:center;min-height:22px;border-radius:999px;background:var(--workspace-soft);color:var(--workspace);border:1px solid rgba(37,33,29,.13);padding:0 8px;font-size:.72rem;font-weight:760}
  .kind.schedule,.kind.daily_report{background:rgba(254,229,0,.12);color:#5d4e00;border-color:rgba(254,229,0,.22)}
  .kind.roles,.kind.decision_roles{background:var(--slack-aubergine-soft);color:var(--slack-aubergine);border-color:rgba(74,21,75,.18)}
  .kind.location,.kind.roadmap_input{background:var(--slack-blue-soft);color:var(--slack-blue);border-color:rgba(18,100,163,.16)}
  .kind.retro,.kind.opinion{background:var(--slack-red-soft);color:var(--slack-red);border-color:rgba(224,30,90,.15)}
  .title{margin:0;font-size:1.05rem;line-height:1.34;font-weight:820;word-break:keep-all}
  .meta{display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end}
  .badge{position:relative;isolation:isolate;overflow:hidden;display:inline-flex;align-items:center;min-height:26px;border:1px solid rgba(33,24,8,.11);border-radius:999px;background:rgba(255,251,241,.64);padding:0 9px;font-size:.76rem;font-weight:720;color:var(--ink-soft)}
  .badge.open{background:var(--amber-soft);color:#82500b;border-color:rgba(216,132,24,.28)}
  .badge.private{background:var(--rose-soft);color:#8b2639;border-color:rgba(191,64,88,.24)}
  .badge.report{background:var(--slack-blue-soft);color:var(--slack-blue);border-color:rgba(18,100,163,.22)}
  .summary{display:grid;gap:13px}
  .block{border-top:1px solid var(--glass-line);padding-top:13px}
  .block:first-child{border-top:0;padding-top:0}
  .block h3{margin:0 0 9px;font-size:.9rem;line-height:1.3;font-weight:800}
  .block p{margin:0;color:var(--muted);line-height:1.5}
  .inline-list{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}
  .mini{position:relative;isolation:isolate;overflow:hidden;display:inline-flex;align-items:center;border:1px solid var(--glass-line);border-radius:999px;background:rgba(255,251,241,.68);padding:6px 9px;color:var(--ink-soft);font-size:.8rem;font-weight:700}
  .best-list{display:flex;flex-wrap:wrap;gap:8px;margin-top:9px}
  .best{position:relative;isolation:isolate;overflow:hidden;display:inline-flex;align-items:center;gap:7px;border:1px solid rgba(254,229,0,.28);border-radius:999px;background:rgba(255,251,241,.82);color:var(--ink);padding:7px 10px;font-weight:800;font-size:.84rem}
  .best:before{content:"";position:relative;z-index:2;flex:0 0 auto;width:7px;height:7px;border-radius:999px;background:var(--kakao-yellow);box-shadow:0 0 0 3px rgba(254,229,0,.16)}
  .bars{display:grid;gap:8px;margin-top:8px}
  .bar{display:grid;grid-template-columns:minmax(92px,1fr) 42px;gap:10px;align-items:center}
  .bar-label{font-size:.86rem;color:var(--ink-soft);font-weight:720;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .bar-value{text-align:right;font-weight:820;color:var(--workspace);font-variant-numeric:tabular-nums}
  .track{height:8px;background:rgba(255,255,255,.76);border-radius:999px;overflow:hidden;border:1px solid rgba(33,24,8,.08)}
  .fill{height:100%;background:linear-gradient(90deg,var(--workspace),var(--warning));border-radius:999px}
  .answers{display:grid;gap:8px;margin:8px 0 0;padding:0;list-style:none}
  .answers li{padding:9px 10px;border:1px solid rgba(33,24,8,.10);border-radius:var(--radius);background:rgba(255,252,244,.76);line-height:1.45;word-break:break-word}
  .preference-grid,.assignment-grid{display:grid;gap:8px;margin-top:9px}
  .assignment-grid{grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}
  .preference-card,.assignment-card{border:1px solid rgba(33,24,8,.10);border-radius:var(--radius);background:rgba(255,252,244,.74);padding:10px;box-shadow:inset 0 1px 0 rgba(255,255,255,.58)}
  .assignment-card{padding:12px 14px}
  .preference-card b,.assignment-card b{display:block;color:var(--ink);font-size:.86rem;font-weight:820;line-height:1.35}
  .preference-list{display:flex;flex-wrap:wrap;gap:6px;margin-top:7px}
  .preference-chip{display:inline-flex;align-items:center;gap:5px;border:1px solid rgba(33,24,8,.10);border-radius:999px;background:rgba(255,251,241,.76);padding:5px 8px;color:var(--ink-soft);font-size:.78rem;font-weight:720;line-height:1.25}
  .preference-rank{display:inline-grid;place-items:center;width:18px;height:18px;border-radius:999px;background:var(--workspace);color:#fff8e8;font-size:.68rem;font-weight:820;font-variant-numeric:tabular-nums}
  .assignment-role{display:block;margin-top:5px;color:var(--ink-soft);font-size:.86rem;font-weight:740;line-height:1.4;overflow-wrap:anywhere}
  .decision-callout{display:grid;gap:10px;border:1px solid rgba(33,24,8,.10);border-radius:var(--radius);background:linear-gradient(180deg,rgba(255,253,247,.84),rgba(255,250,240,.58));padding:12px 14px;box-shadow:inset 0 1px 0 rgba(255,255,255,.72)}
  .decision-time{display:inline-flex;width:max-content;max-width:100%;align-items:center;min-height:30px;border:1px solid rgba(33,24,8,.11);border-radius:999px;background:rgba(255,251,241,.78);padding:0 10px;color:var(--ink);font-size:.86rem;font-weight:820;line-height:1.2;box-shadow:inset 0 1px 0 rgba(255,255,255,.68)}
  .decision-title{margin:0;color:var(--ink);font-weight:820;line-height:1.45}
  .decision-note{margin:0;color:var(--muted);font-size:.88rem;line-height:1.5}
  .empty{border:1px dashed rgba(33,24,8,.24);border-radius:var(--radius);background:rgba(255,251,241,.62);padding:36px 22px;text-align:center;color:var(--muted)}
  @media (max-width:1180px){
    .shell{grid-template-columns:236px minmax(0,1fr);grid-template-areas:"workspace conversation" "workspace rail"}
    .workspace{grid-area:workspace}
    .conversation{grid-area:conversation}
    .project-rail{grid-area:rail;position:relative;top:auto}
  }
  @media (max-width:840px){
    .shell{display:grid;grid-template-columns:1fr;grid-template-areas:"workspace" "conversation" "rail";gap:12px;padding:12px 10px 36px}
    .workspace{position:relative;top:auto;min-height:auto}
    .workspace__top{grid-template-columns:38px minmax(0,1fr);align-items:start}
    .workspace__copy{min-width:0}
    .workspace__nav{grid-template-columns:repeat(2,minmax(0,1fr))}
    .side-section{display:block}
    .members{grid-template-columns:repeat(auto-fit,minmax(142px,1fr))}
    .channel-row{display:block}
    .stats{grid-template-columns:repeat(4,minmax(0,1fr));margin-top:14px}
    .project-rail{position:relative;top:auto}
    .card-head{display:block}
    .meta{justify-content:flex-start;margin-top:10px}
  }
  @media (max-width:480px){
    .workspace{padding:12px}
    .workspace__top{padding-bottom:10px}
    h1{font-size:1.28rem}
    .workspace__sub{margin-top:5px}
    .workspace__nav{grid-template-columns:repeat(4,minmax(0,1fr));gap:5px;margin:10px 0 0}
    .nav-item{grid-template-columns:1fr;justify-items:center;gap:3px;min-height:46px;padding:5px 4px}
    .nav-item span:not(.nav-icon){display:none}
    .nav-item b{font-size:.75rem}
    .side-section{display:none}
    .stats{grid-template-columns:repeat(2,minmax(0,1fr))}
    .event{grid-template-columns:34px minmax(0,1fr);gap:10px;padding:14px 12px}
    .event:after{left:54px;right:12px}
    .event-avatar{width:32px;height:32px}
    .event-avatar svg{width:16px;height:16px}
    .channel-header h2{font-size:1.52rem}
  }
</style>
</head>
<body>
<div class="shell" id="dashboardShell">
  <aside class="workspace">
    <div class="workspace__top">
      <div class="workspace__mark">T</div>
      <div class="workspace__copy">
        <p class="eyebrow">Teamplay room</p>
        <h1 id="roomName"></h1>
        <p class="workspace__sub" id="roomInvite"></p>
      </div>
    </div>
    <nav class="workspace__nav" aria-label="방 요약">
      <button class="nav-item is-active" type="button" data-nav="all"><span class="nav-icon"><i data-lucide="list"></i></span><span>활동 피드</span><b id="sideEventCount">0</b></button>
      <button class="nav-item" type="button" data-nav="tasks"><span class="nav-icon"><i data-lucide="clipboard-check"></i></span><span>태스크</span><b id="sideTaskCount">0</b></button>
      <button class="nav-item" type="button" data-nav="responses"><span class="nav-icon"><i data-lucide="message-circle"></i></span><span>응답</span><b id="sideResponseCount">0</b></button>
      <button class="nav-item" type="button" data-nav="decisions"><span class="nav-icon"><i data-lucide="badge-check"></i></span><span>결정</span><b id="sideDecisionCount">0</b></button>
    </nav>
    <div class="side-section">
      <p class="side-label">Members</p>
      <div class="members" id="members"></div>
    </div>
  </aside>
  <main class="conversation">
    <header class="channel-header glass-panel">
      <div class="channel-row">
        <div>
          <p class="channel-kicker"># teamplay-feed</p>
          <h2>MCP 작업 기록</h2>
          <p class="sub" id="subtitle"></p>
        </div>
        <div class="stats">
          <div class="stat"><strong id="formCount">0</strong><span>기록</span></div>
          <div class="stat"><strong id="memberCount">0</strong><span>멤버</span></div>
          <div class="stat"><strong id="taskCount">0</strong><span>태스크</span></div>
          <div class="stat"><strong id="responseCount">0</strong><span>응답</span></div>
        </div>
      </div>
    </header>
    <section class="timeline" id="timeline"></section>
  </main>
  <aside id="roadmapPanel" class="project-rail"></aside>
</div>
<script>
const dashboard = __DATA__;
const forms = [...dashboard.forms].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
const dailyReports = [...(dashboard.daily_reports || [])].sort((a, b) => new Date(b.report_date) - new Date(a.report_date));
const decisions = [...(dashboard.decisions || [])].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
const roadmap = dashboard.roadmap || {progress:{done:0,total:0}, task_layer_summary:{milestones:0,todos:0}, by_member:[], unassigned_tasks:[], calendar_candidates:[]};
let activeNav = "all";
let currentEvents = [];

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

function taskScheduleLabel(task) {
  const raw = task.end_at || task.start_at;
  if (!raw) return "일정 미정";
  const text = String(raw);
  return text.length >= 10 ? text.slice(0, 10) : text;
}

function kindLabel(kind) {
  return {
    schedule: "회의 시간",
    roles: "역할 분배",
    opinion: "의견수렴",
    retro: "회고",
    checkin: "데일리 체크인",
    location: "장소 수집",
    roadmap_input: "로드맵 의견",
    daily_report: "데일리 리포트",
    decision_roles: "역할 확정",
    decision_meeting_time: "회의 확정",
    decision_meeting_location: "장소 확정",
    decision_general: "결정 기록",
    survey: "투표"
  }[kind] || "투표";
}

function kindClass(kind) {
  return String(kind || "survey").toLowerCase().replace(/[^a-z0-9_-]/g, "_");
}

function eventNumber(sequence) {
  const n = Number(sequence);
  return String(Number.isFinite(n) && n > 0 ? n : 1).padStart(2, "0");
}

function eventTime(event) {
  const time = new Date(event.at).getTime();
  return Number.isNaN(time) ? 0 : time;
}

function collapseDecisionEvents(events) {
  return events.filter((event) => {
    const decision = event.data || {};
    if (decision.kind !== "meeting_time" || decision.source !== "notify_room") return true;
    return !events.some((other) => {
      const otherDecision = other.data || {};
      if (other === event || otherDecision.kind !== "meeting_time") return false;
      if (otherDecision.source !== "calendar_create_room_event") return false;
      return Math.abs(eventTime(other) - eventTime(event)) <= 15 * 60 * 1000;
    });
  });
}

function visibleEventsForNav(events, nav) {
  if (nav === "responses") return events.filter((event) => event.type === "form");
  if (nav === "decisions") return events.filter((event) => event.type === "decision");
  return events;
}

function syncIcons() {
  if (!window.lucide || !window.lucide.createIcons) return;
  window.lucide.createIcons({
    attrs: {
      "aria-hidden": "true",
      "stroke-width": "2.1"
    }
  });
}

function eventIconName(kind) {
  return {
    schedule: "calendar-days",
    roles: "users",
    opinion: "message-circle",
    retro: "rotate-ccw",
    checkin: "circle-check-big",
    location: "map-pin",
    roadmap_input: "map",
    daily_report: "clipboard-list",
    decision_roles: "circle-check-big",
    decision_meeting_time: "calendar-days",
    decision_meeting_location: "map-pin",
    decision_general: "badge-check",
    survey: "vote"
  }[kind] || "vote";
}

function eventIcon(kind) {
  return `<i data-lucide="${eventIconName(kind)}"></i>`;
}

function memberInitial(name) {
  const chars = Array.from(String(name || "?").trim());
  return chars[0] || "?";
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

function renderRolePreferences(form) {
  const responses = form && Array.isArray(form.responses) ? form.responses : [];
  if (!responses.length) return "";
  const cards = responses.map((response) => {
    const answers = response.answers || {};
    const prefs = Array.isArray(answers.roles) ? answers.roles : [];
    const chips = prefs.length
      ? prefs.map((role, index) => `<span class="preference-chip"><span class="preference-rank">${index + 1}</span>${escapeText(role)}</span>`).join("")
      : `<span class="preference-chip">응답 없음</span>`;
    return `
      <article class="preference-card">
        <b>${escapeText(response.nickname || "익명 응답")}</b>
        <div class="preference-list">${chips}</div>
      </article>
    `;
  }).join("");
  return `<div class="preference-grid">${cards}</div>`;
}

function topCount(counts) {
  const entries = Object.entries(counts || {}).sort((a, b) => Number(b[1]) - Number(a[1]));
  return entries[0] || null;
}

function renderResult(result, form) {
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
    const details = form && form.kind === "roles" ? renderRolePreferences(form) : "";
    return `<section class="block"><h3>${escapeText(result.question)}</h3>${renderBars(result.ranking_scores)}${details}</section>`;
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

function renderFormEvent(form, sequence) {
  const when = dt(form.created_at);
  const badges = [
    form.closed ? "마감" : "진행중",
    form.anonymous ? "익명" : "식별",
    `${form.total_responses}응답`
  ];
  const summary = (form.summary || []).map((result) => renderResult(result, form)).join("") || "<section class='block'><p>아직 응답이 없습니다.</p></section>";
  return `
    <article class="event">
      <div class="event-avatar ${escapeText(kindClass(form.kind))}" aria-hidden="true">${eventIcon(form.kind)}</div>
      <section class="card">
        <div class="card-head">
          <div>
            <div class="message-meta">
              <span class="kind ${escapeText(kindClass(form.kind))}">${eventNumber(sequence)} · ${escapeText(kindLabel(form.kind))}</span>
              <time class="when"><b>${escapeText(when.day)}</b><span>${escapeText(when.time)}</span></time>
            </div>
            <h2 class="title">${escapeText(form.title)}</h2>
          </div>
          <div class="meta">${badges.map((b) => `<span class="badge ${b === "진행중" ? "open" : b === "식별" ? "private" : ""}">${escapeText(b)}</span>`).join("")}</div>
        </div>
        <div class="summary">${summary}</div>
      </section>
    </article>
  `;
}

function renderReportEvent(report, sequence) {
  const when = dt(report.created_at || report.report_date);
  const payload = report.payload || {};
  const progress = payload.progress || {};
  const counts = payload.status_counts || {};
  const overdue = (payload.overdue_tasks || []).slice(0, 5);
  const notes = (payload.notes || []).slice(0, 5);
  const dueToday = (payload.due_today_tasks || []).slice(0, 5);
  const future = (payload.future_tasks || []).slice(0, 5);
  const progressText = `${progress.done || 0}/${progress.total || 0} · ${progress.percent || 0}%`;
  return `
    <article class="event">
      <div class="event-avatar daily_report" aria-hidden="true">${eventIcon("daily_report")}</div>
      <section class="card">
        <div class="card-head">
          <div>
            <div class="message-meta">
              <span class="kind daily_report">${eventNumber(sequence)} · ${escapeText(kindLabel("daily_report"))}</span>
              <time class="when"><b>${escapeText(when.day)}</b><span>${escapeText(when.time || report.report_date)}</span></time>
            </div>
            <h2 class="title">${escapeText(report.title || "데일리 리포트")}</h2>
          </div>
          <div class="meta">
            <span class="badge report">진행 ${escapeText(progressText)}</span>
            <span class="badge ${counts.overdue ? "open" : ""}">밀림 ${escapeText(counts.overdue || 0)}</span>
            <span class="badge">오늘 ${escapeText(counts.due_today || 0)}</span>
            <span class="badge">예정 ${escapeText(counts.future || 0)}</span>
          </div>
        </div>
        <div class="summary">
          <section class="block">
            <h3>상태</h3>
            <div class="inline-list">
              <span class="mini">완료 ${escapeText(counts.done || 0)}</span>
              <span class="mini">진행 ${escapeText(counts.doing || 0)}</span>
              <span class="mini">대기 ${escapeText(counts.todo || 0)}</span>
              <span class="mini">응답 ${escapeText(payload.checkin_response_count || 0)}</span>
            </div>
          </section>
          <section class="block">
            <h3>오늘 볼 일</h3>
            <ul class="answers">${dueToday.length ? dueToday.map((task) => `<li>${escapeText(task.title)}${task.assignee ? ` · ${escapeText(task.assignee)}` : ""}</li>`).join("") : "<li>오늘 날짜에 걸린 미완료 todo가 없습니다.</li>"}</ul>
          </section>
          <section class="block">
            <h3>남은 밀린 일</h3>
            <ul class="answers">${overdue.length ? overdue.map((task) => `<li>${escapeText(task.title)}${task.assignee ? ` · ${escapeText(task.assignee)}` : ""}</li>`).join("") : "<li>남은 밀린 일이 없습니다.</li>"}</ul>
          </section>
          <section class="block">
            <h3>앞으로 예정된 일</h3>
            <ul class="answers">${future.length ? future.map((task) => `<li>${escapeText(taskScheduleLabel(task))} · ${escapeText(task.title)}${task.assignee ? ` · ${escapeText(task.assignee)}` : ""}</li>`).join("") : "<li>앞으로 예정된 미완료 todo가 없습니다.</li>"}</ul>
          </section>
          ${notes.length ? `<section class="block"><h3>기타 메모</h3><ul class="answers">${notes.map((note) => `<li>${escapeText(note.member)}: ${escapeText(note.text)}</li>`).join("")}</ul></section>` : ""}
        </div>
      </section>
    </article>
  `;
}

function formatDateTime(value) {
  const date = value ? new Date(value) : null;
  if (!date || Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("ko-KR", {
    month: "numeric",
    day: "numeric",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function formatTime(value) {
  const date = value ? new Date(value) : null;
  if (!date || Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
}

function formatDecisionRange(startAt, endAt) {
  const start = startAt ? new Date(startAt) : null;
  const end = endAt ? new Date(endAt) : null;
  if (!start || Number.isNaN(start.getTime())) return "";
  if (!end || Number.isNaN(end.getTime())) return formatDateTime(startAt);
  const sameDay = start.toDateString() === end.toDateString();
  return sameDay ? `${formatDateTime(startAt)} - ${formatTime(endAt)}` : `${formatDateTime(startAt)} - ${formatDateTime(endAt)}`;
}

function decisionDisplayTitle(decision) {
  if (decision.kind === "roles") return "역할 분배 확정";
  if (decision.kind === "meeting_time" && decision.source === "notify_room") return "회의 시간 공지";
  if (decision.kind === "meeting_time") return decision.title || "회의 확정";
  if (decision.kind === "meeting_location") return decision.title || "장소 확정";
  return decision.title || "결정 기록";
}

function renderDecisionSummary(decision) {
  const payload = decision && typeof decision.payload === "object" && decision.payload ? decision.payload : {};
  const assignments = Array.isArray(payload.assignments) ? payload.assignments : [];
  if (decision.kind === "roles" && assignments.length) {
    const cards = assignments.map((assignment) => `
      <article class="assignment-card">
        <b>${escapeText(assignment.nickname || "멤버")}</b>
        <span class="assignment-role">${escapeText(assignment.role || "역할 미정")}</span>
      </article>
    `).join("");
    return `
      <section class="block">
        <h3>확정된 역할</h3>
        <div class="assignment-grid">${cards}</div>
      </section>
    `;
  }
  if (decision.kind === "meeting_time") {
    const range = formatDecisionRange(payload.start_at, payload.end_at);
    const createdCount = Array.isArray(payload.created) ? payload.created.length : null;
    const failedCount = Array.isArray(payload.failed) ? payload.failed.length : null;
    const status = [
      createdCount != null ? `캘린더 등록 ${createdCount}명` : "",
      failedCount ? `실패 ${failedCount}명` : ""
    ].filter(Boolean).join(" · ");
    const note = payload.message || (!range ? decision.summary : "");
    return `
      <section class="block">
        <div class="decision-callout">
          ${range ? `<span class="decision-time">${escapeText(range)}</span>` : ""}
          <p class="decision-title">${escapeText(payload.title || decision.title || "회의 시간이 확정되었습니다.")}</p>
          ${status ? `<p class="decision-note">${escapeText(status)}</p>` : ""}
          ${note ? `<p class="decision-note">${escapeText(note)}</p>` : ""}
        </div>
      </section>
    `;
  }
  return `<section class="block"><p>${escapeText(decision.summary || "요약이 없습니다.")}</p></section>`;
}

function renderDecisionEvent(decision, sequence) {
  const when = dt(decision.created_at);
  const kind = `decision_${decision.kind || "general"}`;
  return `
    <article class="event">
      <div class="event-avatar ${escapeText(kindClass(kind))}" aria-hidden="true">${eventIcon(kind)}</div>
      <section class="card">
        <div class="card-head">
          <div>
            <div class="message-meta">
              <span class="kind ${escapeText(kindClass(kind))}">${eventNumber(sequence)} · ${escapeText(kindLabel(kind))}</span>
              <time class="when"><b>${escapeText(when.day)}</b><span>${escapeText(when.time)}</span></time>
            </div>
            <h2 class="title">${escapeText(decisionDisplayTitle(decision))}</h2>
          </div>
          <div class="meta"><span class="badge report">확정</span></div>
        </div>
        <div class="summary">${renderDecisionSummary(decision)}</div>
      </section>
    </article>
  `;
}

function timelineEvents() {
  const formEvents = forms.map((form) => ({type: "form", at: form.created_at, data: form}));
  const reportEvents = dailyReports.map((report) => ({type: "report", at: report.created_at || report.report_date, data: report}));
  const decisionEvents = collapseDecisionEvents(decisions.map((decision) => ({type: "decision", at: decision.created_at, data: decision})));
  const events = [...formEvents, ...reportEvents, ...decisionEvents].map((event, order) => ({...event, order}));
  const chronological = events.slice().sort((a, b) => {
    const diff = eventTime(a) - eventTime(b);
    return diff || a.order - b.order;
  });
  chronological.forEach((event, index) => {
    event.sequence = index + 1;
  });
  return chronological.slice().sort((a, b) => {
    const diff = eventTime(b) - eventTime(a);
    return diff || b.order - a.order;
  });
}

function filteredEvents(events) {
  return visibleEventsForNav(events, activeNav);
}

function renderTimelineEvent(event) {
  const sequence = event.sequence || 1;
  if (event.type === "report") return renderReportEvent(event.data, sequence);
  if (event.type === "decision") return renderDecisionEvent(event.data, sequence);
  return renderFormEvent(event.data, sequence);
}

function renderFeed() {
  const timeline = document.getElementById("timeline");
  const events = filteredEvents(currentEvents);
  const emptyText = {
    responses: "아직 투표/폼 기록이 없습니다.",
    decisions: "아직 확정 결정이 없습니다.",
    all: "투표, 체크인, 리포트, 확정 결정이 이곳에 최신순으로 쌓입니다."
  }[activeNav] || "투표, 체크인, 리포트, 확정 결정이 이곳에 최신순으로 쌓입니다.";
  timeline.innerHTML = events.length
    ? events.map(renderTimelineEvent).join("")
    : `<div class="empty"><h2>아직 기록이 없습니다</h2><p>${escapeText(emptyText)}</p></div>`;
  syncIcons();
  if (window.enhanceLiquidGlass) window.enhanceLiquidGlass();
}

function setActiveNav(nav) {
  activeNav = nav;
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.nav === nav);
  });
  if (nav === "tasks") {
    renderFeed();
    const panel = document.querySelector("#roadmapPanel:not([hidden]) .roadmap-panel");
    if (panel) {
      panel.scrollIntoView({behavior: "smooth", block: "start"});
      panel.classList.add("is-focused");
      window.setTimeout(() => panel.classList.remove("is-focused"), 1200);
    }
    return;
  }
  renderFeed();
}

function bindNav() {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.onclick = function() {
      if (button.disabled) return;
      setActiveNav(button.dataset.nav || "all");
    };
  });
}

function render() {
  currentEvents = timelineEvents();
  const taskTotal = (roadmap.task_layer_summary && roadmap.task_layer_summary.todos) || (roadmap.progress && roadmap.progress.total) || 0;
  const responseTotal = forms.reduce((sum, form) => sum + Number(form.total_responses || 0), 0);
  const visibleAllEvents = visibleEventsForNav(currentEvents, "all");
  const visibleDecisionEvents = visibleEventsForNav(currentEvents, "decisions");
  document.getElementById("roomName").textContent = dashboard.room.name;
  document.getElementById("roomInvite").textContent = `초대 코드 ${dashboard.room.invite_code}`;
  document.getElementById("subtitle").textContent = `방에서 만든 투표, 체크인, 리포트, 확정 결정을 최신순으로 모았습니다.`;
  document.getElementById("formCount").textContent = visibleAllEvents.length;
  document.getElementById("memberCount").textContent = dashboard.members.length;
  document.getElementById("taskCount").textContent = taskTotal;
  document.getElementById("responseCount").textContent = responseTotal;
  document.getElementById("sideEventCount").textContent = visibleAllEvents.length;
  document.getElementById("sideTaskCount").textContent = taskTotal;
  document.getElementById("sideResponseCount").textContent = responseTotal;
  document.getElementById("sideDecisionCount").textContent = visibleDecisionEvents.length;

  const members = document.getElementById("members");
  members.innerHTML = dashboard.members.map((member) => `<span class="member" data-initial="${escapeText(memberInitial(member.nickname))}"><span class="member-copy"><b>${escapeText(member.nickname)}</b><span class="member-role">${escapeText(member.role || "역할 미정")}</span></span></span>`).join("");
  const shell = document.getElementById("dashboardShell");
  const roadmapPanel = document.getElementById("roadmapPanel");
  const roadmapHtml = renderRoadmap();
  roadmapPanel.innerHTML = roadmapHtml;
  roadmapPanel.hidden = !roadmapHtml;
  shell.classList.toggle("is-feed-only", !roadmapHtml);
  const taskNav = document.querySelector('[data-nav="tasks"]');
  if (taskNav) taskNav.disabled = !roadmapHtml;
  bindNav();
  renderFeed();
  syncIcons();
  if (window.enhanceLiquidGlass) window.enhanceLiquidGlass();
}

render();
</script>
__APP_REACT_LIQUID_BOOTSTRAP__
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
    page = (
        _PAGE.replace("__TITLE__", title)
        .replace("__APP_FONT_LINKS__", APP_FONT_LINKS)
        .replace("__APP_REACT_LIQUID_IMPORTS__", APP_REACT_LIQUID_IMPORTS)
        .replace("__APP_LUCIDE_SCRIPT__", APP_LUCIDE_SCRIPT)
        .replace("__APP_REACT_LIQUID_BOOTSTRAP__", APP_REACT_LIQUID_BOOTSTRAP)
        .replace("__APP_THEME_CSS__", APP_THEME_CSS)
        .replace("__DATA__", safe_data)
    )
    return HTMLResponse(page)


def register_dashboard_routes(mcp) -> None:
    """대시보드 웹 라우트를 MCP 서버(Starlette)에 등록한다."""
    mcp.custom_route("/dashboard/rooms/{room_id}", methods=["GET"])(view_room_dashboard)
