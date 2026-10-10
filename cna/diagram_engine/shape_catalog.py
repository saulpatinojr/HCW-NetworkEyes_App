"""Shape catalog — single source of truth for draw.io style strings.

Loads curated `azure_shapes.json` and `aws_shapes.json` at import time and
enforces the pinned-library allow-list. The legacy STYLE_* constants in
`drawio_generator` are now thin wrappers around `shape_style()` so a future
catalog refresh (e.g. via the in-app MCP `search_shapes` tool) requires no
code change.

Triple-enforced pinning (matches apps/cna-web/lib/drawio-mcp/allow-list.ts):
  1. Build-time filter on apps/cna-web/lib/drawio-mcp/shape-index.json
  2. Route handler re-filter on each search_shapes response
  3. THIS catalog re-validates every loaded style against ALLOWED_LIBS

If a style violates the allow-list it is dropped at load time with a warning;
callers fall back to the provided default.

Two icon mechanisms, one per cloud — this is not a style preference, it is what
draw.io actually renders (verified 2026-08-28 by exporting each entry with the
headless draw.io CLI and looking at the PNG):

  AWS   `shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.<name>`
        The aws4 stencil set is real. An unknown <name> renders as a plain
        coloured square, so every name in aws_shapes.json was probe-rendered.

  Azure `image=img/lib/azure2/<category>/<File_Name>.svg`
        There is NO mxgraph.azure2 stencil namespace. Styles of the form
        `shape=mxgraph.azure2.*` silently fall back to a plain blue rectangle —
        which is what this catalog shipped until 2026-08-28. Azure icons must
        use the SVG image paths from the official draw.io Azure2 palette.

`is_allowed_style` therefore rejects `shape=mxgraph.azure2.*` outright, so the
blue-box regression cannot come back unnoticed.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger("cna.diagram_engine.shape_catalog")

ALLOWED_LIBS: frozenset[str] = frozenset({"azure2", "aws4"})

_STENCIL_RE = re.compile(r"shape=mxgraph\.([a-z0-9]+)\.", re.IGNORECASE)
_IMAGE_RE = re.compile(r"image=img/lib/([a-z0-9]+)/", re.IGNORECASE)

# Stencil namespaces that draw.io actually ships. `azure2` is deliberately
# absent: it does not exist as a stencil set (see module docstring).
_STENCIL_LIBS: frozenset[str] = frozenset({"aws4"})

_DATA_DIR = Path(__file__).parent / "data"


def _lib_of(style: str) -> str | None:
    """Return the icon library a style draws from, or None if it draws from none.

    A stencil reference only counts when draw.io ships that stencil set; an
    image reference counts by its `img/lib/<lib>/` path.
    """
    m = _IMAGE_RE.search(style or "")
    if m:
        return m.group(1).lower()
    m = _STENCIL_RE.search(style or "")
    if m and m.group(1).lower() in _STENCIL_LIBS:
        return m.group(1).lower()
    return None


def is_allowed_style(style: str) -> bool:
    lib = _lib_of(style)
    return lib is not None and lib in ALLOWED_LIBS


def _load(filename: str) -> dict[str, str]:
    path = _DATA_DIR / filename
    if not path.exists():
        logger.warning("shape catalog missing: %s", path)
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.error("shape catalog %s unreadable: %s", path, e)
        return {}
    if not isinstance(raw, dict):
        logger.error("shape catalog %s must be a JSON object", path)
        return {}
    clean: dict[str, str] = {}
    for key, style in raw.items():
        if not isinstance(style, str) or not is_allowed_style(style):
            logger.warning(
                "shape catalog %s: dropping '%s' — style outside ALLOWED_LIBS %s",
                path.name,
                key,
                sorted(ALLOWED_LIBS),
            )
            continue
        clean[key] = style
    return clean


_AZURE: dict[str, str] = _load("azure_shapes.json")
_AWS: dict[str, str] = _load("aws_shapes.json")


def shape_style(library: str, key: str, default: str = "") -> str:
    """Return a style string for (library, key) or `default` if not catalogued.

    `library` must be one of ALLOWED_LIBS; anything else returns `default`.
    """
    lib = library.lower()
    if lib not in ALLOWED_LIBS:
        return default
    table = _AZURE if lib == "azure2" else _AWS
    return table.get(key, default)


def catalog_snapshot() -> dict[str, dict[str, str]]:
    """Return a deep copy for tests / CI guardrails."""
    return {"azure2": dict(_AZURE), "aws4": dict(_AWS)}
