#!/usr/bin/env python3
"""CI guardrail — every draw.io style in the shape catalog must use a pinned
icon library (azure2 or aws4). Fails non-zero on any violation so a careless
edit cannot drift the deliverables into another icon set.

Each cloud has one valid reference form, and they differ (see
cna/diagram_engine/shape_catalog.py for the full account):

    AWS   shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.<name>
    Azure image=img/lib/azure2/<category>/<File_Name>.svg

`shape=mxgraph.azure2.*` is rejected on purpose: that stencil namespace does
not exist, so draw.io silently renders a plain blue rectangle instead of an
icon. The catalog shipped that form until 2026-08-28.

Run from repo root:
    python scripts/validate_shape_catalog.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ALLOWED_LIBS = {"azure2", "aws4"}
STENCIL_RE = re.compile(r"shape=mxgraph\.([a-z0-9]+)\.", re.IGNORECASE)
IMAGE_RE = re.compile(r"image=img/lib/([a-z0-9]+)/", re.IGNORECASE)
# Stencil namespaces draw.io actually ships. azure2 is deliberately not one.
STENCIL_LIBS = {"aws4"}

ROOT = Path(__file__).resolve().parent.parent
TARGETS = [
    ROOT / "cna" / "diagram_engine" / "data" / "azure_shapes.json",
    ROOT / "cna" / "diagram_engine" / "data" / "aws_shapes.json",
    ROOT / "apps" / "cna-web" / "lib" / "drawio-mcp" / "shape-index.json",
]


def lib_of(style: str) -> str | None:
    m = IMAGE_RE.search(style or "")
    if m:
        return m.group(1).lower()
    m = STENCIL_RE.search(style or "")
    if m and m.group(1).lower() in STENCIL_LIBS:
        return m.group(1).lower()
    return None


def check(path: Path) -> list[str]:
    if not path.exists():
        return [f"{path}: missing"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"{path}: invalid JSON: {e}"]
    violations: list[str] = []
    iterator: list[tuple[str, str]]
    if isinstance(data, dict):
        iterator = [(k, str(v)) for k, v in data.items()]
    elif isinstance(data, list):
        iterator = [(str(e.get("name", i)), str(e.get("style", ""))) for i, e in enumerate(data)]
    else:
        return [f"{path}: unexpected top-level type {type(data).__name__}"]
    for key, style in iterator:
        lib = lib_of(style)
        if lib is None:
            hint = ""
            if "mxgraph.azure2" in style:
                hint = (
                    " — mxgraph.azure2 is not a real stencil set and renders as a"
                    " blank blue box; use image=img/lib/azure2/<category>/<File>.svg"
                )
            violations.append(f"{path}: '{key}' references no pinned icon library{hint}")
        elif lib not in ALLOWED_LIBS:
            violations.append(
                f"{path}: '{key}' uses library '{lib}' outside ALLOWED_LIBS {sorted(ALLOWED_LIBS)}"
            )
    return violations


def main() -> int:
    all_violations: list[str] = []
    for target in TARGETS:
        all_violations.extend(check(target))
    if all_violations:
        print("Shape catalog validation FAILED:", file=sys.stderr)
        for v in all_violations:
            print(f"  - {v}", file=sys.stderr)
        return 1
    print(f"Shape catalog OK ({len(TARGETS)} files, libs={sorted(ALLOWED_LIBS)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
