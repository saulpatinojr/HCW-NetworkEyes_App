"""The hedge check judges the engine's wording, not the customer's resource names (issue 356).

A fact quotes values from the customer's export. Before this fix a resource called
``may-promo-listener`` raised ``ObservedStateViolation`` out of ``evaluate`` and stopped the
whole report. Now the customer's values are masked before the scan, and a finding that still
fails the check is withheld and its rule listed in ``unknowns`` with a content-free reason,
while the rest of the report renders. A hedge word the engine itself writes is still refused.
"""

from __future__ import annotations

import json
import logging
import re

import pytest
from engine_fixtures import export_rows

from network_assessment_azure_engine import AzureSubscriptionTopology, AzureTopology, evaluate
from network_assessment_azure_engine import normalize_resource_graph as normalize
from network_assessment_azure_engine.findings import enforcer as enforcer_module
from network_assessment_azure_engine.findings.enforcer import (
    ObservedStateEnforcer,
    mask_customer_values,
)
from network_assessment_azure_engine.findings.schema import FindingSeverity, FrameworkMapping
from network_assessment_azure_engine.model.azure import VNet
from network_assessment_azure_engine.rules import HEDGED_WORDING_REASON, Observation, rule
from network_assessment_azure_engine.rules.registry import _CustomerValues

ENFORCER = ObservedStateEnforcer()
SUB = "00000000-0000-0000-0000-000000000001"

# One word per pattern in the enforcer's list; the first test proves the two stay in step.
HEDGE_WORDS = [
    "may", "might", "could", "should", "possibly", "probably", "likely", "appears", "seems",
    "suggest", "suggests", "indicates", "potentially", "expected", "typically", "usually",
    "generally",
]  # fmt: skip


def test_the_word_list_covers_every_hedge_pattern() -> None:
    for pattern in enforcer_module._HEDGE_PATTERNS:
        assert any(re.fullmatch(pattern, w) for w in HEDGE_WORDS), pattern
    for word in HEDGE_WORDS:
        assert ENFORCER.scan_text(word) == [word], word


def _renamed_export(prefix: str) -> list[dict]:
    """The sample export with every ``hcw-sample-`` name and id renamed to start ``prefix``."""
    return json.loads(json.dumps(export_rows()).replace("hcw-sample-", prefix))


BASELINE = evaluate(normalize(export_rows()))


@pytest.mark.parametrize("word", HEDGE_WORDS)
def test_names_containing_a_hedge_word_still_give_the_full_report(word: str) -> None:
    """Every resource named ``<word>-promo-...`` (and ``<Word>-promo-...``): same findings."""
    for prefix in (f"{word}-promo-", f"{word.title()}-promo-"):
        report = evaluate(normalize(_renamed_export(prefix)))
        assert sorted(f.id.replace(prefix, "hcw-sample-") for f in report.findings) == sorted(
            f.id for f in BASELINE.findings
        )
        assert report.unknowns == BASELINE.unknowns
        assert any(prefix in f.observed_state.fact for f in report.findings), (
            "the renamed resources reach the facts, so the check really met the hedge word"
        )


@pytest.mark.parametrize("word", HEDGE_WORDS)
def test_a_resource_named_only_a_hedge_word_is_withheld_not_fatal(word: str, caplog) -> None:
    """A VNet named exactly ``may``: its findings go to unknowns; the rest still renders."""
    rows = json.loads(json.dumps(export_rows()).replace("hcw-sample-vnet", word))
    with caplog.at_level(logging.WARNING, logger="network_assessment_azure_engine.rules"):
        report = evaluate(normalize(rows))
    withheld = {u.rule_id for u in report.unknowns if u.reason == HEDGED_WORDING_REASON}
    assert withheld, "a fact quoting the bare name is withheld"
    assert report.total_count > 0, "the other findings are still reported"
    for f in report.findings:
        values = _CustomerValues(normalize(rows))
        for text in (f.observed_state.fact, f.title, f.description or ""):
            assert ENFORCER.scan_text(text, values) == [], (f.rule_id, text)
    for unknown in report.unknowns:
        assert not re.search(rf"\b{word}\b", unknown.reason, re.IGNORECASE), unknown.reason
    for record in caplog.records:
        assert not re.search(rf"\b{word}\b", record.getMessage(), re.IGNORECASE)


def test_masking_keeps_word_boundaries() -> None:
    text = "Listener may-promo-listener on gateway ma is enabled; traffic may be lost."
    masked = mask_customer_values(text, ["may-promo-listener", "ma", "may"])
    assert "may-promo-listener" not in masked
    assert "traffic may be lost" in masked, "a short value never cuts into the engine's words"
    assert ENFORCER.scan_text(text, ["may-promo-listener"]) == ["may"]
    assert (
        ENFORCER.scan_text("Listener may-promo-listener is enabled.", ["may-promo-listener"]) == []
    )


@pytest.fixture
def scratch_registry(monkeypatch):
    monkeypatch.setattr("network_assessment_azure_engine.rules.registry.RULES", {})


def _register_hedged_rule() -> None:
    @rule(
        id="AZ-TEST-001",
        title="Test rule",
        severity=FindingSeverity.LOW,
        category="Test",
        version=1,
        learn_url="https://learn.microsoft.com/azure/virtual-network/",
        frameworks=(FrameworkMapping(framework="Test", control="T-1"),),
        applies_to="export",
        evidence="vnets[]",
    )
    def hedged(sub, topo):
        for vnet in sub.vnets:
            yield Observation(
                resource_id=vnet.id,
                resource_type="microsoft.network/virtualnetworks",
                fact=f"VNet {vnet.name} may be exposed.",
                evidence_ref="e",
            )


@pytest.mark.parametrize("name", ["hcw-sample-vnet", "may", "may-promo-vnet"])
def test_hedged_engine_wording_is_never_reported(scratch_registry, name: str) -> None:
    """Our own "may" is refused whatever the resource is called, and the report still renders."""
    _register_hedged_rule()
    vnet = VNet(
        id=f"/subscriptions/{SUB}/vnet/{name}",
        name=name,
        location="eastus",
        resource_group="hcw-sample-rg",
        subscription_id=SUB,
    )
    topology = AzureTopology(
        engagement_id="hcw-sample",
        tenant_id="t",
        subscriptions=[AzureSubscriptionTopology(subscription_id=SUB, tenant_id="t", vnets=[vnet])],
    )
    report = evaluate(topology)
    assert report.findings == []
    assert [(u.rule_id, u.reason) for u in report.unknowns] == [
        ("AZ-TEST-001", HEDGED_WORDING_REASON)
    ]
    assert name not in report.unknowns[0].reason
