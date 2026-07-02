"""Teamplay Talk 아이콘 — Radial Converge 변형 생성기.

컨셉: **여러 목소리가 출렁이다 하나로 모인다** 를 방사형(360° 대칭)으로.
- 동심(nested) 물결 밴드: 바깥은 크게 출렁(제각각 의견), 안으로 갈수록 진폭이
  0으로 감쇠(합의로 잔잔) → 중심에 코랄 코어(결정).
- 색은 hue 스윕 3앵커: 인디고 → 마젠타(다리) → 코랄. 파랑밭에 코랄 점 하나가
  '툭' 튀지 않고 안으로 갈수록 '익어' 도착하게. 배경은 화이트톤.
- 로고답게 **꽉 차게**: 바깥 봉우리가 캔버스 반지름의 ~93%까지 닿는다.

출력(레이어별 1024x1024 투명 SVG = Apple Icon Composer 임포트용):
  layers/00_background.svg     (화이트톤 풀블리드; Composer가 코너 마스킹)
  layers/01..0N_band_*.svg     (바깥→안쪽 물결 밴드, 이 순서로 임포트)
  layers/NN_core_spark.svg     (중심 결정 하이라이트, 아주 옅게)
  teamplay-icon-preview.svg    (전체 합성 미리보기)
  teamplay-favicon.svg         (웹 파비콘: 라운드 화이트 배경 포함)

전부 파라미터로 조종된다. 숫자만 바꾸면 모양이 바뀐다(감으로 그리지 않음).
"""

from __future__ import annotations

import math
import os

# ── 조종 파라미터 ──────────────────────────────────────────────
CANVAS = 1024
C = CANVAS / 2  # 중심
MARGIN = 36  # 캔버스 가장자리 여백(px) — 작을수록 꽉 참
N_BANDS = 6  # 동심 밴드 수(코어 포함)
FREQ = 6  # 물결 봉우리(lobe) 수 — 방사 대칭
AMP_MAX = 54.0  # 바깥 밴드 진폭(출렁 크기)
AMP_POW = 1.3  # 진폭 감쇠 지수(클수록 빨리 잔잔해짐)
PHASE0_DEG = -90.0  # 첫 봉우리 방향(위쪽)
PHASE_STAGGER_DEG = 13.0  # 밴드마다 위상 어긋남(바깥 '제각각' 느낌)
CORE_R = 70.0  # 중심 코어 기본 반지름
SAMPLES = 120  # 밴드당 샘플 점(부드러움)
STROKE_W = 11.0  # 밴드 사이 흰 리플선 두께(0이면 매끈한 그라데이션 덩어리)

# ── 색: 3스톱 그라데이션 하나 (딱 3색). 밖=인디고 → 중간=마젠타(다리) → 중심=코랄.
GRAD_EDGE = "#4f46e5"  # 인디고 (바깥 = 제각각 목소리)
GRAD_MID = "#b833d6"  # 마젠타 (인디고↔코랄 다리)
GRAD_CORE = "#f35b04"  # 코랄 (중심 = 합쳐진 결정)

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
LAYERS_DIR = os.path.join(OUT_DIR, "layers")

MAX_EXTENT = C - MARGIN  # 바깥 봉우리가 닿을 목표 반지름
BASE_OUTER = MAX_EXTENT - AMP_MAX  # 바깥 밴드 기본 반지름


def _hsl_to_hex(h: float, s: float, lig: float) -> str:
    """HSL(도, %, %) → #rrggbb."""
    h = (h % 360) / 360.0
    s /= 100.0
    lig /= 100.0
    if s == 0:
        r = g = b = lig
    else:
        q = lig * (1 + s) if lig < 0.5 else lig + s - lig * s
        p = 2 * lig - q

        def hue2rgb(t: float) -> float:
            t %= 1.0
            if t < 1 / 6:
                return p + (q - p) * 6 * t
            if t < 1 / 2:
                return q
            if t < 2 / 3:
                return p + (q - p) * (2 / 3 - t) * 6
            return p

        r = hue2rgb(h + 1 / 3)
        g = hue2rgb(h)
        b = hue2rgb(h - 1 / 3)
    return "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255), round(b * 255))


def _band_params(i: int) -> dict:
    """밴드 i(0=바깥 … N-1=코어)의 반지름·진폭·위상. 색은 공유 그라데이션이 담당."""
    t = i / (N_BANDS - 1)  # 0..1 (바깥→안쪽)
    base_r = BASE_OUTER * (1 - t) + CORE_R * t
    amp = AMP_MAX * (1 - t) ** AMP_POW
    phase = math.radians(PHASE0_DEG + PHASE_STAGGER_DEG * i)
    return {"t": t, "base_r": base_r, "amp": amp, "phase": phase}


def _smooth_closed_path(pts: list[tuple[float, float]]) -> str:
    """점들을 지나는 닫힌 Catmull-Rom → 3차 베지어 path(부드럽고 컴팩트)."""
    n = len(pts)
    d = f"M {pts[0][0]:.2f} {pts[0][1]:.2f} "
    for i in range(n):
        p0 = pts[(i - 1) % n]
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n]
        c1x, c1y = p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6
        c2x, c2y = p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6
        d += f"C {c1x:.2f} {c1y:.2f} {c2x:.2f} {c2y:.2f} {p2[0]:.2f} {p2[1]:.2f} "
    return d + "Z"


