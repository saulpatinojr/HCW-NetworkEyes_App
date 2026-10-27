"""CLI: network-assessment discover — Phase C entry point.

Commands:
  network-assessment discover aws    — STS AssumeRole cross-account discovery
  network-assessment discover azure  — subscription discovery as the platform identity (az login / managed identity)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import click

from network_assessment.core.persistence import EngagementStore

logger = logging.getLogger("network_assessment.cli.discover")


@click.group()
def discover():
    """Run cloud network discovery for an engagement."""


@discover.command("aws")
@click.option("--engagement-id", required=True, help="Engagement ID from `network-assessment init`")
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
      network-assessment discover aws \\
        --engagement-id acme-20260305-a3f2 \\
        --org-role arn:aws:iam::123456789012:role/CNA-ReadOnly

      # Single account, specific regions
      network-assessment discover aws \\
        --engagement-id acme-20260305-a3f2 \\
        --org-role arn:aws:iam::123456789012:role/CNA-ReadOnly \\
        --accounts 234567890123 \\
        --regions us-east-1,eu-west-1

      # Resume interrupted discovery
      network-assessment discover aws \\
        --engagement-id acme-20260305-a3f2 \\
        --org-role arn:aws:iam::123456789012:role/CNA-ReadOnly \\
        --resume
    """
    from network_assessment.core.exceptions import NetworkAssessmentAuthError
    from network_assessment.modules.network.discovery.aws_discovery import (
        AWSDiscovery,
        DiscoveryOptions,
    )

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

    except NetworkAssessmentAuthError as e:
        click.echo(f"\u274c Auth error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\n\u26a0 Discovery interrupted. Run with --resume to continue.", err=True)
        sys.exit(130)


@discover.command("azure")
@click.option("--engagement-id", required=True, help="Engagement ID from `network-assessment init`")
@click.option("--tenant-id", required=True, help="Azure tenant (directory) ID")
@click.option(
    "--subscriptions",
    default=None,
    help="Comma-separated subscription IDs. Default: all enabled subscriptions.",
)
@click.option(
    "--resume", is_flag=True, default=False, help="Skip subscriptions with existing checkpoints."
)
@click.option(
    "--no-resource-graph",
    is_flag=True,
    default=False,
    help="Use the ARM list loop (CNA_DISCOVERY_BACKEND=arm; kept for one release).",
)
@click.option(
    "--scope",
    "scopes",
    multiple=True,
    help="Assess only this scope: /subscriptions/<id> or /subscriptions/<id>/resourceGroups/<name>. "
    "Repeatable; also CNA_SCOPES (space-separated).",
)
@click.option(
    "--data-dir", default="./engagements", help="Engagement data directory (default: ./engagements)"
)
def discover_azure(  # noqa: PLR0913
    engagement_id,
    tenant_id,
    subscriptions,
    resume,
    no_resource_graph,
    scopes,
    data_dir,
):
    """Discover Azure network topology via ARM REST + Resource Graph.

    \b
    Examples:
      # The platform identity: az login on a workstation, the managed identity in the appliance
      network-assessment discover azure \\
        --engagement-id acme-20260305-a3f2 \\
        --tenant-id 00000000-0000-0000-0000-000000000000

      # Specific subscriptions + resume
      network-assessment discover azure \\
        --engagement-id acme-20260305-a3f2 \\
        --tenant-id 00000000-0000-0000-0000-000000000000 \\
        --subscriptions sub-id-1,sub-id-2 \\
        --resume
    """
    from network_assessment.core.exceptions import NetworkAssessmentAuthError
    from network_assessment.modules.network.discovery.azure_discovery import (
        AzureDiscovery,
        AzureDiscoveryOptions,
    )

    store = EngagementStore(engagement_id=engagement_id, data_dir=Path(data_dir))

    sub_list = [s.strip() for s in subscriptions.split(",")] if subscriptions else []

    scope_list = list(scopes) or os.environ.get("CNA_SCOPES", "").split()
    opts = AzureDiscoveryOptions(
        tenant_id=tenant_id,
        subscription_ids=sub_list,
        resume=resume,
        use_resource_graph=not no_resource_graph,
        scopes=scope_list,
    )

    click.echo(f"\u25b6 Starting Azure discovery for engagement: {engagement_id}")
    click.echo(f"  Tenant: {tenant_id}")
    click.echo(f"  Backend: {opts.backend}")
    click.echo("  Auth: platform identity (az login / managed identity)")
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

    except NetworkAssessmentAuthError as e:
        click.echo(f"\u274c Auth error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\n\u26a0 Discovery interrupted. Run with --resume to continue.", err=True)
        sys.exit(130)
