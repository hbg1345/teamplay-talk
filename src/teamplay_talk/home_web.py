"""teamplay-talk 홈페이지(랜딩) — https://teamplay-talk.tech/

디자인 원칙:
- **리퀴드 글래스가 기본** (프로스티드·반투명, 뒤가 비침). 그라데이션은 포인트로만.
- 라이트 라벤더/화이트 배경 (아이콘과 통일). 브랜드/파비콘은 실제 아이콘 PNG.
- 히어로 채팅 데모: 채팅 카드 + **한 줄 캡슐 선택바(가로 스크롤)** + **분리된 원형 버튼**
  (iOS 26 Apple News+ 식 — 캡슐과 액션 버튼이 떨어져 떠있음).
"""

from __future__ import annotations

from pathlib import Path

from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse

_FONT_CSS = "https://cdn.jsdelivr.net/gh/wanteddev/wanted-sans@v1.0.3/packages/wanted-sans/fonts/webfonts/variable/split/WantedSansVariable.min.css"
_STATIC = Path(__file__).resolve().parent / "static"

_CSS = """
:root{
  --bg:#F4F1FB; --bg-2:#ECE7F8; --ink:#1b1730; --ink-soft:#3c3653; --muted:#6d6688; --quiet:#9990b0;
  --violet:#7c3aed; --violet-2:#6d5cf5; --cyan:#22b8ff;
  --card:#ffffff; --line:rgba(96,66,168,.14); --line-hi:rgba(96,66,168,.28);
  --accent:linear-gradient(120deg,#9333ea,#6d5cf5 52%,#22b8ff);
  --shadow:0 16px 44px rgba(80,52,140,.12); --shadow-sm:0 6px 20px rgba(80,52,140,.08);
  --radius:16px; --radius-lg:24px;
  --font:"Wanted Sans Variable","Wanted Sans","Pretendard","Apple SD Gothic Neo","Noto Sans KR",system-ui,-apple-system,sans-serif;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;background:var(--bg)}
body{
  margin:0;color:var(--ink);font-family:var(--font);font-size:16px;line-height:1.6;
  word-break:keep-all;-webkit-font-smoothing:antialiased;overflow-x:hidden;
  background:
    radial-gradient(1100px 760px at 82% -8%, rgba(34,184,255,.13), transparent 58%),
    radial-gradient(900px 700px at -10% 12%, rgba(147,51,234,.13), transparent 56%),
    radial-gradient(900px 820px at 50% 116%, rgba(91,108,255,.09), transparent 55%),
    var(--bg);
}
::selection{background:rgba(124,58,237,.22)}
a{color:inherit;text-decoration:none}
img,svg{display:block;max-width:100%}
.wrap{max-width:1120px;margin:0 auto;padding:0 24px}
.eyebrow{font-size:12px;font-weight:700;letter-spacing:.22em;color:var(--violet);text-transform:uppercase}
h1,h2,h3{margin:0;font-weight:800;letter-spacing:-.02em;line-height:1.18;color:var(--ink)}
h2{font-size:clamp(28px,4.4vw,44px)}
.sec{padding:104px 0}
.sec-head{max-width:660px;margin-bottom:52px}
.sec-head p{color:var(--muted);margin:14px 0 0;font-size:17px}

/* ── 리퀴드 글래스 (기본 디자인 언어) ── */
.lg{
  position:relative;
  background:rgba(255,255,255,.5);
  backdrop-filter:blur(26px) saturate(1.8);-webkit-backdrop-filter:blur(26px) saturate(1.8);
  border:1px solid rgba(255,255,255,.6);
  box-shadow:0 10px 34px rgba(70,50,120,.14), inset 0 1px 1px rgba(255,255,255,.85), inset 0 -6px 14px rgba(124,92,200,.06);
}
/* 콘텐츠 카드는 읽기 우선 — 평평한 화이트 */
.card{background:rgba(255,255,255,.6);border:1px solid rgba(255,255,255,.62);border-radius:var(--radius);
  box-shadow:var(--shadow-sm), inset 0 1px 1px rgba(255,255,255,.8);
  backdrop-filter:blur(14px) saturate(1.4);-webkit-backdrop-filter:blur(14px) saturate(1.4)}

/* ── 나브 ── */
.nav{position:fixed;top:18px;left:0;right:0;z-index:50}
.nav-pill{display:flex;align-items:center;gap:6px;width:fit-content;max-width:calc(100% - 20px);margin:0 auto;padding:8px 10px 8px 12px;border-radius:999px}
.nav-brand{display:flex;align-items:center;gap:9px;font-weight:800;font-size:15px;letter-spacing:-.01em;margin-right:6px;color:var(--ink)}
.nav-brand img{width:28px;height:28px;border-radius:8px}
.nav-links{display:flex;gap:2px;margin-left:14px}
.nav-links a{padding:8px 12px;border-radius:999px;font-size:14px;color:var(--ink-soft);transition:background .18s,color .18s;white-space:nowrap}
.nav-links a:hover{background:rgba(124,58,237,.09);color:var(--ink)}
.nav-links a.active{color:var(--violet);background:rgba(255,255,255,.9);box-shadow:0 2px 8px rgba(80,52,140,.14)}
.nav-cta{margin-left:8px;padding:9px 18px;border-radius:999px;font-size:14px;font-weight:700;color:#fff;
  background:var(--accent);box-shadow:0 8px 20px rgba(109,92,245,.3);transition:transform .16s,box-shadow .16s;white-space:nowrap}
.nav-cta:hover{transform:translateY(-1px);box-shadow:0 12px 28px rgba(109,92,245,.4)}
@media(max-width:760px){.nav-links{display:none}.nav-cta{margin-left:auto}}

/* ── 히어로 ── */
.hero{position:relative;min-height:100svh;display:flex;align-items:center;padding:138px 0 88px;overflow:hidden}
.hero-inner{position:relative;z-index:2;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,.96fr);gap:52px;align-items:center;width:100%}
.hero-inner>*{min-width:0}
.hero-badge{display:inline-flex;align-items:center;gap:8px;padding:7px 15px;border-radius:999px;font-size:13px;font-weight:600;color:var(--ink-soft)}
.hero-badge .dot{width:7px;height:7px;border-radius:50%;background:var(--violet);box-shadow:0 0 10px var(--violet)}
.hero h1{font-size:clamp(40px,6.1vw,64px);letter-spacing:-.035em;margin:24px 0 0}
.mlg{position:relative;display:inline-block;color:var(--violet);isolation:isolate}
.mlg::after{content:"";position:absolute;left:-3%;right:-3%;bottom:-17px;height:18px;border-radius:999px;z-index:1;pointer-events:none;opacity:0;background:linear-gradient(100deg,rgba(255,255,255,0),rgba(255,255,255,.62) 30%,rgba(34,184,255,.22) 50%,rgba(124,58,237,.18) 70%,rgba(255,255,255,0));filter:blur(5px);transform:scaleX(.72);transform-origin:center;animation:mlgPrismBreath 8.8s cubic-bezier(.22,1,.36,1) 1.2s infinite}
.wave-underline{position:absolute;left:-4%;bottom:-15px;width:108%;height:16px;overflow:visible;z-index:2;filter:drop-shadow(0 5px 10px rgba(124,58,237,.13))}
.wave-underline path{stroke-linejoin:round;vector-effect:non-scaling-stroke;opacity:.96}
@keyframes mlgPrismBreath{0%,76%,100%{opacity:0;transform:scaleX(.72)}82%,90%{opacity:.38;transform:scaleX(1)}}
.hero-sub{color:var(--muted);font-size:clamp(16px,1.6vw,19px);max-width:500px;margin:28px 0 0}
.hero-ctas{display:flex;gap:14px;margin-top:36px;flex-wrap:wrap}
.btn{display:inline-flex;align-items:center;gap:9px;padding:15px 27px;border-radius:999px;font-size:16px;font-weight:700;border:0;cursor:pointer;transition:transform .16s cubic-bezier(.2,.8,.2,1),box-shadow .2s}
.btn:active{transform:scale(.97)}
.btn-primary{color:#fff;background:var(--accent);box-shadow:0 14px 38px rgba(109,92,245,.32)}
.btn-primary:hover{transform:translateY(-2px);box-shadow:0 20px 50px rgba(109,92,245,.44)}
.btn-ghost{color:var(--ink);border-radius:999px}
.btn-ghost:hover{transform:translateY(-2px)}
@media(max-width:920px){.hero-inner{grid-template-columns:minmax(0,1fr);gap:40px}.hero{padding-top:118px}.hero-visual{order:2}}

/* ── 히어로 채팅 데모 ── */
.hero-visual{position:relative;display:flex;align-items:center;justify-content:center;min-width:0}
.chat-demo{display:flex;flex-direction:column;gap:14px;width:100%;max-width:460px;min-width:0}
.cd-card{border-radius:24px;padding:18px}
.cd-head{display:flex;align-items:center;gap:8px;font-size:12.5px;font-weight:700;color:var(--muted);padding:2px 4px 12px;border-bottom:1px solid var(--line);margin-bottom:12px}
.cd-head .cd-dot{width:7px;height:7px;border-radius:50%;background:#22c55e;box-shadow:0 0 8px #22c55e}
.cd-window{display:flex;flex-direction:column;gap:9px;height:360px;overflow-y:auto;padding:2px}
.cd-msg{max-width:86%;padding:11px 15px;border-radius:16px;font-size:14px;line-height:1.5;overflow-wrap:anywhere;opacity:0;transform:translateY(8px);animation:cdIn .45s cubic-bezier(.2,.8,.2,1) forwards}
.cd-msg.user{align-self:flex-end;background:var(--violet);color:#fff;border-bottom-right-radius:5px;font-weight:600}
.cd-msg.ai{align-self:flex-start;background:rgba(255,255,255,.66);border:1px solid rgba(255,255,255,.7);color:var(--ink-soft);border-bottom-left-radius:5px;backdrop-filter:blur(8px)}
.cd-msg.ai b{color:var(--violet);font-weight:700}
.cd-msg.ai span{color:var(--quiet);font-weight:600;font-size:12.5px}
@keyframes cdIn{to{opacity:1;transform:none}}
/* News+ 식 도크: 한 줄 캡슐 + 분리된 원형 버튼 */
.cd-dock{display:flex;align-items:stretch;gap:10px}
.cd-bar{flex:1;min-width:0;position:relative;padding:6px;border-radius:999px;overflow:hidden}
.cd-bar::before,.cd-bar::after{content:"";position:absolute;top:1px;bottom:1px;width:34px;pointer-events:none;opacity:0;transition:opacity .2s;z-index:1}
.cd-bar::before{left:1px;border-radius:999px 0 0 999px;background:linear-gradient(270deg,rgba(247,244,252,0),rgba(247,244,252,.94))}
.cd-bar::after{right:1px;border-radius:0 999px 999px 0;background:linear-gradient(90deg,rgba(247,244,252,0),rgba(247,244,252,.94))}
.cd-bar.sc-left::before{opacity:1}
.cd-bar.sc-right::after{opacity:1}
.demo-chips{display:flex;flex-wrap:nowrap;gap:4px;overflow-x:auto;scrollbar-width:none}
.demo-chips::-webkit-scrollbar{display:none}
.demo-chip{flex:none;display:flex;align-items:center;gap:7px;padding:9px 14px;border-radius:999px;font-size:13px;font-weight:600;color:var(--ink-soft);background:transparent;border:0;cursor:pointer;white-space:nowrap;transition:color .18s,background .18s;font-family:inherit}
.demo-chip .ci{width:16px;height:16px;flex:none}
.demo-chip .ci svg{width:16px;height:16px;stroke:currentColor;fill:none;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round}
.demo-chip:hover{color:var(--ink)}
.demo-chips{cursor:grab}
.demo-chips:active{cursor:grabbing}
.demo-chip.active{color:var(--violet);background:rgba(255,255,255,.72);box-shadow:inset 0 1px 1px rgba(255,255,255,.9),0 1px 3px rgba(80,52,140,.12);backdrop-filter:blur(8px) saturate(1.4);-webkit-backdrop-filter:blur(8px) saturate(1.4)}
.cd-replay{flex:none;width:54px;border-radius:999px;display:flex;align-items:center;justify-content:center;font-size:19px;color:var(--violet);cursor:pointer;border:0;font-family:inherit;transition:transform .15s}
.cd-replay:hover{transform:translateY(-1px)}
.cd-replay:active{transform:scale(.94)}
@media(max-width:520px){
  .chat-demo{max-width:100%}
  .cd-card{padding:14px}
  .cd-window{height:300px}
  .cd-msg{max-width:90%;font-size:13.5px}
  .demo-chip{padding:8px 12px;font-size:12.5px}
}

/* ── 작동 방식 ── */
.steps{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-bottom:52px}
.step{padding:26px 24px;border-radius:var(--radius)}
.step .no{font-size:13px;font-weight:800;color:var(--violet);letter-spacing:.12em}
.step h3{font-size:19px;margin:10px 0 8px}
.step p{color:var(--muted);font-size:14.5px;margin:0}
@media(max-width:900px){.steps{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:520px){.steps{grid-template-columns:minmax(0,1fr)}}
.flow-line{display:flex;align-items:center;justify-content:center;gap:10px;flex-wrap:wrap}
.flow-node{padding:10px 18px;border-radius:999px;font-size:13.5px;font-weight:700;color:var(--ink-soft);max-width:100%}
.flow-node b{color:var(--ink)}
.flow-arrow{color:var(--muted);font-size:15px}
@media(max-width:560px){.flow-line{flex-direction:column;gap:8px}.flow-arrow{transform:rotate(90deg)}}

/* ── 워크플로우 ── */
.pipe{position:relative;display:grid;gap:14px}
.pipe-item{position:relative;display:grid;grid-template-columns:56px minmax(0,1fr);gap:18px;align-items:start}
.pipe-item:not(:last-child)::before{content:"";position:absolute;left:27px;top:58px;bottom:-14px;width:2px;background:var(--line-hi)}
.pipe-dot{width:56px;height:56px;border-radius:18px;display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:800;color:var(--violet);z-index:1;background:rgba(255,255,255,.6)}
.pipe-card{padding:22px 26px;border-radius:var(--radius);transition:transform .3s,border-color .3s}
.pipe-card:hover{transform:translateX(4px);border-color:var(--line-hi)}
.pipe-card h3{font-size:18px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.pipe-card .tag{font-size:11.5px;font-weight:700;letter-spacing:.04em;padding:3px 10px;border-radius:999px;border:1px solid var(--line);color:var(--muted)}
.pipe-card p{color:var(--muted);font-size:14.5px;margin:8px 0 0}

/* ── 기능 그리드 ── */
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
@media(max-width:1020px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:560px){.grid{grid-template-columns:minmax(0,1fr)}}
.feat{padding:26px 24px;border-radius:var(--radius);transition:transform .3s,border-color .3s}
.feat:hover{transform:translateY(-4px);border-color:var(--line-hi)}
.feat .ico{width:44px;height:44px;border-radius:13px;display:flex;align-items:center;justify-content:center;margin-bottom:16px;background:rgba(124,58,237,.09);color:var(--violet)}
.feat .ico svg{width:22px;height:22px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.feat h3{font-size:16.5px}
.feat p{color:var(--muted);font-size:13.8px;margin:8px 0 0;line-height:1.6}

/* ── 제작자 ── */
.makers{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
@media(max-width:720px){.makers{grid-template-columns:minmax(0,1fr)}}
.maker{display:flex;gap:20px;padding:28px;border-radius:var(--radius-lg);align-items:center}
.maker .face{width:88px;height:88px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;font-size:27px;font-weight:800;color:#fff;background:var(--violet);overflow:hidden}
.maker.b .face{background:var(--violet-2)}
.maker .face img{width:100%;height:100%;object-fit:cover;object-position:center 12%}
.maker h3{font-size:19px}
.maker .cred{list-style:none;margin:9px 0 0;padding:0;display:flex;flex-direction:column;gap:5px}
.maker .cred li{font-size:13px;color:var(--muted);line-height:1.4}
.maker .cred li b{color:var(--ink);font-weight:700}

/* ── 연결 CTA ── */
.connect{padding:60px min(6vw,72px);border-radius:28px;text-align:center;position:relative;overflow:hidden;background:var(--card)}
.connect h2{position:relative;z-index:1}
.connect p{color:var(--muted);margin:14px auto 0;max-width:480px;position:relative;z-index:1}
.endpoint{position:relative;z-index:1;display:inline-flex;align-items:center;gap:14px;margin-top:30px;padding:10px 12px 10px 22px;border-radius:999px;background:var(--bg-2);cursor:pointer;
  max-width:100%;flex-wrap:nowrap;justify-content:center;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:14px;color:var(--ink-soft);white-space:nowrap;overflow-x:auto}
@media(max-width:480px){.endpoint{font-size:12px;padding:12px 20px}.ep-copy{display:none}}
.ep-copy{border:1px solid rgba(255,255,255,.6);border-radius:999px;padding:8px 18px;font-size:13px;font-weight:800;flex:none;cursor:pointer;color:var(--violet);font-family:var(--font);background:rgba(255,255,255,.5);backdrop-filter:blur(20px) saturate(1.7);-webkit-backdrop-filter:blur(20px) saturate(1.7);box-shadow:0 4px 14px rgba(80,52,140,.12),inset 0 1px 1px rgba(255,255,255,.85);transition:transform .15s,background .18s,box-shadow .18s}
.endpoint:hover .ep-copy{background:rgba(255,255,255,.66);box-shadow:0 6px 18px rgba(80,52,140,.16),inset 0 1px 1px rgba(255,255,255,.92)}
.endpoint:active .ep-copy{transform:scale(.95)}
.connect .hero-ctas{justify-content:center;position:relative;z-index:1}

/* ── 푸터 ── */
footer{padding:50px 0 58px;border-top:1px solid var(--line)}
.foot{display:flex;align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap}
.foot-brand{display:flex;align-items:center;gap:11px;font-weight:800;color:var(--ink)}
.foot-brand img{width:30px;height:30px;border-radius:9px}
.foot small{color:var(--muted);font-size:13px}
.foot-end{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.lt-nav{margin-left:6px}.lt-foot{display:none}
@media(max-width:760px){.lt-nav{display:none}.lt-foot{display:inline-flex}}

/* ── 스크롤 리빌 ── */
.rv{opacity:0;transform:translateY(24px);transition:opacity .7s cubic-bezier(.2,.8,.2,1),transform .7s cubic-bezier(.2,.8,.2,1)}
.rv.vis{opacity:1;transform:none}
.rv.d1{transition-delay:.08s}.rv.d2{transition-delay:.16s}.rv.d3{transition-delay:.24s}

/* ── 튜토리얼 모션그래픽 (방장 PlayMCP AI → MCP → 팀원 개인카톡+폼, 전체 워크플로우) ── */
.sr-stage{display:flex;flex-direction:column;gap:14px;height:clamp(560px,72svh,690px);padding:20px;border-radius:var(--radius-lg);overflow:hidden;position:relative}
.sr-stage>*{min-width:0}
.sr-replay{position:absolute;top:16px;right:16px;z-index:5;width:42px;height:42px;border:0;border-radius:999px;display:flex;align-items:center;justify-content:center;color:var(--violet);font-family:inherit;font-size:18px;font-weight:900;cursor:pointer;transition:transform .16s cubic-bezier(.2,.8,.2,1),background .18s,box-shadow .18s}
.sr-replay:hover{transform:translateY(-1px);background:rgba(255,255,255,.72);box-shadow:0 8px 22px rgba(80,52,140,.13),inset 0 1px 1px rgba(255,255,255,.9)}
.sr-replay:active{transform:scale(.94)}
.sr-cmdhint{font-size:11.5px;font-weight:700;color:var(--muted);text-align:center;margin-top:2px}
.sr-cmdhint b{color:var(--violet)}
/* 채팅창 안 '다음 대화' 제안칩 (방장이 보낼 다음 말 — 누르면 전송) */
/* '다음 대화' 칩 — 예비/가이드: 투명(뒤 채팅 그대로 비침) + 점선 보더, 블러 없음(하얗게 안 뜨게) */
.sr-next{align-self:flex-end;max-width:90%;margin-top:4px;position:relative;display:inline-flex;align-items:center;gap:8px;padding:10px 16px;border-radius:17px;border-bottom-right-radius:6px;color:var(--violet);font-family:inherit;font-size:13.5px;font-weight:800;cursor:pointer;background:rgba(124,58,237,.06);border:1.5px dashed rgba(124,58,237,.5);box-shadow:0 2px 10px rgba(80,52,140,.06);transition:transform .16s cubic-bezier(.2,.8,.2,1),background .2s,box-shadow .2s,border-color .2s}
.sr-next::after{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;animation:srNextPulse 2.3s ease-in-out infinite}
.sr-next span{font-weight:900;opacity:.7}
.sr-next:hover{transform:translateY(-1px);background:rgba(124,58,237,.11);border-color:rgba(124,58,237,.68);box-shadow:0 4px 14px rgba(80,52,140,.1)}
.sr-next:active{transform:scale(.98)}
@keyframes srNextPulse{0%,100%{box-shadow:0 0 0 0 rgba(124,58,237,0)}50%{box-shadow:0 0 20px 2px rgba(124,58,237,.24)}}
/* 캡션 */
.sr-caption{min-height:24px;display:flex;flex-direction:column;gap:2px;transition:opacity .35s;padding:0 54px 0 4px}
.sr-caption b{color:var(--ink);font-size:16px;font-weight:800}
.sr-caption span{color:var(--muted);font-size:13px}
.sr-caption.swap{opacity:0}
/* 플로우: 팀원 개인카톡 | AI 허브 | 방장 PlayMCP */
.sr-flow{position:relative;display:grid;grid-template-columns:minmax(0,1fr) 96px minmax(0,1fr);gap:12px;align-items:stretch;min-height:0;flex:1;overflow:hidden}
.sr-flow>*{min-width:0}
.sr-slot{display:flex;flex-direction:column;min-height:0;height:100%;padding:12px;border-radius:var(--radius);outline:2px solid transparent;outline-offset:0;overflow:hidden}
.sr-slot-tag{display:flex;align-items:center;gap:6px;font-size:12px;font-weight:700;color:var(--muted);padding:0 2px 8px;margin-bottom:6px;border-bottom:1px solid var(--line)}
.sr-slot-tag b{color:var(--ink-soft);font-weight:800}
.sr-msgs{flex:1;min-height:0;display:flex;flex-direction:column;gap:9px;padding:0 3px 4px;overflow-y:auto;scroll-behavior:smooth;overscroll-behavior:contain;overflow-anchor:none;scrollbar-width:none;-ms-overflow-style:none}
.sr-msgs::-webkit-scrollbar{display:none}
.sr-actionbar{flex:none;height:52px;min-height:52px;display:flex;align-items:flex-end;justify-content:flex-end;padding:8px 2px 0}
.sr-slot.owner{background:rgba(255,255,255,.5);border:1px solid rgba(255,255,255,.6)}
.sr-slot.member{background:rgba(254,229,0,.12);border:1px solid rgba(254,229,0,.42);box-shadow:inset 0 1px 1px rgba(255,255,255,.7)}
.sr-kk-badge{margin-left:auto;font-size:10.5px;font-weight:800;color:#7a6a00;background:rgba(254,229,0,.5);padding:2px 8px;border-radius:999px;opacity:.5;transition:opacity .3s,box-shadow .3s;white-space:nowrap}
.sr-kk-badge.on{opacity:1;box-shadow:0 0 10px rgba(254,229,0,.55)}
.sr-slot.member .cd-msg.kko-in{align-self:stretch;max-width:100%;background:rgba(255,255,255,.86);border:1px solid rgba(254,229,0,.5);color:var(--ink-soft);backdrop-filter:none;-webkit-backdrop-filter:none;border-bottom-left-radius:5px}
.sr-slot.member .cd-msg.kko-out{align-self:flex-end;background:rgba(254,229,0,.5);color:var(--ink);border-bottom-right-radius:5px;font-weight:600}
.cd-msg .who{display:block;font-size:11px;font-weight:800;opacity:.8;margin-bottom:2px}
.cd-msg.sys{align-self:center;max-width:100%;background:rgba(124,58,237,.08);border:1px dashed var(--line-hi);color:var(--muted);font-size:12px;font-weight:700;text-align:center;padding:7px 12px;border-radius:10px}
.cd-msg.sys b{color:var(--violet)}
/* 팀원이 링크로 여는 teamplay-talk 폼 (제품 = 바이올렛) */
.sr-form{align-self:stretch;margin-top:2px;border-radius:12px;background:rgba(255,255,255,.94);border:1px solid var(--line-hi);box-shadow:0 2px 9px rgba(80,52,140,.1);padding:10px 11px;display:flex;flex-direction:column;gap:8px;opacity:0;transform:translateY(10px) scale(.99);filter:blur(2px)}
.sr-form.in{animation:srCard .42s cubic-bezier(.22,1,.36,1) forwards;will-change:transform,opacity,filter}
@keyframes srCard{0%{opacity:0;transform:translateY(10px) scale(.99);filter:blur(2px)}100%{opacity:1;transform:none;filter:blur(0)}}
/* AOS식 — 요소가 실제로 화면에 들어올 때 재생 (누적 창에서도 애니가 항상 보이게) */
.sr-msgs .cd-msg{animation:none}
.sr-msgs .cd-msg.in{animation:cdIn .45s cubic-bezier(.2,.8,.2,1) forwards}
.sr-form-h{display:flex;align-items:center;gap:6px;font-size:11.5px;font-weight:800;color:var(--violet)}
.sr-form-h::before{content:"";width:13px;height:13px;border-radius:4px;background:var(--violet);flex:none}
.sr-form-body{display:flex;flex-direction:column;gap:6px;min-height:22px}
.sr-form-body:empty::before{content:"응답 작성…";color:var(--quiet);font-size:12.5px;padding:4px 2px}
.sr-form-field{font-size:13px;line-height:1.45;color:var(--ink-soft);padding:8px 10px;border-radius:8px;background:rgba(124,58,237,.06);border:1px solid var(--line)}
.sr-grid{display:flex;flex-direction:column;gap:3px}
.sr-gridrow{display:grid;grid-template-columns:34px repeat(4,1fr);gap:3px;align-items:center}
.sr-gridrow.sr-gridhead span,.sr-gridrow>span:first-child{font-size:10px;font-weight:700;color:var(--muted);text-align:center;line-height:1}
.sr-cell{height:20px;display:flex;align-items:center;justify-content:center;border-radius:5px;background:rgba(124,58,237,.05);border:1px solid var(--line);font-size:10px;font-weight:800;color:transparent;transition:background .2s,color .2s,border-color .2s}
.sr-cell.on{background:rgba(124,58,237,.14);border-color:rgba(124,58,237,.42);color:var(--violet);box-shadow:inset 0 1px 1px rgba(255,255,255,.6);animation:srPick .28s cubic-bezier(.16,1,.3,1)}
.sr-cell.on::before{content:"O"}
.sr-cell.x{background:rgba(214,64,94,.1);border-color:rgba(214,64,94,.38);color:#c53d5a;box-shadow:inset 0 1px 1px rgba(255,255,255,.5);animation:srPick .28s cubic-bezier(.16,1,.3,1)}
.sr-cell.x::before{content:"×"}
.sr-rankchip b:empty{display:none}
.sr-check{display:flex;flex-direction:column;gap:5px}
.sr-checkitem{display:flex;align-items:center;gap:8px;font-size:12.5px;font-weight:600;color:var(--muted)}
.sr-checkitem.on{color:var(--ink-soft)}
.sr-box{flex:none;width:16px;height:16px;border-radius:5px;border:1.5px solid var(--line-hi);background:#fff;position:relative;transition:background .2s,border-color .2s}
.sr-checkitem.on .sr-box,.sr-join-step.on .sr-box{background:var(--violet);border-color:var(--violet);animation:srPick .28s cubic-bezier(.16,1,.3,1)}
.sr-checkitem.on .sr-box::after,.sr-join-step.on .sr-box::after{content:"✓";position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#fff;font-size:11px;font-weight:900;line-height:1}
.sr-checknote{font-size:12px;color:#8a6a00;background:rgba(254,229,0,.1);border:1px solid rgba(230,190,0,.32);border-radius:8px;padding:6px 9px;margin-top:2px}
.sr-join{align-self:stretch;margin-top:2px;border-radius:12px;background:rgba(255,255,255,.94);border:1px solid var(--line-hi);box-shadow:0 2px 9px rgba(80,52,140,.1);padding:11px;display:flex;flex-direction:column;gap:8px;opacity:0;transform:translateY(10px) scale(.99);filter:blur(2px)}
.sr-join.in{animation:srCard .42s cubic-bezier(.22,1,.36,1) forwards;will-change:transform,opacity,filter}
.sr-join-h{display:flex;align-items:center;gap:6px;font-size:11.5px;font-weight:800;color:var(--violet)}
.sr-join-h img{width:16px;height:16px;border-radius:4px;flex:none}
.sr-join-step{display:flex;align-items:center;gap:8px;font-size:12.5px;font-weight:600;color:var(--muted)}
.sr-join-step.on{color:var(--ink-soft)}
.sr-join-step b{color:var(--violet);font-weight:800}
.sr-rank{display:flex;flex-wrap:wrap;gap:6px}
.sr-rankchip{display:inline-flex;align-items:center;gap:5px;font-size:12.5px;font-weight:700;color:var(--ink-soft);background:rgba(124,58,237,.07);border:1px solid var(--line);border-radius:999px;padding:4px 10px}
.sr-rankchip b{display:inline-grid;place-items:center;width:16px;height:16px;border-radius:999px;background:var(--violet);color:#fff;font-size:10px}
.sr-rankchip.on{animation:srPick .28s cubic-bezier(.16,1,.3,1)}
.sr-poll{display:flex;flex-direction:column;gap:5px}
.sr-opt{font-size:12.5px;font-weight:700;color:var(--muted);background:rgba(124,58,237,.05);border:1px solid var(--line);border-radius:8px;padding:6px 10px}
.sr-opt.sel{color:var(--violet);background:rgba(124,58,237,.12);border-color:rgba(124,58,237,.4);font-weight:800;animation:srPick .28s cubic-bezier(.16,1,.3,1)}
.sr-opt.sel::before{content:"● ";font-size:10px}
.sr-form-submit{align-self:flex-end;padding:6px 15px;border-radius:999px;border:0;font-family:inherit;font-size:12px;font-weight:800;color:#fff;background:var(--violet);cursor:default;transition:background .25s}
.sr-form.done .sr-form-submit{background:#22c55e}
.sr-form.done .sr-form-submit{animation:srSubmit .36s cubic-bezier(.16,1,.3,1)}
.sr-form.done .sr-form-body{opacity:.7}
@keyframes srPick{0%{transform:scale(.92);filter:saturate(.8)}100%{transform:none;filter:saturate(1)}}
@keyframes srSubmit{0%{transform:scale(.92)}70%{transform:scale(1.06)}100%{transform:none}}
/* 중앙 AI/MCP 허브 */
.sr-hub{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;position:relative;z-index:4;align-self:stretch;height:100%;margin-top:0;min-width:0;transform:translateY(17px)}
.sr-logo{width:52px;height:52px;border-radius:14px;position:relative;z-index:2;box-shadow:0 8px 22px rgba(109,92,245,.28),0 0 0 1px rgba(255,255,255,.6);transition:filter .3s}
.sr-hub.dinging .sr-logo{filter:brightness(1.12)}
.sr-status{font-size:11px;font-weight:800;letter-spacing:.02em;color:var(--violet);opacity:.9;width:120px;height:26px;display:flex;align-items:center;justify-content:center;text-align:center;line-height:1.25;overflow:hidden}
.sr-ding{position:absolute;top:50%;left:50%;width:52px;height:52px;margin:-39px 0 0 -26px;border-radius:50%;z-index:1;opacity:0;pointer-events:none;background:radial-gradient(circle,rgba(124,58,237,.5),rgba(34,184,255,.28) 55%,transparent 72%)}
.sr-ding.go{animation:srDing .58s cubic-bezier(.2,.8,.2,1)}
@keyframes srDing{0%{opacity:.9;transform:scale(.6)}100%{opacity:0;transform:scale(2.2)}}
.sr-slot.rx{animation:srRx .6s ease-out}
@keyframes srRx{0%{outline-color:rgba(124,58,237,.5);outline-offset:0}100%{outline-color:rgba(124,58,237,0);outline-offset:7px}}
.sr-slot.member.rx{animation:srRxK .6s ease-out}
@keyframes srRxK{0%{outline-color:rgba(224,190,0,.75);outline-offset:0}100%{outline-color:rgba(224,190,0,0);outline-offset:7px}}
.sr-chapdiv{align-self:center;display:flex;align-items:center;gap:8px;margin:6px 0 1px;font-size:11px;font-weight:800;color:var(--quiet);letter-spacing:.03em;opacity:0}
.sr-chapdiv.in{animation:cdIn .4s cubic-bezier(.2,.8,.2,1) forwards}
.sr-chapdiv::before,.sr-chapdiv::after{content:"";height:1px;width:20px;background:var(--line)}
@media(max-width:720px){
  .sr-stage{gap:12px;height:clamp(700px,88svh,840px);padding:16px}
}
@media(max-width:600px){
  .sr-flow{grid-template-columns:minmax(0,1fr);grid-template-rows:minmax(0,1fr) auto minmax(0,1fr);gap:10px}
  .sr-slot.member{order:0}.sr-hub{order:1;flex-direction:row;gap:10px;align-self:auto;height:auto;margin-top:0;transform:none}.sr-slot.owner{order:2}
  .sr-slot{min-height:0}.sr-logo{width:44px;height:44px}.sr-status{position:absolute;left:calc(50% + 34px);top:50%;transform:translateY(-50%);width:auto;max-width:calc(50% - 46px);white-space:nowrap;overflow:hidden;text-align:left}
  .sr-ding{top:50%;margin-top:-22px;width:44px;height:44px}
  .sr-caption span{display:none}
  .sr-replay{width:34px;height:34px;top:12px;right:12px;font-size:15px}
  .sr-caption{min-height:36px;padding-right:44px}
  .sr-flow{margin-top:6px}
}

@media (prefers-reduced-motion: reduce){
  *,*:before,*:after{animation:none!important;transition:none!important}
  .rv,.cd-msg,.sr-form,.sr-join,.sr-chapdiv{opacity:1;transform:none}
  html{scroll-behavior:auto}
  .sr-ding{display:none!important}
  .sr-chapfill{transition:none}
  .mlg::after{display:none}
}
"""

