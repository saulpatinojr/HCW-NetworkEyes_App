"""CI script: enforce the documentation model.

Closes TODO.md T-603: nothing prevented documentation sprawl from returning.
Hardened by T-605 – T-608. Runs in CI (repository-guardrails job) and can be
run locally.

The model is set out in full once, in README.md ("Documentation map"); this script
enforces it. What the code allows, as a document file (a file with a suffix from
DOCUMENT_SUFFIXES) in each place:

* The repository root: the four required documents — README.md, CHANGELOG.md,
  REVIEW.md, TODO.md — plus two that are allowed but not required: CLAUDE.md, the
  agent-instruction file that states the rules an AI coding agent must not infer
  wrongly (the image contract above all), and REFACTOR_APP.md, a temporary working
  document with a planned retirement. That makes six root documents at most.
* docs/ — the one home for long-form documentation (REVIEW.md R-031, decided
  2026-10-27; the GitHub Wiki that held it was deleted). Any document file at any
  depth below the top-level folder named exactly "docs". Nothing in it is required.
  The name is compared exactly, not case-folded: git is case-sensitive, so "Docs/"
  would be a second folder that Windows and macOS checkouts cannot hold beside
  "docs/". Lookalikes are violations: doc/, documentation/, Docs/, DOCS/, a docs/
  folder anywhere other than the top level (src/docs/; a docs/ folder inside docs/
  itself is only a subfolder and is fine), and a root file named docs.md. One
  folder is one home; a second one is a second source of truth. One more refusal
  inside docs/: the community-file names (SECURITY.md and the rest) directly in
  docs/, and the ISSUE_TEMPLATE/ and PULL_REQUEST_TEMPLATE/ folders directly under
  it, stay violations, so that docs/ never holds a second hidden copy of what .github/
  holds (ticket #247 keeps them in .github/ only). GitHub documents most of those names
  as readable from docs/; FUNDING.md and ISSUE_TEMPLATE/ are refused as this
  repository's choice, not because GitHub reads them there. See the comment on
  DOCS_REFUSED_DOCUMENTS.
* .github/: the community-health files GitHub reads, and only where GitHub reads
  them: SECURITY.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md, PULL_REQUEST_TEMPLATE.md,
  SUPPORT.md and FUNDING.md directly in .github/, and markdown files directly in
  .github/ISSUE_TEMPLATE/ and .github/PULL_REQUEST_TEMPLATE/ (issue forms are .yml,
  which is not a document suffix). The same name anywhere else, or any other
  markdown under .github/, is a violation (ticket #247).
* Nowhere else. Vendored agent configuration (.claude/, .agents/, .codex/, .kiro/)
  is excluded from the scan.

The rule for docs/ is about location only. Files without a document suffix (the JSON
role definition in docs/roles/, images, diagrams) were never covered by this script.

The required four are enforced in both directions: a missing required document
is a violation, not just an extra one (T-605).

Candidates come from `git ls-files`, not a filesystem walk, because the rule is
about what the *repository* contains. Untracked scratch — .pytest_cache/README.md
and friends — is not the repository and must not fail the guard (T-608).

Documents are matched on a case-folded suffix set rather than a `*.md` glob, so
ROADMAP.MD, NOTES.markdown, and PLAN.rst cannot slip through (T-606).

Exit 0: the four required documents are present and nothing outside the allow-list is documentation.
Exit 1: a required document is missing, or a file violates the model — blocks merge.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ALLOWED_ROOT_DOCUMENTS = {
    "README.md",
    "CHANGELOG.md",
    "REVIEW.md",
    "TODO.md",
}

# Agent instructions for AI coding tools. Allowed at the root, never required.
AGENT_INSTRUCTION_DOCUMENTS = {
    "CLAUDE.md",
}

# Allowed at the root but not required to exist — temporary working documents
# with a planned retirement (removed again once their work ships).
OPTIONAL_ROOT_DOCUMENTS = {
    # The owner-approved refactoring plan this repository executes (HCW App-to-AddOn
    # initiative, 2026-10); retired once its change sets have shipped.
    "REFACTOR_APP.md",
}

# The one home for long-form documentation (REVIEW.md R-031): the top-level folder with exactly
# this name. Compared exactly, not case-folded — see the module docstring.
DOCS_DIRECTORY = "docs"

_ALLOWED_ROOT_LOWER = {
    name.lower()
    for name in ALLOWED_ROOT_DOCUMENTS | OPTIONAL_ROOT_DOCUMENTS | AGENT_INSTRUCTION_DOCUMENTS
}

# Extensions GitHub renders as a document. Compared case-folded, so ROADMAP.MD
# and NOTES.Md are caught alongside notes.md (T-606).
DOCUMENT_SUFFIXES = {
    ".md",
    ".markdown",
    ".mdown",
    ".mkd",
    ".rst",
    ".adoc",
    ".asciidoc",
    ".textile",
    ".rdoc",
    ".org",
    ".pod",
    ".creole",
    ".wiki",
}

# Vendored agent configuration and tooling directories — not project
# documentation, out of scope for the model (TODO.md T-604). Tracked files live
# under the first four, so the exclusion is still required even though
# candidates now come from git. `.kiro/` holds the Kiro spec workspace
# (requirements/design/tasks of a spec run), which is agent tooling on the
# same footing as `.claude/`.
EXCLUDED_DIRS = {
    "local",  # vendored agent configuration, gitignored (TODO T-411)
    ".git",
    ".claude",
    ".agents",
    ".codex",
    ".kiro",
    "node_modules",
    ".venv",
    "venv",
}

# Community-health documents GitHub reads from `.github/<name>`. Compared case-folded, like the root documents
# (GitHub itself accepts pull_request_template.md and PULL_REQUEST_TEMPLATE.md).
ALLOWED_GITHUB_DOCUMENTS = {
    "PULL_REQUEST_TEMPLATE.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SUPPORT.md",
    "FUNDING.md",
}

_ALLOWED_GITHUB_LOWER = {name.lower() for name in ALLOWED_GITHUB_DOCUMENTS}

# Directories GitHub reads template collections from: `.github/ISSUE_TEMPLATE/<file>` and
# `.github/PULL_REQUEST_TEMPLATE/<file>`. One level only.
GITHUB_TEMPLATE_DIRECTORIES = {"ISSUE_TEMPLATE", "PULL_REQUEST_TEMPLATE"}

_GITHUB_TEMPLATE_DIRECTORIES_LOWER = {name.lower() for name in GITHUB_TEMPLATE_DIRECTORIES}

# Names refused directly in docs/ (and the template folders directly under it), so that docs/ never holds
# a second hidden copy of what .github/ holds. Two kinds of reason, kept apart because only one is a GitHub fact.
#
# What GitHub documents (the text of these docs.github.com pages, read 2026-10-27: "Creating a default community
# health file", "Creating a pull request template for your repository", "Adding a code of conduct to your project",
# "Setting guidelines for repository contributors", "Adding support resources to your project" and "Adding an
# accessibility page to your repository"): ACCESSIBILITY.md, CODE_OF_CONDUCT.md, CONTRIBUTING.md, SECURITY.md and
# SUPPORT.md are read from .github/, the repository root or docs/, and a pull request template is read from
# pull_request_template.md or a PULL_REQUEST_TEMPLATE/ folder in .github/, the root or docs/. A copy in docs/ could
# therefore be shown by GitHub as the repository's own policy.
#
# This repository's choice, not a GitHub claim: FUNDING.md and an ISSUE_TEMPLATE/ folder are refused in docs/ too.
# The same pages document only .github/FUNDING.yml and .github/ISSUE_TEMPLATE/ (no docs/ location), so GitHub would
# not read them there; they stay refused because ticket #247 allows them in .github/ only and one rule is simpler
# than a different one per name. GOVERNANCE.md appears on none of the ten pages read for this (those six plus the
# pages on issue templates, issue template configuration, community profiles and the sponsor button) and is not refused.
DOCS_REFUSED_DOCUMENTS = ALLOWED_GITHUB_DOCUMENTS | {"ACCESSIBILITY.md"}
_DOCS_REFUSED_DOCUMENTS_LOWER = {name.lower() for name in DOCS_REFUSED_DOCUMENTS}


def is_excluded(relative: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in relative.parts)


def is_document(relative: Path) -> bool:
    return relative.suffix.lower() in DOCUMENT_SUFFIXES


def is_under_docs(relative: Path) -> bool:
    """True for a file inside the top-level docs/ folder, at any depth below it."""
    return len(relative.parts) > 1 and relative.parts[0] == DOCS_DIRECTORY


def is_github_reserved_in_docs(relative: Path) -> bool:
    """A community-file name (or template folder) directly in docs/, which the model refuses.

    The model keeps community files in .github/ only (ticket #247). GitHub also reads most of them
    from docs/, so a copy there could be shown as the repository's own policy; see the comment on
    DOCS_REFUSED_DOCUMENTS for which names GitHub documents in docs/ and which are refused only
    as this repository's choice. Only the places directly in docs/ are refused: the file names
    directly in it, and the two template folders directly under it.
    """
    if len(relative.parts) == 2:
        return relative.name.lower() in _DOCS_REFUSED_DOCUMENTS_LOWER
    return relative.parts[1].lower() in _GITHUB_TEMPLATE_DIRECTORIES_LOWER


def is_allowed(relative: Path) -> bool:
    if len(relative.parts) == 1:
        return relative.name.lower() in _ALLOWED_ROOT_LOWER
    if is_under_docs(relative):
        return not is_github_reserved_in_docs(relative)
    if relative.parts[0] == ".github":
        if len(relative.parts) == 2:
            return relative.name.lower() in _ALLOWED_GITHUB_LOWER
        # Issue/PR template collections, e.g. .github/ISSUE_TEMPLATE/bug.md (exactly one level down)
        return len(relative.parts) == 3 and relative.parts[1] in GITHUB_TEMPLATE_DIRECTORIES
    return False


def tracked_files() -> list[Path]:
    """Every file git tracks, relative to REPO_ROOT.

    Falls back to a filesystem walk when git is unavailable or REPO_ROOT is not
    a work tree (a source tarball, say). The fallback warns, because it cannot
    tell a committed document from untracked scratch.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
            capture_output=True,
            text=True,
            check=True,
        )
    except OSError, subprocess.CalledProcessError:
        print(
            "WARNING: git unavailable — falling back to a filesystem walk. "
            "Untracked files may be reported.",
            file=sys.stderr,
        )
        return [p.relative_to(REPO_ROOT) for p in REPO_ROOT.rglob("*") if p.is_file()]

    return [Path(line) for line in result.stdout.split("\0") if line]


