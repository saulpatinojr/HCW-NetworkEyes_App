"""``network_assessment.core.topology_schema`` is a deprecation shim: importing it warns, once, at import."""

from __future__ import annotations

import importlib
import subprocess
import sys
import warnings

import pytest

MESSAGE = "network_assessment.core.topology_schema is deprecated"


def test_import_under_w_error_raises_deprecation_warning():
    result = subprocess.run(
        [sys.executable, "-W", "error", "-c", "import network_assessment.core.topology_schema"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "DeprecationWarning" in result.stderr
    assert MESSAGE in result.stderr


def test_import_in_process_emits_deprecation_warning():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        module = importlib.import_module("network_assessment.core.topology_schema")
    with pytest.warns(DeprecationWarning, match=MESSAGE):
        importlib.reload(module)


def test_the_new_modules_import_silently():
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        importlib.import_module("network_assessment.core.topology.common")
        importlib.import_module("network_assessment.core.topology.azure")
        importlib.import_module("network_assessment.core.topology.aws")
