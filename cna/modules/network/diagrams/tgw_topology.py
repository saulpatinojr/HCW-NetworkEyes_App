"""Transit Gateway topology diagram entry point — Phase B."""

from __future__ import annotations

from pathlib import Path

from cna.core.topology_schema import AWSRegionTopology
from cna.diagram_engine.drawio_generator import generate_tgw_topology
from cna.diagram_engine.export_pipeline import DiagramExporter


def render_tgw_topology(
    region_topology: AWSRegionTopology,
    output_dir: Path,
    skip_raster: bool = False,
) -> dict[str, dict[str, Path]]:
    """Generate TGW hub-and-spoke diagrams for all TGWs in a region.

    Note the return shape differs from its siblings. `render_vpc_topology` and
    `render_vnet_topology` each render a single diagram and return
    `DiagramExporter.export()` directly, i.e. format -> Path. This one renders
    one diagram per transit gateway, so it nests: TGW id -> format -> Path. The
    annotation previously claimed the flat shape (TODO.md T-410).
    """
    paths: dict[str, dict[str, Path]] = {}
    for tgw in region_topology.transit_gateways:
        xml = generate_tgw_topology(tgw, region_topology)
        name = f"tgw-topology-{tgw.id}-{region_topology.region}"
        exporter = DiagramExporter(output_dir=output_dir, skip_raster=skip_raster)
        result = exporter.export(xml, diagram_name=name)
        paths[tgw.id] = result
    return paths
