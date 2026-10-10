"""Findings for the ``documentation`` area (Requirement 9).

This is the *verify-then-close-gaps* record for the documentation audit: the
four required documents (``README.md``, ``CHANGELOG.md``, ``REVIEW.md``,
``TODO.md``) plus the one optional working document (``CNA-0.90-updates.md``),
cross-checked against the actual repository tree, plus the still-open doc-task
entries and the R-009 Wiki-publication escalation.

Facts cross-checked during the audit (design "9. Documentation", Requirement
9.1) — all verified accurate, recorded as ``INFORMATIONAL`` verified-compliant
findings so the plan captures what was checked, not only what broke:

  * **Version.** ``README``/quick-start imply the platform version; the
    packaged version in ``pyproject.toml`` is ``0.8.0b0`` and the spec/intro
    calls the platform ``v0.8.0b0`` — consistent.
  * **CLI entry point.** ``README`` documents the ``cna`` CLI
    (``pip install -e .[dev]`` → ``cna --help``); ``pyproject.toml`` declares
    ``[project.scripts] cna = "cna.cli.main:cli"`` — consistent.
  * **Four-document model.** ``README``'s documentation map claims exactly four
    required markdown files plus at most one optional temporary working
    document. The repository root carries exactly ``README.md``,
    ``CHANGELOG.md``, ``REVIEW.md``, ``TODO.md`` and the one optional
    ``CNA-0.90-updates.md`` — consistent.
  * **Numbered workflows.** ``README`` conventions describe numeric workflow
    bands shared with the appliances and name the four workflows the core keeps
    (``200-build-images.yml``, ``300-test-codebase.yml``,
    ``310-release-version.yml``, ``370-registry-cleanup.yml``). All four exist
    under ``.github/workflows/`` and every referenced filename resolves —
    consistent (the deploy and operations workflows left with the deployment
    layer, ``TODO.md`` T-504).

Executable status of documented paths (Requirement 9.2):

  * **Python CLI quick start.** ``README`` documents ``pip install -e .[dev]``
    then ``cna --help``. The CLI cannot be run from a bare checkout: importing
    ``cna.cli.main`` pulls runtime dependencies (e.g. ``pydantic``) that are
    only present after the documented install step. The documented path is
    therefore *executable only after* its own install prerequisite — recorded so
    the plan states the path's executable status rather than assuming it runs.
  * **Deploy path.** ``README`` states that deployment does not happen from this
    repository — each appliance repository owns its cloud's Terraform and deploy
    workflows, and the AWS appliance's deploy stays fail-fast until its account
    prerequisites clear (its ``REVIEW.md`` R-001 – R-003). That documented status
    is accurate: no deploy path is executable from the core, by design, so it is
    recorded as documented-non-executable-by-design, not a defect.

Open doc tasks (Requirement 9.3). Of T-103, T-304, T-401 — checked against
``TODO.md`` current status:

  * **T-103** — *Not started* → OPEN. Recorded as a plan entry.
  * **T-304** — *Not started — not currently applicable* → OPEN. Recorded as a
    plan entry (a not-currently-applicable open task is still open work).
  * **T-401** — *Done* → CLOSED. Not recorded as an open-task entry; recorded
    instead as a verified-compliant ``INFORMATIONAL`` finding so the plan shows
    the task was checked and found closed.

Escalation (Requirement 9.4). Publishing the prepared Wiki pages depends on
GitHub Wiki write access, which is scoped out (``REVIEW.md`` R-009, "Open — not
blocking"). Recorded as an ``Escalation_Record`` carrying ``blocker_id="R-009"``
— the review never attempts the publication. These records are consumed by the
consolidation step (spec task 14.1) and, for the escalation, routed through the
scope gate (spec task 2.1 / 14.3).
"""

from __future__ import annotations

from cna.review.model import Finding, Severity

_AREA = "documentation"


