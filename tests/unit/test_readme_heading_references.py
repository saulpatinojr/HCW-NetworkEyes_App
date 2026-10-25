"""A live file that sends the reader to a README heading must name a heading that exists.

``200-build-images.yml`` and ``scripts/ci/verify_signed_digest.sh`` say "(README, Verifying images)" and
``REVIEW.md`` once cited "Publishing and verifying the images" after the section had been renamed. A reference to a
heading that is gone sends the reader nowhere, and nothing else catches it, so this test reads every reference of
the three forms below and checks it against the headings of ``README.md``:

* ``README, Heading`` followed by ``)``, ``;`` or ``.`` (the form comments use);
* ``README.md`` -> "Heading" or ``README -> *Heading*`` (an arrow and a quoted or emphasised name);
* more than one heading in one reference, separated by `` / ``.

Only these forms are read; a bare ``README.md -> Quick start`` is not. History (``CHANGELOG.md``,
``CNA-0.90-updates.md``) is not read: it describes what was true then.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Live files that may point at a README heading.
SCANNED_GLOBS = (
    "README.md",
    "CLAUDE.md",
    "REVIEW.md",
    "TODO.md",
    "REFACTOR_APP.md",
    ".github/**/*.md",
    ".github/**/*.yml",
    "scripts/**/*.py",
    "scripts/**/*.sh",
)

_HEADING = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*#*\s*$", re.MULTILINE)
_COMMA_FORM = re.compile(r"\bREADME(?:\.md)?`?, (?P<name>[A-Z][a-z][A-Za-z0-9 \-]*?)(?=[);.])")
_ARROW_FORM = re.compile(
    r"\bREADME(?:\.md)?`?\s*(?:→|->)\s*(?:\*(?P<em>[^*\n]+)\*|\"(?P<q>[^\"\n]+)\")"
)


def readme_headings(text: str) -> set[str]:
    """The README's headings, lower-cased, without markdown emphasis or backticks."""
    return {re.sub(r"[*`_]", "", m.group("title")).strip().lower() for m in _HEADING.finditer(text)}


def referenced_names(text: str) -> list[str]:
    """Every README heading name that ``text`` cites, split at `` / ``."""
    raw = [m.group("name") for m in _COMMA_FORM.finditer(text)]
    raw += [m.group("em") or m.group("q") for m in _ARROW_FORM.finditer(text)]
    names: list[str] = []
    for entry in raw:
        names += [part.strip() for part in re.split(r" / ", entry) if part.strip()]
    return names


def missing_headings(text: str, headings: set[str]) -> list[str]:
    return [name for name in referenced_names(text) if name.lower() not in headings]


def _live_files() -> list[Path]:
    files: set[Path] = set()
    for pattern in SCANNED_GLOBS:
        files.update(p for p in REPO_ROOT.glob(pattern) if p.is_file())
    return sorted(files)


HEADINGS = readme_headings((REPO_ROOT / "README.md").read_text(encoding="utf-8"))


class TestTheMatcher:
    def test_it_reads_the_comma_form_of_a_comment(self):
        text = "# verify before running it (README, Verifying images);"
        assert referenced_names(text) == ["Verifying images"]

    def test_it_reads_the_arrow_forms(self):
        text = 'see `README.md` → "Repository conventions" and README → *Publishing the images*.'
        assert referenced_names(text) == ["Repository conventions", "Publishing the images"]

    def test_it_splits_two_headings(self):
        assert referenced_names('README.md → "Quick start / Configuration"') == [
            "Quick start",
            "Configuration",
        ]

    def test_it_ignores_a_sentence_that_only_mentions_the_readme(self):
        assert referenced_names("the README, CHANGELOG.md and REVIEW.md are the documents") == []

    def test_a_missing_heading_is_reported_and_an_existing_one_is_not(self):
        headings = {"verifying images", "publishing the images"}
        text = "(README, Verifying images) and README → *Publishing and verifying the images*"
        assert missing_headings(text, headings) == ["Publishing and verifying the images"]

    def test_headings_are_read_without_emphasis(self):
        assert readme_headings("## Publishing the images\n### `Verifying` images\n") == {
            "publishing the images",
            "verifying images",
        }


class TestTheRepository:
    def test_the_readme_has_the_headings_the_workflow_and_the_script_cite(self):
        assert "verifying images" in HEADINGS
        assert "publishing the images" in HEADINGS

    def test_the_scan_reads_the_files_that_cite_a_heading(self):
        names = {p.relative_to(REPO_ROOT).as_posix() for p in _live_files()}
        assert {
            "REVIEW.md",
            "TODO.md",
            "scripts/ci/verify_signed_digest.sh",
            ".github/workflows/200-build-images.yml",
        } <= names
        cited = [
            p
            for p in _live_files()
            if referenced_names(p.read_text(encoding="utf-8", errors="replace"))
        ]
        assert cited, "no file cites a README heading, so this test would prove nothing"

    @pytest.mark.parametrize(
        "path", _live_files(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix()
    )
    def test_every_cited_readme_heading_exists(self, path):
        text = path.read_text(encoding="utf-8", errors="replace")
        assert missing_headings(text, HEADINGS) == [], (
            f"{path.relative_to(REPO_ROOT).as_posix()} cites a README heading that does not exist"
        )
