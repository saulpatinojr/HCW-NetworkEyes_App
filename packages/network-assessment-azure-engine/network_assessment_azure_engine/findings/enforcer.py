"""Observed-state enforcer — Phase D (DD-002).

Every finding MUST describe an observed fact.
This enforcer blocks findings that contain hedge language — words that indicate
assumption rather than observation.

Hedge word list is intentionally conservative. If a word is borderline,
it goes on the list. Engineers can request removal via design doc amendment.

The check judges the engine's own wording, not the customer's resource names. A fact quotes
identifiers copied from the customer's input, and a resource called ``may-promo-listener`` is
not hedge language. ``validate`` and ``scan_text`` therefore take ``customer_values``: the
caller passes identifiers only (names, ids, resource groups, locations; never tags,
descriptions, display names or other free text), and a hedge word is excused only when it lies
inside an occurrence of one of those values that passes ``is_maskable``. Such a value has no
whitespace, and every hedge word in it is joined to a letter or digit by ``-``, ``.``,
``/`` or ``:`` (it sits inside an identifier such as ``may-promo-listener`` or ``rg/may.x``).
So no value can excuse a hedge word the engine wrote with a space beside it, and a value that
is a hedge word alone or with only punctuation (``may``, ``may,``) excuses nothing: the
finding is then withheld rather than reported.
"""

from __future__ import annotations

import re
from collections.abc import Container, Iterable

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

# A hedge word inside an identifier: joined to a letter or digit by - . / or :. Not by _: the hedge patterns
# use \b, and _ is a word character, so `may_promo` holds no hedge word to excuse in the first place.
_JOINED_AFTER = re.compile(r"[-./:]+[A-Za-z0-9]")
_JOINED_BEFORE = re.compile(r"[A-Za-z0-9][-./:]+$")


def is_maskable(value: str) -> bool:
    """True when ``value`` holds a hedge word and can excuse it as a customer identifier.

    It must contain a hedge word (any other value changes no verdict), no whitespace,
    and every hedge word in it must be joined to a letter or digit by ``-``, ``.``,
    ``/`` or ``:`` on at least one side. ``may-promo-listener`` and ``rg/may.x`` qualify;
    ``may``, ``may,``, ``may-`` and ``may be`` do not.
    """
    if not value or any(ch.isspace() for ch in value):
        return False
    matches = [m for pattern in _COMPILED for m in pattern.finditer(value)]
    if not matches:
        return False
    return all(
        _JOINED_AFTER.match(value, m.end()) or _JOINED_BEFORE.search(value[: m.start()])
        for m in matches
    )


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _inside_customer_identifier(text: str, start: int, end: int, values: Container[str]) -> bool:
    """True when ``text[start:end]`` (a hedge word) lies inside a maskable customer identifier.

    A maskable value has no whitespace, so an occurrence covering the hedge word lies within
    the run of non-space characters around it. Every slice of that run which covers the hedge
    word and starts and ends on a word boundary (so it is not part of a longer word: a value
    ``ma`` never cuts into ``may``) is looked up in ``values``; a hit that passes
    ``is_maskable`` excuses the word. The answer depends on nothing but the text and the set
    of values, so it is the same in every run.
    """
    left = start
    while left > 0 and not text[left - 1].isspace():
        left -= 1
    right = end
    while right < len(text) and not text[right].isspace():
        right += 1
    starts = [i for i in range(left, start + 1) if i == 0 or not _is_word_char(text[i - 1])]
    ends = [j for j in range(end, right + 1) if j == len(text) or not _is_word_char(text[j])]
    return any(text[i:j] in values and is_maskable(text[i:j]) for i in starts for j in ends)


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

        With ``customer_values``, a hedge word inside one of the customer's identifiers is
        excused (see the module text) and only the engine's own wording is judged. A one-shot
        iterable is read once; pass a set (or any container) to reuse it across calls.
        """
        found = []
        if not self._hits(text):
            return found
        values = (
            customer_values
            if isinstance(customer_values, Container)
            else frozenset(customer_values)
        )
        for pattern in _COMPILED:
            for match in pattern.finditer(text):
                if not _inside_customer_identifier(text, match.start(), match.end(), values):
                    found.append(match.group(0))
                    break
        return found

    @staticmethod
    def _hits(text: str) -> bool:
        return any(pattern.search(text) for pattern in _COMPILED)
