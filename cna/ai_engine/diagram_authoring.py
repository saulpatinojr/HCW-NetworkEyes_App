"""Diagram authoring orchestrator — produces a C4-layered draw.io bundle.

Inputs: discovered topologies (from cna.core.topology_schema).
Outputs: list of `C4Diagram` payloads — one context diagram plus one container
diagram per discovered scope.

This module is the seam between discovery+analysis (already on-disk) and the
draw.io render pipeline. It is intentionally synchronous and side-effect free
— the worker hooks it after analysis and forwards the result to the export
pipeline + manifest. Failures degrade gracefully: a missing or partial
topology yields fewer diagrams, not an exception.

Optional integration with the in-app draw.io MCP surface is via
`DrawioMCPClient.health()` — we log when it is reachable so operators can
verify the studio is functional from the worker. The actual icon styles come
from the local shape catalog (offline-deterministic).
"""

from __future__ import annotations

import logging

from cna.ai_engine.mcp_client.drawio_mcp_client import DrawioMCPClient
from cna.core.topology_schema import AWSRegionTopology, AzureSubscriptionTopology
from cna.diagram_engine.c4_layering import C4Diagram, C4Layer, build_context_xml
from cna.diagram_engine.drawio_generator import (
    generate_vnet_topology,
    generate_vpc_topology,
)

logger = logging.getLogger("cna.ai_engine.diagram_authoring")


def _probe_mcp_health(mcp_client: DrawioMCPClient | None) -> None:
    if mcp_client is None:
        return
    try:
        if mcp_client.health():
            logger.info("draw.io MCP surface reachable")
        else:
            logger.info("draw.io MCP surface unreachable; offline catalog only")
    except Exception:  # noqa: BLE001
        logger.info("draw.io MCP health probe raised; ignoring")


def _aws_region_diagrams(aws_regions: list[AWSRegionTopology]) -> list[C4Diagram]:
    diagrams: list[C4Diagram] = []
    for r in aws_regions:
        if r.discovery_blocked:
            continue
        try:
            xml = generate_vpc_topology(r)
        except Exception as e:  # noqa: BLE001
            logger.warning("generate_vpc_topology failed for %s/%s: %s", r.account_id, r.region, e)
            continue
        scope = f"aws-{r.account_id}-{r.region}"
        diagrams.append(C4Diagram(layer=C4Layer.CONTAINER, name=f"container-{scope}", xml=xml))
    return diagrams


def _azure_sub_diagrams(azure_subs: list[AzureSubscriptionTopology]) -> list[C4Diagram]:
    diagrams: list[C4Diagram] = []
    for s in azure_subs:
        if s.discovery_blocked:
            continue
        try:
            xml = generate_vnet_topology(s)
        except Exception as e:  # noqa: BLE001
            logger.warning("generate_vnet_topology failed for %s: %s", s.subscription_id, e)
            continue
        scope = f"azure-{s.subscription_id}"
        diagrams.append(C4Diagram(layer=C4Layer.CONTAINER, name=f"container-{scope}", xml=xml))
    return diagrams


def author_engagement_bundle(
    engagement_label: str,
    aws_regions: list[AWSRegionTopology] | None = None,
    azure_subs: list[AzureSubscriptionTopology] | None = None,
    *,
    mcp_client: DrawioMCPClient | None = None,
) -> list[C4Diagram]:
    """Produce a context + container diagram bundle.

    Returns a flat list of C4Diagram objects. Callers iterate and hand each
    one to the existing export pipeline + deliverable manifest.

    The COMPONENT (engineer) layer is deliberately absent: until it draws
    something the CONTAINER layer does not — route tables, NSG rules and
    effective routes are the candidates — emitting it would only hand the
    consultant a second identical tab (TODO.md T-418).
    """
    aws_regions = aws_regions or []
    azure_subs = azure_subs or []

    _probe_mcp_health(mcp_client)

    children: list[str] = []
    for r in aws_regions:
        children.append(f"AWS {r.account_id} / {r.region}")
    for s in azure_subs:
        children.append(f"Azure sub {s.subscription_id}")

    bundle: list[C4Diagram] = [
        C4Diagram(
            layer=C4Layer.CONTEXT,
            name="context",
            xml=build_context_xml(engagement_label, children),
        )
    ]

    # Container (architect view), one per discovered scope.
    bundle.extend(_aws_region_diagrams(aws_regions))
    bundle.extend(_azure_sub_diagrams(azure_subs))

    return bundle
