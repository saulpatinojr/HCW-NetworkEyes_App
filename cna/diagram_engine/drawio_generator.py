"""draw.io XML generator — Phase B core.

Converts topology Pydantic models (cna.core.topology_schema) into
draw.io-compatible XML strings. Handles XML-unsafe characters, empty
resource sets, and oversized topologies gracefully.

Supported diagram types:
  - vpc_topology       : VPC + subnets + IGW + NAT + route table summary
  - vnet_topology      : VNet + subnets + peerings + route tables
  - tgw_topology       : Transit Gateway hub-and-spoke
  - vwan_topology      : Azure Virtual WAN hub-and-spoke
  - account_hierarchy  : AWS org tree (Mermaid, see mermaid_generator.py)
  - mg_hierarchy       : Azure management group tree (Mermaid)
  - future_state       : Recommended future-state topology (Phase E)

Export pipeline:
  XML string -> .drawio file -> export_pipeline.py -> .svg -> .png -> .pdf
"""

from __future__ import annotations

import html
import logging
import textwrap
import uuid

from cna.core.topology_schema import (
    AWSRegionTopology,
    AzureSubscriptionTopology,
    AzureTopology,
    AzureVWan,
    SubnetType,
    TransitGateway,
)
from cna.diagram_engine.future_state import (
    FutureStateModel,
    FutureStateNode,
    build_future_state,
)
from cna.diagram_engine.shape_catalog import shape_style
from cna.modules.network.analysis.topology_classifier import TopologyClassification

logger = logging.getLogger("cna.diagram_engine.drawio_generator")

# ── Draw.io style constants ─────────────────────────────────────────────────
#
# Constants below are FALLBACK defaults — they remain the runtime source of
# truth if the curated shape catalog (cna/diagram_engine/data/*_shapes.json)
# is missing or has been filtered to remove an entry. When the catalog has a
# match it wins; this lets us refresh icon styles by editing JSON (or via the
# in-app draw.io MCP `search_shapes` tool) without touching this file.

STYLE_VPC = (
    "rounded=1;whiteSpace=wrap;html=1;"
    "fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=11;fontStyle=1;"
    "verticalAlign=top;"
)
STYLE_VNET = (
    "rounded=1;whiteSpace=wrap;html=1;"
    "fillColor=#d5e8d4;strokeColor=#82b366;fontSize=11;fontStyle=1;"
    "verticalAlign=top;"
)
STYLE_SUBNET_PUBLIC = (
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;fontSize=10;"
)
STYLE_SUBNET_PRIVATE = (
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#f8cecc;strokeColor=#b85450;fontSize=10;"
)
STYLE_SUBNET_ISOLATED = (
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#e1d5e7;strokeColor=#9673a6;fontSize=10;"
)
STYLE_SUBNET_UNKNOWN = (
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#666666;fontSize=10;"
)
STYLE_IGW = shape_style(
    "aws4",
    "igw",
    "shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.internet_gateway;"
    "fillColor=#FF8000;strokeColor=#ffffff;fontStyle=1;fontSize=10;",
)
STYLE_NAT = shape_style(
    "aws4",
    "nat_gateway",
    "shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.nat_gateway;"
    "fillColor=#8C4FFF;strokeColor=#ffffff;fontStyle=1;fontSize=10;",
)
STYLE_TGW = shape_style(
    "aws4",
    "transit_gateway",
    "shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.transit_gateway;"
    "fillColor=#8C4FFF;strokeColor=#ffffff;fontStyle=1;fontSize=10;",
)
# The AWS "Network services" band (TODO.md T-418) — the region-level services
# discovery already captures but the VPC diagram used to leave off the page.
STYLE_DX = shape_style(
    "aws4",
    "direct_connect",
    "shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.direct_connect;"
    "fillColor=#8C4FFF;strokeColor=#ffffff;fontStyle=1;fontSize=10;",
)
STYLE_VPN_GW = shape_style(
    "aws4",
    "vpn_gateway",
    "shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.vpn_gateway;"
    "fillColor=#8C4FFF;strokeColor=#ffffff;fontStyle=1;fontSize=10;",
)
STYLE_NETWORK_FIREWALL = shape_style(
    "aws4",
    "network_firewall",
    "shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.network_firewall;"
    "fillColor=#DD344C;strokeColor=#ffffff;fontStyle=1;fontSize=10;",
)
STYLE_AWS_WAF = shape_style(
    "aws4",
    "waf",
    "shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.waf;"
    "fillColor=#DD344C;strokeColor=#ffffff;fontStyle=1;fontSize=10;",
)


