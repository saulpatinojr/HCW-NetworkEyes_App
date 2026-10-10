"""Observed-state enforcer — Phase D (DD-002).

Every finding MUST describe an observed fact.
This enforcer blocks findings that contain hedge language — words that indicate
assumption rather than observation.

Hedge word list is intentionally conservative. If a word is borderline,
it goes on the list. Engineers can request removal via design doc amendment.
"""

from __future__ import annotations

import re

# Words that indicate assumption, not observation.
# Protocol: lowercase, word-boundary matched.
_HEDGE_PATTERNS = [
    r"\bmay\b",
    r"\bmight\b",
    r"\bcould\b",
    r"\bshould\b",
    r"\bpossibly\b",
    r"\bprobably\b",
    r"\blikely\b",
    r"\bappears\b",
    r"\bseems\b",
    r"\bsuggests?\b",
    r"\bindicates\b",
    r"\bpotentially\b",
    r"\bexpected\b",
    r"\btypically\b",
    r"\busually\b",
    r"\bgenerally\b",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _HEDGE_PATTERNS]


class ObservedStateViolation(ValueError):
    """Raised when a finding contains hedge language in observed_state."""

    pass


class ObservedStateEnforcer:
    """Validates that a finding's observed_state.fact contains no hedge language.

    Usage:
        enforcer = ObservedStateEnforcer()
        enforcer.validate(finding)   # raises ObservedStateViolation on failure
    """

    def validate(self, finding) -> None:
        """Raise ObservedStateViolation if fact contains hedge language."""
        fact = finding.observed_state.fact
        violations = []
        for pattern in _COMPILED:
            match = pattern.search(fact)
            if match:
                violations.append(match.group(0))
        if violations:
            raise ObservedStateViolation(
                f"Finding {finding.rule_id} on {finding.resource_id}: "
                f"observed_state.fact contains hedge language: {violations!r}. "
                f"Fact must describe what was observed, not what is assumed. "
                f"Rewrite without: {violations}"
            )

    def scan_text(self, text: str) -> list[str]:
        """Return list of hedge words found in text. Empty = clean."""
        found = []
        for pattern in _COMPILED:
            match = pattern.search(text)
            if match:
                found.append(match.group(0))
        return found
