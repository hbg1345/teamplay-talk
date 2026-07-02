#!/usr/bin/env python3
"""Generate a Teamplay Talk icon variant based on overlapping opinions.

Concept: Opinion Waveforms.

Each colored wave represents a teammate's opinion or signal. The waves begin
with different amplitudes, overlap through the middle, and settle into one
shared decision pulse. Geometry is generated from a damped sine function so the
mark stays coherent instead of hand-drawn.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, pi, sin
from pathlib import Path


CANVAS = 1024
OUT = Path(__file__).resolve().parent
LAYERS = OUT / "layers"

START_X = 132.0
END_X = 864.0
CENTER_Y = 512.0
FOCUS_X = 512.0
BASE_AMPLITUDE = 92.0
SAMPLES = 88

PALETTE = ("#3d348b", "#7678ed", "#f7b801", "#f18701", "#f35b04")


@dataclass(frozen=True)
class Wave:
    name: str
    layer_file: str
    color: str
    offset: float
    phase: float
    amplitude: float
    stroke: float


WAVES = (
    Wave("strategy", "01_wave_strategy.svg", "#3d348b", -82, 0.15, 1.08, 34),
    Wave("design", "02_wave_design.svg", "#7678ed", -36, 0.9, 0.9, 36),
    Wave("decision", "03_wave_decision.svg", "#f7b801", 18, 1.55, 1.0, 40),
    Wave("timing", "04_wave_timing.svg", "#f18701", 58, 2.3, 0.82, 34),
    Wave("handoff", "05_wave_handoff.svg", "#f35b04", 96, 3.0, 0.74, 32),
)


def fmt(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def damped_wave_y(wave: Wave, t: float) -> float:
    """Different signals converge at center, then continue as one output."""

    x = START_X + (END_X - START_X) * t
    focus_t = (FOCUS_X - START_X) / (END_X - START_X)

    if t <= focus_t:
        local = t / focus_t
        convergence = wave.offset * (1 - local) ** 1.7
        damping = 1 - 0.72 * local
        wobble = sin(2 * pi * 1.42 * local + wave.phase)
        harmonic = 0.28 * sin(2 * pi * 0.72 * local + wave.phase * 0.6)
        return CENTER_Y + convergence + BASE_AMPLITUDE * wave.amplitude * damping * (wobble + harmonic)

    local = (t - focus_t) / (1 - focus_t)
    output = 18 * sin(2 * pi * 1.12 * local + 0.45) * (1 - 0.32 * local)
    settle = -8 * local
    return CENTER_Y + output + settle


def wave_points(wave: Wave, scale: float = 1, offset: float = 0) -> list[tuple[float, float]]:
    points = []
    for i in range(SAMPLES + 1):
        t = i / SAMPLES
        x = START_X + (END_X - START_X) * t
        y = damped_wave_y(wave, t)
        points.append((x * scale + offset, y * scale + offset))
    return points


def catmull_rom_path(points: list[tuple[float, float]], tension: float = 0.72) -> str:
    def p(index: int) -> tuple[float, float]:
        return points[max(0, min(len(points) - 1, index))]

    path = [f"M{fmt(points[0][0])} {fmt(points[0][1])}"]
    for i in range(len(points) - 1):
        p0 = p(i - 1)
        p1 = p(i)
        p2 = p(i + 1)
        p3 = p(i + 2)
        c1 = (
            p1[0] + (p2[0] - p0[0]) * tension / 6,
            p1[1] + (p2[1] - p0[1]) * tension / 6,
        )
        c2 = (
            p2[0] - (p3[0] - p1[0]) * tension / 6,
            p2[1] - (p3[1] - p1[1]) * tension / 6,
        )
        path.append(f"C{fmt(c1[0])} {fmt(c1[1])} {fmt(c2[0])} {fmt(c2[1])} {fmt(p2[0])} {fmt(p2[1])}")
    return "".join(path)


def svg(title: str, body: str, size: int = CANVAS) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
        f'width="{size}" height="{size}">\n'
        f"  <title>Teamplay Talk waveform {title}</title>\n"
        f"{body}"
        "</svg>\n"
    )


def wave_layer(wave: Wave, scale: float = 1, offset: float = 0, gradient: str | None = None) -> str:
    stroke = gradient or wave.color
    return (
        f'  <path d="{catmull_rom_path(wave_points(wave, scale, offset))}" fill="none" '
        f'stroke="{stroke}" stroke-width="{fmt(wave.stroke * scale)}" '
        f'stroke-linecap="round" stroke-linejoin="round"/>\n'
    )


def decision_pulse(scale: float = 1, offset: float = 0) -> str:
    cx = FOCUS_X * scale + offset
    cy = CENTER_Y * scale + offset
    return (
        f'  <circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(34 * scale)}" fill="#FFFFFF" fill-opacity="0.94"/>\n'
        f'  <circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(82 * scale)}" fill="#f7b801" fill-opacity="0.2"/>\n'
    )


def write_layers() -> None:
    LAYERS.mkdir(parents=True, exist_ok=True)
    for stale in LAYERS.glob("*.svg"):
        stale.unlink()

    for wave in WAVES:
        (LAYERS / wave.layer_file).write_text(svg(f"layer {wave.name}", wave_layer(wave)), encoding="utf-8")

    (LAYERS / "06_decision_pulse.svg").write_text(
        svg("layer decision pulse", decision_pulse()),
        encoding="utf-8",
    )

    (OUT / "teamplay-icon-preview.svg").write_text(preview_svg(), encoding="utf-8")
    (OUT / "teamplay-favicon.svg").write_text(favicon_svg(), encoding="utf-8")


def preview_defs() -> str:
    gradients = []
    for wave in WAVES:
        gradients.append(
            f'''    <linearGradient id="{wave.name}" x1="{START_X}" y1="{CENTER_Y + wave.offset}" x2="{END_X}" y2="{CENTER_Y}" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{wave.color}" stop-opacity=".42"/>
      <stop offset=".5" stop-color="{wave.color}" stop-opacity=".96"/>
      <stop offset=".64" stop-color="#FFFFFF" stop-opacity=".78"/>
      <stop offset="1" stop-color="{wave.color}" stop-opacity=".46"/>
    </linearGradient>'''
        )

    return f'''  <defs>
    <radialGradient id="bg" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="translate(516 512) rotate(76) scale(706)">
      <stop offset="0" stop-color="#1B1243"/>
      <stop offset=".58" stop-color="#0A071A"/>
      <stop offset="1" stop-color="#05040C"/>
    </radialGradient>
    <radialGradient id="pulseGlow" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="translate({FOCUS_X} {CENTER_Y}) rotate(90) scale(154)">
      <stop offset="0" stop-color="#FFFFFF" stop-opacity=".96"/>
      <stop offset=".32" stop-color="#FFF7C6" stop-opacity=".45"/>
      <stop offset="1" stop-color="#f7b801" stop-opacity="0"/>
    </radialGradient>
    <filter id="waveShadow" x="46" y="214" width="910" height="604" filterUnits="userSpaceOnUse" color-interpolation-filters="sRGB">
      <feDropShadow dx="0" dy="24" stdDeviation="22" flood-color="#000000" flood-opacity=".3"/>
    </filter>
    <filter id="pulseBloom" x="362" y="362" width="300" height="300" filterUnits="userSpaceOnUse" color-interpolation-filters="sRGB">
      <feGaussianBlur stdDeviation="14"/>
    </filter>
{chr(10).join(gradients)}
  </defs>
'''


def preview_svg() -> str:
    wave_shapes = "".join(wave_layer(wave, gradient=f"url(#{wave.name})") for wave in WAVES)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  <title>Teamplay Talk waveform icon preview</title>
{preview_defs()}  <rect width="1024" height="1024" fill="url(#bg)"/>
  <g filter="url(#waveShadow)">
{wave_shapes}  </g>
  <circle cx="{FOCUS_X}" cy="{CENTER_Y}" r="104" fill="url(#pulseGlow)" filter="url(#pulseBloom)"/>
  <circle cx="{FOCUS_X}" cy="{CENTER_Y}" r="34" fill="#FFFFFF" fill-opacity=".9"/>
  <circle cx="{FOCUS_X}" cy="{CENTER_Y}" r="12" fill="#FFF4B8"/>
</svg>
'''


def favicon_svg() -> str:
    scale = 0.125
    body = '  <rect width="128" height="128" rx="28" fill="#0A071A"/>\n'
    for wave in WAVES:
        body += wave_layer(wave, scale=scale)
    body += decision_pulse(scale=scale)
    return svg("favicon", body, size=128)


if __name__ == "__main__":
    write_layers()
