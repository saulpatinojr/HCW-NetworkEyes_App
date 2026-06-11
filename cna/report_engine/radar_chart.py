"""Maturity radar chart — inline SVG generator (Phase D).

Pure string-building helper: no matplotlib, no raster output. The returned
SVG embeds directly into Jinja2 templates and renders in WeasyPrint.

CBTS palette: navy #012638 (text/axes), warm gray #F2F1ED-derived grid,
bright teal #00E9BB (score polygon), dark teal #004E3D (labels).
"""

from __future__ import annotations

import math
from xml.sax.saxutils import escape

_MIN_RADAR_DIMENSIONS = 3

_NAVY = "#012638"
_DARK_TEAL = "#004E3D"
_BRIGHT_TEAL = "#00E9BB"
_GRID = "#D8D6CE"  # warm-gray grid lines (darkened #F2F1ED for visibility)

_GRID_RINGS = (25, 50, 75, 100)


def _point(cx: float, cy: float, angle: float, radius: float) -> tuple[float, float]:
    return (cx + radius * math.cos(angle), cy + radius * math.sin(angle))


def radar_chart_svg(
    dimensions: list[tuple[str, float]],
    size: int = 460,
    title: str | None = None,
) -> str:
    """Build an inline SVG maturity radar.

    Args:
        dimensions: (label, score) pairs; scores are clamped to 0–100.
                    At least 3 dimensions are required for a polygon.
        size: SVG width/height in px (viewBox units).
        title: Optional accessible <title> element text.

    Returns:
        Self-contained ``<svg>…</svg>`` string (no external CSS required),
        safe to embed in WeasyPrint-rendered HTML.
    """
    if len(dimensions) < _MIN_RADAR_DIMENSIONS:
        raise ValueError("radar_chart_svg requires at least 3 dimensions")

    cx = cy = size / 2.0
    radius = size / 2.0 - 70  # leave room for labels
    n = len(dimensions)
    angles = [(-math.pi / 2) + (2 * math.pi * i / n) for i in range(n)]

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}" role="img">'
    ]
    if title:
        parts.append(f"<title>{escape(title)}</title>")

    # Concentric grid rings
    for ring in _GRID_RINGS:
        ring_pts = " ".join(
            f"{x:.1f},{y:.1f}"
            for x, y in (_point(cx, cy, a, radius * ring / 100.0) for a in angles)
        )
        parts.append(
            f'<polygon points="{ring_pts}" fill="none" stroke="{_GRID}" stroke-width="1"/>'
        )

    # Axes + labels
    for (label, _), angle in zip(dimensions, angles, strict=True):
        ax, ay = _point(cx, cy, angle, radius)
        parts.append(
            f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{ax:.1f}" y2="{ay:.1f}" '
            f'stroke="{_GRID}" stroke-width="1"/>'
        )
        lx, ly = _point(cx, cy, angle, radius + 18)
        anchor = "middle"
        if lx > cx + 8:
            anchor = "start"
        elif lx < cx - 8:
            anchor = "end"
        parts.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
            f'dominant-baseline="middle" font-size="13" font-family="Aeonik, sans-serif" '
            f'fill="{_DARK_TEAL}">{escape(str(label))}</text>'
        )

    # Score polygon
    score_coords = [
        _point(cx, cy, angle, radius * max(0.0, min(100.0, float(score))) / 100.0)
        for (_, score), angle in zip(dimensions, angles, strict=True)
    ]
    score_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in score_coords)
    parts.append(
        f'<polygon points="{score_pts}" fill="{_BRIGHT_TEAL}" fill-opacity="0.35" '
        f'stroke="{_BRIGHT_TEAL}" stroke-width="2.5"/>'
    )

    # Vertex dots + score values
    for (_, score), (x, y) in zip(dimensions, score_coords, strict=True):
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{_DARK_TEAL}"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{y - 9:.1f}" text-anchor="middle" font-size="11" '
            f'font-weight="700" font-family="Aeonik, sans-serif" fill="{_NAVY}">'
            f"{max(0.0, min(100.0, float(score))):.0f}</text>"
        )

    parts.append("</svg>")
    return "".join(parts)
