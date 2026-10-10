"""Compliance-framework mapping helpers shared by the rule modules.

[REVIEW REQUIRED] Every control reference built here is a compliance claim shown to customers
(REFACTOR_APP.md section 22, item 5); the owner's legal/compliance review confirms each before
the appliance's public surface exposes them. The strings are the ones Engine A carried.
"""

from __future__ import annotations

from cna_azure_network_engine.findings.schema import FrameworkMapping


def waf(pillar: str, control: str) -> FrameworkMapping:
    return FrameworkMapping(
        framework="Azure Well-Architected Framework", pillar=pillar, control=control
    )


def cisa(
    control_id: str, control_name: str, alignment: str, pillar: str = "Networks"
) -> FrameworkMapping:
    return FrameworkMapping(
        framework="CISA ZTMM v2",
        version="v2",
        pillar=pillar,
        control_id=control_id,
        control_name=control_name,
        alignment=alignment,
    )


def iso(control: str) -> FrameworkMapping:
    return FrameworkMapping(framework="ISO 27001:2022", pillar="Network Security", control=control)


def hipaa(control: str) -> FrameworkMapping:
    return FrameworkMapping(
        framework="HIPAA §164.312", pillar="Technical Safeguards", control=control
    )


def fedramp(pillar: str, control: str) -> FrameworkMapping:
    return FrameworkMapping(framework="FedRAMP Moderate", pillar=pillar, control=control)


def pci(control: str) -> FrameworkMapping:
    return FrameworkMapping(
        framework="PCI-DSS 4.0", pillar="Network Security Controls", control=control
    )


def nist(pillar: str, control: str) -> FrameworkMapping:
    return FrameworkMapping(framework="NIST CSF", pillar=pillar, control=control)


def cis(control: str) -> FrameworkMapping:
    return FrameworkMapping(
        framework="CIS Microsoft Azure Foundations Benchmark", pillar="Networking", control=control
    )


def asb(control: str) -> FrameworkMapping:
    return FrameworkMapping(
        framework="Azure Security Benchmark", pillar="Network Security", control=control
    )


WAF_NS1 = waf("Security", "NS-1 — Establish network segmentation boundaries")
WAF_NS2 = waf("Security", "NS-2 — Monitor network security")
WAF_NS3 = waf("Security", "NS-3 — Deploy firewall at the edge of enterprise network")
WAF_NS4 = waf("Security", "NS-4 — Protect applications from external network attacks")
WAF_PA2 = waf("Security", "PA-2 — Avoid standing access for user accounts and permissions")
WAF_RE2 = waf("Reliability", "RE-2 — Design for capacity")
WAF_RE3 = waf("Reliability", "RE-3 — Use redundant connectivity")
WAF_RE4_SCALE = waf("Reliability", "RE-4 — Design for scale out")
WAF_RE4_CAPACITY = waf("Reliability", "RE-4 — Design for capacity")
WAF_RE5 = waf("Reliability", "RE-5 — Design for redundancy")
WAF_PE3 = waf("Performance Efficiency", "PE-3 — Monitor and optimize network performance")
WAF_CO7 = waf("Cost Optimization", "CO-7 — Optimize component costs")
FEDRAMP_SC5 = fedramp("System and Communications Protection", "SC-5 — Denial of Service Protection")
FEDRAMP_SC7 = fedramp("System and Communications Protection", "SC-7 — Boundary Protection")
FEDRAMP_CP8 = fedramp("Contingency Planning", "CP-8 — Telecommunications Services")
FEDRAMP_CP8_REDUNDANCY = fedramp(
    "Contingency Planning", "CP-8 — Telecommunications Services (redundancy)"
)
FEDRAMP_AU2 = fedramp("Audit and Accountability", "AU-2 — Audit Events")
PCI_1_2 = pci("Req 1.2 — Network security controls configured and maintained")
PCI_1_3 = pci("Req 1.3 — Restrict inbound and outbound traffic")
ISO_8_20 = iso("A.8.20 — Networks security")
ISO_8_21 = iso("A.8.21 — Security of network services")
ISO_8_22 = iso("A.8.22 — Segregation of networks")
ISO_8_23 = iso("A.8.23 — Web filtering")
NIST_DE_CM_1 = nist(
    "Detect", "DE.CM-1 — The network is monitored to detect potential cybersecurity events"
)
NIST_DE_CM_3 = nist("Detect", "DE.CM-3 — Personnel activity is monitored")
NIST_PR_PT_4 = nist("Protect", "PR.PT-4")

CISA_SEGMENTATION = "Network Segmentation"
CISA_TRAFFIC = "Traffic Management"
CISA_RESILIENCE = "Network Resilience"
CISA_WORKLOADS = "Application and Workload Protection"

BCDR_FRAMEWORK: tuple[FrameworkMapping, ...] = (
    WAF_RE5,
    cisa("3.4", CISA_RESILIENCE, "Redundant network components prevent single points of failure"),
)
FINOPS_FRAMEWORK: tuple[FrameworkMapping, ...] = (
    FrameworkMapping(
        framework="FinOps Framework",
        pillar="Optimize",
        control="Workload optimization — rightsizing and waste elimination",
    ),
    WAF_CO7,
)
