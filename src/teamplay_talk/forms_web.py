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
<link href="https://unpkg.com/survey-core@1.12.63/defaultV2.min.css" rel="stylesheet">
<script src="https://unpkg.com/survey-core@1.12.63/survey.core.min.js"></script>
<script src="https://unpkg.com/survey-js-ui@1.12.63/survey-js-ui.min.js"></script>
<style>
 body{font-family:system-ui,-apple-system,sans-serif;max-width:920px;margin:1.5rem auto;padding:0 1rem;background:#f6f7f8;color:#1f2328}
 #done{text-align:center;padding:3rem 1rem}
 #err{color:#b00;white-space:pre-wrap;padding:1rem;border:1px solid #f3c;border-radius:8px}
 .schedule{background:#fff;border:1px solid #e6e8eb;border-radius:8px;box-shadow:0 1px 8px rgba(0,0,0,.04);overflow:hidden}
 .schedule__head{padding:1.25rem 1.25rem 1rem;border-bottom:1px solid #edf0f2}
 .schedule__title{margin:0;font-size:1.35rem;line-height:1.25}
 .schedule__desc{margin:.45rem 0 0;color:#5b626b;line-height:1.5}
 .schedule__legend{display:flex;gap:.5rem;flex-wrap:wrap;margin-top:.9rem;color:#4d5560;font-size:.94rem}
 .schedule__pill{display:inline-flex;align-items:center;gap:.3rem;border:1px solid #e1e4e8;border-radius:999px;padding:.3rem .6rem;background:#fafbfc}
 .schedule__body{padding:1rem}
 .schedule__desktop{display:none;overflow:auto;border:1px solid #e8ebef;border-radius:8px;background:#fff}
 .schedule__table{border-collapse:separate;border-spacing:0;min-width:max-content;width:100%}
 .schedule__table th,.schedule__table td{border-bottom:1px solid #edf0f2;border-right:1px solid #edf0f2;padding:.55rem;text-align:center;background:#fff}
 .schedule__table th:first-child,.schedule__table td:first-child{position:sticky;left:0;z-index:2;text-align:left;min-width:76px;background:#fbfcfd;font-weight:700}
 .schedule__table th{position:sticky;top:0;z-index:3;background:#fbfcfd;font-weight:800;white-space:nowrap}
 .schedule__table th:first-child{z-index:4}
 .schedule__table tr:last-child td{border-bottom:0}
 .schedule__cell{display:flex;gap:.35rem;justify-content:center}
 .choice{min-width:44px;height:40px;border:1px solid #d7dce2;border-radius:8px;background:#fff;color:#4b5563;font-weight:800;font-size:1rem;cursor:pointer}
 .choice:active{transform:translateY(1px)}
 .choice--o.is-selected{background:#e8f7ee;border-color:#34a853;color:#137333}
 .choice--x.is-selected{background:#fff0f0;border-color:#e5534b;color:#b3261e}
 .schedule__mobile{display:block}
 .date-tabs{display:flex;gap:.5rem;overflow-x:auto;padding:.1rem .05rem .8rem;scroll-snap-type:x proximity}
 .date-tab{flex:0 0 auto;min-height:44px;border:1px solid #dde2e7;border-radius:999px;background:#fff;padding:.55rem .85rem;font-weight:800;color:#3f4650;scroll-snap-align:start}
 .date-tab.is-active{background:#1f2328;color:#fff;border-color:#1f2328}
 .day-panel{border:1px solid #e8ebef;border-radius:8px;background:#fff;overflow:hidden}
 .day-panel__head{position:sticky;top:0;background:#fff;z-index:2;padding:1rem;border-bottom:1px solid #edf0f2}
 .day-panel__date{font-weight:900;font-size:1.15rem}
 .day-actions{display:flex;gap:.5rem;margin-top:.75rem}
 .day-action{min-height:40px;border:1px solid #dce1e6;border-radius:8px;background:#fafbfc;padding:0 .7rem;font-weight:750;color:#4b5563}
 .slot-row{display:grid;grid-template-columns:72px 1fr;gap:.75rem;align-items:center;padding:.75rem 1rem;border-bottom:1px solid #edf0f2}
 .slot-row:last-child{border-bottom:0}
 .slot-row__time{font-weight:850;color:#3b424c}
 .slot-row__choices{display:block}
 .slot-row__choices .schedule__cell{display:grid;grid-template-columns:1fr 1fr;gap:.55rem}
 .slot-row .choice{width:100%;height:46px}
 .schedule__note{margin-top:1rem}
 .schedule__note label{display:block;font-weight:800;margin-bottom:.5rem}
 .schedule__note textarea{box-sizing:border-box;width:100%;min-height:96px;border:1px solid #dce1e6;border-radius:8px;padding:.8rem;font:inherit;resize:vertical;background:#fff}
 .schedule__submit{display:flex;justify-content:flex-end;margin-top:1rem}
 .schedule__submit button{min-height:46px;border:0;border-radius:8px;background:#1f2328;color:#fff;font-weight:900;padding:0 1.2rem;font-size:1rem}
 @media (min-width:760px){
   .schedule__desktop{display:block}
   .schedule__mobile{display:none}
   .schedule__body{padding:1.25rem}
 }
 @media (max-width:480px){
   body{margin:.75rem auto;padding:0 .65rem}
   .schedule__head{padding:1rem}
   .schedule__title{font-size:1.15rem}
   .schedule__body{padding:.75rem}
 }
</style></head><body>
<div id="surveyContainer"></div>
<div id="done" style="display:none"><h2>응답 완료 ✅</h2><p>제출해 주셔서 감사합니다!</p></div>
<script>
  var surveyJson = __SCHEMA__;
  function showErr(m){ document.getElementById("surveyContainer").innerHTML = '<div id="err">폼 로드 오류: ' + m + '</div>'; }
  function postAnswers(data) {
    return fetch(window.location.pathname + window.location.search, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(data)
    }).then(function(){
      document.getElementById("surveyContainer").style.display = "none";
      document.getElementById("done").style.display = "block";
    });
  }
  function findAvailabilityElement(schema) {
    var elements = (schema && schema.elements) || [];
    for (var i = 0; i < elements.length; i++) {
      if (elements[i].type === "matrixdropdown" && elements[i].name === "availability") return elements[i];
    }
    return null;
  }
  function compactAvailability(data) {
    var out = {};
    Object.keys(data).forEach(function(row){
      var cols = {};
      Object.keys(data[row]).forEach(function(col){
        if (data[row][col]) cols[col] = data[row][col];
      });
      if (Object.keys(cols).length) out[row] = cols;
    });
    return out;
  }
  function makeButton(label, className) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = className;
    b.textContent = label;
    return b;
  }
  function renderAvailabilityForm(schema, grid) {
    var container = document.getElementById("surveyContainer");
    var dates = (grid.columns || []).map(function(c){ return {name:c.name, title:c.title || c.name}; });
    var rows = grid.rows || [];
    var note = ((schema.elements || []).filter(function(el){ return el.type === "comment"; })[0]) || null;
    var values = {};
    rows.forEach(function(row){ values[row] = {}; });

    var root = document.createElement("div");
    root.className = "schedule";
    var head = document.createElement("div");
    head.className = "schedule__head";
    var h1 = document.createElement("h1");
    h1.className = "schedule__title";
    h1.textContent = schema.title || "회의 가능 시간";
    head.appendChild(h1);
    if (schema.description) {
      var desc = document.createElement("p");
      desc.className = "schedule__desc";
      desc.textContent = String(schema.description).replace(/\\*\\*/g, "");
      head.appendChild(desc);
    }
    var legend = document.createElement("div");
    legend.className = "schedule__legend";
    ["O 가능", "X 절대 불가", "미선택 보통"].forEach(function(txt){
      var pill = document.createElement("span");
      pill.className = "schedule__pill";
      pill.textContent = txt;
      legend.appendChild(pill);
    });
    head.appendChild(legend);
    root.appendChild(head);

    var body = document.createElement("div");
    body.className = "schedule__body";
    var desktop = document.createElement("div");
    desktop.className = "schedule__desktop";
    var table = document.createElement("table");
    table.className = "schedule__table";
    var thead = document.createElement("thead");
    var hr = document.createElement("tr");
    var corner = document.createElement("th");
    corner.textContent = "시간";
    hr.appendChild(corner);
    dates.forEach(function(date){
      var th = document.createElement("th");
      th.textContent = date.title;
      hr.appendChild(th);
    });
    thead.appendChild(hr);
    table.appendChild(thead);
    var tbody = document.createElement("tbody");
    table.appendChild(tbody);
    desktop.appendChild(table);

    var mobile = document.createElement("div");
    mobile.className = "schedule__mobile";
    var tabs = document.createElement("div");
    tabs.className = "date-tabs";
    var panel = document.createElement("div");
    panel.className = "day-panel";
    mobile.appendChild(tabs);
    mobile.appendChild(panel);
    var activeDate = dates[0] ? dates[0].name : "";

    function selected(row, col, val) {
      return values[row] && values[row][col] === val;
    }
    function setValue(row, col, val) {
      if (!values[row]) values[row] = {};
      values[row][col] = values[row][col] === val ? "" : val;
      draw();
    }
    function setWholeDay(col, val) {
      rows.forEach(function(row){
        if (!values[row]) values[row] = {};
        values[row][col] = val;
      });
      draw();
    }
    function drawChoice(row, col) {
      var wrap = document.createElement("div");
      wrap.className = "schedule__cell";
      var o = makeButton("O", "choice choice--o" + (selected(row, col, "O") ? " is-selected" : ""));
      var x = makeButton("X", "choice choice--x" + (selected(row, col, "X") ? " is-selected" : ""));
      o.onclick = function(){ setValue(row, col, "O"); };
      x.onclick = function(){ setValue(row, col, "X"); };
      wrap.appendChild(o);
      wrap.appendChild(x);
      return wrap;
    }
    function drawDesktop() {
      tbody.textContent = "";
      rows.forEach(function(row){
        var tr = document.createElement("tr");
        var time = document.createElement("td");
        time.textContent = row;
        tr.appendChild(time);
        dates.forEach(function(date){
          var td = document.createElement("td");
          td.appendChild(drawChoice(row, date.name));
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
    }
    function drawMobileTabs() {
      tabs.textContent = "";
      dates.forEach(function(date){
        var b = makeButton(date.title, "date-tab" + (date.name === activeDate ? " is-active" : ""));
        b.onclick = function(){ activeDate = date.name; draw(); };
        tabs.appendChild(b);
      });
    }
    function drawMobilePanel() {
      panel.textContent = "";
      var date = dates.filter(function(d){ return d.name === activeDate; })[0] || dates[0];
      if (!date) return;
      var ph = document.createElement("div");
      ph.className = "day-panel__head";
      var dt = document.createElement("div");
      dt.className = "day-panel__date";
      dt.textContent = date.title;
      ph.appendChild(dt);
      var actions = document.createElement("div");
      actions.className = "day-actions";
      var allO = makeButton("이날 전부 O", "day-action");
      var allX = makeButton("이날 전부 X", "day-action");
      var clear = makeButton("비우기", "day-action");
      allO.onclick = function(){ setWholeDay(date.name, "O"); };
      allX.onclick = function(){ setWholeDay(date.name, "X"); };
      clear.onclick = function(){ setWholeDay(date.name, ""); };
      actions.appendChild(allO);
      actions.appendChild(allX);
      actions.appendChild(clear);
      ph.appendChild(actions);
      panel.appendChild(ph);
      rows.forEach(function(row){
        var sr = document.createElement("div");
        sr.className = "slot-row";
        var time = document.createElement("div");
        time.className = "slot-row__time";
        time.textContent = row;
        var choices = document.createElement("div");
        choices.className = "slot-row__choices";
        choices.appendChild(drawChoice(row, date.name));
        sr.appendChild(time);
        sr.appendChild(choices);
        panel.appendChild(sr);
      });
    }
    function draw() {
      drawDesktop();
      drawMobileTabs();
      drawMobilePanel();
    }

    body.appendChild(desktop);
    body.appendChild(mobile);
    var noteBox = null;
    if (note) {
      var noteWrap = document.createElement("div");
      noteWrap.className = "schedule__note";
      var label = document.createElement("label");
      label.textContent = note.title || "기타 건의사항";
      noteBox = document.createElement("textarea");
      noteBox.name = note.name;
      noteWrap.appendChild(label);
      noteWrap.appendChild(noteBox);
      body.appendChild(noteWrap);
    }
    var submit = document.createElement("div");
    submit.className = "schedule__submit";
    var submitButton = document.createElement("button");
    submitButton.type = "button";
    submitButton.textContent = schema.completeText || "제출";
    submitButton.onclick = function(){
      var payload = {availability: compactAvailability(values)};
      if (noteBox && noteBox.value.trim()) payload[note.name] = noteBox.value.trim();
      postAnswers(payload).catch(function(e){ showErr("제출 실패: " + e); });
    };
    submit.appendChild(submitButton);
    body.appendChild(submit);
    root.appendChild(body);
    container.textContent = "";
    container.appendChild(root);
    draw();
  }
  window.onerror = function(msg, src, line, col){ showErr(msg + ' (' + line + ':' + col + ')'); return true; };
  try {
    var availabilityElement = findAvailabilityElement(surveyJson);
    if (availabilityElement) {
      renderAvailabilityForm(surveyJson, availabilityElement);
    } else if (typeof Survey === "undefined") {
      showErr("SurveyJS 로드 실패 (네트워크 확인)");
    } else {
      var survey = new Survey.Model(surveyJson);
      survey.completeText = "제출";
      survey.onComplete.add(function(sender){
        postAnswers(sender.data).catch(function(e){ showErr("제출 실패: " + e); });
      });
      var el = document.getElementById("surveyContainer");
      if (typeof survey.render === "function") {
        survey.render(el);
      } else if (typeof SurveyUI !== "undefined" && SurveyUI.renderSurvey) {
        SurveyUI.renderSurvey(survey, el);
      } else {
        showErr("render 메서드 없음 (survey-js-ui 로드 확인)");
      }
    }
  } catch(e) { showErr((e && e.message) ? e.message : String(e)); }
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
    # 전원 응답 시 즉시 마감 + 드라이버 nudge (시간 마감은 스케줄러가 담당)
    if form.get("close_on_all") and not form["closed"] and storage.all_members_responded(form_id):
        from . import triggers

        await triggers.process_closed_form(form_id)
    return JSONResponse({"ok": True})


def register_form_routes(mcp) -> None:
    """폼 웹 라우트를 MCP 서버(Starlette)에 등록한다."""
    mcp.custom_route("/form/{form_id}", methods=["GET"])(view_form)
    mcp.custom_route("/form/{form_id}", methods=["POST"])(submit_form)