def _azure_fallback(svg: str) -> str:
    """Fallback style for an Azure icon, in the only form draw.io renders.

    Azure icons are SVG image paths — `shape=mxgraph.azure2.*` is not a real
    stencil namespace and degrades to a plain blue rectangle (see
    shape_catalog.py). Fallbacks must therefore be image styles too, or a
    missing catalog entry silently reintroduces the blue box.
    """
    return (
        f"image;html=1;image=img/lib/azure2/networking/{svg}.svg;"
        "fontFamily=Helvetica;fontSize=10;"
        "verticalLabelPosition=bottom;verticalAlign=top;labelBackgroundColor=none;"
    )


STYLE_VWAN_HUB = shape_style("azure2", "vwan_hub", _azure_fallback("Virtual_WAN_Hub"))
STYLE_FIREWALL = shape_style("azure2", "firewall", _azure_fallback("Firewalls"))
STYLE_VNET_GATEWAY = shape_style(
    "azure2", "vnet_gateway", _azure_fallback("Virtual_Network_Gateways")
)
# Azure Route Server has no dedicated icon in the Azure2 palette; the virtual
# network gateway icon is the closest accurate stand-in for a routing appliance.
STYLE_ROUTE_SERVER = shape_style(
    "azure2", "route_server", _azure_fallback("Virtual_Network_Gateways")
)
STYLE_BASTION = shape_style("azure2", "bastion", _azure_fallback("Bastions"))
STYLE_AZ_NAT = shape_style("azure2", "nat_gateway", _azure_fallback("NAT"))
STYLE_AZ_LB = shape_style("azure2", "load_balancer", _azure_fallback("Load_Balancers"))
STYLE_APP_GATEWAY = shape_style(
    "azure2", "application_gateway", _azure_fallback("Application_Gateways")
)
STYLE_EXPRESSROUTE = shape_style("azure2", "expressroute", _azure_fallback("ExpressRoute_Circuits"))
STYLE_PRIVATE_ENDPOINT = shape_style(
    "azure2", "private_endpoint", _azure_fallback("Private_Endpoint")
)
STYLE_PRIVATE_DNS = shape_style("azure2", "private_dns_zone", _azure_fallback("DNS_Zones"))
STYLE_PUBLIC_IP = shape_style("azure2", "public_ip", _azure_fallback("Public_IP_Addresses"))
STYLE_WAF_POLICY = shape_style(
    "azure2", "waf_policy", _azure_fallback("Web_Application_Firewall_Policies_WAF")
)
STYLE_AZ_VWAN = shape_style("azure2", "vwan", _azure_fallback("Virtual_WANs"))
STYLE_EDGE = "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;exitX=0.5;"
STYLE_SERVICE_BAND = (
    "rounded=1;whiteSpace=wrap;html=1;fillColor=#eef6fc;strokeColor=#0078D4;"
    "dashed=1;fontSize=11;fontStyle=1;verticalAlign=top;align=left;spacingLeft=12;"
    "fontFamily=Helvetica;"
)

# Phase E: net-new (recommended) resources in future-state diagrams get a
# dashed bright-teal border (CBTS accent #00E9BB) and a "(recommended)" suffix.
RECOMMENDED_SUFFIX = " (recommended)"


def _recommended_style(style: str) -> str:
    """Overlay the dashed bright-teal 'recommended' treatment on any style."""
    return style + "dashed=1;dashPattern=6 4;strokeColor=#00E9BB;strokeWidth=2;"


SUBNET_STYLES: dict[SubnetType, str] = {
    SubnetType.PUBLIC: STYLE_SUBNET_PUBLIC,
    SubnetType.PRIVATE: STYLE_SUBNET_PRIVATE,
    SubnetType.ISOLATED: STYLE_SUBNET_ISOLATED,
    SubnetType.UNKNOWN: STYLE_SUBNET_UNKNOWN,
}

# ── Layout constants ─────────────────────────────────────────────────────

VPC_X_GAP = 60  # horizontal gap between VPCs
VPC_Y_START = 80
SUBNET_W = 180
SUBNET_H = 60
SUBNET_COL_GAP = 20
SUBNET_ROW_GAP = 20
SUBNET_PADDING = 20  # padding inside VPC container
ICON_W = 48
ICON_H = 48
SUBNETS_PER_ROW = 4
VPC_HEADER_H = 36
NAT_X_GAP = 60  # FIX P2: horizontal gap between NAT gateway icons


def _safe(text: str | None) -> str:
    """Escape XML-unsafe characters. Handles None gracefully."""
    if not text:
        return ""
    return html.escape(str(text), quote=True)


def _label(text: str | None) -> str:
    """Escape a cell label and turn newlines into real line breaks.

    Every style in this module sets html=1, under which a raw newline collapses
    to a single space — so the multi-line labels this generator has always
    written (name / CIDR / location) rendered as one run-on line.

    The break has to be written as an entity, not as a literal tag: `value` is
    an XML attribute, where a raw "<" is malformed and makes draw.io drop the
    cell (and, in practice, its siblings). Writing "&lt;br&gt;" here means the
    parsed attribute holds "<br>", which html=1 then renders as a line break.
    Escaping before substituting also keeps the substitution the only markup
    that can reach the label.
    """
    return _safe(text).replace("\n", "&lt;br&gt;")