_JS = """
const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('vis');io.unobserve(e.target)}}),{threshold:.14});
document.querySelectorAll('.rv').forEach(el=>io.observe(el));
// 나브 스크롤스파이 — 현재 섹션 항목에 리퀴드 필
(function(){
  const ids=['how','tutorial','flow','features','makers'], links={};
  document.querySelectorAll('.nav-links a').forEach(a=>{const id=a.getAttribute('href').slice(1); if(id)links[id]=a;});
  function spy(){
    const line=window.innerHeight*0.35; let cur=null;
    ids.forEach(id=>{const s=document.getElementById(id); if(s && s.getBoundingClientRect().top<=line) cur=id;});
    ids.forEach(id=>{ if(links[id]) links[id].classList.toggle('active', id===cur); });
  }
  window.addEventListener('scroll', spy, {passive:true});
  window.addEventListener('resize', spy);
  spy();
})();
function copyEndpoint(btn){
  const url='https://teamplay-talk.tech/mcp/';
  const lbl=btn.querySelector('.ep-copy')||btn;
  const flash=ok=>{lbl.textContent=ok?(LANG==='en'?'Copied!':'복사됨!'):(LANG==='en'?'Copy failed':'복사 실패');clearTimeout(lbl._t);lbl._t=setTimeout(()=>{lbl.textContent=(LANG==='en'?'Copy':'복사')},1600)};
  if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(url).then(()=>flash(true)).catch(()=>flash(false));}
  else{try{const ta=document.createElement('textarea');ta.value=url;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.focus();ta.select();document.execCommand('copy');document.body.removeChild(ta);flash(true)}catch(e){flash(false)}}
}
window.copyEndpoint=copyEndpoint;

// 인터랙티브 채팅 데모 — 실제 MCP 흐름(확인 게이트). CD 순서 = 칩 순서.
var CD_KO=[
 [{r:'user',t:'카카오 MCP 대회 로드맵 짜줘'},
  {r:'ai',t:'마감(7/14)까지 <b>6단계</b>로 잡았어요.<br>1 주제·기획 <span>~6/20</span><br>2 서버+카카오 인증 <span>~6/26</span><br>3 핵심 기능 <span>~7/4</span><br>4 홈페이지·데모 <span>~7/9</span><br>5 QC·리허설 <span>~7/12</span><br>6 제출 <span>~7/14</span>'},
  {r:'user',t:'좋아'},
  {r:'ai',t:'확정 — 각 단계를 <b>개인 todo</b>로 쪼개 배정했어요 (함봉구 백엔드 · 이민지 UI · 김주호 프론트). 각자 카톡으로 보냈어요.'}],
 [{r:'user',t:'역할 좀 나눠줘'},
  {r:'ai',t:'<b>4개 역할</b>(기획·백엔드·프론트·디자인)로 나눴어요. 선호 순위 받을까요?'},
  {r:'user',t:'ㅇㅇ'},
  {r:'ai',t:'팀원들 <b>선호 순위</b>를 받았어요. 이제 배정할게요.'},
  {r:'ai',t:'선호·난이도 균형으로 배정했어요.<br>박세원 <b>기획·PM</b> · 함봉구 <b>백엔드</b><br>이민지 <b>디자인·UX</b> · 김주호 <b>프론트엔드</b><br>확정하고 공지했어요.'}],
 [{r:'user',t:'이번 주 회의 시간 잡아줘'},
  {r:'ai',t:'오늘부터 2주 <b>가능 시간표</b>를 만들었어요. 팀원 4명에게 보낼까요?'},
  {r:'user',t:'응 보내줘'},
  {r:'ai',t:'전원 응답 완료 — <b>화 20:00</b>이 4명 다 가능해요.<br>공지하고 톡캘린더에 등록했어요.'}],
 [{r:'user',t:'모일 장소 정하자'},
  {r:'ai',t:'각자 <b>선호 지역</b>을 폼으로 받을게요. 보낼까요?'},
  {r:'user',t:'ㅇㅇ'},
  {r:'ai',t:'투표 결과 <b>강남역</b> 3표 (홍대 1). 강남역으로 정해 공지했어요.'}],
 [{r:'user',t:'회식 메뉴 정하자'},
  {r:'ai',t:'후보 4개로 <b>익명 투표</b>를 만들었어요. 보낼까요?'},
  {r:'user',t:'보내줘'},
  {r:'ai',t:'집계 완료 — <b>삼겹살</b> 5표로 1등 (초밥 2·파스타 1). 결과 공지했어요.'}],
 [{r:'user',t:'오늘 팀 현황 어때?'},
  {r:'ai',t:'어젯밤 체크인 요약이에요.<br>완료 4 · 진행 3 · 밀림 1<br>함봉구 백엔드 <b>완료</b> · 이민지 UI 60% · 김주호 프론트 <b>밀림</b>(오늘 이월)<br>아침 리포트 보낼까요?'},
  {r:'user',t:'응'},
  {r:'ai',t:'팀 카톡에 <b>아침 리포트</b> 보냈어요. 밀린 일은 오늘 체크인에 자동으로 올라가요.'}]
];
var CD=(LANG==='en')?CD_EN:CD_KO;
let cdTok=0, cdCur=0;
function cdPlay(i){
  cdCur=i;
  document.querySelectorAll('.demo-chip').forEach((c,idx)=>c.classList.toggle('active',idx===i));
  const win=document.getElementById('cdWindow'); if(!win)return; win.innerHTML='';
  const my=++cdTok; let delay=150;
  CD[i].forEach((m,idx)=>{
    setTimeout(()=>{ if(my!==cdTok)return;
      const el=document.createElement('div'); el.className='cd-msg '+m.r; el.innerHTML=m.t;
      win.appendChild(el); win.scrollTop=win.scrollHeight;
    },delay);
    const next=CD[i][idx+1];
    delay += !next ? 0 : (next.r==='user' ? 1100 : Math.min(2200, 700 + next.t.length*6));
  });
}
(function(){
  document.querySelectorAll('.demo-chip').forEach((b,i)=>b.addEventListener('click',()=>cdPlay(i)));
  const rb=document.getElementById('cdReplay'); if(rb)rb.addEventListener('click',()=>cdPlay(cdCur));
  const chips=document.getElementById('demoChips'), bar=chips&&chips.closest('.cd-bar');
  function fades(){ if(!chips||!bar)return; const s=chips.scrollLeft, max=chips.scrollWidth-chips.clientWidth;
    bar.classList.toggle('sc-left', s>1); bar.classList.toggle('sc-right', s<max-1); }
  if(chips){ chips.addEventListener('scroll',fades,{passive:true}); window.addEventListener('resize',fades); fades(); setTimeout(fades,120); }
  if(document.querySelector('.demo-chip')) cdPlay(0);
  window.__tptReloadCD=function(){ CD=(LANG==='en')?CD_EN:CD_KO; cdPlay(cdCur||0); };
})();

// 튜토리얼 모션그래픽: 방장 PlayMCP AI → MCP → 팀원 개인카톡+폼 (전체 워크플로우)
(function(){
  var stage=document.getElementById('srStage'); if(!stage)return;
  var cap=document.getElementById('srCap'), flow=document.getElementById('srFlow'),
      ownerBox=document.getElementById('srOwnerMsgs'), memberBox=document.getElementById('srMemberMsgs'),
      actionBar=document.getElementById('srOwnerAction'),
      ownerSlot=document.getElementById('srOwner'), memberSlot=document.getElementById('srMember'),
      memberName=document.getElementById('srMemberName'), memberChan=document.getElementById('srMemberChan'),
      hub=document.getElementById('srHub'), ding=document.getElementById('srDing'),
      statusEl=document.getElementById('srStatus'), kk=document.getElementById('srKk'),
      replayBtn=document.getElementById('srReplay');
  var reduce=window.matchMedia('(prefers-reduced-motion:reduce)').matches;
  // 채팅창 안에서 누를 '다음 대화' 라벨 (auto는 시간 경과 라벨)
  var CHIPS=(LANG==='en')?CHIPS_EN:CHIPS_KO;
  // 고정 높이 채팅 패널 안에서만 재생한다. 뷰포트 IO에 맡기면 내부 스크롤 요소의 폼 애니메이션이 누락된다.
  function rev(box,el){
    if(reduce){ el.classList.add('in'); return; }
    requestAnimationFrame(function(){ el.classList.add('in'); });
  }

  // 전체 워크플로우. member: 'join'(PlayMCP 참여) | 'none' | 'notice' | 'form' | 'auto' | 'autoform'
  var STEPS_KO=[
   {cap:'방을 만들어요', sub:'방장은 방 생성 · 팀원은 PlayMCP로 참여', member:'join', who:'이민지', channel:'PlayMCP', think:'방 생성 중',
    cmd:'카카오 MCP 대회방 만들어줘',
    draft:"<b>'카카오 MCP 대회방'</b> 생성 완료.<br>초대 코드 <b>AbC123xY</b> <span>팀원에게 공유하세요</span>",
    code:'AbC123xY',
    result:'팀원 4명 <b>PlayMCP로 합류</b> 완료.<br><span>이제 로드맵을 잡아볼까요?</span>'},

   {cap:'로드맵 세우고 의견도 받아요', sub:'AI 마일스톤 초안 → 팀 검토 → 확정', member:'form', who:'이민지', channel:'카카오톡', think:'로드맵 설계 중', send:'검토 폼 전송',
    cmd:'대회 출품작 로드맵 만들어줘. 제출 <b>7/10</b>. 팀 의견도 받아줘',
    draft:'<b>6단계</b> 초안이에요.<br>주제확정 · 핵심설계 · MCP서버 · 카카오OAuth · 데모UX · 테스트/제출<br><span>팀원 검토 폼을 보낼게요</span>',
    kko:'<b>[팀플톡]</b> 로드맵 검토 요청<br><span>응답하기 &#9656;</span>',
    form:{type:'text', title:'로드맵 검토 · 의견', answer:'핵심설계 때 화면 흐름(와이어프레임)도 같이 잡아주세요'},
    result:'의견 반영 — 핵심설계에 <b>화면 흐름 설계</b> 포함.<br>로드맵 확정했어요.'},

   {cap:'역할을 나눠요', sub:'선호 순위 폼 → 균형 배정', member:'form', who:'이민지', channel:'카카오톡', think:'역할 후보 생성 중', send:'선호도 폼 전송',
    cmd:'로드맵 기준 <b>역할분배</b> 시작해줘',
    draft:'역할 후보 <b>5개</b>.<br>기획·PM / 백엔드 / 프론트엔드 / 디자인·UX / QA·발표<br><span>선호도 조사 보낼까요?</span>',
    kko:'<b>[팀플톡]</b> 역할 선호도 조사<br><span>응답하기 &#9656;</span>',
    form:{type:'rank', title:'역할 선호 순위 (5개 모두)', items:['디자인·UX','QA·발표','기획·PM','백엔드','프론트엔드']},
    result:'박세원 <b>기획·PM</b> · 함봉구 <b>백엔드</b><br>이민지 <b>디자인·UX</b> · 김주호 <b>프론트엔드</b> <span>확정?</span>'},

   {cap:'할 일로 쪼개요', sub:'로드맵 단계 × 역할 → 개인별 todo → 일정', member:'notice', who:'이민지', channel:'카카오톡', big:true, think:'할 일 분해 중', send:'카톡 전달',
    cmd:'로드맵 단계별로 팀원 <b>todo</b> 만들어줘',
    draft:'로드맵 6단계를 <b>역할별 todo</b>로 쪼개 마감까지 붙였어요.<br>백엔드 → 함봉구 · 디자인·UX → 이민지 · 프론트 → 김주호',
    kko:'<b>[팀플톡] 내 할 일 · 이민지</b><br><b>이번 주</b><br>· 폼 화면 UX 다듬기 <span>~7/8</span><br>· 대시보드 정보구조 정리 <span>~7/9</span><br><b>다음 주</b><br>· 데모 화면 최종 점검 <span>~7/10</span><br><span>끝내면 밤 체크인에서 체크하면 돼요</span>',
    result:'전원에게 <b>마감 붙은 todo</b> 배정 완료.<br><span>이제 회의 일정을 잡을까요?</span>'},

   {cap:'팀에게 물어봐요', sub:'열린 질문 → 투표 폼 → 결과 집계', member:'form', who:'이민지', channel:'카카오톡', think:'투표 만드는 중', send:'투표 폼 전송',
    cmd:'어떤 클라우드 플랫폼 쓸지 팀원들한테 물어봐줘',
    draft:'<b>클라우드 투표</b>를 만들었어요.<br>AWS · GCP · Azure <span>팀에 보낼까요?</span>',
    kko:'<b>[팀플톡]</b> 클라우드 플랫폼 투표<br><span>응답하기 &#9656;</span>',
    form:{type:'poll', title:'어떤 클라우드로 갈까?', opts:['AWS','GCP','Azure'], sel:'GCP'},
    result:'집계 완료 — <b>GCP</b> 3표로 결정.<br>팀에 공지했어요.'},

   {cap:'회의 시간을 잡아요', sub:'그리드 체크 → 겹치는 시간 추천 → 톡캘린더 등록', member:'form', who:'이민지', channel:'카카오톡', think:'그리드 생성 중', send:'시간 그리드 전송',
    cmd:'이번 주 <b>전체 회의</b> 시간 잡아줘',
    draft:'날짜×시간 <b>가능표</b>를 만들었어요.<br><span>팀원에게 보낼까요?</span>',
    kko:'<b>[팀플톡]</b> 회의 가능 시간<br><span>되는 칸 모두 체크 &#9656;</span>',
    form:{type:'grid', title:'회의 가능 시간', cols:['월','화','수','목'], rows:['19시','20시','21시'], on:['2,0','0,1','1,3','2,3'], x:['0,0','2,1']},
    result:'<b>월 21:00</b> — 4명 전원 가능.<br><span>이 시간으로 확정할까요?</span>',
    extra:{cmd:'응, 톡캘린더에도 등록해줘', status:'톡캘린더 등록 중',
      kko:'<b>[톡캘린더]</b> 일정이 등록됐어요<br><b>팀 회의</b> · 7/6(월) 21:00<br><span>시작 30분 전 알림 예약됨</span>',
      result:'<b>톡캘린더 등록 완료</b> — 전원에게 알림 예약.<br><span>회의 장소도 이어서 받을까요?</span>'}},

   {cap:'약속 장소를 정해요', sub:'선호 장소 단답 → 중복 정리 → 후보 집계', member:'form', who:'이민지', channel:'카카오톡', think:'장소 폼 생성 중', send:'장소 폼 전송',
    cmd:'회의 장소 후보 받아봐',
    draft:'선호 장소를 <b>단답</b>으로 받는 폼을 만들었어요.<br><span>카카오맵으로 주소도 정리할게요</span>',
    kko:'<b>[팀플톡]</b> 회의 장소 후보<br><span>가고 싶은 곳 적어줘 &#9656;</span>',
    form:{type:'text', title:'회의 장소 후보', answer:'강남역 근처 스터디카페'},
    result:'후보 집계 — <b>강남역</b> 3표로 최다.<br><span>강남역으로 정해 공지했어요.</span>'},

   {cap:'밤마다 진행을 체크해요', sub:'21:00 자동 → 완료한 일 체크', member:'autoform', who:'이민지', channel:'카카오톡', think:'체크인 폼 준비 중', send:'체크인 자동 발송',
    sched:'&#9200; 매일 21:00 · 자동 실행',
    draft:'밤 체크인 폼을 팀 카톡으로 보냈어요.',
    kko:'<b>[팀플톡]</b> 오늘의 진행 체크 · 21:00<br><span>완료한 일을 체크해줘 &#9656;</span>',
    form:{type:'check', title:'오늘 체크인', items:[{t:'폼 화면 UX 다듬기',on:true},{t:'대시보드 정보구조 정리',on:true},{t:'데모 화면 최종 점검',on:false}], note:'막힘: 폼이 모바일에서 반응형이 깨져요'},
    result:'체크인 <b>수집 완료</b>.<br><span>내일 아침 리포트에 자동 반영돼요.</span>'},

   {cap:'아침마다 리포트가 와요', sub:'09:00 자동 → 어제·오늘·내일·회의 정리', member:'auto', who:'이민지', channel:'카카오톡', big:true, think:'아침 리포트 생성 중', send:'리포트 자동 발송',
    sched:'&#9200; 매일 09:00 · 자동 실행',
    draft:'어제 체크인 기준으로 아침 리포트를 만들었어요.',
    kko:'<b>[팀플톡] 오늘의 진행 리포트 · 09:00</b><br><b>어제 완료</b><br>· 폼 화면 UX 다듬기<br>· 대시보드 정보구조 정리<br><b>오늘 할 일</b><br>· 데모 화면 최종 점검 · 모바일 반응형 수정<br><b>내일 예정</b><br>· 데모 리허설 화면 정리<br><b>오늘 회의</b> 21:00<br><b>막힌 이슈</b><br>· 폼 모바일 반응형 깨짐',
    result:'팀 전원 카톡에 <b>자동 발송</b>.<br><span>지연·리스크는 방장에게 따로 요약해요.</span>'},

   {cap:'정리하고 공지해요', sub:'대시보드 확인 · 팀 카톡 공지', member:'notice', who:'이민지', channel:'카카오톡', big:true, think:'현황 집계 중', send:'팀 카톡 공지',
    cmd:'지금까지 결정된 내용 팀에 공지해줘',
    draft:'확정 사항을 정리했어요.',
    kko:'<b>[팀플톡] 대회 진행 정리</b><br><b>확정</b><br>· 로드맵 6단계 확정<br>· 역할 분배 완료<br>· 회의 <b>7/6(월) 21:00</b><br>· 제출 <b>7/10</b><br><b>오늘 집중</b><br>· MCP 안정화 · OAuth 검증 · 데모 정리 · 발표 초안<br><span>각자 todo 확인해주세요</span>',
    result:'팀 전원에게 공지 전송 완료.<br><span>대시보드에서 전체 흐름을 볼 수 있어요.</span>'}
  ];
  var STEPS=(LANG==='en')?STEPS_EN:STEPS_KO;

  var SR={tok:0,timers:[],playing:false,cur:0,done:false,started:false,formEl:null};
  function after(ms,fn){ SR.timers.push(setTimeout(fn,ms)); }
  function clearTimers(){ SR.timers.forEach(clearTimeout); SR.timers=[]; }
  function resetBoxes(){ ownerBox.innerHTML=''; memberBox.innerHTML=''; if(actionBar)actionBar.innerHTML=''; ownerBox.scrollTop=0; memberBox.scrollTop=0; SR.formEl=null; }
  function sd(box){
    if(reduce || !box)return;
    requestAnimationFrame(function(){
      box.scrollTo({top:box.scrollHeight,behavior:'smooth'});
    });
  }
  function bubble(box,cls,html,who,badge){
    var el=document.createElement('div'); el.className='cd-msg '+cls;
    el.innerHTML=(who?'<span class="who">'+who+'</span>':'')+html;
    if(badge){ var b=document.createElement('span'); b.className='sr-badge'; b.textContent=badge; el.appendChild(b); }
    box.appendChild(el); rev(box,el); sd(box);
  }
  function setCap(s){
    if(!cap)return;
    cap.innerHTML=(LANG==='en')
      ? '<b>AI PM workflow</b><span>Owner talks on PlayMCP → team replies in KakaoTalk → AI wraps up</span>'
      : '<b>AI PM 워크플로우</b><span>방장 PlayMCP 대화 → 팀원 카카오톡 응답 → AI 정리</span>';
  }
  function setMember(name,chan){ if(memberName)memberName.textContent=name; if(memberChan)memberChan.textContent=tr(chan||'카카오톡'); }
  // 받음 플래시: 받는 패널이 잠깐 리플-아웃 링으로 반짝 (강제 리플로우 없이 rAF로 재시작 → 안 들썩)
  function flash(el){ if(!el)return; el.classList.remove('rx'); requestAnimationFrame(function(){ el.classList.add('rx'); }); after(650,function(){ el.classList.remove('rx'); }); }
  function divider(box,text){ var d=document.createElement('div'); d.className='sr-chapdiv'; d.textContent=text; box.appendChild(d); rev(box,d); }
  function pulse(){ hub.classList.add('dinging'); ding.classList.remove('go'); void ding.offsetWidth; ding.classList.add('go'); after(560,function(){ hub.classList.remove('dinging'); }); }
  function setStatus(t){ statusEl.textContent=tr(t); }
  function kkOn(t){ kk.classList.add('on'); kk.textContent=tr(t||'도착'); }
  function kkReset(){ kk.classList.remove('on'); kk.textContent=tr('대기'); }
  function formShell(f){
    if(f.type==='grid'){
      var h='<div class="sr-grid"><div class="sr-gridrow sr-gridhead"><span></span>';
      f.cols.forEach(function(d){ h+='<span>'+d+'</span>'; });
      h+='</div>';
      f.rows.forEach(function(tm,r){
        h+='<div class="sr-gridrow"><span>'+tm+'</span>';
        f.cols.forEach(function(d,c){ h+='<b class="sr-cell" data-rc="'+r+','+c+'"></b>'; });
        h+='</div>';
      });
      return h+'</div>';
    }
    if(f.type==='poll'){
      return '<div class="sr-poll">'+f.opts.map(function(o){ return '<span class="sr-opt" data-opt="'+o+'">'+o+'</span>'; }).join('')+'</div>';
    }
    if(f.type==='check'){
      return '<div class="sr-check">'+f.items.map(function(it,i){ return '<div class="sr-checkitem" data-i="'+i+'"><span class="sr-box"></span>'+it.t+'</div>'; }).join('')+(f.note?'<div class="sr-checknote" style="display:none"></div>':'')+'</div>';
    }
    if(f.type==='rank'){
      return '<div class="sr-rank">'+f.items.map(function(it,i){ return '<span class="sr-rankchip"><b>'+(i+1)+'</b>'+it+'</span>'; }).join('')+'</div>';
    }
    return '<div class="sr-form-field"></div>';
  }
  function typeInto(el,text,my){
    if(reduce){ el.textContent=text; return; }
    var i=0;
    function draw(){ el.innerHTML='<span>'+text.slice(0,i)+'</span><span style="opacity:0">'+text.slice(i)+'</span>'; }
    draw();
    (function step(){ if(my!==SR.tok)return; i+=2; draw(); if(i<text.length){ after(26,step); } })();
  }
  function showForm(f){
    var el=document.createElement('div'); el.className='sr-form';
    el.innerHTML='<div class="sr-form-h">'+f.title+'</div><div class="sr-form-body">'+formShell(f)+'</div><button class="sr-form-submit" type="button">'+tr('제출')+'</button>';
    SR.formEl=el;
    memberBox.appendChild(el); rev(memberBox,el); sd(memberBox);
  }
  function latestForm(){
    var forms=memberBox.querySelectorAll('.sr-form');
    return forms.length?forms[forms.length-1]:null;
  }
  function fillForm(f){
    var form=SR.formEl||latestForm();
    var b=form?form.querySelector('.sr-form-body'):null; if(!b)return; var my=SR.tok;
    if(f.type==='grid'){
      var on=f.on||[], xs=f.x||[];
      on.forEach(function(rc,k){
        var go=function(){ var c=b.querySelector('.sr-cell[data-rc="'+rc+'"]'); if(c)c.classList.add('on'); };
        if(reduce){ go(); } else { after(k*160,function(){ if(my!==SR.tok)return; go(); }); }
      });
      xs.forEach(function(rc,k){
        var go=function(){ var c=b.querySelector('.sr-cell[data-rc="'+rc+'"]'); if(c)c.classList.add('x'); };
        if(reduce){ go(); } else { after((on.length+k)*160,function(){ if(my!==SR.tok)return; go(); }); }
      });
    } else if(f.type==='poll'){
      var o=b.querySelector('.sr-opt[data-opt="'+f.sel+'"]'); if(o)o.classList.add('sel');
    } else if(f.type==='check'){
      f.items.forEach(function(it,i){ if(it.on){
        var go=function(){ var e=b.querySelector('.sr-checkitem[data-i="'+i+'"]'); if(e)e.classList.add('on'); };
        if(reduce){ go(); } else { after(i*180,function(){ if(my!==SR.tok)return; go(); }); }
      } });
      var note=b.querySelector('.sr-checknote'); if(note){ if(reduce){ note.style.display='block'; note.textContent=f.note; } else { after(f.items.length*180+150,function(){ if(my!==SR.tok)return; note.style.display='block'; typeInto(note,f.note,my); sd(memberBox); }); } }
    } else if(f.type==='rank'){
      var chips=b.querySelectorAll('.sr-rankchip'); Array.prototype.forEach.call(chips,function(c,i){ c.classList.add('on'); var bb=c.querySelector('b'); if(bb)bb.textContent=(i+1); });
    } else {
      var fld=b.querySelector('.sr-form-field'); if(fld)typeInto(fld,f.answer,my);
    }
    sd(memberBox);
  }
  function submitForm(){
    var el=SR.formEl||latestForm(); if(!el)return;
    el.classList.add('done');
    var b=el.querySelector('.sr-form-submit'); if(b){ b.textContent=tr('제출됨 ✓'); }
  }
  function showJoin(S){
    var el=document.createElement('div'); el.className='sr-join'; el.id='srJoin';
    var _jt=(LANG==='en')
      ? {h:'PlayMCP · join teamplay-talk',a:'Add teamplay-talk',b:'Kakao login · auth',c:'Enter invite code <b>'+(S.code||'')+'</b>'}
      : {h:'PlayMCP · teamplay-talk 참여',a:'teamplay-talk 추가',b:'카카오 로그인 · 인증',c:'초대코드 <b>'+(S.code||'')+'</b> 입력'};
    el.innerHTML='<div class="sr-join-h"><img src="/icon-mark.png" width="16" height="16" alt="">'+_jt.h+'</div>'
      +'<div class="sr-join-step" id="srJ0"><span class="sr-box"></span>'+_jt.a+'</div>'
      +'<div class="sr-join-step" id="srJ1"><span class="sr-box"></span>'+_jt.b+'</div>'
      +'<div class="sr-join-step" id="srJ2"><span class="sr-box"></span>'+_jt.c+'</div>';
    memberBox.appendChild(el); rev(memberBox,el); sd(memberBox);
  }
  function joinStep(k){ var e=document.getElementById('srJ'+k); if(e)e.classList.add('on'); }
  function joinDone(){ var e=document.getElementById('srJoin'); if(e)e.classList.add('done'); }

  function runStep(si){
    clearTimers();
    var my=SR.tok, S=STEPS[si], m=S.member, auto=(m==='auto'||m==='autoform');
    setCap(S); setMember(S.who||'팀원', S.channel);
    if(si===0){ ownerBox.innerHTML=''; memberBox.innerHTML=''; }  // 첫 챕터 = 처음부터(리셋). 나머지는 누적
    kkReset(); setStatus('대기');
    var beats=[], t=420;
    beats.push([t,function(){ divider(ownerBox,S.cap); divider(memberBox,S.cap); }]); t+=220;
    // 1) 트리거: 방장 명령 or 자동 스케줄
    if(auto){
      beats.push([t,function(){ bubble(ownerBox,'sys',S.sched); setStatus('자동 실행'); }]); t+=820;
    } else {
      beats.push([t,function(){ bubble(ownerBox,'user',S.cmd); setStatus('방장 입력'); }]); t+=760;
      beats.push([t,function(){ pulse(); setStatus('명령 수신'); }]); t+=500;
    }
    // 2) AI 처리 + 초안 (방장 창이 받음 → 플래시)
    beats.push([t,function(){ pulse(); setStatus(S.think||'처리 중'); }]); t+=500;
    beats.push([t,function(){ flash(ownerSlot); bubble(ownerBox,'ai',S.draft); }]); t+=1200;
    // 3) 팀원 단계
    if(m==='join'){
      beats.push([t,function(){ flash(memberSlot); showJoin(S); setStatus('PlayMCP 참여'); }]); t+=780;
      beats.push([t,function(){ joinStep(0); }]); t+=600;
      beats.push([t,function(){ joinStep(1); }]); t+=600;
      beats.push([t,function(){ joinStep(2); setStatus('초대코드 입력'); }]); t+=700;
      beats.push([t,function(){ joinDone(); pulse(); setStatus('합류'); }]); t+=540;
    } else if(m!=='none'){
      var lbl=(m==='form'||m==='autoform')?'폼 도착':'도착';
      beats.push([t,function(){ flash(memberSlot); kkOn(lbl); setStatus(S.send||'카톡 전송'); bubble(memberBox,'kko-in',S.kko); }]); t+=(S.big?1900:1100);
      if(m==='form'||m==='autoform'){
        beats.push([t,function(){ showForm(S.form); setStatus('폼 작성'); }]); t+=920;
        beats.push([t,function(){ fillForm(S.form); }]); t+=(S.form&&S.form.type==='grid'?1500:(S.form&&S.form.type==='rank'?1450:1100));
        beats.push([t,function(){ submitForm(); setStatus('제출'); }]); t+=720;
        beats.push([t,function(){ pulse(); setStatus('응답 수집'); }]); t+=540;
      }
    }
    // 4) 방장에게 결과 (방장 창이 받음 → 플래시)
    beats.push([t,function(){ flash(ownerSlot); bubble(ownerBox,'ai',S.result); setStatus('완료 ✓'); }]); t+=1300;
    // 5) 후속 (예: 톡캘린더 등록 → 팀원 알림)
    if(S.extra){
      var X=S.extra;
      beats.push([t,function(){ bubble(ownerBox,'user',X.cmd); }]); t+=760;
      beats.push([t,function(){ pulse(); setStatus(X.status||'처리 중'); }]); t+=500;
      beats.push([t,function(){ flash(memberSlot); kkOn('알림'); bubble(memberBox,'kko-in',X.kko); }]); t+=1400;
      beats.push([t,function(){ flash(ownerSlot); bubble(ownerBox,'ai',X.result); setStatus('완료 ✓'); }]); t+=1300;
    }
    beats.push([t,function(){ finishStep(si); }]);
    beats.forEach(function(bt){ after(bt[0],function(){ if(my!==SR.tok)return; bt[1](); }); });
  }

  function renderStatic(){
    clearTimers(); SR.tok++;
    var si=5, S=STEPS[si];  // 회의(그리드 폼) = 전체 흐름을 한 프레임에
    setMember(S.who||'팀원', S.channel);
    cap.innerHTML='<b>'+S.cap+'</b><span>'+S.sub+'</span>';
    ownerBox.innerHTML=''; memberBox.innerHTML=''; if(actionBar)actionBar.innerHTML='';
    bubble(ownerBox,'user',S.cmd); bubble(ownerBox,'ai',S.draft);
    bubble(memberBox,'kko-in',S.kko);
    showForm(S.form); fillForm(S.form); submitForm();
    bubble(ownerBox,'ai',S.result);
    kkOn('응답'); setStatus('완료 ✓');
  }

  function clrHub(){ hub.classList.remove('dinging'); ding.classList.remove('go'); }
  function hideNext(){ var bar=actionBar||ownerBox, n=bar.querySelector('.sr-next'); if(n){ n.parentNode.removeChild(n); } }
  function showNext(idx){
    hideNext();
    var el=document.createElement('button'); el.className='sr-next'; el.type='button';
    el.innerHTML=(idx===0?(LANG==='en'?'↻ Start over':'↻ 처음부터 다시'):CHIPS[idx])+' <span>▸</span>';
    el.addEventListener('click',function(){ play(idx); });
    (actionBar||ownerBox).appendChild(el);
  }
  // 채팅창 안에 '다음 대화' 제안 → 누르면 이어짐. 창은 누적(첫 챕터만 리셋)
  function play(i){ SR.tok++; SR.playing=true; SR.done=false; SR.cur=i; clearTimers(); clrHub(); hideNext(); runStep(i); }
  function finishStep(i){ SR.playing=false; SR.done=true; showNext((i+1)%STEPS.length); }
  function stop(){ SR.playing=false; clearTimers(); clrHub(); }
  function enter(){ if(SR.started||SR.playing){ return; } SR.started=true; play(0); }
  function restart(){
    SR.playing=false; SR.done=false; SR.cur=0; SR.started=true;
    SR.tok++; clearTimers(); clrHub(); hideNext(); resetBoxes(); kkReset(); setStatus('대기');
    play(0);
  }
  function stageVisible(){ var r=stage.getBoundingClientRect(); return r.top<window.innerHeight&&r.bottom>0; }

  if(reduce){ renderStatic(); return; }

  if(replayBtn){ replayBtn.addEventListener('click',function(){ restart(); }); }
  var io=new IntersectionObserver(function(es){ es.forEach(function(e){ if(e.isIntersecting){enter();} }); },{threshold:.15});
  io.observe(stage);
  document.addEventListener('visibilitychange',function(){
    if(!document.hidden && stageVisible()){ enter(); }
  });
  window.addEventListener('pageshow',function(e){
    if(!e.persisted)return;
    if(stageVisible()){ enter(); }
  });
  window.__tptReloadSR=function(){ STEPS=(LANG==='en')?STEPS_EN:STEPS_KO; CHIPS=(LANG==='en')?CHIPS_EN:CHIPS_KO; SR.started=false; restart(); };
})();

// 가로 스크롤 바 마우스 드래그 (포인터 캡처 없이 — 클릭 안 깨지게)
(function(){
  function drag(el){
    if(!el)return; var down=false,sx=0,sl=0,moved=false;
    el.addEventListener('mousedown',function(e){ down=true;moved=false;sx=e.clientX;sl=el.scrollLeft; });
    document.addEventListener('mousemove',function(e){ if(!down)return; var dx=e.clientX-sx; if(Math.abs(dx)>4){ moved=true; el.scrollLeft=sl-dx; e.preventDefault(); } });
    document.addEventListener('mouseup',function(){ down=false; });
    el.addEventListener('click',function(e){ if(moved){ e.stopPropagation(); e.preventDefault(); moved=false; } },true);
  }
  drag(document.getElementById('demoChips'));
  drag(document.getElementById('srChapters'));
})();
"""


