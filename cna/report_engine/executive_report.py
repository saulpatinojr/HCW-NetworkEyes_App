"""Phase E — Executive Report Renderer.

Produces a PDF executive report from a reviewed FindingsReport.
Target audience: C-suite, CISO, VP Engineering.

Content:
  - Cover page: client name, engagement date, CNA branding
  - Executive summary: scope, methodology, key findings by severity
  - Finding highlights: CRITICAL and HIGH findings, one paragraph each
  - Recommendations summary: top 5 prioritised by severity
  - Appendix A: discovery coverage (accounts/regions scanned, blocked)
  - Appendix B: framework mapping index

Rendering:
  HTML template (Jinja2) → PDF via WeasyPrint.
  If WeasyPrint is unavailable, writes HTML only and logs a warning.
  HTML output is always written regardless of PDF availability.
"""

from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from cna.core.findings_schema import FindingSeverity, FindingsReport

logger = logging.getLogger("cna.report.executive")

_TEMPLATES_DIR = Path(__file__).parent / "templates"


class ExecutiveReportRenderer:
    """Renders the executive PDF report."""

    def __init__(self, templates_dir: Path = _TEMPLATES_DIR):
        self._env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(["html", "j2"]),
        )

    def render(self, report: FindingsReport, output_path: Path) -> Path:
        """Render executive report to output_path (.pdf or .html).

        Returns path of written file.
        """
        context = self._build_context(report)
        html = self._env.get_template("executive_report.j2").render(**context)

        # Always write HTML sidecar
        html_path = output_path.with_suffix(".html")
        html_path.write_text(html, encoding="utf-8")

        # PDF via WeasyPrint (optional dependency)
        if output_path.suffix == ".pdf":
            try:
                from weasyprint import HTML as WP

                WP(string=html, base_url=str(_TEMPLATES_DIR)).write_pdf(str(output_path))
                logger.info("Executive PDF written: %s", output_path)
            except (ImportError, OSError):
                logger.warning(
                    "WeasyPrint not installed. PDF skipped. HTML written to %s. "
                    "Install with: pip install weasyprint",
                    html_path,
                )
                return html_path
        return output_path

    @staticmethod
    def _build_context(report: FindingsReport) -> dict:
        critical = [f for f in report.findings if f.severity == FindingSeverity.CRITICAL]
        high = [f for f in report.findings if f.severity == FindingSeverity.HIGH]
        medium = [f for f in report.findings if f.severity == FindingSeverity.MEDIUM]
        low = [f for f in report.findings if f.severity == FindingSeverity.LOW]

        # Top 5 prioritised recommendations: CRITICAL first, then HIGH
        top_findings = (critical + high)[:5]

        return {
            "engagement_id": report.engagement_id,
            "generated_at": report.generated_at,
            "schema_version": report.schema_version,
            "total_count": report.total_count,
            "critical_count": report.critical_count,
            "high_count": report.high_count,
            "medium_count": report.medium_count,
            "low_count": report.low_count,
            "critical_findings": critical,
            "high_findings": high,
            "medium_findings": medium,
            "low_findings": low,
            "top_priority_findings": top_findings,
            "all_findings": report.findings,
        }
