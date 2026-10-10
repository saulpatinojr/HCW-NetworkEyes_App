"""SHA-pin checker for the ``cicd`` area (Requirement 5.3).

Spec task 9.1 (:mod:`cna.review.areas.cicd`) audited runner topology and
best-practice gaps but deliberately left third-party action SHA-pinning (5.3)
to this task (9.3) so the two do not double-count.

SHA-pinning (5.3, design Property 14). Every third-party ``uses:`` reference in
``.github/workflows/*.yml`` must be pinned to a **40-hex commit SHA**
(``owner/repo@<40-hex>``). A reference pinned to a tag or branch
(``actions/checkout@v4``) is mutable — the tag can be re-pointed at malicious
code after review — so it is recorded as an unpinned finding. The checker
classifies each ``uses:`` value:

  * ``owner/repo@<ref>`` — a third-party action. Pinned iff ``<ref>`` is exactly
    40 hexadecimal characters. Anything else (a ``vN`` tag, a branch, a short
    SHA) is recorded.
  * ``./path`` or ``owner/repo/.github/workflows/file.yml@<ref>`` — a *local*
    action or a *reusable workflow* reference. Reusable-workflow refs and local
    ``./`` refs live in this repository (or are governed by it), so they are not
    third-party actions subject to the 40-hex-SHA rule and are handled sensibly:
    local ``./`` refs are never flagged; a reusable-workflow ref pinned to a SHA
    is fine, and one pinned to a tag/branch is out of scope for the third-party
    rule (it references first-party workflow code, not a third-party action).
  * ``docker://image@sha256:...`` — a container action reference; out of scope
    for the GitHub-action 40-hex-SHA rule.

Property 14 pins the checker's contract exactly: *for any* workflow ``uses:``
reference to a third-party action, the checker records the reference *exactly
when* it is not pinned to a 40-hex commit SHA. :func:`is_third_party_action` and
:func:`is_sha_pinned` are the two predicates that decision rests on.

The live scan over ``.github/workflows/`` at authoring time found two unpinned
third-party references — ``actions/checkout@v4`` in the AWS deploy workflow and
``actions/create-github-app-token@v3`` in the Azure deploy workflow. Both
workflows left the core with the deployment layer (``TODO.md`` T-504) and are
now the appliances' to pin; every ``uses:`` reference that remains here is
40-hex pinned, so the scan records the single informational all-pinned entry.

Each *distinct* unpinned reference found is recorded once as a fixable
``Finding`` (MEDIUM: a mutable tag is a supply-chain exposure,
engineering-fixable by pinning to the tag's current commit SHA). The R-003
escalation for the AWS deploy workflow (5.4) that used to be recorded here is
owned by the AWS appliance's ``REVIEW.md``. These records are consumed by the
consolidation step (spec task 14.1).
"""

from __future__ import annotations

import re
from pathlib import Path

from cna.review.model import Finding, Severity

_AREA = "cicd"

# Repo-relative directory holding the numbered workflows. Resolved from this
# file's location so the checker scans the real tree, not a fixture.
_WORKFLOWS_DIR = Path(__file__).resolve().parents[3] / ".github" / "workflows"

# A ``uses:`` line: capture the reference value (strip an inline ``# comment``).
_USES_RE = re.compile(r"""^\s*-?\s*uses:\s*(?P<ref>[^\s#]+)""")

# A 40-character lowercase-or-uppercase hex commit SHA.
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def is_local_reference(ref: str) -> bool:
    """True for a local action reference (``./path`` or ``../path``).

    Local references resolve inside the repository, so they are never a
    third-party action subject to the SHA-pin rule.
    """
    return ref.startswith("./") or ref.startswith("../")


def is_docker_reference(ref: str) -> bool:
    """True for a container action reference (``docker://...``).

    Out of scope for the GitHub-action 40-hex commit-SHA rule (a Docker ref
    pins by ``sha256:`` digest or tag, not a 40-hex git SHA).
    """
    return ref.startswith("docker://")


def is_reusable_workflow_reference(ref: str) -> bool:
    """True for a reusable-workflow reference (``owner/repo/….yml@ref``).

    A reusable-workflow ``uses:`` points at a workflow *file* path ending in
    ``.yml``/``.yaml`` (before the ``@ref``), not at an action. These reference
    first-party workflow code and are not third-party actions under the 5.3
    rule, so they are handled sensibly rather than flagged as unpinned actions.
    """
    path_part = ref.split("@", 1)[0]
    return path_part.endswith(".yml") or path_part.endswith(".yaml")