def _icon(name: str) -> str:
    paths = {
        "poll": '<path d="M5 20V10M12 20V4M19 20v-7"/>',
        "grid": '<rect x="3" y="4" width="18" height="17" rx="2.5"/><path d="M3 9.5h18M8.5 4v17M15 9.5V21"/>',
        "pin": '<path d="M12 21s7-5.6 7-11a7 7 0 1 0-14 0c0 5.4 7 11 7 11Z"/><circle cx="12" cy="10" r="2.6"/>',
        "roles": '<circle cx="9" cy="8" r="3.2"/><path d="M3.5 20c.6-3.4 2.9-5 5.5-5s4.9 1.6 5.5 5"/><path d="M16.5 3.8a3.2 3.2 0 0 1 0 6.2M17.5 15.2c1.9.6 3 2 3.4 4.3"/>',
        "map": '<path d="M6 4v13l6 3 6-3V4"/><path d="M6 4l6 3 6-3M12 7v13"/>',
        "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2.4M12 19.6V22M2 12h2.4M19.6 12H22M4.9 4.9l1.7 1.7M17.4 17.4l1.7 1.7M19.1 4.9l-1.7 1.7M6.6 17.4l-1.7 1.7"/>',
        "bell": '<path d="M18 9a6 6 0 1 0-12 0c0 6-2.5 7-2.5 7h17S18 15 18 9Z"/><path d="M10 20a2.2 2.2 0 0 0 4 0"/>',
        "dash": '<rect x="3" y="3" width="8" height="10" rx="2"/><rect x="13" y="3" width="8" height="6" rx="2"/><rect x="13" y="11" width="8" height="10" rx="2"/><rect x="3" y="15" width="8" height="6" rx="2"/>',
    }
    return f'<svg viewBox="0 0 24 24">{paths[name]}</svg>'


