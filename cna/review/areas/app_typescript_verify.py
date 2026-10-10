"""Verification of the ``app-typescript`` area (spec task 5.3, Requirements 1.1/1.2).

Task 5.1 recorded the app-area type-safety / error-handling audit (F-APP-001 –
F-APP-003, ``CHANGELOG.md`` → Unreleased → Fixed) and task 5.2 recorded the AWS-view alignment
entries (in :mod:`cna.review.areas.app_typescript`). This module closes the area
by running the executed verification the design's "1. App / TypeScript"
*Verification* line calls for — ``npm run lint``, ``npm run build`` (type-check +
production build), and ``tsc --noEmit`` where a standalone type-check is faster —
and recording the result as structured :class:`~cna.review.model.Finding`
records the task-14 consolidation engine can ingest.

What was run
------------

In ``apps/cna-web`` (Node v26, npm v11):

  * ``npm ci`` — installed 581 packages cleanly (exit 0). Install scripts are not
    run by default under this npm's ``allow-scripts`` policy, so the Prisma
    client was generated explicitly with ``npx prisma generate`` (exit 0) before
    the type-check/build, which need the generated ``@prisma/client`` types.
  * ``npx tsc --noEmit`` — **clean (exit 0)**. This is the fast standalone
    type-check the design allows and it directly exercises the task-5.1/5.2
    TypeScript edits (``lib/summarize-error.ts`` ``sanitizeBackendDetail`` /
    generalized ``summarizeErrorText``, the ``lib/auth.ts`` unknown-narrowed
    error ``type`` accessor, and the ``sanitizeBackendDetail`` call sites in the
    chat route and the ``client-deliverables`` / ``cloud-credentials`` actions).
    None introduced a type error.
  * ``npm run build`` (``next build``) — **succeeds (exit 0)**: "Compiled
    successfully", the in-build "Running TypeScript" step passes, and all routes
    are generated. This confirms the same edits build end-to-end under the
    production compiler, not only the standalone type-checker. The build also
    emitted a non-fatal deprecation notice: the ``middleware`` file convention is
    deprecated in Next 16 in favour of ``proxy`` (recorded below as a LOW
    residual gap, not a blocker).

Residual gap found
------------------

  * ``npm run lint`` — **fails (exit 1)**. The ``lint`` script is
    ``next lint``, which Next.js 16 removed; it errors with "Invalid project
    directory provided, no such directory: .../lint". Running ESLint 10 directly
    also fails because there is no flat-config file: "ESLint couldn't find an
    eslint.config.(js|mjs|cjs) file" (ESLint v9+ requires flat config; the
    project has neither ``eslint.config.*`` nor a legacy ``.eslintrc.*``). So the
    web area currently has **no runnable lint step** — a genuine
    verification-coverage gap, recorded as a MEDIUM fixable finding rather than a
    silent pass. ``eslint`` and ``eslint-config-next`` are already installed, so
    the fix is to add an ``eslint.config.mjs`` flat config (e.g. via
    ``@eslint/eslintrc``'s ``FlatCompat`` around ``next/core-web-vitals``) and
    repoint the ``lint`` script at ``eslint .``.

The type-check and build outcomes are recorded as ``INFORMATIONAL``
verified-compliant findings (they passed and confirm the 5.1/5.2 edits are
sound); the broken lint step and the ``middleware`` deprecation are recorded as
fixable residual gaps. Every finding here is a **fixable app-area finding** with
no ``blocker_id`` — running lint/build and migrating the middleware convention
need no AWS account or gated resource. These records are consumed by the
consolidation step (spec task 14.1).
"""

from __future__ import annotations

from cna.review.model import Finding, Severity

_AREA = "app-typescript"


