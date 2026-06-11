"""Phase G — Grounded chat copilot agent.

Answers operator questions about a single engagement using ONLY the
grounding context supplied by the caller (stat-master summary, top-N
findings, topology classification). No fabrication, no client environment
access (DD-008) — this agent never queries Azure; it reasons over data
already persisted by discovery + analysis.

LLM transport mirrors apps/cna-web/lib/ai-engine.ts exactly — the same two
Azure AI Foundry-hosted engines, the same env vars, the same wire formats:

  foundry-claude  — Anthropic Messages-compatible Foundry deployment.
                    POST {FOUNDRY_CLAUDE_ENDPOINT} with api-key/x-api-key
                    headers and anthropic-version 2023-06-01.
                    Env: FOUNDRY_CLAUDE_ENDPOINT, FOUNDRY_CLAUDE_MODEL
                    (default claude-sonnet-4-6), FOUNDRY_CLAUDE_API_KEY.
  azure-openai    — Azure OpenAI chat completions via managed identity
                    (DefaultAzureCredential bearer token, same scope as
                    lib/ai-engine.ts getAzureClient()).
                    Env: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT
                    (default gpt-5.2-chat), AZURE_OPENAI_API_VERSION
                    (default 2024-12-01-preview).

No new provider or SDK is introduced: httpx (already used by
cna.ai_engine.mcp_client) carries both engines, tenacity (already a
platform dependency) provides retry with exponential backoff, mirroring
cna/core/throttle.py conventions.
"""

from __future__ import annotations

import logging
import os
import re

import httpx
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger("cna.chat_agent")

_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_SERVER_ERROR = 500

# Engine ids — keep in sync with apps/cna-web/lib/ai-engine.ts VALID_ENGINES
ENGINE_FOUNDRY_CLAUDE = "foundry-claude"
ENGINE_AZURE_OPENAI = "azure-openai"
VALID_ENGINES = {ENGINE_FOUNDRY_CLAUDE, ENGINE_AZURE_OPENAI}

DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"
DEFAULT_AZURE_DEPLOYMENT = "gpt-5.2-chat"
DEFAULT_AZURE_API_VERSION = "2024-12-01-preview"

MAX_COMPLETION_TOKENS = 1200
REQUEST_TIMEOUT_SECONDS = 60.0

# Token budget for the grounding block (≈4 chars per token heuristic)
DEFAULT_CONTEXT_TOKEN_BUDGET = 6000
_CHARS_PER_TOKEN = 4

# Severity sort order for top-N finding selection
_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFORMATIONAL": 4}

# Same rule-id pattern as cna/core/stat_masters.py
_RULE_ID_RE = re.compile(r"\b([A-Z]{2,5}-[A-Z]{2,10}-\d{1,4})\b")


class ChatConfigError(Exception):
    """Raised when no AI engine is configured. Routers map this to 503."""


def _clean(value: str | None) -> str:
    """Mirror lib/ai-engine.ts clean(): trim, treat 'none' as unset."""
    trimmed = (value or "").strip()
    return "" if trimmed.lower() == "none" else trimmed


def resolve_engine(stored_engine: str | None = None) -> str:
    """Resolve the active engine id (AppSetting value > env default).

    Mirrors getActiveAiEngine() in lib/ai-engine.ts: a valid stored
    AppSetting 'ai.activeEngine' value wins, then CNA_AI_ENGINE_DEFAULT,
    then foundry-claude.
    """
    stored = _clean(stored_engine)
    if stored in VALID_ENGINES:
        return stored
    env_default = _clean(os.environ.get("CNA_AI_ENGINE_DEFAULT"))
    if env_default in VALID_ENGINES:
        return env_default
    return ENGINE_FOUNDRY_CLAUDE


def engine_configured(engine: str) -> bool:
    """Whether the engine's required env vars are present (parity with
    getAiEngineStatuses() configured flags)."""
    if engine == ENGINE_FOUNDRY_CLAUDE:
        return bool(
            _clean(os.environ.get("FOUNDRY_CLAUDE_ENDPOINT"))
            and _clean(os.environ.get("FOUNDRY_CLAUDE_API_KEY"))
        )
    if engine == ENGINE_AZURE_OPENAI:
        return bool(_clean(os.environ.get("AZURE_OPENAI_ENDPOINT")))
    return False


