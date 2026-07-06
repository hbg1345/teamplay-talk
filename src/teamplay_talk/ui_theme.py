"""Shared visual system for Teamplay Talk web surfaces."""

APP_FONT_LINKS = """
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<style>
@font-face{font-family:"Kakao Big Sans";font-style:normal;font-display:swap;font-weight:400;src:url("https://cdn.jsdelivr.net/gh/kakao/kakao-font@main/Kakao-Big-Sans/fonts/KakaoBigSans-Regular.ttf") format("truetype")}
@font-face{font-family:"Kakao Big Sans";font-style:normal;font-display:swap;font-weight:700;src:url("https://cdn.jsdelivr.net/gh/kakao/kakao-font@main/Kakao-Big-Sans/fonts/KakaoBigSans-Bold.ttf") format("truetype")}
@font-face{font-family:"Kakao Small Sans";font-style:normal;font-display:swap;font-weight:400;src:url("https://cdn.jsdelivr.net/gh/kakao/kakao-font@main/Kakao-Small-Sans/fonts/KakaoSmallSans-Regular.ttf") format("truetype")}
@font-face{font-family:"Kakao Small Sans";font-style:normal;font-display:swap;font-weight:700;src:url("https://cdn.jsdelivr.net/gh/kakao/kakao-font@main/Kakao-Small-Sans/fonts/KakaoSmallSans-Bold.ttf") format("truetype")}
</style>
"""

APP_REACT_LIQUID_IMPORTS = """
<script type="importmap">
{
  "imports": {
    "react": "https://esm.sh/react@18.2.0",
    "react-dom": "https://esm.sh/react-dom@18.2.0",
    "react-dom/client": "https://esm.sh/react-dom@18.2.0/client",
    "react/jsx-runtime": "https://esm.sh/react@18.2.0/jsx-runtime",
    "liquid-glass-react": "https://esm.sh/liquid-glass-react@1.1.1?external=react,react-dom"
  }
}
</script>
"""

APP_LUCIDE_SCRIPT = """
<script src="https://unpkg.com/lucide@0.468.0/dist/umd/lucide.min.js"></script>
"""

