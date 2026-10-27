"""The documentation model is set out in full once, in the README, and it agrees with the validator.

``scripts/validate_documentation_model.py`` decides which document files may exist. The README's *Documentation map*
is the one full statement of that in words (owner decision 2026-10-27, ``REVIEW.md`` R-031: a ``docs/`` folder
replaces the deleted wiki, and the temporary 0.9.0 working document was removed). Earlier, the count in the README
("seven root documents") and in the validator's docstring ("exactly four") drifted away from what the code enforced,
and nothing noticed. These tests fail when:

* the README's count of root documents, or its list of them, differs from the validator's sets;
* a link in the map points at a file that is not there;
* another document that states the model restates the count, in any wording that gives a number, "documents", "root"
  (or "top level") and a limit such as "at most" (there must be one statement, not several that can disagree);
* the bullet of ``README.md``, ``CLAUDE.md`` or ``.github/CONTRIBUTING.md`` that says where documents live stops
  pointing at ``docs/``, or calls the destination missing;
* ``docs/README.md`` stops naming the community-file names the validator refuses inside ``docs/``;
* the removed working document comes back, or is allowed again.

The two pure helpers (``restates_the_count`` and ``bullet``) are tested on sample text, so a weakened pattern fails
here even when the real files happen to pass.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"
DOCS_INDEX = REPO_ROOT / "docs" / "README.md"
REMOVED_DOCUMENT = "CNA-0.90-updates.md"

#: Live documents that state (or point at) the model and must not restate the count of root documents. The README
#: itself is checked apart: its map says it once and nothing else in the file may.
OTHER_STATEMENT_FILES = (
    "CLAUDE.md",
    ".github/CONTRIBUTING.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    "docs/README.md",
    "REFACTOR_APP.md",
)

#: The backlog documents keep dated records that quote old counts on purpose (``TODO.md`` T-605 says "exactly four
#: documents"), so the broad wording check would flag history. They are held to the narrow phrase only, as before:
#: "<n> root documents at most" or "at most <n> root documents". ``CHANGELOG.md`` ("seven root documents") is history
#: from top to bottom and is not scanned.
BACKLOG_FILES = ("TODO.md", "REVIEW.md")

#: The bullet that says where documents live, in each document that has one: (file, text its first line starts with).
DOCUMENT_BULLETS = (
    ("README.md", "- **Documents go where the Documentation map says.**"),
    ("CLAUDE.md", "- **Documents:**"),
    (".github/CONTRIBUTING.md", "- **Documents:**"),
)

_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
_NUMBER = r"(?:\d+|" + "|".join(_NUMBER_WORDS) + r")"
_LIMIT = (
    r"(?:at\s+(?:the\s+)?most|no\s+more\s+than|up\s+to|a\s+maximum\s+of|maximum\s+of|exactly|only)"
)
#: A number, up to three words (``root``, ``required``, ``optional``...), then ``document(s)``.
_NUMBER_BEFORE_DOCUMENTS = re.compile(
    rf"\b(?P<number>{_NUMBER})\b(?:\s+[\w-]+){{0,3}}\s+documents?\b", re.IGNORECASE
)
_ROOT = re.compile(r"\broot\b|\btop[- ]level\b", re.IGNORECASE)
_LIMIT_WORDS = re.compile(rf"\b{_LIMIT}\b", re.IGNORECASE)
NARROW_COUNT_PHRASE = re.compile(
    rf"\b{_NUMBER}\s+root\s+documents?\s+at\s+most\b|\bat\s+most\s+{_NUMBER}\s+root\s+documents?\b",
    re.IGNORECASE,
)


def restates_the_count(text: str) -> list[str]:
    """The sentences of ``text`` that state how many root documents are allowed.

    A sentence counts when it has a number (word or digit) shortly before "documents", the word "root" or "top
    level", and a limit such as "at most", "no more than", "up to" or "exactly". That catches "six root documents at
    most", "at most six documents at the root" and "no more than six top-level documents" alike.
    """
    sentences = re.split(r"(?<=[.!?])\s+|\n\s*\n", text)
    return [
        " ".join(sentence.split())
        for sentence in sentences
        if _NUMBER_BEFORE_DOCUMENTS.search(sentence)
        and _ROOT.search(sentence)
        and _LIMIT_WORDS.search(sentence)
    ]


def bullet(text: str, lead: str) -> str:
    """The Markdown bullet whose first line starts with ``lead``: that line and the indented lines after it."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(lead):
            collected = [line]
            for following in lines[index + 1 :]:
                if not following.startswith((" ", "\t")):
                    break
                collected.append(following)
            return "\n".join(collected)
    raise AssertionError(f"no bullet starts with {lead!r}")


