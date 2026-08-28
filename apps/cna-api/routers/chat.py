"""Chat router — grounded copilot Q&A per engagement (Phase G).

Stateless: each POST loads the engagement's persisted Finding rows,
MetricRecord summary and latest discovery topology from Postgres, builds a
GroundingContext, and asks cna.ai_engine.chat_agent.GroundedChatAgent for an
answer over that context only. No conversation state is stored server-side —
the client resends the full message list each turn.

The active AI engine follows the same AppSetting 'ai.activeEngine' switch
the web tier uses (apps/cna-web/lib/ai-engine.ts); transport/config is the
existing Azure Foundry path — no new provider.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# Ensure the repo root is on the path so `cna` package is importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from cna.ai_engine.chat_agent import (
    ChatConfigError,
    GroundedChatAgent,
    build_grounding_context,
)

logger = logging.getLogger("cna-api.chat")

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Keep in sync with apps/cna-web/lib/ai-engine.ts AI_ENGINE_SETTING_KEY
AI_ENGINE_SETTING_KEY = "ai.activeEngine"

MAX_MESSAGES = 30
MAX_MESSAGE_CHARS = 4000

router = APIRouter(prefix="/chat", tags=["chat"])


def _get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant" | "system" (system turns are ignored)
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)


def _load_findings(engagement_id: str) -> list[dict]:
    with _get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, title, severity, category, description,
                          "trafficDirection", region, "resourceType",
                          "estCostImpact", "credentialId"
                   FROM "Finding" WHERE "engagementId" = %s""",
                (engagement_id,),
            )
            rows = cur.fetchall()
    return [dict(row) for row in rows]


def _load_stat_summary(engagement_id: str) -> dict:
    """Compact rollups from MetricRecord rows (Phase C) for the prompt."""
    with _get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT "trafficDirection", severity,
                          SUM("findingCount") AS findings,
                          SUM("estMonthlyCostImpact") AS cost
                   FROM "MetricRecord" WHERE "engagementId" = %s
                   GROUP BY "trafficDirection", severity""",
                (engagement_id,),
            )
            rows = cur.fetchall()

    by_direction: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    total_cost = 0.0
    for row in rows:
        direction = row["trafficDirection"] or "unclassified"
        severity = row["severity"] or "UNKNOWN"
        count = int(row["findings"] or 0)
        by_direction[direction] = by_direction.get(direction, 0) + count
        by_severity[severity] = by_severity.get(severity, 0) + count
        total_cost += float(row["cost"] or 0.0)

    if not rows:
        return {}
    return {
        "findings_by_traffic_direction": by_direction,
        "findings_by_severity": by_severity,
        "total_est_monthly_cost_impact_usd [VERIFY]": round(total_cost, 2),
    }


def _load_topology_classification(engagement_id: str) -> tuple[str | None, str | None]:
    """Classify the latest discovery topology. Best effort — (None, None)
    when no checkpoint exists or parsing fails."""
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
        return None, None
    try:
        from cna.core.topology_schema import AzureTopology
        from cna.modules.network.analysis.topology_classifier import classify_topology

        classification = classify_topology(AzureTopology.model_validate_json(row["topologyJson"]))
        return classification.pattern, classification.rationale
    except Exception as exc:  # noqa: BLE001 — grounding metadata only, never fatal
        logger.warning("topology classify failed for %s: %s", engagement_id, exc)
        return None, None


def _load_active_engine() -> str | None:
    """Read the AppSetting engine switch; None falls back to env default."""
    try:
        with _get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'SELECT value FROM "AppSetting" WHERE key = %s',
                    (AI_ENGINE_SETTING_KEY,),
                )
                row = cur.fetchone()
        return row["value"] if row else None
    except Exception:  # noqa: BLE001 — setting read must never block chat
        return None


@router.post("/{engagement_id}")
def chat(engagement_id: str, request: ChatRequest) -> dict:
    """Grounded Q&A over the engagement's findings + metrics + topology."""
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="DATABASE_URL not configured")
    if not request.messages:
        raise HTTPException(status_code=422, detail="messages must not be empty")

    messages = [
        {"role": m.role, "content": m.content[:MAX_MESSAGE_CHARS]}
        for m in request.messages[-MAX_MESSAGES:]
    ]

    findings = _load_findings(engagement_id)
    stat_summary = _load_stat_summary(engagement_id)
    pattern, rationale = _load_topology_classification(engagement_id)

    context = build_grounding_context(
        engagement_id=engagement_id,
        findings=findings,
        stat_summary=stat_summary,
        topology_pattern=pattern,
        topology_rationale=rationale,
    )

    try:
        agent = GroundedChatAgent(engine=_load_active_engine())
        result = agent.answer(messages, context)
    except ChatConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — surface upstream failures as 502
        # Full details stay in the server log; callers get a sanitized message.
        logger.exception("chat completion failed for %s", engagement_id)
        raise HTTPException(
            status_code=502,
            detail="AI engine request failed — see the API logs for details.",
        ) from exc

    return {
        "answer": result.text,
        "citations": [c.model_dump() for c in result.citations],
        "engine": result.engine,
        "grounding": {
            "findings_in_context": len(context.findings),
            "total_findings": context.total_finding_count,
            "truncated": context.truncated,
            "topology_pattern": context.topology_pattern,
        },
    }


__all__ = ["router"]