def _truncate(text: str, limit: int = 24) -> str:
    """Shorten a resource name that would otherwise overrun its icon column."""
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


def _cell_id() -> str:
    return str(uuid.uuid4()).replace("-", "")[:16]


def _vpc_dims(subnet_count: int) -> tuple[int, int]:
    """Calculate VPC container width/height from subnet count."""
    cols = min(subnet_count, SUBNETS_PER_ROW) if subnet_count > 0 else 1
    rows = max(1, -(-subnet_count // SUBNETS_PER_ROW))  # ceiling div
    w = SUBNET_PADDING * 2 + cols * SUBNET_W + (cols - 1) * SUBNET_COL_GAP
    h = (
        VPC_HEADER_H
        + SUBNET_PADDING
        + rows * SUBNET_H
        + (rows - 1) * SUBNET_ROW_GAP
        + SUBNET_PADDING
    )
    return w, h


# ── XML helpers ───────────────────────────────────────────────────────────


def _container_cell(cell_id: str, label: str, x: int, y: int, w: int, h: int, style: str) -> str:  # noqa: PLR0913
    return (
        f'<mxCell id="{cell_id}" value="{_label(label)}" style="{style}" '
        f'vertex="1" parent="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/>'
        f"</mxCell>\n"
    )


def _child_cell(  # noqa: PLR0913
    cell_id: str, label: str, x: int, y: int, w: int, h: int, style: str, parent_id: str
) -> str:
    return (
        f'<mxCell id="{cell_id}" value="{_label(label)}" style="{style}" '
        f'vertex="1" parent="{parent_id}">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/>'
        f"</mxCell>\n"
    )


def _edge_cell(src: str, tgt: str, label: str = "") -> str:
    eid = _cell_id()
    return (
        f'<mxCell id="{eid}" value="{_safe(label)}" style="{STYLE_EDGE}" '
        f'edge="1" source="{src}" target="{tgt}" parent="1">'
        f'<mxGeometry relative="1" as="geometry"/>'
        f"</mxCell>\n"
    )


def _wrap_diagram(cells: str, label: str) -> str:
    return textwrap.dedent(f"""\
        <mxfile host="CNA" version="21.0.0">
          <diagram name="{_safe(label)}">
            <mxGraphModel dx="1422" dy="762" grid="1" gridSize="10"
              connect="1" arrows="1" fold="1" page="0"
              pageScale="1" pageWidth="1169" pageHeight="827"
              math="0" shadow="0">
              <root>
                <mxCell id="0"/>
                <mxCell id="1" parent="0"/>
                {cells}
              </root>
            </mxGraphModel>
          </diagram>
        </mxfile>
    """).strip()


# ── VPC Topology ───────────────────────────────────────────────────────────


def generate_vpc_topology(region_topology: AWSRegionTopology) -> str:
    """Generate draw.io XML for all VPCs in a single AWS region.

    Args:
        region_topology: Discovered AWSRegionTopology for one account+region.

    Returns:
        draw.io XML string. Empty diagram with a note if no VPCs discovered.

    Raises:
        ValueError: If region_topology.discovery_blocked is True
          (caller should check before invoking).
    """
    if region_topology.discovery_blocked:
        raise ValueError(
            f"Discovery was blocked for "
            f"{region_topology.account_id}/{region_topology.region}: "
            f"{region_topology.block_reason}. "
            "Cannot generate diagram from incomplete data."
        )

    cursor_x = 40

    # Region-level network services (transit gateways, Direct Connect, VPN
    # gateways, Network Firewall, WAF) render as a labelled band of AWS icons
    # above the VPCs — the same band the VNet diagram draws for Azure. A
    # region with none of them lays out exactly as before.
    cells, band_h = _service_band_cells(
        f"Network services — {region_topology.account_id} / {region_topology.region}",
        _aws_service_groups(region_topology),
        VPC_Y_START,
    )
    vpc_y = VPC_Y_START + (band_h + 40 if band_h else 0)

    if not region_topology.vpcs:
        note_id = _cell_id()
        cells += _container_cell(
            note_id,
            f"No VPCs found in {region_topology.account_id} / {region_topology.region}",
            40,
            vpc_y,
            400,
            60,
            "text;html=1;strokeColor=none;fillColor=#ffe6cc;align=center;",
        )
        label = f"VPC Topology — {region_topology.account_id} / {region_topology.region} (empty)"
        return _wrap_diagram(cells, label)

    for vpc in region_topology.vpcs:
        subnet_count = len(vpc.subnets)
        vpc_w, vpc_h = _vpc_dims(subnet_count)
        vpc_id = _cell_id()
        vpc_label = f"{vpc.name or vpc.id}\n{vpc.cidr}" + (" [default]" if vpc.is_default else "")
        cells += _container_cell(vpc_id, vpc_label, cursor_x, vpc_y, vpc_w, vpc_h, STYLE_VPC)

        # Subnets inside VPC container
        for idx, subnet in enumerate(vpc.subnets):
            col = idx % SUBNETS_PER_ROW
            row = idx // SUBNETS_PER_ROW
            sx = SUBNET_PADDING + col * (SUBNET_W + SUBNET_COL_GAP)
            sy = VPC_HEADER_H + SUBNET_PADDING + row * (SUBNET_H + SUBNET_ROW_GAP)
            sn_id = _cell_id()
            sn_label = (
                f"{subnet.name or subnet.id}\n"
                f"{subnet.cidr} | {subnet.az}\n"
                f"[{subnet.subnet_type.value}]"
                + (" \U0001f512" if not subnet.auto_assign_public_ip else " \U0001f310")
            )
            style = SUBNET_STYLES.get(subnet.subnet_type, STYLE_SUBNET_UNKNOWN)
            cells += _child_cell(sn_id, sn_label, sx, sy, SUBNET_W, SUBNET_H, style, vpc_id)

        # IGW icon centered above VPC
        igw_ids = []
        for igw in vpc.internet_gateways:
            igw_id = _cell_id()
            igw_x = cursor_x + vpc_w // 2 - ICON_W // 2
            igw_y = vpc_y - ICON_H - 20
            igw_label = igw.name or igw.id
            cells += _container_cell(igw_id, igw_label, igw_x, igw_y, ICON_W, ICON_H, STYLE_IGW)
            cells += _edge_cell(igw_id, vpc_id)
            igw_ids.append(igw_id)

        # FIX P2: NAT gateway icons laid out horizontally below the VPC.
        # nat_x advances by NAT_X_GAP per gateway so multi-AZ NATs
        # (a common prod pattern) are distinct nodes, not stacked on top of each other.
        nat_base_x = cursor_x + SUBNET_PADDING
        nat_y = vpc_y + vpc_h + 10
        for nat_idx, nat in enumerate(vpc.nat_gateways):
            nat_id = _cell_id()
            nat_x = nat_base_x + nat_idx * (ICON_W + NAT_X_GAP)
            nat_label = f"{nat.name or nat.id}\n{nat.public_ip or ''}"
            cells += _container_cell(nat_id, nat_label, nat_x, nat_y, ICON_W, ICON_H, STYLE_NAT)
            cells += _edge_cell(vpc_id, nat_id)

        cursor_x += vpc_w + VPC_X_GAP

    label = f"VPC Topology — {region_topology.account_id} / {region_topology.region}"
    return _wrap_diagram(cells, label)


# ── VNet Topology ──────────────────────────────────────────────────────────


# ── Network services band (both clouds) ────────────────────────────────────
#
# The VNet and VPC diagrams used to show networks, subnets and peerings only,
# which left every firewall, gateway, bastion and load balancer the discovery
# already captured off the page. These render as a labelled band of real
# cloud icons above the networks, so the diagram reflects what was actually
# found. The layout is cloud-neutral; each cloud contributes its own list of
# (label, style, names) groups.

SERVICE_ICON_W = 48
SERVICE_ICON_H = 48
SERVICE_COL_GAP = 132
SERVICE_ROW_H = 108
SERVICE_BAND_PADDING = 20
SERVICE_BAND_HEADER_H = 30
SERVICES_PER_ROW = 6
# Per resource type: draw this many named icons, then summarise the remainder.
# Keeps a subscription with 200 private endpoints from producing 200 icons.
MAX_ICONS_PER_TYPE = 4


def _azure_service_groups(sub: AzureSubscriptionTopology) -> list[tuple[str, str, list[str]]]:
    """Return (label, style, names) per network service type actually present."""
    groups: list[tuple[str, str, list[str]]] = [
        ("Firewall", STYLE_FIREWALL, [f.name for f in sub.firewalls]),
        ("VNet Gateway", STYLE_VNET_GATEWAY, [g.name for g in sub.virtual_network_gateways]),
        ("ExpressRoute", STYLE_EXPRESSROUTE, [c.name for c in sub.express_route_circuits]),
        ("Virtual WAN", STYLE_AZ_VWAN, [w.name for w in sub.virtual_wans]),
        ("Route Server", STYLE_ROUTE_SERVER, [r.name for r in sub.route_servers]),
        ("App Gateway", STYLE_APP_GATEWAY, [a.name for a in sub.application_gateways]),
        ("Load Balancer", STYLE_AZ_LB, [lb.name for lb in sub.load_balancers]),
        ("WAF Policy", STYLE_WAF_POLICY, [w.name for w in sub.front_door_waf_policies]),
        ("Bastion", STYLE_BASTION, [b.name for b in sub.bastion_hosts]),
        ("NAT Gateway", STYLE_AZ_NAT, [n.name for n in sub.nat_gateways]),
        ("Private Endpoint", STYLE_PRIVATE_ENDPOINT, [p.name for p in sub.private_endpoints]),
        ("Private DNS", STYLE_PRIVATE_DNS, [z.name for z in sub.private_dns_zones]),
        ("Public IP", STYLE_PUBLIC_IP, [p.name for p in sub.public_ips]),
    ]
    return [g for g in groups if g[2]]


def _aws_service_groups(region: AWSRegionTopology) -> list[tuple[str, str, list[str]]]:
    """Return (label, style, names) per AWS network service type actually present.

    Transit gateways, Direct Connect, VPN gateways, Network Firewall and WAF
    are what `AWSRegionTopology` carries today; VPC endpoints and Shield are
    not discovered yet and join this list when they are.
    """
    groups: list[tuple[str, str, list[str]]] = [
        ("Transit Gateway", STYLE_TGW, [t.name or t.id for t in region.transit_gateways]),
        (
            "Direct Connect",
            STYLE_DX,
            [c.name or c.id for c in region.direct_connect_connections],
        ),
        ("VPN Gateway", STYLE_VPN_GW, [g.name or g.id for g in region.vpn_gateways]),
        (
            "Network Firewall",
            STYLE_NETWORK_FIREWALL,
            [f.firewall_name for f in region.aws_network_firewalls]
            + [p.name for p in region.network_firewalls],
        ),
        ("WAF Web ACL", STYLE_AWS_WAF, [w.name for w in region.waf_web_acls]),
    ]
    return [g for g in groups if g[2]]


def _service_band_cells(
    title: str, groups: list[tuple[str, str, list[str]]], y: int
) -> tuple[str, int]:
    """Render the services band `title` for `groups` at `y`. Returns (cells, band_height).

    An empty band renders nothing and reports zero height, so a scope with no
    discovered network services lays out exactly as before.
    """
    if not groups:
        return "", 0

    # One slot per icon drawn, plus one slot for each type that overflows.
    slots: list[tuple[str, str]] = []  # (style, label)
    for label, style, names in groups:
        for name in names[:MAX_ICONS_PER_TYPE]:
            slots.append((style, f"{_truncate(name)}\n{label}"))
        overflow = len(names) - MAX_ICONS_PER_TYPE
        if overflow > 0:
            slots.append((style, f"+{overflow} more\n{label}"))

    rows = max(1, -(-len(slots) // SERVICES_PER_ROW))  # ceiling div
    cols = min(len(slots), SERVICES_PER_ROW)
    band_w = SERVICE_BAND_PADDING * 2 + cols * SERVICE_COL_GAP
    band_h = SERVICE_BAND_HEADER_H + SERVICE_BAND_PADDING + rows * SERVICE_ROW_H

    band_id = _cell_id()
    cells = _container_cell(
        band_id,
        title,
        40,
        y,
        band_w,
        band_h,
        STYLE_SERVICE_BAND,
    )
    for idx, (style, label) in enumerate(slots):
        col = idx % SERVICES_PER_ROW
        row = idx // SERVICES_PER_ROW
        sx = SERVICE_BAND_PADDING + col * SERVICE_COL_GAP
        sy = SERVICE_BAND_HEADER_H + row * SERVICE_ROW_H
        # Nudge the icon to its column centre so the wider label beneath it
        # stays inside the band instead of colliding with its neighbour.
        cells += _child_cell(
            _cell_id(),
            label,
            sx + (SERVICE_COL_GAP - SERVICE_ICON_W) // 2,
            sy,
            SERVICE_ICON_W,
            SERVICE_ICON_H,
            style,
            band_id,
        )
    return cells, band_h


def generate_vnet_topology(sub_topology: AzureSubscriptionTopology) -> str:
    """Generate draw.io XML for all VNets in an Azure subscription."""
    if sub_topology.discovery_blocked:
        raise ValueError(
            f"Discovery was blocked for subscription "
            f"{sub_topology.subscription_id}: {sub_topology.block_reason}. "
            "Cannot generate diagram from incomplete data."
        )

    # Subscription-level network services render above the VNets; the VNet row
    # starts below whatever height that band needed.
    cells, band_h = _service_band_cells(
        f"Network services — {sub_topology.subscription_name or sub_topology.subscription_id}",
        _azure_service_groups(sub_topology),
        VPC_Y_START,
    )
    vnet_y = VPC_Y_START + (band_h + 40 if band_h else 0)
    cursor_x = 40

    if not sub_topology.vnets:
        note_id = _cell_id()
        cells += _container_cell(
            note_id,
            f"No VNets found in subscription {sub_topology.subscription_id}",
            40,
            vnet_y,
            420,
            60,
            "text;html=1;strokeColor=none;fillColor=#ffe6cc;align=center;",
        )
        label = f"VNet Topology — {sub_topology.subscription_id} (empty)"
        return _wrap_diagram(cells, label)

    for vnet in sub_topology.vnets:
        subnet_count = len(vnet.subnets)
        vnet_w, vnet_h = _vpc_dims(subnet_count)
        vnet_id = _cell_id()
        vnet_label = (
            f"{vnet.name}\n{', '.join(vnet.address_space)}\n{vnet.location} | {vnet.resource_group}"
        )
        cells += _container_cell(vnet_id, vnet_label, cursor_x, vnet_y, vnet_w, vnet_h, STYLE_VNET)

        for idx, subnet in enumerate(vnet.subnets):
            col = idx % SUBNETS_PER_ROW
            row = idx // SUBNETS_PER_ROW
            sx = SUBNET_PADDING + col * (SUBNET_W + SUBNET_COL_GAP)
            sy = VPC_HEADER_H + SUBNET_PADDING + row * (SUBNET_H + SUBNET_ROW_GAP)
            sn_id = _cell_id()
            nsg_indicator = " \U0001f512" if subnet.nsg_id else " \u26a0\ufe0f"
            sn_label = (
                f"{subnet.name}\n"
                f"{subnet.address_prefix}"
                + (f"\n{subnet.delegation}" if subnet.delegation else "")
                + nsg_indicator
            )
            # Colour by the classifier's verdict — painting every subnet with
            # the private style hid public exposure, the thing the diagram is
            # most often read to check.
            subnet_style = SUBNET_STYLES.get(subnet.subnet_type, STYLE_SUBNET_UNKNOWN)
            cells += _child_cell(sn_id, sn_label, sx, sy, SUBNET_W, SUBNET_H, subnet_style, vnet_id)

        for peering in vnet.peerings:
            peer_note_id = _cell_id()
            peer_x = cursor_x + vnet_w + 40
            peer_y = vnet_y + 20
            remote_name = peering.remote_vnet_name or peering.remote_vnet_id.split("/")[-1]
            cells += _container_cell(
                peer_note_id,
                f"\u21c4 {remote_name}\n[{peering.peering_state}]",
                peer_x,
                peer_y,
                160,
                50,
                "rounded=1;fillColor=#fff2cc;strokeColor=#d6b656;fontSize=9;",
            )
            cells += _edge_cell(vnet_id, peer_note_id, peering.name)

        cursor_x += vnet_w + VPC_X_GAP

    label = f"VNet Topology — {sub_topology.subscription_id}"
    return _wrap_diagram(cells, label)


# ── TGW Hub-and-Spoke ──────────────────────────────────────────────────────


def generate_tgw_topology(tgw: TransitGateway, region_topology: AWSRegionTopology) -> str:
    """Generate draw.io XML for a single Transit Gateway and all its attachments."""
    import math

    cells = ""
    center_x, center_y = 500, 400
    tgw_id = _cell_id()
    tgw_label = f"{tgw.name or tgw.id}\n{tgw.owner_account_id}\nASN:{tgw.amazon_side_asn or 'N/A'}"
    cells += _container_cell(
        tgw_id, tgw_label, center_x, center_y, ICON_W * 2, ICON_H * 2, STYLE_TGW
    )

    count = len(tgw.attachments)
    radius = max(250, count * 40)
    for i, attachment in enumerate(tgw.attachments):
        angle = (2 * math.pi * i) / max(count, 1)
        ax = int(center_x + radius * math.cos(angle) - SUBNET_W // 2)
        ay = int(center_y + radius * math.sin(angle) - SUBNET_H // 2)
        att_id = _cell_id()
        display_name = attachment.resource_id
        for vpc in region_topology.vpcs:
            if vpc.id == attachment.resource_id:
                display_name = vpc.name or vpc.id
                break
        att_label = f"{display_name}\n[{attachment.resource_type.value}]\n{attachment.state}"
        cells += _container_cell(
            att_id, att_label, ax, ay, SUBNET_W, SUBNET_H, STYLE_SUBNET_PRIVATE
        )
        cells += _edge_cell(tgw_id, att_id)

    label = f"TGW Topology — {tgw.name or tgw.id}"
    return _wrap_diagram(cells, label)


# ── Azure Virtual WAN Hub-and-Spoke ───────────────────────────────────────


def generate_vwan_topology(vwan: AzureVWan) -> str:
    """Generate draw.io XML for an Azure Virtual WAN and all its hubs."""
    import math

    cells = ""
    count = len(vwan.hubs)

    if count == 0:
        note_id = _cell_id()
        cells += _container_cell(
            note_id,
            f"Virtual WAN {vwan.name} has no hubs.",
            40,
            80,
            360,
            60,
            "text;html=1;strokeColor=none;fillColor=#ffe6cc;align=center;",
        )
        return _wrap_diagram(cells, f"vWAN Topology — {vwan.name} (empty)")

    center_x, center_y = 500, 400
    vwan_id = _cell_id()
    vwan_label = f"vWAN: {vwan.name}\n[{vwan.sku}]"
    cells += _container_cell(
        vwan_id, vwan_label, center_x, center_y, ICON_W * 2, ICON_H, STYLE_VWAN_HUB
    )

    radius = max(300, count * 60)
    for i, hub in enumerate(vwan.hubs):
        angle = (2 * math.pi * i) / count
        hx = int(center_x + radius * math.cos(angle) - ICON_W)
        hy = int(center_y + radius * math.sin(angle) - ICON_H)
        hub_id = _cell_id()
        fw_note = " \U0001f525 AFW" if hub.azure_firewall_id else ""
        er_note = " \U0001f517 ER" if hub.express_route_gateway_id else ""
        hub_label = (
            f"{hub.name}\n"
            f"{hub.location} | {hub.address_prefix}\n"
            f"[{hub.routing_state}]{fw_note}{er_note}"
        )
        cells += _container_cell(hub_id, hub_label, hx, hy, SUBNET_W, SUBNET_H + 20, STYLE_VWAN_HUB)
        cells += _edge_cell(vwan_id, hub_id)

        for j, vnet_id_str in enumerate(hub.connected_vnet_ids[:8]):
            vnet_spoke_id = _cell_id()
            vnet_name = vnet_id_str.split("/")[-1]
            inner_radius = 120
            inner_angle = angle + (math.pi / 4 * (j - len(hub.connected_vnet_ids) / 2))
            vx = int(hx + inner_radius * math.cos(inner_angle))
            vy = int(hy + inner_radius * math.sin(inner_angle))
            cells += _container_cell(vnet_spoke_id, vnet_name, vx, vy, 120, 40, STYLE_VNET)
            cells += _edge_cell(hub_id, vnet_spoke_id)

    label = f"vWAN Topology — {vwan.name}"
    return _wrap_diagram(cells, label)


# ── Future-State Topology (Phase E) ────────────────────────────────────────

_FUTURE_COMPONENT_STYLES: dict[str, str] = {
    "firewall": STYLE_FIREWALL,
    "gateway": STYLE_VNET_GATEWAY,
    "route_server": STYLE_ROUTE_SERVER,
}

_FUTURE_HUB_W = 520
_FUTURE_HUB_H = 160
_FUTURE_HUB_GAP = 80
_FUTURE_SPOKE_Y_GAP = 120
_FUTURE_SPOKES_PER_ROW = 5


def _future_node_style(node: FutureStateNode, base_style: str) -> str:
    return _recommended_style(base_style) if node.is_new else base_style


def _future_node_label(node: FutureStateNode) -> str:
    label = node.name + (f"\n{node.location}" if node.location else "")
    return label + (RECOMMENDED_SUFFIX if node.is_new else "")


def generate_future_state_topology(
    topology: AzureTopology,
    classification: TopologyClassification,
    future: FutureStateModel | None = None,
) -> str:
    """Generate draw.io XML for the recommended future-state topology.

    Args:
        topology: Discovered AzureTopology checkpoint.
        classification: Output of classify_topology(topology).
        future: Pre-built future-state model; built from the inputs when None.

    Returns:
        draw.io XML string. Net-new (recommended) resources are rendered with
        a dashed bright-teal border and a "(recommended)" label suffix.
    """
    if future is None:
        future = build_future_state(topology, classification)

    cells = ""
    hub_style_base = STYLE_VWAN_HUB if future.target_pattern == "vwan" else STYLE_VNET

    if not future.hubs and not future.spokes:
        note_id = _cell_id()
        cells += _container_cell(
            note_id,
            "No VNets discovered — no future-state topology to model.",
            40,
            80,
            420,
            60,
            "text;html=1;strokeColor=none;fillColor=#ffe6cc;align=center;",
        )
        return _wrap_diagram(cells, "Future State Topology (empty)")

    # Hubs in a row at the top, components laid out inside each hub container
    hub_cell_ids: list[str] = []
    cursor_x = 40
    for hub in future.hubs:
        hub_id = _cell_id()
        hub_cell_ids.append(hub_id)
        cells += _container_cell(
            hub_id,
            _future_node_label(hub),
            cursor_x,
            VPC_Y_START,
            _FUTURE_HUB_W,
            _FUTURE_HUB_H,
            _future_node_style(hub, hub_style_base),
        )
        # Components named after a specific hub (e.g. secured-hub firewalls)
        # land in that hub; everything else lands in the first hub.
        comps = []
        for c in future.hub_components:
            named_hub = next((h for h in future.hubs if h.name in c.name), None)
            target = named_hub or future.hubs[0]
            if target is hub:
                comps.append(c)
        comp_x = SUBNET_PADDING
        comp_y = VPC_HEADER_H + SUBNET_PADDING
        for comp in comps:
            comp_id = _cell_id()
            base = _FUTURE_COMPONENT_STYLES.get(comp.kind, STYLE_SUBNET_UNKNOWN)
            cells += _child_cell(
                comp_id,
                _future_node_label(comp),
                comp_x,
                comp_y,
                ICON_W * 2,
                ICON_H + 24,
                _future_node_style(comp, base),
                hub_id,
            )
            comp_x += ICON_W * 2 + SUBNET_COL_GAP * 2
        cursor_x += _FUTURE_HUB_W + _FUTURE_HUB_GAP

    # Spokes in a grid below the hub row, each peered to the nearest hub
    spoke_y_start = VPC_Y_START + _FUTURE_HUB_H + _FUTURE_SPOKE_Y_GAP
    for idx, spoke in enumerate(future.spokes):
        col = idx % _FUTURE_SPOKES_PER_ROW
        row = idx // _FUTURE_SPOKES_PER_ROW
        sx = 40 + col * (SUBNET_W + SUBNET_COL_GAP * 2)
        sy = spoke_y_start + row * (SUBNET_H + SUBNET_ROW_GAP * 2)
        spoke_id = _cell_id()
        cells += _container_cell(
            spoke_id,
            _future_node_label(spoke),
            sx,
            sy,
            SUBNET_W,
            SUBNET_H,
            _future_node_style(spoke, STYLE_VNET),
        )
        if hub_cell_ids:
            hub_cell = hub_cell_ids[idx % len(hub_cell_ids)]
            edge_label = "peering" + (
                RECOMMENDED_SUFFIX
                if spoke.is_new or future.hubs[idx % len(future.hubs)].is_new
                else ""
            )
            cells += _edge_cell(hub_cell, spoke_id, edge_label)

    # Change list as a side legend so the diagram is self-explanatory
    legend_x = 40
    legend_y = (
        spoke_y_start
        + (
            (max(1, -(-len(future.spokes) // _FUTURE_SPOKES_PER_ROW)))
            * (SUBNET_H + SUBNET_ROW_GAP * 2)
        )
        + 60
    )
    for change in future.changes:
        note_id = _cell_id()
        cells += _container_cell(
            note_id,
            f"→ {change.title}",
            legend_x,
            legend_y,
            420,
            36,
            "rounded=1;whiteSpace=wrap;html=1;fillColor=none;"
            "dashed=1;dashPattern=6 4;strokeColor=#00E9BB;fontSize=10;align=left;spacingLeft=8;",
        )
        legend_y += 46

    label = f"Future State Topology — {future.target_pattern}"
    return _wrap_diagram(cells, label)


# ── Multi-page assembly ────────────────────────────────────────────────────


def merge_diagrams(pages: list[tuple[str, str]]) -> str:
    """Combine single-page diagram XML strings into one multi-page .drawio file.

    Each generator here emits a complete `<mxfile>` with exactly one
    `<diagram>`. draw.io shows one tab per `<diagram>`, so an engagement that
    spans several subscriptions or regions belongs in one file with one tab
    each rather than in several files the consultant has to open separately.

    `pages` is a list of (tab_name, single_page_xml). Inputs that cannot be
    parsed are skipped rather than failing the whole bundle — a malformed page
    from one scope should not cost the consultant every other scope.
    """
    # defusedxml, not xml.dom: these strings reach us through the API from
    # persisted discovery data, so the parser must not honour entity expansion.
    from defusedxml import minidom  # noqa: PLC0415 — only needed on this path

    fragments: list[str] = []
    for name, xml in pages:
        if not xml or not xml.strip():
            continue
        try:
            doc = minidom.parseString(xml)
        except Exception as exc:  # noqa: BLE001 — one bad page must not sink the file
            logger.warning("skipping unparseable diagram page %r: %s", name, exc)
            continue
        for node in doc.getElementsByTagName("diagram"):
            node.setAttribute("name", name)
            node.setAttribute("id", _cell_id())
            fragments.append(node.toxml())

    if not fragments:
        # An empty bundle still has to be a valid, openable document.
        fragments.append(
            f'<diagram name="No topology" id="{_cell_id()}">'
            '<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
            "</root></mxGraphModel></diagram>"
        )

    body = "\n  ".join(fragments)
    return f'<mxfile host="CNA" version="21.0.0">\n  {body}\n</mxfile>'
