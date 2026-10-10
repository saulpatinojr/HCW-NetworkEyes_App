"""Phase E — Regional Report Renderer.

Produces localised PDF reports. Supported languages: EN, JA.

DD-015 enforcement:
  JA reports require ja_review_complete=True at the RenderPipeline level.
  This module raises JaReviewGateError as a second defence if called directly
  without the pipeline gate check.

Content (both languages):
  - Executive summary (localised)
  - All findings: title, severity, observed_state, recommendations
  - Framework mapping table
  - Remediation roadmap
"""

from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from cna.core.findings_schema import FindingSeverity, FindingsReport

logger = logging.getLogger("cna.report.regional")

_TEMPLATES_DIR = Path(__file__).parent / "templates"

_SUPPORTED_LANGS = {"en", "ja"}


class RegionalReportRenderer:
    """Renders localised regional reports (EN/JA)."""

    def __init__(self, lang: str = "en", templates_dir: Path = _TEMPLATES_DIR):
        lang = lang.lower()
        if lang not in _SUPPORTED_LANGS:
            raise ValueError(f"Unsupported language: {lang!r}. Supported: {_SUPPORTED_LANGS}")
        self._lang = lang
        self._env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(["html", "j2"]),
        )

    def render(
        self,
        report: FindingsReport,
        output_path: Path,
        ja_review_complete: bool = False,
    ) -> Path:
        """Render regional report. JA requires ja_review_complete=True (DD-015)."""
        if self._lang == "ja" and not ja_review_complete:
            from cna.report_engine.render_pipeline import JaReviewGateError

            raise JaReviewGateError(
                "JA regional report render attempted without native speaker review. "
                "Set ja_review_complete=True only after native speaker sign-off."
            )

        template_name = f"regional_report_{self._lang}.j2"
        context = self._build_context(report)
        html = self._env.get_template(template_name).render(**context)

        html_path = output_path.with_suffix(".html")
        html_path.write_text(html, encoding="utf-8")

        if output_path.suffix == ".pdf":
            try:
                from weasyprint import HTML as WP

                WP(string=html, base_url=str(_TEMPLATES_DIR)).write_pdf(str(output_path))
                logger.info("Regional %s PDF written: %s", self._lang.upper(), output_path)
            except (ImportError, OSError):
                logger.warning(
                    "WeasyPrint not installed. Regional %s PDF skipped. HTML at %s.",
                    self._lang.upper(),
                    html_path,
                )
                return html_path
        return output_path

    @staticmethod
    def _build_context(report: FindingsReport) -> dict:
        return {
            "engagement_id": report.engagement_id,
            "generated_at": report.generated_at,
            "total_count": report.total_count,
            "critical_count": report.critical_count,
            "high_count": report.high_count,
            "medium_count": report.medium_count,
            "low_count": report.low_count,
            "critical_findings": [
                f for f in report.findings if f.severity == FindingSeverity.CRITICAL
            ],
            "high_findings": [f for f in report.findings if f.severity == FindingSeverity.HIGH],
            "all_findings": report.findings,
        }
