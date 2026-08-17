"""Draw.io MCP Client — same-origin REST surface served by cna-web.

This is the third leg of the triple-enforced icon-library pinning. The first
two layers (build-time filter on shape-index.json, route-handler allow-list)
live in apps/cna-web/lib/drawio-mcp. This client re-filters every response so
callers can never receive a shape outside ALLOWED_LIBS, no matter how the
server is configured at runtime.

Connection:
  - Default URL: http://localhost:3000/api/drawio-mcp (override via
    CNA_DRAWIO_MCP_URL).
  - HTTP+JSON contract — no MCP SDK required. The cna-web route exposes the
    same `search_shapes` / `create_diagram` tool shapes as the upstream
    draw.io MCP App Server.
  - Timeouts fail fast (5s); on any error the client returns an empty list
    or None so the diagram pipeline keeps moving with its built-in fallbacks.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

import httpx

logger = logging.getLogger("cna.mcp.drawio")

# Pinned per the Draw.io integration plan. Update here AND in
# apps/cna-web/lib/drawio-mcp/allow-list.ts AND in
# apps/cna-web/scripts/filter-shape-index.mjs when switching libraries.
ALLOWED_LIBS: frozenset[str] = frozenset({"azure2", "aws4"})

_DEFAULT_URL = os.getenv("CNA_DRAWIO_MCP_URL", "http://localhost:3000/api/drawio-mcp").rstrip("/")
_DEFAULT_TIMEOUT = float(os.getenv("CNA_DRAWIO_MCP_TIMEOUT", "5"))

_STYLE_PREFIX_RE = re.compile(r"shape=mxgraph\.([a-z0-9]+)\.", re.IGNORECASE)


def _lib_of(style: str) -> str | None:
    m = _STYLE_PREFIX_RE.search(style or "")
    return m.group(1).lower() if m else None


def _is_allowed_style(style: str) -> bool:
    lib = _lib_of(style)
    return lib is not None and lib in ALLOWED_LIBS


@dataclass(frozen=True)
class ShapeHit:
    name: str
    library: str
    tags: tuple[str, ...]
    style: str
    score: int


@dataclass(frozen=True)
class CreateDiagramResult:
    name: str
    xml: str
    embed_url: str


class DrawioMCPClient:
    """Thin REST client for the in-app draw.io MCP surface."""

    def __init__(
        self,
        base_url: str = _DEFAULT_URL,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def search_shapes(self, query: str, limit: int = 20) -> list[ShapeHit]:
        """Return ranked, allow-list-filtered shape hits. Empty list on any error."""
        if not query or not query.strip():
            return []
        payload: dict[str, object] = {"query": query.strip(), "limit": int(limit)}
        body = self._post("search_shapes", payload)
        if body is None:
            return []
        raw_hits = body.get("hits") or []
        hits: list[ShapeHit] = []
        for raw in raw_hits:
            style = str(raw.get("style", ""))
            if not _is_allowed_style(style):
                logger.warning("drawio MCP returned disallowed style; dropped (style=%s)", style)
                continue
            hits.append(
                ShapeHit(
                    name=str(raw.get("name", "")),
                    library=str(raw.get("library", "")),
                    tags=tuple(raw.get("tags", []) or []),
                    style=style,
                    score=int(raw.get("score", 0)),
                )
            )
        return hits

    def create_diagram(self, xml: str, name: str | None = None) -> CreateDiagramResult | None:
        """Echo XML back with a viewer embed URL, or None on failure."""
        if not xml or "<mxfile" not in xml:
            logger.warning("drawio MCP create_diagram: payload missing <mxfile> root")
            return None
        payload: dict[str, object] = {"xml": xml}
        if name:
            payload["name"] = name
        body = self._post("create_diagram", payload)
        if body is None:
            return None
        return CreateDiagramResult(
            name=str(body.get("name", name or "diagram")),
            xml=str(body.get("xml", xml)),
            embed_url=str(body.get("embedUrl", "")),
        )

    def health(self) -> bool:
        try:
            r = httpx.get(f"{self._base_url}/health", timeout=self._timeout)
            r.raise_for_status()
            return bool(r.json().get("status") == "ok")
        except Exception as e:  # noqa: BLE001 — graceful degradation
            logger.info("drawio MCP health check failed: %s", e)
            return False

    def _post(self, tool: str, payload: dict[str, object]) -> dict | None:
        url = f"{self._base_url}/{tool}"
        try:
            r = httpx.post(url, json=payload, timeout=self._timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001 — graceful degradation
            logger.info("drawio MCP %s failed: %s", tool, e)
            return None