# 채팅 데모 칩 (순서 = JS CD 순서) — 워크플로우 순서, 아이콘 + 라벨 인라인
_CHIPS = [("map", "로드맵"), ("roles", "역할 분배"), ("grid", "회의 시간"),
          ("pin", "약속 장소"), ("poll", "투표"), ("sun", "데일리")]

# 기능 카드 — 튜토리얼/설명톤: "언제 쓰고, 어떤 결정에 도움되는지"
_FEATURES = [
    ("poll", "투표 · 의견 모으기", "회식 메뉴부터 발표 주제까지, 의견이 갈릴 때. 팀 답을 한곳에 모아 무엇을 원하는지 한눈에 보여줘요."),
    ("grid", "회의 시간 맞추기", "다들 언제 되는지 몰라 헤맬 때. 날짜×시간 표에 각자 체크만 받아, 모두가 되는 시간을 짚어줘요."),
    ("pin", "약속 장소 정하기", "어디서 볼지 정할 때. 후보를 모아 팀이 직접 고르게 해, 한 사람이 정하는 부담을 덜어줘요."),
    ("roles", "역할 나누기", "누가 뭘 맡을지 애매할 때. 선호와 난이도를 함께 보고 공평하게 나눠, 뒷말 없는 분배를 도와줘요."),
    ("map", "로드맵 · 할 일 쪼개기", "무엇부터 할지 막막할 때. 큰 그림을 세우고 각자 할 일까지 나눠, 다음에 뭘 할지 분명해져요."),
    ("sun", "매일 진행 챙기기", "진행이 흐지부지될 때. 밤엔 오늘 한 일을 체크받고, 아침엔 누가 어디까지 왔는지 정리해줘요."),
    ("bell", "공지 · 일정 전하기", "정한 걸 놓치지 않게. 결정과 일정을 팀 카톡과 톡캘린더로 바로 전해줘요."),
    ("dash", "팀 상태 한눈에 보기", "전체가 궁금할 때. 투표·체크인·결정을 한 화면에 모아 팀이 어디쯤인지 보여줘요."),
]

