"""VNet topology diagram entry point — Phase B."""

from __future__ import annotations

from pathlib import Path

from cna.core.topology_schema import AzureSubscriptionTopology
from cna.diagram_engine.drawio_generator import generate_vnet_topology
from cna.diagram_engine.export_pipeline import DiagramExporter


def render_vnet_topology(
    sub_topology: AzureSubscriptionTopology,
    output_dir: Path,
    skip_raster: bool = False,
) -> dict[str, Path]:
    """Generate and export VNet topology diagram for one Azure subscription."""
    xml = generate_vnet_topology(sub_topology)
    name = f"vnet-topology-{sub_topology.subscription_id}"
    exporter = DiagramExporter(output_dir=output_dir, skip_raster=skip_raster)
    return exporter.export(xml, diagram_name=name)
