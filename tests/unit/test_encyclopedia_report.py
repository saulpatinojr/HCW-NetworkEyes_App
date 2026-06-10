"""Unit tests for cna.report_engine.encyclopedia_report (Phase D)."""

from __future__ import annotations

from datetime import datetime

import pytest

from cna.core.findings_schema import (
    Finding,
    FindingRecommendation,
    FrameworkMapping,
)
from cna.core.stat_masters import build_stat_masters
from cna.core.topology_schema import (
    AzureFirewall,
    AzurePublicIP,
    AzureSubnet,
    AzureSubscriptionTopology,
    AzureTopology,
    AzureVirtualNetworkGateway,
    ObservabilityData,
    VNet,
    VNetPeering,
)
from cna.diagram_engine.future_state import build_future_state
from cna.modules.network.analysis.topology_classifier import classify_topology
from cna.report_engine.encyclopedia_report import (
    EDITION_CONDENSED,
    EDITION_EXPANDED,
    EncyclopediaReportRenderer,
    build_encyclopedia_context,
    build_maturity_dimensions,
    normalize_finding,
)
from cna.report_engine.radar_chart import radar_chart_svg

# ── Fixtures ───────────────────────────────────────────────────────────────────


def _finding(rule_id: str, severity: str, cost: float | None = None) -> Finding:
    return Finding(
        id=f"F-{rule_id}",
        rule_id=rule_id,
        severity=severity,
        platform="azure",
        region="eastus",
        category="network",
        title=f"[{rule_id}] Test finding {rule_id}",
        description=f"Description for {rule_id}",
        resource_id=f"/subscriptions/sub-1/resource/{rule_id}",
        resource_type="Microsoft.Network/virtualNetworks",
        account_id="sub-1",
        observed_state=f"Observed state for {rule_id}",
        est_monthly_cost_usd=cost,
        framework_mappings=[
            FrameworkMapping(
                framework="CIS Azure Foundations",
                control_id="6.5",
                control_name="Network Watcher",
                alignment="Gap",
            )
        ],
        recommendations=[
            FindingRecommendation(source="CNA Platform", text=f"Remediate {rule_id} step 1"),
            FindingRecommendation(source="CNA Platform", text=f"Remediate {rule_id} step 2"),
        ],
    )


@pytest.fixture
def findings() -> list[Finding]:
    return [
        _finding("AZ-NET-002", "critical"),  # east_west
        _finding("AZ-NET-012", "high"),  # east_west
        _finding("AZ-NET-001", "high"),  # north_south
        _finding("AZ-NET-007", "medium"),  # north_south
        _finding("AZ-NET-006", "medium"),  # management
        _finding("AZ-NET-014", "low"),  # management
        _finding("AZ-COST-001", "low", cost=43.80),  # finops
        _finding("AZ-COST-002", "medium", cost=140.16),  # finops
        _finding("AZ-BCDR-002", "high"),  # bc/dr
    ]


def _vnet(idx: int, peer_to: str | None = None, hub: bool = False) -> VNet:
    sub_id = "sub-1"
    vnet_id = f"/subscriptions/{sub_id}/vnets/vnet-{idx}"
    subnets = []
    if hub:
        subnets.append(
            AzureSubnet(
                id=f"{vnet_id}/subnets/GatewaySubnet",
                name="GatewaySubnet",
                address_prefix="10.0.0.0/27",
            )
        )
    peerings = []
    if peer_to:
        peerings.append(
            VNetPeering(
                id=f"{vnet_id}/peerings/to-hub",
                name="to-hub",
                remote_vnet_id=peer_to,
                remote_vnet_name=peer_to.rsplit("/", 1)[-1],
                remote_subscription_id=sub_id,
                peering_state="Connected",
                allow_forwarded_traffic=True,
                allow_gateway_transit=hub,
                use_remote_gateways=not hub,
            )
        )
    return VNet(
        id=vnet_id,
        name=f"vnet-{idx}",
        location="eastus",
        resource_group="rg-net",
        subscription_id=sub_id,
        address_space=[f"10.{idx}.0.0/16"],
        subnets=subnets,
        peerings=peerings,
    )


