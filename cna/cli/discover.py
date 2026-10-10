"""CLI: cna discover — Phase C entry point.

Commands:
  cna discover aws    — STS AssumeRole cross-account discovery
  cna discover azure  — DefaultAzureCredential subscription discovery
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from cna.core.persistence import EngagementStore

logger = logging.getLogger("cna.cli.discover")


@click.group()
def discover():
    """Run cloud network discovery for an engagement."""


@discover.command("aws")
@click.option("--engagement-id", required=True, help="Engagement ID from `cna init`")
@click.option(
    "--org-role",
    required=True,
    help="ARN of the cross-account read-only role (e.g. arn:aws:iam::MGMT:role/CNA-ReadOnly)",
)
@click.option("--external-id", default=None, help="STS ExternalId for the role assumption")
@click.option(
    "--regions", default=None, help="Comma-separated region list. Default: all enabled regions."
)
@click.option(
    "--accounts", default=None, help="Comma-separated account IDs. Default: all org accounts."
)
@click.option(
    "--resume", is_flag=True, default=False, help="Skip accounts/regions with existing checkpoints."
)
@click.option(
    "--skip-opt-in-regions",
    is_flag=True,
    default=True,
    help="Skip opt-in regions that require explicit enablement.",
)
@click.option(
    "--data-dir", default="./engagements", help="Engagement data directory (default: ./engagements)"
)
def discover_aws(  # noqa: PLR0913
    engagement_id, org_role, external_id, regions, accounts, resume, skip_opt_in_regions, data_dir
):
    """Discover AWS network topology via STS AssumeRole.

    \b
    Examples:
      # Full org discovery
      cna discover aws \\
        --engagement-id acme-20260305-a3f2 \\
        --org-role arn:aws:iam::123456789012:role/CNA-ReadOnly

      # Single account, specific regions
      cna discover aws \\
        --engagement-id acme-20260305-a3f2 \\
        --org-role arn:aws:iam::123456789012:role/CNA-ReadOnly \\
        --accounts 234567890123 \\
        --regions us-east-1,eu-west-1

      # Resume interrupted discovery
      cna discover aws \\
        --engagement-id acme-20260305-a3f2 \\
        --org-role arn:aws:iam::123456789012:role/CNA-ReadOnly \\
        --resume
    """
    from cna.core.exceptions import CNAAuthError
    from cna.modules.network.discovery.aws_discovery import AWSDiscovery, DiscoveryOptions

    store = EngagementStore(engagement_id=engagement_id, data_dir=Path(data_dir))

    region_list = [r.strip() for r in regions.split(",")] if regions else []
    account_list = [a.strip() for a in accounts.split(",")] if accounts else []

    opts = DiscoveryOptions(
        org_role_arn=org_role,
        external_id=external_id,
        regions=region_list,
        account_ids=account_list,
        skip_opt_in_regions=skip_opt_in_regions,
        resume=resume,
    )

    click.echo(f"\u25b6 Starting AWS discovery for engagement: {engagement_id}")
    click.echo(f"  Role: {org_role}")
    click.echo(f"  Resume: {resume}")

    try:
        discovery = AWSDiscovery(store=store, options=opts)
        topology = discovery.run()

        total_vpcs = sum(len(r.vpcs) for r in topology.regions)
        blocked = sum(1 for r in topology.regions if r.discovery_blocked)
        click.echo("\n\u2705 AWS discovery complete.")
        click.echo(f"   Accounts : {len(topology.accounts)}")
        click.echo(f"   Regions  : {len(topology.regions)}")
        click.echo(f"   VPCs     : {total_vpcs}")
        click.echo(f"   Blocked  : {blocked}")

    except CNAAuthError as e:
        click.echo(f"\u274c Auth error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\n\u26a0 Discovery interrupted. Run with --resume to continue.", err=True)
        sys.exit(130)


@discover.command("azure")
@click.option("--engagement-id", required=True, help="Engagement ID from `cna init`")
@click.option("--tenant-id", required=True, help="Azure tenant (directory) ID")
@click.option(
    "--subscriptions",
    default=None,
    help="Comma-separated subscription IDs. Default: all enabled subscriptions.",
)
@click.option(
    "--client-id",
    default=None,
    help="Service principal client ID (optional — DefaultAzureCredential if not set)",
)
@click.option(
    "--client-secret",
    default=None,
    help="Service principal secret (in-memory only, never logged or written to disk)",
)
@click.option(
    "--resume", is_flag=True, default=False, help="Skip subscriptions with existing checkpoints."
)
@click.option(
    "--no-resource-graph",
    is_flag=True,
    default=False,
    help="Disable Azure Resource Graph (use ARM REST only — slower).",
)
@click.option(
    "--data-dir", default="./engagements", help="Engagement data directory (default: ./engagements)"
)
def discover_azure(  # noqa: PLR0913
    engagement_id,
    tenant_id,
    subscriptions,
    client_id,
    client_secret,
    resume,
    no_resource_graph,
    data_dir,
):
    """Discover Azure network topology via ARM REST + Resource Graph.

    \b
    Examples:
      # DefaultAzureCredential (az login / managed identity / env vars)
      cna discover azure \\
        --engagement-id acme-20260305-a3f2 \\
        --tenant-id 00000000-0000-0000-0000-000000000000

      # Service principal
      cna discover azure \\
        --engagement-id acme-20260305-a3f2 \\
        --tenant-id 00000000-0000-0000-0000-000000000000 \\
        --client-id <app-id> \\
        --client-secret <secret>

      # Specific subscriptions + resume
      cna discover azure \\
        --engagement-id acme-20260305-a3f2 \\
        --tenant-id 00000000-0000-0000-0000-000000000000 \\
        --subscriptions sub-id-1,sub-id-2 \\
        --resume
    """
    from cna.core.exceptions import CNAAuthError
    from cna.modules.network.discovery.azure_discovery import AzureDiscovery, AzureDiscoveryOptions

    store = EngagementStore(engagement_id=engagement_id, data_dir=Path(data_dir))

    sub_list = [s.strip() for s in subscriptions.split(",")] if subscriptions else []

    opts = AzureDiscoveryOptions(
        tenant_id=tenant_id,
        subscription_ids=sub_list,
        resume=resume,
        use_resource_graph=not no_resource_graph,
        client_id=client_id,
        client_secret=client_secret,
    )

    click.echo(f"\u25b6 Starting Azure discovery for engagement: {engagement_id}")
    click.echo(f"  Tenant: {tenant_id}")
    click.echo(f"  Auth: {'Service Principal' if client_id else 'DefaultAzureCredential'}")
    click.echo(f"  Resume: {resume}")

    try:
        discovery = AzureDiscovery(store=store, options=opts)
        topology = discovery.run()

        total_vnets = sum(len(s.vnets) for s in topology.subscriptions)
        blocked = sum(1 for s in topology.subscriptions if s.discovery_blocked)
        click.echo("\n\u2705 Azure discovery complete.")
        click.echo(f"   Subscriptions     : {len(topology.subscriptions)}")
        click.echo(f"   Management Groups : {len(topology.management_groups)}")
        click.echo(f"   VNets             : {total_vnets}")
        click.echo(f"   Blocked           : {blocked}")

    except CNAAuthError as e:
        click.echo(f"\u274c Auth error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\n\u26a0 Discovery interrupted. Run with --resume to continue.", err=True)
        sys.exit(130)
