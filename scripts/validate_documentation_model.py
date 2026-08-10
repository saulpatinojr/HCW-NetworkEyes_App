"""CI script: enforce the four-document documentation model.

Closes TODO.md T-603: nothing prevented documentation sprawl from returning.
Runs in CI (repository-guardrails job) and can be run locally.

The model (README.md → "Repository conventions"): the repository keeps exactly
four markdown documents — README.md, CHANGELOG.md, REVIEW.md, TODO.md — and
long-form documentation lives in the GitHub Wiki. Vendored agent configuration
(.claude/, .agents/, .codex/) is excluded, matching the ruff exclusion in
pyproject.toml. Platform-required documents under .github/ are permitted.

Exit 0: no markdown file outside the allow-list.
Exit 1: one or more markdown files violate the model — blocks merge.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ALLOWED_ROOT_DOCUMENTS = {
    "README.md",
    "CHANGELOG.md",
    "REVIEW.md",
    "TODO.md",
}

# Vendored agent configuration and tooling directories — not project
# documentation, out of scope for the model (TODO.md T-604).
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


def is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.parts)


def is_allowed(relative: Path) -> bool:
    if len(relative.parts) == 1:
        return relative.name in ALLOWED_ROOT_DOCUMENTS
    if relative.parts[0] == ".github":
        if relative.name in ALLOWED_GITHUB_DOCUMENTS:
            return True
        # Issue/PR template collections, e.g. .github/ISSUE_TEMPLATE/bug.md
        return "ISSUE_TEMPLATE" in relative.parts or "PULL_REQUEST_TEMPLATE" in relative.parts
    return False


def validate() -> bool:
    violations = []
    for md_file in sorted(REPO_ROOT.rglob("*.md")):
        relative = md_file.relative_to(REPO_ROOT)
        if is_excluded(relative):
            continue
        if not is_allowed(relative):
            violations.append(relative)

    if violations:
        print("Documentation model violation — the repository keeps exactly four")
        print("markdown documents (README.md, CHANGELOG.md, REVIEW.md, TODO.md).")
        print("Long-form documentation belongs in the GitHub Wiki.")
        print()
        for violation in violations:
            print(f"  {violation}")
        print()
        print("Move the content to one of the four documents or the Wiki")
        print("(content determines destination), then delete the file.")
        return False

    print("Documentation model OK: no markdown files outside the allow-list.")
    return True


if __name__ == "__main__":
    sys.exit(0 if validate() else 1)