@pytest.fixture
def topology() -> AzureTopology:
    hub = _vnet(0, hub=True)
    spokes = [_vnet(i, peer_to=hub.id) for i in (1, 2)]
    hub.peerings = [
        VNetPeering(
            id=f"{hub.id}/peerings/to-spoke-{i}",
            name=f"to-spoke-{i}",
            remote_vnet_id=s.id,
            remote_vnet_name=s.name,
            remote_subscription_id="sub-1",
            peering_state="Connected",
            allow_forwarded_traffic=True,
            allow_gateway_transit=True,
            use_remote_gateways=False,
        )
        for i, s in enumerate(spokes, start=1)
    ]
    sub = AzureSubscriptionTopology(
        subscription_id="sub-1",
        subscription_name="Prod",
        tenant_id="tenant-1",
        vnets=[hub, *spokes],
        public_ips=[
            AzurePublicIP(
                id="/subscriptions/sub-1/pips/pip-orphan",
                name="pip-orphan",
                location="eastus",
                resource_group="rg-net",
            )
        ],
        firewalls=[
            AzureFirewall(
                id="/subscriptions/sub-1/fw/azfw-hub",
                name="azfw-hub",
                location="eastus",
                resource_group="rg-net",
                sku_tier="Standard",
                subnet_id=f"{hub.id}/subnets/AzureFirewallSubnet",
            )
        ],
        virtual_network_gateways=[
            AzureVirtualNetworkGateway(
                id="/subscriptions/sub-1/gw/vpngw-1",
                name="vpngw-1",
                location="eastus",
                resource_group="rg-net",
                gateway_type="Vpn",
                subnet_id=f"{hub.id}/subnets/GatewaySubnet",
                active_active=False,
            )
        ],
        observability=ObservabilityData(
            nsg_flow_logs_enabled=1,
            nsg_flow_logs_total=3,
            gateways_with_diagnostics=0,
            gateways_total=1,
            firewalls_with_diagnostics=1,
            firewalls_total=1,
            metric_alert_count=2,
        ),
    )
    return AzureTopology(engagement_id="eng-ency-001", tenant_id="tenant-1", subscriptions=[sub])


def _render(findings, topology, edition: str) -> str:
    classification = classify_topology(topology)
    future = build_future_state(topology, classification)
    bundle = build_stat_masters(topology, findings, engagement_id="eng-ency-001")
    renderer = EncyclopediaReportRenderer(edition=edition)
    return renderer.render_html(
        findings,
        topology=topology,
        classification=classification,
        future_state=future,
        stat_bundle=bundle,
        engagement={
            "engagement_id": "eng-ency-001",
            "client_org": "Acme Corp",
            "engagement_name": "Acme Cloud Network Assessment",
            "generated_at": datetime(2026, 6, 10).isoformat(),
        },
        current_diagram_svg="<svg data-diagram='current'></svg>",
        future_diagram_svg="<svg data-diagram='future'></svg>",
    )


# ── radar_chart ────────────────────────────────────────────────────────────────


def test_radar_chart_svg_basic():
    svg = radar_chart_svg([("A", 50), ("B", 80), ("C", 120), ("D", -5)])
    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")
    assert "#00E9BB" in svg  # bright teal polygon
    assert ">120<" not in svg  # clamped to 100
    assert ">100<" in svg


def test_radar_chart_requires_three_dimensions():
    with pytest.raises(ValueError):
        radar_chart_svg([("A", 1), ("B", 2)])


# ── normalization & maturity ───────────────────────────────────────────────────


def test_normalize_finding_from_dict_prisma_shape():
    f = normalize_finding(
        {
            "title": "[AZ-COST-001] Orphaned public IP",
            "severity": "low",
            "category": "FinOps",
            "description": "desc",
            "trafficDirection": None,
            "resourceType": "Microsoft.Network/publicIPAddresses",
            "estCostImpact": 3.65,
            "recommendation": "Delete the orphaned IP",
        }
    )
    assert f["rule_id"] == "AZ-COST-001"
    assert f["severity"] == "LOW"
    assert f["traffic_direction"] == "north_south"
    assert f["est_monthly_cost_usd"] == 3.65
    assert f["recommendations"][0]["text"] == "Delete the orphaned IP"


