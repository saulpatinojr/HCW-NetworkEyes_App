"""Unit tests for the grounded chat copilot agent (Phase G).

No real LLM calls — transport is monkeypatched. Covers grounding-context
building/truncation, prompt assembly, citation extraction, engine
resolution, and the answer() flow end-to-end with a fake Azure OpenAI response.
"""

import httpx
import pytest

from cna.ai_engine.chat_agent import (
    ChatConfigError,
    GroundedChatAgent,
    GroundingContext,
    build_grounding_context,
    build_system_prompt,
    extract_citations,
    resolve_engine,
)

ENG = "eng-123"


def _finding(**overrides) -> dict:
    base = {
        "id": "f-1",
        "title": "Subnet has no Network Security Group (AZ-NET-002)",
        "severity": "HIGH",
        "category": "Segmentation",
        "description": "Subnet snet-app has no NSG attached.",
        "trafficDirection": "east_west",
        "region": "eastus",
        "resourceType": "Microsoft.Network/virtualNetworks/subnets",
        "estCostImpact": None,
        "resource_id": "snet-app",
    }
    base.update(overrides)
    return base


# ── grounding context ────────────────────────────────────────────────────────


def test_context_sorts_by_severity():
    findings = [
        _finding(id="f-low", severity="LOW", title="Low one (AZ-NET-001)"),
        _finding(id="f-crit", severity="CRITICAL", title="Crit one (AZ-NET-003)"),
        _finding(id="f-med", severity="MEDIUM", title="Med one (AZ-NET-014)"),
    ]
    ctx = build_grounding_context(ENG, findings)
    assert [f.finding_id for f in ctx.findings] == ["f-crit", "f-med", "f-low"]
    assert ctx.total_finding_count == 3
    assert not ctx.truncated


def test_context_extracts_rule_id_from_title():
    ctx = build_grounding_context(ENG, [_finding()])
    assert ctx.findings[0].rule_id == "AZ-NET-002"


def test_context_token_budget_truncates_lower_severity():
    findings = [
        _finding(id=f"f-{i}", severity="LOW", description="x" * 500, title=f"Low (AZ-NET-0{i:02d})")
        for i in range(50)
    ]
    findings.append(_finding(id="f-crit", severity="CRITICAL", title="Crit (AZ-NET-003)"))
    ctx = build_grounding_context(ENG, findings, token_budget=500)
    assert ctx.truncated
    assert len(ctx.findings) < 51
    # the critical finding survives truncation (sorted first)
    assert ctx.findings[0].finding_id == "f-crit"


def test_context_keeps_at_least_one_finding():
    ctx = build_grounding_context(ENG, [_finding(description="x" * 9000)], token_budget=1)
    assert len(ctx.findings) == 1


# ── prompt assembly ──────────────────────────────────────────────────────────


def test_system_prompt_embeds_context():
    ctx = build_grounding_context(
        ENG,
        [_finding()],
        stat_summary={"findings_by_severity": {"HIGH": 1}},
        topology_pattern="hub_spoke",
        topology_rationale="1 hub VNet identified.",
    )
    prompt = build_system_prompt(ctx)
    assert ENG in prompt
    assert "hub_spoke" in prompt
    assert "AZ-NET-002" in prompt
    assert "snet-app" in prompt
    assert "findings_by_severity" in prompt
    assert "Answer ONLY from the assessment context" in prompt
    assert "refuse questions outside" in prompt


def test_system_prompt_empty_findings():
    prompt = build_system_prompt(GroundingContext(engagement_id=ENG))
    assert "(no findings recorded for this engagement)" in prompt


# ── citations ────────────────────────────────────────────────────────────────


def test_extract_citations_maps_rule_ids():
    ctx = build_grounding_context(ENG, [_finding()])
    citations = extract_citations(
        "Subnet **AZ-NET-002** lacks an NSG; AZ-NET-999 is not in context.", ctx
    )
    assert len(citations) == 1
    assert citations[0].rule_id == "AZ-NET-002"
    assert citations[0].resource_id == "snet-app"
    assert citations[0].finding_id == "f-1"


def test_extract_citations_dedupes():
    ctx = build_grounding_context(ENG, [_finding(), _finding(id="f-2")])
    citations = extract_citations("AZ-NET-002 mentioned twice: AZ-NET-002.", ctx)
    assert len(citations) == 1


# ── engine resolution ────────────────────────────────────────────────────────


def test_resolve_engine_prefers_stored_value(monkeypatch):
    monkeypatch.setenv("CNA_AI_ENGINE_DEFAULT", "azure-openai")
    # azure-openai is now the only valid engine; the retired foundry-claude id
    # is rejected and falls through to the env default.
    assert resolve_engine("azure-openai") == "azure-openai"
    assert resolve_engine("foundry-claude") == "azure-openai"
    assert resolve_engine("bogus") == "azure-openai"
    monkeypatch.delenv("CNA_AI_ENGINE_DEFAULT")
    assert resolve_engine(None) == "azure-openai"


def test_agent_raises_config_error_when_nothing_configured(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    with pytest.raises(ChatConfigError):
        GroundedChatAgent()


# ── answer() with mocked Azure OpenAI transport ──────────────────────────────


class _FakeToken:
    token = "fake-aad-token"


class _FakeCredential:
    def get_token(self, *_scopes):
        return _FakeToken()


def test_answer_grounded_via_mocked_azure_openai(monkeypatch):
    import azure.identity

    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://aif.example")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-chat-latest")
    monkeypatch.setattr(azure.identity, "DefaultAzureCredential", _FakeCredential)

    captured: dict = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Fix AZ-NET-002 on snet-app."}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    ctx = build_grounding_context(ENG, [_finding()])
    agent = GroundedChatAgent()
    result = agent.answer(
        [{"role": "system", "content": "ignored"}, {"role": "user", "content": "What is risky?"}],
        ctx,
    )

    assert result.text == "Fix AZ-NET-002 on snet-app."
    assert result.engine == "azure-openai"
    assert [c.rule_id for c in result.citations] == ["AZ-NET-002"]

    # wire format mirrors lib/ai-engine.ts completeWithAzure
    assert captured["url"] == (
        "https://aif.example/openai/deployments/gpt-chat-latest"
        "/chat/completions?api-version=2024-12-01-preview"
    )
    assert captured["headers"]["Authorization"] == "Bearer fake-aad-token"
    body = captured["json"]
    # the grounded system prompt is the first message
    assert body["messages"][0]["role"] == "system"
    assert "Answer ONLY from the assessment context" in body["messages"][0]["content"]
    # client-side system turns are excluded from the user/assistant turns
    assert all(m["role"] in ("user", "assistant") for m in body["messages"][1:])
    assert body["messages"][-1]["content"] == "What is risky?"
