"""AWS security posture discovery — Phase C.

Collects AWS security-service findings (Security Hub, GuardDuty, AWS Config) for
one account + region and normalizes them into AWSSecurityFinding records — the
AWS analog of Azure Defender for Cloud assessment collection
(cna.modules.network.discovery.azure_discovery._collect_defender_assessments).

Design principles (mirrors aws_discovery):
  - Observed state only (DD-002): findings are reported as returned, never inferred.
  - Dynamic region (DD-006): the caller passes the region; no hardcoded region list.
  - Every disabled/blocked service is logged with a reason — never silently skipped.
  - Rate limiting uses cna.core.throttle.with_retry, the same convention as the
    network discovery path.
  - A security service that is simply not enabled in the account/region degrades
    gracefully to an empty list, exactly as the Azure Defender collector returns
    [] when SecurityReader access or the azure-mgmt-security package is missing.
"""

from __future__ import annotations

import logging

import boto3
import botocore.exceptions

from cna.core.throttle import with_retry
from cna.core.topology_schema import AWSSecurityFinding

logger = logging.getLogger("cna.discovery.aws.security")

# Security Hub workflow states worth surfacing; RESOLVED / SUPPRESSED are noise
# for a posture snapshot.
_ACTIONABLE_WORKFLOW_STATES = ("NEW", "NOTIFIED")

# GuardDuty get_findings accepts at most 50 finding IDs per call.
_GUARDDUTY_BATCH = 50

# Error codes that mean "service not enabled / not accessible here" rather than a
# hard failure — treated as an empty result and logged at debug, mirroring the
# Azure collector's graceful [] on missing access.
_NOT_ENABLED_CODES = {
    "InvalidAccessException",  # Security Hub / GuardDuty not enabled in region
    "AccessDeniedException",
    "AccessDenied",
    "UnauthorizedOperation",
    "ResourceNotFoundException",
    "BadRequestException",
    "SubscriptionRequiredException",
}