def _accuracy_findings() -> list[Finding]:
    """Verified-compliant accuracy cross-checks (Requirement 9.1)."""
    return [
        Finding(
            area=_AREA,
            severity=Severity.INFORMATIONAL,
            proposed_action=(
                "Verified compliant: the documented platform version is "
                "consistent with the packaged version. pyproject.toml declares "
                "version 0.8.0b0 and the platform is described as v0.8.0b0; keep "
                "the two in step when the version bumps."
            ),
            dedup_key="documentation:version-accurate",
            subject="pyproject.toml / README.md",
        ),
        Finding(
            area=_AREA,
            severity=Severity.INFORMATIONAL,
            proposed_action=(
                "Verified compliant: README documents the `cna` CLI "
                "(pip install -e .[dev] -> cna --help) and pyproject.toml "
                "declares the matching entry point "
                '[project.scripts] cna = "cna.cli.main:cli". No inaccuracy.'
            ),
            dedup_key="documentation:cli-entry-point-accurate",
            subject="README.md / pyproject.toml::[project.scripts]",
        ),
        Finding(
            area=_AREA,
            severity=Severity.INFORMATIONAL,
            proposed_action=(
                "Verified compliant: README's documentation map (four required "
                "docs + one optional temporary working doc) matches the "
                "repository root, which carries exactly README.md, CHANGELOG.md, "
                "REVIEW.md, TODO.md and the optional CNA-0.90-updates.md. Retire "
                "CNA-0.90-updates.md when 0.9.0 ships, as the map states."
            ),
            dedup_key="documentation:four-document-model-accurate",
            subject="README.md::documentation-map",
        ),
        Finding(
            area=_AREA,
            severity=Severity.INFORMATIONAL,
            proposed_action=(
                "Verified compliant: the four core workflows exist under "
                ".github/workflows/ (200-build-images.yml, 300-test-codebase.yml, "
                "310-release-version.yml, 370-registry-cleanup.yml) and every "
                "workflow filename README references resolves; the deploy and "
                "operations workflows live in the appliance repositories (TODO.md "
                "T-504). Reference workflows by filename per the numbered-workflow "
                "convention."
            ),
            dedup_key="documentation:workflow-references-accurate",
            subject="README.md / .github/workflows",
        ),
        Finding(
            area=_AREA,
            severity=Severity.INFORMATIONAL,
            proposed_action=(
                "Verified compliant: TODO.md T-401 (retire/reconcile the "
                "superseded migrate/ Terraform root) is Done — the directory and "
                "its bootstrap script are deleted and the assessment-level IAM "
                "gate was verified — so it is not recorded as an open doc task."
            ),
            dedup_key="documentation:t-401-closed",
            subject="TODO.md::T-401",
        ),
    ]


def _executable_status_findings() -> list[Finding]:
    """Executable status of documented deploy/CLI paths (Requirement 9.2)."""
    return [
        Finding(
            area=_AREA,
            severity=Severity.LOW,
            proposed_action=(
                "Executable status: the documented Python CLI quick start "
                "(pip install -e .[dev] then cna --help) is not runnable from a "
                "bare checkout — importing cna.cli.main pulls runtime "
                "dependencies (e.g. pydantic) that only exist after the install "
                "step. Keep the install prerequisite explicit in README so the "
                "documented `cna --help` path is understood to run only after it."
            ),
            dedup_key="documentation:cli-path-requires-install",
            subject="README.md::python-cli-quick-start",
        ),
        Finding(
            area=_AREA,
            severity=Severity.LOW,
            proposed_action=(
                "Executable status: the deploy path is not executable from this "
                "repository — README's Deploying an environment section points "
                "at the appliance repositories, which own the Terraform and "
                "deploy workflows (TODO.md T-504); the AWS appliance's deploy "
                "stays fail-fast until its REVIEW.md R-001 - R-003 clear. "
                "Recorded as documented-non-executable-by-design; keep README "
                "pointing at the appliances for deployment."
            ),
            dedup_key="documentation:aws-deploy-path-not-executable",
            subject="README.md::deploying-an-environment",
        ),
    ]


def _open_doc_task_findings() -> list[Finding]:
    """One plan entry per still-open doc task among T-103, T-304 (Requirement 9.3)."""
    return [
        Finding(
            area=_AREA,
            severity=Severity.MEDIUM,
            proposed_action=(
                "Open doc task T-103 (Not started): confirm ADR-0001 through "
                "ADR-0005 exist as GitHub Wiki pages (the CHANGELOG references "
                "were corrected to name the Wiki but the target pages are "
                "unconfirmed), recreate any missing page from the CHANGELOG "
                "subjects, and link them from the Wiki home. Depends on Wiki read "
                "access."
            ),
            dedup_key="documentation:open-task:T-103",
            subject="TODO.md::T-103",
        ),
        Finding(
            area=_AREA,
            severity=Severity.LOW,
            proposed_action=(
                "Open doc task T-304 (Not started - not currently applicable): "
                "the Log Analytics workspace state-migration runbook is a no-op "
                "for the initial rollout but remains open for any environment "
                "already deployed with the old layout. Keep the runbook until it "
                "is either executed per-environment or the pre-old-layout "
                "environments are confirmed absent."
            ),
            dedup_key="documentation:open-task:T-304",
            subject="TODO.md::T-304",
        ),
    ]


def _wiki_escalation_finding() -> Finding:
    """R-009 Wiki-publication escalation (Requirement 9.4, escalation-only)."""
    return Finding(
        area=_AREA,
        severity=Severity.LOW,
        proposed_action=(
            "Escalation: publishing the prepared long-form Wiki pages depends on "
            "GitHub Wiki write access, which is scoped out (the wiki remote "
            "returns 401 to the automation). The review records the requirement "
            "and never attempts the publication; owner: REVIEW.md R-009 "
            "(Open - not blocking). Grant Wiki write access or publish the "
            "prepared pages manually (TODO.md T-601/T-602)."
        ),
        dedup_key="documentation:wiki-publication-r009",
        subject="GitHub Wiki (long-form documentation publication)",
        blocker_id="R-009",
    )


