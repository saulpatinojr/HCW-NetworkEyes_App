"""VPC topology diagram entry point — Phase B.

Bridges discovery output (AWSRegionTopology) to diagram engine.
"""

from __future__ import annotations

from pathlib import Path

from cna.core.topology_schema import AWSRegionTopology
from cna.diagram_engine.drawio_generator import generate_vpc_topology
from cna.diagram_engine.export_pipeline import DiagramExporter


def render_vpc_topology(
    region_topology: AWSRegionTopology,
    output_dir: Path,
    skip_raster: bool = False,
) -> dict[str, Path]:
    """Generate and export VPC topology diagram for one AWS account+region.

    Args:
        region_topology: Discovered AWSRegionTopology model.
        output_dir: Where to write outputs.
        skip_raster: If True, write .drawio only (used in CI/test).

    Returns:
        Dict of format -> Path for all outputs produced.
    """
    xml = generate_vpc_topology(region_topology)
    name = f"vpc-topology-{region_topology.account_id}-{region_topology.region}"
    exporter = DiagramExporter(output_dir=output_dir, skip_raster=skip_raster)
    return exporter.export(xml, diagram_name=name)
