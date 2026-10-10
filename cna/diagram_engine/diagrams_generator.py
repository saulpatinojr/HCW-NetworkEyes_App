"""Mingrammer `diagrams` generator — Phase B Gap 1 closure.

Produces programmatic architecture-as-code PNG diagrams using the
`diagrams` library (https://diagrams.mingrammer.com/).

This is the third diagram format alongside draw.io and Mermaid:
  - draw.io  : editable, client-deliverable, relationship-rich
  - Mermaid  : text-based, version-controlled, portal/Markdown embedded
  - diagrams : code-driven, reproducible, AWS/Azure icon fidelity

Fallback: if `diagrams` is not installed, functions log a warning
and return None rather than crashing the engagement run.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("cna.diagram_engine.diagrams_generator")


def _diagrams_available() -> bool:
    try:
        import diagrams  # noqa: F401

        return True
    except ImportError:
        return False


def _render_aws_vpc_cluster(vpc, igw_nodes: dict, nat_nodes: dict) -> None:
    from diagrams import Edge
    from diagrams.aws.network import VPC as SubnetNode
    from diagrams.aws.network import InternetGateway, NATGateway

    for igw in vpc.internet_gateways:
        igw_node = InternetGateway(igw.name or igw.id)
        igw_nodes[igw.id] = igw_node

    for nat in vpc.nat_gateways:
        nat_node = NATGateway(nat.name or nat.id)
        nat_nodes[nat.id] = nat_node
        if igw_nodes:
            list(igw_nodes.values())[0] >> Edge(label="egress") >> nat_node

    for subnet in vpc.subnets:
        if subnet.subnet_type.value == "public":
            SubnetNode(f"{subnet.name or subnet.id}\n{subnet.cidr}")
        else:
            SubnetNode(f"{subnet.name or subnet.id}\n{subnet.cidr}")


def _render_aws_tgw_connections(region_topology, tgw_nodes: dict) -> None:
    from diagrams import Edge

    for tgw in region_topology.transit_gateways:
        if tgw.id in tgw_nodes:
            for attachment in tgw.attachments:
                for vpc in region_topology.vpcs:
                    if vpc.id == attachment.resource_id:
                        tgw_nodes[tgw.id] >> Edge(label=attachment.state)


def generate_aws_vpc_diagram(
    region_topology,  # AWSRegionTopology — avoid circular import at module level
    output_path: Path,
) -> Path | None:
    """Generate a Mingrammer diagrams PNG for all VPCs in an AWS region.

    Args:
        region_topology: AWSRegionTopology instance.
        output_path: Directory to write the PNG into.

    Returns:
        Path to generated PNG, or None if diagrams library unavailable.
    """
    if not _diagrams_available():
        logger.warning(
            "diagrams library not installed. Skipping Mingrammer output. "
            "Install with: pip install diagrams"
        )
        return None

    from diagrams import Cluster, Diagram
    from diagrams.aws.network import DirectConnect, TransitGateway

    output_path.mkdir(parents=True, exist_ok=True)
    safe_region = region_topology.region.replace("-", "_")
    filename = str(output_path / f"aws_vpc_{region_topology.account_id}_{safe_region}")

    graph_attr = {
        "fontsize": "12",
        "bgcolor": "white",
        "pad": "0.5",
        "splines": "ortho",
    }

    with Diagram(
        f"AWS VPC — {region_topology.account_id} / {region_topology.region}",
        filename=filename,
        show=False,
        graph_attr=graph_attr,
        outformat="png",
    ):
        igw_nodes = {}
        nat_nodes = {}
        tgw_nodes = {}

        # Transit Gateways at top level
        for tgw in region_topology.transit_gateways:
            tgw_label = tgw.name or tgw.id
            tgw_nodes[tgw.id] = TransitGateway(tgw_label)

        # Direct Connect
        for dx in region_topology.direct_connect_connections:
            dx_label = dx.name or dx.id
            DirectConnect(dx_label)

        # VPC clusters
        for vpc in region_topology.vpcs:
            vpc_label = vpc.name or vpc.id
            with Cluster(f"VPC: {vpc_label}\n{vpc.cidr}"):
                _render_aws_vpc_cluster(vpc, igw_nodes, nat_nodes)

        # TGW connections to VPCs via attachments
        _render_aws_tgw_connections(region_topology, tgw_nodes)

    result_path = Path(f"{filename}.png")
    if result_path.exists():
        logger.info("Written: %s", result_path)
        return result_path
    logger.warning("diagrams generator ran but produced no output at %s", result_path)
    return None


def generate_azure_vnet_diagram(
    sub_topology,  # AzureSubscriptionTopology
    output_path: Path,
) -> Path | None:
    """Generate a Mingrammer diagrams PNG for all VNets in an Azure subscription.

    Args:
        sub_topology: AzureSubscriptionTopology instance.
        output_path: Directory to write the PNG into.

    Returns:
        Path to generated PNG, or None if diagrams library unavailable.
    """
    if not _diagrams_available():
        logger.warning(
            "diagrams library not installed. Skipping Mingrammer output. "
            "Install with: pip install diagrams"
        )
        return None

    from diagrams import Cluster, Diagram, Edge
    from diagrams.azure.network import Subnets, VirtualNetworks

    output_path.mkdir(parents=True, exist_ok=True)
    safe_sub = sub_topology.subscription_id.replace("-", "_")[:16]
    filename = str(output_path / f"azure_vnet_{safe_sub}")

    graph_attr = {
        "fontsize": "12",
        "bgcolor": "white",
        "pad": "0.5",
        "splines": "ortho",
    }

    with Diagram(
        f"Azure VNet — {sub_topology.subscription_id}",
        filename=filename,
        show=False,
        graph_attr=graph_attr,
        outformat="png",
    ):
        for vnet in sub_topology.vnets:
            with Cluster(f"VNet: {vnet.name}\n{', '.join(vnet.address_space)}"):
                subnet_nodes = []
                for subnet in vnet.subnets:
                    sn_label = f"{subnet.name}\n{subnet.address_prefix}"
                    subnet_nodes.append(Subnets(sn_label))

                # Peering stubs
                for peering in vnet.peerings:
                    remote_name = peering.remote_vnet_name or peering.remote_vnet_id.split("/")[-1]
                    peer_node = VirtualNetworks(f"Peer: {remote_name}\n[{peering.peering_state}]")
                    if subnet_nodes:
                        subnet_nodes[0] >> Edge(label="peering", style="dashed") >> peer_node

    result_path = Path(f"{filename}.png")
    if result_path.exists():
        logger.info("Written: %s", result_path)
        return result_path
    logger.warning("diagrams generator ran but produced no output at %s", result_path)
    return None
