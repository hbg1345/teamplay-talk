"""네이티브 폼 웹 페이지 (SurveyJS 렌더).

create_poll이 만든 SurveyJS JSON 폼을 누구나 브라우저로 응답한다.
- 익명 폼: 공유 링크 1개 (``/form/<id>``)
- identified 폼: 멤버별 매직링크 (``/form/<id>?t=<token>``) → 로그인 없이 신원 식별

응답(SurveyJS 결과 객체)은 Postgres(``form_responses.answers_json``)에 저장된다.
폼이 모두의 입력/출력 통로 — 팀원은 AI·앱·로그인 없이 카톡 링크 클릭만 하면 된다.
"""

from __future__ import annotations

import html
import json as jsonlib

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from . import storage

_PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link href="https://unpkg.com/survey-core@1/survey-core.min.css" rel="stylesheet">
<script src="https://unpkg.com/survey-core@1/survey.core.min.js"></script>
<script src="https://unpkg.com/survey-js-ui@1/survey-js-ui.min.js"></script>
<style>
 body{font-family:system-ui,-apple-system,sans-serif;max-width:680px;margin:1.5rem auto;padding:0 1rem}
 #done{text-align:center;padding:3rem 1rem}
</style></head><body>
<div id="surveyContainer"></div>
<div id="done" style="display:none"><h2>응답 완료 ✅</h2><p>제출해 주셔서 감사합니다!</p></div>
<script>
  const surveyJson = __SCHEMA__;
  const survey = new Survey.Model(surveyJson);
  survey.completeText = "제출";
  survey.onComplete.add(function(sender) {
    fetch(window.location.pathname + window.location.search, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(sender.data)
    }).then(function() {
      document.getElementById("surveyContainer").style.display = "none";
      document.getElementById("done").style.display = "block";
    });
  });
  survey.render("surveyContainer");
</script>
</body></html>"""


def _message(title: str, msg: str, status: int = 200) -> HTMLResponse:
    page = (
        f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)}</title></head>"
        f'<body style="font-family:system-ui;max-width:640px;margin:3rem auto;text-align:center">'
        f"<h1>{html.escape(title)}</h1><p>{html.escape(msg)}</p></body></html>"
    )
    return HTMLResponse(page, status_code=status)


def _resolve(request: Request) -> tuple[int | None, int | None]:
    """경로/쿼리에서 form_id + (매직링크면) member_id 를 해석한다."""
    try:
        form_id = int(request.path_params["form_id"])
    except (ValueError, KeyError):
        return None, None
    member_id = None
    token = request.query_params.get("t")
    if token:
        inv = storage.get_invite(token)
        if inv and inv["form_id"] == form_id:
            member_id = inv["member_id"]
    return form_id, member_id


async def view_form(request: Request) -> HTMLResponse:
    """GET /form/<id>[?t=token] — SurveyJS 폼 렌더링."""
    form_id, _member = _resolve(request)
    if form_id is None:
        return _message("잘못된 요청", "폼 ID가 올바르지 않습니다.", 400)
    form = storage.get_form(form_id)
    if form is None:
        return _message("폼을 찾을 수 없음", "존재하지 않는 폼입니다.", 404)
    if form["closed"]:
        return _message("마감된 폼", "이 폼은 응답이 마감되었습니다.", 403)

    schema = form.get("schema_json") or {"elements": []}
    schema_str = jsonlib.dumps(schema, ensure_ascii=False).replace("</", "<\\/")
    page = _PAGE.replace("__TITLE__", html.escape(str(form["title"]))).replace("__SCHEMA__", schema_str)
    return HTMLResponse(page)


async def submit_form(request: Request) -> JSONResponse:
    """POST /form/<id>[?t=token] — SurveyJS 결과(JSON) 저장."""
    form_id, member_id = _resolve(request)
    if form_id is None:
        return JSONResponse({"ok": False, "error": "bad form id"}, status_code=400)
    form = storage.get_form(form_id)
    if form is None:
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    if form["closed"]:
        return JSONResponse({"ok": False, "error": "closed"}, status_code=403)

    try:
        answers = await request.json()
    except Exception:
        answers = {}
    if not isinstance(answers, dict):
        answers = {}

    storage.save_response(form_id, answers, member_id=member_id)
    # (Phase4) close_on_all 체크 → 마감 + 드라이버 nudge 는 스케줄러 단계에서 추가
    return JSONResponse({"ok": True})


def register_form_routes(mcp) -> None:
    """폼 웹 라우트를 MCP 서버(Starlette)에 등록한다."""
    mcp.custom_route("/form/{form_id}", methods=["GET"])(view_form)
    mcp.custom_route("/form/{form_id}", methods=["POST"])(submit_form)
