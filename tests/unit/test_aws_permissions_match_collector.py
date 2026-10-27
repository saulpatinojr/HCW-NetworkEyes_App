"""The AWS permission list in module.aws.yaml is exactly what the collector calls.

The list used to be a hand-written guess: it missed calls the collector makes (security groups,
network ACLs, Network Firewall, WAFv2, regions) and carried actions nothing calls. Each boto3 call in
``aws_discovery.py`` maps to one IAM action named like the call (``describe_vpcs`` is
``ec2:DescribeVpcs``), so the two can be compared mechanically. This test keeps them in step: add the
call and the action in the same change.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COLLECTOR = (
    REPO_ROOT / "network_assessment" / "modules" / "network" / "discovery" / "aws_discovery.py"
)
MANIFEST = REPO_ROOT / "network_assessment" / "modules" / "network" / "module.aws.yaml"

# Calls that need no IAM permission (sts:GetCallerIdentity) or are not API calls.
NO_PERMISSION_NEEDED = {"get_paginator", "get_caller_identity"}

# Boto3 clients the collector builds, as the variable names it calls them through.
CLIENT_CALL = re.compile(r"\b(?:ec2|dc|orgs|sts|client)\.([a-z_]+)\b")
PAGINATOR_CALL = re.compile(r'get_paginator\("([a-z_]+)"\)')
WRAPPED_CALL = re.compile(r"with_retry\(\)\((?:ec2|dc|orgs|sts|client)\.([a-z_]+)\)")


def _normal(name: str) -> str:
    return name.replace("_", "").lower()


def _called_methods() -> set[str]:
    text = COLLECTOR.read_text(encoding="utf-8")
    found = set(PAGINATOR_CALL.findall(text)) | set(CLIENT_CALL.findall(text))
    found |= set(WRAPPED_CALL.findall(text))
    return {_normal(m) for m in found - NO_PERMISSION_NEEDED}


def _listed_actions() -> set[str]:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    return {a.split(":", 1)[1] for a in manifest["required_permissions"]["aws"]}


def test_every_collector_call_has_an_iam_action():
    listed = {_normal(a) for a in _listed_actions()}
    assert sorted(_called_methods() - listed) == []


def test_every_listed_action_is_called_by_the_collector():
    called = _called_methods()
    assert sorted(a for a in _listed_actions() if _normal(a) not in called) == []


def test_the_collector_is_read_only():
    methods = [a for a in _listed_actions() if a != "AssumeRole"]
    assert all(a.startswith(("Describe", "List", "Get")) for a in methods)