class AWSSecurityDiscovery:
    """Collects normalized security findings for a single account + region."""

    def __init__(self, session: boto3.Session, account_id: str, region: str):
        self.session = session
        self.account_id = account_id
        self.region = region

    def collect(self) -> list[AWSSecurityFinding]:
        """Collect from every supported security service.

        Never raises for a service that is simply not enabled — those degrade to
        fewer findings so a partial posture is still returned.
        """
        findings: list[AWSSecurityFinding] = []
        findings.extend(self._collect_security_hub())
        findings.extend(self._collect_guardduty())
        findings.extend(self._collect_config())
        return findings

    # ------------------------------------------------------------ Security Hub

    def _collect_security_hub(self) -> list[AWSSecurityFinding]:
        client = self.session.client("securityhub", region_name=self.region)
        findings: list[AWSSecurityFinding] = []
        filters = {
            "RecordState": [{"Value": "ACTIVE", "Comparison": "EQUALS"}],
            "WorkflowStatus": [
                {"Value": state, "Comparison": "EQUALS"} for state in _ACTIONABLE_WORKFLOW_STATES
            ],
        }
        try:
            paginator = client.get_paginator("get_findings")
            for page in paginator.paginate(Filters=filters):
                for f in page.get("Findings", []):
                    findings.append(self._from_security_hub(f))
        except botocore.exceptions.ClientError as e:
            self._handle_service_error("Security Hub", e)
        return findings

    def _from_security_hub(self, f: dict) -> AWSSecurityFinding:
        resources = f.get("Resources") or []
        resource = resources[0] if resources else {}
        remediation = f.get("Remediation", {}).get("Recommendation", {}).get("Text")
        types = f.get("Types") or []
        return AWSSecurityFinding(
            finding_id=f.get("Id", ""),
            source="SecurityHub",
            title=f.get("Title", ""),
            description=f.get("Description"),
            remediation=remediation,
            status=f.get("Workflow", {}).get("Status", "NEW"),
            severity=f.get("Severity", {}).get("Label", "MEDIUM"),
            resource_id=resource.get("Id"),
            resource_type=resource.get("Type"),
            category=types[0] if types else None,
            region=self.region,
            account_id=self.account_id,
            types=types,
            first_observed_at=f.get("FirstObservedAt") or f.get("CreatedAt"),
        )

    # --------------------------------------------------------------- GuardDuty

    def _collect_guardduty(self) -> list[AWSSecurityFinding]:
        client = self.session.client("guardduty", region_name=self.region)
        findings: list[AWSSecurityFinding] = []
        try:
            detectors = with_retry()(client.list_detectors)().get("DetectorIds", [])
        except botocore.exceptions.ClientError as e:
            self._handle_service_error("GuardDuty", e)
            return findings

        for detector_id in detectors:
            try:
                finding_ids: list[str] = []
                paginator = client.get_paginator("list_findings")
                for page in paginator.paginate(
                    DetectorId=detector_id,
                    FindingCriteria={"Criterion": {"service.archived": {"Eq": ["false"]}}},
                ):
                    finding_ids.extend(page.get("FindingIds", []))
                for start in range(0, len(finding_ids), _GUARDDUTY_BATCH):
                    batch = finding_ids[start : start + _GUARDDUTY_BATCH]
                    resp = with_retry()(client.get_findings)(
                        DetectorId=detector_id, FindingIds=batch
                    )
                    for f in resp.get("Findings", []):
                        findings.append(self._from_guardduty(f))
            except botocore.exceptions.ClientError as e:
                self._handle_service_error(f"GuardDuty detector {detector_id}", e)
        return findings

    def _from_guardduty(self, f: dict) -> AWSSecurityFinding:
        resource = f.get("Resource", {})
        service = f.get("Service") or {}
        finding_type = f.get("Type")
        return AWSSecurityFinding(
            finding_id=f.get("Id", ""),
            source="GuardDuty",
            title=f.get("Title", ""),
            description=f.get("Description"),
            status="ACTIVE",
            severity=self._guardduty_severity(f.get("Severity")),
            resource_type=resource.get("ResourceType"),
            category=finding_type,
            region=self.region,
            account_id=self.account_id,
            types=[finding_type] if finding_type else [],
            first_observed_at=service.get("EventFirstSeen"),
        )

    @staticmethod
    def _guardduty_severity(value) -> str:
        """Map GuardDuty's numeric severity (0.1-8.9) onto a normalized label."""
        try:
            score = float(value)
        except (TypeError, ValueError):
            return "MEDIUM"
        if score >= 7.0:
            return "HIGH"
        if score >= 4.0:
            return "MEDIUM"
        return "LOW"

    # -------------------------------------------------------------- AWS Config

    def _collect_config(self) -> list[AWSSecurityFinding]:
        client = self.session.client("config", region_name=self.region)
        findings: list[AWSSecurityFinding] = []
        try:
            paginator = client.get_paginator("describe_compliance_by_config_rule")
            for page in paginator.paginate(ComplianceTypes=["NON_COMPLIANT"]):
                for rule in page.get("ComplianceByConfigRules", []):
                    if rule.get("Compliance", {}).get("ComplianceType") != "NON_COMPLIANT":
                        continue
                    rule_name = rule.get("ConfigRuleName", "")
                    findings.append(
                        AWSSecurityFinding(
                            finding_id=f"config:{self.region}:{rule_name}",
                            source="Config",
                            title=f"Config rule non-compliant: {rule_name}",
                            status="NON_COMPLIANT",
                            severity="MEDIUM",
                            resource_type="AWS::Config::ConfigRule",
                            category="Software and Configuration Checks",
                            region=self.region,
                            account_id=self.account_id,
                        )
                    )
        except botocore.exceptions.ClientError as e:
            self._handle_service_error("AWS Config", e)
        return findings

    # ------------------------------------------------------------------ shared

    def _handle_service_error(self, service: str, e: botocore.exceptions.ClientError) -> None:
        error = e.response.get("Error", {})
        code = error.get("Code", "")
        msg = error.get("Message", str(e))
        if code in _NOT_ENABLED_CODES:
            logger.debug(
                "[%s/%s] %s not enabled or not accessible: %s",
                self.account_id,
                self.region,
                service,
                msg,
            )
            return
        logger.warning(
            "[%s/%s] %s finding collection failed (%s): %s",
            self.account_id,
            self.region,
            service,
            code,
            msg,
        )


def collect_security_findings(
    session: boto3.Session, account_id: str, region: str
) -> list[AWSSecurityFinding]:
    """Collect normalized AWS security findings for one account + region.

    Function-style entry point mirroring
    cna.modules.security.discovery.azure_security.collect_defender_assessments.
    """
    return AWSSecurityDiscovery(session, account_id, region).collect()


__all__ = ["AWSSecurityDiscovery", "collect_security_findings"]