_PIPELINE = [
    ("01", "방 개설 · 초대", "초대 코드 하나로 팀원 합류 — 이후 모든 조율이 이 방을 중심으로 돌아갑니다.", "room"),
    ("02", "로드맵 · 의견 수렴", "주제를 말하면 AI가 마일스톤을 설계하고, 팀 검토를 받아 확정합니다.", "roadmap"),
    ("03", "역할 분배", "선호 순위 → 난이도 균형 배정 → 방장 확인 후 확정.", "roles"),
    ("04", "개인 todo · 일정", "로드맵 단계 × 역할로 개인 todo를 쪼개고 마감까지 배정합니다.", "todo"),
    ("05", "회의 · 장소 · 캘린더", "날짜×시간 그리드로 시간 확정, 장소 집계, 톡캘린더 등록까지.", "meet"),
    ("06", "데일리 · 공지", "밤 체크인 → 아침 리포트가 자동으로 돌고, 결정사항은 팀 카톡으로 공지.", "daily"),
]


def _chips_html() -> str:
    return "".join(
        f'<button class="demo-chip" type="button"><span class="ci">{_icon(ico)}</span><span data-i18n="chip{i}">{label}</span></button>'
        for i, (ico, label) in enumerate(_CHIPS)
    )


def _features_html() -> str:
    return "".join(
        f'<div class="feat card rv d{i % 4 % 3 + 1}">'
        f'<div class="ico">{_icon(ico)}</div><h3 data-i18n="feat{i}t">{title}</h3><p data-i18n="feat{i}d">{desc}</p></div>'
        for i, (ico, title, desc) in enumerate(_FEATURES)
    )


