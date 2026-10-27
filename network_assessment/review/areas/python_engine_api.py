"""Findings for the ``python-engine-api`` area (Requirement 2 correctness).

This is a *verify-then-close-gaps* record for the ``network_assessment/`` core, the
``apps/network-assessment-api`` FastAPI service, and the ``apps/network-assessment-worker`` retirement. The
audit against Requirement 2 confirmed:

  * **2.1 — `/intake` honesty (verified compliant).** ``apps/network-assessment-api/main.py``
    returns an honest ``501`` (``Outcome.NOT_IMPLEMENTED``) for ``/intake``
    rather than a fabricated ``200``. Recorded as an ``INFORMATIONAL`` finding
    so the plan captures the verified-compliant outcome and guards against a
    regression to a fake success.
  * **2.2 / 2.4 — outcome→status mapping (gap closed here).** Before this task,
    every handler hard-coded its HTTP status literals, so the
    "success→2xx / failure→matching-4xx-or-5xx" contract lived only in review
    convention. A single mapping (:mod:`network_assessment.api_status`) now owns status
    selection and every handler routes through it, so no handler can return a
    ``200`` on an error path. Recorded as a ``LOW`` residual gap that this task
    remediates.

  * **2.5 — worker retirement decision (retire; carried out 2026-10-27).** The ``apps/network-assessment-worker``
    placeholder was a run-once script that stubbed the publish job against a
    hardcoded ``sample-engagement``. The ``apps/network-assessment-api`` ``POST /publish``
    endpoint now does that job for real (real deliverables -> private
    per-engagement blob container -> portal generation -> TTL-capped SAS URL)
    and its docstring states it supersedes the placeholder. The decision is
    therefore **retire** (not retained with a responsibility). The owner
    approved it on 2026-10-27 (``REVIEW.md`` R-016) and it is done in this
    repository: the directory, its Dockerfile, its build job and its image are removed.
    What remains is outside this repository: whoever deploys the images drops the
    worker service (the container the Azure and AWS ``compute`` modules ran). Recorded
    as a ``LOW`` finding that stays until that step is taken.

These records are consumed by the consolidation step (spec task 14.1).
"""

from __future__ import annotations

from network_assessment.review.model import Finding, Severity

_AREA = "python-engine-api"


def python_engine_api_findings() -> list[Finding]:
    """Return the Requirement 2 findings recorded for this area."""
    return [
        Finding(
            area=_AREA,
            severity=Severity.INFORMATIONAL,
            proposed_action=(
                "Verified compliant: /intake returns an honest 501 "
                "(Outcome.NOT_IMPLEMENTED), not a fabricated 200. Keep the "
                "status wired through network_assessment.api_status so it cannot regress to a "
                "fake success."
            ),
            dedup_key="python-engine-api:intake-honest-501",
            subject="apps/network-assessment-api/main.py::intake",
        ),
        Finding(
            area=_AREA,
            severity=Severity.LOW,
            proposed_action=(
                "Introduce a single outcome→status mapping (network_assessment.api_status) so "
                "success maps to 2xx and every failure to the matching 4xx/5xx; "
                "route all API handlers through it so no handler returns 200 on "
                "an error path."
            ),
            dedup_key="python-engine-api:single-outcome-status-mapping",
            subject="apps/network-assessment-api",
        ),
        Finding(
            area=_AREA,
            severity=Severity.LOW,
            proposed_action=(
                "Retired (owner decision 2026-10-27, REVIEW.md R-016): the run-once "
                "placeholder apps/network-assessment-worker (hardcoded sample-engagement) "
                "is superseded by the apps/network-assessment-api POST /publish endpoint, "
                "which performs the real publish job. Its directory, Dockerfile, build job "
                "and image are removed from this repository. Remaining step, outside it: "
                "whoever deploys the images removes the worker service (the container in "
                "the Azure and AWS compute modules); the worker is not retained with any "
                "responsibility."
            ),
            dedup_key="python-engine-api:worker-retirement",
            subject="apps/network-assessment-worker",
        ),
    ]
