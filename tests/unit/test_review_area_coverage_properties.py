"""Property-based tests for the production-readiness consolidation coverage.

Feature: production-readiness
Property 2: Area coverage is complete

For any completed review, the consolidated ``Remediation_Plan`` represents every
subject in each area's fixed expected set — the nine owner areas overall, the
eight AWS module boundaries (``ai, compute, database, identity, observability,
runtime, security, storage``), all 14 CI workflows, and every service Dockerfile
plus ``docker-compose.yml``.

Validates: Requirements 1.1, 4.1, 5.1, 7.1

The universal invariant tested here is that *consolidation preserves coverage*:
for any set of findings that between them cover a given expected subject set, the
consolidated plan still represents every one of those subjects — deduplication,
severity ordering, and re-consolidation never drop an area or a subject. The
generative test builds an arbitrary finding set that includes at least the fixed
expected subjects (the nine areas, the eight AWS module subjects, the 14 workflow
subjects, the four Dockerfiles + compose), sprinkles in arbitrary extra findings
plus deliberate ``dedup_key`` collisions and orderings, consolidates, and asserts
every expected area appears in some entry's ``referenced_areas`` and every
expected subject appears in some entry's ``subjects``.

A concrete anchor test then checks the *real* ``build_remediation_plan()`` plan
covers all nine areas / eight AWS modules / 14 workflows / dockerfiles + compose,
tying Property 2 to the actual review.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from cna.review import (
    AREAS,
    Finding,
    RemediationPlan,
    Severity,
    build_remediation_plan,
    consolidate,
)
from cna.review.areas.cicd import (
    GITHUB_HOSTED_WORKFLOWS,
    SELF_HOSTED_ONLY_WORKFLOWS,
)

# A minimum of 100 iterations per the spec's property-test configuration.
_PROPERTY_SETTINGS = settings(max_examples=100)

# ── the fixed expected sets (design Property 2) ──────────────────────────────

# The nine owner areas — the closed set every finding's area is drawn from.
_EXPECTED_AREAS = frozenset(AREAS)

# The two Terraform areas are represented by their relocation records: the
# Terraform itself lives in the appliance repositories (TODO.md T-504).
_EXPECTED_AWS_SUBJECTS = frozenset(
    {"saulpatinojr/Work-Cloud_Network_AWS_Appliance:infra/terraform"}
)

# The core's numbered CI workflows, recorded as repo-relative workflow subjects.
_ALL_WORKFLOWS = SELF_HOSTED_ONLY_WORKFLOWS + GITHUB_HOSTED_WORKFLOWS
_EXPECTED_WORKFLOW_SUBJECTS = frozenset(
    f".github/workflows/{workflow}" for workflow in _ALL_WORKFLOWS
)

# The four service Dockerfiles plus the compose file (Requirement 7.1).
_EXPECTED_CONTAINER_SUBJECTS = frozenset(
    {
        "Dockerfile",
        "apps/cna-api/Dockerfile",
        "apps/cna-web/Dockerfile",
        "apps/cna-worker/Dockerfile",
        "docker-compose.yml",
    }
)

# Every fixed subject that Property 2 requires the consolidated plan to represent.
_EXPECTED_SUBJECTS = (
    _EXPECTED_AWS_SUBJECTS | _EXPECTED_WORKFLOW_SUBJECTS | _EXPECTED_CONTAINER_SUBJECTS
)


# ── generators ───────────────────────────────────────────────────────────────

_AREA = st.sampled_from(sorted(AREAS))
_SEVERITY = st.sampled_from(list(Severity))
# Non-empty once stripped, matching the Finding well-formedness constraint.
_NON_EMPTY_ACTION = st.text(min_size=1).filter(lambda s: s.strip())
# A small shared alphabet of extra dedup keys so arbitrary findings frequently
# collide on a key and exercise the merge/union behaviour.
_EXTRA_DEDUP_KEY = st.sampled_from(["extra-a", "extra-b", "extra-c", "extra-d"])
_EXTRA_SUBJECT = st.text()
# Either fixable (no blocker) or blocker-owned; a group is an escalation iff any
# contributing finding is blocker-owned. Coverage must hold regardless.
_BLOCKER_ID = st.none() | st.sampled_from(
    ["R-001", "R-002", "R-003", "R-004", "R-005", "R-006", "R-008", "R-009"]
)


@st.composite
def _extra_finding(draw: st.DrawFn) -> Finding:
    """An arbitrary well-formed finding not tied to any expected subject.

    These are the "noise" findings: arbitrary area/severity/action/subject with a
    dedup key drawn from a small pool so collisions (and thus merges) are common.
    """
    return Finding(
        area=draw(_AREA),
        severity=draw(_SEVERITY),
        proposed_action=draw(_NON_EMPTY_ACTION),
        dedup_key=draw(_EXTRA_DEDUP_KEY),
        subject=draw(_EXTRA_SUBJECT),
        blocker_id=draw(_BLOCKER_ID),
    )


def _covering_finding(
    area: str,
    subject: str,
    *,
    severity: Severity,
    dedup_key: str,
    blocker_id: str | None,
) -> Finding:
    """A finding that records one required (area, subject) into the plan."""
    return Finding(
        area=area,
        severity=severity,
        proposed_action=f"cover {subject}",
        dedup_key=dedup_key,
        subject=subject,
        blocker_id=blocker_id,
    )


@st.composite
def _covering_findings(draw: st.DrawFn) -> list[Finding]:
    """Findings that between them cover every fixed expected area and subject.

    Every one of the nine owner areas is emitted at least once (so area coverage
    is representable), the AWS relocation subject is attached to the
    ``terraform-aws`` area, the workflow subjects to ``cicd``, and the
    container subjects to ``containers-packaging`` — matching how the real area
    emitters record them. Severity, dedup key, and blocker id are drawn freely so
    the required subjects land under merges, escalations, and every ordering.
    """
    findings: list[Finding] = []

    # Ensure each of the nine owner areas is present at least once. Its subject
    # is arbitrary here (area coverage, not subject coverage, is what this line
    # guarantees); the subject-specific lines below cover the fixed subjects.
    for area in sorted(AREAS):
        findings.append(
            _covering_finding(
                area,
                draw(_EXTRA_SUBJECT),
                severity=draw(_SEVERITY),
                dedup_key=draw(st.text(min_size=1).filter(lambda s: s.strip())),
                blocker_id=None,
            )
        )

    # The AWS relocation subject under the terraform-aws area.
    for subject in sorted(_EXPECTED_AWS_SUBJECTS):
        findings.append(
            _covering_finding(
                "terraform-aws",
                subject,
                severity=draw(_SEVERITY),
                dedup_key=draw(st.text(min_size=1).filter(lambda s: s.strip())),
                blocker_id=draw(_BLOCKER_ID),
            )
        )

    # The workflow subjects under the cicd area.
    for subject in sorted(_EXPECTED_WORKFLOW_SUBJECTS):
        findings.append(
            _covering_finding(
                "cicd",
                subject,
                severity=draw(_SEVERITY),
                dedup_key=draw(st.text(min_size=1).filter(lambda s: s.strip())),
                blocker_id=draw(_BLOCKER_ID),
            )
        )

    # The four Dockerfiles + compose under the containers-packaging area.
    for subject in sorted(_EXPECTED_CONTAINER_SUBJECTS):
        findings.append(
            _covering_finding(
                "containers-packaging",
                subject,
                severity=draw(_SEVERITY),
                dedup_key=draw(st.text(min_size=1).filter(lambda s: s.strip())),
                blocker_id=draw(_BLOCKER_ID),
            )
        )

    return findings


@st.composite
def _covering_plan_input(draw: st.DrawFn) -> list[Finding]:
    """A shuffled mix of the covering findings plus arbitrary extra findings.

    The extra findings add dedup-collisions and noise; the shuffle exercises
    arbitrary orderings so coverage cannot depend on emitter order.
    """
    findings = draw(_covering_findings())
    findings += draw(st.lists(_extra_finding(), max_size=20))
    return draw(st.permutations(findings))


def _represented_areas(plan: RemediationPlan) -> set[str]:
    """Every area represented across the plan's entries."""
    represented: set[str] = set()
    for entry in plan.entries:
        represented |= entry.referenced_areas
    return represented