def _verify_findings() -> list[Finding]:
    """Verification of the documentation model (spec task 13.2, Requirement 9.1/9.2).

    Task 13.1 recorded the audit; this closes it by running the checks that
    prove the documented facts still resolve, rather than asserting them by
    inspection:

      * ``scripts/validate_documentation_model.py`` — the CI guard for the
        four-document model (README "Repository conventions"). Run against the
        tracked tree it exits 0: the four required root documents plus the one
        optional ``CNA-0.90-updates.md`` are present and nothing else is
        documentation. This is the executable form of the 9.1 four-document
        cross-check.
      * **Link / path resolution.** Every relative document link README's
        documentation map carries (``CHANGELOG.md``, ``REVIEW.md``, ``TODO.md``,
        ``CNA-0.90-updates.md``) resolves on the tree, as do the ``.env.example``
        inventory files README points at (repository root and
        ``apps/cna-web/``).
      * **Command / workflow-name resolution.** Every workflow filename README
        references by name (``200-build-images.yml``, ``300-test-codebase.yml``,
        ``310-release-version.yml``, ``370-registry-cleanup.yml``) exists under
        ``.github/workflows/``, and the
        documented ``cna`` CLI command resolves to a declared entry point
        (``pyproject.toml`` ``[project.scripts] cna = "cna.cli.main:cli"`` with
        the ``cna/cli/main.py`` module present). Running ``cna --help`` itself
        needs the documented ``pip install -e .[dev]`` step first (task 13.1
        recorded this executable-status caveat), so the command-name check is
        static: the entry point and its module resolve.

    All checks pass, so this is recorded verified-compliant. No documentation
    fix was required.
    """
    return [
        Finding(
            area=_AREA,
            severity=Severity.INFORMATIONAL,
            proposed_action=(
                "Verified compliant: scripts/validate_documentation_model.py "
                "exits 0 against the tracked tree — the four required root "
                "documents (README.md, CHANGELOG.md, REVIEW.md, TODO.md) plus "
                "the one optional CNA-0.90-updates.md are present and nothing "
                "outside the allow-list is documentation. Keep the guard in CI "
                "so documentation sprawl cannot return (TODO.md T-603)."
            ),
            dedup_key="documentation:model-validator-passes",
            subject="scripts/validate_documentation_model.py",
        ),
        Finding(
            area=_AREA,
            severity=Severity.INFORMATIONAL,
            proposed_action=(
                "Verified compliant: every relative link in README's "
                "documentation map resolves (CHANGELOG.md, REVIEW.md, TODO.md, "
                "CNA-0.90-updates.md) and the documented .env.example inventory "
                "files resolve (repository root and apps/cna-web/). No broken "
                "documentation link found."
            ),
            dedup_key="documentation:links-resolve",
            subject="README.md::documentation-map / .env.example",
        ),
        Finding(
            area=_AREA,
            severity=Severity.INFORMATIONAL,
            proposed_action=(
                "Verified compliant: every workflow filename README references "
                "by name (200-build-images.yml, 300-test-codebase.yml, "
                "310-release-version.yml, 370-registry-cleanup.yml) exists under "
                ".github/workflows/, and the "
                "documented `cna` command resolves to its declared entry point "
                '(pyproject.toml [project.scripts] cna = "cna.cli.main:cli", '
                "module cna/cli/main.py present). Running `cna --help` still "
                "requires the documented install step first (executable-status "
                "caveat recorded in the audit)."
            ),
            dedup_key="documentation:commands-and-workflows-resolve",
            subject="README.md / .github/workflows / pyproject.toml::[project.scripts]",
        ),
    ]


def documentation_verify_findings() -> list[Finding]:
    """Return the documentation-model verification findings (spec task 13.2).

    Complements :func:`documentation_findings` (the 13.1 audit) with the
    executed verification: the documentation-model validator result, the
    link/path-resolution checks, and the command/workflow-name resolution
    checks (Requirements 9.1, 9.2). All pass, so every finding is recorded
    verified-compliant.
    """
    return list(_verify_findings())


def documentation_findings() -> list[Finding]:
    """Return the Requirement 9 findings recorded for the documentation area.

    Covers the accuracy cross-checks (9.1), the executable-status entries for
    documented deploy/CLI paths (9.2), one plan entry per still-open doc task
    among T-103/T-304/T-401 (9.3, and T-401 is closed so recorded as
    verified-compliant instead), and the R-009 Wiki-publication escalation (9.4).
    """
    findings: list[Finding] = []
    findings.extend(_accuracy_findings())
    findings.extend(_executable_status_findings())
    findings.extend(_open_doc_task_findings())
    findings.append(_wiki_escalation_finding())
    return findings
