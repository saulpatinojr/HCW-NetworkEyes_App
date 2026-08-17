"""Phase E — Technical Report Renderer.

Produces a full technical PDF from a reviewed FindingsReport.
Target audience: network engineers, security architects, cloud ops teams.

Content:
  - Cover page + table of contents
  - Methodology: discovery scope, tools, IAM roles used
  - All findings: full detail per finding (observed_state, evidence,
    framework mappings, recommendations)
  - Architecture diagram references (linked from Phase B output)
  - Discovery coverage table: every account/region/subscription scanned
  - Blocked resources table: every blocked account/region with reason
  - Appendix: full topology summary by account/subscription
"""

from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from cna.core.findings_schema import FindingSeverity, FindingsReport

logger = logging.getLogger("cna.report.technical")

_TEMPLATES_DIR = Path(__file__).parent / "templates"


class TechnicalReportRenderer:
    """Renders the full technical PDF report."""

    def __init__(self, templates_dir: Path = _TEMPLATES_DIR):
        self._env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(["html", "j2"]),
        )

    def render(self, report: FindingsReport, output_path: Path) -> Path:
        context = self._build_context(report)
        html = self._env.get_template("technical_report.j2").render(**context)

        html_path = output_path.with_suffix(".html")
        html_path.write_text(html, encoding="utf-8")

        if output_path.suffix == ".pdf":
            try:
                from weasyprint import HTML as WP

                WP(string=html, base_url=str(_TEMPLATES_DIR)).write_pdf(str(output_path))
                logger.info("Technical PDF written: %s", output_path)
            except ImportError:
                logger.warning(
                    "WeasyPrint not installed. Technical PDF skipped. HTML written to %s.",
                    html_path,
                )
                return html_path
        return output_path

    @staticmethod
    def _build_context(report: FindingsReport) -> dict:
        findings_by_severity = {
            "CRITICAL": [f for f in report.findings if f.severity == FindingSeverity.CRITICAL],
            "HIGH": [f for f in report.findings if f.severity == FindingSeverity.HIGH],
            "MEDIUM": [f for f in report.findings if f.severity == FindingSeverity.MEDIUM],
            "LOW": [f for f in report.findings if f.severity == FindingSeverity.LOW],
        }
        # Group by account/region for coverage tables
        # account_id is Optional; a single finding without one makes sorted()
        # raise "'<' not supported between 'str' and 'NoneType'".
        aws_accounts = sorted(
            {
                f.account_id
                for f in report.findings
                if (f.resource_type or "").startswith("AWS") and f.account_id
            }
        )
        azure_subscriptions = sorted(
            {
                f.account_id
                for f in report.findings
                if (f.resource_type or "").startswith("Microsoft") and f.account_id
            }
        )
        return {
            "engagement_id": report.engagement_id,
            "generated_at": report.generated_at,
            "schema_version": report.schema_version,
            "total_count": report.total_count,
            "critical_count": report.critical_count,
            "high_count": report.high_count,
            "medium_count": report.medium_count,
            "low_count": report.low_count,
            "findings_by_severity": findings_by_severity,
            "all_findings": report.findings,
            "aws_accounts": aws_accounts,
            "azure_subscriptions": azure_subscriptions,
        }
