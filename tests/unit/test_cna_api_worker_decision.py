"""Worker-retirement decision test for task 4.6 (Requirement 2.5).

Task 4.6 pairs the FastAPI ``TestClient`` error-path tests (see
``test_cna_api_error_paths.py``) with an assertion of the recorded
worker-retirement entry. This test lives in its own module — separate from the
``TestClient`` suite — because it only reads the review findings via
:func:`cna.review.areas.python_engine_api_findings` and therefore has **no**
dependency on the API's runtime stack (fastapi / httpx / psycopg2). It runs in
every environment, including the minimal ``cna``-only checkout where the
``TestClient`` suite is skipped.

Requirement 2.5: where the Worker_Service is confirmed a retirement candidate,
the review records a ``Remediation_Plan`` entry stating whether it is retired or
retained with a defined responsibility. The design records the decision as
**retire** — the ``apps/cna-api`` ``POST /publish`` endpoint supersedes the
``apps/cna-worker`` placeholder.
"""

from __future__ import annotations

from cna.review import AREAS, Severity, consolidate
from cna.review.areas import python_engine_api_findings

_WORKER_DEDUP_KEY = "python-engine-api:worker-retirement"


def _worker_finding():
    return next(f for f in python_engine_api_findings() if f.dedup_key == _WORKER_DEDUP_KEY)


def test_worker_retirement_entry_exists_and_is_well_formed():
    """2.5: a worker-retirement entry is recorded in the python-engine-api area."""
    worker = _worker_finding()
    assert worker.area == "python-engine-api"
    assert worker.area in AREAS
    assert worker.subject == "apps/cna-worker"
    assert worker.proposed_action.strip()


def test_worker_decision_is_retire_superseded_by_publish():
    """2.5: the decision is 'retire', superseded by /publish, not retained."""
    action = _worker_finding().proposed_action
    lowered = action.lower()
    assert "retire" in lowered
    # A retire decision must carry the removal action, not a retention duty.
    assert "remove" in lowered
    assert "/publish" in action
    # Guard against a "retained with a responsibility" wording sneaking in.
    assert "retained" not in lowered or "not retained" in lowered


def test_worker_entry_is_fixable_not_an_escalation():
    """2.5: the worker retirement is engineering-fixable — no blocker id."""
    worker = _worker_finding()
    assert worker.blocker_id is None


def test_worker_entry_consolidates_as_a_fixable_plan_entry():
    """2.5: the entry flows into the plan as a fixable (non-escalation) entry."""
    plan = consolidate([_worker_finding()])
    assert len(plan.entries) == 1
    entry = plan.entries[0]
    assert entry.dedup_key == _WORKER_DEDUP_KEY
    assert entry.is_escalation is False
    assert entry.blocker_id is None
    assert entry.severity is Severity.LOW
    assert "python-engine-api" in entry.referenced_areas
    assert "apps/cna-worker" in entry.subjects
