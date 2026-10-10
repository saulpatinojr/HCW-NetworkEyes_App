"""Verification results for the ``python-engine-api`` area (spec task 4.7).

Where :mod:`cna.review.areas.python_engine_api` records the audit's
verify-then-close-gaps findings (the ``/intake`` honest-501 (2.1), the single
outcome->status mapping (2.2/2.4), and the worker retirement decision (2.5)),
this module records the *verification suite* result for the area — the design's
"Verification" line for section 2: ``ruff check cna apps``, ``ty check cna``,
and ``pytest`` under the 80% coverage gate. Failures are recorded as
``Finding`` records rather than swallowed (design "Error Handling": a failing
verification command is itself a finding; a missing tool is a coverage gap).

The suite was run in a clean virtualenv with ``pip install -e .[dev,enrichment]``
plus the API runtime deps (``fastapi``/``starlette``/``httpx``/``psycopg2``) so
the FastAPI ``TestClient`` error-path tests execute rather than skip. What the
tools reported, and what this module records:

  * **ruff (verified compliant).** ``ruff check cna apps`` -> ``All checks
    passed!``. ``ruff format --check`` (the CI/pre-commit gate,
    ``300-test-codebase.yml`` + ``.pre-commit-config.yaml``) initially flagged
    ten files this feature's work introduced (``cna/api_status.py``,
    ``apps/cna-api/main.py``, ``cna/review/model.py``, and seven
    ``cna/review/areas/*`` modules). ``ruff format`` was run over those files to
    fix the genuine formatting-gate failure this feature introduced (no lint
    rule was silenced and no gate weakened); both ``ruff check`` and ``ruff
    format --check`` are clean afterward. Recorded ``INFORMATIONAL``.

  * **ty (residual gap, fixable).** ``ty check cna`` reports two
    ``unresolved-attribute`` diagnostics, both in
    ``cna/ai_engine/foundry_agent_client.py`` (``AIProjectClient.agents``), which
    is the exact azure-ai-projects 1.x surface documented in ``pyproject.toml``
    (T-413) and tracked as not-yet-green in ``TODO.md`` (T-410). **No ty
    diagnostic touches this area's files** (``cna/api_status.py``,
    ``cna/api_errors.py``, ``cna/review/*``) — the Python-area work introduced no
    type error. (Run against the base interpreter ty instead reports ~84
    ``unresolved-import`` diagnostics for third-party libraries; those are a ty
    environment-resolution artifact, not code defects, and clear when ty is
    pointed at the environment that has the dependencies installed.) Recorded
    ``LOW`` and owned by this area's tracked ``ty`` gap (T-410), not an
    escalation.

  * **pytest (verified compliant + one cross-area failure).** ``pytest
    tests/unit/`` under ``--cov=cna --cov-fail-under=80`` **passed the coverage
    gate at 88.08%** (well above ``fail_under = 80``); every ``python-engine-api``
    test passed, including the FastAPI ``TestClient`` error-path/sanitization and
    worker-decision tests (4.6). Three collected tests skip for environment
    reasons unrelated to this area (``weasyprint`` native lib, the draw.io CLI).
    Two tests failed — both in ``tests/unit/test_logging_config_properties.py``
    (observability area, Property 16 / task 12.2), not in this area: Hypothesis
    generates an ``extra`` dict whose key collides with a reserved ``LogRecord``
    attribute (``levelname`` overwrites the rendered level to ``null``;
    ``processName`` makes ``logger.makeRecord`` raise ``KeyError``). These are
    generator bugs in the observability property test, independent of the
    Python-area changes, and are recorded here so the failure reaches the plan
    (owned by the ``observability`` area's dedup key). The coverage-gate pass and
    the all-green area tests are recorded ``INFORMATIONAL``.

These records feed the consolidation step (spec task 14.1).
"""

from __future__ import annotations

from cna.review.model import Finding, Severity

_AREA = "python-engine-api"

# The measured coverage of the ``cna`` package under the suite, recorded so the
# verified-compliant finding names the real number against the gate.
COVERAGE_PERCENT = 88.08
COVERAGE_GATE = 80


