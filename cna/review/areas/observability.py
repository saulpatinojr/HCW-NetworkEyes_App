"""Findings for the ``observability`` area (Requirement 8).

This is a *verify-then-close-gaps* record for the platform's logging and
telemetry across the three reviewed surfaces — the ``apps/cna-api`` FastAPI
service, the ``apps/cna-web`` Next.js front end, and the ``cna`` Core_Engine —
with emphasis on the AI analysis path (the least-proven capability, design
section "8. Observability").

Structured-logging audit (Requirements 8.1, 8.2)
------------------------------------------------

  * **Core_Engine — verified compliant.** ``cna/core/logging_config.py`` defines
    a :class:`~cna.core.logging_config.JSONFormatter` that emits every record as
    single-line JSON carrying ``level``, ``message``, ``logger``, ``timestamp``,
    and an ``engagement_id`` correlation id, with ``extra={...}`` fields merged
    and ``exc_info`` rendered into an ``exception`` field. Errors logged through
    it (e.g. ``logger.exception(...)``) parse as structured records with at
    least a level and a message (design Property 16). Recorded as
    ``INFORMATIONAL`` so the plan reflects the verified-compliant surface.

  * **Web_Service — verified compliant.** ``apps/cna-web/instrumentation.ts``
    ``onRequestError`` serialises each server error to a single JSON line
    (``level``, ``message``, ``digest``, ``stack``, ``path``, ``route``) so a
    user-reported error digest can be correlated with the real message in Log
    Analytics. Recorded as ``INFORMATIONAL`` (verified compliant).

  * **API_Service — gap closed here.** ``apps/cna-api/main.py`` previously
    configured logging with ``logging.basicConfig(level=logging.INFO)``, which
    emits **unstructured plain-text** lines. Its error paths already log with
    ``logger.exception(...)`` (level + message + traceback), but the emitted
    records were not parseable structured records — a real Requirement 8.2 gap.
    This task attaches the Core_Engine ``JSONFormatter`` to a stdout handler on
    the root logger so every API record (and the ``cna`` engine records it
    propagates) is emitted as JSON with at least a level and a message. Recorded
    as a ``LOW`` residual gap that this task remediates.

AI-path observability coverage (Requirement 8.3)
------------------------------------------------

The AI analysis path is the least-proven capability and its observability is the
thinnest. Today the path logs only *transitions* and *counts*:
``RecommendationEngine`` logs a ``warning`` when the Foundry agent or MCP router
fails and falls back, and an ``info`` with per-source enrichment counts;
``GroundedChatAgent`` retries transient Azure OpenAI errors but records nothing
about the call itself. Two concrete coverage requirements are recorded as
**fixable** ``Remediation_Plan`` entries (the coverage requirement itself is
recorded regardless of the live backend — design "8. Observability" escalation
boundary):

  * **Trace/span correlation** across the fallback chain (Foundry agent →
    MCPRouter → offline library, and the web ``generateAiCompletion`` path) so a
    single enrichment/answer can be followed end to end.
  * **Token-usage capture.** Both ``cna.ai_engine.chat_agent._complete_azure``
    and the web ``lib/ai-engine.ts completeWithAzure`` discard the provider's
    ``response.usage`` (prompt/completion/total tokens). Recording it is required
    for cost/latency observability of the AI path.
  * **Fallback-path logging** is present but unstructured/count-only — the
    fixable entry folds the fallback-visibility requirement into the trace/span
    coverage above.

One AI-path coverage requirement is an **escalation**: verifying and
instrumenting the **live Bedrock** invocation path (trace/span + token usage +
throttling/error telemetry around real ``bedrock:InvokeModel`` calls) cannot be
exercised without Bedrock foundation-model access, which is enabled manually per
account/region and is owned by ``REVIEW.md`` **R-005**. That single finding
carries ``blocker_id="R-005"`` and no automated fix; the non-Bedrock coverage
requirements above remain fixable. These records are consumed by the
consolidation step (spec task 14.1) and, for the escalation, routed through the
scope gate (spec task 2.1 / 14.3).
"""

from __future__ import annotations

from cna.review.model import Finding, Severity

_AREA = "observability"


