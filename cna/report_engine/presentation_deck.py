"""Phase E — Presentation Deck Builder (PPTX).

Builds a 10-section executive PPTX deck using python-pptx.

Slide sections (in order):
  1. Cover — client name, engagement ID, date, CNA branding
  2. Engagement Overview — scope, platforms, discovery dates
  3. Methodology — three-tier model, discovery approach, data handling
  4. Executive Summary — findings by severity (bar chart placeholder)
  5. Critical Findings — one slide per CRITICAL finding (max 10 slides)
  6. High Findings — one slide per HIGH finding (max 10 slides)
  7. Key Recommendations — top 5, one per slide
  8. Architecture Diagrams — placeholder slides (linked from Phase B)
  9. Remediation Roadmap — short-term / medium-term / long-term
  10. Appendix — full finding table (rule ID, resource, severity, framework)
"""

from __future__ import annotations

import logging
from pathlib import Path

from cna.core.findings_schema import FindingSeverity, FindingsReport

logger = logging.getLogger("cna.report.pptx")

# Severity colour palette (RGB tuples)
_SEVERITY_COLORS = {
    "CRITICAL": (0xD3, 0x2F, 0x2F),  # red
    "HIGH": (0xF5, 0x7C, 0x00),  # orange
    "MEDIUM": (0xF9, 0xA8, 0x25),  # amber
    "LOW": (0x43, 0xA0, 0x47),  # green
}


class PresentationDeckBuilder:
    """Builds the 10-section PPTX engagement deck."""

    def build(self, report: FindingsReport, output_path: Path) -> Path:
        """Build PPTX and write to output_path. Returns path."""
        try:
            from pptx import Presentation
            from pptx.util import Inches
        except ImportError:
            logger.warning(
                "python-pptx not installed. PPTX skipped. Install with: pip install python-pptx"
            )
            return output_path

        prs = Presentation()
        prs.slide_width = Inches(13.33)
        prs.slide_height = Inches(7.5)

        title_layout = prs.slide_layouts[0]  # title + subtitle
        body_layout = prs.slide_layouts[1]  # title + content

        critical = [f for f in report.findings if f.severity == FindingSeverity.CRITICAL]
        high = [f for f in report.findings if f.severity == FindingSeverity.HIGH]
        medium = [f for f in report.findings if f.severity == FindingSeverity.MEDIUM]
        low = [f for f in report.findings if f.severity == FindingSeverity.LOW]

        def add_title_slide(title_text: str, subtitle_text: str = "") -> None:
            slide = prs.slides.add_slide(title_layout)
            slide.shapes.title.text = title_text
            slide.placeholders[1].text = subtitle_text

        def add_body_slide(title_text: str, body_text: str) -> None:
            slide = prs.slides.add_slide(body_layout)
            slide.shapes.title.text = title_text
            tf = slide.placeholders[1].text_frame
            tf.text = body_text
            tf.word_wrap = True

        def add_finding_slide(finding) -> None:
            slide = prs.slides.add_slide(body_layout)
            severity_tag = finding.severity.value
            slide.shapes.title.text = f"[{severity_tag}] {finding.title}"
            body = (
                f"Rule: {finding.rule_id}\n"
                f"Resource: {finding.resource_id} ({finding.resource_type})\n"
                f"Account/Sub: {finding.account_id} | Region: {finding.region}\n\n"
                f"Observed: {finding.observed_state.fact}\n\n"
                f"Framework: "
                + ", ".join(f"{m.framework} — {m.control}" for m in finding.framework_mappings)
            )
            tf = slide.placeholders[1].text_frame
            tf.text = body
            tf.word_wrap = True

        # Section 1: Cover
        add_title_slide(
            title_text="Cloud Network Assessment",
            subtitle_text=(
                f"Engagement: {report.engagement_id}\n"
                f"Generated: {report.generated_at}\n"
                "Prepared by: Saul Patino Jr. | AWS SAP | Azure SAE"
            ),
        )

        # Section 2: Engagement Overview
        add_body_slide(
            "Engagement Overview",
            f"Engagement ID: {report.engagement_id}\n"
            f"Schema Version: {report.schema_version}\n"
            f"Findings Total: {report.total_count}\n"
            f"Generated: {report.generated_at}",
        )

        # Section 3: Methodology
        add_body_slide(
            "Methodology",
            "Discovery: Read-only STS AssumeRole (AWS) + DefaultAzureCredential (Azure)\n"
            "Analysis: Observed-state findings — facts only, no assumptions\n"
            "Frameworks: AWS Well-Architected, Azure WAF, NIST CSF, CIS Benchmarks\n"
            "Data handling: Credentials never written to disk. Data retained 90 days.",
        )

        # Section 4: Executive Summary
        add_body_slide(
            "Executive Summary — Finding Counts",
            f"Critical : {len(critical)}\n"
            f"High     : {len(high)}\n"
            f"Medium   : {len(medium)}\n"
            f"Low      : {len(low)}\n"
            f"Total    : {report.total_count}",
        )

        # Section 5: Critical Findings (max 10)
        for finding in critical[:10]:
            add_finding_slide(finding)

        # Section 6: High Findings (max 10)
        for finding in high[:10]:
            add_finding_slide(finding)

        # Section 7: Key Recommendations (top 5)
        top5 = (critical + high)[:5]
        for finding in top5:
            recs = finding.recommendations or []
            rec_text = (
                "\n".join(f"• {r.text}" for r in recs[:2])
                if recs
                else "See technical report for full recommendations."
            )
            add_body_slide(
                f"Recommendation: {finding.rule_id}",
                f"{finding.title}\n\n{rec_text}",
            )

        # Section 8: Architecture Diagrams placeholder
        add_body_slide(
            "Architecture Diagrams",
            "See engagement deliverables folder for:\n"
            "  • draw.io network topology (editable)\n"
            "  • Mermaid diagrams (version-controlled)\n"
            "  • PNG exports (Phase B output)",
        )

        # Section 9: Remediation Roadmap
        add_body_slide(
            "Remediation Roadmap",
            "Short-term (0–30 days): Remediate all CRITICAL findings\n"
            "Medium-term (30–90 days): Remediate HIGH findings, implement flow logs\n"
            "Long-term (90–180 days): Address MEDIUM findings, WAF tuning, DX redundancy",
        )

        # Section 10: Appendix — full finding table
        table_text = "Rule ID | Resource | Severity | Framework\n"
        for f in report.findings:
            fw = f.framework_mappings[0].control if f.framework_mappings else "—"
            table_text += f"{f.rule_id} | {f.resource_id} | {f.severity.value} | {fw}\n"
        add_body_slide("Appendix — Full Finding Catalog", table_text)

        prs.save(str(output_path))
        logger.info("PPTX deck written: %s (%d slides)", output_path, len(prs.slides))
        return output_path
