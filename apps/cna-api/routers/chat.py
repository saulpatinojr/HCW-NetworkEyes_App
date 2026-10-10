"""Chat router — grounded copilot Q&A per engagement (Phase G).

Stateless: each POST loads the engagement's persisted Finding rows,
MetricRecord summary and latest discovery topology from Postgres, builds a
GroundingContext, and asks cna.ai_engine.chat_agent.GroundedChatAgent for an
answer over that context only. No conversation state is stored server-side —
the client resends the full message list each turn.

The active AI engine follows the same AppSetting 'ai.activeEngine' switch
the web tier uses (apps/cna-web/lib/ai-engine.ts). In bring-your-own mode
(CNA_AI_MODE=byo-api) the admin-entered Anthropic/OpenAI keys are read from
the same table (ai.byo.<provider>.apiKey, AES-256-GCM blobs written by
lib/crypto.ts) and decrypted here with cna.core.credential_crypto. Keys never
leave this process and are never logged.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# Ensure the repo root is on the path so `cna` package is importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from cna.ai_engine.chat_agent import (
    BYO_ENGINES,
    MODE_BYO_API,
    ChatConfigError,
    GroundedChatAgent,
    build_grounding_context,
    resolve_ai_mode,
)
from cna.api_errors import sanitize_downstream_error
from cna.api_status import Outcome, status_for
from cna.core.credential_crypto import CredentialCryptoError, decrypt

logger = logging.getLogger("cna-api.chat")

import db  # noqa: E402, I001 — apps/cna-api is on sys.path (see main.py)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Keep in sync with apps/cna-web/lib/ai-engine.ts AI_ENGINE_SETTING_KEY and
# lib/ai-byo-credentials.ts byoSettingKey()
AI_ENGINE_SETTING_KEY = "ai.activeEngine"


def _byo_setting_key(provider: str, field: str) -> str:
    return f"ai.byo.{provider}.{field}"


AI_SETTING_KEYS = (
    AI_ENGINE_SETTING_KEY,
    *(_byo_setting_key(p, "apiKey") for p in BYO_ENGINES),
    *(_byo_setting_key(p, "model") for p in BYO_ENGINES),
)

MAX_MESSAGES = 30
MAX_MESSAGE_CHARS = 4000

router = APIRouter(prefix="/chat", tags=["chat"])


def _get_db():
    # Pooled connection with ``with conn:`` transaction semantics (T-704).
    return db.connection(DATABASE_URL)


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


def _load_ai_settings() -> dict[str, str]:
    """Read the engine switch and BYO provider settings in one round trip.

    Empty on any failure — a settings read must never block chat; the agent
    then resolves from env alone (saas) or reports the missing key (byo-api).
    """
    try:
        with _get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'SELECT key, value FROM "AppSetting" WHERE key = ANY(%s)',
                    (list(AI_SETTING_KEYS),),
                )
                rows = cur.fetchall()
        return {row["key"]: row["value"] for row in rows if row.get("value")}
    except Exception:  # noqa: BLE001 — setting read must never block chat
        logger.warning("AppSetting read failed; resolving AI engine from env only")
        return {}


def _load_byo_credentials(
    settings: dict[str, str],
) -> tuple[dict[str, str | None], dict[str, str | None]]:
    """Decrypt the admin-entered BYO keys — only in byo-api mode, so a saas
    appliance never needs CREDENTIAL_ENCRYPTION_KEY in the API container."""
    if resolve_ai_mode() != MODE_BYO_API:
        return {}, {}
    keys = {
        provider: (
            decrypt(blob) if (blob := settings.get(_byo_setting_key(provider, "apiKey"))) else None
        )
        for provider in BYO_ENGINES
    }
    models = {
        provider: settings.get(_byo_setting_key(provider, "model")) for provider in BYO_ENGINES
    }
    return keys, models


@router.post("/{engagement_id}")
def chat(engagement_id: str, request: ChatRequest) -> dict:
    """Grounded Q&A over the engagement's findings + metrics + topology."""
    if not DATABASE_URL:
        raise HTTPException(
            status_code=status_for(Outcome.NOT_CONFIGURED),
            detail="DATABASE_URL not configured",
        )
    if not request.messages:
        raise HTTPException(
            status_code=status_for(Outcome.INVALID_REQUEST),
            detail="messages must not be empty",
        )

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
        settings = _load_ai_settings()
        byo_keys, byo_models = _load_byo_credentials(settings)
        agent = GroundedChatAgent(
            engine=settings.get(AI_ENGINE_SETTING_KEY),
            byo_keys=byo_keys,
            byo_models=byo_models,
        )
        result = agent.answer(messages, context)
    except (ChatConfigError, CredentialCryptoError) as exc:
        # Both are operator configuration problems (no engine / no key / bad
        # encryption key), not caller errors and not upstream failures.
        raise HTTPException(
            status_code=status_for(Outcome.NOT_CONFIGURED), detail=str(exc)
        ) from exc
    except Exception as exc:  # noqa: BLE001 — surface upstream failures as 502
        # Raw AI-engine/SDK detail is logged server-side; the caller gets a
        # sanitized, category-level message with no raw text (Requirement 2.3).
        sanitized = sanitize_downstream_error(
            exc, logger=logger, context=f"chat completion for {engagement_id}"
        )
        raise HTTPException(
            status_code=status_for(sanitized.outcome),
            detail=sanitized.client_message,
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
