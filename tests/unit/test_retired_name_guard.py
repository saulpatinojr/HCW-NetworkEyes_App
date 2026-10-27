"""A retired product name stays out of the repository, and the product is spelled in one word (owner decision 2026-10-27).

The owner's rule: the name of a product that is no longer associated with Hybrid Cloud Works is not written in this
repository, even as a reference, and the product itself is written "NetworkEyes", never as two words. The patterns below
are built from pieces, so this file does not contain the retired name or the two-word spelling itself.

``CHANGELOG.md`` and ``REVIEW.md`` are dated records that quote the old report text, so they may hold the two-word
spelling; no file may hold the retired name.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_SHORT = "c" + "na"
_SECOND_WORD = "plat" + "form"
# the short code name, one to four separator characters (space, hyphen, underscore, a closing bracket), then the second word
RETIRED_NAME = re.compile(rf"\b{_SHORT}[)\s_-]{{1,4}}{_SECOND_WORD}", re.IGNORECASE)

_TWO_WORDS = re.compile(r"\bNetwork" + r"[ \t]+" + "Eyes", re.IGNORECASE)
DATED_RECORDS = frozenset({"CHANGELOG.md", "REVIEW.md"})


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [name for name in out.split("\0") if name]


def _text_of(name: str) -> str | None:
    try:
        data = (REPO_ROOT / name).read_bytes()
    except OSError:  # a tracked file that was deleted in the working tree
        return None
    if b"\0" in data:  # an image, a font or another binary file
        return None
    return data.decode("utf-8", errors="replace")


def _hits(pattern: re.Pattern[str], skip: frozenset[str] = frozenset()) -> list[str]:
    found: list[str] = []
    for name in _tracked_files():
        if name in skip:
            continue
        if pattern.search(name):
            found.append(f"{name} (file name)")
        text = _text_of(name)
        if text is None:
            continue
        for match in pattern.finditer(text):
            found.append(f"{name}:{text.count(chr(10), 0, match.start()) + 1}")
    return found


def test_the_retired_name_is_in_no_tracked_file_or_file_name() -> None:
    hits = _hits(RETIRED_NAME)
    assert not hits, f"the retired product name is back (owner rule 2026-10-27): {hits}"


def test_the_product_is_never_written_as_two_words_outside_the_dated_records() -> None:
    hits = _hits(_TWO_WORDS, skip=DATED_RECORDS)
    assert not hits, f'write the product as "NetworkEyes", one word (owner rule 2026-10-27): {hits}'


def test_the_retired_name_pattern_catches_every_spelling_that_was_found() -> None:
    first = _SHORT.upper()
    spellings = [
        f"{first} {_SECOND_WORD.capitalize()}",
        f"{first} {_SECOND_WORD}",
        f"({first}) {_SECOND_WORD}",
        f"{_SHORT}-{_SECOND_WORD}-cert",
        f"certs/{_SHORT}-{_SECOND_WORD}.pfx",
        f"{first}_{_SECOND_WORD.upper()}",
        f"{first}\n{_SECOND_WORD}",
    ]
    for text in spellings:
        assert RETIRED_NAME.search(text), text


def test_the_retired_name_pattern_leaves_the_code_names_alone() -> None:
    first = _SHORT.upper()
    for text in (
        f"the {_SHORT} Python package",
        f"apps/{_SHORT}-web",
        f"{first}_API_TOKEN",
        f"{first}-ReadOnly",
        f"a {_SECOND_WORD} for networks",
        f"{_SHORT}.core.exceptions",
    ):
        assert not RETIRED_NAME.search(text), text
