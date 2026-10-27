"""The CLI and API images ship neither pip nor virtualenv.

The first real build (run 40240474498) stopped at Docker Scout on both images with 1 critical and 11 high
findings, every one of them read from ``virtualenv-*.dist-info/sboms/virtualenv.cdx.json``: virtualenv
embeds pip wheels, and the SBOM names their vendored certifi, urllib3, msgpack and setuptools. virtualenv
arrives through ``diagrams`` -> ``pre-commit`` -> ``virtualenv`` and nothing in either image creates a
virtual environment. The worker image has no virtualenv and passed.

This is a static check of the Dockerfiles; whether Scout is then clean is only known from a real build.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIPPED = {
    "cli (root Dockerfile)": REPO_ROOT / "Dockerfile",
    "api": REPO_ROOT / "apps" / "network-assessment-api" / "Dockerfile",
}
UNINSTALL = re.compile(r"^RUN python -m pip uninstall -y pip virtualenv\s*$", re.M)


@pytest.mark.parametrize("name", SHIPPED)
def test_the_image_uninstalls_pip_and_virtualenv_after_the_copy(name: str) -> None:
    text = SHIPPED[name].read_text(encoding="utf-8")
    copy = re.compile(
        r"^COPY --from=builder --chown=network-assessment:network-assessment /install /usr/local",
        re.M,
    )
    copies = [m.start() for m in copy.finditer(text)]
    uninstalls = [m.start() for m in UNINSTALL.finditer(text)]
    assert copies, f"{name}: no copy of the builder's /install into /usr/local"
    assert uninstalls, f"{name}: pip and virtualenv must be uninstalled in the shipped stage"
    assert max(copies) < max(uninstalls), (
        f"{name}: uninstall must follow the copy that brings virtualenv in"
    )
