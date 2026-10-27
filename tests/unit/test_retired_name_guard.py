"""A retired product name stays out of the repository, and the product is spelled in one word (owner decision 2026-10-27).

The owner's rule: the name of a product that is no longer associated with Hybrid Cloud Works is not written in this
repository, even as a reference, and the product itself is written "NetworkEyes", never as two words. The patterns below
are built from pieces, so this file does not contain the retired name, its long form or the two-word spelling itself.

``CHANGELOG.md`` is a dated record that quotes the old report text, so it may hold the two-word spelling; no file may
hold the retired name.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
# Same convention as test_free_tool_wording.py: the `cna-test` compose service builds from a context without `.git`,
# where there is nothing to list. A worktree has `.git` as a file, so the check is `exists()`, not `is_dir()`.
if shutil.which("git") is None or not (REPO_ROOT / ".git").exists():
    pytest.skip("needs a git checkout and the git program", allow_module_level=True)

_SHORT = "c" + "na"
_SECOND_WORD = "plat" + "form"
_LONG = "Cloud" + r"\s+Network\s+Assessment"

# A letter or digit may not come right before the short name (so `apps/cna-web` and `HCW_<name>` are judged on what
# follows), but an underscore, hyphen or slash may. Up to 16 characters that are not letters or digits may separate
# the two words: a space, hyphen, underscore, bracket, dot, slash, apostrophe, markdown emphasis, a dash, or a line
# break with an indented continuation (a Windows line break counts as two characters).
RETIRED_NAME = re.compile(
    rf"(?<![A-Za-z0-9]){_SHORT}(?:['’]s)?[\W_]{{0,16}}{_SECOND_WORD}", re.IGNORECASE
)
# The same name written out: the long form, with or without the short form in brackets before the second word.
RETIRED_LONG_FORM = re.compile(
    rf"{_LONG}[\W_]{{0,16}}(?:{_SHORT}[\W_]{{0,16}})?{_SECOND_WORD}", re.IGNORECASE
)
# The product in two words, with any separator or a non-breaking-space entity between them.
TWO_WORDS = re.compile(
    r"(?<![A-Za-z0-9])Network(?:[\W_]|&nbsp;|&#160;|&#x[aA]0;){1,16}Eyes", re.IGNORECASE
)
DATED_RECORDS = frozenset({"CHANGELOG.md"})
#: There are 565 tracked files today. A scan that sees far fewer has lost its list.
PLAUSIBLE_FILE_COUNT = 100


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
        capture_output=True,
        check=True,
    ).stdout
    return [name for name in out.decode("utf-8", errors="replace").split("\0") if name]


def _text_of(name: str) -> str | None:
    try:
        data = (REPO_ROOT / name).read_bytes()
    except FileNotFoundError:  # a tracked file that was deleted in the working tree
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


def test_the_scan_sees_a_plausible_number_of_files() -> None:
    assert len(_tracked_files()) > PLAUSIBLE_FILE_COUNT


def test_the_retired_name_is_in_no_tracked_file_or_file_name() -> None:
    hits = _hits(RETIRED_NAME)
    assert not hits, f"the retired product name is back (owner rule 2026-10-27): {hits}"


def test_the_long_form_of_the_retired_name_is_in_no_tracked_file() -> None:
    hits = _hits(RETIRED_LONG_FORM)
    assert not hits, (
        f"the long form of the retired product name is back (owner rule 2026-10-27): {hits}"
    )


def test_the_product_is_never_written_as_two_words_outside_the_dated_record() -> None:
    hits = _hits(TWO_WORDS, skip=DATED_RECORDS)
    assert not hits, f'write the product as "NetworkEyes", one word (owner rule 2026-10-27): {hits}'


def test_the_retired_name_pattern_catches_every_spelling_that_was_found_or_could_come_back() -> (
    None
):
    first = _SHORT.upper()
    word = _SECOND_WORD
    spellings = [
        f"{first} {word.capitalize()}",
        f"{first} {word}",
        f"({first}) {word}",
        f"{_SHORT}-{word}-cert",
        f"certs/{_SHORT}-{word}.pfx",
        f"{first}_{word.upper()}",
        f"HCW_{first}_{word.upper()}_URL",  # a prefix joined by an underscore
        f"{first}\n{word}",
        f"({first})\r\n  {word}",  # a Windows line break and an indented continuation
        f"({first})\n    {word}",
        f"{_SHORT}.{word}",
        f"{_SHORT}/{word}",
        f"{first}'s {word}",
        f"**{first}** {word}",
        f"{first} — {word}",  # an em dash
        f"{_SHORT}{word}",  # no separator at all
    ]
    for text in spellings:
        assert RETIRED_NAME.search(text), repr(text)


def test_the_retired_name_pattern_leaves_the_code_names_alone() -> None:
    first = _SHORT.upper()
    for text in (
        f"the {_SHORT} Python package",
        f"apps/{_SHORT}-web",
        f"{first}_API_TOKEN",
        f"{first}-ReadOnly",
        f"a {_SECOND_WORD} for networks",
        f"{_SHORT}.core.exceptions",
        f"a{_SHORT} {_SECOND_WORD}",  # a letter right before the short name
    ):
        assert not RETIRED_NAME.search(text), repr(text)


def test_the_long_form_pattern_catches_the_long_spellings_and_spares_the_description() -> None:
    first = _SHORT.upper()
    long_name = "Cloud Network Assessment"
    for text in (
        f"{long_name} {_SECOND_WORD}",
        f"{long_name} ({first}) {_SECOND_WORD.capitalize()}",
        f"{long_name} {_SECOND_WORD.capitalize()} CLI",
        f"{long_name}\r\n  {_SECOND_WORD}",
    ):
        assert RETIRED_LONG_FORM.search(text), repr(text)
    for text in (
        long_name,
        f"NetworkEyes — {long_name}",
        f"{long_name} tool",
        f"{long_name} ({first})",
    ):
        assert not RETIRED_LONG_FORM.search(text), repr(text)


def test_the_two_word_pattern_catches_every_split_and_spares_the_one_word_name() -> None:
    first, second = (
        "Net" + "work",
        "Ey" + "es",
    )  # pieces, so this file does not hold the spelling itself
    for text in (
        f"{first} {second}",
        f"{first.lower()} {second.lower()}",
        f"{first}\n{second}",
        f"{first}\r\n  {second}",
        f"{first}-{second}",
        f"{first.lower()}_{second.lower()}",
        f"{first}&nbsp;{second}",
        f"{first} {second}",
        f"**{first}** {second}",
    ):
        assert TWO_WORDS.search(text), repr(text)
    for text in (
        f"{first}{second}",
        f"{first.lower()}{second.lower()}",
        f"HCW-{first}{second}_App",
        f"product:{first.lower()}{second.lower()}",
        f"the {first.lower()} and {second.lower()}",
    ):
        assert not TWO_WORDS.search(text), repr(text)
