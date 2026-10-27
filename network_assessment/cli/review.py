"""CLI: network-assessment review — DD-009 human review gate.

Commands:
  network-assessment review complete — sign off the FindingsReport (sets review_complete=True)

`network-assessment report generate` refuses to render until this has run
(ReviewGateError in RenderPipeline).
"""

from __future__ import annotations

import getpass
import logging
import sys
from pathlib import Path

import click

logger = logging.getLogger("network_assessment.cli.review")


@click.group("review")
def review_group():
    """Human architect review gate — required before `network-assessment report` (DD-009)."""
    pass


@review_group.command("complete")
@click.option("--engagement-id", required=True, help="Engagement ID from `network-assessment init`")
@click.option(
    "--operator",
    default=None,
    help="Reviewer recorded in the audit trail (default: current OS user)",
)
@click.option(
    "--data-dir", default="./engagements", help="Engagement data directory (default: ./engagements)"
)
def complete(engagement_id, operator, data_dir):
    """Mark the FindingsReport as human-reviewed (DD-009 sign-off).

    \b
    Sets review_complete=True on the stored FindingsReport and logs the
    sign-off to the engagement audit trail. Run it after inspecting the
    findings, e.g. via `network-assessment report preview`.
    """
    from network_assessment.core.persistence import EngagementNotFoundError, EngagementStore

    store = EngagementStore(engagement_id=engagement_id, data_dir=Path(data_dir))

    try:
        report = store.load_findings_report(engagement_id)
    except FileNotFoundError:
        click.echo("✗ No FindingsReport found. Run `network-assessment analyze` first.", err=True)
        sys.exit(1)

    if report.review_complete:
        click.echo(f"Review already complete for {engagement_id} — nothing to do.")
        return

    reviewer = operator or getpass.getuser()

    report.review_complete = True
    for finding in report.findings:
        finding.human_reviewed = True
    store.write_findings_report(engagement_id, report.model_dump())

    # Mirror the flag on the engagement state when it exists, so
    # engagement.json and the report never disagree about the gate.
    try:
        config = store.load(engagement_id)
        config.review_complete = True
        store.save(config)
    except EngagementNotFoundError:
        logger.debug("[%s] No engagement.json to mirror review_complete onto", engagement_id)

    store.write_audit_event(
        engagement_id,
        {
            "type": "review_complete",
            "operator": reviewer,
            "findings_signed_off": report.total_count,
        },
    )

    click.echo(f"✅ Review complete — {report.total_count} finding(s) signed off by {reviewer}")
    click.echo(f"\nNext: network-assessment report generate --engagement-id {engagement_id}")
