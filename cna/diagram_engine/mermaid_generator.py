"""Mermaid diagram generator — Phase B.

Generates Mermaid syntax strings for:
  - AWS account / OU hierarchy  (flowchart TD)
  - Azure management group tree (flowchart TD)
  - Landing zone architecture   (flowchart LR)
  - Module dependency graph     (flowchart LR)

Mermaid output is embedded in the static portal HTML and in Markdown reports.
For stand-alone SVG export, call export_pipeline.mmdc_to_svg().
"""

from __future__ import annotations

from cna.core.topology_schema import AWSTopology, AzureTopology, ManagementGroup

_SAFE_CHARS = str.maketrans({" ": "_", "/": "_", ".": "_", "-": "_", "(": "", ")": ""})


def _node_id(raw: str) -> str:
    """Make a Mermaid-safe node ID (no spaces or special chars)."""
    return raw.translate(_SAFE_CHARS)[:32]


def generate_aws_account_hierarchy(topology: AWSTopology) -> str:
    """Mermaid flowchart of AWS organization: management > OUs > member accounts.

    Args:
        topology: Full AWSTopology with accounts populated.

    Returns:
        Mermaid flowchart string ready for ```mermaid fences.
    """
    lines = ["flowchart TD"]

    if not topology.accounts:
        lines.append('  EMPTY["No accounts discovered"]')
        return "\n".join(lines)

    # Management account at top
    mgmt_id = topology.management_account_id or "unknown"
    mgmt_node = _node_id(mgmt_id)
    # FIX P0: split into two separate lines.append() calls — no multi-line f-strings
    lines.append(f'  {mgmt_node}["Management Account\\n{mgmt_id}"]')
    lines.append(f"  style {mgmt_node} fill:#FF8000,color:#fff,stroke:#333")

    # OU grouping
    ou_accounts: dict[str, list] = {}
    for account in topology.accounts:
        if account.is_management_account:
            continue
        ou = account.ou_name or "Root"
        ou_accounts.setdefault(ou, []).append(account)

    for ou_name, accounts in ou_accounts.items():
        ou_node = _node_id(ou_name)
        # FIX P0: split into two separate lines.append() calls
        lines.append(f'  {ou_node}[["{ou_name}"]]')
        lines.append(f"  style {ou_node} fill:#8C4FFF,color:#fff,stroke:#333")
        lines.append(f"  {mgmt_node} --> {ou_node}")
        for account in accounts:
            acc_node = _node_id(account.account_id)
            acc_label = account.account_name or account.account_id
            lines.append(f'  {acc_node}["{acc_label}\\n{account.account_id}"]')
            lines.append(f"  {ou_node} --> {acc_node}")

    return "\n".join(lines)


def generate_azure_mg_hierarchy(topology: AzureTopology) -> str:
    """Mermaid flowchart of Azure tenant: root MG > child MGs > subscriptions.

    Args:
        topology: Full AzureTopology with management_groups populated.

    Returns:
        Mermaid flowchart string.
    """
    lines = ["flowchart TD"]

    if not topology.management_groups:
        lines.append('  EMPTY["No management groups discovered"]')
        return "\n".join(lines)

    def _render_mg(mg: ManagementGroup, all_mgs: dict[str, ManagementGroup]) -> None:
        mg_node = _node_id(mg.id)
        # FIX P0: split into two separate lines.append() calls
        lines.append(f'  {mg_node}[["{mg.display_name}"]]')
        lines.append(f"  style {mg_node} fill:#0078D4,color:#fff,stroke:#333")
        for sub_id in mg.subscription_ids:
            sub_node = _node_id(sub_id)
            # FIX P0: split into two separate lines.append() calls
            lines.append(f'  {sub_node}["Sub\\n{sub_id[:8]}..."]')
            lines.append(f"  style {sub_node} fill:#50E6FF,stroke:#0078D4")
            lines.append(f"  {mg_node} --> {sub_node}")
        for child_id in mg.child_mg_ids:
            if child_id in all_mgs:
                child_node = _node_id(child_id)
                lines.append(f"  {mg_node} --> {child_node}")
                _render_mg(all_mgs[child_id], all_mgs)

    mg_map = {mg.id: mg for mg in topology.management_groups}
    roots = [mg for mg in topology.management_groups if not mg.parent_id]
    for root in roots:
        _render_mg(root, mg_map)

    return "\n".join(lines)


def generate_landing_zone_diagram(platform: str, design_notes: dict) -> str:
    """Mermaid LR flowchart for landing zone architecture documentation.

    DD-011: Presents design, does not produce IaC.

    Args:
        platform: 'aws' | 'azure'
        design_notes: Dict with keys: management_layer, connectivity_layer,
          workload_layers (list), security_controls (list)

    Returns:
        Mermaid flowchart string.
    """
    lines = ["flowchart LR"]

    mgmt = _node_id(design_notes.get("management_layer", "Management"))
    conn = _node_id(design_notes.get("connectivity_layer", "Connectivity"))
    lines.append(f'  {mgmt}["Management & Governance"]')
    lines.append(f'  {conn}["Connectivity Hub"]')
    lines.append(f"  {mgmt} --- {conn}")

    for i, layer in enumerate(design_notes.get("workload_layers", [])):
        node = _node_id(f"{layer}_{i}")
        lines.append(f'  {node}["{layer}"]')
        lines.append(f"  {conn} --> {node}")

    for ctrl in design_notes.get("security_controls", []):
        ctrl_node = _node_id(ctrl)
        # FIX P0: split into two separate lines.append() calls
        lines.append(f'  {ctrl_node}(("{ctrl}"))')
        lines.append(f"  style {ctrl_node} fill:#FF4444,color:#fff")
        lines.append(f"  {mgmt} -.-> {ctrl_node}")

    return "\n".join(lines)
