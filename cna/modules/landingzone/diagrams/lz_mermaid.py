"""Landing zone architecture diagram entry point — Phase B.

DD-011: Mermaid-based documentation, not IaC.
"""

from __future__ import annotations

from pathlib import Path

from cna.diagram_engine.mermaid_generator import generate_landing_zone_diagram


def render_lz_diagram(
    platform: str,
    design_notes: dict,
    output_dir: Path,
    engagement_id: str,
) -> Path:
    """Generate landing zone Mermaid diagram and write .mmd file.

    Args:
        platform: 'aws' | 'azure'
        design_notes: Dict with management_layer, connectivity_layer,
          workload_layers, security_controls keys.
        output_dir: Where to write output.
        engagement_id: Used in filename.

    Returns:
        Path to written .mmd file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    mermaid_str = generate_landing_zone_diagram(platform, design_notes)
    out_path = output_dir / f"lz-architecture-{platform}-{engagement_id}.mmd"
    out_path.write_text(mermaid_str, encoding="utf-8")
    return out_path