def python_engine_api_verify_findings() -> list[Finding]:
    """Return the verification-suite findings for the ``python-engine-api`` area.

    Records the result of running the design's section-2 verification suite —
    ``ruff check cna apps`` / ``ruff format --check``, ``ty check cna``, and
    ``pytest`` under the 80% coverage gate. Clean/passing outcomes are recorded
    ``INFORMATIONAL`` (verified compliant); the residual ``ty`` gap is a fixable
    ``LOW`` finding; the two observability Property-16 test failures surfaced by
    the suite are recorded as a ``MEDIUM`` finding under the observability area's
    dedup key so they reach the consolidated plan.

    :returns: the ruff, ty, pytest-coverage, area-tests, and cross-area
        test-failure findings. None is an escalation — every gap here is
        engineering-fixable and carries no ``blocker_id``.
    """
    return [
        Finding(
            area=_AREA,
            severity=Severity.INFORMATIONAL,
            proposed_action=(
                "Verified compliant (ruff): 'ruff check cna apps' passes with no "
                "findings. 'ruff format --check' (the CI/pre-commit gate) flagged "
                "ten feature-introduced files (cna/api_status.py, "
                "apps/cna-api/main.py, cna/review/model.py, and seven "
                "cna/review/areas/* modules); 'ruff format' was run over them to "
                "fix the formatting-gate failure this feature introduced — no lint "
                "rule silenced, no gate weakened. Both 'ruff check' and 'ruff "
                "format --check' are clean afterward. Keep them clean in CI "
                "(300-test-codebase.yml) and pre-commit."
            ),
            dedup_key="python-engine-api:verify-ruff-clean",
            subject="cna, apps",
        ),
        Finding(
            area=_AREA,
            severity=Severity.LOW,
            proposed_action=(
                "'ty check cna' reports two unresolved-attribute diagnostics, "
                "both in cna/ai_engine/foundry_agent_client.py "
                "(AIProjectClient.agents) — the azure-ai-projects 1.x surface "
                "documented in pyproject.toml (T-413) and tracked not-yet-green in "
                "TODO.md (T-410). No ty diagnostic touches this area's files "
                "(cna/api_status.py, cna/api_errors.py, cna/review/*); the "
                "Python-area work introduced no type error. Resolve the two "
                "foundry_agent_client findings (T-410) rather than widening any "
                "ignore list, so 'ty check cna' becomes green."
            ),
            dedup_key="python-engine-api:verify-ty-foundry-agents-gap",
            subject="cna/ai_engine/foundry_agent_client.py",
        ),
        Finding(
            area=_AREA,
            severity=Severity.INFORMATIONAL,
            proposed_action=(
                "Verified compliant (pytest coverage gate): 'pytest tests/unit/ "
                f"--cov=cna --cov-fail-under={COVERAGE_GATE}' passed the gate at "
                f"{COVERAGE_PERCENT:.2f}% total coverage (pyproject fail_under = "
                f"{COVERAGE_GATE}). Every python-engine-api test passed, including "
                "the FastAPI TestClient error-path/sanitization and worker-decision "
                "tests (task 4.6). Three tests skip for environment reasons "
                "unrelated to this area (weasyprint native lib and the draw.io CLI, "
                "both present inside the container images). Keep the gate at 80 and "
                "do not weaken it to absorb future gaps."
            ),
            dedup_key="python-engine-api:verify-pytest-coverage-gate",
            subject="cna",
        ),
        Finding(
            area="observability",
            severity=Severity.MEDIUM,
            proposed_action=(
                "Two Property-16 structured-log tests fail in "
                "tests/unit/test_logging_config_properties.py (observability area, "
                "task 12.2): the Hypothesis 'extra' generator can produce a key "
                "that collides with a reserved logging.LogRecord attribute — "
                "'levelname' overwrites the rendered level to null "
                "(test_property16_records_parse_as_structured_logs), and "
                "'processName' makes logger.makeRecord raise KeyError "
                "(test_property16_error_events_carry_level_and_message). Fix the "
                "generator to also exclude the reserved LogRecord attribute names "
                "(levelname, name, msg, args, exc_info, funcName, module, "
                "processName, threadName, ...), not only message/level/logger/"
                "timestamp. Surfaced by the python-engine-api verification suite; "
                "owned by the observability area."
            ),
            dedup_key="observability:property16-reserved-logrecord-key-collision",
            subject="tests/unit/test_logging_config_properties.py",
        ),
    ]