APP_REACT_LIQUID_BOOTSTRAP = """
<script type="module">
import React from "react";
import { createRoot } from "react-dom/client";
import LiquidGlass from "liquid-glass-react";

const liquidRoots = new WeakMap();
const defaultLiquidSelector = [
  ".glass-panel:not(.workspace)",
  ".roadmap-panel",
  ".date-tab",
  ".day-action",
  ".sd-btn",
  ".sd-navigation__complete-btn",
  ".schedule__submit button"
].join(",");
const contentWrapSelector = [
  "button",
  ".date-tab",
  ".day-action",
  ".sd-btn",
  ".sd-navigation__complete-btn",
  ".schedule__submit button"
].join(",");
const repeatedDashboardSelector = [
  ".event-avatar",
  ".kind",
  ".badge",
  ".best",
  ".mini",
  ".preference-chip",
  ".assignment-card",
  ".task-item"
].join(",");

function radiusFor(element) {
  const value = window.getComputedStyle(element).borderTopLeftRadius;
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? Math.max(6, parsed) : 8;
}

function propsFor(element) {
  const isDateControl = element.matches(".date-tab,.day-action");
  const isControl = element.matches(contentWrapSelector);
  return {
    displacementScale: isDateControl ? 4 : isControl ? 10 : 18,
    blurAmount: isDateControl ? 0.006 : isControl ? 0.018 : 0.032,
    saturation: isDateControl ? 104 : isControl ? 106 : 112,
    aberrationIntensity: isDateControl ? 0.08 : isControl ? 0.28 : 0.55,
    elasticity: isDateControl ? 0.02 : isControl ? 0.1 : 0.04,
    cornerRadius: radiusFor(element),
    padding: "0",
    overLight: false,
    mode: "standard",
    style: {
      position: "absolute",
      top: "50%",
      left: "50%",
      width: "100%",
      height: "100%",
      pointerEvents: "none"
    }
  };
}

function shouldSkipLiquid(element) {
  if (!element || element.matches(repeatedDashboardSelector)) return true;
  if (
    element.closest(".sd-root-modern") &&
    element.matches(
      ".sd-selectbase__item,.sd-ranking-item,.sd-input,.sd-comment,.sd-dropdown,.sd-tagbox,.sd-btn,.sd-navigation__complete-btn"
    )
  ) {
    return true;
  }
  return Boolean(element.closest(".timeline") && element.matches(".glass-panel,.roadmap-panel"));
}

function wrapLiquidContent(element) {
  if (!element.matches(contentWrapSelector) || element.querySelector(":scope > .liquid-react-content")) {
    return;
  }
  const content = document.createElement("span");
  content.className = "liquid-react-content";
  while (element.firstChild) content.appendChild(element.firstChild);
  element.appendChild(content);
}

function mountLiquidGlass(element) {
  if (!element || liquidRoots.has(element) || element.closest(".liquid-react-layer")) return;
  if (shouldSkipLiquid(element)) return;
  const rect = element.getBoundingClientRect();
  if (rect.width < 16 || rect.height < 16) return;

  wrapLiquidContent(element);
  element.classList.add("liquid-react-host", "liquid-react-mounted");
  if (element.matches(".date-tab,.day-action")) {
    element.classList.add("liquid-react-date-control");
  }
  const layer = document.createElement("span");
  layer.className = "liquid-react-layer";
  layer.setAttribute("aria-hidden", "true");
  element.prepend(layer);

  const root = createRoot(layer);
  liquidRoots.set(element, root);
  root.render(
    React.createElement(
      LiquidGlass,
      propsFor(element),
      React.createElement("span", { className: "liquid-react-fill" })
    )
  );
}

function enhanceLiquidGlass(selector = defaultLiquidSelector) {
  document.querySelectorAll(selector).forEach(mountLiquidGlass);
  window.__teamplayLiquidGlassCount = document.querySelectorAll(".liquid-react-layer").length;
}

window.TeamplayLiquidGlass = { enhance: enhanceLiquidGlass };
window.enhanceLiquidGlass = enhanceLiquidGlass;

let liquidTimer = 0;
function scheduleEnhance() {
  window.clearTimeout(liquidTimer);
  liquidTimer = window.setTimeout(() => enhanceLiquidGlass(), 80);
}

if (document.body) {
  enhanceLiquidGlass();
  new MutationObserver(scheduleEnhance).observe(document.body, { childList: true, subtree: true });
} else {
  document.addEventListener("DOMContentLoaded", enhanceLiquidGlass, { once: true });
}
window.__teamplayLiquidGlassReady = true;
</script>
"""

APP_BRAND_MARK_SVG = (
    '<svg class="tp-mark" viewBox="-24 -128 1856 1800" aria-hidden="true">'
    '<path fill="currentColor" d="M808.218 1235.31C1039.76 1137.05 1371 982.131 1724.1 1223.27C1792.51 1269.99 1810.09 1363.32 1763.37 1431.73C1716.65 1500.15 1623.32 1517.73 1554.91 1471.01C1354.5 1334.15 1180.49 1403.23 925.409 1511.47C808.15 1561.23 665.723 1621.97 517.716 1632.6C357.204 1644.12 197.802 1597.23 47.5386 1456.69C-12.965 1400.1 -16.1392 1305.18 40.4487 1244.68C97.0368 1184.17 191.959 1181 252.462 1237.59C341.699 1321.05 419.047 1338.91 496.238 1333.37C585.934 1326.93 682.165 1288.8 808.218 1235.31ZM808.718 659.642C1040.26 561.387 1371.5 406.466 1724.6 647.604C1793.01 694.324 1810.59 787.657 1763.87 856.069C1717.15 924.48 1623.82 942.064 1555.41 895.344C1355 758.482 1180.99 827.561 925.909 935.806C808.65 985.565 666.223 1046.31 518.216 1056.93C357.704 1068.45 198.302 1021.56 48.0386 881.026C-12.465 824.438 -15.6393 729.516 40.9487 669.012C97.5368 608.509 192.459 605.334 252.962 661.922C342.199 745.384 419.547 763.243 496.738 757.703C586.434 751.264 682.665 713.133 808.718 659.642ZM809.218 140.307C1040.76 42.0521 1372 -112.869 1725.1 128.269C1793.51 174.989 1811.09 268.322 1764.37 336.734C1717.65 405.145 1624.32 422.729 1555.91 376.009C1355.5 239.148 1181.49 308.226 926.409 416.471C809.15 466.23 666.723 526.974 518.716 537.598C358.204 549.12 198.802 502.229 48.5386 361.691C-11.965 305.103 -15.1393 210.181 41.4487 149.677C98.0368 89.1736 192.959 85.9994 253.462 142.587C342.699 226.049 420.047 243.908 497.238 238.368C586.934 231.929 683.165 193.798 809.218 140.307Z"/>'
    "</svg>"
)

