"""``pip install cna`` installs no boto3 (change set K of REFACTOR_APP.md).

Read from the single source of truth and the lock rather than from a throwaway install:
``pyproject.toml`` declares ``boto3`` under the ``aws`` extra only, the lock's base export
resolves no ``boto3``/``botocore`` while the ``--extra aws`` export does, and the guard every
AWS module calls raises the install hint when ``boto3`` is absent.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from cna import aws as aws_extra

REPO_ROOT = Path(__file__).resolve().parents[2]


def _export(*extra_args: str) -> list[str]:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("needs uv to read the lock")
    result = subprocess.run(
        [
            uv,
            "export",
            "--locked",
            "--no-default-groups",
            "--no-emit-project",
            "--no-emit-workspace",
            *extra_args,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return [
        line.split("==", 1)[0].strip().lower()
        for line in result.stdout.splitlines()
        if "==" in line and not line.startswith(("#", " ", "-"))
    ]


def test_boto3_is_declared_under_the_aws_extra_only():
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    base = data["project"]["dependencies"]
    assert not [d for d in base if d.startswith(("boto3", "botocore"))], base
    aws = data["project"]["optional-dependencies"]["aws"]
    assert any(d.startswith("boto3") for d in aws), aws


def test_the_base_resolution_carries_no_aws_sdk_and_the_extra_does():
    base = _export()
    assert "boto3" not in base and "botocore" not in base
    with_aws = _export("--extra", "aws")
    assert "boto3" in with_aws and "botocore" in with_aws


def test_the_guard_names_the_extra_when_boto3_is_absent(monkeypatch):
    monkeypatch.delitem(sys.modules, "boto3", raising=False)
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    assert aws_extra.aws_extra_installed() is False
    with pytest.raises(ImportError, match=r'pip install "cna\[aws\]"'):
        aws_extra.require_aws_extra()


def test_the_guard_passes_when_boto3_resolves(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    aws_extra.require_aws_extra()


def test_every_boto3_importer_calls_the_guard_first():
    """Each module that imports boto3 at import time guards it (the lazy call sites guard inline)."""
    offenders = []
    for path in sorted((REPO_ROOT / "cna").rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        top_level = [
            ln
            for ln in text.splitlines()
            if ln.startswith(("import boto3", "from boto3", "import botocore"))
        ]
        if top_level and "from cna.aws import" not in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


def test_the_aws_permission_list_lives_in_its_own_manifest():
    import yaml

    network = REPO_ROOT / "cna" / "modules" / "network"
    main = yaml.safe_load((network / "module.yaml").read_text(encoding="utf-8"))
    assert "aws" not in (main.get("required_permissions") or {})
    aws = yaml.safe_load((network / "module.aws.yaml").read_text(encoding="utf-8"))
    assert aws["cloud"] == "aws"
    assert "ec2:DescribeVpcs" in aws["required_permissions"]["aws"]