def validate() -> bool:
    documents = [
        relative
        for relative in tracked_files()
        if not is_excluded(relative) and is_document(relative)
    ]

    root_documents = {relative.name for relative in documents if len(relative.parts) == 1}
    missing = sorted(name for name in ALLOWED_ROOT_DOCUMENTS if name not in root_documents)
    violations = sorted(relative for relative in documents if not is_allowed(relative))

    if missing:
        print(
            "Documentation model violation — required document(s) missing:",
            file=sys.stderr,
        )
        print(file=sys.stderr)
        for name in missing:
            print(f"  {name}", file=sys.stderr)
        print(file=sys.stderr)
        print(
            "The repository requires four markdown documents (README.md, CHANGELOG.md,",
            file=sys.stderr,
        )
        print(
            "REVIEW.md, TODO.md). Restore the missing file(s) rather than deleting the model.",
            file=sys.stderr,
        )

    if violations:
        if missing:
            print(file=sys.stderr)
        print(
            "Documentation model violation — document files are allowed only here:",
            file=sys.stderr,
        )
        print(
            "  * the repository root: README.md, CHANGELOG.md, REVIEW.md and TODO.md (required),",
            file=sys.stderr,
        )
        print(
            "    CLAUDE.md and the temporary REFACTOR_APP.md (optional), six at most;",
            file=sys.stderr,
        )
        print(
            "  * the folder named exactly docs/ at the top of the repository, at any depth",
            file=sys.stderr,
        )
        print(
            "    (long-form documentation; not Docs/, doc/, documentation/ or a docs/ anywhere but the",
            file=sys.stderr,
        )
        print(
            "    top level, and not a community-file name such as SECURITY.md, which belongs in .github/);",
            file=sys.stderr,
        )
        print(
            "  * the GitHub community files in .github/ (SECURITY.md, CONTRIBUTING.md,",
            file=sys.stderr,
        )
        print(
            "    CODE_OF_CONDUCT.md, PULL_REQUEST_TEMPLATE.md, SUPPORT.md, FUNDING.md and the",
            file=sys.stderr,
        )
        print(
            "    files in .github/ISSUE_TEMPLATE/ and .github/PULL_REQUEST_TEMPLATE/).",
            file=sys.stderr,
        )
        print('The model is set out in full in README.md, "Documentation map".', file=sys.stderr)
        print(file=sys.stderr)
        # Every file allowed under docs/ is accepted, so a violation under docs/ is always a refused
        # community-file name. Moving it into docs/ would not help, so it gets its own hint.
        outside_docs = [violation for violation in violations if not is_under_docs(violation)]
        in_docs = [violation for violation in violations if is_under_docs(violation)]
        if outside_docs:
            print("Document files in a place the model does not allow:", file=sys.stderr)
            for violation in outside_docs:
                print(f"  {violation}", file=sys.stderr)
            print(file=sys.stderr)
            print(
                "Move long-form content into docs/, or into one of the other allowed documents,",
                file=sys.stderr,
            )
            print("then delete the file.", file=sys.stderr)
        if in_docs:
            if outside_docs:
                print(file=sys.stderr)
            print(
                "Files inside docs/ named like a GitHub community file (GitHub reads those names",
                file=sys.stderr,
            )
            print(
                "from docs/ as well as .github/, and the model keeps them in .github/ only):",
                file=sys.stderr,
            )
            for violation in in_docs:
                print(f"  {violation}", file=sys.stderr)
            print(file=sys.stderr)
            print(
                "These are already in docs/, so moving them there would not help. Rename the page",
                file=sys.stderr,
            )
            print(
                "(for example security-notes.md). A real community file belongs in .github/, and only",
                file=sys.stderr,
            )
            print("the names listed above are allowed there.", file=sys.stderr)

    if missing or violations:
        return False

    docs_documents = [relative for relative in documents if is_under_docs(relative)]
    print(
        f"Documentation model OK: {len(root_documents)} root documents, "
        f"{len(docs_documents)} under docs/, nothing outside the allow-list."
    )
    return True


if __name__ == "__main__":
    sys.exit(0 if validate() else 1)
