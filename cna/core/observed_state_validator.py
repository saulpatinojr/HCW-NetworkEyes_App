"""Observed-state validator for AI-generated findings.

Closes TODO_PhaseA: DD-002 and DD-008 are policies, not controls.

The problem: `observed_state` is a required string field. A model could write
'this is likely a dev environment' and pass schema validation. That is an
assumption masquerading as an observed fact.

This module implements a two-layer control:

  Layer 1 — Linguistic hedge detector:
    Scans observed_state text for assumption language patterns.
    Words like 'likely', 'probably', 'appears to be', 'seems', 'may be',
    'could be', 'we assume' are prohibited.
    Raises ObservedStateViolation with the offending phrase.

  Layer 2 — Evidence linkage check:
    Every observed_state must reference at least one evidence_id from the
    engagement's collected topology data.
    If the finding has no evidence_ids, it cannot be verified as grounded.
    Raises ObservedStateViolation with remediation guidance.

This runs on every finding before it enters the findings store.
AI pipeline (Phase D) calls validate_finding() before persisting.
"""

from __future__ import annotations

import re

# Patterns that indicate assumption, not observation
HEDGE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\blikely\b", re.IGNORECASE),
    re.compile(r"\bprobably\b", re.IGNORECASE),
    re.compile(r"\bappears to\b", re.IGNORECASE),
    re.compile(r"\bseems\b", re.IGNORECASE),
    re.compile(r"\bmay be\b", re.IGNORECASE),
    re.compile(r"\bcould be\b", re.IGNORECASE),
    re.compile(r"\bwe assume\b", re.IGNORECASE),
    re.compile(r"\btypically\b", re.IGNORECASE),
    re.compile(r"\busually\b", re.IGNORECASE),
    re.compile(r"\bin most cases\b", re.IGNORECASE),
    re.compile(r"\bpossibly\b", re.IGNORECASE),
    re.compile(r"\bperhaps\b", re.IGNORECASE),
    re.compile(r"\bexpected to\b", re.IGNORECASE),
    re.compile(r"\bshould be\b", re.IGNORECASE),
    re.compile(r"\bI think\b", re.IGNORECASE),
    re.compile(r"\bthis suggests\b", re.IGNORECASE),
]


class ObservedStateViolation(Exception):
    """Raised when a finding's observed_state contains non-observed language."""

    def __init__(self, finding_id: str, violation: str, offending_phrase: str | None = None):
        msg = f"Finding '{finding_id}' observed_state violation: {violation}"
        if offending_phrase:
            msg += f" (offending phrase: '{offending_phrase}')"
        super().__init__(msg)
        self.finding_id = finding_id
        self.violation = violation
        self.offending_phrase = offending_phrase


def validate_observed_state(finding_id: str, observed_state: str, evidence_ids: list[str]) -> None:
    """Validate that observed_state contains only observed facts.

    Args:
        finding_id: Finding identifier for error context.
        observed_state: The observed_state string from the finding.
        evidence_ids: List of evidence IDs this finding is grounded in.

    Raises:
        ObservedStateViolation: If hedging language or missing evidence found.
    """
    # Layer 1: hedge detection
    for pattern in HEDGE_PATTERNS:
        match = pattern.search(observed_state)
        if match:
            raise ObservedStateViolation(
                finding_id=finding_id,
                violation="Assumption language detected in observed_state. "
                "Only observed, evidence-backed facts are permitted.",
                offending_phrase=match.group(0),
            )

    # Layer 2: evidence linkage
    if not evidence_ids:
        raise ObservedStateViolation(
            finding_id=finding_id,
            violation="No evidence_ids provided. Every finding must be grounded "
            "in at least one piece of collected topology data.",
        )
