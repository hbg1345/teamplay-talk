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
from .ui_theme import APP_FONT_LINKS, APP_REACT_LIQUID_BOOTSTRAP, APP_REACT_LIQUID_IMPORTS, APP_THEME_CSS

_PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
__APP_FONT_LINKS__
__APP_REACT_LIQUID_IMPORTS__
<link href="https://unpkg.com/survey-core@1.12.63/defaultV2.min.css" rel="stylesheet">
<script src="https://unpkg.com/survey-core@1.12.63/survey.core.min.js"></script>
<script src="https://unpkg.com/survey-js-ui@1.12.63/survey-js-ui.min.js"></script>
<style>
 __APP_THEME_CSS__
 body{padding:24px clamp(12px,3vw,36px) 52px}
 #surveyContainer,#done{position:relative;z-index:1;width:min(920px,100%);margin:0 auto}
 #done{margin-top:16px;text-align:center;padding:42px 24px}
 #done h2{margin:0 0 8px;font-family:var(--font-display);font-size:1.35rem;line-height:1.2;font-weight:850}
 #done p{margin:0;color:var(--muted);line-height:1.5}
 #err{color:var(--rose);white-space:pre-wrap;padding:1rem;border:1px solid rgba(191,64,88,.28);border-radius:var(--radius);background:var(--rose-soft);box-shadow:var(--shadow-md)}
 .sd-root-modern{background:transparent!important;color:var(--ink);font-family:inherit;--sjs-primary-backcolor:var(--workspace);--sjs-primary-backcolor-light:var(--workspace-soft);--sjs-border-default:var(--glass-line);--sjs-general-backcolor:transparent;--sjs-general-backcolor-dim:transparent;--sjs-general-forecolor:var(--ink);--sjs-general-forecolor-light:var(--muted)}
 .sd-container-modern{background:transparent!important}
 .sd-body,.sd-page{background:transparent!important}
 .sd-title{color:var(--ink)!important;font-weight:850;letter-spacing:0}
 .sd-description,.sd-question__description{color:var(--muted);line-height:1.55;white-space:pre-line}
 .sd-header__text{max-width:920px;margin:0 auto}
 .sd-container-modern__title{position:relative!important;box-shadow:none!important;border:0!important;margin:0 auto 28px!important;padding:0 0 24px!important}
 .sd-container-modern__title:after{content:"";position:absolute;left:0;right:0;bottom:0;height:1px;background:linear-gradient(90deg,transparent,rgba(37,33,29,.22) 14%,rgba(254,229,0,.22) 50%,rgba(37,33,29,.18) 86%,transparent);box-shadow:0 1px 0 rgba(255,255,255,.72)}
 .sd-page__title{font-family:var(--font-display);font-size:1.9rem;line-height:1.14;margin-bottom:8px;font-weight:850;color:var(--ink)!important}
 .sd-page__description{font-size:1rem;margin-bottom:18px}
 .sd-question{position:relative!important;isolation:isolate!important;border:0!important;border-radius:var(--radius)!important;background:radial-gradient(460px 180px at 14% 0%,rgba(255,255,255,.78),transparent 66%),linear-gradient(180deg,rgba(255,255,255,.68),rgba(255,250,240,.46)),rgba(255,251,241,.58)!important;box-shadow:0 0 0 1px rgba(33,24,8,.12),inset 0 1px 0 rgba(255,255,255,.86),inset 0 -1px 0 rgba(255,255,255,.26),0 26px 72px rgba(45,36,18,.12)!important;overflow:hidden!important;backdrop-filter:blur(20px) saturate(1.34) contrast(1.02);-webkit-backdrop-filter:blur(20px) saturate(1.34) contrast(1.02)}
 .sd-question:before{content:"";position:absolute;inset:0;z-index:0;pointer-events:none;border-radius:inherit;padding:1px;background:linear-gradient(135deg,rgba(255,255,255,.92),rgba(255,255,255,.12) 36%,rgba(254,229,0,.22) 62%,rgba(37,33,29,.10));-webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude;opacity:.82}
 .sd-question:after{content:"";position:absolute;inset:1px;z-index:0;pointer-events:none;border-radius:calc(var(--radius) - 1px);background:radial-gradient(280px 86px at 18% 0%,rgba(255,255,255,.34),transparent 72%),linear-gradient(116deg,rgba(255,255,255,.20),transparent 42%,rgba(255,255,255,.10) 70%,transparent);mix-blend-mode:screen;opacity:.64}
 .sd-question > *{position:relative;z-index:1}
 .sd-question__header{padding-bottom:8px}
 .sd-question__title{font-weight:800;color:var(--ink);line-height:1.35}
 .sd-input,.sd-comment,.sd-dropdown,.sd-tagbox{border:0!important;border-radius:var(--radius)!important;background:radial-gradient(260px 86px at 12% 0%,rgba(255,255,255,.82),transparent 68%),linear-gradient(180deg,rgba(255,255,255,.72),rgba(255,250,240,.54))!important;color:var(--ink)!important;box-shadow:0 0 0 1px rgba(33,24,8,.13),inset 0 1px 0 rgba(255,255,255,.88),inset 0 -1px 0 rgba(33,24,8,.035),0 12px 28px rgba(45,36,18,.055)!important;backdrop-filter:blur(14px) saturate(1.22);-webkit-backdrop-filter:blur(14px) saturate(1.22)}
 .sd-input:focus,.sd-comment:focus,.sd-dropdown:focus{outline:0!important;box-shadow:0 0 0 1px rgba(37,33,29,.28),0 0 0 4px rgba(254,229,0,.26),inset 0 1px 0 rgba(255,255,255,.88),0 14px 32px rgba(45,36,18,.08)!important}
 .sd-selectbase{display:grid!important;gap:10px!important}
 .sd-selectbase__item,.sd-ranking-item{border:0!important;border-radius:var(--radius)!important;background:radial-gradient(220px 72px at 12% 0%,rgba(255,255,255,.76),transparent 68%),linear-gradient(180deg,rgba(255,255,255,.68),rgba(255,250,240,.52))!important;box-shadow:0 0 0 1px rgba(33,24,8,.11),inset 0 1px 0 rgba(255,255,255,.82),0 10px 24px rgba(45,36,18,.05)!important}
 .sd-selectbase__item{display:flex!important;align-items:stretch!important;min-height:52px!important;padding:0!important;overflow:hidden!important}
 .sd-selectbase__label{display:flex!important;align-items:center!important;gap:12px!important;width:100%!important;min-height:52px!important;padding:0 16px!important;cursor:pointer!important}
 .sd-item__decorator{flex:0 0 24px!important;margin:0!important}
 .sd-item__control-label{flex:1 1 auto!important;min-width:0!important;line-height:1.35!important;padding-top:1px!important;color:var(--ink)!important;word-break:keep-all;overflow-wrap:anywhere}
 .sd-selectbase__item.sd-item--checked{box-shadow:0 0 0 1px rgba(216,188,0,.34),inset 0 1px 0 rgba(255,255,255,.82),0 12px 26px rgba(254,229,0,.10)!important}
 .sd-selectbase__item:focus-within,.sd-ranking-item:focus-within{box-shadow:0 0 0 3px rgba(254,229,0,.26)!important}
 .sd-btn,.sd-navigation__complete-btn{position:relative!important;overflow:hidden!important;border:0!important;border-radius:var(--radius)!important;background:radial-gradient(120px 52px at 18% 0%,rgba(255,255,255,.70),transparent 70%),linear-gradient(135deg,#fff178,var(--kakao-yellow))!important;color:var(--kakao-black)!important;font-weight:850!important;box-shadow:0 0 0 1px rgba(118,98,0,.18),inset 0 1px 0 rgba(255,255,255,.84),inset 0 -1px 0 rgba(118,98,0,.20),0 16px 34px rgba(254,229,0,.23)!important}
 .sd-btn:hover,.sd-navigation__complete-btn:hover{transform:translateY(-1px);box-shadow:0 0 0 1px rgba(118,98,0,.22),inset 0 1px 0 rgba(255,255,255,.88),inset 0 -1px 0 rgba(118,98,0,.22),0 18px 40px rgba(254,229,0,.28)!important}
 .sd-btn:active,.sd-navigation__complete-btn:active{transform:scale(.985)}
 .sd-progress__bar{background:linear-gradient(90deg,var(--workspace),var(--warning))!important}
 .sd-ranking-item__icon,.sd-ranking-item__index{background:var(--workspace-soft)!important;color:var(--workspace)!important}
 .sd-completedpage{display:none!important}
 .schedule{position:relative;isolation:isolate;border:0;border-radius:var(--radius);background:radial-gradient(520px 190px at 14% 0%,rgba(255,255,255,.80),transparent 66%),linear-gradient(180deg,rgba(255,255,255,.68),rgba(255,250,240,.48)),rgba(255,251,241,.58);box-shadow:0 0 0 1px rgba(33,24,8,.12),inset 0 1px 0 rgba(255,255,255,.88),inset 0 -1px 0 rgba(255,255,255,.26),0 26px 72px rgba(45,36,18,.13);overflow:hidden;backdrop-filter:blur(20px) saturate(1.34) contrast(1.02);-webkit-backdrop-filter:blur(20px) saturate(1.34) contrast(1.02)}
 .schedule:before{content:"";position:absolute;inset:0;z-index:0;pointer-events:none;border-radius:inherit;padding:1px;background:linear-gradient(135deg,rgba(255,255,255,.92),rgba(255,255,255,.12) 36%,rgba(254,229,0,.22) 62%,rgba(37,33,29,.10));-webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude;opacity:.82}
 .schedule:after{content:"";position:absolute;inset:1px;z-index:0;pointer-events:none;border-radius:calc(var(--radius) - 1px);background:radial-gradient(300px 92px at 18% 0%,rgba(255,255,255,.35),transparent 72%),linear-gradient(116deg,rgba(255,255,255,.20),transparent 42%,rgba(255,255,255,.10) 70%,transparent);mix-blend-mode:screen;opacity:.64}
 .schedule > *{position:relative;z-index:1}
 .schedule__head{padding:1.35rem 1.35rem 1.05rem;border-bottom:1px solid rgba(33,24,8,.10);background:linear-gradient(180deg,rgba(255,255,255,.34),rgba(255,255,255,.12))}
 .schedule__title{margin:0;font-family:var(--font-display);font-size:1.85rem;line-height:1.14;letter-spacing:0;font-weight:850}
 .schedule__desc{margin:.55rem 0 0;color:var(--muted);line-height:1.55}
 .schedule__legend{display:flex;gap:.5rem;flex-wrap:wrap;margin-top:1rem;color:var(--muted);font-size:.92rem}
 .schedule__pill{display:inline-flex;align-items:center;gap:.3rem;border:0;border-radius:999px;padding:.34rem .62rem;background:radial-gradient(90px 36px at 18% 0%,rgba(255,255,255,.72),transparent 72%),linear-gradient(180deg,rgba(255,255,255,.68),rgba(255,250,240,.48));box-shadow:0 0 0 1px rgba(33,24,8,.10),inset 0 1px 0 rgba(255,255,255,.80);font-weight:700}
 .schedule__body{padding:1rem}
 .schedule__desktop{display:none;overflow:auto;border:0;border-radius:var(--radius);background:rgba(255,250,240,.46);box-shadow:0 0 0 1px rgba(33,24,8,.10),inset 0 1px 0 rgba(255,255,255,.74)}
 .schedule__table{border-collapse:separate;border-spacing:0;min-width:max-content;width:100%}
 .schedule__table th,.schedule__table td{border-bottom:1px solid rgba(33,24,8,.11);border-right:1px solid rgba(33,24,8,.11);padding:.55rem;text-align:center;background:rgba(255,252,244,.68)}
 .schedule__table th:first-child,.schedule__table td:first-child{position:sticky;left:0;z-index:2;text-align:left;min-width:76px;background:rgba(255,250,240,.94);font-weight:760}
 .schedule__table th{position:sticky;top:0;z-index:3;background:rgba(255,250,240,.94);font-weight:800;white-space:nowrap}
 .schedule__table th:first-child{z-index:4}
 .schedule__date-title{display:block;margin-bottom:.38rem;font-weight:850}
 .day-actions--desktop{justify-content:center;margin:.25rem 0 0;gap:.32rem}
 .day-actions--desktop .day-action{min-height:30px;border-radius:999px;padding:0 .5rem;font-size:.72rem;font-weight:820}
 .schedule__table tr:last-child td{border-bottom:0}
 .schedule__cell{display:flex;gap:.35rem;justify-content:center}
 .choice{min-width:44px;height:40px;border:0;border-radius:var(--radius);background:radial-gradient(82px 36px at 18% 0%,rgba(255,255,255,.74),transparent 72%),linear-gradient(180deg,rgba(255,255,255,.70),rgba(255,250,240,.50));color:var(--ink-soft);font-weight:800;font-size:1rem;cursor:pointer;box-shadow:0 0 0 1px rgba(33,24,8,.12),inset 0 1px 0 rgba(255,255,255,.84),inset 0 -1px 0 rgba(33,24,8,.04),0 8px 18px rgba(45,36,18,.06);transition:transform .16s cubic-bezier(.2,.8,.2,1),box-shadow .16s ease,background .16s ease,color .16s ease}
 .choice:hover{transform:translateY(-1px)}
 .choice:active{transform:scale(.985)}
 .choice--o.is-selected{background:radial-gradient(86px 38px at 18% 0%,rgba(255,255,255,.66),transparent 70%),linear-gradient(135deg,#fff276,var(--kakao-yellow));color:var(--kakao-black);box-shadow:0 0 0 1px rgba(216,188,0,.44),inset 0 1px 0 rgba(255,255,255,.84),inset 0 -1px 0 rgba(118,98,0,.12),0 10px 22px rgba(254,229,0,.22)}
 .choice--x.is-selected{background:radial-gradient(86px 38px at 18% 0%,rgba(255,255,255,.62),transparent 70%),linear-gradient(180deg,rgba(255,232,237,.88),rgba(255,244,246,.58));box-shadow:0 0 0 1px rgba(191,64,88,.32),inset 0 1px 0 rgba(255,255,255,.82),0 10px 22px rgba(191,64,88,.10);color:#8b2639}
 .schedule__mobile{display:block}
 .date-tabs{display:flex;gap:.5rem;overflow-x:auto;padding:.1rem .05rem .8rem;scroll-snap-type:x proximity}
 .date-tab{flex:0 0 auto;min-height:44px;border:0;border-radius:999px;background:radial-gradient(96px 40px at 18% 0%,rgba(255,255,255,.74),transparent 72%),linear-gradient(180deg,rgba(255,255,255,.70),rgba(255,250,240,.50));padding:.55rem .85rem;font-weight:760;color:var(--ink-soft);scroll-snap-align:start;box-shadow:0 0 0 1px rgba(33,24,8,.12),inset 0 1px 0 rgba(255,255,255,.84),0 9px 20px rgba(45,36,18,.06);transition:transform .16s cubic-bezier(.2,.8,.2,1),box-shadow .16s ease,background .16s ease,color .16s ease}
 .date-tab:hover{transform:translateY(-1px)}
 .date-tab:active{transform:scale(.985)}
 .date-tab.is-active{background:radial-gradient(102px 42px at 20% 0%,rgba(255,255,255,.18),transparent 70%),linear-gradient(135deg,var(--workspace),var(--workspace-2));color:#fff8e8;box-shadow:0 0 0 1px rgba(255,255,255,.14),inset 0 1px 0 rgba(255,255,255,.16),0 10px 22px rgba(37,33,29,.18)}
 .day-panel{border:0;border-radius:var(--radius);background:rgba(255,250,240,.46);box-shadow:0 0 0 1px rgba(33,24,8,.11),inset 0 1px 0 rgba(255,255,255,.74);overflow:hidden}
 .day-panel__head{position:sticky;top:0;background:radial-gradient(220px 72px at 18% 0%,rgba(255,255,255,.66),transparent 72%),linear-gradient(180deg,rgba(255,252,244,.82),rgba(255,250,240,.58));z-index:2;padding:1rem;border-bottom:1px solid rgba(33,24,8,.10)}
 .day-panel__date{font-weight:850;font-size:1.1rem}
 .day-actions{display:flex;gap:.5rem;margin-top:.75rem}
 .day-action{min-height:40px;border:0;border-radius:var(--radius);background:radial-gradient(84px 36px at 18% 0%,rgba(255,255,255,.72),transparent 72%),linear-gradient(180deg,rgba(255,255,255,.70),rgba(255,250,240,.50));padding:0 .7rem;font-weight:760;color:var(--ink-soft);box-shadow:0 0 0 1px rgba(33,24,8,.12),inset 0 1px 0 rgba(255,255,255,.84),0 8px 18px rgba(45,36,18,.06);transition:transform .16s cubic-bezier(.2,.8,.2,1),box-shadow .16s ease,background .16s ease,color .16s ease}
 .day-action:hover{transform:translateY(-1px)}
 .day-action:active{transform:scale(.985)}
 .day-actions .day-action:first-child{background:radial-gradient(88px 38px at 18% 0%,rgba(255,255,255,.66),transparent 70%),linear-gradient(135deg,rgba(255,242,118,.88),rgba(254,229,0,.26));box-shadow:0 0 0 1px rgba(216,188,0,.30),inset 0 1px 0 rgba(255,255,255,.84),0 8px 18px rgba(254,229,0,.10);color:#5d4e00}
 .day-actions .day-action:nth-child(2){background:radial-gradient(88px 38px at 18% 0%,rgba(255,255,255,.62),transparent 70%),linear-gradient(180deg,rgba(255,232,237,.86),rgba(255,244,246,.54));box-shadow:0 0 0 1px rgba(191,64,88,.26),inset 0 1px 0 rgba(255,255,255,.82),0 8px 18px rgba(191,64,88,.08);color:#8b2639}
 .slot-row{display:grid;grid-template-columns:72px 1fr;gap:.75rem;align-items:center;padding:.75rem 1rem;border-bottom:1px solid rgba(33,24,8,.11)}
 .slot-row:last-child{border-bottom:0}
 .slot-row__time{font-weight:820;color:var(--ink-soft);font-variant-numeric:tabular-nums}
 .slot-row__choices{display:block}
 .slot-row__choices .schedule__cell{display:grid;grid-template-columns:1fr 1fr;gap:.55rem}
 .slot-row .choice{width:100%;height:46px}
 .schedule__note{margin-top:1rem}
 .schedule__note label{display:block;font-weight:800;margin-bottom:.5rem}
 .schedule__note textarea{box-sizing:border-box;width:100%;min-height:96px;border:0;border-radius:var(--radius);padding:.85rem;font:inherit;resize:vertical;background:radial-gradient(260px 86px at 12% 0%,rgba(255,255,255,.82),transparent 68%),linear-gradient(180deg,rgba(255,255,255,.72),rgba(255,250,240,.54));color:var(--ink);box-shadow:0 0 0 1px rgba(33,24,8,.13),inset 0 1px 0 rgba(255,255,255,.88),0 12px 28px rgba(45,36,18,.055)}
 .schedule__submit{display:flex;justify-content:flex-end;margin-top:1rem}
 .schedule__submit button{min-height:46px;border:0;border-radius:var(--radius);background:radial-gradient(120px 52px at 18% 0%,rgba(255,255,255,.70),transparent 70%),linear-gradient(135deg,#fff178,var(--kakao-yellow));color:var(--kakao-black);font-weight:850;padding:0 1.2rem;font-size:1rem;box-shadow:0 0 0 1px rgba(118,98,0,.18),inset 0 1px 0 rgba(255,255,255,.84),inset 0 -1px 0 rgba(118,98,0,.20),0 16px 34px rgba(254,229,0,.23);transition:transform .16s cubic-bezier(.2,.8,.2,1),box-shadow .16s ease}
 .schedule__submit button:hover{transform:translateY(-1px)}
 .schedule__submit button:active{transform:scale(.985)}
 .sd-question.liquid-react-mounted,.schedule.liquid-react-mounted,.day-panel.liquid-react-mounted{background:rgba(255,251,241,.38)!important;box-shadow:0 18px 54px rgba(45,36,18,.10),inset 0 1px 0 rgba(255,255,255,.62)!important}
 .date-tab.liquid-react-mounted,.day-action.liquid-react-mounted{background:rgba(255,251,241,.34)!important;box-shadow:0 0 0 1px rgba(33,24,8,.12),inset 0 1px 0 rgba(255,255,255,.38),0 10px 26px rgba(45,36,18,.07)!important;backdrop-filter:blur(8px) saturate(1.06);-webkit-backdrop-filter:blur(8px) saturate(1.06)}
 .date-tab.is-active.liquid-react-mounted{background:rgba(37,33,29,.82)!important;color:#fff8e8!important;box-shadow:0 0 0 1px rgba(255,255,255,.13),inset 0 1px 0 rgba(255,255,255,.14),0 10px 24px rgba(37,33,29,.17)!important}
 .day-actions .day-action:first-child.liquid-react-mounted{background:rgba(254,229,0,.18)!important;color:#5d4e00!important}
 .day-actions .day-action:nth-child(2).liquid-react-mounted{background:rgba(255,232,237,.34)!important;color:#8b2639!important}
 .date-tab.liquid-react-mounted .liquid-react-fill,.day-action.liquid-react-mounted .liquid-react-fill{background:linear-gradient(180deg,rgba(255,255,255,.14),rgba(255,255,255,.03)),rgba(255,255,255,.02)}
 .sd-btn.liquid-react-mounted,.sd-navigation__complete-btn.liquid-react-mounted,.schedule__submit button.liquid-react-mounted{background:rgba(255,251,241,.42)!important;box-shadow:0 0 0 1px rgba(33,24,8,.12),0 10px 28px rgba(45,36,18,.08)!important}
 .sd-navigation__complete-btn.liquid-react-mounted,.schedule__submit button.liquid-react-mounted{color:var(--kakao-black)!important}
 .sd-question{background:rgba(255,252,244,.76)!important;box-shadow:0 0 0 1px rgba(33,24,8,.10),0 12px 32px rgba(45,36,18,.07)!important;backdrop-filter:blur(8px) saturate(1.04)!important;-webkit-backdrop-filter:blur(8px) saturate(1.04)!important}
 .sd-question:before,.sd-question:after,.schedule:before,.schedule:after{display:none!important}
 .sd-input,.sd-comment,.sd-dropdown,.sd-tagbox,.schedule__note textarea{background:rgba(255,253,247,.82)!important;box-shadow:0 0 0 1px rgba(33,24,8,.12),inset 0 1px 0 rgba(255,255,255,.54)!important;backdrop-filter:none!important;-webkit-backdrop-filter:none!important}
 .sd-selectbase__item,.sd-ranking-item{background:rgba(255,253,247,.76)!important;box-shadow:0 0 0 1px rgba(33,24,8,.10)!important}
 .sd-selectbase__item{padding:0!important}
 .schedule{background:rgba(255,252,244,.70)!important;box-shadow:0 0 0 1px rgba(33,24,8,.10),0 16px 42px rgba(45,36,18,.08)!important;backdrop-filter:blur(10px) saturate(1.04)!important;-webkit-backdrop-filter:blur(10px) saturate(1.04)!important}
 .schedule__head,.day-panel__head{background:rgba(255,252,244,.62)!important}
 .schedule__pill,.choice,.date-tab,.day-action{background:linear-gradient(180deg,rgba(255,255,255,.62),rgba(255,250,240,.38))!important;box-shadow:0 0 0 1px rgba(33,24,8,.10),0 8px 18px rgba(45,36,18,.045)!important}
 .choice--o.is-selected{background:linear-gradient(180deg,rgba(255,242,118,.86),rgba(254,229,0,.62))!important;box-shadow:0 0 0 1px rgba(216,188,0,.34),0 9px 20px rgba(254,229,0,.14)!important}
 .choice--x.is-selected{background:linear-gradient(180deg,rgba(255,242,245,.86),rgba(255,232,237,.58))!important;box-shadow:0 0 0 1px rgba(191,64,88,.24),0 9px 20px rgba(191,64,88,.06)!important}
 .date-tab.is-active{background:linear-gradient(180deg,rgba(37,33,29,.92),rgba(37,33,29,.76))!important;color:#fff8e8!important;box-shadow:0 0 0 1px rgba(255,255,255,.12),0 9px 20px rgba(37,33,29,.14)!important}
 .day-panel{background:rgba(255,252,244,.58)!important;box-shadow:0 0 0 1px rgba(33,24,8,.10)!important}
 @media (min-width:760px){
   .schedule__desktop{display:block}
   .schedule__mobile{display:none}
   .schedule__body{padding:1.25rem}
 }
 @media (max-width:480px){
   body{padding:.75rem .65rem 32px}
   .schedule__head{padding:1rem}
   .schedule__title{font-size:1.25rem}
   .schedule__body{padding:.75rem}
 }
</style></head><body>
<div id="surveyContainer"></div>
<div id="done" class="glass-panel" style="display:none"><h2>응답 완료</h2><p>제출해 주셔서 감사합니다.</p></div>
<script>
  var surveyJson = __SCHEMA__;
  function showErr(m){
    document.getElementById("done").style.display = "none";
    document.getElementById("surveyContainer").style.display = "block";
    document.getElementById("surveyContainer").innerHTML = '<div id="err">폼 로드 오류: ' + m + '</div>';
  }
  function showDone(){
    document.getElementById("surveyContainer").style.display = "none";
    document.getElementById("done").style.display = "block";
    requestLiquidEnhance();
  }
  function postAnswers(data) {
    showDone();
    return fetch(window.location.pathname + window.location.search, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(data)
    }).then(function(response){
      if (!response.ok) throw new Error("HTTP " + response.status);
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
  function requestLiquidEnhance() {
    window.requestAnimationFrame(function(){
      if (window.enhanceLiquidGlass) window.enhanceLiquidGlass();
    });
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
      var title = document.createElement("span");
      title.className = "schedule__date-title";
      title.textContent = date.title;
      th.appendChild(title);
      var actions = document.createElement("div");
      actions.className = "day-actions day-actions--desktop";
      var allO = makeButton("전부 O", "day-action");
      var allX = makeButton("전부 X", "day-action");
      var clear = makeButton("비우기", "day-action");
      allO.onclick = function(){ setWholeDay(date.name, "O"); };
      allX.onclick = function(){ setWholeDay(date.name, "X"); };
      clear.onclick = function(){ setWholeDay(date.name, ""); };
      actions.appendChild(allO);
      actions.appendChild(allX);
      actions.appendChild(clear);
      th.appendChild(actions);
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
    requestLiquidEnhance();
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
      survey.showCompletedPage = false;
      survey.completedHtml = "";
      survey.onComplete.add(function(sender){
        postAnswers(sender.data).catch(function(e){ showErr("제출 실패: " + e); });
      });
      var el = document.getElementById("surveyContainer");
      if (typeof survey.render === "function") {
        survey.render(el);
        requestLiquidEnhance();
      } else if (typeof SurveyUI !== "undefined" && SurveyUI.renderSurvey) {
        SurveyUI.renderSurvey(survey, el);
        requestLiquidEnhance();
      } else {
        showErr("render 메서드 없음 (survey-js-ui 로드 확인)");
      }
    }
  } catch(e) { showErr((e && e.message) ? e.message : String(e)); }
</script>
__APP_REACT_LIQUID_BOOTSTRAP__
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
    form_id: int | None = None
    if "room_public_id" in request.path_params and "form_public_id" in request.path_params:
        form = storage.get_form_by_public_ids(
            str(request.path_params["room_public_id"]),
            str(request.path_params["form_public_id"]),
        )
        if form is not None:
            form_id = int(form["id"])
    else:
        try:
            form_id = int(request.path_params["form_id"])
        except (ValueError, KeyError):
            return None, None
    if form_id is None:
        return None, None
    member_id = None
    token = request.path_params.get("invite_token") or request.query_params.get("t")
    if token:
        inv = storage.get_invite(token)
        if inv and inv["form_id"] == form_id:
            member_id = inv["member_id"]
    return form_id, member_id


async def view_form(request: Request) -> HTMLResponse:
    """GET /form/<id>[?t=token] — SurveyJS 폼 렌더링."""
    form_id, member_id = _resolve(request)
    if form_id is None:
        return _message("잘못된 요청", "폼 ID가 올바르지 않습니다.", 400)
    form = storage.get_form(form_id)
    if form is None:
        return _message("폼을 찾을 수 없음", "존재하지 않는 폼입니다.", 404)
    if form["closed"]:
        return _message("마감된 폼", "이 폼은 응답이 마감되었습니다.", 403)
    if not form["anonymous"] and member_id is None:
        return _message("개인 링크 필요", "이 폼은 개인별 링크로만 응답할 수 있습니다.", 403)
    if member_id is not None and not storage.is_form_member(form_id, member_id):
        return _message("권한이 없습니다", "이 방의 현재 멤버만 응답할 수 있습니다.", 403)

    schema = form.get("schema_json") or {"elements": []}
    schema_str = jsonlib.dumps(schema, ensure_ascii=False).replace("</", "<\\/")
    page = (
        _PAGE.replace("__TITLE__", html.escape(str(form["title"])))
        .replace("__APP_FONT_LINKS__", APP_FONT_LINKS)
        .replace("__APP_REACT_LIQUID_IMPORTS__", APP_REACT_LIQUID_IMPORTS)
        .replace("__APP_REACT_LIQUID_BOOTSTRAP__", APP_REACT_LIQUID_BOOTSTRAP)
        .replace("__APP_THEME_CSS__", APP_THEME_CSS)
        .replace("__SCHEMA__", schema_str)
    )
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
    if not form["anonymous"] and member_id is None:
        return JSONResponse({"ok": False, "error": "personal link required"}, status_code=403)
    if member_id is not None and not storage.is_form_member(form_id, member_id):
        return JSONResponse({"ok": False, "error": "not a current room member"}, status_code=403)

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
    mcp.custom_route(
        "/r/{room_public_id}/f/{form_public_id}",
        methods=["GET"],
    )(view_form)
    mcp.custom_route(
        "/r/{room_public_id}/f/{form_public_id}",
        methods=["POST"],
    )(submit_form)
    mcp.custom_route(
        "/r/{room_public_id}/f/{form_public_id}/{invite_token}",
        methods=["GET"],
    )(view_form)
    mcp.custom_route(
        "/r/{room_public_id}/f/{form_public_id}/{invite_token}",
        methods=["POST"],
    )(submit_form)
    mcp.custom_route("/form/{form_id}", methods=["GET"])(view_form)
    mcp.custom_route("/form/{form_id}", methods=["POST"])(submit_form)
