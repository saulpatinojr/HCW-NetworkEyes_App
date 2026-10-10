"""Unit tests for the production-readiness consolidation engine.

Example and edge-case coverage for :func:`cna.review.consolidate` — the merge
(union of areas/subjects, max severity), severity-descending ordering,
idempotence, and fixable-vs-escalation classification described in the design
("Consolidation, Deduplication, and Escalation"). The universal invariants for
ordering and dedup are covered separately by the property tests (tasks 1.4/1.5).
"""

from cna.review import (
    Finding,
    PlanEntry,
    RemediationPlan,
    Severity,
    consolidate,
)


def _finding(
    *,
    area: str,
    severity: Severity,
    dedup_key: str,
    subject: str,
    blocker_id: str | None = None,
    proposed_action: str = "do a thing",
) -> Finding:
    return Finding(
        area=area,
        severity=severity,
        proposed_action=proposed_action,
        dedup_key=dedup_key,
        subject=subject,
        blocker_id=blocker_id,
    )


def test_consolidate_empty_yields_empty_plan():
    plan = consolidate([])
    assert isinstance(plan, RemediationPlan)
    assert plan.entries == []


def test_single_finding_becomes_one_entry():
    plan = consolidate(
        [
            _finding(
                area="cicd",
                severity=Severity.HIGH,
                dedup_key="cicd:unpinned",
                subject=".github/workflows/010-ci.yml",
            )
        ]
    )
    assert len(plan.entries) == 1
    entry = plan.entries[0]
    assert entry.dedup_key == "cicd:unpinned"
    assert entry.severity is Severity.HIGH
    assert entry.referenced_areas == {"cicd"}
    assert entry.subjects == {".github/workflows/010-ci.yml"}
    assert entry.is_escalation is False
    assert entry.blocker_id is None


def test_merge_unions_areas_and_subjects_and_takes_max_severity():
    plan = consolidate(
        [
            _finding(
                area="terraform-aws",
                severity=Severity.LOW,
                dedup_key="shared:defect",
                subject="modules/storage/main.tf",
            ),
            _finding(
                area="observability",
                severity=Severity.CRITICAL,
                dedup_key="shared:defect",
                subject="modules/observability/main.tf",
            ),
            _finding(
                area="terraform-aws",
                severity=Severity.MEDIUM,
                dedup_key="shared:defect",
                subject="modules/storage/main.tf",  # duplicate subject collapses
            ),
        ]
    )
    assert len(plan.entries) == 1
    entry = plan.entries[0]
    assert entry.referenced_areas == {"terraform-aws", "observability"}
    assert entry.subjects == {
        "modules/storage/main.tf",
        "modules/observability/main.tf",
    }
    assert entry.severity is Severity.CRITICAL  # max among contributors


def test_distinct_dedup_keys_stay_separate():
    plan = consolidate(
        [
            _finding(
                area="cicd",
                severity=Severity.LOW,
                dedup_key="a",
                subject="s1",
            ),
            _finding(
                area="cicd",
                severity=Severity.LOW,
                dedup_key="b",
                subject="s2",
            ),
        ]
    )
    assert {e.dedup_key for e in plan.entries} == {"a", "b"}


def test_entries_ordered_by_severity_descending():
    plan = consolidate(
        [
            _finding(area="cicd", severity=Severity.LOW, dedup_key="low", subject="s"),
            _finding(area="cicd", severity=Severity.CRITICAL, dedup_key="crit", subject="s"),
            _finding(area="cicd", severity=Severity.MEDIUM, dedup_key="med", subject="s"),
        ]
    )
    severities = [e.severity for e in plan.entries]
    assert severities == [Severity.CRITICAL, Severity.MEDIUM, Severity.LOW]


def test_blocker_owned_finding_classified_as_escalation():
    plan = consolidate(
        [
            _finding(
                area="terraform-aws",
                severity=Severity.HIGH,
                dedup_key="aws:needs-account",
                subject="environments/aws/prod",
                blocker_id="R-001",
            )
        ]
    )
    entry = plan.entries[0]
    assert entry.is_escalation is True
    assert entry.blocker_id == "R-001"