def _pipeline_html() -> str:
    return "".join(
        f'<div class="pipe-item rv"><div class="pipe-dot lg">{no}</div>'
        f'<div class="pipe-card card"><h3><span data-i18n="pipe{i}t">{title}</span><span class="tag">{tag}</span></h3><p data-i18n="pipe{i}d">{desc}</p></div></div>'
        for i, (no, title, desc, tag) in enumerate(_PIPELINE)
    )


def _tutorial_html() -> str:
    return f"""<div class="sr-stage lg rv" id="srStage" aria-label="teamplay-talk 작동 데모">
      <button class="sr-replay lg" id="srReplay" type="button" aria-label="데모 처음부터 다시 재생">↻</button>
      <div class="sr-caption" id="srCap"><b>AI PM 워크플로우</b><span>방장 PlayMCP 대화 → 팀원 카카오톡 응답 → AI 정리</span></div>
      <div class="sr-flow" id="srFlow">
        <div class="sr-slot member lg" id="srMember">
          <div class="sr-slot-tag"><b id="srMemberName">이민지</b> · <span id="srMemberChan">PlayMCP</span><span class="sr-kk-badge" id="srKk">대기</span></div>
          <div class="sr-msgs" id="srMemberMsgs"></div>
        </div>
        <div class="sr-hub" id="srHub">
          <div class="sr-ding" id="srDing" aria-hidden="true"></div>
          <img class="sr-logo" src="/favicon.png" alt="teamplay-talk AI" width="52" height="52">
          <div class="sr-status" id="srStatus">대기</div>
        </div>
        <div class="sr-slot owner" id="srOwner">
          <div class="sr-slot-tag" data-i18n="owner_tag">방장 · PlayMCP AI</div>
          <div class="sr-msgs" id="srOwnerMsgs"></div>
          <div class="sr-actionbar" id="srOwnerAction"></div>
        </div>
      </div>
      <div class="sr-cmdhint" data-i18n="cmdhint">👆 방장 채팅창의 <b>파란 '다음 대화'</b>를 눌러 직접 진행해보세요</div>
    </div>"""


def _avatar(initial: str, filename: str) -> str:
    """아바타: static/에 이미지가 있으면 원형 사진, 없으면 이니셜 폴백."""
    if (_STATIC / filename).exists():
        return f'<div class="face"><img src="/{filename}" alt=""></div>'
    return f'<div class="face">{initial}</div>'


