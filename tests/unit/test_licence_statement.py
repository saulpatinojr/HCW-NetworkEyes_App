"""The repository, the image label and NOTICE must state the same licence (ticket #251, REVIEW.md R-020).

The root ``Dockerfile`` once labelled the image ``Proprietary`` while ``LICENSE`` is Apache-2.0. Nothing compared the
two, so this test does: it reads the licence name from ``LICENSE``, every ``org.opencontainers.image.licenses``
label in every tracked Dockerfile, and ``NOTICE``, and fails when they disagree or when a bundled font or a Hybrid Cloud
Works logo file is not listed.
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


def test_notice_says_the_name_and_every_logo_file_are_not_covered_by_the_licence() -> None:
    notice = (REPO_ROOT / "NOTICE").read_text(encoding="utf-8")
    heading = "Name and logo that are NOT covered by the Apache License"
    assert heading in notice, "NOTICE has no section for the Hybrid Cloud Works name and logo"
    section = notice[
        notice.index(heading) :
    ]  # the checks below read this section, not the font entry above it
    logos = [str(p.relative_to(REPO_ROOT)).replace("\\", "/") for p in _tracked("*hcw-logo*")]
    assert logos, "expected the Hybrid Cloud Works logo files to be tracked"
    missing = [name for name in logos if name not in section]
    assert not missing, (
        f"NOTICE does not list these logo files in its name and logo section: {missing}"
    )
    text = " ".join(section.split())  # line breaks and runs of spaces do not matter
    assert 'The name "Hybrid Cloud Works" and the Hybrid Cloud Works logo' in text
    assert "The Apache License does not cover the name or the logo" in text
    assert "Section 6 of it (Trademarks) grants no permission to use them" in text
    # section 6 of LICENSE has an exception; NOTICE quotes it in the licence's own words rather than paraphrasing it
    assert (
        '"except as required for reasonable and customary use in describing the origin of the Work '
        'and reproducing the content of the NOTICE file"'
    ) in text
    licence = " ".join((REPO_ROOT / "LICENSE").read_text(encoding="utf-8").split())
    assert (
        "except as required for reasonable and customary use in describing the origin of the Work"
        in licence
    )


def test_readme_points_at_the_licence_and_notice() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "(LICENSE)" in readme
    assert "(NOTICE)" in readme