def _subject_tokens(plan: RemediationPlan) -> set[str]:
    """Every subject token across the plan, split on commas.

    Some real findings record several subjects in one comma-joined ``subject``
    string; splitting on commas exposes each individual subject path so the
    coverage assertions see them.
    """
    tokens: set[str] = set()
    for entry in plan.entries:
        for subject in entry.subjects:
            for token in subject.split(","):
                tokens.add(token.strip())
    return tokens


# ── the universal invariant: consolidation preserves coverage ────────────────


@_PROPERTY_SETTINGS
@given(findings=_covering_plan_input())
def test_property2_consolidation_preserves_area_coverage(
    findings: list[Finding],
) -> None:
    """Feature: production-readiness, Property 2: Area coverage is complete.

    For any finding set that emits every one of the nine owner areas (plus
    arbitrary extra findings, dedup collisions, and orderings), the consolidated
    plan still represents all nine areas across its entries' ``referenced_areas``.
    """
    plan = consolidate(findings)
    represented = _represented_areas(plan)
    missing = _EXPECTED_AREAS - represented
    assert not missing, f"consolidation dropped owner areas: {sorted(missing)}"


@_PROPERTY_SETTINGS
@given(findings=_covering_plan_input())
def test_property2_consolidation_preserves_subject_coverage(
    findings: list[Finding],
) -> None:
    """Feature: production-readiness, Property 2: Area coverage is complete.

    For any finding set that records every fixed expected subject (the eight AWS
    module subjects, the 14 workflow subjects, and the four Dockerfiles + compose)
    plus arbitrary noise, dedup collisions, and orderings, the consolidated plan
    still represents every one of those subjects across its entries' ``subjects``.
    """
    plan = consolidate(findings)
    tokens = _subject_tokens(plan)
    missing = _EXPECTED_SUBJECTS - tokens
    assert not missing, f"consolidation dropped subjects: {sorted(missing)}"


