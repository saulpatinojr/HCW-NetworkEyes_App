"""CLI: cna report — Phase E entry point.

Commands:
  cna report          — full render pipeline (all formats)
  cna report preview  — HTML only, no PDF toolchain required
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

logger = logging.getLogger("cna.cli.report")


@click.group("report")
def report_group():
    """Generate engagement deliverables from a reviewed FindingsReport."""
    pass


@report_group.command("generate")
@click.option("--engagement-id", required=True, help="Engagement ID from `cna init`")
@click.option(
    "--data-dir", default="./engagements", help="Engagement data directory (default: ./engagements)"
)
@click.option(
    "--skip-pdf",
    is_flag=True,
    default=False,
    help="Skip PDF rendering (HTML output only, no WeasyPrint required)",
)
@click.option("--no-pptx", is_flag=True, default=False, help="Skip PPTX deck generation")
@click.option(
    "--regional-ja",
    is_flag=True,
    default=False,
    help="Generate JA regional report (requires --ja-review-complete)",
)
@click.option(
    "--ja-review-complete",
    is_flag=True,
    default=False,
    help="Confirm native speaker review complete (DD-015)",
)
@click.option("--output-dir", default=None, help="Override deliverables output directory")
def generate(  # noqa: PLR0913
    engagement_id, data_dir, skip_pdf, no_pptx, regional_ja, ja_review_complete, output_dir
):
    """Render all engagement deliverables.

    \b
    Requires FindingsReport with review_complete=True.
    Run `cna review complete --engagement-id <id>` first.

    \b
    Examples:
      # Full render (executive PDF + technical PDF + PPTX + HTML preview)
      cna report generate --engagement-id acme-20260305-a3f2

      # HTML only (no PDF toolchain required)
      cna report generate --engagement-id acme-20260305-a3f2 --skip-pdf

      # Include JA regional report
      cna report generate \\
        --engagement-id acme-20260305-a3f2 \\
        --regional-ja --ja-review-complete
    """
    # SCAFFOLD — not implemented (TODO.md T-412).
    #
    # Calls EngagementStore.load_findings_report(), and RenderPipeline finishes
    # by calling write_deliverable_manifest(). Neither exists on
    # EngagementStore, so this died with an unhandled AttributeError.
    raise NotImplementedError(
        "`cna report generate` is not implemented yet. It needs EngagementStore "
        "methods load_findings_report() and write_deliverable_manifest(), neither "
        "of which exists — see TODO.md T-412."
    )
    from cna.core.persistence import EngagementStore
    from cna.report_engine.render_pipeline import (
        RenderOptions,
        RenderPipeline,
        ReviewGateError,
    )

    store = EngagementStore(
        engagement_id=engagement_id,
        data_dir=Path(data_dir),
    )

    # Load FindingsReport
    click.echo("▶ Loading FindingsReport...")
    try:
        report = store.load_findings_report(engagement_id)
    except FileNotFoundError:
        click.echo("✗ No FindingsReport found. Run `cna analyze` first.", err=True)
        sys.exit(1)

    opts = RenderOptions(
        render_executive=not skip_pdf,
        render_technical=not skip_pdf,
        render_pptx=not no_pptx,
        render_html_preview=True,
        render_regional_en=not skip_pdf,
        render_regional_ja=regional_ja,
        ja_review_complete=ja_review_complete,
        skip_pdf=skip_pdf,
        output_dir=Path(output_dir) if output_dir else None,
    )

    pipeline = RenderPipeline(store=store, options=opts)

    try:
        click.echo("▶ Running render pipeline...")
        manifest = pipeline.run(report)
    except ReviewGateError as e:
        click.echo(f"\n✗ Review gate blocked render:\n  {e}", err=True)
        click.echo(f"  Run: cna review complete --engagement-id {engagement_id}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"\n✗ Render failed: {e}", err=True)
        logger.exception("Render pipeline failure")
        sys.exit(1)

    # Summary
    click.echo(f"\n✅ Render complete — {len(manifest.records)} deliverable(s):")
    for rec in manifest.records:
        size = f" ({rec.size_bytes:,} bytes)" if rec.size_bytes else ""
        click.echo(f"   [{rec.format.upper():4}] {rec.label}{size}")
        click.echo(f"          → {rec.path}")


@report_group.command("preview")
@click.option("--engagement-id", required=True, help="Engagement ID")
@click.option("--data-dir", default="./engagements")
@click.option("--output", default=None, help="Output HTML path (default: deliverables dir)")
def preview(engagement_id, data_dir, output):
    """Generate HTML preview — no PDF toolchain required.

    \b
    Does NOT require review_complete=True — useful for pre-review inspection.

    \b
    Example:
      cna report preview --engagement-id acme-20260305-a3f2
    """
    # SCAFFOLD — not implemented (TODO.md T-412).
    #
    # Calls EngagementStore.load_findings_report(), which does not exist.
    raise NotImplementedError(
        "`cna report preview` is not implemented yet. It needs "
        "EngagementStore.load_findings_report(), which does not exist — "
        "see TODO.md T-412."
    )
    from cna.core.persistence import EngagementStore
    from cna.report_engine.html_preview import HtmlPreviewRenderer

    store = EngagementStore(
        engagement_id=engagement_id,
        data_dir=Path(data_dir),
    )

    try:
        report = store.load_findings_report(engagement_id)
    except FileNotFoundError:
        click.echo("✗ No FindingsReport found. Run `cna analyze` first.", err=True)
        sys.exit(1)

    out_path = (
        Path(output)
        if output
        else Path(data_dir) / engagement_id / "deliverables" / f"{engagement_id}_preview.html"
    )

    renderer = HtmlPreviewRenderer()
    written = renderer.render(report=report, output_path=out_path)

    status = "(pre-review)" if not report.review_complete else "(reviewed)"
    click.echo(f"\n✅ HTML preview written {status}")
    click.echo(f"   → {written}")
    click.echo("   Open in browser to inspect findings before running `cna review complete`.")
