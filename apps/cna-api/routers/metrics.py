"""Metrics router — stat-master records per engagement (Phase C).

Builds flat aggregated records (cna.core.stat_masters) from the persisted
Finding rows + latest discovery topology, materializes them into the
MetricRecord table, and serves them back to cna-web. Record shape matches
apps/cna-web/lib/types/stat-master.ts so pages can swap from client-side
derivation to this endpoint without type changes.
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, HTTPException, Query

# Ensure the repo root is on the path so `cna` package is importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from cna.core.stat_masters import StatMasterRecord, build_stat_masters

logger = logging.getLogger("cna-api.metrics")

DATABASE_URL = os.environ.get("DATABASE_URL", "")

router = APIRouter(prefix="/metrics", tags=["metrics"])


def _get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


# Prisma MetricRecord column ↔ StatMasterRecord field mapping
_DIMENSION_COLUMNS: dict[str, str] = {
    "traffic_direction": "trafficDirection",
    "severity": "severity",
    "framework": "framework",
    "region": "region",
    "subscription_id": "subscriptionId",
    "resource_type": "resourceType",
    "category": "category",
    "rule_id": "ruleId",
}


def _row_to_record(row: dict) -> dict:
    """Map a MetricRecord DB row to the StatMasterRecord wire shape."""
    return {
        "traffic_direction": row["trafficDirection"] or "unclassified",
        "severity": row["severity"] or "",
        "framework": row["framework"] or "Unmapped",
        "region": row["region"] or "Unknown",
        "subscription_id": row["subscriptionId"] or "default",
        "resource_type": row["resourceType"] or "Other",
        "category": row["category"] or "Uncategorized",
        "rule_id": row["ruleId"] or "—",
        "finding_count": row["findingCount"],
        "resource_count": row["resourceCount"],
        "est_monthly_cost_impact": row["estMonthlyCostImpact"],
    }


def _load_finding_dicts(engagement_id: str) -> list[dict]:
    with _get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT title, severity, category, "trafficDirection", region,
                          "resourceType", "estCostImpact", "credentialId"
                   FROM "Finding" WHERE "engagementId" = %s""",
                (engagement_id,),
            )
            rows = cur.fetchall()
    return [dict(row) for row in rows]


def _load_latest_topology(engagement_id: str) -> Any | None:
    """Parse the most recent DiscoveryJob.topologyJson into an AzureTopology.

    Best effort — returns None when no checkpoint exists or parsing fails
    (topology is only used for bundle metadata)."""
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
    except Exception as exc:  # noqa: BLE001 — metadata only, never fatal
        logger.warning("topology parse failed for engagement %s: %s", engagement_id, exc)
        return None


def rebuild_metrics(engagement_id: str) -> int:
    """Rebuild MetricRecord rows for an engagement. Returns the row count.

    Delete + insert inside a single transaction so readers never observe a
    half-built set. Also called from main.py at the end of a discovery run.
    """
    if not DATABASE_URL:
        return 0
    findings = _load_finding_dicts(engagement_id)
    topology = _load_latest_topology(engagement_id)
    bundle = build_stat_masters(topology, findings, engagement_id=engagement_id)

    now = datetime.now(UTC)
    with _get_db() as conn:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM "MetricRecord" WHERE "engagementId" = %s', (engagement_id,))
            if bundle.records:
                psycopg2.extras.execute_values(
                    cur,
                    """INSERT INTO "MetricRecord"
                         (id, "engagementId", "trafficDirection", severity, framework,
                          region, "subscriptionId", "resourceType", category, "ruleId",
                          "findingCount", "resourceCount", "estMonthlyCostImpact",
                          "createdAt")
                       VALUES %s""",
                    [
                        (
                            str(uuid.uuid4()),
                            engagement_id,
                            r.traffic_direction,
                            r.severity,
                            r.framework,
                            r.region,
                            r.subscription_id,
                            r.resource_type,
                            r.category,
                            r.rule_id,
                            r.finding_count,
                            r.resource_count,
                            r.est_monthly_cost_impact,
                            now,
                        )
                        for r in bundle.records
                    ],
                )
        conn.commit()
    return len(bundle.records)


@router.post("/{engagement_id}/rebuild")
def rebuild(engagement_id: str) -> dict:
    """Rebuild stat-master records from current findings + latest topology."""
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="DATABASE_URL not configured")
    count = rebuild_metrics(engagement_id)
    return {"engagement_id": engagement_id, "records": count, "status": "rebuilt"}


@router.get("/{engagement_id}")
def get_metrics(  # noqa: PLR0913 — one optional filter per dimension
    engagement_id: str,
    traffic_direction: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    framework: str | None = Query(default=None),
    region: str | None = Query(default=None),
    subscription_id: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    rule_id: str | None = Query(default=None),
) -> list[dict]:
    """Flat StatMasterRecord rows, optionally filtered per dimension."""
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="DATABASE_URL not configured")

    filters = {
        "traffic_direction": traffic_direction,
        "severity": severity,
        "framework": framework,
        "region": region,
        "subscription_id": subscription_id,
        "resource_type": resource_type,
        "category": category,
        "rule_id": rule_id,
    }
    where = ['"engagementId" = %s']
    values: list[Any] = [engagement_id]
    for field, value in filters.items():
        if value is not None:
            where.append(f'"{_DIMENSION_COLUMNS[field]}" = %s')
            values.append(value)

    with _get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f'SELECT * FROM "MetricRecord" WHERE {" AND ".join(where)}',  # noqa: S608 — identifiers from fixed map
                values,
            )
            rows = cur.fetchall()
    return [_row_to_record(row) for row in rows]


@router.get("/{engagement_id}/summary")
def get_summary(engagement_id: str) -> dict:
    """Rollups for dashboards: by direction, severity × direction, by region,
    plus the total estimated monthly cost impact."""
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="DATABASE_URL not configured")

    with _get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT * FROM "MetricRecord" WHERE "engagementId" = %s',
                (engagement_id,),
            )
            rows = cur.fetchall()

    records = [_row_to_record(row) for row in rows]

    by_direction: dict[str, dict[str, float]] = {}
    severity_by_direction: dict[str, dict[str, int]] = {}
    by_region: dict[str, dict[str, float]] = {}
    total_cost = 0.0

    for r in records:
        direction = r["traffic_direction"]
        dir_agg = by_direction.setdefault(
            direction, {"finding_count": 0, "est_monthly_cost_impact": 0.0}
        )
        dir_agg["finding_count"] += r["finding_count"]
        dir_agg["est_monthly_cost_impact"] += r["est_monthly_cost_impact"]

        sev_agg = severity_by_direction.setdefault(direction, {})
        sev_agg[r["severity"]] = sev_agg.get(r["severity"], 0) + r["finding_count"]

        region_agg = by_region.setdefault(
            r["region"], {"finding_count": 0, "est_monthly_cost_impact": 0.0}
        )
        region_agg["finding_count"] += r["finding_count"]
        region_agg["est_monthly_cost_impact"] += r["est_monthly_cost_impact"]

        total_cost += r["est_monthly_cost_impact"]

    return {
        "engagement_id": engagement_id,
        "record_count": len(records),
        "total_findings": sum(r["finding_count"] for r in records),
        "total_est_monthly_cost_impact": round(total_cost, 2),
        "by_traffic_direction": by_direction,
        "severity_by_direction": severity_by_direction,
        "by_region": by_region,
    }


# Exported for type checkers / OpenAPI consumers
__all__ = ["router", "rebuild_metrics", "StatMasterRecord"]
