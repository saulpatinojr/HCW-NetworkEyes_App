"""AWS account hierarchy diagram entry point — Phase B."""

from __future__ import annotations

from pathlib import Path

from cna.core.topology_schema import AWSTopology
from cna.diagram_engine.mermaid_generator import generate_aws_account_hierarchy


def render_account_hierarchy(topology: AWSTopology, output_dir: Path) -> Path:
    """Write Mermaid account hierarchy to .mmd file.

    .mmd -> SVG conversion done by export_pipeline.mmdc_to_svg() (Phase B next).

    Returns:
        Path to written .mmd file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    mermaid_str = generate_aws_account_hierarchy(topology)
    out_path = output_dir / f"account-hierarchy-{topology.engagement_id}.mmd"
    out_path.write_text(mermaid_str, encoding="utf-8")
    return out_path
