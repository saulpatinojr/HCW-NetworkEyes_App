"""Worker-retirement decision test for task 4.6 (Requirement 2.5), kept after the retirement was carried out.

Task 4.6 paired the FastAPI ``TestClient`` error-path tests (see
``test_network_assessment_api_error_paths.py``) with an assertion of the recorded
worker-retirement entry. This test lives in its own module — separate from the
``TestClient`` suite — because it only reads the review findings via
:func:`network_assessment.review.areas.python_engine_api_findings` and therefore has **no**
dependency on the API's runtime stack (fastapi / httpx / psycopg2). It runs in
every environment, including the minimal ``network_assessment``-only checkout where the
``TestClient`` suite is skipped.

Requirement 2.5: where the Worker_Service is confirmed a retirement candidate,
the review records a ``Remediation_Plan`` entry stating whether it is retired or
retained with a defined responsibility. The design records the decision as
**retire** — the ``apps/network-assessment-api`` ``POST /publish`` endpoint supersedes the
``apps/network-assessment-worker`` placeholder.

The owner approved the retirement on 2026-10-27 (``REVIEW.md`` R-016) and it is done: the directory, its
Dockerfile and its build job are removed. The invariant this module protects is therefore no longer "the review
says retire" alone, but the two facts that make retiring it safe and keep it retired:

* ``POST /publish`` exists in the API (the job the placeholder only sketched is done there), and
* the worker is not needed and does not come back: no directory, no Dockerfile, no build matrix leg, no tag
  and no digest in the publish workflow ``200-build-images.yml``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

from network_assessment.review import AREAS, Severity, consolidate
from network_assessment.review.areas import python_engine_api_findings

REPO_ROOT = Path(__file__).resolve().parents[2]
API_MAIN = REPO_ROOT / "apps" / "network-assessment-api" / "main.py"
BUILD_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "200-build-images.yml"
# Every Dockerfile that is tracked today (tests/unit/test_ci_hygiene.py pins the exact list).
DOCKERFILES = (
    REPO_ROOT / "Dockerfile",
    REPO_ROOT / "apps" / "network-assessment-api" / "Dockerfile",
    REPO_ROOT / "apps" / "network-assessment-web" / "Dockerfile",
)

_WORKER_DEDUP_KEY = "python-engine-api:worker-retirement"


def _worker_finding():
    return next(f for f in python_engine_api_findings() if f.dedup_key == _WORKER_DEDUP_KEY)


def test_worker_retirement_entry_exists_and_is_well_formed():
    """2.5: a worker-retirement entry is recorded in the python-engine-api area."""
    worker = _worker_finding()
    assert worker.area == "python-engine-api"
    assert worker.area in AREAS
    # The subject names the thing that was retired; the path itself no longer exists (see below).
    assert worker.subject == "apps/network-assessment-worker"
    assert worker.proposed_action.strip()


def test_worker_decision_is_retire_superseded_by_publish():
    """2.5: the decision is 'retire', superseded by /publish, not retained."""
    action = _worker_finding().proposed_action
    lowered = action.lower()
    assert "retire" in lowered
    # A retire decision must carry the removal, not a retention duty.
    assert "remove" in lowered
    assert "/publish" in action
    # The record says who decided and when, so it cannot drift into an unowned claim.
    assert "2026-10-27" in action and "R-016" in action
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
    assert "apps/network-assessment-worker" in entry.subjects


# --- the invariant behind the decision: /publish does the job, and the worker is not needed -------------------


def _mounted_publish_routers(source: str) -> set[str]:
    """The routers of ``source`` that declare ``@<router>.post("/publish")`` on a function ``publish`` AND that the
    module mounts with ``app.include_router(<router>)``.

    Read from the syntax tree, not by importing the module: the API's runtime stack (fastapi, psycopg2) is
    not needed, so this runs in every environment. A route on a router that is never included answers 404, so
    the decorator alone does not prove that ``POST /publish`` exists.
    """
    tree = ast.parse(source)
    declaring: set[str] = set()
    included: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == "publish":
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr == "post"
                    and isinstance(decorator.func.value, ast.Name)
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                    and decorator.args[0].value == "/publish"
                ):
                    declaring.add(decorator.func.value.id)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "include_router"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "app"
            and node.args
            and isinstance(node.args[0], ast.Name)
        ):
            included.add(node.args[0].id)
    return declaring & included


def test_post_publish_exists_in_the_api_and_its_router_is_mounted():
    """The job the worker placeholder only sketched is done by ``POST /publish`` in the API."""
    assert _mounted_publish_routers(API_MAIN.read_text(encoding="utf-8")) == {"internal"}


def test_the_mount_check_notices_a_router_that_is_never_included():
    declared = (
        'internal = APIRouter()\n\n@internal.post("/publish")\ndef publish(request):\n    ...\n'
    )
    assert _mounted_publish_routers(declared) == set()
    assert _mounted_publish_routers(declared + "app.include_router(internal)\n") == {"internal"}
    # another router being included is not enough, and neither is a route of another name or path
    assert _mounted_publish_routers(declared + "app.include_router(other)\n") == set()
    assert (
        _mounted_publish_routers(
            declared.replace("/publish", "/other") + "app.include_router(internal)\n"
        )
        == set()
    )


def test_the_worker_directory_is_gone():
    assert not (REPO_ROOT / "apps" / "network-assessment-worker").exists()


def test_no_dockerfile_builds_or_copies_the_worker():
    for dockerfile in DOCKERFILES:
        text = dockerfile.read_text(encoding="utf-8")
        assert "network-assessment-worker" not in text, dockerfile.name


def test_the_publish_workflow_builds_and_tags_no_worker_image():
    """200-build-images.yml publishes four images: cli, api, web and migrator, and nothing for the worker."""
    doc = yaml.safe_load(BUILD_WORKFLOW.read_text(encoding="utf-8"))
    jobs = doc["jobs"]

    # The matrix of the CLI/API job has no worker leg and builds no Dockerfile under the worker's directory.
    matrix = jobs["build-images"]["strategy"]["matrix"]["include"]
    assert {row["key"] for row in matrix} == {"cli", "api"}
    assert not [row for row in matrix if "worker" in row["file"] or "worker" in row["sha_prefix"]]

    # No job hands a worker digest or tag list on.
    for name in ("build-images", "build-web"):
        assert not [key for key in jobs[name]["outputs"] if "worker" in key], name
    tag_step = next(
        step
        for step in jobs["tag-images"]["steps"]
        if "Verify, tag and record" in step.get("name", "")
    )
    assert not [key for key in tag_step["env"] if "WORKER" in key]
    assert 'COMPONENTS="cli api web migrator"' in tag_step["run"]
    assert "worker" not in tag_step["run"]

    # Nothing in the path filter names the worker's directory.
    on = doc.get("on", doc.get(True))
    assert not [path for path in on["push"]["paths"] if "worker" in path]