def _band_path(base_r: float, amp: float, phase: float) -> str:
    """물결 밴드 하나의 닫힌 path d 문자열."""
    pts: list[tuple[float, float]] = []
    for k in range(SAMPLES):
        th = 2 * math.pi * k / SAMPLES
        r = base_r + amp * math.sin(FREQ * th + phase)
        pts.append((C + r * math.cos(th), C + r * math.sin(th)))
    return _smooth_closed_path(pts)


def _svg(inner: str, defs: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CANVAS} {CANVAS}" '
        f'width="{CANVAS}" height="{CANVAS}">{defs}{inner}</svg>'
    )


def _background_inner(rounded: bool) -> str:
    """화이트톤 배경(중심 흰색 → 가장자리 아주 옅은 라벤더-화이트)."""
    shape = (
        f'<rect x="0" y="0" width="{CANVAS}" height="{CANVAS}" rx="230" ry="230" fill="url(#bg)"/>'
        if rounded
        else f'<rect x="0" y="0" width="{CANVAS}" height="{CANVAS}" fill="url(#bg)"/>'
    )
    return shape


_DEFS = (
    '<defs><radialGradient id="bg" cx="50%" cy="42%" r="72%">'
    '<stop offset="0%" stop-color="#ffffff"/>'
    '<stop offset="100%" stop-color="#f2f1fb"/></radialGradient>'
    f'<radialGradient id="grad" gradientUnits="userSpaceOnUse" cx="{C}" cy="{C}" r="{MAX_EXTENT:.0f}">'
    f'<stop offset="0%" stop-color="{GRAD_CORE}"/>'
    f'<stop offset="50%" stop-color="{GRAD_MID}"/>'
    f'<stop offset="100%" stop-color="{GRAD_EDGE}"/></radialGradient>'
    '<radialGradient id="spark" cx="50%" cy="50%" r="50%">'
    '<stop offset="0%" stop-color="#ffffff" stop-opacity="0.95"/>'
    '<stop offset="55%" stop-color="#ffffff" stop-opacity="0.35"/>'
    '<stop offset="100%" stop-color="#ffffff" stop-opacity="0"/></radialGradient></defs>'
)
_STROKE_ATTR = f' stroke="#f7f6fc" stroke-width="{STROKE_W}" stroke-linejoin="round"' if STROKE_W > 0 else ""


def build() -> dict:
    os.makedirs(LAYERS_DIR, exist_ok=True)
    bands = [_band_params(i) for i in range(N_BANDS)]

    # 레이어: 00 배경
    with open(os.path.join(LAYERS_DIR, "00_background.svg"), "w") as f:
        f.write(_svg(_background_inner(rounded=False), _DEFS))

    # 레이어: 01..0N 밴드 (바깥→안쪽; 임포트 순서 = 파일 순서). 색=공유 그라데이션.
    band_svgs = []
    for i, b in enumerate(bands):
        path = _band_path(b["base_r"], b["amp"], b["phase"])
        el = f'<path d="{path}" fill="url(#grad)"{_STROKE_ATTR}/>'
        band_svgs.append(el)
        name = "core" if i == N_BANDS - 1 else f"band{i+1}"
        with open(os.path.join(LAYERS_DIR, f"{i+1:02d}_{name}.svg"), "w") as f:
            f.write(_svg(el, _DEFS))

    # 레이어: 코어 스파크(결정 하이라이트)
    spark_r = CORE_R * 0.72
    spark = f'<circle cx="{C}" cy="{C}" r="{spark_r:.1f}" fill="url(#spark)"/>'
    with open(os.path.join(LAYERS_DIR, f"{N_BANDS+1:02d}_core_spark.svg"), "w") as f:
        f.write(_svg(spark, _DEFS))

    stack = "".join(band_svgs) + spark

    # 미리보기(라운드 배경 + 밴드)
    with open(os.path.join(OUT_DIR, "teamplay-icon-preview.svg"), "w") as f:
        f.write(_svg(_background_inner(rounded=True) + stack, _DEFS))

    # 웹 파비콘(라운드 화이트 배경 포함)
    with open(os.path.join(OUT_DIR, "teamplay-favicon.svg"), "w") as f:
        f.write(_svg(_background_inner(rounded=True) + stack, _DEFS))

    # 채움 비율 증명
    outer = bands[0]
    peak = outer["base_r"] + outer["amp"]
    valley = outer["base_r"] - outer["amp"]
    return {
        "bands": [
            {"i": i, "base_r": round(b["base_r"], 1), "amp": round(b["amp"], 1)}
            for i, b in enumerate(bands)
        ],
        "outer_peak": round(peak, 1),
        "outer_valley": round(valley, 1),
        "fill_peak_pct": round(peak / C * 100, 1),
        "fill_valley_pct": round(valley / C * 100, 1),
    }


if __name__ == "__main__":
    stats = build()
    print(f"색(3): edge {GRAD_EDGE} · mid {GRAD_MID} · core {GRAD_CORE}")
    print("밴드(바깥→코어):")
    for b in stats["bands"]:
        print(f"  #{b['i']} r={b['base_r']:>6} amp={b['amp']:>5}")
    print(f"바깥 봉우리 반지름 {stats['outer_peak']} / 캔버스반경 {C:.0f}"
          f" → 채움 {stats['fill_peak_pct']}% (봉우리), {stats['fill_valley_pct']}% (골)")
