"""Property-based tests for self-hosted-only SPOF flagging in the ``cicd`` area.

Feature: production-readiness
Property 13: Self-hosted-only workflows are flagged as SPOFs

For any CI workflow whose set of runners is exactly the self-hosted runner, the
review records a ``Remediation_Plan`` entry identifying the single point of
failure and carrying a proposed mitigation. Concretely, the pure classifier
``is_self_hosted_spof`` returns ``True`` exactly when the runner set is
``{"self-hosted"}`` (no GitHub-hosted fallback, no matrix), and the recorded
SPOF finding is a MEDIUM ``cna.review.model.Finding`` carrying a mitigation in
its ``proposed_action``.

Validates: Requirements 5.2
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from cna.review.areas.cicd import (
    SELF_HOSTED_RUNNER,
    _spof_finding,
    is_self_hosted_spof,
)
from cna.review.model import Severity

# A minimum of 100 iterations per the spec's property-test configuration.
_PROPERTY_SETTINGS = settings(max_examples=100)

# GitHub-hosted (and other non-self-hosted) runner labels a workflow might use.
# Any of these in the set means there is a fallback executor, so the workflow is
# not a self-hosted single point of failure.
_GITHUB_HOSTED_RUNNERS = (
    "ubuntu-latest",
    "ubuntu-22.04",
    "windows-latest",
    "macos-latest",
    "self-hosted-linux-arm64",  # a distinct label, not the bare self-hosted SPOF
)

# An arbitrary runner set drawn from both the self-hosted label and GitHub-hosted
# labels — covers the empty set, the SPOF singleton, mixed sets, and multi-runner
# matrices.
_RUNNER = st.sampled_from([SELF_HOSTED_RUNNER, *_GITHUB_HOSTED_RUNNERS])
_RUNNER_SET = st.sets(_RUNNER, max_size=5)


@_PROPERTY_SETTINGS
@given(runners=_RUNNER_SET)
def test_property13_spof_iff_runners_are_exactly_self_hosted(
    runners: set[str],
) -> None:
    """Feature: production-readiness, Property 13: Self-hosted-only workflows are flagged as SPOFs.

    ``is_self_hosted_spof`` is ``True`` exactly when the runner set is the lone
    self-hosted runner: any GitHub-hosted fallback (or a matrix with an extra
    runner) makes it ``False``, and the empty set is ``False``.
    """
    flagged = is_self_hosted_spof(runners)

    expected = runners == {SELF_HOSTED_RUNNER}
    assert flagged is expected

    if flagged:
        # Exactly the singleton self-hosted set — no fallback, no matrix.
        assert runners == {SELF_HOSTED_RUNNER}
        assert SELF_HOSTED_RUNNER in runners
    else:
        # Not flagged ⇒ either no self-hosted executor at all, or at least one
        # other runner provides a fallback path.
        assert runners != {SELF_HOSTED_RUNNER}
        if runners:
            assert (runners - {SELF_HOSTED_RUNNER}) or SELF_HOSTED_RUNNER not in runners


@_PROPERTY_SETTINGS
@given(runners=_RUNNER_SET)
def test_property13_flagged_workflows_record_a_mitigating_spof_finding(
    runners: set[str],
) -> None:
    """Feature: production-readiness, Property 13: Self-hosted-only workflows are flagged as SPOFs.

    When (and only when) a workflow's runner set is exactly the self-hosted
    runner, the review records a SPOF ``Finding`` that is MEDIUM severity,
    identifies the single point of failure, and carries a proposed mitigation.
    """
    workflow = "999-synthetic.yml"

    if not is_self_hosted_spof(runners):
        # No SPOF finding is warranted for a non-self-hosted-only runner set.
        return

    finding = _spof_finding(workflow)

    # A Remediation_Plan entry for the cicd area, at MEDIUM severity.
    assert finding.area == "cicd"
    assert finding.severity is Severity.MEDIUM
    assert finding.subject.endswith(workflow)
    assert finding.dedup_key == f"cicd:self-hosted-spof:{workflow}"

    action = finding.proposed_action.lower()
    # Identifies the single point of failure...
    assert "single" in action and "point of failure" in action
    assert "self-hosted" in action
    # ...and carries a concrete proposed mitigation.
    assert "mitigate" in action