def test_group_with_any_blocker_becomes_escalation():
    """A group is an escalation iff any contributing finding is blocker-owned."""
    plan = consolidate(
        [
            _finding(
                area="terraform-aws",
                severity=Severity.MEDIUM,
                dedup_key="aws:runtime-secret",
                subject="environments/aws/prod",
            ),
            _finding(
                area="security-secrets",
                severity=Severity.HIGH,
                dedup_key="aws:runtime-secret",
                subject="environments/aws/prod",
                blocker_id="R-006",
            ),
        ]
    )
    assert len(plan.entries) == 1
    entry = plan.entries[0]
    assert entry.is_escalation is True
    assert entry.blocker_id == "R-006"


def test_fixable_group_carries_no_blocker_id():
    plan = consolidate(
        [
            _finding(
                area="documentation",
                severity=Severity.LOW,
                dedup_key="doc:stale-version",
                subject="README.md",
            )
        ]
    )
    entry = plan.entries[0]
    assert entry.is_escalation is False
    assert entry.blocker_id is None


def test_consolidation_is_idempotent():
    findings = [
        _finding(
            area="terraform-aws",
            severity=Severity.LOW,
            dedup_key="shared",
            subject="modules/storage/main.tf",
        ),
        _finding(
            area="observability",
            severity=Severity.CRITICAL,
            dedup_key="shared",
            subject="modules/observability/main.tf",
        ),
        _finding(
            area="cicd",
            severity=Severity.HIGH,
            dedup_key="pin",
            subject=".github/workflows/010-ci.yml",
            blocker_id="R-003",
        ),
        _finding(
            area="documentation",
            severity=Severity.MEDIUM,
            dedup_key="doc",
            subject="README.md",
        ),
    ]

    once = consolidate(findings)
    twice = consolidate(once.entries)

    assert _plan_shape(once) == _plan_shape(twice)


def test_reconsolidating_plan_entries_preserves_classification():
    once = consolidate(
        [
            _finding(
                area="terraform-aws",
                severity=Severity.HIGH,
                dedup_key="aws:account",
                subject="environments/aws/prod",
                blocker_id="R-001",
            )
        ]
    )
    twice = consolidate(once.entries)
    entry = twice.entries[0]
    assert entry.is_escalation is True
    assert entry.blocker_id == "R-001"
    assert entry.referenced_areas == {"terraform-aws"}


def test_lowest_blocker_id_chosen_when_group_has_several():
    plan = consolidate(
        [
            _finding(
                area="terraform-aws",
                severity=Severity.HIGH,
                dedup_key="aws:multi",
                subject="s",
                blocker_id="R-004",
            ),
            _finding(
                area="terraform-aws",
                severity=Severity.HIGH,
                dedup_key="aws:multi",
                subject="s",
                blocker_id="R-002",
            ),
        ]
    )
    assert plan.entries[0].blocker_id == "R-002"


def _plan_shape(plan: RemediationPlan) -> list[tuple[object, ...]]:
    """A comparable, order-sensitive snapshot of a plan's entries."""
    return [
        (
            e.dedup_key,
            e.severity,
            e.proposed_action,
            frozenset(e.referenced_areas),
            frozenset(e.subjects),
            e.is_escalation,
            e.blocker_id,
        )
        for e in plan.entries
    ]


def test_mixed_findings_and_entries_merge_together():
    """A raw finding and a plan entry sharing a dedup_key collapse into one."""
    existing = PlanEntry(
        dedup_key="shared",
        severity=Severity.LOW,
        proposed_action="do a thing",
        referenced_areas={"cicd"},
        subjects={"s1"},
        is_escalation=False,
    )
    new = _finding(
        area="observability",
        severity=Severity.HIGH,
        dedup_key="shared",
        subject="s2",
    )
    plan = consolidate([existing, new])
    assert len(plan.entries) == 1
    entry = plan.entries[0]
    assert entry.referenced_areas == {"cicd", "observability"}
    assert entry.subjects == {"s1", "s2"}
    assert entry.severity is Severity.HIGH