# ── concrete anchor: the real review plan is fully covered ───────────────────


def test_property2_real_plan_covers_all_nine_owner_areas() -> None:
    """Feature: production-readiness, Property 2: Area coverage is complete.

    The real ``build_remediation_plan()`` plan represents all nine owner areas
    (Requirement 1.1) across its entries' ``referenced_areas``.
    """
    plan = build_remediation_plan()
    represented = _represented_areas(plan)
    assert represented == _EXPECTED_AREAS, (
        f"missing owner areas: {sorted(_EXPECTED_AREAS - represented)}"
    )


def test_property2_real_plan_covers_the_aws_relocation_subject() -> None:
    """Feature: production-readiness, Property 2: Area coverage is complete.

    The real plan represents the AWS Terraform area (Requirement 4.1) through its
    relocation record — the modules themselves live in the AWS appliance.
    """
    tokens = _subject_tokens(build_remediation_plan())
    for subject in sorted(_EXPECTED_AWS_SUBJECTS):
        assert any(token.startswith(subject) for token in tokens), (
            f"AWS module subject not covered: {subject}"
        )


def test_property2_real_plan_covers_all_core_workflows() -> None:
    """Feature: production-readiness, Property 2: Area coverage is complete.

    The real plan represents every core CI workflow (Requirement 5.1) as a subject.
    """
    assert len(_ALL_WORKFLOWS) == 4
    tokens = _subject_tokens(build_remediation_plan())
    missing = _EXPECTED_WORKFLOW_SUBJECTS - tokens
    assert not missing, f"CI workflows not covered: {sorted(missing)}"


def test_property2_real_plan_covers_dockerfiles_and_compose() -> None:
    """Feature: production-readiness, Property 2: Area coverage is complete.

    The real plan represents the four service Dockerfiles and
    ``docker-compose.yml`` (Requirement 7.1) as subjects.
    """
    tokens = _subject_tokens(build_remediation_plan())
    missing = _EXPECTED_CONTAINER_SUBJECTS - tokens
    assert not missing, f"container subjects not covered: {sorted(missing)}"
