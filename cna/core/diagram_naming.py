"""Diagram naming and versioning conventions.

Phase B fix for TODO_PhaseA: no diagram naming convention defined.
All output files use this module — zero ad-hoc naming allowed.

Convention:
  <engagement_slug>/<region_group>/<platform>_<type>_<scope>_v<version>.<ext>

Example:
  acme/us/aws_vpc_topology_us-east-1_v1.0.0.drawio
  acme/japan/azure_vnet_topology_japaneast_v1.0.0.svg
"""

from pathlib import Path

DIAGRAM_TYPES = {
    "vpc_topology",
    "vnet_topology",
    "account_hierarchy",
    "security_overlay",
    "traffic_flow",
    "trust_boundaries",
    "tgw_topology",
    "lz_architecture",
    "zerotrust_radar",
}

OUTPUT_FORMATS = ["drawio", "svg", "png", "pdf"]


def diagram_filename(  # noqa: PLR0913
    engagement_slug: str,
    region_group: str,
    platform: str,  # aws | azure
    diagram_type: str,
    scope: str,  # region name, account_id, tenant_id, or "all"
    version: str = "1.0.0",
    ext: str = "drawio",
) -> Path:
    """Return canonical output path for a diagram file."""
    if diagram_type not in DIAGRAM_TYPES:
        raise ValueError(f"Unknown diagram type: {diagram_type}. Valid: {DIAGRAM_TYPES}")
    if ext not in OUTPUT_FORMATS + ["html"]:
        raise ValueError(f"Unknown format: {ext}. Valid: {OUTPUT_FORMATS}")
    # Sanitize scope (no slashes, no spaces)
    safe_scope = scope.replace("/", "-").replace(" ", "_")
    filename = f"{platform}_{diagram_type}_{safe_scope}_v{version}.{ext}"
    return Path("output") / "diagrams" / engagement_slug / region_group / filename


def all_format_paths(  # noqa: PLR0913
    engagement_slug: str,
    region_group: str,
    platform: str,
    diagram_type: str,
    scope: str,
    version: str = "1.0.0",
) -> dict[str, Path]:
    """Return paths for all output formats of a single diagram."""
    return {
        ext: diagram_filename(
            engagement_slug, region_group, platform, diagram_type, scope, version, ext
        )
        for ext in OUTPUT_FORMATS
    }


def diagram_version_from_existing(output_dir: Path, base_name: str) -> str:
    """Scan existing files and return next patch version.
    Prevents overwriting — each discovery run produces a new version.
    """
    from cna.core.version_manager import bump_version

    existing = sorted(output_dir.glob(f"{base_name}_v*.drawio"))
    if not existing:
        return "1.0.0"
    last = existing[-1].stem  # e.g. aws_vpc_topology_us-east-1_v1.0.2
    version_part = last.rsplit("_v", 1)[-1]  # e.g. 1.0.2
    return bump_version(version_part, "patch")