def _load_validator() -> ModuleType:
    path = REPO_ROOT / "scripts" / "validate_documentation_model.py"
    spec = importlib.util.spec_from_file_location("validate_documentation_model", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load_validator()
ROOT_DOCUMENTS = (
    set(VALIDATOR.ALLOWED_ROOT_DOCUMENTS)
    | set(VALIDATOR.AGENT_INSTRUCTION_DOCUMENTS)
    | set(VALIDATOR.OPTIONAL_ROOT_DOCUMENTS)
)


def _map_section() -> str:
    """The README text from the "Documentation map" heading to the next rule or heading."""
    text = README.read_text(encoding="utf-8")
    match = re.search(r"^## Documentation map\s*$", text, re.MULTILINE)
    assert match, "README.md has no 'Documentation map' heading"
    rest = text[match.end() :]
    end = re.search(r"^(?:---|## )", rest, re.MULTILINE)
    return rest[: end.start()] if end else rest


# --- the helpers, on sample text -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sentence",
    [
        "That makes six root documents at most.",
        "The repository allows at most six documents at the root.",
        "There are no more than six top-level documents.",
        "Up to six documents may sit at the top level of the repository.",
        "The root holds exactly four required documents.",
        "The root may hold only six documents.",
        "That makes 6 root documents at most.",
        "A maximum of seven optional documents is allowed at the root.",
    ],
)
def test_the_count_check_catches_each_wording_of_the_limit(sentence: str) -> None:
    assert restates_the_count(f"Some other sentence. {sentence} And one more.") == [sentence]


@pytest.mark.parametrize(
    "sentence",
    [
        "The repository keeps four required documents at the root plus CLAUDE.md.",
        "Long-form documentation lives in docs/ at any depth.",
        "Six documents were reviewed.",
        "At most six pull requests may be open.",
        "There are six workflows at the root of the build.",
    ],
)
def test_the_count_check_leaves_other_sentences_alone(sentence: str) -> None:
    assert restates_the_count(sentence) == []


def test_the_count_check_reads_across_a_line_break() -> None:
    assert restates_the_count("That makes six\nroot documents at most.") == [
        "That makes six root documents at most."
    ]


def test_the_bullet_helper_takes_the_bullet_and_nothing_around_it() -> None:
    text = "- **Other:** x\n  more of x\n- **Documents:** the rule\n  continued line\n\n- **Next:** y\n  docs/"
    assert bullet(text, "- **Documents:**") == "- **Documents:** the rule\n  continued line"
    with pytest.raises(AssertionError):
        bullet(text, "- **Missing:**")


# --- the real files --------------------------------------------------------------------------------------------


def test_the_readme_states_the_number_of_root_documents_the_validator_allows() -> None:
    statements = restates_the_count(_map_section())
    assert len(statements) == 1, f"the map must state the count exactly once, found: {statements}"
    match = _NUMBER_BEFORE_DOCUMENTS.search(statements[0])
    assert match
    number = match.group("number").lower()
    stated = int(number) if number.isdigit() else _NUMBER_WORDS[number]
    assert stated == len(ROOT_DOCUMENTS), (
        f"the map says {stated} root documents at most, the validator allows {len(ROOT_DOCUMENTS)}"
    )


