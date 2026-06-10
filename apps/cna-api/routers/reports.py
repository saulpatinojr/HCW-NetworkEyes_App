"""Reports router — encyclopedia deliverable rendering (Phase D).

Stateless: POST loads the engagement's persisted Finding rows and latest
discovery topology from Postgres, builds the stat-master bundle, and renders
the six-chapter encyclopedia (cna.report_engine.encyclopedia_report) to an
HTML string returned to cna-web, which stores it as a Deliverable (same
content/blob path the COMPREHENSIVE_ASSESSMENT HTML deliverable uses).
Diagram SVG embedding degrades gracefully when the draw.io CLI is absent.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Ensure the repo root is on the path so `cna` package is importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from cna.core.stat_masters import build_stat_masters
from cna.report_engine.encyclopedia_report import (
    EDITION_CONDENSED,
    EDITION_EXPANDED,
    EncyclopediaReportRenderer,
)

logger = logging.getLogger("cna-api.reports")

DATABASE_URL = os.environ.get("DATABASE_URL", "")

router = APIRouter(prefix="/reports", tags=["reports"])


def _get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


class EncyclopediaRequest(BaseModel):
    edition: str = EDITION_EXPANDED  # "condensed" | "expanded"
    client_org: str = ""
    engagement_name: str = ""
    generated_at: str = ""


def _load_findings(engagement_id: str) -> list[dict]:
    with _get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, title, severity, category, description,
                          recommendation, "trafficDirection", region,
                          "resourceType", "estCostImpact", "credentialId"
                   FROM "Finding" WHERE "engagementId" = %s""",
                (engagement_id,),
            )
            rows = cur.fetchall()
    return [dict(row) for row in rows]


def _load_latest_topology(engagement_id: str):
    """Parse the most recent DiscoveryJob.topologyJson into an AzureTopology.

    Best effort — returns None when no checkpoint exists or parsing fails
    (the encyclopedia renders without topology tables and diagrams)."""
    with _get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT "topologyJson" FROM "DiscoveryJob"
                   WHERE "engagementId" = %s AND "topologyJson" IS NOT NULL
                   ORDER BY "updatedAt" DESC LIMIT 1""",
                (engagement_id,),
            )
            row = cur.fetchone()
    if not row or not row["topologyJson"]:
        return None
    try:
        from cna.core.topology_schema import AzureTopology

        return AzureTopology.model_validate_json(row["topologyJson"])
    except Exception as exc:  # noqa: BLE001 — degrade to findings-only report
        logger.warning("topology parse failed for engagement %s: %s", engagement_id, exc)
        return None


@router.post("/{engagement_id}/encyclopedia")
def render_encyclopedia(engagement_id: str, body: EncyclopediaRequest) -> dict:
    """Render the encyclopedia report as HTML for the given edition."""
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="DATABASE_URL not configured")
    if body.edition not in (EDITION_CONDENSED, EDITION_EXPANDED):
        raise HTTPException(
            status_code=422,
            detail=f"edition must be 'condensed' or 'expanded', got {body.edition!r}",
        )

    findings = _load_findings(engagement_id)
    if not findings:
        raise HTTPException(
            status_code=409,
            detail="No findings for this engagement — run discovery/analysis first.",
        )

    topology = _load_latest_topology(engagement_id)
    stat_bundle = build_stat_masters(topology, findings, engagement_id=engagement_id)

    renderer = EncyclopediaReportRenderer(edition=body.edition)
    html = renderer.render_html(
        findings,
        topology=topology,
        stat_bundle=stat_bundle,
        engagement={
            "engagement_id": engagement_id,
            "client_org": body.client_org,
            "engagement_name": body.engagement_name or "Cloud Network Assessment",
            "generated_at": body.generated_at,
        },
    )
    return {
        "engagement_id": engagement_id,
        "edition": body.edition,
        "format": "html",
        "content": html,
    }
