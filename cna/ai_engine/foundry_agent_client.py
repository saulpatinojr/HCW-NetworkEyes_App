"""Foundry Agent client — recommendation enrichment via Azure AI Foundry Agent Service.

Routes a finding to a **portal-configured** Foundry agent that has MCP tools (Azure MCP,
AWS MCP, Microsoft Learn, optionally web search) and answer-style *instructions* attached.
The agent reasons over the finding, calls the MCP tools server-side, and returns a strict
JSON array of vendor recommendations, which this client parses into
``FindingRecommendation`` objects.

This is an alternative transport to ``cna.ai_engine.mcp_client.MCPRouter`` — the agent +
its tools + its instructions all live in the Foundry portal; CNA only references the agent
by id. See docs/adr/0001 (Azure OpenAI on the same account) and the plan for context.

Config (env):
  FOUNDRY_PROJECT_ENDPOINT        — the Foundry project endpoint
  FOUNDRY_RECOMMENDATION_AGENT_ID — the portal-created agent id

Auth: ``DefaultAzureCredential`` (managed identity in Azure — the same identity the rest
of the AI path uses). The identity needs the **Cognitive Services User** role on the
Foundry account (Microsoft documents "Azure AI User" for the agents API, but that role
does not exist in this tenant; Cognitive Services User's Microsoft.CognitiveServices/*
data actions are a superset that covers it — see the workload main.tf RBAC block).

Resilience: every failure path (unconfigured, SDK missing, run not completed, unparseable
output) raises ``FoundryAgentError`` so ``RecommendationEngine`` falls back to ``MCPRouter``
and then the curated offline library. The agent is never allowed to block enrichment.
"""

from __future__ import annotations

import json
import logging
import os
import re

from cna.core.findings_schema import FindingRecommendation

logger = logging.getLogger("cna.foundry_agent")

# Scope of a single enrichment run. Foundry MCP tool-calling can take a while; keep it
# bounded so a slow agent does not stall the whole report.
_RUN_TIMEOUT_SECONDS = 90


class FoundryAgentError(Exception):
    """Raised on any agent transport/parse failure so the caller can fall back."""


def _clean(value: str | None) -> str:
    """Mirror chat_agent._clean(): trim, treat 'none' as unset."""
    trimmed = (value or "").strip()
    return "" if trimmed.lower() == "none" else trimmed


def agent_configured() -> bool:
    """Whether both the project endpoint and the agent id are set."""
    return bool(
        _clean(os.environ.get("FOUNDRY_PROJECT_ENDPOINT"))
        and _clean(os.environ.get("FOUNDRY_RECOMMENDATION_AGENT_ID"))
    )


