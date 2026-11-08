"""Observed-state enforcer — Phase D (DD-002).

Every finding MUST describe an observed fact.
This enforcer blocks findings that contain hedge language — words that indicate
assumption rather than observation.

Hedge word list is intentionally conservative. If a word is borderline,
it goes on the list. Engineers can request removal via design doc amendment.

The check judges the engine's own wording, not the customer's. A fact quotes values copied
from the customer's input (resource names, ids, locations), and a resource called
``may-promo-listener`` is not hedge language. ``validate`` and ``scan_text`` therefore take
``customer_values``: each occurrence of one of those values in the text, as a whole word, is
masked before the scan. A value that is nothing but a hedge word (a resource named ``may``) is
never masked, so a hedge word the engine wrote can only be hidden by a customer value that
also contains the engine's surrounding words.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

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

# What a masked customer value is replaced with: no word characters, so it cannot form or
# complete a hedge word, and the words beside it keep their word boundaries.
_MASK = "<value>"


def _is_hedge_word(value: str) -> bool:
    """True when ``value`` is a hedge word and nothing else (ignoring surrounding spaces)."""
    stripped = value.strip()
    return any(pattern.fullmatch(stripped) for pattern in _COMPILED)


def mask_customer_values(text: str, customer_values: Iterable[str]) -> str:
    """``text`` with every whole-word occurrence of a customer value replaced by a mask.

    Longest values first, so an id is masked before the name inside it. An occurrence counts
    only when it is not part of a longer word (a value ``ma`` never cuts into ``may``), and a
    value that is only a hedge word is left in place for the scan to judge.
    """
    candidates = sorted(
        {v for v in customer_values if v and v.strip() and v in text and not _is_hedge_word(v)},
        key=len,
        reverse=True,
    )
    for value in candidates:
        text = re.sub(rf"(?<!\w){re.escape(value)}(?!\w)", _MASK, text)
    return text


class ObservedStateViolation(ValueError):
    """Raised when a finding contains hedge language in observed_state."""

    pass


class ObservedStateEnforcer:
    """Validates that a finding's observed_state.fact contains no hedge language.

    Usage:
        enforcer = ObservedStateEnforcer()
        enforcer.validate(finding)   # raises ObservedStateViolation on failure
    """

    def validate(self, finding, customer_values: Iterable[str] = ()) -> None:
        """Raise ObservedStateViolation if fact contains hedge language.

        ``customer_values`` are values copied from the customer's input; see the module text.
        """
        violations = self.scan_text(finding.observed_state.fact, customer_values)
        if violations:
            raise ObservedStateViolation(
                f"Finding {finding.rule_id} on {finding.resource_id}: "
                f"observed_state.fact contains hedge language: {violations!r}. "
                f"Fact must describe what was observed, not what is assumed. "
                f"Rewrite without: {violations}"
            )

    def scan_text(self, text: str, customer_values: Iterable[str] = ()) -> list[str]:
        """Return list of hedge words found in text. Empty = clean.

        With ``customer_values``, the customer's values are masked first and only the rest of
        the text, the engine's own wording, is judged.
        """
        found = []
        if not self._hits(text):
            return found
        text = mask_customer_values(text, customer_values)
        for pattern in _COMPILED:
            match = pattern.search(text)
            if match:
                found.append(match.group(0))
        return found

    @staticmethod
    def _hits(text: str) -> bool:
        return any(pattern.search(text) for pattern in _COMPILED)