def test_the_map_names_every_root_document_the_validator_allows() -> None:
    section = _map_section()
    missing = sorted(name for name in ROOT_DOCUMENTS if f"`{name}`" not in section)
    assert not missing, f"the Documentation map does not name: {missing}"


def test_the_map_names_the_docs_folder_and_its_index() -> None:
    section = _map_section()
    assert f"[`{VALIDATOR.DOCS_DIRECTORY}/`]({VALIDATOR.DOCS_DIRECTORY})" in section
    assert "(docs/README.md)" in section
    assert DOCS_INDEX.is_file()


def test_every_relative_link_in_the_map_resolves() -> None:
    links = re.findall(r"\]\((?P<target>[^)\s]+)\)", _map_section())
    assert links, "the map lost its links"
    broken = [
        target
        for target in links
        if not target.startswith(("http://", "https://", "#"))
        and not (REPO_ROOT / target.split("#", 1)[0]).exists()
    ]
    assert not broken, f"the Documentation map links to files that do not exist: {broken}"


def test_the_removed_working_document_is_gone_and_not_allowed() -> None:
    assert not (REPO_ROOT / REMOVED_DOCUMENT).exists()
    assert REMOVED_DOCUMENT not in ROOT_DOCUMENTS
    assert REMOVED_DOCUMENT not in _map_section()


def test_the_count_is_stated_in_the_readme_map_and_nowhere_else() -> None:
    readme = README.read_text(encoding="utf-8")
    outside_the_map = readme.replace(_map_section(), "")
    offenders = {
        name: statements
        for name, text in (
            ("README.md (outside the map)", outside_the_map),
            *(
                (name, (REPO_ROOT / name).read_text(encoding="utf-8"))
                for name in OTHER_STATEMENT_FILES
                if (REPO_ROOT / name).is_file()
            ),
        )
        if (statements := restates_the_count(text))
    }
    assert not offenders, f"the count of root documents is restated: {offenders}"


def test_the_backlog_documents_do_not_restate_the_count_in_the_narrow_phrase() -> None:
    offenders = {
        name: [m.group(0) for m in NARROW_COUNT_PHRASE.finditer(text)]
        for name in BACKLOG_FILES
        if (text := (REPO_ROOT / name).read_text(encoding="utf-8"))
        and NARROW_COUNT_PHRASE.search(text)
    }
    assert not offenders, f"the count of root documents is restated: {offenders}"


@pytest.mark.parametrize(
    "phrase",
    [
        "six root documents at most",
        "That makes six\nroot documents at most",
        "at most six root documents",
        "AT MOST 6 root document",
    ],
)
def test_the_narrow_phrase_matches_its_forms(phrase: str) -> None:
    assert NARROW_COUNT_PHRASE.search(phrase)


def test_the_docs_index_names_the_community_files_the_validator_refuses_in_docs() -> None:
    text = DOCS_INDEX.read_text(encoding="utf-8")
    missing = sorted(name for name in VALIDATOR.DOCS_REFUSED_DOCUMENTS if f"`{name}`" not in text)
    assert not missing, f"docs/README.md does not name the refused community files: {missing}"
    for directory in sorted(VALIDATOR.GITHUB_TEMPLATE_DIRECTORIES):
        assert f"`{directory}`" in text, f"docs/README.md does not name the folder {directory}"


@pytest.mark.parametrize(("document", "lead"), DOCUMENT_BULLETS)
def test_the_bullet_that_says_where_documents_live_points_to_docs(document: str, lead: str) -> None:
    text = (REPO_ROOT / document).read_text(encoding="utf-8")
    where = bullet(text, lead)
    assert "docs/" in where, f"{document}: the bullet {lead!r} no longer points to docs/"
    assert not re.search(r"no destination", where, re.IGNORECASE), (
        f"{document}: the bullet {lead!r} says long-form documentation has no destination"
    )


def test_the_map_itself_points_to_docs_and_not_to_a_wiki() -> None:
    section = _map_section()
    assert "docs/" in section
    assert not re.search(r"no destination", section, re.IGNORECASE)