def _passing_check_findings() -> list[Finding]:
    """Verified-compliant type-check + build results (Requirements 1.1, 1.2)."""
    return [
        Finding(
            area=_AREA,
            severity=Severity.INFORMATIONAL,
            proposed_action=(
                "Verified compliant (Requirements 1.1/1.2): in apps/cna-web "
                "'npm ci' installed cleanly and 'npx tsc --noEmit' passed with no "
                "errors (exit 0) after generating the Prisma client with "
                "'npx prisma generate'. The standalone type-check exercises the "
                "task-5.1/5.2 edits (lib/summarize-error.ts sanitizeBackendDetail "
                "/ summarizeErrorText, lib/auth.ts unknown-narrowed error type "
                "accessor, and the sanitizeBackendDetail call sites in the chat "
                "route and the client-deliverables / cloud-credentials actions); "
                "none introduced a type error. Keep the type-check green."
            ),
            dedup_key="app-typescript:tsc-noemit-clean",
            subject="apps/cna-web (npx tsc --noEmit)",
        ),
        Finding(
            area=_AREA,
            severity=Severity.INFORMATIONAL,
            proposed_action=(
                "Verified compliant (Requirements 1.1/1.2): 'npm run build' "
                "(next build) succeeds in apps/cna-web (exit 0) — 'Compiled "
                "successfully', the in-build TypeScript step passes, and all "
                "routes generate. This confirms the task-5.1/5.2 TypeScript edits "
                "build end-to-end under the production compiler, not only the "
                "standalone type-checker. No build fix required."
            ),
            dedup_key="app-typescript:next-build-succeeds",
            subject="apps/cna-web (npm run build / next build)",
        ),
    ]


def _lint_gap_finding() -> Finding:
    """The web area has no runnable lint step — residual gap (Requirement 1.1)."""
    return Finding(
        area=_AREA,
        severity=Severity.MEDIUM,
        proposed_action=(
            "Restore a runnable lint step for apps/cna-web. 'npm run lint' fails "
            "(exit 1) because the script is 'next lint', which Next.js 16 removed "
            "('Invalid project directory provided, no such directory: .../lint'), "
            "and running ESLint 10 directly fails because there is no flat-config "
            "file ('ESLint couldn't find an eslint.config.(js|mjs|cjs) file'; "
            "ESLint v9+ requires flat config and the project has neither "
            "eslint.config.* nor a legacy .eslintrc.*). eslint and "
            "eslint-config-next are already installed, so add an "
            "eslint.config.mjs flat config (e.g. FlatCompat around "
            "next/core-web-vitals via @eslint/eslintrc) and repoint the 'lint' "
            "script at 'eslint .' so lint runs in CI again. Fixable app-area "
            "entry; no AWS account required."
        ),
        dedup_key="app-typescript:lint-step-not-runnable",
        subject="apps/cna-web/package.json::scripts.lint (next lint removed; no eslint.config.*)",
    )


def _middleware_deprecation_finding() -> Finding:
    """next build flags the deprecated middleware convention (Requirement 1.1)."""
    return Finding(
        area=_AREA,
        severity=Severity.LOW,
        proposed_action=(
            "Migrate the deprecated Next 16 'middleware' file convention to "
            "'proxy'. 'next build' emits a non-fatal deprecation notice: 'The "
            '"middleware" file convention is deprecated. Please use "proxy" '
            "instead.' The build still succeeds, so this is a LOW residual gap. "
            "Run 'npx @next/codemod@canary middleware-to-proxy .' (or rename "
            "middleware.ts to proxy.ts per the Next 16 migration) to clear the "
            "warning before the convention is removed in a future major. Fixable "
            "app-area entry; no AWS account required."
        ),
        dedup_key="app-typescript:middleware-convention-deprecated",
        subject="apps/cna-web/middleware.ts",
    )


def app_typescript_verify_findings() -> list[Finding]:
    """Return the ``app-typescript`` area verification findings (spec task 5.3).

    Complements the task-5.1 audit (F-APP-001 – F-APP-003 in ``CHANGELOG.md``) and the
    task-5.2 AWS-view alignment entries (:func:`~cna.review.areas.app_typescript.
    app_typescript_findings`) with the executed verification the design requires:
    ``tsc --noEmit`` and ``npm run build`` both pass (recorded verified-compliant,
    confirming the 5.1/5.2 edits are type-correct), while ``npm run lint`` cannot
    run under Next 16 / ESLint 10 (recorded as a MEDIUM fixable gap) and the build
    flags the deprecated ``middleware`` convention (recorded as a LOW fixable
    gap). Every entry is a fixable app-area finding with no ``blocker_id``; the
    records are consumed by the consolidation step (spec task 14.1).
    """
    findings = _passing_check_findings()
    findings.append(_lint_gap_finding())
    findings.append(_middleware_deprecation_finding())
    return findings
