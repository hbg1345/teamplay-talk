"""흰 계열 배경용 그라데이션 후보 비교 (2×2 한 장).

split_layers 의 파도 path/transform 을 재사용해, 각 후보(그라데이션+배경)를
타일로 나란히 렌더한다. objectBoundingBox 그라데이션이라 중첩 변환에 안전.
"""

from __future__ import annotations

import os

from split_layers import CANVAS, _TF, _subpaths

COMBOS = [
    ("C1  Indigo→Violet", [(0, "#3730a3"), (1, "#8b5cf6")], "#F1EFFB"),
    ("C2  Blue→Violet→Lilac", [(0, "#2b2d8f"), (0.5, "#6d28d9"), (1, "#a78bfa")], "#F1EFFB"),
    ("C3  Indigo→Periwinkle (airy)", [(0, "#4338ca"), (1, "#b3a4f7")], "#F1EFFB"),
    ("C2 · bg 더 라벤더", [(0, "#2b2d8f"), (0.5, "#6d28d9"), (1, "#a78bfa")], "#E9E4F7"),
]

T = 560  # 타일(아이콘) 크기
PAD = 48
LABEL = 34
OUT_DIR = os.path.dirname(os.path.abspath(__file__))


def _grad(gid: str, stops: list[tuple[float, str]]) -> str:
    s = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in stops)
    # objectBoundingBox 대각(TL→BR)
    return f'<linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="1">{s}</linearGradient>'


def build() -> None:
    combined = "".join(_subpaths())
    w = PAD + T + PAD + T + PAD
    h = LABEL + PAD + T + PAD + LABEL + PAD + T + PAD
    defs = "".join(_grad(f"g{i}", stops) for i, (_, stops, _) in enumerate(COMBOS))

    tiles = []
    positions = [(PAD, LABEL + PAD), (PAD + T + PAD, LABEL + PAD),
                 (PAD, LABEL + PAD + T + PAD + LABEL + PAD), (PAD + T + PAD, LABEL + PAD + T + PAD + LABEL + PAD)]
    for i, (name, _stops, bg) in enumerate(COMBOS):
        ox, oy = positions[i]
        sc = T / CANVAS
        icon = (
            f'<g transform="translate({ox} {oy}) scale({sc:.5f})">'
            f'<rect x="0" y="0" width="{CANVAS}" height="{CANVAS}" rx="230" ry="230" fill="{bg}"/>'
            f'<g transform="{_TF}"><path d="{combined}" fill="url(#g{i})"/></g></g>'
        )
        label = (
            f'<text x="{ox}" y="{oy-12}" font-family="-apple-system,Helvetica,sans-serif" '
            f'font-size="26" font-weight="700" fill="#1a1a22">{name}</text>'
        )
        tiles.append(label + icon)

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
        f'<rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff"/>'
        f"<defs>{defs}</defs>{''.join(tiles)}</svg>"
    )
    path = os.path.join(OUT_DIR, "gradient_compare.svg")
    open(path, "w").write(svg)
    print("wrote", path)


if __name__ == "__main__":
    build()
