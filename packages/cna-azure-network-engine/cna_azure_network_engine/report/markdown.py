"""``report.md``: the findings report as Markdown, findings by severity, then the rules the
input could not answer. The text states observed configuration only; the compliance references
and Learn links it prints are marked for verification, as the rule data is."""

from __future__ import annotations

from cna_azure_network_engine.classify.topology import TopologyClassification
from cna_azure_network_engine.findings.schema import Finding, FindingsReport

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4}
_FRAMEWORKS_SHOWN = 3


def _cell(value: object) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _by_severity(report: FindingsReport) -> dict[str, int]:
    counts = dict.fromkeys(SEVERITY_ORDER, 0)
    for finding in report.findings:
        counts[finding.severity.value] = counts.get(finding.severity.value, 0) + 1
    return counts


def _finding_block(f: Finding) -> list[str]:
    frameworks = "; ".join(
        f"{m.framework} {m.control or m.control_id or ''}".strip()
        for m in f.framework_mappings[:_FRAMEWORKS_SHOWN]
    )
    return [
        f"### {f.severity.value.upper()} · {f.rule_id} · {_cell(f.title)}",
        "",
        f"- Resource: `{f.resource_id}` ({_cell(f.resource_type)}, {_cell(f.region)}, "
        f"subscription {_cell(f.account_id)})",
        f"- Fact ({f.observed_state.state}): {_cell(f.observed_state.fact)}",
        f"- Evidence: `{_cell(f.observed_state.evidence_ref)}`",
        f"- Remediation: {_cell(f.remediation)}",
        f"- Learn: {f.learn_url} [VERIFY]",
        f"- Frameworks [VERIFY]: {_cell(frameworks)}",
        f"- Traffic plane: {f.traffic_direction or 'unclassified'}",
        "",
    ]


def render_markdown(
    report: FindingsReport,
    *,
    classification: TopologyClassification | None = None,
    warnings: list[str] | None = None,
    title: str = "Azure network assessment report",
) -> str:
    lines: list[str] = [f"# {title}", ""]
    scope = f"Engagement `{report.engagement_id}`. " if report.engagement_id else ""
    lines.append(
        f"{scope}Rules {report.rules_version}, model {report.model_version}, generated "
        f"{report.generated_at}."
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Severity | Findings |")
    lines.append("|---|---|")
    lines.extend(f"| {sev} | {count} |" for sev, count in _by_severity(report).items())
    lines.append("")
    if warnings:
        lines.append(f"Ingestion warnings: {len(warnings)}")
        lines.append("")
        lines.extend(f"- {_cell(w)}" for w in warnings)
        lines.append("")
    if classification is not None:
        lines.append("## Topology")
        lines.append("")
        lines.append(f"Pattern: **{classification.pattern}**. {_cell(classification.rationale)}")
        if classification.hub_vnet_ids:
            lines.append("")
            lines.extend(f"- hub: `{h}`" for h in classification.hub_vnet_ids)
        if classification.spoke_vnet_ids:
            lines.extend(f"- spoke: `{v}`" for v in classification.spoke_vnet_ids)
        lines.append("")
    lines.append("## Findings by severity")
    lines.append("")
    ordered = sorted(
        report.findings,
        key=lambda f: (
            SEVERITY_ORDER.get(f.severity.value, 9),
            f.rule_id or "",
            f.resource_id or "",
        ),
    )
    if not ordered:
        lines.append("No finding was observed.")
        lines.append("")
    for finding in ordered:
        lines.extend(_finding_block(finding))
    lines.append("## Rules this input cannot answer")
    lines.append("")
    if report.unknowns:
        lines.append("| Rule | Reason |")
        lines.append("|---|---|")
        lines.extend(f"| {u.rule_id} | {_cell(u.reason)} |" for u in report.unknowns)
    else:
        lines.append("Every registered rule was evaluated over this input.")
    lines.append("")
    lines.append("## Notice")
    lines.append("")
    lines.append(
        "Findings state observed configuration only; compliance references and Learn links are "
        "marked for verification. Microsoft and Azure are trademarks of Microsoft Corporation; "
        "this project is not affiliated with or endorsed by Microsoft."
    )
    lines.append("")
    return "\n".join(lines)
