"""The AWS analysis judges our wording, not the customer's resource names (issue 362).

Same contract as the Azure engine (issues 356, PRs 361 and 363): a hedge word inside one of
the customer's AWS identifiers (``may-promo-vpc``) is excused; tags, descriptions and other
free text never excuse one; a finding that still hedges is withheld and its rule listed in
``unknowns`` with the fixed reason, and the rest of the analysis still runs.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from unittest.mock import MagicMock

import pytest

from network_assessment.ai_engine import analysis_engine as analysis_module
from network_assessment.ai_engine.analysis_engine import AnalysisEngine, AnalysisOptions
from network_assessment.ai_engine.observed_state_enforcer import HEDGED_WORDING_REASON
from network_assessment.core.findings_schema import (
    Finding,
    FindingSeverity,
    FindingStatus,
    FrameworkMapping,
    ObservedState,
)
from network_assessment.core.topology.aws import (
    VPC,
    AWSAccount,
    AWSRegionTopology,
    AWSTopology,
    SecurityGroup,
    SecurityGroupRule,
)
from network_assessment_azure_engine.findings import enforcer as enforcer_module

ACCOUNT = "111111111111"

HEDGE_WORDS = [
    "may", "might", "could", "should", "possibly", "probably", "likely", "appears", "seems",
    "suggest", "suggests", "indicates", "potentially", "expected", "typically", "usually",
    "generally",
]  # fmt: skip


def _engine() -> AnalysisEngine:
    store = MagicMock()
    store.engagement_id = "hcw-sample-engagement"
    return AnalysisEngine(store=store, options=AnalysisOptions(dry_run=True))


def _vpc(prefix: str, **extra) -> VPC:
    """A VPC that fires AWS-NET-001, -002 and -003, every name and id starting ``prefix``."""
    return VPC(
        id=f"vpc-{prefix}main",
        name=f"{prefix}vpc",
        cidr="10.0.0.0/16",
        is_default=True,
        flow_logs_enabled=False,
        security_groups=[
            SecurityGroup(
                id=f"sg-{prefix}web",
                name=f"{prefix}web-sg",
                vpc_id=f"vpc-{prefix}main",
                rules=[
                    SecurityGroupRule(
                        direction="ingress",
                        protocol="tcp",
                        from_port=22,
                        to_port=22,
                        cidr_ranges=["0.0.0.0/0"],
                    )
                ],
            )
        ],
        **extra,
    )


def _topology(*vpcs: VPC, account_name: str | None = None) -> AWSTopology:
    return AWSTopology(
        engagement_id="hcw-sample-engagement",
        accounts=[AWSAccount(account_id=ACCOUNT, account_name=account_name)],
        regions=[AWSRegionTopology(account_id=ACCOUNT, region="us-east-1", vpcs=list(vpcs))],
    )


BASELINE = _engine().run(aws_topology=_topology(_vpc("hcw-sample-")))


def test_the_word_list_covers_every_hedge_pattern() -> None:
    for pattern in enforcer_module._HEDGE_PATTERNS:
        assert any(re.fullmatch(pattern, w) for w in HEDGE_WORDS), pattern


def test_the_baseline_fires_rules_that_quote_names() -> None:
    assert {f.rule_id for f in BASELINE.findings} >= {"AWS-NET-001", "AWS-NET-002", "AWS-NET-003"}
    assert BASELINE.unknowns == []


@pytest.mark.parametrize("word", HEDGE_WORDS)
def test_names_containing_a_hedge_word_still_give_the_full_analysis(word: str) -> None:
    for prefix in (f"{word}-promo-", f"{word.title()}-promo-"):
        report = _engine().run(aws_topology=_topology(_vpc(prefix)))
        assert sorted(f.rule_id for f in report.findings) == sorted(
            f.rule_id for f in BASELINE.findings
        )
        assert report.unknowns == []
        assert any(prefix in f.observed_state.fact for f in report.findings), (
            "the names reach the facts, so the check really met the hedge word"
        )


@pytest.mark.parametrize("word", HEDGE_WORDS)
def test_a_name_that_is_only_a_hedge_word_is_reported_without_the_name(word: str, caplog) -> None:
    """A VPC named exactly ``may``: the finding that quotes it is reported with the name left out."""
    vpc = _vpc("hcw-sample-")
    vpc.name = word
    with caplog.at_level(logging.INFO, logger="network_assessment.analysis"):
        report = _engine().run(aws_topology=_topology(vpc, _vpc("hcw-other-")))
    assert report.unknowns == []
    assert sorted(f.rule_id for f in report.findings) == sorted(
        f.rule_id for f in BASELINE.findings for _ in range(2)
    )
    flow_log = [
        f for f in report.findings if f.resource_id == vpc.id and f.rule_id == "AWS-NET-002"
    ]
    assert [f.observed_state.fact for f in flow_log] == [
        f"VPC {vpc.id} {analysis_module.NAME_NOT_SHOWN} has no flow logs enabled."
    ]
    assert all(word not in f.observed_state.fact.split() for f in report.findings)
    for record in caplog.records:
        assert not re.search(rf"\b{word}\b", record.getMessage(), re.IGNORECASE)


@pytest.mark.parametrize(
    "sg_name", ["Default SG - should be removed", "web servers may need ssh", "may"]
)
def test_a_critical_finding_is_never_lost_to_a_security_group_name(sg_name: str) -> None:
    """AWS allows spaces in security group names, so a name can fail the hedge check on its own.
    The CRITICAL finding is still reported, without the name, and still escalated (DD-016)."""
    vpc = _vpc("hcw-sample-")
    sg = vpc.security_groups[0]
    sg.name = sg_name
    sg.rules[0].protocol = "-1"
    engine = _engine()
    report = engine.run(aws_topology=_topology(vpc))
    open_all = [f for f in report.findings if f.rule_id == "AWS-NET-005"]
    assert len(open_all) == 1 and open_all[0].severity == FindingSeverity.CRITICAL
    assert sg_name not in open_all[0].observed_state.fact
    assert f"{sg.id} {analysis_module.NAME_NOT_SHOWN} in VPC" in open_all[0].observed_state.fact
    assert report.critical_count == 1
    assert report.unknowns == []


def _hedged_vpc_check(self, vpc, account_id, region):
    """Stands in for a rule whose own wording hedges."""
    self._emit(
        Finding(
            rule_id="AWS-NET-001",
            severity=FindingSeverity.LOW,
            resource_id=vpc.id,
            resource_type="AWS::EC2::VPC",
            account_id=account_id,
            region=region,
            title="Test",
            observed_state=ObservedState(
                fact=f"VPC {vpc.id} ({vpc.name}) may be exposed.", evidence_ref="test"
            ),
            framework_mappings=[FrameworkMapping(framework="Test", control="T-1")],
            status=FindingStatus.OPEN,
        ),
        customer_name=vpc.name,  # leaving the name out must not excuse our own "may be"
    )


@pytest.mark.parametrize(
    ("prefix", "extra", "account_name"),
    [
        ("hcw-sample-", {}, None),
        ("may-promo-", {}, None),
        ("hcw-sample-", {"tags": {"note": "may be"}}, None),
        ("hcw-sample-", {"tags": {"may be exposed.": "x"}}, None),
        ("hcw-sample-", {}, "may be exposed."),
        ("may be exposed. ", {}, None),
    ],
    ids=["plain", "hedge-in-name", "tag-value", "tag-key", "account-display-name", "spaced-name"],
)
def test_our_own_hedge_is_never_reported(monkeypatch, prefix, extra, account_name) -> None:
    """Our "may be" is refused whatever the names, tags or display names hold."""
    monkeypatch.setattr(AnalysisEngine, "_check_aws_vpc", _hedged_vpc_check)
    report = _engine().run(aws_topology=_topology(_vpc(prefix, **extra), account_name=account_name))
    assert report.findings == []
    assert [(u.rule_id, u.reason) for u in report.unknowns] == [
        ("AWS-NET-001", HEDGED_WORDING_REASON)
    ]


def test_only_identifier_fields_are_collected() -> None:
    vpc = _vpc("may-promo-", tags={"may-promo-tag": "may-promo-value"})
    values = analysis_module._AwsIdentifiers(_topology(vpc, account_name="may-promo-account"))
    assert "may-promo-vpc" in values and "vpc-may-promo-main" in values
    assert "sg-may-promo-web" in values
    for free_text in ("may-promo-tag", "may-promo-value", "may-promo-account"):
        assert free_text not in values


def test_azure_unknowns_do_not_replace_withheld_aws_rules(monkeypatch) -> None:
    """The AWS withheld entries survive the Azure half of the same run."""
    from network_assessment.core.topology.azure import AzureTopology

    monkeypatch.setattr(AnalysisEngine, "_check_aws_vpc", _hedged_vpc_check)
    report = _engine().run(
        aws_topology=_topology(_vpc("hcw-sample-")),
        azure_topology=AzureTopology(engagement_id="hcw-sample-engagement", subscriptions=[]),
    )
    assert ("AWS-NET-001", HEDGED_WORDING_REASON) in [
        (u.rule_id, u.reason) for u in report.unknowns
    ]


def test_verdicts_do_not_depend_on_hash_order() -> None:
    code = (
        "from tests.unit.test_aws_hedge_check import _engine, _topology, _vpc;"
        "r = _engine().run(aws_topology=_topology(_vpc('may-qq-may-'), _vpc('qq-may-')));"
        "print(sorted(f.id or f.rule_id + f.resource_id for f in r.findings), r.unknowns)"
    )
    outputs = {
        subprocess.run(
            [sys.executable, "-c", code],
            env={**os.environ, "PYTHONHASHSEED": str(seed)},
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for seed in range(1, 11)
    }
    assert len(outputs) == 1, outputs
