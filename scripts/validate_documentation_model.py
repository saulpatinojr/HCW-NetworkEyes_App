"""CI script: enforce the documentation model.

Closes TODO.md T-603: nothing prevented documentation sprawl from returning.
Hardened by T-605 – T-608. Runs in CI (repository-guardrails job) and can be
run locally.

The model (README.md → "Repository conventions"): the repository keeps four
required documents — README.md, CHANGELOG.md, REVIEW.md, TODO.md — and long-form
documentation lives in the GitHub Wiki. Three more root documents are allowed
but not required: CLAUDE.md, the agent-instruction file that states the rules an
AI coding agent must not infer wrongly (the core ↔ appliance contract above
all), and two temporary working documents with a planned retirement,
CNA-0.90-updates.md and REFACTOR_APP.md. That makes seven root documents at
most. Vendored agent configuration (.claude/, .agents/, .codex/, .kiro/) is
excluded. Platform-required documents under .github/ are permitted.

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
# with a planned retirement (removed again once their release ships).
OPTIONAL_ROOT_DOCUMENTS = {
    "CNA-0.90-updates.md",
    # The owner-approved refactoring plan this repository executes (HCW App-to-AddOn
    # initiative, 2026-10); retired once its change sets have shipped.
    "REFACTOR_APP.md",
}

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

# Platform-required documents GitHub reads from these paths. None exist
# today; the allowance is here so adding one later does not break CI.
ALLOWED_GITHUB_DOCUMENTS = {
    "PULL_REQUEST_TEMPLATE.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SUPPORT.md",
    "FUNDING.md",
}


def is_excluded(relative: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in relative.parts)


def is_document(relative: Path) -> bool:
    return relative.suffix.lower() in DOCUMENT_SUFFIXES


def is_allowed(relative: Path) -> bool:
    if len(relative.parts) == 1:
        return relative.name.lower() in _ALLOWED_ROOT_LOWER
    if relative.parts[0] == ".github":
        if relative.name in ALLOWED_GITHUB_DOCUMENTS:
            return True
        # Issue/PR template collections, e.g. .github/ISSUE_TEMPLATE/bug.md
        return "ISSUE_TEMPLATE" in relative.parts or "PULL_REQUEST_TEMPLATE" in relative.parts
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
            "Documentation model violation — the repository allows seven root documents",
            file=sys.stderr,
        )
        print(
            "at most: README.md, CHANGELOG.md, REVIEW.md and TODO.md (required), CLAUDE.md, and the",
            file=sys.stderr,
        )
        print(
            "temporary CNA-0.90-updates.md and REFACTOR_APP.md (optional).",
            file=sys.stderr,
        )
        print("Long-form documentation belongs in the GitHub Wiki.", file=sys.stderr)
        print(file=sys.stderr)
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        print(file=sys.stderr)
        print(
            "Move the content to one of the allowed documents or the Wiki",
            file=sys.stderr,
        )
        print("(content determines destination), then delete the file.", file=sys.stderr)

    if missing or violations:
        return False

    print(
        f"Documentation model OK: {len(root_documents)} root documents, "
        "nothing outside the allow-list."
    )
    return True


if __name__ == "__main__":
    sys.exit(0 if validate() else 1)
