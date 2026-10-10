"""CLI: cna analyze — Phase D entry point.

Loads topology checkpoints from EngagementStore, runs AnalysisEngine,
enriches with RecommendationEngine, writes FindingsReport.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

logger = logging.getLogger("cna.cli.analyze")


@click.command("analyze")
@click.option("--engagement-id", required=True, help="Engagement ID from `cna init`")
@click.option(
    "--aws",
    "load_aws",
    is_flag=True,
    default=False,
    help="Load and analyze AWS topology checkpoints",
)
@click.option(
    "--azure",
    "load_azure",
    is_flag=True,
    default=False,
    help="Load and analyze Azure topology checkpoints",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Generate findings but do not write FindingsReport to store",
)
@click.option(
    "--no-recommendations", is_flag=True, default=False, help="Skip MCP recommendation enrichment"
)
@click.option(
    "--data-dir", default="./engagements", help="Engagement data directory (default: ./engagements)"
)
def analyze(engagement_id, load_aws, load_azure, dry_run, no_recommendations, data_dir):  # noqa: C901, PLR0912, PLR0913
    """Analyze discovery checkpoints and generate a FindingsReport.

    \b
    Examples:
      # Analyze both AWS and Azure
      cna analyze \\
        --engagement-id acme-20260305-a3f2 \\
        --aws --azure

      # AWS only, dry run
      cna analyze \\
        --engagement-id acme-20260305-a3f2 \\
        --aws --dry-run

      # Skip MCP enrichment (offline / air-gapped)
      cna analyze \\
        --engagement-id acme-20260305-a3f2 \\
        --aws --azure --no-recommendations
    """
    from cna.ai_engine.analysis_engine import AnalysisEngine, AnalysisOptions
    from cna.ai_engine.recommendation_engine import RecommendationEngine
    from cna.core.persistence import EngagementStore

    if not load_aws and not load_azure:
        click.echo("\u274c Specify at least one of --aws or --azure", err=True)
        sys.exit(1)

    store = EngagementStore(engagement_id=engagement_id, data_dir=Path(data_dir))

    # Load topology checkpoints
    aws_topology = None
    azure_topology = None

    if load_aws:
        click.echo("\u25b6 Loading AWS topology checkpoints...")
        try:
            aws_topology = store.load_aws_topology(engagement_id)
            regions = len(aws_topology.regions) if aws_topology else 0
            blocked = sum(
                1 for r in (aws_topology.regions if aws_topology else []) if r.discovery_blocked
            )
            click.echo(f"  \u2713 {regions} regions loaded ({blocked} blocked)")
        except FileNotFoundError:
            click.echo("  \u26a0 No AWS checkpoints found. Run `cna discover aws` first.", err=True)
            if not load_azure:
                sys.exit(1)

    if load_azure:
        click.echo("\u25b6 Loading Azure topology checkpoints...")
        try:
            azure_topology = store.load_azure_topology(engagement_id)
            subs = len(azure_topology.subscriptions) if azure_topology else 0
            blocked = sum(
                1
                for s in (azure_topology.subscriptions if azure_topology else [])
                if s.discovery_blocked
            )
            click.echo(f"  \u2713 {subs} subscriptions loaded ({blocked} blocked)")
        except FileNotFoundError:
            click.echo(
                "  \u26a0 No Azure checkpoints found. Run `cna discover azure` first.", err=True
            )
            if not load_aws or not aws_topology:
                sys.exit(1)

    # Progress callback for CLI output
    def progress(cloud: str, current: int, total: int, label: str) -> None:
        click.echo(f"  [{cloud.upper()}] {current}/{total} — {label}")

    # Analysis
    click.echo("\u25b6 Running analysis engine...")
    opts = AnalysisOptions(
        load_aws=load_aws,
        load_azure=load_azure,
        dry_run=dry_run,
        progress_callback=progress,
    )
    engine = AnalysisEngine(store=store, options=opts)
    report = engine.run(aws_topology=aws_topology, azure_topology=azure_topology)

    # Recommendation enrichment
    if not no_recommendations:
        click.echo("\u25b6 Enriching with MCP recommendations...")
        enricher = RecommendationEngine()
        report = enricher.enrich(report)

    # Summary
    dry_tag = " (dry run — not written)" if dry_run else ""
    click.echo(f"\n\u2705 Analysis complete{dry_tag}")
    click.echo(f"   Total    : {report.total_count}")
    click.echo(f"   Critical : {report.critical_count}")
    click.echo(f"   High     : {report.high_count}")
    click.echo(f"   Medium   : {report.medium_count}")
    click.echo(f"   Low      : {report.low_count}")

    if report.critical_count > 0:
        click.echo(
            f"\n\u26a0  {report.critical_count} CRITICAL finding(s) detected. "
            "Escalation engine has been notified.",
            err=True,
        )

    if not dry_run:
        click.echo(
            "\nFindings written. Reviewer must set review_complete=True "
            "before running `cna report` (DD-009)."
        )
