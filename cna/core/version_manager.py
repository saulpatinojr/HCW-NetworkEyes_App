"""Document version management — manual and automatic.

DD-012: Every generated document is versioned.
Automatic: patch bump on every regeneration.
Manual: cna version bump --doc <name> --type minor/major
"""

from datetime import datetime

from pydantic import BaseModel


class DocumentVersion(BaseModel):
    version: str  # semver: 1.0.0
    generated_at: datetime
    generated_by: str  # ai-engine | human-review | manual
    change_summary: str
    parent_version: str | None = None


def bump_version(current: str, bump_type: str = "patch") -> str:
    """Bump semver string. bump_type: patch | minor | major"""
    major, minor, patch = map(int, current.split("."))
    if bump_type == "major":
        return f"{major + 1}.0.0"
    if bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"
