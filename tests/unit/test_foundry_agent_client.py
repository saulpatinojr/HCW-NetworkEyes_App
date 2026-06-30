"""Unit tests for the Foundry recommendation agent client and the
RecommendationEngine fallback chain (agent -> MCP -> offline).

No live Foundry calls — the agent transport is injected/mocked. Covers JSON parsing
tolerance, configuration gating, and that enrichment degrades gracefully.
"""

import pytest

from cna.ai_engine.foundry_agent_client import (
    FoundryAgentClient,
    FoundryAgentError,
    agent_configured,
)
from cna.ai_engine.recommendation_engine import RecommendationEngine
from cna.core.findings_schema import Finding, FindingRecommendation, FindingsReport

# ── _parse tolerance ─────────────────────────────────────────────────────────


def test_parse_plain_json_array():
    recs = FoundryAgentClient._parse(
        '[{"source": "Azure WAF", "text": "Attach an NSG.", "reference_url": "https://x"}]'
    )
    assert len(recs) == 1
    assert recs[0].source == "Azure WAF"
    assert recs[0].text == "Attach an NSG."
    assert recs[0].reference_url == "https://x"


def test_parse_strips_code_fence():
    recs = FoundryAgentClient._parse(
        '```json\n[{"source": "CIS", "text": "Remove 0.0.0.0/0 SSH."}]\n```'
    )
    assert len(recs) == 1
    assert recs[0].reference_url == ""  # missing key -> empty default


def test_parse_skips_items_without_text():
    recs = FoundryAgentClient._parse(
        '[{"source": "x", "text": ""}, {"source": "y", "text": "Keep me."}]'
    )
    assert [r.text for r in recs] == ["Keep me."]


def test_parse_invalid_json_raises():
    with pytest.raises(FoundryAgentError):
        FoundryAgentClient._parse("not json at all")


def test_parse_non_list_raises():
    with pytest.raises(FoundryAgentError):
        FoundryAgentClient._parse('{"source": "x", "text": "y"}')


def test_parse_empty_list_raises():
    with pytest.raises(FoundryAgentError):
        FoundryAgentClient._parse("[]")


# ── configuration gating ─────────────────────────────────────────────────────


def test_agent_configured_requires_both(monkeypatch):
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    monkeypatch.delenv("FOUNDRY_RECOMMENDATION_AGENT_ID", raising=False)
    assert agent_configured() is False
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://proj.example")
    assert agent_configured() is False  # agent id still missing
    monkeypatch.setenv("FOUNDRY_RECOMMENDATION_AGENT_ID", "asst_123")
    assert agent_configured() is True
    # "none" sentinel is treated as unset
    monkeypatch.setenv("FOUNDRY_RECOMMENDATION_AGENT_ID", "none")
    assert agent_configured() is False


def test_get_recommendations_unconfigured_raises():
    client = FoundryAgentClient(endpoint="", agent_id="")
    with pytest.raises(FoundryAgentError):
        client.get_recommendations(
            cloud="azure", rule_id="AZ-NET-002", resource_type="Microsoft.Network/x", finding_title="t"
        )


# ── RecommendationEngine fallback chain ──────────────────────────────────────


def _report() -> FindingsReport:
    finding = Finding(
        rule_id="AZ-NET-002",
        severity="high",
        title="Subnet has no NSG",
        resource_type="Microsoft.Network/virtualNetworks/subnets",
        observed_state="snet-app has no NSG attached",
    )
    return FindingsReport(
        engagement_id="eng-1",
        findings=[finding],
        total_count=1,
        critical_count=0,
        high_count=1,
        medium_count=0,
        low_count=0,
        generated_at="2026-06-29T00:00:00Z",
    )


class _Stub:
    def __init__(self, *, recs=None, error=None):
        self._recs = recs or []
        self._error = error

    def get_recommendations(self, **_kwargs):
        if self._error is not None:
            raise self._error
        return self._recs


def test_agent_result_wins():
    agent = _Stub(recs=[FindingRecommendation(source="agent", text="do x")])
    router = _Stub(recs=[FindingRecommendation(source="mcp", text="do y")])
    report = RecommendationEngine(router=router, agent_client=agent).enrich(_report())
    assert [r.source for r in report.findings[0].recommendations] == ["agent"]


def test_agent_error_falls_back_to_mcp():
    agent = _Stub(error=FoundryAgentError("run failed"))
    router = _Stub(recs=[FindingRecommendation(source="mcp", text="do y")])
    report = RecommendationEngine(router=router, agent_client=agent).enrich(_report())
    assert [r.source for r in report.findings[0].recommendations] == ["mcp"]


def test_empty_everything_falls_back_to_offline():
    agent = _Stub(recs=[])  # agent yields nothing
    router = _Stub(recs=[])  # MCP yields nothing
    report = RecommendationEngine(router=router, agent_client=agent).enrich(_report())
    recs = report.findings[0].recommendations
    assert len(recs) >= 1
    # AZ-NET-002 has a curated offline entry
    assert any("NSG" in r.text for r in recs)
