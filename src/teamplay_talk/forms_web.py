"""네이티브 폼 웹 페이지.

``create_poll`` 도구로 만든 폼을 누구나 브라우저로 응답할 수 있도록
``GET/POST /form/<id>`` 를 제공한다. 응답은 Postgres(form_responses/answers)에
저장된다.
"""

from __future__ import annotations

import html
from typing import Any

from starlette.requests import Request
from starlette.responses import HTMLResponse

from . import storage

_PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
 body{{font-family:system-ui,-apple-system,sans-serif;max-width:640px;margin:2rem auto;padding:0 1rem;color:#222}}
 .card{{border:1px solid #e3e3e3;border-radius:12px;padding:1.2rem 1.4rem;margin-bottom:1rem}}
 h1{{font-size:1.4rem}} .q{{font-weight:600;margin:.2rem 0 .6rem}}
 label{{display:block;padding:.3rem 0}} input[type=text]{{width:100%;padding:.5rem;border:1px solid #ccc;border-radius:8px}}
 button{{background:#2c5cff;color:#fff;border:0;border-radius:10px;padding:.7rem 1.4rem;font-size:1rem;cursor:pointer}}
 .desc{{color:#666}}
</style></head><body>
<h1>{title}</h1>
{desc}
<form method="post">
{name_field}
{questions}
<button type="submit">제출</button>
</form>
</body></html>"""


def _render_question(q: dict[str, Any]) -> str:
    qid = q["id"]
    text = html.escape(q["text"])
    field = f"q_{qid}"
    if q["qtype"] == "text":
        body = f'<input type="text" name="{field}" />'
    else:
        input_type = "checkbox" if q["qtype"] == "multi" else "radio"
        opts = q.get("options") or []
        body = "".join(
            f'<label><input type="{input_type}" name="{field}" '
            f'value="{html.escape(str(o))}" /> {html.escape(str(o))}</label>'
            for o in opts
        )
    return f'<div class="card"><div class="q">{text}</div>{body}</div>'


def _render_form(form: dict[str, Any], questions: list[dict[str, Any]]) -> str:
    desc = f'<p class="desc">{html.escape(form["description"])}</p>' if form.get("description") else ""
    name_field = ""
    if not form["anonymous"]:
        name_field = (
            '<div class="card"><div class="q">이름</div>'
            '<input type="text" name="respondent" /></div>'
        )
    return _PAGE.format(
        title=html.escape(form["title"]),
        desc=desc,
        name_field=name_field,
        questions="".join(_render_question(q) for q in questions),
    )


def _message(title: str, msg: str, status: int = 200) -> HTMLResponse:
    page = (
        f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)}</title></head>"
        f'<body style="font-family:system-ui;max-width:640px;margin:3rem auto;text-align:center">'
        f"<h1>{html.escape(title)}</h1><p>{html.escape(msg)}</p></body></html>"
    )
    return HTMLResponse(page, status_code=status)


async def view_form(request: Request) -> HTMLResponse:
    """GET /form/<id> — 폼 페이지 렌더링."""
    try:
        form_id = int(request.path_params["form_id"])
    except (ValueError, KeyError):
        return _message("잘못된 요청", "폼 ID가 올바르지 않습니다.", 400)

    data = storage.get_form(form_id)
    if data is None:
        return _message("폼을 찾을 수 없음", "존재하지 않는 폼입니다.", 404)
    if data["form"]["closed"]:
        return _message("마감된 폼", "이 폼은 응답이 마감되었습니다.", 403)
    return HTMLResponse(_render_form(data["form"], data["questions"]))


async def submit_form(request: Request) -> HTMLResponse:
    """POST /form/<id> — 응답 저장."""
    try:
        form_id = int(request.path_params["form_id"])
    except (ValueError, KeyError):
        return _message("잘못된 요청", "폼 ID가 올바르지 않습니다.", 400)

    data = storage.get_form(form_id)
    if data is None:
        return _message("폼을 찾을 수 없음", "존재하지 않는 폼입니다.", 404)
    if data["form"]["closed"]:
        return _message("마감된 폼", "이 폼은 응답이 마감되었습니다.", 403)

    formdata = await request.form()
    answers: list[dict[str, Any]] = []
    for q in data["questions"]:
        field = f"q_{q['id']}"
        if q["qtype"] == "multi":
            values = formdata.getlist(field)
        else:
            v = formdata.get(field)
            values = [v] if v else []
        for value in values:
            if value:
                answers.append({"question_id": q["id"], "value": str(value)})

    respondent = None
    if not data["form"]["anonymous"]:
        respondent = (formdata.get("respondent") or "").strip() or None

    storage.save_response(form_id, answers, respondent=respondent)
    return _message("응답 완료 ✅", "제출해 주셔서 감사합니다!")


def register_form_routes(mcp: Any) -> None:
    """폼 웹 라우트를 MCP 서버(Starlette)에 등록한다."""
    mcp.custom_route("/form/{form_id}", methods=["GET"])(view_form)
    mcp.custom_route("/form/{form_id}", methods=["POST"])(submit_form)