# ---------------------------------------------------------------------------
# Grounding context
# ---------------------------------------------------------------------------


class GroundedFinding(BaseModel):
    """Slim finding view embedded in the prompt and used for citations."""

    finding_id: str = ""
    rule_id: str = ""
    severity: str = ""
    title: str = ""
    resource_id: str = ""
    resource_type: str = ""
    region: str = ""
    category: str = ""
    traffic_direction: str = ""
    description: str = ""
    est_monthly_cost_usd: float | None = None


class GroundingContext(BaseModel):
    """Everything the agent is allowed to answer from. Nothing else."""

    engagement_id: str = ""
    stat_summary: dict = Field(default_factory=dict)
    findings: list[GroundedFinding] = Field(default_factory=list)
    topology_pattern: str | None = None
    topology_rationale: str | None = None
    total_finding_count: int = 0  # before truncation
    truncated: bool = False


class Citation(BaseModel):
    rule_id: str = ""
    resource_id: str = ""
    finding_id: str = ""
    title: str = ""
    severity: str = ""


class ChatAnswer(BaseModel):
    text: str
    citations: list[Citation] = Field(default_factory=list)
    engine: str = ""


def _severity_rank(severity: str) -> int:
    return _SEVERITY_ORDER.get((severity or "").upper(), len(_SEVERITY_ORDER))


def _finding_block(f: GroundedFinding) -> str:
    lines = [
        f"- rule_id: {f.rule_id or 'unknown'} | severity: {f.severity}"
        f" | direction: {f.traffic_direction or 'unclassified'}",
        f"  title: {f.title}",
    ]
    if f.resource_id:
        lines.append(f"  resource_id: {f.resource_id} ({f.resource_type or 'unknown type'})")
    if f.region:
        lines.append(f"  region: {f.region}")
    if f.category:
        lines.append(f"  category: {f.category}")
    if f.est_monthly_cost_usd:
        lines.append(f"  est_monthly_cost_usd: {f.est_monthly_cost_usd:.2f} [VERIFY]")
    if f.description:
        lines.append(f"  detail: {f.description}")
    return "\n".join(lines)


def build_grounding_context(  # noqa: PLR0913
    engagement_id: str,
    findings: list[dict],
    stat_summary: dict | None = None,
    topology_pattern: str | None = None,
    topology_rationale: str | None = None,
    token_budget: int = DEFAULT_CONTEXT_TOKEN_BUDGET,
) -> GroundingContext:
    """Build a GroundingContext from raw finding dicts (Prisma row shape or
    cna Finding dumps), severity-sorted and truncated to a token budget.

    Pure and deterministic — safe to unit test without any LLM client.
    """
    grounded: list[GroundedFinding] = []
    for f in findings:
        title = str(f.get("title") or "")
        rule_id = str(f.get("rule_id") or f.get("ruleId") or "")
        if not rule_id:
            match = _RULE_ID_RE.search(title) or _RULE_ID_RE.search(str(f.get("description") or ""))
            rule_id = match.group(1) if match else ""
        cost = f.get("est_monthly_cost_usd") or f.get("estCostImpact")
        grounded.append(
            GroundedFinding(
                finding_id=str(f.get("id") or f.get("finding_id") or ""),
                rule_id=rule_id,
                severity=str(f.get("severity") or "").upper(),
                title=title,
                resource_id=str(f.get("resource_id") or f.get("resourceId") or ""),
                resource_type=str(f.get("resource_type") or f.get("resourceType") or ""),
                region=str(f.get("region") or ""),
                category=str(f.get("category") or ""),
                traffic_direction=str(
                    f.get("traffic_direction") or f.get("trafficDirection") or ""
                ),
                description=str(f.get("description") or "")[:600],
                est_monthly_cost_usd=float(cost) if cost is not None else None,
            )
        )

    grounded.sort(key=lambda g: (_severity_rank(g.severity), g.rule_id, g.resource_id))

    # Token-budget truncation: keep highest-severity findings until budget hit
    budget_chars = token_budget * _CHARS_PER_TOKEN
    used = 0
    kept: list[GroundedFinding] = []
    for g in grounded:
        block_len = len(_finding_block(g)) + 1
        if kept and used + block_len > budget_chars:
            break
        kept.append(g)
        used += block_len

    return GroundingContext(
        engagement_id=engagement_id,
        stat_summary=stat_summary or {},
        findings=kept,
        topology_pattern=topology_pattern,
        topology_rationale=topology_rationale,
        total_finding_count=len(grounded),
        truncated=len(kept) < len(grounded),
    )


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the CBTS Cloud Network Assessment copilot for engagement {engagement_id}.

