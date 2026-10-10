"""Unit tests for Phase E Report Engine.

All rendering is tested in HTML-only mode (no WeasyPrint / python-pptx required).
Tests cover:
  - ReviewGateError raised when review_complete=False (DD-009)
  - JaReviewGateError raised when JA requested without ja_review_complete (DD-015)
  - HtmlPreviewRenderer produces valid HTML with all severity classes
  - HtmlPreviewRenderer works without review_complete (pre-review mode)
  - ExecutiveReportRenderer builds correct Jinja2 context
  - TechnicalReportRenderer groups findings by severity correctly
  - DeliverableManifest records and serialises correctly
  - DeliverableManifest.checksum is stable (same input = same SHA-256)
  - RenderPipeline writes manifest to store
  - Findings sorted by severity in HTML preview (CRITICAL first)
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from cna.core.findings_schema import (
    Finding,
    FindingSeverity,
    FindingsReport,
    FindingStatus,
    FrameworkMapping,
    ObservedState,
)
from cna.report_engine.deliverable_manifest import DeliverableManifest, DeliverableRecord
from cna.report_engine.executive_report import ExecutiveReportRenderer
from cna.report_engine.html_preview import HtmlPreviewRenderer
from cna.report_engine.render_pipeline import (
    JaReviewGateError,
    RenderOptions,
    RenderPipeline,
    ReviewGateError,
)
from cna.report_engine.technical_report import TechnicalReportRenderer


def _make_finding(rule_id: str, severity: FindingSeverity, resource_id: str = "r-001") -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=severity,
        resource_id=resource_id,
        resource_type="AWS::EC2::SecurityGroup",
        account_id="111111111111",
        region="us-east-1",
        title=f"Test finding {rule_id}",
        observed_state=ObservedState(
            fact=f"Resource {resource_id} has a misconfiguration.",
            evidence_ref="test:evidence",
        ),
        framework_mappings=[
            FrameworkMapping(framework="AWS WAF", pillar="Security", control="SEC 5")
        ],
        status=FindingStatus.OPEN,
    )


def _make_report(review_complete: bool = True) -> FindingsReport:
    findings = [
        _make_finding("AWS-NET-003", FindingSeverity.CRITICAL),
        _make_finding("AWS-NET-002", FindingSeverity.HIGH),
        _make_finding("AWS-NET-001", FindingSeverity.MEDIUM),
    ]
    return FindingsReport(
        engagement_id="test-20260305-e001",
        schema_version="1.0.0",
        findings=findings,
        total_count=len(findings),
        critical_count=1,
        high_count=1,
        medium_count=1,
        low_count=0,
        review_complete=review_complete,
        generated_at=datetime.now(UTC).isoformat(),
    )


@pytest.fixture
def store():
    s = MagicMock()
    s.engagement_id = "test-20260305-e001"
    return s


class TestReviewGate:
    def test_review_gate_blocks_render_when_not_reviewed(self, store, tmp_path):
        report = _make_report(review_complete=False)
        opts = RenderOptions(
            render_html_preview=True,
            render_executive=False,
            render_technical=False,
            render_pptx=False,
            render_regional_en=False,
            output_dir=tmp_path,
        )
        pipeline = RenderPipeline(store=store, options=opts)
        with pytest.raises(ReviewGateError):
            pipeline.run(report)

    def test_reviewed_report_passes_gate(self, store, tmp_path):
        report = _make_report(review_complete=True)
        opts = RenderOptions(
            render_html_preview=True,
            render_executive=False,
            render_technical=False,
            render_pptx=False,
            render_regional_en=False,
            output_dir=tmp_path,
        )
        pipeline = RenderPipeline(store=store, options=opts)
        # Should not raise
        manifest = pipeline.run(report)
        assert len(manifest.records) == 1

    def test_ja_gate_blocks_without_flag(self, store, tmp_path):
        report = _make_report(review_complete=True)
        opts = RenderOptions(
            render_html_preview=False,
            render_executive=False,
            render_technical=False,
            render_pptx=False,
            render_regional_en=False,
            render_regional_ja=True,
            ja_review_complete=False,  # NOT set
            output_dir=tmp_path,
        )
        pipeline = RenderPipeline(store=store, options=opts)
        with pytest.raises(JaReviewGateError):
            pipeline.run(report)


class TestHtmlPreview:
    def test_renders_without_review_complete(self, tmp_path):
        """HTML preview must work in pre-review mode."""
        report = _make_report(review_complete=False)
        renderer = HtmlPreviewRenderer()
        out = tmp_path / "preview.html"
        # HtmlPreviewRenderer does NOT check review_complete
        written = renderer.render(report=report, output_path=out)
        assert written.exists()
        content = written.read_text()
        assert "pre-review" in content.lower() or "Pre-review" in content

    def test_findings_sorted_critical_first(self, tmp_path):
        report = _make_report(review_complete=True)
        renderer = HtmlPreviewRenderer()
        out = tmp_path / "preview.html"
        renderer.render(report=report, output_path=out)
        content = out.read_text()
        # CRITICAL badge must appear before HIGH badge
        assert content.index("badge CRITICAL") < content.index("badge HIGH")

    def test_all_severity_classes_present(self, tmp_path):
        report = _make_report(review_complete=True)
        renderer = HtmlPreviewRenderer()
        out = tmp_path / "preview.html"
        renderer.render(report=report, output_path=out)
        content = out.read_text()
        for sev in ["CRITICAL", "HIGH", "MEDIUM"]:
            assert sev in content


class TestExecutiveReportContext:
    def test_context_counts_match_report(self):
        report = _make_report()
        ctx = ExecutiveReportRenderer._build_context(report)
        assert ctx["critical_count"] == 1
        assert ctx["high_count"] == 1
        assert ctx["medium_count"] == 1
        assert ctx["total_count"] == 3

    def test_top_priority_findings_are_critical_first(self):
        report = _make_report()
        ctx = ExecutiveReportRenderer._build_context(report)
        top = ctx["top_priority_findings"]
        assert top[0].severity == FindingSeverity.CRITICAL


class TestTechnicalReportContext:
    def test_findings_grouped_by_severity(self):
        report = _make_report()
        ctx = TechnicalReportRenderer._build_context(report)
        assert len(ctx["findings_by_severity"]["CRITICAL"]) == 1
        assert len(ctx["findings_by_severity"]["HIGH"]) == 1
        assert len(ctx["findings_by_severity"]["MEDIUM"]) == 1
        assert len(ctx["findings_by_severity"]["LOW"]) == 0

    def test_aws_accounts_extracted(self):
        report = _make_report()
        ctx = TechnicalReportRenderer._build_context(report)
        assert "111111111111" in ctx["aws_accounts"]


class TestDeliverableManifest:
    def test_manifest_serialises(self):
        m = DeliverableManifest(engagement_id="test-001")
        m.add(
            DeliverableRecord(
                label="Executive Report",
                path="/tmp/executive.html",
                format="html",
                lang="en",
            )
        )
        d = m.to_dict()
        assert d["total_deliverables"] == 1
        assert d["records"][0]["format"] == "html"

    def test_checksum_is_stable(self):
        data = '{"engagement_id": "test"}'
        c1 = DeliverableManifest.checksum(data)
        c2 = DeliverableManifest.checksum(data)
        assert c1 == c2
        assert len(c1) == 64  # SHA-256 hex digest

    def test_different_data_different_checksum(self):
        c1 = DeliverableManifest.checksum('{"a": 1}')
        c2 = DeliverableManifest.checksum('{"a": 2}')
        assert c1 != c2
