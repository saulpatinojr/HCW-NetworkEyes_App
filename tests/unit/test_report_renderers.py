"""Unit tests for cna.report_engine.regional_report and presentation_deck."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from cna.core.findings_schema import Finding, FindingsReport, FrameworkMapping
from cna.report_engine.regional_report import RegionalReportRenderer

# ── Fixtures ───────────────────────────────────────────────────────────────────


def _make_finding(severity: str = "high", rule_id: str = "AWS-NET-001") -> Finding:
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
        resource_type="AWS::EC2::VPC",
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
    findings = (
        findings
        if findings is not None
        else [_make_finding("critical"), _make_finding("high", "AWS-NET-002")]
    )
    return FindingsReport(
        engagement_id="eng-test-001",
        findings=findings,
        total_count=len(findings),
        critical_count=sum(1 for f in findings if f.severity == "critical"),
        high_count=sum(1 for f in findings if f.severity == "high"),
        medium_count=sum(1 for f in findings if f.severity == "medium"),
        low_count=sum(1 for f in findings if f.severity == "low"),
        generated_at=datetime.now(UTC).isoformat(),
    )


# ── RegionalReportRenderer — constructor ───────────────────────────────────────


class TestRegionalReportRendererConstructor:
    def test_valid_language_en(self):
        renderer = RegionalReportRenderer(lang="en")
        assert renderer._lang == "en"

    def test_valid_language_ja(self):
        renderer = RegionalReportRenderer(lang="ja")
        assert renderer._lang == "ja"

    def test_case_insensitive_lang(self):
        renderer = RegionalReportRenderer(lang="EN")
        assert renderer._lang == "en"

    def test_invalid_language_raises(self):
        with pytest.raises(ValueError, match="Unsupported language"):
            RegionalReportRenderer(lang="fr")

    def test_custom_templates_dir(self, tmp_path):
        """Renderer must accept a custom templates dir (used in testing)."""
        # Create placeholder template files so Jinja2 doesn't error during construction
        (tmp_path / "regional_report_en.j2").write_text("{{ engagement_id }}")
        renderer = RegionalReportRenderer(lang="en", templates_dir=tmp_path)
        assert renderer._lang == "en"


# ── RegionalReportRenderer — JA gate ──────────────────────────────────────────


class TestRegionalReportJaGate:
    def test_ja_render_raises_without_review_flag(self, tmp_path):
        renderer = RegionalReportRenderer(lang="ja")
        report = _make_report()
        output = tmp_path / "report.html"
        with pytest.raises(Exception, match="ja_review_complete"):
            renderer.render(report, output, ja_review_complete=False)

    def test_ja_render_proceeds_with_review_flag(self, tmp_path):
        """When ja_review_complete=True, JA renderer should attempt template render."""

        # Provide a minimal JA template
        (tmp_path / "regional_report_ja.j2").write_text(
            "<html><body>{{ engagement_id }}</body></html>"
        )
        renderer = RegionalReportRenderer(lang="ja", templates_dir=tmp_path)
        report = _make_report()
        output = tmp_path / "report.html"
        result = renderer.render(report, output, ja_review_complete=True)
        assert result.exists()
        assert "eng-test-001" in result.read_text(encoding="utf-8")


# ── RegionalReportRenderer — HTML render ──────────────────────────────────────


class TestRegionalReportHTMLRender:
    def test_renders_html_file(self, tmp_path):
        (tmp_path / "regional_report_en.j2").write_text(
            "<html><body>{{ engagement_id }} - {{ total_count }} findings</body></html>",
            encoding="utf-8",
        )
        renderer = RegionalReportRenderer(lang="en", templates_dir=tmp_path)
        report = _make_report()
        output = tmp_path / "report.html"
        result = renderer.render(report, output)
        assert result.exists()
        content = result.read_text(encoding="utf-8")
        assert "eng-test-001" in content

    def test_html_file_written_when_pdf_requested_no_weasyprint(self, tmp_path):
        """When output is .pdf but WeasyPrint unavailable, falls back to .html."""
        (tmp_path / "regional_report_en.j2").write_text("<html>{{ engagement_id }}</html>")
        renderer = RegionalReportRenderer(lang="en", templates_dir=tmp_path)
        report = _make_report()
        pdf_output = tmp_path / "report.pdf"

        with patch.dict("sys.modules", {"weasyprint": None}):
            result = renderer.render(report, pdf_output)

        # Should return .html path as fallback
        assert result.suffix == ".html"
        assert result.exists()

    def test_build_context_includes_correct_counts(self):
        report = _make_report(
            findings=[
                _make_finding("critical"),
                _make_finding("critical", "AWS-NET-002"),
                _make_finding("high", "AWS-NET-003"),
            ]
        )
        context = RegionalReportRenderer._build_context(report)
        assert context["total_count"] == 3
        assert context["critical_count"] == 2
        assert context["high_count"] == 1
        assert context["medium_count"] == 0
        assert context["low_count"] == 0

    def test_build_context_critical_findings_filtered(self):
        critical_finding = _make_finding("critical")
        high_finding = _make_finding("high", "AWS-NET-002")
        report = _make_report(findings=[critical_finding, high_finding])
        context = RegionalReportRenderer._build_context(report)
        assert all(f.severity == "critical" for f in context["critical_findings"])
        assert len(context["critical_findings"]) == 1

    def test_build_context_all_findings_included(self):
        findings = [
            _make_finding("critical"),
            _make_finding("high", "AWS-NET-002"),
            _make_finding("medium", "AWS-NET-003"),
        ]
        report = _make_report(findings=findings)
        context = RegionalReportRenderer._build_context(report)
        assert len(context["all_findings"]) == 3

    def test_build_context_engagement_id_and_timestamp(self):
        report = _make_report()
        context = RegionalReportRenderer._build_context(report)
        assert context["engagement_id"] == "eng-test-001"
        assert context["generated_at"] is not None


# ── PresentationDeckBuilder ────────────────────────────────────────────────────


class TestPresentationDeckBuilder:
    def test_build_skips_gracefully_without_pptx(self, tmp_path):
        """python-pptx not installed → logs warning, returns path without crashing."""
        from cna.report_engine.presentation_deck import PresentationDeckBuilder

        with patch.dict("sys.modules", {"pptx": None, "pptx.util": None}):
            builder = PresentationDeckBuilder()
            report = _make_report()
            output = tmp_path / "deck.pptx"
            # Must not raise — returns output_path unchanged
            result = builder.build(report, output)
            assert result == output

    def test_build_with_pptx_installed(self, tmp_path):
        """When python-pptx is available, build() should produce a real .pptx file."""
        try:
            from pptx import Presentation  # noqa: F401
        except ImportError:
            pytest.skip("python-pptx not installed in this environment")

        from cna.report_engine.presentation_deck import PresentationDeckBuilder

        builder = PresentationDeckBuilder()
        report = _make_report(
            findings=[
                _make_finding("critical"),
                _make_finding("high", "AWS-NET-002"),
            ]
        )
        output = tmp_path / "deck.pptx"
        result = builder.build(report, output)
        assert result == output
        assert output.exists()
        assert output.stat().st_size > 0

    def test_build_with_empty_findings(self, tmp_path):
        """Empty report must not crash the builder."""
        try:
            from pptx import Presentation  # noqa: F401
        except ImportError:
            pytest.skip("python-pptx not installed in this environment")

        from cna.report_engine.presentation_deck import PresentationDeckBuilder

        builder = PresentationDeckBuilder()
        report = _make_report(findings=[])
        output = tmp_path / "deck_empty.pptx"
        result = builder.build(report, output)
        assert result == output