class FoundryAgentClient:
    """Calls a portal-configured Foundry recommendation agent for one finding at a time.

    Mirrors the ``get_recommendations`` contract of the MCP clients so it is a drop-in
    transport for ``RecommendationEngine``.
    """

    def __init__(self, endpoint: str | None = None, agent_id: str | None = None):
        self._endpoint = _clean(
            endpoint if endpoint is not None else os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
        )
        self._agent_id = _clean(
            agent_id if agent_id is not None else os.environ.get("FOUNDRY_RECOMMENDATION_AGENT_ID")
        )

    # ------------------------------------------------------------------ public

    def get_recommendations(
        self,
        cloud: str,
        rule_id: str,
        resource_type: str,
        finding_title: str,
    ) -> list[FindingRecommendation]:
        """Ask the Foundry agent for recommendations for one finding.

        Raises ``FoundryAgentError`` on any failure so the caller can fall back.
        """
        if not (self._endpoint and self._agent_id):
            raise FoundryAgentError("Foundry agent is not configured (endpoint/agent id missing).")
        prompt = self._build_prompt(cloud, rule_id, resource_type, finding_title)
        text = self._run(prompt)
        return self._parse(text)

    # ----------------------------------------------------------------- prompt

    @staticmethod
    def _build_prompt(cloud: str, rule_id: str, resource_type: str, finding_title: str) -> str:
        """Compact per-finding instruction. The agent's portal *instructions* own the
        persona, tool-use policy, and output contract; this only supplies the finding and
        restates the required shape as a guardrail."""
        return (
            "Provide vendor remediation recommendations for this cloud network finding.\n"
            f"- cloud: {cloud}\n"
            f"- rule_id: {rule_id}\n"
            f"- resource_type: {resource_type}\n"
            f"- finding_title: {finding_title}\n\n"
            "Use your attached tools to ground the guidance in authoritative sources. "
            "Return ONLY a JSON array (no prose, no code fences) of objects with the keys "
            '"source", "text", and "reference_url". Use a real, verifiable reference_url '
            "or an empty string — never invent one."
        )

    # ---------------------------------------------------------------- transport

    def _run(self, prompt: str) -> str:
        """Run the agent on a fresh thread and return the final assistant message text.

        Imports the SDK lazily (the rest of the platform does the same for
        azure.identity) so environments without azure-ai-projects degrade to fallback.
        """
        try:
            from azure.ai.projects import AIProjectClient
            from azure.identity import DefaultAzureCredential
        except ImportError as e:  # SDK not installed in this image
            raise FoundryAgentError(f"azure-ai-projects not available: {e}") from e

        project = None
        thread_id = None
        try:
            project = AIProjectClient(endpoint=self._endpoint, credential=DefaultAzureCredential())
            agents = project.agents
            thread = agents.threads.create()
            thread_id = thread.id
            agents.messages.create(thread_id=thread_id, role="user", content=prompt)
            run = agents.runs.create_and_process(
                thread_id=thread_id,
                agent_id=self._agent_id,
                timeout=_RUN_TIMEOUT_SECONDS,
            )
            status = str(getattr(run, "status", "")).lower()
            if status != "completed":
                raise FoundryAgentError(
                    f"agent run status={status or 'unknown'} error={getattr(run, 'last_error', None)}"
                )
            text = self._latest_assistant_text(agents, thread_id)
            if not text:
                raise FoundryAgentError("agent run completed but produced no assistant text.")
            return text
        except FoundryAgentError:
            raise
        except Exception as e:  # network, auth, SDK shape, etc.
            raise FoundryAgentError(f"Foundry agent run failed: {e}") from e
        finally:
            # Best-effort thread cleanup; never mask the real error.
            if project is not None and thread_id is not None:
                try:
                    project.agents.threads.delete(thread_id)
                except Exception:  # noqa: BLE001 — cleanup is best-effort
                    logger.debug("Could not delete Foundry thread %s", thread_id)

    @staticmethod
    def _latest_assistant_text(agents, thread_id: str) -> str:
        """Extract the most recent assistant message's text, tolerant of SDK shape."""
        messages = agents.messages.list(thread_id=thread_id, order="desc")
        for msg in messages:
            if getattr(msg, "role", None) != "assistant":
                continue
            # azure-ai-agents exposes text parts via .text_messages[].text.value
            parts = getattr(msg, "text_messages", None)
            if parts:
                joined = "\n".join(
                    p.text.value for p in parts if getattr(getattr(p, "text", None), "value", None)
                )
                if joined.strip():
                    return joined
            # Fallback: a plain .content string or list of content blocks
            content = getattr(msg, "content", None)
            if isinstance(content, str) and content.strip():
                return content
            if isinstance(content, list):
                joined = "\n".join(
                    getattr(getattr(c, "text", None), "value", "") or "" for c in content
                )
                if joined.strip():
                    return joined
        return ""

    # ------------------------------------------------------------------- parse

    @staticmethod
    def _parse(text: str) -> list[FindingRecommendation]:
        """Parse the agent's JSON array into FindingRecommendation objects.

        Tolerates a ```json code fence and surrounding whitespace. Raises
        ``FoundryAgentError`` on anything that is not a usable, non-empty list so the
        caller falls back rather than publishing junk.
        """
        cleaned = text.strip()
        # Strip a leading/trailing markdown code fence if the model added one.
        fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL)
        if fence:
            cleaned = fence.group(1).strip()
        try:
            data = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as e:
            raise FoundryAgentError(f"agent output was not valid JSON: {e}") from e

        if not isinstance(data, list):
            raise FoundryAgentError("agent output JSON was not a list of recommendations.")

        recs: list[FindingRecommendation] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            txt = str(item.get("text") or "").strip()
            if not txt:
                continue
            recs.append(
                FindingRecommendation(
                    source=str(item.get("source") or "Azure AI Foundry agent").strip(),
                    text=txt,
                    reference_url=str(item.get("reference_url") or "").strip(),
                )
            )
        if not recs:
            raise FoundryAgentError("agent returned no usable recommendations.")
        return recs


__all__ = ["FoundryAgentClient", "FoundryAgentError", "agent_configured"]