def is_third_party_action(ref: str) -> bool:
    """True iff ``ref`` is a third-party action reference (``owner/repo@ref``).

    Third-party actions are the references the 5.3 SHA-pin rule governs. A
    local ``./`` ref, a ``docker://`` ref, and a reusable-workflow ``.yml@ref``
    are excluded. A well-formed action ref is ``owner/repo[/subpath]@ref`` — it
    contains an ``@`` and at least one ``/`` in the path before it.
    """
    if is_local_reference(ref) or is_docker_reference(ref):
        return False
    if "@" not in ref:
        return False
    if is_reusable_workflow_reference(ref):
        return False
    path_part = ref.split("@", 1)[0]
    return "/" in path_part


def is_sha_pinned(ref: str) -> bool:
    """True iff ``ref``'s ``@`` component is exactly a 40-hex commit SHA."""
    if "@" not in ref:
        return False
    _, _, git_ref = ref.partition("@")
    return bool(_SHA_RE.match(git_ref))


def scan_uses_references(workflow_text: str) -> list[str]:
    """Return every ``uses:`` reference value in a workflow's text, in order."""
    refs: list[str] = []
    for line in workflow_text.splitlines():
        match = _USES_RE.match(line)
        if match:
            refs.append(match.group("ref"))
    return refs


def find_unpinned_references(workflow_text: str) -> list[str]:
    """Return the third-party ``uses:`` refs that are *not* 40-hex SHA pinned.

    This is the decision Property 14 pins: a reference is returned exactly when
    it is a third-party action and it is not pinned to a 40-hex commit SHA.
    """
    return [
        ref
        for ref in scan_uses_references(workflow_text)
        if is_third_party_action(ref) and not is_sha_pinned(ref)
    ]


def _scan_workflow_tree(
    workflows_dir: Path = _WORKFLOWS_DIR,
) -> dict[str, list[str]]:
    """Map each workflow file name → its distinct unpinned third-party refs.

    Refs are de-duplicated per file (a ref used in three jobs is one finding
    for that file) while preserving first-seen order. Files with no unpinned
    reference are omitted.
    """
    result: dict[str, list[str]] = {}
    if not workflows_dir.is_dir():
        return result
    for path in sorted(workflows_dir.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        seen: list[str] = []
        for ref in find_unpinned_references(text):
            if ref not in seen:
                seen.append(ref)
        if seen:
            result[path.name] = seen
    return result


def sha_pin_findings(workflows_dir: Path = _WORKFLOWS_DIR) -> list[Finding]:
    """Return the Requirement 5.3 SHA-pinning findings for the CI/CD area.

    Scans the real ``.github/workflows/`` tree and records one MEDIUM finding
    per distinct unpinned third-party ``uses:`` reference per workflow. When
    every reference is already 40-hex pinned, a single verified-compliant
    INFORMATIONAL record is returned so the plan reflects that 5.3 was audited,
    not merely that nothing broke.
    """
    unpinned = _scan_workflow_tree(workflows_dir)
    findings: list[Finding] = []

    for workflow in sorted(unpinned):
        for ref in unpinned[workflow]:
            action = ref.split("@", 1)[0]
            findings.append(
                Finding(
                    area=_AREA,
                    severity=Severity.MEDIUM,
                    proposed_action=(
                        f"{workflow} references the third-party action '{ref}', "
                        "which is pinned to a mutable tag/branch rather than a "
                        "40-hex commit SHA. A tag can be re-pointed at malicious "
                        f"code after review, so pin '{action}' to the commit SHA "
                        "the tag currently resolves to (keeping the tag in a "
                        "trailing comment for readability), matching every other "
                        "already-pinned uses: reference in the workflow tree."
                    ),
                    dedup_key=f"cicd:sha-pin:{workflow}:{action}",
                    subject=f".github/workflows/{workflow}",
                )
            )

    if not findings:
        findings.append(
            Finding(
                area=_AREA,
                severity=Severity.INFORMATIONAL,
                proposed_action=(
                    "Verified compliant: every third-party uses: reference "
                    "across .github/workflows/ is pinned to a 40-hex commit SHA. "
                    "Keep new workflows pinning actions to a commit SHA rather "
                    "than a mutable tag."
                ),
                dedup_key="cicd:sha-pin:all-pinned",
                subject=".github/workflows",
            )
        )

    return findings


def cicd_sha_and_escalation_findings(
    workflows_dir: Path = _WORKFLOWS_DIR,
) -> list[Finding]:
    """Return spec task 9.3's findings: the SHA-pinning scan (5.3).

    The R-003 escalation for the AWS deploy workflow (5.4) that this function
    used to append left the core with that workflow (``TODO.md`` T-504); the
    AWS appliance's ``REVIEW.md`` owns it. The name is kept so the plan wiring
    and its tests read the same.
    """
    return [*sha_pin_findings(workflows_dir)]
