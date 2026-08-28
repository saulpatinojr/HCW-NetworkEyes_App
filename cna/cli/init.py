"""CLI: cna init — Phase A entry point.

Creates the engagement directory structure and initial state via
EngagementStore. Everything downstream (`cna discover`, `cna analyze`,
`cna report`, `cna publish`) keys off the engagement ID minted here.
"""

from __future__ import annotations

import logging
from pathlib import Path

import click

logger = logging.getLogger("cna.cli.init")


@click.command("init")
@click.option("--client", required=True, help="Client name (used to derive the engagement ID)")
@click.option("--regions", default="us", help="Comma-separated region groups: us,emea,japan")
@click.option(
    "--engagement-id",
    "engagement_id_override",
    default=None,
    help="Override the generated engagement ID",
)
@click.option(
    "--data-dir", default="./engagements", help="Engagement data directory (default: ./engagements)"
)
def init(client, regions, engagement_id_override, data_dir):
    """Initialize a new assessment engagement.

    \b
    Example:
      cna init --client "Acme Corp" --regions us,emea
    """
    from cna.core.engagement import EngagementConfig
    from cna.core.persistence import EngagementStore, generate_engagement_id

    engagement_id = engagement_id_override or generate_engagement_id(client)
    config = EngagementConfig(
        engagement_id=engagement_id,
        client_name=client,
        client_slug=client.lower().replace(" ", "-"),
        regions=[r.strip() for r in regions.split(",") if r.strip()],
    )

    store = EngagementStore(data_dir=Path(data_dir))
    eng_dir = store.init(config)

    click.echo(f"✅ Engagement initialized: {engagement_id}")
    click.echo(f"   → {eng_dir.resolve()}")
    click.echo(f"\nNext: cna discover aws|azure --engagement-id {engagement_id}")
