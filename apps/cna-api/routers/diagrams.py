"""Diagrams router — generate draw.io topology diagrams from discovered data.

Stateless, same shape as routers/reports.py: POST loads the engagement's
persisted discovery topologies from Postgres, runs them through the diagram
engine, and returns one multi-page .drawio document that cna-web stores as a
NETWORK_DIAGRAM document and loads into the embedded editor.

This is the seam that was missing. cna.ai_engine.diagram_authoring
(`author_engagement_bundle`) and the generators under cna.diagram_engine have
existed since Phase B, but nothing called them: the docstring says "the worker
hooks it after analysis", and the worker is a placeholder. As a result the
Diagram page only ever offered a blank canvas.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Ensure the repo root is on the path so `cna` package is importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from cna.ai_engine.diagram_authoring import author_engagement_bundle
from cna.core.topology_schema import AWSTopology, AzureTopology
from cna.diagram_engine.c4_layering import C4Layer
from cna.diagram_engine.drawio_generator import merge_diagrams

logger = logging.getLogger("cna-api.diagrams")

import db  # noqa: E402, I001 — apps/cna-api is on sys.path (see main.py)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

router = APIRouter(prefix="/diagrams", tags=["diagrams"])


def _get_db():
    # Pooled connection with ``with conn:`` transaction semantics (T-704).
    return db.connection(DATABASE_URL)


class GenerateDiagramRequest(BaseModel):
    engagement_name: str = ""
    client_org: str = ""


def _load_topology_rows(engagement_id: str) -> list[str]:
    """Latest completed topology JSON per credential.

    One CloudCredential is one subscription/account sync group, so taking only
    the single most recent job would silently drop every other cloud the
    engagement scanned. This mirrors getMergedTopologyJson() in cna-web.
    """
    with _get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT DISTINCT ON (COALESCE("credentialId", '')) "topologyJson"
               FROM "DiscoveryJob"
               WHERE "engagementId" = %s AND "topologyJson" IS NOT NULL
               ORDER BY COALESCE("credentialId", ''), "updatedAt" DESC""",
            (engagement_id,),
        )
        rows = cur.fetchall()
    return [r["topologyJson"] for r in rows if r.get("topologyJson")]


def _parse_topologies(raw_rows: list[str]) -> tuple[list, list]:
    """Split raw topology JSON into (azure_subscriptions, aws_regions).

    A row that will not parse is skipped with a warning: one malformed
    checkpoint should cost its own scope, not the whole diagram.
    """
    azure_subs: list = []
    aws_regions: list = []
    for raw in raw_rows:
        parsed = False
        try:
            azure_subs.extend(AzureTopology.model_validate_json(raw).subscriptions)
            parsed = True
        except Exception as exc:  # noqa: BLE001 — not an Azure checkpoint, try AWS
            logger.debug("row is not an Azure topology, trying AWS: %s", exc)
        if not parsed:
            try:
                aws_regions.extend(AWSTopology.model_validate_json(raw).regions)
            except Exception as exc:  # noqa: BLE001
                logger.warning("topology row parsed as neither Azure nor AWS: %s", exc)
    return azure_subs, aws_regions


@router.post("/{engagement_id}/generate")
def generate_diagram(engagement_id: str, body: GenerateDiagramRequest) -> dict:
    """Build a multi-page .drawio document from the engagement's discovery data."""
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="DATABASE_URL not configured")

    raw_rows = _load_topology_rows(engagement_id)
    if not raw_rows:
        raise HTTPException(
            status_code=409,
            detail="No discovery topology for this engagement — run discovery first.",
        )

    azure_subs, aws_regions = _parse_topologies(raw_rows)
    if not azure_subs and not aws_regions:
        raise HTTPException(
            status_code=422,
            detail="Discovery topology could not be parsed; nothing to diagram.",
        )

    label = body.client_org or body.engagement_name or engagement_id
    bundle = author_engagement_bundle(label, aws_regions=aws_regions, azure_subs=azure_subs)

    # One tab per diagram: "Context", then one container diagram per scope.
    pages: list[tuple[str, str]] = [
        ("Context" if diagram.layer is C4Layer.CONTEXT else diagram.name, diagram.xml)
        for diagram in bundle
    ]

    xml = merge_diagrams(pages)
    return {
        "engagement_id": engagement_id,
        "format": "drawio",
        "page_count": len(pages),
        "azure_subscriptions": len(azure_subs),
        "aws_regions": len(aws_regions),
        "content": xml,
    }
