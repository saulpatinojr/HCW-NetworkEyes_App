"""C4 layering helpers for draw.io deliverables.

We adopt the C4 model (https://c4model.com) to map each diagram to one of the
three CNA deliverable audiences:

  * Context   → executive deliverable (system-of-systems, no internals)
  * Container → architect deliverable (regions, VPCs/VNets, hubs, gateways)
  * Component → engineer deliverable (subnets, route tables, NSGs, peerings)

Each layer is a thin façade over the existing draw.io generators in
`drawio_generator.py`. The container layer is the one we already produce
today; the context layer summarises it; the component layer is the existing
detailed output. This file does not import the heavy generator at import time
so unit tests can stub it out cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class C4Layer(StrEnum):
    CONTEXT = "context"
    CONTAINER = "container"
    COMPONENT = "component"


# Audience routing — matches DeliverableRecord.audience values added in this
# sprint. The portal uses these tags to gate diagrams to the right reader.
AUDIENCE_BY_LAYER: dict[C4Layer, str] = {
    C4Layer.CONTEXT: "executive",
    C4Layer.CONTAINER: "architect",
    C4Layer.COMPONENT: "engineer",
}


@dataclass(frozen=True)
class C4Diagram:
    layer: C4Layer
    name: str
    xml: str

    @property
    def audience(self) -> str:
        return AUDIENCE_BY_LAYER[self.layer]


def build_context_xml(system_label: str, child_labels: list[str]) -> str:
    """Render a minimal Context diagram: one system box, one box per top-level child.

    `system_label` is the engagement / customer name.
    `child_labels` are accounts, subscriptions, or major business units —
    whatever the executive should see at the top of the deck.
    """
    from cna.diagram_engine.drawio_generator import (
        _cell_id,
        _container_cell,
        _edge_cell,
        _safe,
        _wrap_diagram,
    )

    cells = ""
    sys_id = _cell_id()
    cells += _container_cell(
        sys_id,
        _safe(system_label),
        500,
        80,
        260,
        80,
        "rounded=1;whiteSpace=wrap;html=1;fillColor=#1168bd;strokeColor=#0b4884;"
        "fontColor=#ffffff;fontSize=14;fontStyle=1;verticalAlign=middle;align=center;",
    )
    x = 80
    y = 260
    per_row = 4
    box_w = 220
    box_h = 70
    x_gap = 40
    y_gap = 30
    for idx, label in enumerate(child_labels or ["(no top-level systems discovered)"]):
        col = idx % per_row
        row = idx // per_row
        cx = x + col * (box_w + x_gap)
        cy = y + row * (box_h + y_gap)
        child_id = _cell_id()
        cells += _container_cell(
            child_id,
            _safe(label),
            cx,
            cy,
            box_w,
            box_h,
            "rounded=1;whiteSpace=wrap;html=1;fillColor=#438dd5;strokeColor=#2e6295;"
            "fontColor=#ffffff;fontSize=12;verticalAlign=middle;align=center;",
        )
        cells += _edge_cell(sys_id, child_id)
    return _wrap_diagram(cells, f"Context — {system_label}")


def classify_existing(layer: C4Layer, name: str, xml: str) -> C4Diagram:
    """Wrap an already-rendered XML payload with C4 metadata."""
    return C4Diagram(layer=layer, name=name, xml=xml)
