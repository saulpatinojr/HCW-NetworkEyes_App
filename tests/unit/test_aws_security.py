"""Unit tests for AWS security posture discovery — Phase C.

All AWS API calls are mocked with unittest.mock. No real AWS credentials required.
Covers Security Hub / GuardDuty / Config normalization, GuardDuty severity
mapping, graceful degradation when a service is not enabled, and the
collect()/collect_security_findings aggregation.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from cna.core.topology_schema import AWSSecurityFinding
from cna.modules.security.discovery.aws_security import (
    AWSSecurityDiscovery,
    collect_security_findings,
)


def _paginator(pages):
    p = MagicMock()
    p.paginate.return_value = pages
    return p


def _client_error(code):
    return ClientError({"Error": {"Code": code, "Message": code}}, "Op")


def _make_session(clients: dict):
    """Build a fake boto3 Session whose .client(service, region_name=...) returns
    the per-service MagicMock from `clients`."""
    session = MagicMock()

    def _client(service, region_name=None):
        return clients[service]

    session.client.side_effect = _client
    return session


@pytest.fixture
def account_region():
    return ("123456789012", "us-east-1")


class TestSecurityHub:
    def test_normalizes_finding(self, account_region):
        account_id, region = account_region
        sh = MagicMock()
        sh.get_paginator.return_value = _paginator(
            [
                {
                    "Findings": [
                        {
                            "Id": "arn:aws:securityhub:us-east-1:123456789012:finding/abc",
                            "Title": "S3 bucket public",
                            "Description": "Bucket allows public read",
                            "Severity": {"Label": "HIGH"},
                            "Workflow": {"Status": "NEW"},
                            "Types": ["Effects/Data Exposure"],
                            "Resources": [{"Id": "arn:aws:s3:::my-bucket", "Type": "AwsS3Bucket"}],
                            "Remediation": {"Recommendation": {"Text": "Block public access"}},
                            "FirstObservedAt": "2026-01-01T00:00:00Z",
                        }
                    ]
                }
            ]
        )
        disc = AWSSecurityDiscovery(_make_session({"securityhub": sh}), account_id, region)
        findings = disc._collect_security_hub()
        assert len(findings) == 1
        f = findings[0]
        assert isinstance(f, AWSSecurityFinding)
        assert f.source == "SecurityHub"
        assert f.severity == "HIGH"
        assert f.resource_id == "arn:aws:s3:::my-bucket"
        assert f.resource_type == "AwsS3Bucket"
        assert f.remediation == "Block public access"
        assert f.category == "Effects/Data Exposure"
        assert f.account_id == account_id
        assert f.region == region

    def test_not_enabled_degrades_to_empty(self, account_region):
        account_id, region = account_region
        sh = MagicMock()
        sh.get_paginator.return_value.paginate.side_effect = _client_error("InvalidAccessException")
        disc = AWSSecurityDiscovery(_make_session({"securityhub": sh}), account_id, region)
        assert disc._collect_security_hub() == []


class TestGuardDuty:
    def test_normalizes_and_maps_severity(self, account_region):
        account_id, region = account_region
        gd = MagicMock()
        gd.list_detectors.return_value = {"DetectorIds": ["d-1"]}
        gd.get_paginator.return_value = _paginator([{"FindingIds": ["f-1"]}])
        gd.get_findings.return_value = {
            "Findings": [
                {
                    "Id": "f-1",
                    "Title": "EC2 crypto mining",
                    "Description": "Instance querying mining domain",
                    "Severity": 8.0,
                    "Type": "CryptoCurrency:EC2/BitcoinTool.B",
                    "Resource": {"ResourceType": "Instance"},
                    "Service": {"EventFirstSeen": "2026-01-02T00:00:00Z"},
                }
            ]
        }
        disc = AWSSecurityDiscovery(_make_session({"guardduty": gd}), account_id, region)
        findings = disc._collect_guardduty()
        assert len(findings) == 1
        f = findings[0]
        assert f.source == "GuardDuty"
        assert f.severity == "HIGH"
        assert f.category == "CryptoCurrency:EC2/BitcoinTool.B"
        assert f.resource_type == "Instance"

    def test_no_detectors_returns_empty(self, account_region):
        account_id, region = account_region
        gd = MagicMock()
        gd.list_detectors.return_value = {"DetectorIds": []}
        disc = AWSSecurityDiscovery(_make_session({"guardduty": gd}), account_id, region)
        assert disc._collect_guardduty() == []
        gd.get_findings.assert_not_called()

    @pytest.mark.parametrize(
        ("value", "label"),
        [(8.9, "HIGH"), (7.0, "HIGH"), (4.0, "MEDIUM"), (3.9, "LOW"), (None, "MEDIUM")],
    )
    def test_severity_mapping(self, value, label):
        assert AWSSecurityDiscovery._guardduty_severity(value) == label


class TestConfig:
    def test_non_compliant_rule(self, account_region):
        account_id, region = account_region
        cfg = MagicMock()
        cfg.get_paginator.return_value = _paginator(
            [
                {
                    "ComplianceByConfigRules": [
                        {
                            "ConfigRuleName": "s3-bucket-ssl-requests-only",
                            "Compliance": {"ComplianceType": "NON_COMPLIANT"},
                        }
                    ]
                }
            ]
        )
        disc = AWSSecurityDiscovery(_make_session({"config": cfg}), account_id, region)
        findings = disc._collect_config()
        assert len(findings) == 1
        assert findings[0].source == "Config"
        assert findings[0].status == "NON_COMPLIANT"
        assert "s3-bucket-ssl-requests-only" in findings[0].finding_id


class TestCollectAggregation:
    def test_collect_merges_all_sources(self, account_region):
        account_id, region = account_region
        sh = MagicMock()
        sh.get_paginator.return_value = _paginator(
            [{"Findings": [{"Id": "sh-1", "Title": "x", "Severity": {"Label": "LOW"}}]}]
        )
        gd = MagicMock()
        gd.list_detectors.return_value = {"DetectorIds": ["d-1"]}
        gd.get_paginator.return_value = _paginator([{"FindingIds": ["f-1"]}])
        gd.get_findings.return_value = {
            "Findings": [{"Id": "gd-1", "Title": "y", "Severity": 2.0, "Type": "Recon"}]
        }
        cfg = MagicMock()
        cfg.get_paginator.return_value = _paginator([{"ComplianceByConfigRules": []}])

        session = _make_session({"securityhub": sh, "guardduty": gd, "config": cfg})
        findings = collect_security_findings(session, account_id, region)
        sources = sorted(f.source for f in findings)
        assert sources == ["GuardDuty", "SecurityHub"]
