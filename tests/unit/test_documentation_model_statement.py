"""The documentation model is written out once, in the README, and it agrees with the validator.

``scripts/validate_documentation_model.py`` decides which document files may exist. The README's *Documentation map*
is the one place that says so in words (owner decision 2026-10-27, ``REVIEW.md`` R-031: a ``docs/`` folder replaces the
deleted wiki, and the temporary 0.9.0 working document was removed). Earlier, the count in the README ("seven root
documents") and in the validator's docstring ("exactly four") drifted away from what the code enforced, and nothing
noticed. These tests fail when:

* the README's count of root documents, or its list of them, differs from the validator's sets;
* a link in the map points at a file that is not there;
* another live document restates the count (there must be one statement, not several that can disagree);
* ``docs/README.md`` stops naming the community-file names the validator refuses inside ``docs/``;
* the removed working document comes back, or is allowed again.
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

#: Live documents that must not restate the count of root documents. The README itself is checked apart: its
#: map says it once and nothing else in the file may.
OTHER_LIVE_DOCUMENTS = (
    "CLAUDE.md",
    ".github/CONTRIBUTING.md",
    "docs/README.md",
    "REVIEW.md",
    "TODO.md",
    "REFACTOR_APP.md",
)
COUNT_PHRASE = re.compile(r"\broot\s+documents?\s+at\s+most\b", re.IGNORECASE)
NUMBER_WORDS = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
}


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


def test_the_readme_states_the_number_of_root_documents_the_validator_allows() -> None:
    expected = NUMBER_WORDS[len(ROOT_DOCUMENTS)]
    match = re.search(r"\b(\w+)\s+root\s+documents\s+at\s+most\b", _map_section())
    assert match, "the Documentation map no longer says how many root documents are allowed"
    assert match.group(1).lower() == expected, (
        f"the map says {match.group(1)!r} root documents at most, the validator allows {expected}"
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
    offenders = [
        name
        for name, text in (
            ("README.md (outside the map)", outside_the_map),
            *(
                (name, (REPO_ROOT / name).read_text(encoding="utf-8"))
                for name in OTHER_LIVE_DOCUMENTS
                if (REPO_ROOT / name).is_file()
            ),
        )
        if COUNT_PHRASE.search(text)
    ]
    assert not offenders, f"the count of root documents is restated in: {offenders}"


def test_the_docs_index_names_the_community_files_the_validator_refuses_in_docs() -> None:
    text = DOCS_INDEX.read_text(encoding="utf-8")
    missing = sorted(name for name in VALIDATOR.ALLOWED_GITHUB_DOCUMENTS if f"`{name}`" not in text)
    assert not missing, f"docs/README.md does not name the refused community files: {missing}"
    for directory in sorted(VALIDATOR.GITHUB_TEMPLATE_DIRECTORIES):
        assert f"`{directory}`" in text, f"docs/README.md does not name the folder {directory}"


@pytest.mark.parametrize("document", ["README.md", "CLAUDE.md", ".github/CONTRIBUTING.md"])
def test_the_documents_that_state_the_rule_point_to_docs_and_not_to_a_wiki(document: str) -> None:
    text = (REPO_ROOT / document).read_text(encoding="utf-8")
    assert "docs/" in text
    assert not re.search(r"no destination", text, re.IGNORECASE)
