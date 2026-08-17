"""CI script: enforce the four-document documentation model.

Closes TODO.md T-603: nothing prevented documentation sprawl from returning.
Hardened by T-605 – T-608. Runs in CI (repository-guardrails job) and can be
run locally.

The model (README.md → "Repository conventions"): the repository keeps exactly
four markdown documents — README.md, CHANGELOG.md, REVIEW.md, TODO.md — and
long-form documentation lives in the GitHub Wiki. Vendored agent configuration
(.claude/, .agents/, .codex/) is excluded. Platform-required documents under
.github/ are permitted.

"Exactly four" is enforced in both directions: a missing required document is a
violation, not just an extra one (T-605).

Candidates come from `git ls-files`, not a filesystem walk, because the rule is
about what the *repository* contains. Untracked scratch — .pytest_cache/README.md
and friends — is not the repository and must not fail the guard (T-608).

Documents are matched on a case-folded suffix set rather than a `*.md` glob, so
ROADMAP.MD, NOTES.markdown, and PLAN.rst cannot slip through (T-606).

Exit 0: the four documents are present and nothing else is documentation.
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

_ALLOWED_ROOT_LOWER = {name.lower() for name in ALLOWED_ROOT_DOCUMENTS}

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
# under the first three, so the exclusion is still required even though
# candidates now come from git.
EXCLUDED_DIRS = {
    ".git",
    ".claude",
    ".agents",
    ".codex",
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
    except (OSError, subprocess.CalledProcessError):
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
            "The repository keeps exactly four markdown documents. Restore the",
            file=sys.stderr,
        )
        print("missing file(s) rather than deleting the model.", file=sys.stderr)

    if violations:
        if missing:
            print(file=sys.stderr)
        print(
            "Documentation model violation — the repository keeps exactly four",
            file=sys.stderr,
        )
        print(
            "markdown documents (README.md, CHANGELOG.md, REVIEW.md, TODO.md).",
            file=sys.stderr,
        )
        print("Long-form documentation belongs in the GitHub Wiki.", file=sys.stderr)
        print(file=sys.stderr)
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        print(file=sys.stderr)
        print(
            "Move the content to one of the four documents or the Wiki",
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
