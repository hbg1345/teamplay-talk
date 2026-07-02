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

_FONT_CSS = "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css"
_STATIC = Path(__file__).resolve().parent / "static"

_CSS = """
:root{
  --bg:#F4F1FB; --bg-2:#ECE7F8; --ink:#1b1730; --ink-soft:#3c3653; --muted:#6d6688; --quiet:#9990b0;
  --violet:#7c3aed; --violet-2:#6d5cf5; --cyan:#22b8ff;
  --card:#ffffff; --line:rgba(96,66,168,.14); --line-hi:rgba(96,66,168,.28);
  --accent:linear-gradient(120deg,#9333ea,#6d5cf5 52%,#22b8ff);
  --shadow:0 16px 44px rgba(80,52,140,.12); --shadow-sm:0 6px 20px rgba(80,52,140,.08);
  --radius:16px; --radius-lg:24px;
  --font:"Pretendard Variable",Pretendard,"Apple SD Gothic Neo","Noto Sans KR",system-ui,-apple-system,sans-serif;
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
.nav-pill{display:flex;align-items:center;gap:6px;max-width:min(760px,calc(100% - 32px));margin:0 auto;padding:8px 10px 8px 12px;border-radius:999px}
.nav-brand{display:flex;align-items:center;gap:9px;font-weight:800;font-size:15px;letter-spacing:-.01em;margin-right:6px;color:var(--ink)}
.nav-brand img{width:28px;height:28px;border-radius:8px}
.nav-links{display:flex;gap:2px;margin-left:auto}
.nav-links a{padding:8px 13px;border-radius:999px;font-size:14px;color:var(--ink-soft);transition:background .18s,color .18s}
.nav-links a:hover{background:rgba(124,58,237,.09);color:var(--ink)}
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
.mlg{position:relative;display:inline-block;color:var(--violet)}
.wave-underline{position:absolute;left:-3%;bottom:-14px;width:106%;height:14px;overflow:visible}
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
.cd-bar::after{content:"";position:absolute;top:1px;bottom:1px;right:1px;width:36px;border-radius:0 999px 999px 0;pointer-events:none;background:linear-gradient(90deg,rgba(247,244,252,0),rgba(247,244,252,.9))}
.demo-chips{display:flex;flex-wrap:nowrap;gap:3px;margin:0;overflow-x:auto;scrollbar-width:none}
.demo-chips::-webkit-scrollbar{display:none}
.demo-chip{flex:none;display:flex;align-items:center;gap:7px;padding:9px 14px;border-radius:999px;font-size:13px;font-weight:600;color:var(--ink-soft);background:transparent;border:0;cursor:pointer;white-space:nowrap;transition:color .18s,background .18s;font-family:inherit}
.demo-chip .ci{width:16px;height:16px;flex:none}
.demo-chip .ci svg{width:16px;height:16px;stroke:currentColor;fill:none;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round}
.demo-chip:hover{color:var(--ink)}
.demo-chip.active{color:var(--violet);background:rgba(255,255,255,.92);box-shadow:0 2px 10px rgba(80,52,140,.14)}
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
.steps{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-bottom:52px}
.step{padding:26px 24px;border-radius:var(--radius)}
.step .no{font-size:13px;font-weight:800;color:var(--violet);letter-spacing:.12em}
.step h3{font-size:19px;margin:10px 0 8px}
.step p{color:var(--muted);font-size:14.5px;margin:0}
@media(max-width:820px){.steps{grid-template-columns:minmax(0,1fr)}}
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
.makers{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;max-width:860px}
@media(max-width:720px){.makers{grid-template-columns:minmax(0,1fr)}}
.maker{display:flex;gap:20px;padding:28px;border-radius:var(--radius-lg);align-items:center}
.maker .face{width:82px;height:82px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;font-size:26px;font-weight:800;color:#fff;background:var(--violet)}
.maker.b .face{background:var(--violet-2)}
.maker h3{font-size:19px}
.maker .cred{list-style:none;margin:9px 0 0;padding:0;display:flex;flex-direction:column;gap:5px}
.maker .cred li{font-size:13px;color:var(--muted);line-height:1.4}
.maker .cred li b{color:var(--ink);font-weight:700}

/* ── 연결 CTA ── */
.connect{padding:60px min(6vw,72px);border-radius:28px;text-align:center;position:relative;overflow:hidden;background:var(--card)}
.connect h2{position:relative;z-index:1}
.connect p{color:var(--muted);margin:14px auto 0;max-width:480px;position:relative;z-index:1}
.endpoint{position:relative;z-index:1;display:inline-flex;align-items:center;gap:12px;margin-top:30px;padding:12px 14px 12px 22px;border-radius:999px;background:var(--bg-2);
  max-width:100%;flex-wrap:wrap;justify-content:center;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:14px;color:var(--ink-soft);word-break:break-all}
@media(max-width:480px){.endpoint{font-size:12px;padding:11px 14px;gap:8px}}
.endpoint button{border:0;border-radius:999px;padding:8px 16px;font-size:13px;font-weight:700;cursor:pointer;color:#fff;font-family:var(--font);background:var(--accent);transition:transform .15s}
.endpoint button:active{transform:scale(.95)}
.connect .hero-ctas{justify-content:center;position:relative;z-index:1}

/* ── 푸터 ── */
footer{padding:50px 0 58px;border-top:1px solid var(--line)}
.foot{display:flex;align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap}
.foot-brand{display:flex;align-items:center;gap:11px;font-weight:800;color:var(--ink)}
.foot-brand img{width:30px;height:30px;border-radius:9px}
.foot small{color:var(--muted);font-size:13px}

/* ── 스크롤 리빌 ── */
.rv{opacity:0;transform:translateY(24px);transition:opacity .7s cubic-bezier(.2,.8,.2,1),transform .7s cubic-bezier(.2,.8,.2,1)}
.rv.vis{opacity:1;transform:none}
.rv.d1{transition-delay:.08s}.rv.d2{transition-delay:.16s}.rv.d3{transition-delay:.24s}

@media (prefers-reduced-motion: reduce){
  *,*:before,*:after{animation:none!important;transition:none!important}
  .rv,.cd-msg{opacity:1;transform:none}
  html{scroll-behavior:auto}
}
"""