APP_WORDMARK_HTML = (
    '<span class="tp-wordmark">' + APP_BRAND_MARK_SVG + "<b>teamplay-talk</b></span>"
)

APP_THEME_CSS = """
:root{
  color-scheme:light;
  --font-display:"Kakao Big Sans","Kakao Small Sans","Apple SD Gothic Neo","Noto Sans KR",ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  --font-sans:"Kakao Small Sans","Kakao Big Sans","Apple SD Gothic Neo","Noto Sans KR",ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  --ink:#17140f;
  --ink-soft:#34302a;
  --muted:#6f6a5f;
  --quiet:#928b7e;
  --canvas:#f7f4ee;
  --canvas-2:#f0ede7;
  --surface:#fffaf0;
  --surface-raised:rgba(255,252,244,.92);
  --surface-flat:rgba(255,250,240,.74);
  --panel:rgba(255,251,241,.66);
  --panel-strong:rgba(255,253,247,.86);
  --panel-soft:rgba(255,250,240,.48);
  --glass-line:rgba(33,24,8,.13);
  --glass-line-strong:rgba(37,33,29,.30);
  --glass-hi:rgba(255,255,255,.82);
  --glass-sheen:rgba(255,255,255,.42);
  --glass-edge:rgba(255,255,255,.72);
  --kakao-yellow:#fee500;
  --kakao-yellow-deep:#d9bd00;
  --kakao-yellow-soft:rgba(254,229,0,.18);
  --kakao-black:#191919;
  --workspace:#25211d;
  --workspace-2:#1b1814;
  --workspace-soft:rgba(37,33,29,.09);
  --slack-aubergine:var(--workspace);
  --slack-aubergine-soft:var(--workspace-soft);
  --slack-blue:#1264a3;
  --slack-blue-soft:rgba(18,100,163,.11);
  --slack-cyan:#36c5f0;
  --slack-cyan-soft:rgba(54,197,240,.13);
  --slack-red:#e01e5a;
  --slack-red-soft:rgba(224,30,90,.11);
  --warning:#ecb22e;
  --warning-soft:rgba(236,178,46,.18);
  --primary:var(--kakao-yellow);
  --primary-deep:var(--kakao-black);
  --primary-soft:var(--kakao-yellow-soft);
  --cyan:var(--slack-cyan);
  --cyan-soft:var(--slack-cyan-soft);
  --amber:var(--warning);
  --amber-soft:var(--warning-soft);
  --rose:var(--slack-red);
  --rose-soft:var(--slack-red-soft);
  --shadow-xl:0 34px 110px rgba(45,36,18,.18);
  --shadow-lg:0 22px 56px rgba(45,36,18,.13);
  --shadow-md:0 10px 28px rgba(45,36,18,.09);
  --blur:18px;
  --radius:8px;
  --radius-control:18px;
  --space-1:4px;
  --space-2:8px;
  --space-3:12px;
  --space-4:16px;
  --space-5:20px;
  --space-6:24px;
  --space-8:32px;
  --space-10:40px;
}
*{box-sizing:border-box}
html{
  min-height:100%;
  background:var(--canvas);
  -webkit-font-smoothing:antialiased;
  text-rendering:optimizeLegibility;
  font-kerning:normal;
}
body{
  margin:0;
  min-height:100vh;
  color:var(--ink);
  font-family:var(--font-sans);
  font-size:1rem;
  line-height:1.5;
  word-break:keep-all;
  background:
    linear-gradient(135deg, rgba(247,244,238,.98) 0%, rgba(244,240,234,.94) 48%, rgba(240,246,249,.95) 100%),
    linear-gradient(90deg, rgba(254,229,0,.035), rgba(37,33,29,.035) 46%, rgba(54,197,240,.04));
}
body:before{
  content:"";
  position:fixed;
  inset:0;
  pointer-events:none;
  z-index:0;
  background:
    linear-gradient(rgba(255,255,255,.42) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.34) 1px, transparent 1px),
    linear-gradient(135deg, rgba(254,229,0,.025), transparent 38%, rgba(37,33,29,.034) 70%, transparent);
  background-size:48px 48px,48px 48px,100% 100%;
  mask-image:linear-gradient(to bottom, rgba(0,0,0,.82), rgba(0,0,0,.46) 58%, transparent 100%);
  -webkit-mask-image:linear-gradient(to bottom, rgba(0,0,0,.82), rgba(0,0,0,.46) 58%, transparent 100%);
}
body:after{
  content:"";
  position:fixed;
  inset:0;
  pointer-events:none;
  z-index:0;
  background:
    linear-gradient(180deg, rgba(255,255,255,.62), rgba(255,255,255,0) 30%),
    linear-gradient(120deg, rgba(254,229,0,.055), transparent 28%, rgba(37,33,29,.045) 70%, transparent);
}
button,input,textarea,select{font:inherit}
button{cursor:pointer}
::selection{background:rgba(254,229,0,.45)}
.glass-panel{
  position:relative;
  isolation:isolate;
  overflow:hidden;
  border:1px solid rgba(33,24,8,.11);
  border-radius:var(--radius);
  background:
    linear-gradient(180deg, rgba(255,255,255,.62), rgba(255,250,237,.42)),
    linear-gradient(135deg, rgba(255,255,255,.12), transparent 58%),
    var(--panel);
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,.58),
    inset 0 -1px 0 rgba(255,255,255,.22),
    var(--shadow-lg);
  backdrop-filter:blur(14px) saturate(1.08);
  -webkit-backdrop-filter:blur(14px) saturate(1.08);
}
.glass-panel:before{
  content:"";
  position:absolute;
  inset:0;
  z-index:0;
  pointer-events:none;
  border-radius:inherit;
  padding:1px;
  background:linear-gradient(180deg, rgba(255,255,255,.64), rgba(255,255,255,.10) 52%, rgba(33,24,8,.10));
  -webkit-mask:linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite:xor;
  mask-composite:exclude;
  opacity:.52;
}
.glass-panel:after{
  content:"";
  position:absolute;
  inset:1px;
  z-index:0;
  pointer-events:none;
  border-radius:calc(var(--radius) - 1px);
  background:linear-gradient(180deg, rgba(255,255,255,.10), transparent 46%);
  opacity:.32;
  mix-blend-mode:screen;
}
.glass-panel > *{
  position:relative;
  z-index:1;
}
.liquid-react-host{
  position:relative!important;
  isolation:isolate!important;
  overflow:hidden!important;
}
.liquid-react-host > :not(.liquid-react-layer){
  position:relative;
  z-index:2;
}
.liquid-react-content{
  position:relative;
  z-index:2;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  width:100%;
  min-width:0;
  gap:inherit;
  color:inherit;
  line-height:inherit;
}
.liquid-react-host > .liquid-react-content{
  z-index:3;
}
.liquid-react-layer{
  position:absolute!important;
  inset:0!important;
  z-index:0!important;
  pointer-events:none!important;
  border-radius:inherit!important;
  overflow:hidden!important;
}
.glass-panel.liquid-react-mounted:before,
.glass-panel.liquid-react-mounted:after,
.roadmap-panel.liquid-react-mounted:before,
.roadmap-panel.liquid-react-mounted:after{
  opacity:0!important;
}
.liquid-react-layer > *,
.liquid-react-layer .relative{
  position:absolute!important;
  top:50%!important;
  left:50%!important;
  width:100%!important;
  height:100%!important;
}
.liquid-react-layer svg{
  position:absolute!important;
  inset:0!important;
  width:100%!important;
  height:100%!important;
}
.liquid-react-layer .glass{
  width:100%!important;
  height:100%!important;
  padding:0!important;
  display:flex!important;
  border-radius:inherit!important;
  box-shadow:0 8px 24px rgba(45,36,18,.08), inset 0 1px 0 rgba(255,255,255,.36)!important;
}
.liquid-react-date-control .liquid-react-content{
  white-space:nowrap;
}
.liquid-react-date-control .liquid-react-layer .glass{
  box-shadow:inset 0 1px 0 rgba(255,255,255,.28), inset 0 -1px 0 rgba(33,24,8,.04)!important;
}
.liquid-react-layer .glass > div:last-child{
  display:block!important;
  width:100%!important;
  height:100%!important;
}
.liquid-react-fill{
  display:block;
  width:100%;
  height:100%;
  border-radius:inherit;
  background:
    linear-gradient(180deg, rgba(255,255,255,.12), rgba(255,255,255,.04)),
    rgba(255,255,255,.03);
}
.glass-control{
  border:1px solid var(--glass-line);
  border-radius:var(--radius-control);
  background:
    radial-gradient(80px 42px at 20% 0%, rgba(255,255,255,.56), transparent 72%),
    linear-gradient(180deg, rgba(255,255,255,.70), rgba(255,250,240,.52));
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,.78),
    inset 0 -1px 0 rgba(255,255,255,.30),
    0 8px 22px rgba(27,33,58,.07);
  backdrop-filter:blur(12px) saturate(1.24);
  -webkit-backdrop-filter:blur(12px) saturate(1.24);
}
.primary-surface{
  background:linear-gradient(135deg,#ffe812,var(--kakao-yellow));
  color:var(--kakao-black);
  box-shadow:0 16px 36px rgba(254,229,0,.30);
}
.slack-surface{
  background:linear-gradient(135deg,var(--workspace),var(--workspace-2));
  color:#fff8e8;
  box-shadow:0 18px 44px rgba(37,33,29,.22);
}
.liquid-tap{
  transition:transform .16s cubic-bezier(.2,.8,.2,1), box-shadow .16s ease, background .16s ease;
}
.liquid-tap:hover{transform:translateY(-1px)}
.liquid-tap:active{transform:scale(.985)}
@supports (background:color-mix(in srgb, white, black)){
  .glass-panel{
    border-color:color-mix(in srgb, var(--glass-line) 82%, white);
  }
}
@media (prefers-reduced-motion: reduce){
  *,*:before,*:after{animation-duration:.01ms!important;animation-iteration-count:1!important;scroll-behavior:auto!important;transition-duration:.01ms!important}
}
.tp-wordmark{display:inline-flex;align-items:center;gap:6px;font-family:var(--font-display);font-weight:850;font-size:.82rem;letter-spacing:.01em;line-height:1;color:var(--muted);white-space:nowrap}
.tp-mark{width:15px;height:auto;flex:0 0 auto;display:block}
.tp-wordmark .tp-mark{opacity:.85}
.tp-brandbar{position:relative;z-index:1;width:min(920px,100%);margin:2px auto 14px;display:flex;justify-content:center}
.tp-brandbar--link{color:inherit;text-decoration:none;border-radius:999px}
.tp-brandbar--link:hover .tp-wordmark{color:var(--ink-soft)}
.tp-brandbar--link:focus-visible{outline:2px solid var(--kakao-yellow);outline-offset:4px}
"""
