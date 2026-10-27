"""BC/DR signals — AZ-BCDR-* resilience findings from discovery checkpoints.

The rules live in the engine package (``network_assessment_azure_engine.rules.azure_bcdr``,
``AZ-BCDR-001..007``); ``generate_bcdr_findings`` evaluates them over a topology and returns the
monorepo's findings, for callers that want the BC/DR set on its own. Pure post-processing
over an existing AzureTopology (DD-008: data store only).
"""

from __future__ import annotations

from network_assessment.core.findings_schema import Finding
from network_assessment.core.topology.azure import AzureTopology
from network_assessment_azure_engine.rules import evaluate
from network_assessment_azure_engine.rules.azure_bcdr import (
    R_AZ_BCDR_APPGW_NOT_ZONE_REDUNDANT,
    R_AZ_BCDR_FW_NOT_ZONE_REDUNDANT,
    R_AZ_BCDR_GW_NOT_ZONE_REDUNDANT,
    R_AZ_BCDR_LB_NOT_ZONE_REDUNDANT,
    R_AZ_BCDR_SINGLE_ER_GATEWAY,
    R_AZ_BCDR_SINGLE_FIREWALL_SPOF,
    R_AZ_BCDR_VPN_ACTIVE_PASSIVE,
)

__all__ = [
    "R_AZ_BCDR_APPGW_NOT_ZONE_REDUNDANT",
    "R_AZ_BCDR_FW_NOT_ZONE_REDUNDANT",
    "R_AZ_BCDR_GW_NOT_ZONE_REDUNDANT",
    "R_AZ_BCDR_LB_NOT_ZONE_REDUNDANT",
    "R_AZ_BCDR_SINGLE_ER_GATEWAY",
    "R_AZ_BCDR_SINGLE_FIREWALL_SPOF",
    "R_AZ_BCDR_VPN_ACTIVE_PASSIVE",
    "generate_bcdr_findings",
]

_BCDR_PREFIX = "AZ-BCDR-"


def generate_bcdr_findings(topology: AzureTopology) -> list[Finding]:
    """Generate AZ-BCDR-* findings for every unblocked subscription (pure)."""
    report = evaluate(topology)
    return [
        Finding.from_engine(f)
        for f in report.findings
        if (f.rule_id or "").startswith(_BCDR_PREFIX)
    ]