_I18N_HEAD = r"""
var LANG=(function(){try{return localStorage.getItem('tpt_lang')||'ko'}catch(e){return 'ko'}})();
var KO_TITLE=(document&&document.title)||'';
var EN={
  "doc_title":"teamplay-talk — Your team's PM, handled by AI",
  "nav_how":"How it works","nav_demo":"Demo","nav_flow":"Workflow","nav_features":"Features","nav_makers":"Makers","nav_cta":"Connect PlayMCP",
  "hero_badge":"Kakao PlayMCP · team-project MCP",
  "hero_h1":"Your team's PM,<br>handed to <span class=\"mlg\">AI<svg class=\"wave-underline\" viewBox=\"0 0 120 14\" preserveAspectRatio=\"none\" aria-hidden=\"true\"><defs><linearGradient id=\"ulg2\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"0\"><stop stop-color=\"#7c3aed\"/><stop offset=\"1\" stop-color=\"#22b8ff\"/></linearGradient></defs><path d=\"M1.5 9.2 C12.5 3.2 24.5 3.2 35.8 8.8 C47.7 14 57.5 13.4 68.4 7.4 C80.2 1.5 91.2 2.7 102.3 8.5 C111.4 13.1 116.8 11.1 118.5 7.4\" fill=\"none\" stroke=\"url(#ulg2)\" stroke-width=\"4.5\" stroke-linecap=\"round\"/></svg></span>",
  "hero_sub":"Polls, meeting times, role splits, roadmaps, daily reports — all of it. AI handles the busywork of team coordination like a PM, and teammates just reply in the KakaoTalk they already use.",
  "cta_primary":"Connect on PlayMCP","cta_ghost":"See how it works","chat_head":"teamplay-talk · AI conversation demo",
  "how_h2":"One word from the owner,<br>and it reaches the whole team.","how_p":"No installs, no new app. Teammates get forms and alerts in the KakaoTalk they already use, and reply with a single link.",
  "s1t":"Connect on PlayMCP","s1d":"One Kakao login connects teamplay-talk to your AI agent.",
  "s2t":"Talk to the AI","s2d":"\"Split the roles,\" \"find a meeting time.\" One line of natural language is enough.",
  "s3t":"Auto-broadcast to the team","s3d":"Forms, polls, and notices spread to your teammates' KakaoTalk.",
  "s4t":"AI wraps up & decides","s4d":"As replies come in, AI analyzes them and lays out the result and next move.",
  "flow1":"Talk to AI on <b>PlayMCP</b>","flow2":"<b>teamplay-talk</b> runs","flow3":"Team <b>KakaoTalk · forms · calendar</b>",
  "tut_h2":"From room setup to the final notice,<br>in one flow.","tut_p":"The owner talks to AI on PlayMCP; teammates just reply to forms in their own KakaoTalk. AI organizes it into roadmaps, roles, schedules, and reports.",
  "wf_h2":"From kickoff to deadline,<br>one workflow.","wf_p":"Not a pile of one-off features — the whole team project runs end to end. Each step's output becomes the next step's input.",
  "feat_h2":"Right when you need it, here's how it helps.","feat_p":"One tool for every moment a decision is needed. Teammates just reply with a single link.",
  "mk_h2":"The makers","mk_p":"Built by two, serious about making team projects actually run.",
  "cn_h2":"Connect right from PlayMCP","cn_p":"One Kakao login and you're in. Developers can also connect directly via the MCP endpoint.","cn_copy":"Copy",
  "owner_tag":"Owner · PlayMCP AI","cmdhint":"👆 Tap the blue <b>'next'</b> chip in the owner's chat to step through it yourself",
  "feat0t":"Polls · gather opinions","feat0d":"From dinner spots to talk topics — when opinions split. Pools the team's answers in one place so you see what everyone wants.",
  "feat1t":"Match meeting times","feat1d":"When nobody knows who's free. Everyone checks a date×time grid, and AI pinpoints the slot that works for all.",
  "feat2t":"Pick the place","feat2d":"When you're deciding where to meet. Gathers candidates and lets the team choose, so it's not on one person.",
  "feat3t":"Split the roles","feat3d":"When who-does-what is fuzzy. Weighs preference and difficulty for a fair split.",
  "feat4t":"Roadmap · break down tasks","feat4d":"When you don't know where to start. Sets the big picture and splits each person's tasks.",
  "feat5t":"Keep daily progress","feat5d":"When momentum fizzles. At night it checks what got done; in the morning it lays out who is where.",
  "feat6t":"Notices · schedules, delivered","feat6d":"So nothing decided slips. Sends decisions and schedules straight to team KakaoTalk and Talk Calendar.",
  "feat7t":"See team status at a glance","feat7d":"Gathers votes, check-ins, and decisions on one screen to show where the team stands.",
  "pipe0t":"Room setup · invite","pipe0d":"One invite code brings the team in — from here, all coordination revolves around this room.",
  "pipe1t":"Roadmap · gather input","pipe1d":"Say the topic; AI designs milestones and locks them in after team review.",
  "pipe2t":"Role assignment","pipe2d":"Preference ranking → difficulty-balanced assignment → owner confirms.",
  "pipe3t":"Personal todos · schedule","pipe3d":"Splits personal todos by roadmap stage × role and assigns deadlines.",
  "pipe4t":"Meeting · place · calendar","pipe4d":"Locks the time via a date×time grid, tallies the place, adds it to Talk Calendar.",
  "pipe5t":"Daily · notices","pipe5d":"Night check-in → morning report runs automatically; decisions go to team KakaoTalk.",
  "chip0":"Roadmap","chip1":"Roles","chip2":"Meeting time","chip3":"Place","chip4":"Poll","chip5":"Daily"
};
var CD_EN=[
 [{r:"user",t:"Plan a roadmap for the Kakao MCP contest"},{r:"ai",t:"Mapped it in <b>6 stages</b> to the deadline (7/14).<br>1 Topic·plan <span>~6/20</span><br>2 Server + Kakao auth <span>~6/26</span><br>3 Core features <span>~7/4</span><br>4 Homepage·demo <span>~7/9</span><br>5 QC·rehearsal <span>~7/12</span><br>6 Submit <span>~7/14</span>"},{r:"user",t:"Nice"},{r:"ai",t:"Locked in — split each stage into <b>personal todos</b> (Bonggu backend · Minji UI · Juho frontend). Sent to each via KakaoTalk."}],
 [{r:"user",t:"Split the roles"},{r:"ai",t:"Split into <b>4 roles</b> (planning·backend·frontend·design). Collect preference rankings?"},{r:"user",t:"yep"},{r:"ai",t:"Got everyone's <b>preference rankings</b>. Assigning now."},{r:"ai",t:"Balanced by preference·difficulty.<br>Sewon <b>Planning·PM</b> · Bonggu <b>Backend</b><br>Minji <b>Design·UX</b> · Juho <b>Frontend</b><br>Confirmed and announced."}],
 [{r:"user",t:"Find a meeting time this week"},{r:"ai",t:"Built a 2-week <b>availability grid</b> from today. Send to all 4?"},{r:"user",t:"yes, send it"},{r:"ai",t:"All replied — <b>Tue 8:00 PM</b> works for all 4.<br>Announced and added to Talk Calendar."}],
 [{r:"user",t:"Let's pick a place"},{r:"ai",t:"I'll collect each person's <b>preferred area</b> via a form. Send it?"},{r:"user",t:"yep"},{r:"ai",t:"Result: <b>Gangnam Station</b> 3 votes (Hongdae 1). Set to Gangnam and announced."}],
 [{r:"user",t:"Let's pick the dinner menu"},{r:"ai",t:"Built an <b>anonymous poll</b> with 4 options. Send it?"},{r:"user",t:"send it"},{r:"ai",t:"Tallied — <b>samgyeopsal</b> wins with 5 (sushi 2·pasta 1). Result announced."}],
 [{r:"user",t:"How's the team doing today?"},{r:"ai",t:"Here's last night's check-in.<br>Done 4 · In progress 3 · Behind 1<br>Bonggu backend <b>done</b> · Minji UI 60% · Juho frontend <b>behind</b> (rolled to today)<br>Send the morning report?"},{r:"user",t:"yes"},{r:"ai",t:"Sent the <b>morning report</b> to team KakaoTalk. Behind items auto-carry to today's check-in."}]
];
var STEPS_EN=[
 {cap:"Create the room",sub:"Owner creates the room · teammates join via PlayMCP",member:"join",who:"Minji",channel:"PlayMCP",think:"Creating",cmd:"Create a room for the Kakao MCP contest",draft:"<b>'Kakao MCP contest room'</b> created.<br>Invite code <b>AbC123xY</b> <span>share it with your team</span>",code:"AbC123xY",result:"4 teammates <b>joined via PlayMCP</b>.<br><span>Shall we set the roadmap now?</span>"},
 {cap:"Set the roadmap, gather input",sub:"AI drafts milestones → team review → lock in",member:"form",who:"Minji",channel:"KakaoTalk",think:"Planning",send:"Sending",cmd:"Make a roadmap for our contest entry. Submission <b>7/10</b>. Gather the team's input too",draft:"<b>6-stage</b> draft.<br>Topic · Core design · MCP server · Kakao OAuth · Demo UX · Test/submit<br><span>Sending a review form to the team</span>",kko:"<b>[TeamplayTalk]</b> Roadmap review request<br><span>Respond &#9656;</span>",form:{type:"text",title:"Roadmap review · comments",answer:"Please lock the screen flow during core design too"},result:"Feedback applied — <b>screen-flow design</b> added.<br>Roadmap locked in."},
 {cap:"Split the roles",sub:"Preference-ranking form → balanced assignment",member:"form",who:"Minji",channel:"KakaoTalk",think:"Roles",send:"Sending",cmd:"Start <b>role assignment</b> based on the roadmap",draft:"<b>5 role</b> candidates.<br>Planning·PM / Backend / Frontend / Design·UX / QA·Demo<br><span>Send the preference survey?</span>",kko:"<b>[TeamplayTalk]</b> Role preference survey<br><span>Respond &#9656;</span>",form:{type:"rank",title:"Rank role preferences (all 5)",items:["Design·UX","QA·Demo","Planning·PM","Backend","Frontend"]},result:"Sewon <b>Planning·PM</b> · Bonggu <b>Backend</b><br>Minji <b>Design·UX</b> · Juho <b>Frontend</b> <span>Confirm?</span>"},
 {cap:"Break into to-dos",sub:"Roadmap stage × role → personal todos → schedule",member:"notice",who:"Minji",channel:"KakaoTalk",big:true,think:"Splitting",send:"Sending",cmd:"Create <b>todos</b> for the team by roadmap stage",draft:"Split the 6 stages into <b>role-based todos</b> with deadlines.<br>Backend → Bonggu · Design·UX → Minji · Frontend → Juho",kko:"<b>[TeamplayTalk] My to-dos · Minji</b><br><b>This week</b><br>· Polish form-screen UX <span>~7/8</span><br>· Organize dashboard IA <span>~7/9</span><br><b>Next week</b><br>· Final demo-screen check <span>~7/10</span><br><span>Check them off at the night check-in when done</span>",result:"Assigned <b>todos with deadlines</b> to everyone.<br><span>Shall we set a meeting time now?</span>"},
 {cap:"Ask the team",sub:"Open question → poll form → tally",member:"form",who:"Minji",channel:"KakaoTalk",think:"Building",send:"Sending",cmd:"Ask the team which cloud platform to use",draft:"Built a <b>cloud poll</b>.<br>AWS · GCP · Azure <span>Send to the team?</span>",kko:"<b>[TeamplayTalk]</b> Cloud platform poll<br><span>Respond &#9656;</span>",form:{type:"poll",title:"Which cloud should we go with?",opts:["AWS","GCP","Azure"],sel:"GCP"},result:"Tallied — <b>GCP</b> wins with 3 votes.<br>Announced to the team."},
 {cap:"Set a meeting time",sub:"Grid check → suggest overlap → add to Talk Calendar",member:"form",who:"Minji",channel:"KakaoTalk",think:"Building",send:"Sending",cmd:"Find a time for this week's <b>full-team meeting</b>",draft:"Built a date×time <b>availability grid</b>.<br><span>Send it to the team?</span>",kko:"<b>[TeamplayTalk]</b> Meeting availability<br><span>Check all slots that work &#9656;</span>",form:{type:"grid",title:"Meeting availability",cols:["Mon","Tue","Wed","Thu"],rows:["7 PM","8 PM","9 PM"],on:["2,0","0,1","1,3","2,3"],x:["0,0","2,1"]},result:"<b>Mon 9:00 PM</b> — all 4 free.<br><span>Lock this time?</span>",extra:{cmd:"Yes, add it to Talk Calendar too",status:"Calendar",kko:"<b>[Talk Calendar]</b> Event added<br><b>Team meeting</b> · Mon 7/6, 9:00 PM<br><span>Reminder set 30 min before</span>",result:"<b>Added to Talk Calendar</b> — reminders set for all.<br><span>Collect the meeting place next?</span>"}},
 {cap:"Pick the place",sub:"Short-answer preferences → dedupe → tally candidates",member:"form",who:"Minji",channel:"KakaoTalk",think:"Building",send:"Sending",cmd:"Collect meeting-place candidates",draft:"Built a <b>short-answer</b> form for preferred places.<br><span>I'll tidy addresses via KakaoMap</span>",kko:"<b>[TeamplayTalk]</b> Meeting place<br><span>Write where you'd like to meet &#9656;</span>",form:{type:"text",title:"Meeting place",answer:"A study cafe near Gangnam Station"},result:"Tallied — <b>Gangnam Station</b> leads with 3.<br><span>Set to Gangnam Station and announced.</span>"},
 {cap:"Check progress each night",sub:"9 PM auto → check off what's done",member:"autoform",who:"Minji",channel:"KakaoTalk",think:"Check-in",send:"Auto-send",sched:"&#9200; Daily 9:00 PM · auto",draft:"Sent the night check-in form to team KakaoTalk.",kko:"<b>[TeamplayTalk]</b> Today's progress · 9:00 PM<br><span>Check off what you finished &#9656;</span>",form:{type:"check",title:"Today's check-in",items:[{t:"Polish form-screen UX",on:true},{t:"Organize dashboard IA",on:true},{t:"Final demo-screen check",on:false}],note:"Blocked: the form breaks responsively on mobile"},result:"Check-ins <b>collected</b>.<br><span>Auto-rolled into tomorrow's morning report.</span>"},
 {cap:"A report every morning",sub:"9 AM auto → yesterday·today·tomorrow·meeting",member:"auto",who:"Minji",channel:"KakaoTalk",big:true,think:"Report",send:"Auto-send",sched:"&#9200; Daily 9:00 AM · auto",draft:"Built the morning report from last night's check-ins.",kko:"<b>[TeamplayTalk] Today's progress report · 9:00 AM</b><br><b>Done yesterday</b><br>· Polish form-screen UX<br>· Organize dashboard IA<br><b>Today</b><br>· Final demo-screen check · fix mobile responsiveness<br><b>Tomorrow</b><br>· Tidy demo-rehearsal screens<br><b>Meeting today</b> 9:00 PM<br><b>Blocked</b><br>· Form breaks responsively on mobile",result:"Auto-sent to everyone's KakaoTalk.<br><span>Delays·risks are summarized separately to the owner.</span>"},
 {cap:"Wrap up & announce",sub:"Check the dashboard · announce to team KakaoTalk",member:"notice",who:"Minji",channel:"KakaoTalk",big:true,think:"Summing",send:"Announce",cmd:"Announce everything decided so far to the team",draft:"Summarized the confirmed items.",kko:"<b>[TeamplayTalk] Contest progress summary</b><br><b>Confirmed</b><br>· Roadmap: 6 stages<br>· Roles assigned<br>· Meeting <b>Mon 7/6, 9:00 PM</b><br>· Submission <b>7/10</b><br><b>Focus today</b><br>· Stabilize backend · verify OAuth · polish demo · draft the pitch<br><span>Please check your todos</span>",result:"Announcement sent to the whole team.<br><span>See the full flow on the dashboard.</span>"}
];
var CHIPS_KO=["대회방 만들어줘","로드맵 만들어줘","역할 나눠줘","할 일 만들어줘","클라우드 뭐 쓸지 물어봐","회의 시간 잡아줘","회의 장소 받아봐","⏰ 밤 9시 · 자동 체크인","⏰ 다음날 아침 · 자동 리포트","진행 공지해줘"];
var CHIPS_EN=["Create the contest room","Build a roadmap","Split the roles","Make the to-dos","Ask which cloud to use","Find a meeting time","Collect meeting places","⏰ 9 PM · auto check-in","⏰ Next morning · auto report","Announce the progress"];
var _LB={"대기":"Idle","자동 실행":"Auto","방장 입력":"Input","명령 수신":"Received","처리 중":"Working","완료 ✓":"Done ✓","카톡 전송":"Sending","폼 작성":"Filling","제출":"Submit","응답 수집":"Collecting","PlayMCP 참여":"Joining","초대코드 입력":"Code","합류":"Joined","폼 도착":"Form in","도착":"Received","알림":"Alert","응답":"Reply","카카오톡":"KakaoTalk","팀원":"Member","제출됨 ✓":"Submitted ✓"};
function tr(s){return (LANG==='en'&&_LB[s]!==undefined)?_LB[s]:s;}
"""


