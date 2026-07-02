"""Wave-stroke 로고를 Apple Icon Composer 임포트용 레이어로 분리.

입력: 사용자가 만든 3겹 물결 마크(Vector (Stroke).svg) — 한 path에 3개 파도 subpath,
퍼플(#BB00FF)→시안(#00F7FF) 대각 그라데이션.

출력(1024×1024):
  layers/00_background_light.svg / 00_background_dark.svg  (풀블리드 배경; 코너는 Composer가 마스킹)
  layers/01_wave_bottom.svg / 02_wave_mid.svg / 03_wave_top.svg  (투명, 각 파도 1개)
  layers/foreground_combined.svg  (파도 3개 한 겹 — '합친' 옵션)
  preview_light.svg / preview_dark.svg  (합성 미리보기, 라운드 코너)

원본 그림자/베벨은 없음(원본이 flat). Composer가 하이라이트·그림자·굴절을 네이티브로 입힌다.
그라데이션은 3파도가 같은 userSpaceOnUse 좌표를 공유해 합치면 원본과 동일하게 재구성된다.
"""

from __future__ import annotations

import os

CANVAS = 1024
# 원본 아트(viewBox 1791×1635, 약간 오버슈트)를 1024 캔버스에 ~10% 여백으로 앉히는 변환.
# 코너(스퀘어클)에 안 닿게 보수적으로. 필요하면 이 3값만 조정.
TF_SCALE = 0.455
TF_TX = 103.0
TF_TY = 140.0

# 색 = 후보 B (바이올렛→마젠타→코랄). 흰 계열 배경에서 양끝 다 삼.
GRAD_STOPS = [(0.0, "#3730a3"), (1.0, "#8b5cf6")]

BG_LIGHT = "#EBE4F8"  # 쿨 라벤더-화이트 (순백 아님) — 기본/라이트 모드
BG_DARK = "#0E0B1F"   # 딥 인디고 — 다크 모드용

# 원본 path d (3개 파도 subpath = M...Z ×3)
PATH_D = (
    "M808.218 1235.31C1039.76 1137.05 1371 982.131 1724.1 1223.27C1792.51 1269.99 1810.09 1363.32 1763.37 1431.73C1716.65 1500.15 1623.32 1517.73 1554.91 1471.01C1354.5 1334.15 1180.49 1403.23 925.409 1511.47C808.15 1561.23 665.723 1621.97 517.716 1632.6C357.204 1644.12 197.802 1597.23 47.5386 1456.69C-12.965 1400.1 -16.1392 1305.18 40.4487 1244.68C97.0368 1184.17 191.959 1181 252.462 1237.59C341.699 1321.05 419.047 1338.91 496.238 1333.37C585.934 1326.93 682.165 1288.8 808.218 1235.31Z"
    "M808.718 659.642C1040.26 561.387 1371.5 406.466 1724.6 647.604C1793.01 694.324 1810.59 787.657 1763.87 856.069C1717.15 924.48 1623.82 942.064 1555.41 895.344C1355 758.482 1180.99 827.561 925.909 935.806C808.65 985.565 666.223 1046.31 518.216 1056.93C357.704 1068.45 198.302 1021.56 48.0386 881.026C-12.465 824.438 -15.6393 729.516 40.9487 669.012C97.5368 608.509 192.459 605.334 252.962 661.922C342.199 745.384 419.547 763.243 496.738 757.703C586.434 751.264 682.665 713.133 808.718 659.642Z"
    "M809.218 140.307C1040.76 42.0521 1372 -112.869 1725.1 128.269C1793.51 174.989 1811.09 268.322 1764.37 336.734C1717.65 405.145 1624.32 422.729 1555.91 376.009C1355.5 239.148 1181.49 308.226 926.409 416.471C809.15 466.23 666.723 526.974 518.716 537.598C358.204 549.12 198.802 502.229 48.5386 361.691C-11.965 305.103 -15.1393 210.181 41.4487 149.677C98.0368 89.1736 192.959 85.9994 253.462 142.587C342.699 226.049 420.047 243.908 497.238 238.368C586.934 231.929 683.165 193.798 809.218 140.307Z"
)

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
LAYERS = os.path.join(OUT_DIR, "layers")

_GRAD = (
    '<linearGradient id="wg" gradientUnits="userSpaceOnUse" '
    'x1="0" y1="0" x2="1844" y2="1634">'
    + "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in GRAD_STOPS)
    + "</linearGradient>"
)
_TF = f'translate({TF_TX} {TF_TY}) scale({TF_SCALE})'


def _subpaths() -> list[str]:
    segs = [s for s in PATH_D.split("M") if s.strip()]
    return ["M" + s for s in segs]  # [bottom, mid, top]


def _svg(inner: str, defs: str = "") -> str:
    d = f"<defs>{defs}</defs>" if defs else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CANVAS} {CANVAS}" '
        f'width="{CANVAS}" height="{CANVAS}">{d}{inner}</svg>'
    )


def _wave(d: str) -> str:
    return f'<g transform="{_TF}"><path d="{d}" fill="url(#wg)"/></g>'


def _bg(color: str, rounded: bool) -> str:
    rx = ' rx="230" ry="230"' if rounded else ""
    return f'<rect x="0" y="0" width="{CANVAS}" height="{CANVAS}"{rx} fill="{color}"/>'


def build() -> None:
    os.makedirs(LAYERS, exist_ok=True)
    bottom, mid, top = _subpaths()

    # 배경 레이어 (풀블리드; Composer가 코너 마스킹)
    open(os.path.join(LAYERS, "00_background_light.svg"), "w").write(_svg(_bg(BG_LIGHT, False)))
    open(os.path.join(LAYERS, "00_background_dark.svg"), "w").write(_svg(_bg(BG_DARK, False)))

    # 파도 레이어 3개 (투명, 각 1개, 그림자 없음)
    names = [("01_wave_bottom", bottom), ("02_wave_mid", mid), ("03_wave_top", top)]
    for name, d in names:
        open(os.path.join(LAYERS, f"{name}.svg"), "w").write(_svg(_wave(d), _GRAD))

    # 합친 포그라운드 (한 겹 옵션)
    combined = f'<g transform="{_TF}"><path d="{bottom}{mid}{top}" fill="url(#wg)"/></g>'
    open(os.path.join(LAYERS, "foreground_combined.svg"), "w").write(_svg(combined, _GRAD))

    # 미리보기 (배경 + 3파도, 라운드)
    fg = _wave(bottom) + _wave(mid) + _wave(top)
    open(os.path.join(OUT_DIR, "preview_light.svg"), "w").write(
        _svg(_bg(BG_LIGHT, True) + fg, _GRAD)
    )
    open(os.path.join(OUT_DIR, "preview_dark.svg"), "w").write(
        _svg(_bg(BG_DARK, True) + fg, _GRAD)
    )
    print("레이어 생성 완료:", LAYERS)
    print("  배경: light/dark, 파도: bottom/mid/top, 합본: foreground_combined")
    print(f"  변환: {_TF}  (코너 안 닿게 ~10% 여백)")


if __name__ == "__main__":
    build()
