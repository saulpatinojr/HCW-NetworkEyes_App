"""Phase E — HTML Preview Renderer.

Generates a self-contained HTML file from a FindingsReport.
Requires NO external PDF toolchain — safe for CI, air-gapped environments,
and pre-review workflow where a full PDF render is premature.

Design:
  - Single-file output: all CSS inlined, no external dependencies
  - Severity colour-coded finding cards
  - Framework mapping badges per finding
  - Recommendation text per finding
  - Collapsible sections via pure CSS (no JavaScript)
  - Print-ready: @media print styles included
"""

from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from cna.core.findings_schema import FindingSeverity, FindingsReport

logger = logging.getLogger("cna.report.preview")

_TEMPLATES_DIR = Path(__file__).parent / "templates"


class HtmlPreviewRenderer:
    """Renders a self-contained HTML preview. No external toolchain required."""

    def __init__(self, templates_dir: Path = _TEMPLATES_DIR):
        self._env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(["html", "j2"]),
        )

    def render(self, report: FindingsReport, output_path: Path) -> Path:
        """Render HTML preview to output_path. Returns path."""
        context = self._build_context(report)
        html = self._env.get_template("html_preview.j2").render(**context)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        logger.info("HTML preview written: %s", output_path)
        return output_path

    @staticmethod
    def _build_context(report: FindingsReport) -> dict:
        severity_order = {
            FindingSeverity.CRITICAL: 0,
            FindingSeverity.HIGH: 1,
            FindingSeverity.MEDIUM: 2,
            FindingSeverity.LOW: 3,
        }
        sorted_findings = sorted(report.findings, key=lambda f: severity_order.get(f.severity, 99))
        return {
            "engagement_id": report.engagement_id,
            "generated_at": report.generated_at,
            "schema_version": report.schema_version,
            "total_count": report.total_count,
            "critical_count": report.critical_count,
            "high_count": report.high_count,
            "medium_count": report.medium_count,
            "low_count": report.low_count,
            "findings": sorted_findings,
            "review_complete": report.review_complete,
        }
