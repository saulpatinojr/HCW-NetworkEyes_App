"""Findings for the ``python-engine-api`` area (Requirement 2 correctness).

This is a *verify-then-close-gaps* record for the ``cna/`` core, the
``apps/cna-api`` FastAPI service, and the ``apps/cna-worker`` decision. The
audit against Requirement 2 confirmed:

  * **2.1 — `/intake` honesty (verified compliant).** ``apps/cna-api/main.py``
    returns an honest ``501`` (``Outcome.NOT_IMPLEMENTED``) for ``/intake``
    rather than a fabricated ``200``. Recorded as an ``INFORMATIONAL`` finding
    so the plan captures the verified-compliant outcome and guards against a
    regression to a fake success.
  * **2.2 / 2.4 — outcome→status mapping (gap closed here).** Before this task,
    every handler hard-coded its HTTP status literals, so the
    "success→2xx / failure→matching-4xx-or-5xx" contract lived only in review
    convention. A single mapping (:mod:`cna.api_status`) now owns status
    selection and every handler routes through it, so no handler can return a
    ``200`` on an error path. Recorded as a ``LOW`` residual gap that this task
    remediates.

  * **2.5 — worker retirement decision (retire).** The ``apps/cna-worker``
    placeholder was a run-once script that stubbed the publish job against a
    hardcoded ``sample-engagement``. The ``apps/cna-api`` ``POST /publish``
    endpoint now does that job for real (real deliverables -> private
    per-engagement blob container -> portal generation -> TTL-capped SAS URL)
    and its docstring states it supersedes the placeholder. The decision is
    therefore **retire** (not retained with a responsibility). The worker is
    still wired into the Azure and AWS Terraform ``compute`` modules, the
    ``apps/cna-worker/Dockerfile`` container audit, and the README, so the
    removal is a coordinated change carried as the plan action rather than
    performed here. Recorded as a ``LOW`` finding.

These records are consumed by the consolidation step (spec task 14.1).
"""

from __future__ import annotations

from cna.review.model import Finding, Severity

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
                "status wired through cna.api_status so it cannot regress to a "
                "fake success."
            ),
            dedup_key="python-engine-api:intake-honest-501",
            subject="apps/cna-api/main.py::intake",
        ),
        Finding(
            area=_AREA,
            severity=Severity.LOW,
            proposed_action=(
                "Introduce a single outcome→status mapping (cna.api_status) so "
                "success maps to 2xx and every failure to the matching 4xx/5xx; "
                "route all API handlers through it so no handler returns 200 on "
                "an error path."
            ),
            dedup_key="python-engine-api:single-outcome-status-mapping",
            subject="apps/cna-api",
        ),
        Finding(
            area=_AREA,
            severity=Severity.LOW,
            proposed_action=(
                "Retire apps/cna-worker: the run-once placeholder (hardcoded "
                "sample-engagement) is superseded by the apps/cna-api POST "
                "/publish endpoint, which performs the real publish job. Remove "
                "the worker service and its Dockerfile, and drop the worker "
                "container from the Azure and AWS Terraform compute modules "
                "(and the README service list) as a coordinated change; the "
                "worker is not retained with any responsibility."
            ),
            dedup_key="python-engine-api:worker-retirement",
            subject="apps/cna-worker",
        ),
    ]
