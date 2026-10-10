"""CLI: cna publish — Phase F entry point.

Commands:
  cna publish          — upload deliverables, generate portal, issue access links
  cna publish status   — check if portal is live and access link is still valid
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

logger = logging.getLogger("cna.cli.publish")


@click.group("publish")
def publish_group():
    """Publish engagement deliverables to a client-accessible portal."""
    pass


@publish_group.command("run")
@click.option("--engagement-id", required=True, help="Engagement ID")
@click.option("--cloud", required=True, type=click.Choice(["aws", "azure"]), help="Storage target")
@click.option("--bucket", default=None, help="S3 bucket name (aws)")
@click.option("--s3-prefix", default=None, help="S3 key prefix (default: engagement-id)")
@click.option("--storage-account", default=None, help="Azure storage account name (azure)")
@click.option("--container", default=None, help="Azure Blob container name (azure)")
@click.option("--ttl-hours", default=168, help="Link TTL in hours (max 168 = 7 days)")
@click.option("--data-dir", default="./engagements")
def run(engagement_id, cloud, bucket, s3_prefix, storage_account, container, ttl_hours, data_dir):  # noqa: PLR0913
    """Upload deliverables and publish portal.

    \b
    Examples:
      # AWS S3
      cna publish run \\
        --engagement-id acme-20260305-a3f2 \\
        --cloud aws \\
        --bucket cna-deliverables-prod \\
        --ttl-hours 168

      # Azure Blob Storage
      cna publish run \\
        --engagement-id acme-20260305-a3f2 \\
        --cloud azure \\
        --storage-account cnadeliveries \\
        --container acme-20260305-a3f2
    """
    from cna.core.persistence import EngagementStore
    from cna.delivery_portal.access_manager import AccessManager
    from cna.delivery_portal.portal_generator import PortalGenerator
    from cna.delivery_portal.retention_engine import RetentionEngine, RetentionExpiredError
    from cna.report_engine.deliverable_manifest import DeliverableManifest

    store = EngagementStore(
        engagement_id=engagement_id,
        data_dir=Path(data_dir),
    )

    # DD-019: Retention check FIRST — before any upload
    click.echo("▶ Checking retention window...")
    try:
        delivery_date = store.get_delivery_date(engagement_id)
        RetentionEngine.check(engagement_id, delivery_date)
    except RetentionExpiredError as e:
        click.echo(f"\n✗ Retention expired:\n  {e}", err=True)
        sys.exit(1)

    # Load manifest
    click.echo("▶ Loading deliverable manifest...")
    try:
        manifest_data = store.load_deliverable_manifest(engagement_id)
        manifest = DeliverableManifest(
            engagement_id=engagement_id,
            records=manifest_data["records"],
        )
    except FileNotFoundError:
        click.echo("✗ No deliverable manifest found. Run `cna report generate` first.", err=True)
        sys.exit(1)

    # Current findings checksum for staleness detection
    try:
        findings_json = store.load_findings_report_json(engagement_id)
        current_checksum = DeliverableManifest.checksum(findings_json)
    except FileNotFoundError:
        current_checksum = None

    # Build deployer
    file_paths = [Path(r["path"]) for r in manifest_data["records"]]
    file_paths = [fp for fp in file_paths if fp.exists()]

    if not file_paths:
        click.echo("✗ No deliverable files found on disk.", err=True)
        sys.exit(1)

    click.echo(f"▶ Uploading {len(file_paths)} file(s) to {cloud.upper()}...")

    def _progress(name: str, transferred: int, total: int) -> None:
        pct = int(transferred / total * 100) if total else 100
        click.echo(f"   {name}: {pct}%", nl=False)
        click.echo("\r", nl=False)

    # Each branch keeps its deployer under its own name and hands back a
    # publish_portal closure, so no call is ever made against the
    # S3Deployer | AzureBlobDeployer union (their signing methods differ).
    if cloud == "aws":
        from cna.delivery_portal.s3_deployer import S3Deployer

        prefix = s3_prefix or engagement_id
        s3_deployer = S3Deployer(
            bucket=bucket,
            prefix=prefix,
            presigned_ttl_seconds=ttl_hours * 3600,
        )
        signed_urls = s3_deployer.upload_all(file_paths, progress_callback=_progress)
        storage_location = f"s3://{bucket}/{prefix}"

        def publish_portal(portal_path: Path) -> str:
            key = s3_deployer.upload(portal_path)
            return s3_deployer.generate_presigned_url(key)

    else:
        from cna.delivery_portal.azure_blob_deployer import AzureBlobDeployer

        cont = container or engagement_id
        blob_deployer = AzureBlobDeployer(
            account_name=storage_account,
            container_name=cont,
            sas_ttl_hours=ttl_hours,
        )
        signed_urls = blob_deployer.upload_all(file_paths, progress_callback=_progress)
        storage_location = f"https://{storage_account}.blob.core.windows.net/{cont}"

        def publish_portal(portal_path: Path) -> str:
            blob = blob_deployer.upload(portal_path)
            return blob_deployer.generate_sas_token(blob)

    click.echo("")

    # Rebuild manifest with DeliverableRecord objects
    from cna.report_engine.deliverable_manifest import DeliverableRecord

    records = [
        DeliverableRecord(
            **{k: v for k, v in r.items() if k in DeliverableRecord.__dataclass_fields__}
        )
        for r in manifest_data["records"]
    ]
    manifest.records = records

    entries = PortalGenerator.build_entries(
        manifest=manifest,
        signed_urls=signed_urls,
        current_findings_checksum=current_checksum or "",
    )

    # Generate and upload portal index.html
    access_record = AccessManager.build_record(
        engagement_id=engagement_id,
        cloud=cloud,
        storage_location=storage_location,
        deliverable_count=len(entries),
        ttl_hours=ttl_hours,
    )

    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        portal_path = Path(tmpdir) / "index.html"
        PortalGenerator().generate(
            manifest=manifest,
            entries=entries,
            published_at=access_record.issued_at,
            expires_at=access_record.expires_at,
            output_path=portal_path,
        )
        portal_url = publish_portal(portal_path)

    # Store access record (metadata only, no URL)
    store.write_access_record(
        engagement_id=engagement_id,
        record=access_record.to_dict(),
    )

    stale_count = sum(1 for e in entries if e.is_stale)
    click.echo(f"\n✅ Portal published — {len(entries)} deliverable(s)")
    if stale_count:
        click.echo(
            f"   ⚠  {stale_count} stale deliverable(s) — re-run `cna report generate` to refresh"
        )
    click.echo(f"   Expires: {access_record.expires_at}")
    click.echo(f"   Portal URL: {portal_url}")
    click.echo("   (Share this URL with the client. It expires automatically.)")


@publish_group.command("status")
@click.option("--engagement-id", required=True, help="Engagement ID")
@click.option("--data-dir", default="./engagements")
def status(engagement_id, data_dir):
    """Check portal publication status and access link expiry.

    \b
    Example:
      cna publish status --engagement-id acme-20260305-a3f2
    """
    from cna.core.persistence import EngagementStore
    from cna.delivery_portal.access_manager import AccessRecord

    store = EngagementStore(
        engagement_id=engagement_id,
        data_dir=Path(data_dir),
    )

    try:
        record_data = store.load_access_record(engagement_id)
    except FileNotFoundError:
        click.echo("✗ No publication record found. Run `cna publish run` first.")
        sys.exit(1)

    record = AccessRecord(**record_data)
    hours = record.hours_remaining()

    if record.is_expired():
        click.echo(f"✗ Access link EXPIRED ({-hours:.1f}h ago)")
        click.echo(f"   Expired at: {record.expires_at}")
        click.echo("   Re-run `cna publish run` to issue a new link.")
    else:
        click.echo("✅ Portal active")
        click.echo(f"   Cloud:        {record.cloud.upper()}")
        click.echo(f"   Location:     {record.storage_location}")
        click.echo(f"   Deliverables: {record.deliverable_count}")
        click.echo(f"   Expires:      {record.expires_at} ({hours:.1f}h remaining)")