_JS = """
const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('vis');io.unobserve(e.target)}}),{threshold:.14});
document.querySelectorAll('.rv').forEach(el=>io.observe(el));
function copyEndpoint(btn){
  const url='https://teamplay-talk.tech/mcp/';
  if(!btn.dataset.label)btn.dataset.label=btn.textContent;
  const flash=ok=>{btn.textContent=ok?'복사됨!':'복사 실패';clearTimeout(btn._t);btn._t=setTimeout(()=>{btn.textContent=btn.dataset.label},1600)};
  if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(url).then(()=>flash(true)).catch(()=>flash(false));}
  else{try{const ta=document.createElement('textarea');ta.value=url;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.focus();ta.select();document.execCommand('copy');document.body.removeChild(ta);flash(true)}catch(e){flash(false)}}
}
window.copyEndpoint=copyEndpoint;

// 인터랙티브 채팅 데모 — 실제 MCP 흐름(확인 게이트). CD 순서 = 칩 순서.
const CD=[
 [{r:'user',t:'이번 주 회의 시간 잡아줘'},
  {r:'ai',t:'오늘부터 2주 <b>가능 시간표</b>를 만들었어요. 팀원 4명에게 보낼까요?'},
  {r:'user',t:'응 보내줘'},
  {r:'ai',t:'전원 응답 완료 — <b>화 20:00</b>이 4명 다 가능해요.<br>공지하고 톡캘린더에 등록했어요.'}],
 [{r:'user',t:'역할 좀 나눠줘'},
  {r:'ai',t:'<b>4개 역할</b>(기획·개발·디자인·문서)로 나눴어요. 선호 순위 받을까요?'},
  {r:'user',t:'ㅇㅇ'},
  {r:'ai',t:'팀원들 <b>선호 순위</b>를 받았어요. 이제 배정할게요.'},
  {r:'ai',t:'선호·난이도 균형으로 배정했어요.<br>세원 <b>기획</b> · 봉구 <b>개발</b> · 지윤 <b>디자인</b> · 민아 <b>문서</b><br>확정하고 공지했어요.'}],
 [{r:'user',t:'회식 메뉴 정하자'},
  {r:'ai',t:'후보 4개로 <b>익명 투표</b>를 만들었어요. 보낼까요?'},
  {r:'user',t:'보내줘'},
  {r:'ai',t:'집계 완료 — <b>삼겹살</b> 5표로 1등 (초밥 2·파스타 1). 결과 공지했어요.'}],
 [{r:'user',t:'카카오 MCP 대회 로드맵 짜줘'},
  {r:'ai',t:'마감(7/14)까지 <b>6단계</b>로 잡았어요.<br>1 주제·기획 <span>~6/20</span><br>2 서버+카카오 인증 <span>~6/26</span><br>3 핵심 기능 <span>~7/4</span><br>4 홈페이지·데모 <span>~7/9</span><br>5 QC·리허설 <span>~7/12</span><br>6 제출 <span>~7/14</span>'},
  {r:'user',t:'좋아'},
  {r:'ai',t:'확정 — 각 단계를 <b>개인 todo</b>로 쪼개 배정했어요 (봉구 인증 · 지윤 폼 UI · 민아 발표…). 각자 카톡으로 보냈어요.'}],
 [{r:'user',t:'오늘 팀 현황 어때?'},
  {r:'ai',t:'어젯밤 체크인 요약이에요.<br>완료 4 · 진행 3 · 밀림 1<br>봉구 인증 <b>완료</b> · 지윤 폼 UI 60% · 민아 발표 <b>밀림</b>(오늘 이월)<br>아침 리포트 보낼까요?'},
  {r:'user',t:'응'},
  {r:'ai',t:'팀 카톡에 <b>아침 리포트</b> 보냈어요. 밀린 일은 오늘 체크인에 자동으로 올라가요.'}],
 [{r:'user',t:'모일 장소 정하자'},
  {r:'ai',t:'각자 <b>선호 지역</b>을 폼으로 받을게요. 보낼까요?'},
  {r:'user',t:'ㅇㅇ'},
  {r:'ai',t:'투표 결과 <b>강남역</b> 3표 (홍대 1). 강남역으로 정해 공지했어요.'}]
];
let cdTok=0, cdCur=0;
function cdPlay(i){
  cdCur=i;
  document.querySelectorAll('.demo-chip').forEach((c,idx)=>c.classList.toggle('active',idx===i));
  const win=document.getElementById('cdWindow'); if(!win)return; win.innerHTML='';
  const my=++cdTok; let delay=150;
  CD[i].forEach(m=>{
    setTimeout(()=>{ if(my!==cdTok)return;
      const el=document.createElement('div'); el.className='cd-msg '+m.r; el.innerHTML=m.t;
      win.appendChild(el); win.scrollTop=win.scrollHeight;
    },delay);
    delay += m.r==='user'?750:Math.min(2600, 1000 + m.t.length*9);
  });
}
(function(){
  document.querySelectorAll('.demo-chip').forEach((b,i)=>b.addEventListener('click',()=>cdPlay(i)));
  const rb=document.getElementById('cdReplay'); if(rb)rb.addEventListener('click',()=>cdPlay(cdCur));
  if(document.querySelector('.demo-chip')) cdPlay(0);
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


# 채팅 데모 칩 (순서 = JS CD 순서)
_CHIPS = [("grid", "회의 시간"), ("roles", "역할 분배"), ("poll", "투표"),
          ("map", "로드맵"), ("sun", "데일리"), ("pin", "약속 장소")]

# 기능 카드 — 튜토리얼/설명톤: "언제 쓰고, 어떤 결정에 도움되는지"
_FEATURES = [
    ("poll", "투표 · 의견 모으기", "회식 메뉴부터 발표 주제까지, 의견이 갈릴 때. 팀 답을 한곳에 모아 무엇을 원하는지 한눈에 보여줘요."),
    ("grid", "회의 시간 맞추기", "다들 언제 되는지 몰라 헤맬 때. 각자 가능한 시간을 받아 모두가 되는 시간을 짚어줘요."),
    ("pin", "약속 장소 정하기", "어디서 볼지 정할 때. 후보를 모아 팀이 직접 고르게 해, 한 사람이 정하는 부담을 덜어줘요."),
    ("roles", "역할 나누기", "누가 뭘 맡을지 애매할 때. 선호와 난이도를 함께 보고 공평하게 나눠, 뒷말 없는 분배를 도와줘요."),
    ("map", "로드맵 · 할 일 쪼개기", "무엇부터 할지 막막할 때. 큰 그림을 세우고 각자 할 일까지 나눠, 다음에 뭘 할지 분명해져요."),
    ("sun", "매일 진행 챙기기", "진행이 흐지부지될 때. 매일 현황을 모아 누가 어디까지 왔는지 아침에 정리해줘요."),
    ("bell", "공지 · 일정 흘려보내기", "정한 걸 놓치지 않게. 결정과 일정을 팀 카톡과 톡캘린더로 바로 전해줘요."),
    ("dash", "팀 상태 한눈에 보기", "전체가 궁금할 때. 투표·체크인·결정을 한 화면에 모아 팀이 어디쯤인지 보여줘요."),
]

_PIPELINE = [
    ("01", "방 만들고 초대", "초대 코드 하나로 팀원 합류 — 이후 모든 조율이 이 방을 중심으로 돌아갑니다.", "room"),
    ("02", "로드맵 수립", "주제를 말하면 AI가 마일스톤을 설계하고, 팀 의견을 모아 다듬습니다.", "roadmap"),
    ("03", "역할 분배", "선호 순위 투표 → 난이도 균형 배정 → 방장 확인 후 확정.", "roles"),
    ("04", "개인 todo 분해", "마일스톤을 역할별 실행 todo로 쪼개 각자에게 연결합니다.", "todo"),
    ("05", "데일리 루프", "밤 체크인 → 아침 리포트 → 밀린 일 추적까지 자동으로 돌아갑니다.", "daily"),
    ("06", "회의·공지·캘린더", "회의 시간 확정, 전원 공지, 톡캘린더 등록까지 마무리합니다.", "meet"),
]


def _chips_html() -> str:
    return "".join(
        f'<button class="demo-chip" type="button"><span class="ci">{_icon(ico)}</span>{label}</button>'
        for ico, label in _CHIPS
    )


def _features_html() -> str:
    return "".join(
        f'<div class="feat card rv d{i % 4 % 3 + 1}">'
        f'<div class="ico">{_icon(ico)}</div><h3>{title}</h3><p>{desc}</p></div>'
        for i, (ico, title, desc) in enumerate(_FEATURES)
    )


def _pipeline_html() -> str:
    return "".join(
        f'<div class="pipe-item rv"><div class="pipe-dot lg">{no}</div>'
        f'<div class="pipe-card card"><h3>{title}<span class="tag">{tag}</span></h3><p>{desc}</p></div></div>'
        for no, title, desc, tag in _PIPELINE
    )


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
<style>{_CSS}</style>
</head>
<body>

<nav class="nav">
  <div class="nav-pill lg">
    <a class="nav-brand" href="#top"><img src="/icon-mark.png" alt="teamplay-talk" width="28" height="28"> teamplay-talk</a>
    <div class="nav-links">
      <a href="#how">작동 방식</a><a href="#flow">워크플로우</a><a href="#features">기능</a><a href="#makers">제작자</a>
    </div>
    <a class="nav-cta" href="https://playmcp.kakao.com" target="_blank" rel="noopener">PlayMCP 연결</a>
  </div>
</nav>

<header class="hero" id="top">
  <div class="wrap hero-inner">
    <div>
      <span class="hero-badge lg"><span class="dot"></span>Kakao PlayMCP · 팀플 협업 MCP</span>
      <h1>팀플의 PM을,<br>AI에게 <span class="mlg">맡기세요<svg class="wave-underline" viewBox="0 0 120 14" preserveAspectRatio="none" aria-hidden="true"><defs><linearGradient id="ulg" x1="0" y1="0" x2="1" y2="0"><stop stop-color="#7c3aed"/><stop offset="1" stop-color="#22b8ff"/></linearGradient></defs><path d="M3 9 q15 -8 30 0 t30 0 t30 0 t24 0" fill="none" stroke="url(#ulg)" stroke-width="4.5" stroke-linecap="round"/></svg></span></h1>
      <p class="hero-sub">AI에게 한마디면 — 투표, 회의 시간, 역할 분배, 로드맵, 데일리 리포트가
      팀원들의 카카오톡으로. 조율은 AI가 PM처럼, 팀은 실행만 합니다.</p>
      <div class="hero-ctas">
        <a class="btn btn-primary" href="https://playmcp.kakao.com" target="_blank" rel="noopener">PlayMCP에서 연결하기</a>
        <a class="btn btn-ghost lg" href="#how">작동 방식 보기</a>
      </div>
    </div>
    <div class="hero-visual">
      <div class="chat-demo">
        <div class="cd-card lg">
          <div class="cd-head"><span class="cd-dot"></span>teamplay-talk · AI 대화 예시</div>
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
      <h2>방장이 톡 하면,<br>팀 전체에 후두둑.</h2>
      <p>설치도, 새 앱도 없습니다. 팀원들은 늘 쓰던 카카오톡으로 폼과 알림을 받고, 링크 하나로 응답합니다.</p>
    </div>
    <div class="steps">
      <div class="step card rv d1"><div class="no">STEP 1</div><h3>PlayMCP에서 연결</h3><p>카카오 로그인 한 번으로 teamplay-talk가 AI 에이전트에 연결됩니다.</p></div>
      <div class="step card rv d2"><div class="no">STEP 2</div><h3>AI에게 말하기</h3><p>"역할 나눠줘", "회의 시간 잡아줘" — 자연어 한마디면 충분합니다.</p></div>
      <div class="step card rv d3"><div class="no">STEP 3</div><h3>팀에 자동 전파</h3><p>폼·투표·공지·캘린더가 팀원들의 카톡으로 퍼지고, 응답이 모이면 결정까지.</p></div>
    </div>
    <div class="flow-line rv">
      <span class="flow-node card"><b>PlayMCP</b>에서 AI와 대화</span><span class="flow-arrow" aria-hidden="true">→</span>
      <span class="flow-node card"><b>teamplay-talk</b>가 실행</span><span class="flow-arrow" aria-hidden="true">→</span>
      <span class="flow-node card">팀원 <b>카톡 · 폼 · 캘린더</b></span>
    </div>
  </div>
</section>

<section class="sec" id="flow">
  <div class="wrap">
    <div class="sec-head rv">
      <span class="eyebrow">Workflow</span>
      <h2>결성부터 마감까지,<br>하나의 워크플로우.</h2>
      <p>단발 기능의 나열이 아니라, 팀플의 전 과정이 이어집니다. 각 단계의 결과가 다음 단계의 입력이 됩니다.</p>
    </div>
    <div class="pipe">{_pipeline_html()}</div>
  </div>
</section>

<section class="sec" id="features">
  <div class="wrap">
    <div class="sec-head rv">
      <span class="eyebrow">Features</span>
      <h2>이럴 때, 이렇게 도와줘요.</h2>
      <p>어떤 결정이 필요한 순간마다 하나씩. 팀원은 링크 하나로 응답하면 끝입니다.</p>
    </div>
    <div class="grid">{_features_html()}</div>
  </div>
</section>

<section class="sec" id="makers">
  <div class="wrap">
    <div class="sec-head rv">
      <span class="eyebrow">Makers</span>
      <h2>만든 사람들</h2>
      <p>역할을 나누기보다, 기획부터 개발까지 둘이 함께 만들었습니다.</p>
    </div>
    <div class="makers">
      <div class="maker card rv d1 a">
        <div class="face">박</div>
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
        <div class="face">함</div>
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
      <h2 style="margin-top:14px">PlayMCP에서 바로 연결하세요</h2>
      <p>카카오 로그인 한 번이면 끝. 개발자는 MCP 엔드포인트로 직접 연결할 수도 있습니다.</p>
      <div class="endpoint">https://teamplay-talk.tech/mcp/<button onclick="copyEndpoint(this)">복사</button></div>
      <div class="hero-ctas" style="margin-top:32px">
        <a class="btn btn-primary" href="https://playmcp.kakao.com" target="_blank" rel="noopener">PlayMCP에서 연결하기</a>
      </div>
    </div>
  </div>
</section>

<footer>
  <div class="wrap foot">
    <div class="foot-brand"><img src="/icon-mark.png" alt="" width="30" height="30"> teamplay-talk</div>
    <small>Kakao PlayMCP · AGENTIC PLAYER · © 2026 teamplay-talk</small>
  </div>
</footer>

<script>{_JS}</script>
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
    mcp.custom_route("/favicon.png", methods=["GET"])(lambda r: _png("web-favicon-256.png"))
    mcp.custom_route("/favicon.ico", methods=["GET"])(lambda r: _png("web-favicon-256.png"))
    mcp.custom_route("/icon-mark.png", methods=["GET"])(lambda r: _png("web-mark-96.png"))
    mcp.custom_route("/apple-touch-icon.png", methods=["GET"])(lambda r: _png("apple-touch-180.png"))
    mcp.custom_route("/og-image.png", methods=["GET"])(lambda r: _png("og-image.png"))