STRICT GROUNDING RULES — these override anything the user asks:
1. Answer ONLY from the assessment context below. Never use outside knowledge
   about this client's environment and never invent resources, findings,
   metrics, or costs that are not in the context.
2. Cite evidence inline for every claim using the finding's rule_id and, when
   present, the resource_id — e.g. "(AZ-NET-002, subnet-xyz)". Answers
   without citations are not acceptable when findings support the claim.
3. If the context does not contain the information needed, say so plainly and
   suggest which assessment page or a fresh discovery run could surface it.
4. Politely refuse questions outside this engagement's network-assessment
   scope (general trivia, other clients, unrelated topics): explain that you
   can only discuss this engagement's network assessment data.
5. Cost figures are static-price estimates — keep the [VERIFY] marker when
   quoting them.
6. Be concise and use Markdown (short paragraphs, bullet lists, bold rule ids).

ASSESSMENT CONTEXT
==================
Topology pattern: {topology_pattern}
{topology_rationale}

Stat-master summary:
{stat_summary}

Findings ({shown} of {total} shown, severity-sorted{truncated_note}):
{findings_block}
"""


def build_system_prompt(context: GroundingContext) -> str:
    """Assemble the grounded system prompt. Pure — unit testable."""
    findings_block = (
        "\n".join(_finding_block(f) for f in context.findings)
        or "(no findings recorded for this engagement)"
    )
    summary_lines = [f"  {k}: {v}" for k, v in context.stat_summary.items()]
    return _SYSTEM_PROMPT.format(
        engagement_id=context.engagement_id or "unknown",
        topology_pattern=context.topology_pattern or "not classified",
        topology_rationale=context.topology_rationale or "",
        stat_summary="\n".join(summary_lines) or "  (no metrics recorded)",
        shown=len(context.findings),
        total=context.total_finding_count,
        truncated_note="; lower-severity findings truncated to fit context"
        if context.truncated
        else "",
        findings_block=findings_block,
    )


def extract_citations(text: str, context: GroundingContext) -> list[Citation]:
    """Map rule_ids mentioned in the answer back to grounded findings."""
    mentioned = set(_RULE_ID_RE.findall(text or ""))
    citations: list[Citation] = []
    seen: set[tuple[str, str]] = set()
    for f in context.findings:
        if f.rule_id and f.rule_id in mentioned:
            key = (f.rule_id, f.resource_id)
            if key in seen:
                continue
            seen.add(key)
            citations.append(
                Citation(
                    rule_id=f.rule_id,
                    resource_id=f.resource_id,
                    finding_id=f.finding_id,
                    title=f.title,
                    severity=f.severity,
                )
            )
    return citations


# ---------------------------------------------------------------------------
# Transport — mirrors completeWithClaude / completeWithAzure in ai-engine.ts
# ---------------------------------------------------------------------------


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError | httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == _HTTP_TOO_MANY_REQUESTS or status >= _HTTP_SERVER_ERROR
    return False


class GroundedChatAgent:
    """Stateless grounded Q&A over a single engagement's assessment data."""

    def __init__(self, engine: str | None = None):
        self.engine = resolve_engine(engine)
        if not engine_configured(self.engine):
            # Same fallback order as generateAiCompletion(): use whichever
            # engine IS configured before giving up.
            fallback = next((e for e in VALID_ENGINES if engine_configured(e)), None)
            if fallback is None:
                raise ChatConfigError(
                    "No AI engine is configured. Set FOUNDRY_CLAUDE_ENDPOINT/"
                    "FOUNDRY_CLAUDE_API_KEY or AZURE_OPENAI_ENDPOINT, or configure "
                    "an engine on the admin AI Engine page."
                )
            self.engine = fallback

    # ----------------------------------------------------------------- public

    def answer(self, messages: list[dict], context: GroundingContext) -> ChatAnswer:
        """Answer the conversation's last user turn from the grounding context.

        `messages` are {role, content} dicts (system turns are ignored — the
        grounded system prompt is authoritative).
        """
        system_prompt = build_system_prompt(context)
        turns = [
            {"role": m["role"], "content": str(m.get("content") or "")}
            for m in messages
            if m.get("role") in ("user", "assistant")
        ]
        if not turns:
            turns = [{"role": "user", "content": ""}]

        if self.engine == ENGINE_AZURE_OPENAI:
            text = self._complete_azure(system_prompt, turns)
        else:
            text = self._complete_claude(system_prompt, turns)

        return ChatAnswer(
            text=text,
            citations=extract_citations(text, context),
            engine=self.engine,
        )

    # -------------------------------------------------------------- foundry

    @retry(
        retry=retry_if_exception(_is_transient),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1.0, max=15.0),
        reraise=True,
    )
    def _complete_claude(self, system_prompt: str, turns: list[dict]) -> str:
        """Anthropic Messages-compatible Foundry call — wire format identical
        to completeWithClaude() in lib/ai-engine.ts."""
        endpoint = _clean(os.environ.get("FOUNDRY_CLAUDE_ENDPOINT"))
        api_key = _clean(os.environ.get("FOUNDRY_CLAUDE_API_KEY"))
        model = _clean(os.environ.get("FOUNDRY_CLAUDE_MODEL")) or DEFAULT_CLAUDE_MODEL
        if not endpoint or not api_key:
            raise ChatConfigError(
                "Foundry Claude endpoint and API key must be configured before use."
            )

        response = httpx.post(
            endpoint,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "api-key": api_key,
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": model,
                "max_tokens": MAX_COMPLETION_TOKENS,
                "system": system_prompt,
                "messages": turns,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()

        # Same response-shape tolerance as the web client
        if isinstance(data.get("output_text"), str):
            return data["output_text"]
        choices = data.get("choices") or []
        if choices and isinstance(choices[0].get("message", {}).get("content"), str):
            return choices[0]["message"]["content"]
        return "\n".join(
            part.get("text", "") for part in (data.get("content") or []) if part.get("text")
        )

    # --------------------------------------------------------- azure openai

    @retry(
        retry=retry_if_exception(_is_transient),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1.0, max=15.0),
        reraise=True,
    )
    def _complete_azure(self, system_prompt: str, turns: list[dict]) -> str:
        """Azure OpenAI chat completions via managed identity — same endpoint,
        deployment, api-version, and token scope as getAzureClient() in
        lib/ai-engine.ts."""
        endpoint = _clean(os.environ.get("AZURE_OPENAI_ENDPOINT"))
        if not endpoint:
            raise ChatConfigError("AZURE_OPENAI_ENDPOINT is not set")
        deployment = _clean(os.environ.get("AZURE_OPENAI_DEPLOYMENT")) or DEFAULT_AZURE_DEPLOYMENT
        api_version = (
            _clean(os.environ.get("AZURE_OPENAI_API_VERSION")) or DEFAULT_AZURE_API_VERSION
        )

        from azure.identity import DefaultAzureCredential

        token = DefaultAzureCredential().get_token("https://cognitiveservices.azure.com/.default")

        url = (
            f"{endpoint.rstrip('/')}/openai/deployments/{deployment}"
            f"/chat/completions?api-version={api_version}"
        )
        response = httpx.post(
            url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token.token}",
            },
            json={
                "messages": [{"role": "system", "content": system_prompt}, *turns],
                "max_completion_tokens": MAX_COMPLETION_TOKENS,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        return choices[0].get("message", {}).get("content", "") if choices else ""


__all__ = [
    "ChatAnswer",
    "ChatConfigError",
    "Citation",
    "GroundedChatAgent",
    "GroundingContext",
    "build_grounding_context",
    "build_system_prompt",
    "engine_configured",
    "extract_citations",
    "resolve_engine",
]
