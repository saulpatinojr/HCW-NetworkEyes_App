"""``.gitleaksignore`` stays an exact, explained list (ticket #253).

A full-history gitleaks scan reported 122 hits, all false positives. ``.gitleaksignore`` silences exactly those by
fingerprint (``commit:file:rule:line``), so a new finding, even in the same file or of the same rule, still shows.
This test keeps the file from turning into a broad suppression: every entry has the fingerprint shape, nothing is
listed twice, and each class of false positive keeps the sentence that explains it.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
IGNORE_FILE = REPO_ROOT / ".gitleaksignore"

#: commit (40 hex) : file : rule id : line number
FINGERPRINT = re.compile(r"^[0-9a-f]{40}:[^:\s]+:[a-z0-9-]+:\d+$")

#: Each class of false positive is introduced by a comment that starts with its letter.
CLASSES = ("# A. ", "# B. ", "# C. ", "# D. ", "# E. ")


def _entries() -> list[str]:
    lines = IGNORE_FILE.read_text(encoding="utf-8").splitlines()
    return [line for line in lines if line.strip() and not line.startswith("#")]


def test_every_entry_is_an_exact_fingerprint() -> None:
    bad = [line for line in _entries() if not FINGERPRINT.match(line)]
    assert not bad, (
        f"not a commit:file:rule:line fingerprint (a path or rule glob would hide new findings): {bad}"
    )


def test_no_fingerprint_is_listed_twice() -> None:
    entries = _entries()
    assert len(entries) == len(set(entries))


def test_every_class_keeps_its_explanation() -> None:
    text = IGNORE_FILE.read_text(encoding="utf-8")
    missing = [c.strip() for c in CLASSES if c not in text]
    assert not missing, f"the explanation of these classes is missing: {missing}"
    assert "all false positives" in text


def test_the_file_is_not_a_blanket() -> None:
    """The point of the file is that it is finite; a runaway list is a reason to look again, not to extend it."""
    assert 1 <= len(_entries()) <= 200
