"""The repository, the image label and NOTICE must state the same licence (ticket #251, REVIEW.md R-020).

The root ``Dockerfile`` once labelled the image ``Proprietary`` while ``LICENSE`` is Apache-2.0. Nothing compared the
two, so this test does: it reads the licence name from ``LICENSE``, every ``org.opencontainers.image.licenses``
label in every tracked Dockerfile, and ``NOTICE``, and fails when they disagree or when a bundled font is not listed.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LICENSE_LABEL = re.compile(r'org\.opencontainers\.image\.licenses\s*=\s*"(?P<value>[^"]*)"')


def _tracked(pattern: str) -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z", pattern],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [REPO_ROOT / name for name in out.split("\0") if name]


def test_license_file_is_apache_2() -> None:
    first_lines = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")[:400]
    assert "Apache License" in first_lines
    assert "Version 2.0" in first_lines


def test_every_dockerfile_licence_label_is_apache_2() -> None:
    labels: list[tuple[Path, str]] = []
    for dockerfile in _tracked("*Dockerfile*"):
        text = dockerfile.read_text(encoding="utf-8")
        labels.extend((dockerfile, m.group("value")) for m in LICENSE_LABEL.finditer(text))
    assert labels, "no Dockerfile carries an org.opencontainers.image.licenses label"
    wrong = [
        f"{path.relative_to(REPO_ROOT)}: {value!r}"
        for path, value in labels
        if value != "Apache-2.0"
    ]
    assert not wrong, f"image licence label disagrees with LICENSE (Apache-2.0): {wrong}"


def test_notice_states_the_licence_and_lists_every_bundled_font() -> None:
    notice = (REPO_ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "Apache License, Version 2.0" in notice
    fonts = [
        p for suffix in ("*.ttf", "*.otf", "*.woff", "*.woff2") for p in _tracked(f"*{suffix[1:]}")
    ]
    assert fonts, "expected the Aeonik font files to be tracked"
    missing = [str(p.relative_to(REPO_ROOT)).replace("\\", "/") for p in fonts]
    missing = [name for name in missing if name not in notice]
    assert not missing, f"NOTICE does not list these font files: {missing}"


def test_readme_points_at_the_licence_and_notice() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "(LICENSE)" in readme
    assert "(NOTICE)" in readme
