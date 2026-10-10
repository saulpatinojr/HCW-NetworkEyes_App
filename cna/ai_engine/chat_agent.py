"""Phase G — Grounded chat copilot agent.

Answers operator questions about a single engagement using ONLY the
grounding context supplied by the caller (stat-master summary, top-N
findings, topology classification). No fabrication, no client environment
access (DD-008) — this agent never queries Azure; it reasons over data
already persisted by discovery + analysis.

Engine selection mirrors apps/cna-web/lib/ai-engine.ts exactly — same engine
ids, same env vars, same resolution rules. The appliance's deploy-time AI mode
(``CNA_AI_MODE``) decides which family of engines is allowed:

  saas      — the cloud-native engine for this appliance's cloud
              (``CNA_APPLIANCE_CLOUD``): ``azure-openai`` on Azure (Azure
              OpenAI via managed identity — DefaultAzureCredential bearer
              token, same scope as lib/ai-engine.ts getAzureClient()), or
              ``bedrock`` on AWS (Bedrock Converse via the task role).
  byo-api   — bring-your-own provider: ``anthropic`` and/or ``openai``,
              authenticated with an API key the admin entered on the AI Engine
              page. Keys live AES-256-GCM encrypted in the AppSetting table
              (see cna.core.credential_crypto) and are passed in already
              decrypted by the caller (apps/cna-api/routers/chat.py).

Resolution (byo-api): exactly one key configured → that provider is active
regardless of the stored setting; both configured → the stored
``ai.activeEngine`` wins, then ``CNA_AI_ENGINE_DEFAULT``, then ``anthropic``;
none → ChatConfigError (503). A stored value from another mode is skipped,
never fatal.

Transports use the official SDKs (``anthropic``, ``openai``, ``boto3``) with
their own retries disabled so tenacity — already a platform dependency,
mirroring cna/core/throttle.py — is the single retry layer. Azure OpenAI stays
on httpx to keep its wire format byte-identical to the web tier.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping

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
ENGINE_AZURE_OPENAI = "azure-openai"
ENGINE_BEDROCK = "bedrock"
ENGINE_ANTHROPIC = "anthropic"
ENGINE_OPENAI = "openai"
VALID_ENGINES = {ENGINE_AZURE_OPENAI, ENGINE_BEDROCK, ENGINE_ANTHROPIC, ENGINE_OPENAI}

# Deploy-time AI mode + appliance cloud (env contract set by Terraform)
MODE_SAAS = "saas"
MODE_BYO_API = "byo-api"
CLOUD_AZURE = "azure"
CLOUD_AWS = "aws"
SAAS_ENGINE_BY_CLOUD = {CLOUD_AZURE: ENGINE_AZURE_OPENAI, CLOUD_AWS: ENGINE_BEDROCK}
# Ordered: the first entry is the deterministic tie-break when both are
# configured and neither the stored setting nor the env default applies.
BYO_ENGINES = (ENGINE_ANTHROPIC, ENGINE_OPENAI)

DEFAULT_AZURE_DEPLOYMENT = "gpt-chat-latest"
DEFAULT_AZURE_API_VERSION = "2024-12-01-preview"
# Model ids are overridable per provider (AppSetting ai.byo.<provider>.model,
# then env) so a deployment never has to edit code to move models.
DEFAULT_ANTHROPIC_MODEL = "claude-opus-5"
DEFAULT_OPENAI_MODEL = "gpt-5.4"
ANTHROPIC_MODEL_ENV = "CNA_ANTHROPIC_MODEL"
OPENAI_MODEL_ENV = "CNA_OPENAI_MODEL"
BEDROCK_MODEL_ENV = "CNA_BEDROCK_MODEL_ID"
BEDROCK_PROFILE_ENV = "CNA_BEDROCK_INFERENCE_PROFILE_ARN"

MAX_COMPLETION_TOKENS = 1200
REQUEST_TIMEOUT_SECONDS = 60.0

# Token budget for the grounding block (≈4 chars per token heuristic)
DEFAULT_CONTEXT_TOKEN_BUDGET = 6000
_CHARS_PER_TOKEN = 4

# Severity sort order for top-N finding selection
_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFORMATIONAL": 4}

# Same rule-id pattern as cna/core/stat_masters.py
_RULE_ID_RE = re.compile(r"\b([A-Z]{2,5}-[A-Z]{2,10}-\d{1,4})\b")

_BOTO_TRANSIENT_CODES = {
    "ThrottlingException",
    "TooManyRequestsException",
    "ServiceUnavailableException",
    "InternalServerException",
    "ModelNotReadyException",
}


class ChatConfigError(Exception):
    """Raised when no AI engine is configured. Routers map this to 503."""


def _clean(value: str | None) -> str:
    """Mirror lib/ai-engine.ts clean(): trim, treat 'none' as unset."""
    trimmed = (value or "").strip()
    return "" if trimmed.lower() == "none" else trimmed


def resolve_ai_mode(value: str | None = None) -> str:
    """Normalise the AI mode (argument, else env CNA_AI_MODE). Unset ⇒ saas."""
    mode = _clean(value if value is not None else os.environ.get("CNA_AI_MODE"))
    return MODE_BYO_API if mode == MODE_BYO_API else MODE_SAAS


def resolve_appliance_cloud(value: str | None = None) -> str:
    """Normalise the appliance cloud (argument, else env). Unset ⇒ azure."""
    cloud = _clean(value if value is not None else os.environ.get("CNA_APPLIANCE_CLOUD"))
    return CLOUD_AWS if cloud == CLOUD_AWS else CLOUD_AZURE


def allowed_engines(mode: str, cloud: str) -> tuple[str, ...]:
    """Engines the current mode permits — mirrors allowedEngines() in ai-engine.ts."""
    if mode == MODE_BYO_API:
        return BYO_ENGINES
    return (SAAS_ENGINE_BY_CLOUD[resolve_appliance_cloud(cloud)],)


def engine_configured(engine: str, byo_keys: Mapping[str, str | None] | None = None) -> bool:
    """Whether the engine can be used right now (parity with getAiEngineStatuses()
    configured flags). SaaS engines read env; BYO engines need a decrypted key."""
    if engine == ENGINE_AZURE_OPENAI:
        return bool(_clean(os.environ.get("AZURE_OPENAI_ENDPOINT")))
    if engine == ENGINE_BEDROCK:
        return bool(
            _clean(os.environ.get(BEDROCK_PROFILE_ENV)) or _clean(os.environ.get(BEDROCK_MODEL_ENV))
        )
    if engine in BYO_ENGINES:
        return bool(_clean((byo_keys or {}).get(engine)))
    return False


def resolve_engine(
    stored_engine: str | None = None,
    *,
    mode: str | None = None,
    cloud: str | None = None,
    configured: set[str] | frozenset[str] | None = None,
) -> str:
    """Resolve the active engine id.

    Mirrors getActiveAiEngine() in lib/ai-engine.ts:

    * saas — the single engine allowed for this cloud. Stored/env preferences
      are irrelevant (one engine per appliance); configuration is checked by
      the caller, which raises ChatConfigError when it is missing.
    * byo-api — among the configured BYO engines: one ⇒ it wins outright;
      two ⇒ stored AppSetting, then CNA_AI_ENGINE_DEFAULT, then the first of
      BYO_ENGINES; none ⇒ ChatConfigError.

    A stored value that is not allowed in the current mode is ignored.
    """
    resolved_mode = resolve_ai_mode(mode)
    allowed = allowed_engines(resolved_mode, resolve_appliance_cloud(cloud))

    if resolved_mode == MODE_SAAS:
        return allowed[0]

    if configured is None:
        configured = {e for e in VALID_ENGINES if engine_configured(e)}
    candidates = [e for e in allowed if e in configured]
    if not candidates:
        raise ChatConfigError(
            "No bring-your-own AI API key is configured. Add an Anthropic or OpenAI "
            "key on the admin AI Engine page."
        )
    if len(candidates) == 1:
        return candidates[0]

    stored = _clean(stored_engine)
    if stored in candidates:
        return stored
    env_default = _clean(os.environ.get("CNA_AI_ENGINE_DEFAULT"))
    if env_default in candidates:
        return env_default
    return candidates[0]


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
# Transport
# ---------------------------------------------------------------------------


def _is_transient(exc: BaseException) -> bool:
    """Retry on throttling, 5xx and connection/timeout failures.

    Covers httpx (Azure OpenAI), the anthropic/openai SDKs (both expose
    ``status_code`` on status errors and use the APIConnectionError /
    APITimeoutError class names) and botocore ClientError (Bedrock).
    """
    if isinstance(exc, httpx.TransportError | httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == _HTTP_TOO_MANY_REQUESTS or status >= _HTTP_SERVER_ERROR
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code == _HTTP_TOO_MANY_REQUESTS or status_code >= _HTTP_SERVER_ERROR
    if type(exc).__name__ in {"APIConnectionError", "APITimeoutError"}:
        return True
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        return response.get("Error", {}).get("Code") in _BOTO_TRANSIENT_CODES
    return False


_transport_retry = retry(
    retry=retry_if_exception(_is_transient),
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1.0, max=15.0),
    reraise=True,
)


class GroundedChatAgent:
    """Stateless grounded Q&A over a single engagement's assessment data."""

    def __init__(
        self,
        engine: str | None = None,
        *,
        byo_keys: Mapping[str, str | None] | None = None,
        byo_models: Mapping[str, str | None] | None = None,
        mode: str | None = None,
        cloud: str | None = None,
    ):
        self.mode = resolve_ai_mode(mode)
        self.cloud = resolve_appliance_cloud(cloud)
        self._byo_keys = {k: _clean(v) for k, v in (byo_keys or {}).items()}
        self._byo_models = {k: _clean(v) for k, v in (byo_models or {}).items()}

        configured = {e for e in VALID_ENGINES if engine_configured(e, self._byo_keys)}
        self.engine = resolve_engine(
            engine, mode=self.mode, cloud=self.cloud, configured=configured
        )
        if self.engine not in configured:
            raise ChatConfigError(self._unconfigured_message(self.engine))

    @staticmethod
    def _unconfigured_message(engine: str) -> str:
        if engine == ENGINE_AZURE_OPENAI:
            return (
                "Azure OpenAI is not configured. Set AZURE_OPENAI_ENDPOINT before running analysis."
            )
        if engine == ENGINE_BEDROCK:
            return (
                f"Bedrock is not configured. Set {BEDROCK_MODEL_ENV} (or "
                f"{BEDROCK_PROFILE_ENV}) before running analysis."
            )
        return f"{engine} has no API key configured. Add one on the admin AI Engine page."

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

        if self.engine == ENGINE_ANTHROPIC:
            text = self._complete_anthropic(system_prompt, turns)
        elif self.engine == ENGINE_OPENAI:
            text = self._complete_openai(system_prompt, turns)
        elif self.engine == ENGINE_BEDROCK:
            text = self._complete_bedrock(system_prompt, turns)
        else:
            text = self._complete_azure(system_prompt, turns)

        return ChatAnswer(
            text=text,
            citations=extract_citations(text, context),
            engine=self.engine,
        )

    # --------------------------------------------------------- azure openai

    @_transport_retry
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

    # -------------------------------------------------------------- bedrock

    @_transport_retry
    def _complete_bedrock(self, system_prompt: str, turns: list[dict]) -> str:
        """Bedrock Converse via the appliance's task role (boto3 default chain).
        An inference profile ARN takes precedence over a bare model id, matching
        the aws/ai Terraform module which bills through the profile."""
        model_id = _clean(os.environ.get(BEDROCK_PROFILE_ENV)) or _clean(
            os.environ.get(BEDROCK_MODEL_ENV)
        )
        if not model_id:
            raise ChatConfigError(self._unconfigured_message(ENGINE_BEDROCK))

        import boto3

        client = boto3.client("bedrock-runtime")
        response = client.converse(
            modelId=model_id,
            system=[{"text": system_prompt}],
            messages=[{"role": t["role"], "content": [{"text": t["content"]}]} for t in turns],
            inferenceConfig={"maxTokens": MAX_COMPLETION_TOKENS},
        )
        content = response.get("output", {}).get("message", {}).get("content", [])
        return "".join(block.get("text", "") for block in content)

    # ------------------------------------------------------------ anthropic

    def _byo_model(self, provider: str, env_name: str, default: str) -> str:
        return self._byo_models.get(provider) or _clean(os.environ.get(env_name)) or default

    @_transport_retry
    def _complete_anthropic(self, system_prompt: str, turns: list[dict]) -> str:
        """Anthropic Messages API with the admin-entered key. Thinking is left at
        the model's adaptive default; a safety refusal is surfaced as text rather
        than treated as a transport failure."""
        api_key = self._byo_keys.get(ENGINE_ANTHROPIC)
        if not api_key:
            raise ChatConfigError(self._unconfigured_message(ENGINE_ANTHROPIC))

        import anthropic

        client = anthropic.Anthropic(
            api_key=api_key, max_retries=0, timeout=REQUEST_TIMEOUT_SECONDS
        )
        response = client.messages.create(
            model=self._byo_model(ENGINE_ANTHROPIC, ANTHROPIC_MODEL_ENV, DEFAULT_ANTHROPIC_MODEL),
            max_tokens=MAX_COMPLETION_TOKENS,
            system=system_prompt,
            messages=turns,
        )
        if response.stop_reason == "refusal":
            logger.warning("anthropic refused the request (%s)", response.stop_details)
            return "The AI provider declined to answer this request."
        return "".join(block.text for block in response.content if block.type == "text")

    # --------------------------------------------------------------- openai

    @_transport_retry
    def _complete_openai(self, system_prompt: str, turns: list[dict]) -> str:
        """OpenAI chat completions (api.openai.com) with the admin-entered key —
        same request shape as the Azure path, minus the deployment routing."""
        api_key = self._byo_keys.get(ENGINE_OPENAI)
        if not api_key:
            raise ChatConfigError(self._unconfigured_message(ENGINE_OPENAI))

        from openai import OpenAI

        client = OpenAI(api_key=api_key, max_retries=0, timeout=REQUEST_TIMEOUT_SECONDS)
        response = client.chat.completions.create(
            model=self._byo_model(ENGINE_OPENAI, OPENAI_MODEL_ENV, DEFAULT_OPENAI_MODEL),
            messages=[{"role": "system", "content": system_prompt}, *turns],
            max_completion_tokens=MAX_COMPLETION_TOKENS,
        )
        choices = response.choices or []
        return (choices[0].message.content or "") if choices else ""


__all__ = [
    "BYO_ENGINES",
    "CLOUD_AWS",
    "CLOUD_AZURE",
    "ENGINE_ANTHROPIC",
    "ENGINE_AZURE_OPENAI",
    "ENGINE_BEDROCK",
    "ENGINE_OPENAI",
    "MODE_BYO_API",
    "MODE_SAAS",
    "VALID_ENGINES",
    "ChatAnswer",
    "ChatConfigError",
    "Citation",
    "GroundedChatAgent",
    "GroundingContext",
    "allowed_engines",
    "build_grounding_context",
    "build_system_prompt",
    "engine_configured",
    "extract_citations",
    "resolve_ai_mode",
    "resolve_appliance_cloud",
    "resolve_engine",
]
