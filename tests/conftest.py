"""Root test configuration: the ``aws`` marker (change set K of REFACTOR_APP.md).

Tests that need ``boto3`` are marked ``@pytest.mark.aws`` and skipped, not failed, when the
``[aws]`` extra is not installed, so an Azure-only checkout runs green and the AWS paths are
exercised wherever the extra is present (CI installs it).
"""

from __future__ import annotations

import pytest

from cna.aws import INSTALL_HINT, aws_extra_installed


def pytest_collection_modifyitems(config, items):  # noqa: ARG001
    if aws_extra_installed():
        return
    skip = pytest.mark.skip(reason=INSTALL_HINT)
    for item in items:
        if "aws" in item.keywords:
            item.add_marker(skip)
