"""Unit tests for findings schema (DD-002)."""

from cna.core.findings_schema import Finding, FrameworkMapping


def test_finding_requires_observed_state():
    """observed_state is required — no assumptions allowed."""
    f = Finding(
        id="F-001",
        severity="critical",
        platform="aws",
        region="us-east-1",
        category="network",
        title="SSH exposed",
        description="Security group allows 0.0.0.0/0 on port 22",
        observed_state="IngressRule: protocol=tcp, port=22, cidr=0.0.0.0/0",
        framework_mappings=[
            FrameworkMapping(
                framework="CIS AWS Foundations Benchmark",
                version="3.0",
                control_id="5.1",
                control_name="Ensure no security groups allow ingress from 0.0.0.0/0 to SSH",
                alignment="Gap",
            )
        ],
    )
    assert f.observed_state != ""
    assert len(f.framework_mappings) >= 1


def test_finding_not_human_reviewed_by_default():
    """Findings start unreviewed — review gate must be explicit (DD-009)."""
    f = Finding(
        id="F-002",
        severity="high",
        platform="azure",
        region="us",
        category="security",
        title="NSG any-any",
        description="NSG allows all inbound traffic",
        observed_state="SecurityRule: direction=Inbound, access=Allow, source=*, dest=*",
    )
    assert f.human_reviewed is False


def test_finding_data_confidence_default():
    f = Finding(
        id="F-003",
        severity="medium",
        platform="aws",
        region="us-east-1",
        category="network",
        title="Test",
        description="Test",
        observed_state="Test observed state",
    )
    assert f.data_confidence == "HIGH"
