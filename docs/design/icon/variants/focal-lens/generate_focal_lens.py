#!/usr/bin/env python3
"""Generate a Teamplay Talk icon variant based on focal length.

Concept: Focal Lens.

Multiple team signals enter as separate light paths, pass through one liquid
lens, and converge into a single focal decision. The geometry is generated from
one optical system: input offsets, lens compression, and focal point.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


CANVAS = 1024
OUT = Path(__file__).resolve().parent
LAYERS = OUT / "layers"

CENTER_Y = 512.0
INPUT_X = 148.0
LENS_X = 468.0
FOCAL_X = 792.0
FOCAL_Y = 512.0
LENS_HALF_HEIGHT = 214.0
LENS_WIDTH = 118.0

PALETTE = ("#3d348b", "#7678ed", "#f7b801", "#f18701", "#f35b04")


@dataclass(frozen=True)
class Ray:
    name: str
    layer_file: str
    input_offset: float
    lens_offset: float
    color: str
    width: float


RAYS = (
    Ray("upper", "01_ray_upper.svg", -174, -72, "#3d348b", 42),
    Ray("middle_upper", "02_ray_middle_upper.svg", -62, -24, "#7678ed", 46),
    Ray("middle_lower", "03_ray_middle_lower.svg", 62, 24, "#f7b801", 48),
    Ray("lower", "04_ray_lower.svg", 174, 72, "#f35b04", 42),
)


def fmt(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def svg(title: str, body: str, size: int = CANVAS) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
        f'width="{size}" height="{size}">\n'
        f"  <title>Teamplay Talk focal lens {title}</title>\n"
        f"{body}"
        "</svg>\n"
    )


def ray_path(ray: Ray, scale: float = 1, offset: float = 0) -> str:
    """Cubic path from input, through lens, to the focal point."""

    x0 = INPUT_X
    y0 = CENTER_Y + ray.input_offset
    x1 = LENS_X - LENS_WIDTH * 0.44
    y1 = CENTER_Y + ray.lens_offset
    x2 = LENS_X + LENS_WIDTH * 0.44
    y2 = CENTER_Y + ray.lens_offset * 0.44
    x3 = FOCAL_X
    y3 = FOCAL_Y

    def p(x: float, y: float) -> str:
        return f"{fmt(x * scale + offset)} {fmt(y * scale + offset)}"

    return (
        f"M{p(x0, y0)}"
        f"C{p(x0 + 128, y0)} {p(x1 - 88, y1)} {p(x1, y1)}"
        f"C{p(x2 + 82, y2)} {p(x3 - 142, y3)} {p(x3, y3)}"
    )


def lens_path(scale: float = 1, offset: float = 0) -> str:
    """Biconvex lens cross-section."""

    top = (LENS_X, CENTER_Y - LENS_HALF_HEIGHT)
    bottom = (LENS_X, CENTER_Y + LENS_HALF_HEIGHT)
    left_mid = (LENS_X - LENS_WIDTH, CENTER_Y)
    right_mid = (LENS_X + LENS_WIDTH, CENTER_Y)

    def p(point: tuple[float, float]) -> str:
        return f"{fmt(point[0] * scale + offset)} {fmt(point[1] * scale + offset)}"

    return (
        f"M{p(top)}"
        f"C{p((LENS_X - LENS_WIDTH * 0.96, CENTER_Y - LENS_HALF_HEIGHT * 0.62))} "
        f"{p((LENS_X - LENS_WIDTH * 0.96, CENTER_Y + LENS_HALF_HEIGHT * 0.62))} "
        f"{p(bottom)}"
        f"C{p((LENS_X + LENS_WIDTH * 0.96, CENTER_Y + LENS_HALF_HEIGHT * 0.62))} "
        f"{p((LENS_X + LENS_WIDTH * 0.96, CENTER_Y - LENS_HALF_HEIGHT * 0.62))} "
        f"{p(top)}Z"
    )


def focal_point(scale: float = 1, offset: float = 0) -> str:
    cx = FOCAL_X * scale + offset
    cy = FOCAL_Y * scale + offset
    return (
        f'  <circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(34 * scale)}" fill="#FFFFFF" fill-opacity="0.94"/>\n'
        f'  <circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(78 * scale)}" fill="#f7b801" fill-opacity="0.22"/>\n'
    )


def write_layers() -> None:
    LAYERS.mkdir(parents=True, exist_ok=True)
    for stale in LAYERS.glob("*.svg"):
        stale.unlink()

    for ray in RAYS:
        body = (
            f'  <path d="{ray_path(ray)}" fill="none" stroke="{ray.color}" '
            f'stroke-width="{fmt(ray.width)}" stroke-linecap="round"/>\n'
        )
        (LAYERS / ray.layer_file).write_text(svg(f"layer {ray.name} ray", body), encoding="utf-8")

    (LAYERS / "05_lens_body.svg").write_text(
        svg("layer liquid lens", f'  <path d="{lens_path()}" fill="#FFFFFF" fill-opacity="0.48"/>\n'),
        encoding="utf-8",
    )
    (LAYERS / "06_focal_point.svg").write_text(svg("layer focal point", focal_point()), encoding="utf-8")
    (OUT / "teamplay-icon-preview.svg").write_text(preview_svg(), encoding="utf-8")
    (OUT / "teamplay-favicon.svg").write_text(favicon_svg(), encoding="utf-8")


def preview_defs() -> str:
    gradients = []
    for ray in RAYS:
        gradients.append(
            f'''    <linearGradient id="{ray.name}" x1="{INPUT_X}" y1="{CENTER_Y + ray.input_offset}" x2="{FOCAL_X}" y2="{FOCAL_Y}" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{ray.color}" stop-opacity=".42"/>
      <stop offset=".48" stop-color="{ray.color}" stop-opacity=".9"/>
      <stop offset="1" stop-color="#FFFFFF" stop-opacity=".88"/>
    </linearGradient>'''
        )

    return f'''  <defs>
    <radialGradient id="bg" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="translate(520 512) rotate(76) scale(710)">
      <stop offset="0" stop-color="#1B1243"/>
      <stop offset=".6" stop-color="#0A071A"/>
      <stop offset="1" stop-color="#05040C"/>
    </radialGradient>
    <linearGradient id="lensGlass" x1="{LENS_X - LENS_WIDTH}" y1="{CENTER_Y - LENS_HALF_HEIGHT}" x2="{LENS_X + LENS_WIDTH}" y2="{CENTER_Y + LENS_HALF_HEIGHT}" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#FFFFFF" stop-opacity=".36"/>
      <stop offset=".5" stop-color="#FFFFFF" stop-opacity=".72"/>
      <stop offset="1" stop-color="#7678ed" stop-opacity=".22"/>
    </linearGradient>
    <radialGradient id="focalGlow" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="translate({FOCAL_X} {FOCAL_Y}) rotate(90) scale(132)">
      <stop offset="0" stop-color="#FFFFFF" stop-opacity=".98"/>
      <stop offset=".28" stop-color="#FFF7C6" stop-opacity=".5"/>
      <stop offset="1" stop-color="#f7b801" stop-opacity="0"/>
    </radialGradient>
    <filter id="softShadow" x="38" y="176" width="848" height="672" filterUnits="userSpaceOnUse" color-interpolation-filters="sRGB">
      <feDropShadow dx="0" dy="26" stdDeviation="24" flood-color="#000000" flood-opacity=".28"/>
    </filter>
    <filter id="bloom" x="650" y="370" width="284" height="284" filterUnits="userSpaceOnUse" color-interpolation-filters="sRGB">
      <feGaussianBlur stdDeviation="14"/>
    </filter>
{chr(10).join(gradients)}
  </defs>
'''


def preview_svg() -> str:
    ray_shapes = []
    for ray in RAYS:
        ray_shapes.append(
            f'    <path d="{ray_path(ray)}" fill="none" stroke="url(#{ray.name})" '
            f'stroke-width="{fmt(ray.width)}" stroke-linecap="round"/>\n'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  <title>Teamplay Talk focal lens icon preview</title>
{preview_defs()}  <rect width="1024" height="1024" fill="url(#bg)"/>
  <g filter="url(#softShadow)">
{''.join(ray_shapes)}    <path d="{lens_path()}" fill="url(#lensGlass)" stroke="#FFFFFF" stroke-opacity=".34" stroke-width="6"/>
  </g>
  <circle cx="{FOCAL_X}" cy="{FOCAL_Y}" r="96" fill="url(#focalGlow)" filter="url(#bloom)"/>
  <circle cx="{FOCAL_X}" cy="{FOCAL_Y}" r="34" fill="#FFFFFF" fill-opacity=".92"/>
  <circle cx="{FOCAL_X}" cy="{FOCAL_Y}" r="12" fill="#FFF4B8"/>
</svg>
'''


def favicon_svg() -> str:
    scale = 0.125
    body = '  <rect width="128" height="128" rx="28" fill="#0A071A"/>\n'
    for ray in RAYS:
        body += (
            f'  <path d="{ray_path(ray, scale=scale)}" fill="none" stroke="{ray.color}" '
            f'stroke-width="{fmt(ray.width * scale)}" stroke-linecap="round"/>\n'
        )
    body += f'  <path d="{lens_path(scale=scale)}" fill="#FFFFFF" fill-opacity=".48"/>\n'
    body += focal_point(scale=scale)
    return svg("favicon", body, size=128)


if __name__ == "__main__":
    write_layers()
