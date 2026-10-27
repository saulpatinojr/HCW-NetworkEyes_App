"""Real-time critical finding escalation.

DD-016: Fires during DISCOVERY — not during analysis.
Critical findings are escalated immediately, not held until final report.
"""

from datetime import UTC, datetime

CRITICAL_TRIGGERS_AWS = [
    {"service": "ec2", "check": "sg_ingress_0000_port_22", "title": "SSH exposed to internet"},
    {"service": "ec2", "check": "sg_ingress_0000_port_3389", "title": "RDP exposed to internet"},
    {
        "service": "ec2",
        "check": "sg_ingress_0000_all_ports",
        "title": "All ports exposed to internet",
    },
    {
        "service": "nfw",
        "check": "firewall_default_allow",
        "title": "Network Firewall default allow",
    },
]

CRITICAL_TRIGGERS_AZURE = [
    {"service": "nsg", "check": "any_any_allow", "title": "NSG allows any-to-any traffic"},
    {"service": "afw", "check": "idps_off", "title": "Azure Firewall IDPS disabled"},
]


class CriticalFindingEscalationEngine:
    def __init__(self, notifier=None):
        self.notifier = notifier  # Teams/email notifier injected at runtime
        self.critical_log: list = []

    def evaluate(self, resource: dict, service: str, platform: str) -> None:
        """Called per-resource during discovery — not during analysis."""
        triggers = CRITICAL_TRIGGERS_AWS if platform == "aws" else CRITICAL_TRIGGERS_AZURE
        for trigger in triggers:
            if trigger["service"] == service and self._matches(resource, trigger["check"]):
                self._escalate(resource, trigger)

    def flag(self, finding) -> None:
        """Called inline from _emit() when a CRITICAL finding is raised during analysis.

        The finding is recorded in critical_log and the optional notifier is
        invoked. This is the DD-016 real-time escalation path.
        """
        event = {
            "rule_id": finding.rule_id,
            "resource_id": finding.resource_id,
            "severity": str(finding.severity),
            "title": finding.title,
            "at": datetime.now(UTC).isoformat(),
        }
        self.critical_log.append(event)
        if self.notifier:
            self.notifier.send_critical_alert(event)

    def process(self, engagement_id: str, findings: list) -> None:
        """Bulk-escalate a list of CRITICAL findings at end of analysis run."""
        for finding in findings:
            self.flag(finding)

    def _matches(self, resource: dict, check: str) -> bool:
        # TODO: Phase C — implement per-check matching logic
        return False

    def _escalate(self, resource: dict, trigger: dict) -> None:
        event = {
            "trigger": trigger,
            "resource_id": resource.get("id") or resource.get("ResourceId"),
            "at": datetime.now(UTC).isoformat(),
        }
        self.critical_log.append(event)
        if self.notifier:
            self.notifier.send_critical_alert(event)