def _structured_logging_findings() -> list[Finding]:
    """Requirements 8.1 / 8.2 — structured-log capture across the three surfaces."""
    return [
        Finding(
            area=_AREA,
            severity=Severity.INFORMATIONAL,
            proposed_action=(
                "Verified compliant: the Core_Engine logging_config.JSONFormatter "
                "emits every record as single-line JSON (level, message, logger, "
                "timestamp, engagement_id correlation id) with extra fields merged "
                "and exc_info rendered, so errors logged through it parse as "
                "structured records with at least a level and a message. Keep it "
                "as the engine's log formatter."
            ),
            dedup_key="observability:core-engine-structured-json-logging",
            subject="cna/core/logging_config.py",
        ),
        Finding(
            area=_AREA,
            severity=Severity.INFORMATIONAL,
            proposed_action=(
                "Verified compliant: the Web_Service instrumentation.ts "
                "onRequestError hook serialises each server error to a single "
                "JSON line (level, message, digest, stack, path, route) so a "
                "user-reported error digest correlates with the real message in "
                "Log Analytics. Keep the onRequestError structured-log path."
            ),
            dedup_key="observability:web-onrequesterror-structured-logging",
            subject="apps/cna-web/instrumentation.ts",
        ),
        Finding(
            area=_AREA,
            severity=Severity.LOW,
            proposed_action=(
                "The API_Service configured logging with "
                "logging.basicConfig(level=INFO), emitting unstructured "
                "plain-text lines; error paths log via logger.exception(...) but "
                "the records were not parseable structured records (Requirement "
                "8.2 gap). Attach the Core_Engine JSONFormatter to a stdout "
                "handler on the root logger so every API record — and the cna "
                "engine records it propagates — is emitted as JSON with at least "
                "a level and a message. Applied by this task."
            ),
            dedup_key="observability:api-structured-json-logging",
            subject="apps/cna-api/main.py",
        ),
    ]


def _ai_path_coverage_findings() -> list[Finding]:
    """Requirement 8.3 — observability coverage required for the AI path.

    The non-Bedrock coverage (trace/span + token usage across the Foundry
    agent / MCP router / Azure OpenAI fallback chain) is a fixable plan entry;
    instrumenting the live Bedrock invocation path is gated on ``REVIEW.md``
    R-005 (Bedrock model-access opt-in) and is the one escalation here.
    """
    return [
        Finding(
            area=_AREA,
            severity=Severity.MEDIUM,
            proposed_action=(
                "AI-path observability coverage required (least-proven "
                "capability): add trace/span correlation across the "
                "RecommendationEngine fallback chain (Foundry agent -> MCPRouter "
                "-> offline library) and the web generateAiCompletion path so a "
                "single enrichment/answer is followable end to end, and capture "
                "token usage — both cna.ai_engine.chat_agent._complete_azure and "
                "apps/cna-web/lib/ai-engine.ts completeWithAzure currently discard "
                "response.usage (prompt/completion/total tokens). Today the path "
                "logs only fallback-transition warnings and per-source counts. "
                "Fixable: this coverage does not depend on a live cloud backend."
            ),
            dedup_key="observability:ai-path-trace-token-coverage",
            subject="cna/ai_engine",
        ),
        Finding(
            area=_AREA,
            severity=Severity.MEDIUM,
            proposed_action=(
                "Escalation: verifying and instrumenting the live Bedrock "
                "invocation path (trace/span, token usage, and "
                "throttling/error telemetry around real bedrock:InvokeModel "
                "calls) cannot be exercised without Bedrock foundation-model "
                "access, which is enabled manually per account/region and is "
                "owned by REVIEW.md R-005. Record the AI-path Bedrock "
                "observability requirement; do not attempt a live invocation. "
                "Owner: REVIEW.md R-005."
            ),
            dedup_key="observability:ai-path-bedrock-coverage",
            subject="cna/ai_engine (Bedrock invocation path)",
            blocker_id="R-005",
        ),
    ]


def observability_findings() -> list[Finding]:
    """Return the Requirement 8 findings recorded for the observability area.

    Combines the structured-logging audit across the API, web, and core engine
    (8.1 / 8.2 — two verified-compliant surfaces plus the API gap this task
    closes) with the AI-path coverage requirement (8.3 — a fixable trace/span +
    token-usage entry and the R-005 live-Bedrock escalation).
    """
    return _structured_logging_findings() + _ai_path_coverage_findings()
