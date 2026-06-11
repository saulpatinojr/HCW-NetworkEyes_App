"""Phase D — Encyclopedia Report Renderer.

Produces the six-chapter CBTS-branded "Networking Encyclopedia" deliverable
from findings + discovery data. Two editions from one template set:

  condensed — executive-level: exec summary, maturity radar, key stats,
              top findings (CRITICAL/HIGH), diagrams, roadmap summary.
  expanded  — full density: every chapter with per-finding domain sections,
              pivot tables, and step-by-step remediation playbooks.

Chapters:
  1. Executive summary + maturity radar
  2. East-West traffic deep dive + current-state diagram
  3. North-South perimeter audit
  4. FinOps cost matrix (every cost figure suffixed [VERIFY])
  5. Observability / BC-DR gaps
  6. Future-state roadmap + future-state diagram

Rendering:
  Jinja2 (templates/encyclopedia/) → HTML → PDF via WeasyPrint.
  HTML sidecar is always written; PDF is skipped with a warning when
  WeasyPrint is unavailable (same degradation as technical_report.py).
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from cna.core.finding_taxonomy import classify_traffic_direction
from cna.core.findings_schema import Finding
from cna.core.stat_masters import StatMasterBundle
from cna.diagram_engine.future_state import FutureStateModel, build_future_state
from cna.modules.network.analysis.topology_classifier import (
    TopologyClassification,
    classify_topology,
)
from cna.report_engine.radar_chart import radar_chart_svg

logger = logging.getLogger("cna.report.encyclopedia")

_TEMPLATES_DIR = Path(__file__).parent / "templates"

EDITION_CONDENSED = "condensed"
EDITION_EXPANDED = "expanded"
_EDITIONS = (EDITION_CONDENSED, EDITION_EXPANDED)

_SEVERITY_ORDER = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL")
_SEVERITY_PENALTY = {"CRITICAL": 25, "HIGH": 15, "MEDIUM": 8, "LOW": 3, "INFORMATIONAL": 1}


# ── Finding normalization ──────────────────────────────────────────────────


def _get(finding: Finding | dict, *keys: str) -> Any:
    """First present, non-empty value among model attrs / dict key aliases."""
    if isinstance(finding, dict):
        for key in keys:
            value = finding.get(key)
            if value not in (None, ""):
                return value
        return None
    for key in keys:
        value = getattr(finding, key, None)
        if value not in (None, ""):
            return value
    return None


def normalize_finding(finding: Finding | dict) -> dict:
    """Flatten a Finding model or dict (API / Prisma shape) into the uniform
    dict the encyclopedia templates consume."""
    severity = str(_get(finding, "severity") or "").upper() or "LOW"

    if isinstance(finding, dict):
        fact = str(_get(finding, "observed_state", "observedState", "description") or "")
        evidence = ""
        frameworks: list[dict] = []
        fw = _get(finding, "framework")
        if fw:
            frameworks = [
                {"framework": str(fw), "control_id": None, "control_name": None, "alignment": None}
            ]
        recommendations: list[dict] = []
        rec = _get(finding, "recommendation")
        if rec:
            recommendations = [
                {
                    "text": str(rec),
                    "source": str(_get(finding, "recommendation_source") or "CNA Platform"),
                }
            ]
    else:
        fact = finding.observed_state.fact
        evidence = finding.observed_state.evidence_ref
        frameworks = [
            {
                "framework": m.framework,
                "control_id": m.control_id,
                "control_name": m.control_name,
                "alignment": m.alignment,
            }
            for m in finding.framework_mappings
        ]
        recommendations = [{"text": r.text, "source": r.source} for r in finding.recommendations]
        if not recommendations and finding.recommendation:
            recommendations = [
                {
                    "text": finding.recommendation,
                    "source": finding.recommendation_source or "CNA Platform",
                }
            ]

    title = str(_get(finding, "title") or "")
    rule_id = str(_get(finding, "rule_id", "ruleId") or "")
    if not rule_id:
        # Dict findings (API mapper / Prisma rows) embed the rule id in the
        # title — same extraction the stat-master builder uses.
        from cna.core.stat_masters import _extract_rule_id

        extracted = _extract_rule_id(title)
        rule_id = extracted if extracted != "—" else ""
    category = str(_get(finding, "category") or "")
    resource_type = str(_get(finding, "resource_type", "resourceType") or "")
    direction = str(_get(finding, "traffic_direction", "trafficDirection") or "")
    if not direction:
        direction = classify_traffic_direction(rule_id, category, resource_type)

    cost = _get(finding, "est_monthly_cost_usd", "est_cost_impact", "estCostImpact")
    try:
        cost = float(cost) if cost is not None else None
    except (TypeError, ValueError):
        cost = None

    return {
        "rule_id": rule_id,
        "severity": severity,
        "title": title,
        "description": str(_get(finding, "description") or ""),
        "fact": fact,
        "evidence": evidence,
        "resource_id": str(_get(finding, "resource_id", "resourceId") or ""),
        "resource_type": resource_type,
        "account_id": str(
            _get(finding, "account_id", "subscription_id", "subscriptionId", "credentialId") or ""
        ),
        "region": str(_get(finding, "region") or ""),
        "category": category,
        "traffic_direction": direction or "unclassified",
        "frameworks": frameworks,
        "recommendations": recommendations,
        "est_monthly_cost_usd": cost,
    }


# ── Maturity scoring ───────────────────────────────────────────────────────


def _maturity_score(findings: list[dict]) -> float:
    """Deterministic 0–100 score: 100 minus severity-weighted penalties."""
    penalty = sum(_SEVERITY_PENALTY.get(f["severity"], 1) for f in findings)
    return float(max(5, 100 - penalty))


def build_maturity_dimensions(findings: list[dict]) -> list[tuple[str, float]]:
    """Five maturity dimensions scored from severity-weighted finding counts."""
    east_west = [f for f in findings if f["traffic_direction"] == "east_west"]
    north_south = [
        f
        for f in findings
        if f["traffic_direction"] == "north_south"
        and not f["rule_id"].startswith(("AZ-COST-", "AZ-BCDR-"))
    ]
    management = [f for f in findings if f["traffic_direction"] == "management"]
    cost = [f for f in findings if f["rule_id"].startswith("AZ-COST-")]
    bcdr = [f for f in findings if f["rule_id"].startswith("AZ-BCDR-")]
    return [
        ("Segmentation (E-W)", _maturity_score(east_west)),
        ("Perimeter (N-S)", _maturity_score(north_south)),
        ("Observability", _maturity_score(management)),
        ("Cost Efficiency", _maturity_score(cost)),
        ("Resilience (BC/DR)", _maturity_score(bcdr)),
    ]


# ── Topology table extraction ──────────────────────────────────────────────


def _accumulate_subscription_tables(sub, tables: dict, obs_totals: dict) -> bool:
    """Append one subscription's resources into *tables* and *obs_totals*.

    Returns True if observability data was found.
    """
    has_obs = False
    if getattr(sub, "discovery_blocked", False):
        tables["subscriptions"].append(
            {"id": sub.subscription_id, "name": sub.subscription_name, "blocked": True}
        )
        return has_obs
    tables["subscriptions"].append(
        {"id": sub.subscription_id, "name": sub.subscription_name, "blocked": False}
    )
    tables["vnet_count"] += len(sub.vnets)
    _accumulate_vnets(sub, tables)
    _accumulate_resources(sub, tables)
    obs = getattr(sub, "observability", None)
    if obs is not None:
        has_obs = True
        for key in obs_totals:
            obs_totals[key] += getattr(obs, key, 0) or 0
    return has_obs


def _accumulate_vnets(sub, tables: dict) -> None:
    for vnet in sub.vnets:
        for peering in vnet.peerings:
            tables["peerings"].append(
                {
                    "vnet": vnet.name,
                    "remote": peering.remote_vnet_name or peering.remote_vnet_id.rsplit("/", 1)[-1],
                    "state": peering.peering_state,
                    "gateway_transit": peering.allow_gateway_transit,
                    "use_remote_gateways": peering.use_remote_gateways,
                    "forwarded_traffic": peering.allow_forwarded_traffic,
                }
            )
        for rt in vnet.route_tables:
            tables["route_tables"].append(
                {
                    "name": rt.name,
                    "vnet": vnet.name,
                    "routes": len(rt.routes),
                    "subnets": len(rt.associated_subnet_ids),
                    "bgp_propagation_disabled": rt.disable_bgp_route_propagation,
                }
            )


def _accumulate_resources(sub, tables: dict) -> None:
    for pip in sub.public_ips:
        tables["public_ips"].append(
            {
                "name": pip.name,
                "ip": pip.ip_address,
                "sku": pip.sku_name,
                "associated": bool(pip.associated_resource_id),
                "associated_type": pip.associated_resource_type,
                "region": pip.location,
            }
        )
    for fw in sub.firewalls:
        tables["firewalls"].append(
            {
                "name": fw.name,
                "sku": fw.sku_tier,
                "threat_intel": fw.threat_intel_mode,
                "zones": ", ".join(fw.zones) or "none",
                "region": fw.location,
            }
        )
    for agw in sub.application_gateways:
        tables["app_gateways"].append(
            {
                "name": agw.name,
                "sku": agw.sku_name,
                "waf_enabled": agw.waf_enabled,
                "waf_mode": agw.waf_mode,
                "zones": ", ".join(agw.zones) or "none",
                "region": agw.location,
            }
        )
    for gw in sub.virtual_network_gateways:
        tables["gateways"].append(
            {
                "name": gw.name,
                "type": gw.gateway_type,
                "sku": gw.sku_name,
                "active_active": gw.active_active,
                "bgp": gw.enable_bgp,
                "connections": len(gw.connections),
                "region": gw.location,
            }
        )
    for nat in sub.nat_gateways:
        tables["nat_gateways"].append(
            {
                "name": nat.name,
                "public_ips": len(nat.public_ip_ids),
                "subnets": len(nat.associated_subnet_ids),
                "zones": ", ".join(nat.zones) or "none",
                "region": nat.location,
            }
        )
    for waf in getattr(sub, "front_door_waf_policies", []) or []:
        tables["front_door_waf"].append(
            {
                "name": waf.name,
                "mode": waf.policy_mode,
                "state": waf.policy_enabled_state,
                "custom_rules": waf.custom_rules_count,
            }
        )


def _topology_tables(topology: Any | None) -> dict:
    """Flatten an AzureTopology into the row dicts the chapter tables render.

    Best-effort and None-safe: returns empty lists when no topology is given.
    """
    tables: dict[str, Any] = {
        "subscriptions": [],
        "peerings": [],
        "route_tables": [],
        "public_ips": [],
        "firewalls": [],
        "app_gateways": [],
        "gateways": [],
        "nat_gateways": [],
        "front_door_waf": [],
        "observability": None,
        "vnet_count": 0,
    }
    if topology is None:
        return tables

    obs_totals = {
        "nsg_flow_logs_enabled": 0,
        "nsg_flow_logs_total": 0,
        "traffic_analytics_enabled": 0,
        "gateways_with_diagnostics": 0,
        "gateways_total": 0,
        "firewalls_with_diagnostics": 0,
        "firewalls_total": 0,
        "appgw_with_diagnostics": 0,
        "appgw_total": 0,
        "lb_with_diagnostics": 0,
        "lb_total": 0,
        "metric_alert_count": 0,
        "activity_log_alert_count": 0,
    }
    has_obs = False

    for sub in getattr(topology, "subscriptions", []) or []:
        if _accumulate_subscription_tables(sub, tables, obs_totals):
            has_obs = True

    if has_obs:
        tables["observability"] = obs_totals
    return tables


# ── Diagram generation ─────────────────────────────────────────────────────


def generate_diagram_svgs(
    topology: Any,
    classification: TopologyClassification,
    future_state: FutureStateModel | None = None,
) -> tuple[str | None, str | None]:
    """Generate (current_state_svg, future_state_svg) via the draw.io export
    pipeline. Degrades gracefully: returns None entries when the draw.io CLI
    or export chain is unavailable — the templates skip absent diagrams.
    """
    try:
        from cna.diagram_engine.drawio_generator import (
            generate_future_state_topology,
            generate_vnet_topology,
        )
        from cna.diagram_engine.export_pipeline import DiagramExporter
    except ImportError as exc:  # pragma: no cover — diagram engine is in-repo
        logger.warning("diagram engine unavailable: %s", exc)
        return None, None

    current_svg: str | None = None
    future_svg: str | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="cna-ency-diagrams-") as tmp:
            exporter = DiagramExporter(output_dir=Path(tmp))
            subs = [
                s
                for s in (getattr(topology, "subscriptions", []) or [])
                if not getattr(s, "discovery_blocked", False) and s.vnets
            ]
            if subs:
                xml = generate_vnet_topology(subs[0])
                paths = exporter.export(xml, "encyclopedia-current-state")
                if ".svg" in paths:
                    current_svg = paths[".svg"].read_text(encoding="utf-8")
            xml = generate_future_state_topology(topology, classification, future_state)
            paths = exporter.export(xml, "encyclopedia-future-state")
            if ".svg" in paths:
                future_svg = paths[".svg"].read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 — diagrams are best-effort
        logger.warning("diagram SVG generation failed: %s", exc)

    if current_svg is None or future_svg is None:
        logger.info(
            "diagram SVG conversion unavailable (draw.io CLI not found?) — "
            "encyclopedia renders without missing diagram(s)."
        )
    return current_svg, future_svg


# ── Context builder ────────────────────────────────────────────────────────


def build_encyclopedia_context(  # noqa: PLR0913 — one optional input per data source
    findings: list[Finding | dict],
    *,
    edition: str = EDITION_EXPANDED,
    topology: Any | None = None,
    classification: TopologyClassification | None = None,
    future_state: FutureStateModel | None = None,
    stat_bundle: StatMasterBundle | None = None,
    engagement: dict | None = None,
    current_diagram_svg: str | None = None,
    future_diagram_svg: str | None = None,
) -> dict:
    """Assemble the full template context for both editions.

    Pure given its inputs (no I/O): diagram SVG strings are passed in —
    use generate_diagram_svgs() to produce them when a topology exists.
    """
    if edition not in _EDITIONS:
        raise ValueError(f"edition must be one of {_EDITIONS}, got {edition!r}")

    normalized = [normalize_finding(f) for f in findings]

    if topology is not None and classification is None:
        classification = classify_topology(topology)
    if topology is not None and classification is not None and future_state is None:
        future_state = build_future_state(topology, classification)

    severity_counts = dict.fromkeys(_SEVERITY_ORDER, 0)
    for f in normalized:
        severity_counts[f["severity"]] = severity_counts.get(f["severity"], 0) + 1

    by_direction: dict[str, list[dict]] = {
        "east_west": [],
        "north_south": [],
        "management": [],
        "unclassified": [],
    }
    for f in normalized:
        by_direction.setdefault(f["traffic_direction"], by_direction["unclassified"])
        by_direction[
            f["traffic_direction"] if f["traffic_direction"] in by_direction else "unclassified"
        ].append(f)

    sev_rank = {sev: i for i, sev in enumerate(_SEVERITY_ORDER)}

    def _sorted(items: list[dict]) -> list[dict]:
        return sorted(
            items, key=lambda f: (sev_rank.get(f["severity"], 99), f["rule_id"], f["title"])
        )

    cost_findings = _sorted([f for f in normalized if f["rule_id"].startswith("AZ-COST-")])
    bcdr_findings = _sorted([f for f in normalized if f["rule_id"].startswith("AZ-BCDR-")])
    top_findings = _sorted([f for f in normalized if f["severity"] in ("CRITICAL", "HIGH")])
    total_est_cost = round(sum(f["est_monthly_cost_usd"] or 0.0 for f in normalized), 2)

    # Stat-master pivots (cost matrix + severity × direction)
    stat_records = stat_bundle.records if stat_bundle else []
    cost_matrix = [r for r in stat_records if r.est_monthly_cost_impact > 0]
    severity_direction: dict[str, dict[str, int]] = {}
    for r in stat_records:
        row = severity_direction.setdefault(r.traffic_direction, {})
        row[r.severity] = row.get(r.severity, 0) + r.finding_count

    maturity = build_maturity_dimensions(normalized)
    radar_svg = radar_chart_svg(maturity, title="Network maturity radar")

    engagement = engagement or {}
    return {
        "edition": edition,
        "is_condensed": edition == EDITION_CONDENSED,
        "engagement": {
            "engagement_id": engagement.get("engagement_id", ""),
            "client_org": engagement.get("client_org", ""),
            "engagement_name": engagement.get("engagement_name", "Cloud Network Assessment"),
            "generated_at": engagement.get("generated_at", ""),
            "prepared_by": engagement.get("prepared_by", "CBTS"),
        },
        "severity_counts": severity_counts,
        "severity_order": list(_SEVERITY_ORDER),
        "total_count": len(normalized),
        "all_findings": _sorted(normalized),
        "findings_by_direction": {k: _sorted(v) for k, v in by_direction.items()},
        "east_west_findings": _sorted(by_direction["east_west"]),
        "north_south_findings": _sorted(
            [
                f
                for f in by_direction["north_south"]
                if not f["rule_id"].startswith(("AZ-COST-", "AZ-BCDR-"))
            ]
        ),
        "management_findings": _sorted(by_direction["management"]),
        "cost_findings": cost_findings,
        "bcdr_findings": bcdr_findings,
        "top_findings": top_findings,
        "total_est_monthly_cost": total_est_cost,
        "maturity_dimensions": maturity,
        "radar_svg": radar_svg,
        "classification": classification,
        "future_state": future_state,
        "stat_records": stat_records,
        "cost_matrix": cost_matrix,
        "severity_direction": severity_direction,
        "topology_tables": _topology_tables(topology),
        "current_diagram_svg": current_diagram_svg,
        "future_diagram_svg": future_diagram_svg,
    }


# ── Renderer ───────────────────────────────────────────────────────────────


class EncyclopediaReportRenderer:
    """Renders the six-chapter encyclopedia report (condensed or expanded)."""

    def __init__(self, templates_dir: Path = _TEMPLATES_DIR, edition: str = EDITION_EXPANDED):
        if edition not in _EDITIONS:
            raise ValueError(f"edition must be one of {_EDITIONS}, got {edition!r}")
        self.edition = edition
        self._env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(["html", "j2"]),
        )

    def render_html(  # noqa: PLR0913 — one optional input per data source
        self,
        findings: list[Finding | dict],
        *,
        topology: Any | None = None,
        classification: TopologyClassification | None = None,
        future_state: FutureStateModel | None = None,
        stat_bundle: StatMasterBundle | None = None,
        engagement: dict | None = None,
        current_diagram_svg: str | None = None,
        future_diagram_svg: str | None = None,
    ) -> str:
        """Render the encyclopedia to an HTML string (no file I/O)."""
        if topology is not None and current_diagram_svg is None and future_diagram_svg is None:
            cls = classification or classify_topology(topology)
            current_diagram_svg, future_diagram_svg = generate_diagram_svgs(
                topology, cls, future_state
            )
            classification = cls
        context = build_encyclopedia_context(
            findings,
            edition=self.edition,
            topology=topology,
            classification=classification,
            future_state=future_state,
            stat_bundle=stat_bundle,
            engagement=engagement,
            current_diagram_svg=current_diagram_svg,
            future_diagram_svg=future_diagram_svg,
        )
        return self._env.get_template("encyclopedia/book.j2").render(**context)

    def render(  # noqa: PLR0913 — one optional input per data source
        self,
        findings: list[Finding | dict],
        output_path: Path,
        *,
        topology: Any | None = None,
        classification: TopologyClassification | None = None,
        future_state: FutureStateModel | None = None,
        stat_bundle: StatMasterBundle | None = None,
        engagement: dict | None = None,
        current_diagram_svg: str | None = None,
        future_diagram_svg: str | None = None,
    ) -> Path:
        """Render to output_path (.pdf or .html). Returns path of written file.

        HTML sidecar is always written; PDF requires WeasyPrint.
        """
        html = self.render_html(
            findings,
            topology=topology,
            classification=classification,
            future_state=future_state,
            stat_bundle=stat_bundle,
            engagement=engagement,
            current_diagram_svg=current_diagram_svg,
            future_diagram_svg=future_diagram_svg,
        )

        html_path = output_path.with_suffix(".html")
        html_path.write_text(html, encoding="utf-8")

        if output_path.suffix == ".pdf":
            try:
                from weasyprint import HTML as WP

                WP(string=html, base_url=str(_TEMPLATES_DIR)).write_pdf(str(output_path))
                logger.info("Encyclopedia (%s) PDF written: %s", self.edition, output_path)
            except (ImportError, OSError):
                # OSError: WeasyPrint installed but native GTK/Pango libs missing
                logger.warning(
                    "WeasyPrint unavailable. Encyclopedia PDF skipped. HTML written to %s.",
                    html_path,
                )
                return html_path
        return output_path