def test_maturity_dimensions_are_five_and_bounded(findings):
    dims = build_maturity_dimensions([normalize_finding(f) for f in findings])
    assert len(dims) == 5
    assert all(0 <= score <= 100 for _, score in dims)


# ── context builder ────────────────────────────────────────────────────────────


def test_context_classifies_and_builds_future_state(findings, topology):
    ctx = build_encyclopedia_context(findings, topology=topology)
    assert ctx["classification"].pattern == "hub_spoke"
    assert ctx["future_state"] is not None
    assert ctx["topology_tables"]["peerings"]
    assert ctx["topology_tables"]["public_ips"][0]["associated"] is False
    assert ctx["total_est_monthly_cost"] == pytest.approx(183.96)


def test_context_rejects_unknown_edition(findings):
    with pytest.raises(ValueError):
        build_encyclopedia_context(findings, edition="normal")


# ── HTML rendering — both editions ─────────────────────────────────────────────

_CHAPTER_HEADINGS = [
    "Executive Summary &amp; Maturity",
    "East-West Traffic Deep Dive",
    "North-South Perimeter Audit",
    "FinOps Cost Matrix",
    "Observability &amp; Resilience",
    "Future State &amp; Roadmap",
]


def test_expanded_html_contains_all_chapters_and_toc(findings, topology):
    html = _render(findings, topology, EDITION_EXPANDED)
    for heading in _CHAPTER_HEADINGS:
        assert heading in html, f"missing chapter heading: {heading}"
    assert "Table of Contents" in html
    assert 'href="#ch6"' in html
    assert "Expanded Edition" in html
    assert "Remediation steps" in html  # per-finding playbooks
    assert "[VERIFY]" in html  # cost figures flagged
    assert "data-diagram='current'" in html
    assert "data-diagram='future'" in html
    assert "<svg" in html  # radar
    assert "Acme Corp" in html


def test_condensed_html_is_shorter_and_omits_remediation_detail(findings, topology):
    expanded = _render(findings, topology, EDITION_EXPANDED)
    condensed = _render(findings, topology, EDITION_CONDENSED)
    for heading in _CHAPTER_HEADINGS:
        assert heading in condensed, f"missing chapter heading: {heading}"
    assert "Condensed Edition" in condensed
    assert "Remediation steps" not in condensed
    assert len(condensed) < len(expanded)


def test_render_handles_dict_findings_without_topology():
    dict_findings = [
        {
            "title": "[AZ-NET-002] Subnet without NSG",
            "severity": "high",
            "category": "Network Segmentation",
            "description": "desc",
            "resourceType": "Microsoft.Network/virtualNetworks/subnets",
        }
    ]
    renderer = EncyclopediaReportRenderer(edition=EDITION_CONDENSED)
    html = renderer.render_html(dict_findings)
    assert "Subnet without NSG" in html
    assert "No topology checkpoint was available" in html


def test_render_writes_html_sidecar(tmp_path, findings, topology):
    renderer = EncyclopediaReportRenderer(edition=EDITION_EXPANDED)
    out = tmp_path / "ency.html"
    result = renderer.render(
        findings,
        out,
        topology=topology,
        current_diagram_svg="<svg></svg>",
        future_diagram_svg="<svg></svg>",
    )
    assert result == out
    assert out.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_pdf_render_page_count_if_weasyprint_available(findings, topology):
    try:
        import weasyprint
    except Exception as exc:  # noqa: BLE001 — missing GTK DLLs raise OSError
        pytest.skip(f"weasyprint unavailable: {exc}")
    html = _render(findings, topology, EDITION_EXPANDED)
    from cna.report_engine.encyclopedia_report import _TEMPLATES_DIR

    document = weasyprint.HTML(string=html, base_url=str(_TEMPLATES_DIR)).render()
    assert len(document.pages) >= 8  # fixture is small; real estates reach 20+
