"""The AWS discovery job names, in its progress log, every rule the analysis could not answer.

A finding the hedge check withholds (issue 362) is listed in ``unknowns[]``; the Azure job
already logs those rule ids, and the AWS job now does the same, so a missing finding is never
silent. Only rule ids reach the log, never a resource name.
"""

from __future__ import annotations

from network_assessment.ai_engine.analysis_engine import AnalysisEngine
from network_assessment.core.topology.aws import AWSTopology

from . import test_network_assessment_api_azure_discovery as azure_api
from .test_aws_hedge_check import _hedged_vpc_check, _topology, _vpc

# The API loader, the captured writes and the skip rule are shared with the Azure job's tests.
pytestmark = azure_api.pytestmark
api_main = azure_api.api_main
captured = azure_api.captured
_progress_lines = azure_api._progress_lines


def _fake_aws_discovery(topology: AWSTopology):
    class FakeDiscovery:
        def __init__(self, store, options):
            pass

        def run(self) -> AWSTopology:
            return topology

    return FakeDiscovery


def _aws_request(api_main):
    return api_main.DiscoveryStartRequest(
        job_id="hcw-sample-job",
        engagement_id="hcw-sample-engagement",
        credential_id="hcw-sample-credential",
        platform="AWS",
        aws_role_arn="arn:aws:iam::111111111111:role/hcw-sample-role",
        aws_regions=["us-east-1"],
    )


def _run(api_main, monkeypatch, topology: AWSTopology) -> None:
    from network_assessment.modules.network.discovery import aws_discovery

    monkeypatch.setattr(aws_discovery, "AWSDiscovery", _fake_aws_discovery(topology))
    api_main._run_aws_discovery(_aws_request(api_main))


def test_a_withheld_aws_rule_is_named_in_the_job_log(api_main, captured, monkeypatch):
    monkeypatch.setattr(AnalysisEngine, "_check_aws_vpc", _hedged_vpc_check)
    vpc = _vpc("hcw-sample-")
    _run(api_main, monkeypatch, _topology(vpc))
    progress = "\n".join(_progress_lines(captured))
    assert "1 rule(s) could not be answered from this topology: AWS-NET-001" in progress
    assert vpc.name not in progress and vpc.id not in progress
    assert all(r["rule_id"] != "AWS-NET-001" for r in captured.records or [])


def test_nothing_is_logged_when_every_rule_answered(api_main, captured, monkeypatch):
    _run(api_main, monkeypatch, _topology(_vpc("hcw-sample-")))
    assert captured.records, "the job wrote the findings"
    assert "could not be answered" not in "\n".join(_progress_lines(captured))