_I18N_TAIL = "(function(){function apply(){var els=document.querySelectorAll('[data-i18n]');for(var i=0;i<els.length;i++){var el=els[i];if(el.__ko===undefined)el.__ko=el.innerHTML;var k=el.getAttribute('data-i18n');el.innerHTML=(LANG==='en'&&EN[k]!==undefined)?EN[k]:el.__ko;}document.documentElement.lang=LANG;document.title=(LANG==='en'&&EN.doc_title)?EN.doc_title:KO_TITLE;}window.__tptApply=apply;var tgs=document.querySelectorAll('.lang-toggle');function paint(){for(var i=0;i<tgs.length;i++)tgs[i].setAttribute('data-lang',LANG);}if(LANG==='en')apply();paint();for(var i=0;i<tgs.length;i++){tgs[i].addEventListener('click',function(){LANG=(LANG==='en')?'ko':'en';try{localStorage.setItem('tpt_lang',LANG)}catch(e){}apply();paint();if(window.__tptReloadCD)window.__tptReloadCD();if(window.__tptReloadSR)window.__tptReloadSR();});}})();"
_LANG_CSS = '.lang-toggle{display:inline-flex;align-items:center;gap:0;padding:3px;border-radius:999px;cursor:pointer;font-family:inherit;font-weight:800;font-size:12px;line-height:1;color:var(--muted);margin-left:0}.lang-toggle span{padding:6px 9px;border-radius:999px;transition:color .2s,background .2s,box-shadow .2s;letter-spacing:.03em}.lang-toggle[data-lang="ko"] span:first-child,.lang-toggle[data-lang="en"] span:last-child{color:var(--violet);background:rgba(255,255,255,.72);box-shadow:0 2px 8px rgba(80,52,140,.14),inset 0 1px 1px rgba(255,255,255,.9)}'


def _page() -> str:
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>teamplay-talk — 팀플의 PM을, AI에게</title>
<meta name="description" content="AI에게 한마디면 투표·회의 시간·역할 분배·로드맵·데일리 리포트까지. 결과는 팀원들의 카카오톡으로. 팀플 조율을 AI가 PM처럼 해내는 Kakao PlayMCP 협업 도구.">
<meta property="og:title" content="teamplay-talk — 팀플의 PM을, AI에게">
<meta property="og:description" content="조율은 AI가, 팀은 실행만. Kakao PlayMCP에서 바로 연결하세요.">
<meta property="og:image" content="/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#F4F1FB">
<link rel="icon" type="image/png" href="/favicon.png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<link rel="stylesheet" href="{_FONT_CSS}" media="print" onload="this.media='all'">
<noscript><link rel="stylesheet" href="{_FONT_CSS}"></noscript>
<style>{_CSS}{_LANG_CSS}</style>
</head>
<body>

<nav class="nav">
  <div class="nav-pill lg">
    <a class="nav-brand" href="#top"><img src="/icon-mark.png" alt="teamplay-talk" width="28" height="28"> teamplay-talk</a>
    <div class="nav-links">
      <a href="#how" data-i18n="nav_how">작동 방식</a><a href="#tutorial" data-i18n="nav_demo">데모</a><a href="#flow" data-i18n="nav_flow">워크플로우</a><a href="#features" data-i18n="nav_features">기능</a><a href="#makers" data-i18n="nav_makers">제작자</a>
    </div>
    <a class="nav-cta" href="https://playmcp.kakao.com" target="_blank" rel="noopener" data-i18n="nav_cta">PlayMCP 연결</a>
    <button class="lang-toggle lg lt-nav" type="button" aria-label="Language / 언어"><span>KO</span><span>EN</span></button>
  </div>
</nav>

<header class="hero" id="top">
  <div class="wrap hero-inner">
    <div>
      <span class="hero-badge lg"><span class="dot"></span><span data-i18n="hero_badge">Kakao PlayMCP · 팀플 협업 MCP</span></span>
      <h1 data-i18n="hero_h1">팀플의 PM을,<br>AI에게 <span class="mlg">맡기세요<svg class="wave-underline" viewBox="0 0 120 14" preserveAspectRatio="none" aria-hidden="true"><defs><linearGradient id="ulg" x1="0" y1="0" x2="1" y2="0"><stop stop-color="#7c3aed"/><stop offset="1" stop-color="#22b8ff"/></linearGradient></defs><path d="M1.5 9.2 C12.5 3.2 24.5 3.2 35.8 8.8 C47.7 14 57.5 13.4 68.4 7.4 C80.2 1.5 91.2 2.7 102.3 8.5 C111.4 13.1 116.8 11.1 118.5 7.4" fill="none" stroke="url(#ulg)" stroke-width="4.5" stroke-linecap="round"/></svg></span></h1>
      <p class="hero-sub" data-i18n="hero_sub">투표, 회의 시간, 역할 분배, 로드맵, 데일리 리포트까지.
      손 많이 가는 팀플 조율은 AI가 PM처럼 맡고, 팀원은 늘 쓰던 카카오톡으로 응답만 하면 돼요.</p>
      <div class="hero-ctas">
        <a class="btn btn-primary" href="https://playmcp.kakao.com" target="_blank" rel="noopener" data-i18n="cta_primary">PlayMCP에서 연결하기</a>
        <a class="btn btn-ghost lg" href="#how" data-i18n="cta_ghost">작동 방식 보기</a>
      </div>
    </div>
    <div class="hero-visual">
      <div class="chat-demo">
        <div class="cd-card lg">
          <div class="cd-head"><span class="cd-dot"></span><span data-i18n="chat_head">teamplay-talk · AI 대화 예시</span></div>
          <div class="cd-window" id="cdWindow"></div>
        </div>
        <div class="cd-dock">
          <div class="cd-bar lg"><div class="demo-chips" id="demoChips">{_chips_html()}</div></div>
          <button class="cd-replay lg" id="cdReplay" type="button" aria-label="다시 재생">↻</button>
        </div>
      </div>
    </div>
  </div>
</header>

<section class="sec" id="how">
  <div class="wrap">
    <div class="sec-head rv">
      <span class="eyebrow">How it works</span>
      <h2 data-i18n="how_h2">방장이 한마디면,<br>팀 전체에 후두둑.</h2>
      <p data-i18n="how_p">설치도, 새 앱도 없습니다. 팀원들은 늘 쓰던 카카오톡으로 폼과 알림을 받고, 링크 하나로 응답합니다.</p>
    </div>
    <div class="steps">
      <div class="step card rv d1"><div class="no">STEP 1</div><h3 data-i18n="s1t">PlayMCP에서 연결</h3><p data-i18n="s1d">카카오 로그인 한 번으로 teamplay-talk가 AI 에이전트에 연결됩니다.</p></div>
      <div class="step card rv d2"><div class="no">STEP 2</div><h3 data-i18n="s2t">AI에게 말하기</h3><p data-i18n="s2d">"역할 나눠줘", "회의 시간 잡아줘". 자연어 한마디면 충분합니다.</p></div>
      <div class="step card rv d3"><div class="no">STEP 3</div><h3 data-i18n="s3t">팀에 자동 전파</h3><p data-i18n="s3d">폼·투표·공지가 팀원들의 카카오톡으로 퍼집니다.</p></div>
      <div class="step card rv d1"><div class="no">STEP 4</div><h3 data-i18n="s4t">AI가 정리·결정</h3><p data-i18n="s4d">응답이 모이면 AI가 받아서 분석하고, 결과와 다음 행동까지 정리해줘요.</p></div>
    </div>
    <div class="flow-line rv">
      <span class="flow-node card" data-i18n="flow1"><b>PlayMCP</b>에서 AI와 대화</span><span class="flow-arrow" aria-hidden="true">→</span>
      <span class="flow-node card" data-i18n="flow2"><b>teamplay-talk</b>가 실행</span><span class="flow-arrow" aria-hidden="true">→</span>
      <span class="flow-node card" data-i18n="flow3">팀원 <b>카톡 · 폼 · 캘린더</b></span>
    </div>
  </div>
</section>

<section class="sec" id="tutorial">
  <div class="wrap">
    <div class="sec-head rv">
      <span class="eyebrow">Live demo</span>
      <h2 data-i18n="tut_h2">방 개설부터 공지까지,<br>한 흐름으로.</h2>
      <p data-i18n="tut_p">방장은 PlayMCP로 AI에게 말하고, 팀원은 개인 카카오톡으로 온 폼에 응답만. AI가 로드맵·역할·일정·리포트로 정리해 다시 방장에게 보고합니다.</p>
    </div>
    {_tutorial_html()}
  </div>
</section>

<section class="sec" id="flow">
  <div class="wrap">
    <div class="sec-head rv">
      <span class="eyebrow">Workflow</span>
      <h2 data-i18n="wf_h2">결성부터 마감까지,<br>하나의 워크플로우.</h2>
      <p data-i18n="wf_p">단발 기능의 나열이 아니라, 팀플의 전 과정이 이어집니다. 각 단계의 결과가 다음 단계의 입력이 됩니다.</p>
    </div>
    <div class="pipe">{_pipeline_html()}</div>
  </div>
</section>

<section class="sec" id="features">
  <div class="wrap">
    <div class="sec-head rv">
      <span class="eyebrow">Features</span>
      <h2 data-i18n="feat_h2">이럴 때, 이렇게 도와줘요.</h2>
      <p data-i18n="feat_p">어떤 결정이 필요한 순간마다 하나씩. 팀원은 링크 하나로 응답하면 끝입니다.</p>
    </div>
    <div class="grid">{_features_html()}</div>
  </div>
</section>

<section class="sec" id="makers">
  <div class="wrap">
    <div class="sec-head rv">
      <span class="eyebrow">Makers</span>
      <h2 data-i18n="mk_h2">만든 사람들</h2>
      <p data-i18n="mk_p">둘이서 만들었습니다. 팀플이 잘 굴러가게 하는 데 진심입니다.</p>
    </div>
    <div class="makers">
      <div class="maker card rv d1 a">
        {_avatar("박", "av-park.png")}
        <div>
          <h3>박세원</h3>
          <ul class="cred">
            <li><b>University of Seoul</b> · B.Eng. Transportation Eng.</li>
            <li><b>Arthur D. Little</b> · Strategy Consulting Intern</li>
            <li><b>CnerG</b> · Analyst Intern</li>
            <li><b>Campus Startup Camp</b> · 3rd of 40+ teams</li>
          </ul>
        </div>
      </div>
      <div class="maker card rv d2 b">
        {_avatar("함", "av-hbg.png")}
        <div>
          <h3>함봉구</h3>
          <ul class="cred">
            <li><b>KAIST</b> · B.S. School of Computing</li>
            <li><b>Kaggle</b> · Orbit Wars Silver Medalist</li>
            <li><b>Plask Corp.</b> · Prompt Engineering Intern</li>
            <li><b>SCPC 2025</b> · Finalist</li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</section>

<section class="sec" id="connect">
  <div class="wrap">
    <div class="connect card rv">
      <span class="eyebrow">Connect</span>
      <h2 style="margin-top:14px" data-i18n="cn_h2">PlayMCP에서 바로 연결하세요</h2>
      <p data-i18n="cn_p">카카오 로그인 한 번이면 끝. 개발자는 MCP 엔드포인트로 직접 연결할 수도 있습니다.</p>
      <div class="endpoint" role="button" tabindex="0" onclick="copyEndpoint(this)"><span class="ep-url">https://teamplay-talk.tech/mcp/</span><span class="ep-copy" data-i18n="cn_copy">복사</span></div>
      <div class="hero-ctas" style="margin-top:32px">
        <a class="btn btn-primary" href="https://playmcp.kakao.com" target="_blank" rel="noopener" data-i18n="cta_primary">PlayMCP에서 연결하기</a>
      </div>
    </div>
  </div>
</section>

<footer>
  <div class="wrap foot">
    <div class="foot-brand"><img src="/icon-mark.png" alt="" width="30" height="30"> teamplay-talk</div>
    <div class="foot-end"><small>Kakao PlayMCP · AGENTIC PLAYER · © 2026 teamplay-talk</small><button class="lang-toggle lg lt-foot" type="button" aria-label="Language / 언어"><span>KO</span><span>EN</span></button></div>
  </div>
</footer>

<script>{_I18N_HEAD}{_JS}{_I18N_TAIL}</script>
</body>
</html>"""


async def view_home(_request: Request) -> HTMLResponse:
    """랜딩 페이지."""
    return HTMLResponse(_page())


def _png(name: str) -> FileResponse:
    return FileResponse(_STATIC / name, media_type="image/png")


def register_home_routes(mcp) -> None:
    """홈페이지 + 아이콘 라우트 등록."""
    mcp.custom_route("/", methods=["GET"])(view_home)
    mcp.custom_route("/favicon.png", methods=["GET"])(lambda r: _png("web-favicon-512.png"))
    mcp.custom_route("/favicon.ico", methods=["GET"])(lambda r: _png("web-favicon-512.png"))
    mcp.custom_route("/icon-mark.png", methods=["GET"])(lambda r: _png("web-mark-256.png"))
    mcp.custom_route("/apple-touch-icon.png", methods=["GET"])(lambda r: _png("apple-touch-180.png"))
    mcp.custom_route("/og-image.png", methods=["GET"])(lambda r: _png("og-image.png"))
    mcp.custom_route("/av-park.png", methods=["GET"])(lambda r: _png("av-park.png"))
    mcp.custom_route("/av-hbg.png", methods=["GET"])(lambda r: _png("av-hbg.png"))
