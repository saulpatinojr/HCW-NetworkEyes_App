"""Unit tests for the consolidated ``Remediation_Plan`` builder (spec task 14.1).

Covers :func:`cna.review.build_remediation_plan`, the CONSOLIDATE-stage entry
point that gathers every owner area's ``Finding`` records, routes each through
the ``REVIEW.md`` scope gate, and folds them into one severity-ordered
``Remediation_Plan``.

The concrete coverage assertions here (Requirements 1.1, 1.4, 1.5, 4.1, 5.1,
7.1) check that the single plan represents every subject in each area's fixed
expected set:

  * all nine owner areas are represented across the plan's ``referenced_areas``;
  * the eight AWS module boundaries (ai, compute, database, identity,
    observability, runtime, security, storage) appear as subjects;
  * all 14 CI workflows appear as subjects;
  * the four service Dockerfiles and ``docker-compose.yml`` appear as subjects.

Property 2 (the universal area-coverage invariant) is spec task 14.2's dedicated
property test; this module asserts the concrete coverage of the real plan.
"""

from __future__ import annotations

from cna.review import (
    AREAS,
    RemediationPlan,
    Severity,
    build_remediation_plan,
    collect_findings,
)
from cna.review.areas.cicd import (
    GITHUB_HOSTED_WORKFLOWS,
    SELF_HOSTED_ONLY_WORKFLOWS,
)

# The full set of numbered workflows under .github/workflows/.
_ALL_WORKFLOWS = SELF_HOSTED_ONLY_WORKFLOWS + GITHUB_HOSTED_WORKFLOWS

# The four service Dockerfiles plus the compose file (Requirement 7.1).
_SERVICE_DOCKERFILES = (
    "Dockerfile",
    "apps/cna-api/Dockerfile",
    "apps/cna-web/Dockerfile",
    "apps/cna-worker/Dockerfile",
)
_COMPOSE_FILE = "docker-compose.yml"

# The escalation blockers this review consumes in the core (design "Blocker model"
# table): R-005 observability, R-009 documentation. The AWS/Azure Terraform
# consumers left with the deployment layer (TODO.md T-504).
_EXPECTED_ESCALATION_BLOCKERS = frozenset({"R-005", "R-009"})


def _all_subject_tokens(plan: RemediationPlan) -> set[str]:
    """Every subject token across the plan, split on commas.

    Some findings record several subjects in one comma-joined ``subject`` string
    (e.g. the multi-Dockerfile HEALTHCHECK entry); splitting on commas exposes
    each individual subject path for the coverage assertions.
    """
    tokens: set[str] = set()
    for entry in plan.entries:
        for subject in entry.subjects:
            for token in subject.split(","):
                tokens.add(token.strip())
    return tokens


def test_build_remediation_plan_returns_ordered_nonempty_plan():
    """The builder returns a non-empty, severity-descending plan."""
    plan = build_remediation_plan()
    assert isinstance(plan, RemediationPlan)
    assert plan.entries, "the consolidated plan must have entries"
    severities = [entry.severity for entry in plan.entries]
    assert severities == sorted(severities, reverse=True)


def test_plan_entries_are_well_formed():
    """Every entry is severity-typed, has an action, and areas within AREAS."""
    plan = build_remediation_plan()
    for entry in plan.entries:
        assert isinstance(entry.severity, Severity)
        assert entry.proposed_action.strip()
        assert entry.referenced_areas <= AREAS
        # Escalations carry a blocker id; fixable entries never do.
        if entry.is_escalation:
            assert entry.blocker_id
        else:
            assert entry.blocker_id is None


def test_coverage_all_nine_owner_areas_represented():
    """Requirement 1.1: all nine owner areas appear across the plan."""
    plan = build_remediation_plan()
    represented: set[str] = set()
    for entry in plan.entries:
        represented |= entry.referenced_areas
    assert represented == AREAS, f"missing areas: {sorted(AREAS - represented)}"


def test_coverage_terraform_areas_point_at_the_appliances():
    """Requirement 4.1: the Terraform areas are represented by their relocation records."""
    tokens = _all_subject_tokens(build_remediation_plan())
    assert any(
        token.startswith("saulpatinojr/Work-Cloud_Network_AWS_Appliance:") for token in tokens
    )
    assert any(
        token.startswith("saulpatinojr/Work-Cloud_Network_Azure_Appliance:") for token in tokens
    )


def test_coverage_all_core_ci_workflows_present():
    """Requirement 5.1: every core CI workflow appears as a subject."""
    assert len(_ALL_WORKFLOWS) == 4
    tokens = _all_subject_tokens(build_remediation_plan())
    for workflow in _ALL_WORKFLOWS:
        expected = f".github/workflows/{workflow}"
        assert expected in tokens, f"CI workflow not covered: {workflow}"


def test_coverage_service_dockerfiles_and_compose_present():
    """Requirement 7.1: four service Dockerfiles + docker-compose.yml as subjects."""
    tokens = _all_subject_tokens(build_remediation_plan())
    for dockerfile in _SERVICE_DOCKERFILES:
        assert dockerfile in tokens, f"Dockerfile not covered: {dockerfile}"
    assert _COMPOSE_FILE in tokens, "docker-compose.yml not covered"


def test_escalations_carry_expected_blocker_ids():
    """Escalation entries reference the R-005 and R-009 consumers that remain in the core."""
    plan = build_remediation_plan()
    escalation_blockers = {entry.blocker_id for entry in plan.entries if entry.is_escalation}
    assert escalation_blockers == _EXPECTED_ESCALATION_BLOCKERS, (
        f"escalation blockers were {sorted(escalation_blockers)}"
    )
    # No fixable entry carries a blocker id.
    for entry in plan.entries:
        if not entry.is_escalation:
            assert entry.blocker_id is None


def test_deduplication_is_a_union():
    """Requirement 1.5: entries sharing a dedup key merge into one.

    Every dedup key across all gathered findings appears exactly once in the
    consolidated plan, and each merged entry's referenced_areas is the union of
    its contributing findings' areas.
    """
    findings = collect_findings()
    plan = build_remediation_plan()

    plan_keys = [entry.dedup_key for entry in plan.entries]
    assert len(plan_keys) == len(set(plan_keys)), "a dedup key appears twice"
    assert set(plan_keys) == {f.dedup_key for f in findings}

    # Spot-check the union semantics on any dedup key with multiple areas.
    areas_by_key: dict[str, set[str]] = {}
    for finding in findings:
        areas_by_key.setdefault(finding.dedup_key, set()).add(finding.area)
    for entry in plan.entries:
        assert entry.referenced_areas == areas_by_key[entry.dedup_key]


def test_consolidation_is_idempotent():
    """Requirement 1.5: consolidating the plan again yields the same plan."""
    from cna.review import consolidate

    plan = build_remediation_plan()
    again = consolidate(plan.entries)
    assert [e.dedup_key for e in again.entries] == [e.dedup_key for e in plan.entries]
    for a, b in zip(again.entries, plan.entries, strict=True):
        assert a.severity == b.severity
        assert a.referenced_areas == b.referenced_areas
        assert a.is_escalation == b.is_escalation
        assert a.blocker_id == b.blocker_id
