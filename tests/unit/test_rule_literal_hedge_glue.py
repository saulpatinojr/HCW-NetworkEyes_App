"""No rule glues a hedge word to a separator in its own string literals (issue 364).

The hedge check excuses a hedge word that sits inside one of the customer's identifiers, joined
to the rest by ``-``, ``.``, ``/`` or ``:`` (``hub-may-01``). So a rule that wrote its own hedge
word straight after a customer value, as in ``f"{name}-may"``, would be excused whenever a
customer owns the identifier ``hub-may``. No rule does this today; this test keeps it that way.

It reads the source of every Azure rule module and of the AWS analysis, which share the same
check, and fails on any string literal (f-string parts included) that has a hedge word from the
enforcer's own list next to ``-``, ``_``, ``.``, ``/`` or ``:``. Docstrings and other bare string
statements are skipped: they are never shown to a reader.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import network_assessment.ai_engine.analysis_engine as aws_analysis
import network_assessment_azure_engine.rules as azure_rules
from network_assessment_azure_engine.findings import enforcer

SEPARATORS = "-_./:"
# The enforcer's own list, read from it: each pattern is ``\b<word>\b``. Here the boundary is a
# letter or digit only, so ``_`` next to the word counts as a separator, not as part of a word.
_WORDS = "|".join(p.replace(r"\b", "") for p in enforcer._HEDGE_PATTERNS)
_HEDGE = re.compile(rf"(?<![A-Za-z0-9])(?:{_WORDS})(?![A-Za-z0-9])", re.IGNORECASE)

RULE_SOURCES = sorted(Path(azure_rules.__file__).parent.glob("*.py")) + [
    Path(aws_analysis.__file__)
]


def glued_hedge_words(source: str) -> list[tuple[int, str]]:
    """``(line, literal)`` for every literal in ``source`` with a hedge word beside a separator."""
    tree = ast.parse(source)
    skipped = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
    }
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in skipped:
            continue
        text = node.value
        for match in _HEDGE.finditer(text):
            before = text[match.start() - 1] if match.start() else ""
            after = text[match.end()] if match.end() < len(text) else ""
            if (before and before in SEPARATORS) or (after and after in SEPARATORS):
                found.append((node.lineno, text))
                break
    return found


def test_every_enforcer_pattern_is_a_plain_bounded_word():
    """The list is read by stripping ``\\b``; a pattern of another shape would be read wrongly."""
    for pattern in enforcer._HEDGE_PATTERNS:
        assert pattern.startswith(r"\b") and pattern.endswith(r"\b"), pattern
        assert re.fullmatch(r"[a-z?]+", pattern[2:-2]), pattern


@pytest.mark.parametrize(
    "source",
    [
        'name = "hub"\nfact = f"Listener {name}-may has no WAF."\n',
        'fact = f"Listener {name}.likely has no WAF."\n',
        'fact = "Gateway " + name + "_could"\n',
        'fact = f"Route {prefix}:should"\n',
        'fact = f"{rg}/possibly-{name}"\n',
        'fact = f"{name}-SHOULD"\n',
    ],
)
def test_the_check_catches_a_glued_hedge_word(source):
    assert glued_hedge_words(source), source


@pytest.mark.parametrize(
    "source",
    [
        '"""A docstring may mention ``may-promo-listener``."""\n',
        'def f():\n    """Return the may-x example."""\n',
        'fact = f"Listener {name} has no WAF."\n',
        'title = "Mayday maybe dismayed"\n',
    ],
)
def test_the_check_leaves_clean_literals_alone(source):
    assert glued_hedge_words(source) == [], source


@pytest.mark.parametrize("path", RULE_SOURCES, ids=lambda p: p.name)
def test_no_rule_literal_glues_a_hedge_word_to_a_separator(path):
    assert RULE_SOURCES, "no rule modules found"
    found = glued_hedge_words(path.read_text(encoding="utf-8"))
    assert found == [], (
        f"{path.name}: a hedge word sits next to one of {SEPARATORS!r}, so a customer "
        f"identifier could excuse it; reword with a space or drop the word: {found}"
    )
