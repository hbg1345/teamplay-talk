#!/usr/bin/env python3
"""Generate Teamplay Talk app icon source layers.

Concept: Converging Aperture.

The mark is generated from a camera-aperture/focusing metaphor:

- Five colored aperture blades are placed by one polar function.
- Each blade is a curved sector between an inner radius and an outer radius.
- The blades swirl toward one central focal point, representing messy team
  signals becoming a shared decision.

Layer SVGs stay simple and mostly flat. Icon Composer should provide Liquid
Glass material, depth, specular highlights, soft shadows, and appearance-mode
tuning. The preview SVG bakes in gradients only to show the intended mood.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, pi, radians, sin
from pathlib import Path


CANVAS = 1024
CENTER = (512.0, 512.0)
OUT = Path(__file__).resolve().parent
LAYERS = OUT / "layers"

COLORS = ("#3d348b", "#7678ed", "#f7b801", "#f18701", "#f35b04")
N = len(COLORS)

INNER_RADIUS = 68.0
OUTER_RADIUS = 352.0
BLADE_WIDTH = 2 * pi / N * 0.82
SWIRL = radians(34)
BASE_ROTATION = radians(-92)


@dataclass(frozen=True)
class Blade:
    name: str
    layer_file: str
    title: str
    index: int
    angle: float
    fill: str


BLADES = tuple(
    Blade(
        name=name,
        layer_file=f"{i + 1:02d}_aperture_{name}.svg",
        title=f"{name} aperture blade",
        index=i,
        angle=BASE_ROTATION + i * 2 * pi / N,
        fill=COLORS[i],
    )
    for i, name in enumerate(("idea", "coordination", "decision", "timing", "handoff"))
)


def fmt(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def polar(radius: float, angle: float) -> tuple[float, float]:
    return (CENTER[0] + radius * cos(angle), CENTER[1] + radius * sin(angle))


def point(radius: float, angle: float) -> str:
    x, y = polar(radius, angle)
    return f"{fmt(x)} {fmt(y)}"


def blade_path(blade: Blade, scale: float = 1, offset: float = 0) -> str:
    """Create a rounded iris blade as a four-curve polar sector.

    The blade has an inner edge near the focal point, a broader outer lip, and
    a tangential skew. The skew is what makes the mark feel like an aperture
    gathering light rather than unrelated petals.
    """

    theta = blade.angle
    w = BLADE_WIDTH
    inner = INNER_RADIUS
    outer = OUTER_RADIUS

    def p(radius: float, angle: float) -> tuple[float, float]:
        x, y = polar(radius, angle)
        return (x * scale + offset, y * scale + offset)

    def s(pt: tuple[float, float]) -> str:
        return f"{fmt(pt[0])} {fmt(pt[1])}"

    p1 = p(inner, theta - w * 0.44)
    p2 = p(outer * 0.95, theta + SWIRL - w * 0.26)
    p3 = p(outer, theta + SWIRL + w * 0.48)
    p4 = p(inner * 1.42, theta + w * 0.32)

    c12a = p(inner + (outer - inner) * 0.32, theta - w * 0.58)
    c12b = p(inner + (outer - inner) * 0.78, theta + SWIRL - w * 0.44)
    c23a = p(outer * 1.02, theta + SWIRL - w * 0.02)
    c23b = p(outer * 1.02, theta + SWIRL + w * 0.24)
    c34a = p(inner + (outer - inner) * 0.72, theta + SWIRL + w * 0.68)
    c34b = p(inner + (outer - inner) * 0.28, theta + w * 0.52)
    c41a = p(inner * 1.1, theta + w * 0.18)
    c41b = p(inner * 0.9, theta - w * 0.18)

    return (
        f"M{s(p1)}"
        f"C{s(c12a)} {s(c12b)} {s(p2)}"
        f"C{s(c23a)} {s(c23b)} {s(p3)}"
        f"C{s(c34a)} {s(c34b)} {s(p4)}"
        f"C{s(c41a)} {s(c41b)} {s(p1)}"
        "Z"
    )


def focal_point(scale: float = 1, offset: float = 0) -> str:
    cx = CENTER[0] * scale + offset
    cy = CENTER[1] * scale + offset
    return (
        f'  <circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(30 * scale)}" fill="#FFFFFF" fill-opacity="0.94"/>\n'
        f'  <circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(82 * scale)}" fill="#FFFFFF" fill-opacity="0.18"/>\n'
    )


def svg(title: str, body: str, size: int = CANVAS) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
        f'width="{size}" height="{size}">\n'
        f"  <title>Teamplay Talk icon {title}</title>\n"
        f"{body}"
        "</svg>\n"
    )


def write_layers() -> None:
    LAYERS.mkdir(parents=True, exist_ok=True)

    for stale in LAYERS.glob("*.svg"):
        stale.unlink()

    for blade in BLADES:
        body = f'  <path d="{blade_path(blade)}" fill="{blade.fill}"/>\n'
        (LAYERS / blade.layer_file).write_text(svg(f"layer {blade.title}", body), encoding="utf-8")

    (LAYERS / "06_focal_point.svg").write_text(
        svg("layer focal point", focal_point()),
        encoding="utf-8",
    )

    (OUT / "teamplay-icon-preview.svg").write_text(preview_svg(), encoding="utf-8")
    (OUT / "teamplay-favicon.svg").write_text(favicon_svg(), encoding="utf-8")


def preview_defs() -> str:
    gradients = []
    for blade in BLADES:
        gradients.append(
            f'''    <linearGradient id="blade{blade.index}" x1="220" y1="176" x2="806" y2="854" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#FFFFFF" stop-opacity=".5"/>
      <stop offset=".24" stop-color="{blade.fill}" stop-opacity=".96"/>
      <stop offset="1" stop-color="{blade.fill}" stop-opacity=".72"/>
    </linearGradient>'''
        )

    return f'''  <defs>
    <radialGradient id="bg" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="translate(512 512) rotate(75) scale(700)">
      <stop offset="0" stop-color="#1A1244"/>
      <stop offset=".58" stop-color="#0A071A"/>
      <stop offset="1" stop-color="#05040C"/>
    </radialGradient>
    <radialGradient id="focalGlow" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="translate(512 512) rotate(90) scale(180)">
      <stop offset="0" stop-color="#FFFFFF" stop-opacity=".96"/>
      <stop offset=".24" stop-color="#FFFFFF" stop-opacity=".46"/>
      <stop offset=".62" stop-color="#f7b801" stop-opacity=".18"/>
      <stop offset="1" stop-color="#f7b801" stop-opacity="0"/>
    </radialGradient>
    <filter id="bladeShadow" x="58" y="58" width="908" height="908" filterUnits="userSpaceOnUse" color-interpolation-filters="sRGB">
      <feDropShadow dx="0" dy="28" stdDeviation="24" flood-color="#000000" flood-opacity=".34"/>
    </filter>
    <filter id="focalBloom" x="350" y="350" width="324" height="324" filterUnits="userSpaceOnUse" color-interpolation-filters="sRGB">
      <feGaussianBlur stdDeviation="14"/>
    </filter>
{chr(10).join(gradients)}
  </defs>
'''


def preview_svg() -> str:
    blade_paths = []
    for blade in BLADES:
        blade_paths.append(
            f'    <path d="{blade_path(blade)}" fill="url(#blade{blade.index})" '
            f'stroke="#FFFFFF" stroke-opacity=".16" stroke-width="5"/>\n'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  <title>Teamplay Talk app icon preview</title>
{preview_defs()}  <rect width="1024" height="1024" fill="url(#bg)"/>
  <g filter="url(#bladeShadow)">
{''.join(blade_paths)}  </g>
  <circle cx="512" cy="512" r="104" fill="url(#focalGlow)" filter="url(#focalBloom)"/>
  <circle cx="512" cy="512" r="34" fill="#FFFFFF" fill-opacity=".9"/>
  <circle cx="512" cy="512" r="13" fill="#FFF7C6"/>
</svg>
'''


def favicon_svg() -> str:
    scale = 0.125
    body = '  <rect width="128" height="128" rx="28" fill="#0A071A"/>\n'
    for blade in BLADES:
        body += f'  <path d="{blade_path(blade, scale=scale)}" fill="{blade.fill}"/>\n'
    body += focal_point(scale=scale)
    return svg("favicon", body, size=128)


if __name__ == "__main__":
    write_layers()
