"""Unit tests for cna.ai_engine.recommendation_engine."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from cna.ai_engine.recommendation_engine import RecommendationEngine
from cna.core.findings_schema import (
    Finding,
    FindingRecommendation,
    FindingsReport,
    FrameworkMapping,
)

# ── Fixtures ───────────────────────────────────────────────────────────────────


def _make_finding(
    rule_id: str = "AWS-NET-001",
    resource_type: str = "AWS::EC2::VPC",
    severity: str = "high",
) -> Finding:
    return Finding(
        id=f"F-{rule_id}",
        rule_id=rule_id,
        severity=severity,
        platform="aws",
        region="us-east-1",
        category="network",
        title=f"Test finding {rule_id}",
        description="Test description",
        resource_id="vpc-001",
        resource_type=resource_type,
        account_id="123456789012",
        observed_state="VPC: is_default=True",
        framework_mappings=[
            FrameworkMapping(
                framework="AWS Well-Architected",
                version="2024",
                control_id="REL-01",
                control_name="VPC design",
                alignment="Gap",
            )
        ],
    )


def _make_report(findings=None) -> FindingsReport:
    findings = findings if findings is not None else [_make_finding()]
    return FindingsReport(
        engagement_id="eng-test-001",
        findings=findings,
        total_count=len(findings),
        critical_count=sum(1 for f in findings if f.severity == "critical"),
        high_count=sum(1 for f in findings if f.severity == "high"),
        medium_count=sum(1 for f in findings if f.severity == "medium"),
        low_count=sum(1 for f in findings if f.severity == "low"),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


# ── Offline fallback library ───────────────────────────────────────────────────


class TestOfflineFallback:
    def test_returns_list_for_known_rule(self):
        recs = RecommendationEngine._offline_fallback("AWS-NET-001")
        assert len(recs) >= 1
        assert isinstance(recs[0], FindingRecommendation)

    def test_returns_generic_for_unknown_rule(self):
        recs = RecommendationEngine._offline_fallback("UNKNOWN-RULE-999")
        assert len(recs) == 1
        assert recs[0].source == "CNA Platform"
        assert "MCP server was unavailable" in recs[0].text

    def test_all_known_aws_rules_have_recs(self):
        known_rules = [
            "AWS-NET-001",
            "AWS-NET-002",
            "AWS-NET-003",
            "AWS-NET-004",
            "AWS-NET-006",
            "AWS-NET-008",
        ]
        for rule_id in known_rules:
            recs = RecommendationEngine._offline_fallback(rule_id)
            assert len(recs) >= 1, f"No offline recs for {rule_id}"

    def test_all_known_azure_rules_have_recs(self):
        known_rules = ["AZ-NET-001", "AZ-NET-002", "AZ-NET-003", "AZ-NET-007"]
        for rule_id in known_rules:
            recs = RecommendationEngine._offline_fallback(rule_id)
            assert len(recs) >= 1, f"No offline recs for {rule_id}"

    def test_all_offline_recs_have_source_and_text(self):
        for rule_id in ["AWS-NET-001", "AZ-NET-001"]:
            for rec in RecommendationEngine._offline_fallback(rule_id):
                assert rec.source
                assert rec.text


# ── RecommendationEngine.enrich ────────────────────────────────────────────────


class TestRecommendationEngineEnrich:
    def test_enrich_calls_router_per_finding(self):
        router = MagicMock()
        router.get_recommendations.return_value = [
            FindingRecommendation(
                source="mcp-test",
                text="Recommendation text",
                reference_url="https://example.com",
            )
        ]
        engine = RecommendationEngine(router=router)
        report = _make_report(findings=[_make_finding("AWS-NET-001"), _make_finding("AWS-NET-002")])
        engine.enrich(report)
        assert router.get_recommendations.call_count == 2

    def test_enrich_injects_recommendations_into_findings(self):
        router = MagicMock()
        router.get_recommendations.return_value = [
            FindingRecommendation(
                source="mcp-test",
                text="Delete default VPCs",
                reference_url="https://docs.aws.amazon.com",
            )
        ]
        engine = RecommendationEngine(router=router)
        report = _make_report()
        result = engine.enrich(report)
        assert len(result.findings[0].recommendations) == 1
        assert result.findings[0].recommendations[0].text == "Delete default VPCs"

    def test_enrich_falls_back_offline_when_router_raises(self):
        router = MagicMock()
        router.get_recommendations.side_effect = RuntimeError("MCP down")
        engine = RecommendationEngine(router=router)
        report = _make_report(findings=[_make_finding("AWS-NET-001")])
        result = engine.enrich(report)
        # Must use offline fallback — not crash
        assert len(result.findings[0].recommendations) >= 1
        # Offline fallback for AWS-NET-001 is a proper recommendation
        assert result.findings[0].recommendations[0].source != ""

    def test_enrich_returns_same_report_object(self):
        router = MagicMock()
        router.get_recommendations.return_value = []
        engine = RecommendationEngine(router=router)
        report = _make_report()
        result = engine.enrich(report)
        assert result is report  # in-place modification, returns same object

    def test_enrich_empty_report(self):
        router = MagicMock()
        engine = RecommendationEngine(router=router)
        report = _make_report(findings=[])
        result = engine.enrich(report)
        assert result.findings == []
        router.get_recommendations.assert_not_called()

    def test_cloud_routing_aws_by_resource_type(self):
        router = MagicMock()
        router.get_recommendations.return_value = []
        engine = RecommendationEngine(router=router)
        report = _make_report(findings=[_make_finding(resource_type="AWS::EC2::VPC")])
        engine.enrich(report)
        call_kwargs = router.get_recommendations.call_args[1]
        assert call_kwargs["cloud"] == "aws"

    def test_cloud_routing_azure_by_resource_type(self):
        router = MagicMock()
        router.get_recommendations.return_value = []
        engine = RecommendationEngine(router=router)
        report = _make_report(
            findings=[_make_finding(resource_type="Microsoft.Network/virtualNetworks")]
        )
        engine.enrich(report)
        call_kwargs = router.get_recommendations.call_args[1]
        assert call_kwargs["cloud"] == "azure"

    def test_cloud_routing_by_slash_prefix(self):
        router = MagicMock()
        router.get_recommendations.return_value = []
        engine = RecommendationEngine(router=router)
        # resource_type with cloud prefix separated by slash
        finding = _make_finding(resource_type="aws/ec2/vpc")
        report = _make_report(findings=[finding])
        engine.enrich(report)
        call_kwargs = router.get_recommendations.call_args[1]
        assert call_kwargs["cloud"] == "aws"
