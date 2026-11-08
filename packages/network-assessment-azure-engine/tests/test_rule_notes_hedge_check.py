"""Remediation and framework notes are hedge-free, and customer values are never a plain string (issue 364).

A rule's title and description were checked for hedge words when it was registered, but its
``remediation`` and the ``alignment`` note of each framework mapping were not, although both are
shown to the reader beside the finding. Two notes said "suggests" and "indicates". Registration
now checks them too.

``scan_text`` takes the customer's identifiers as a collection. A plain ``str`` is a collection
of its characters, so passing one by mistake would turn the identifier lookup into something
else; it is refused with ``TypeError`` on every call, whether or not the text holds a hedge word,
so a wrong caller fails at its first test instead of on the first customer name with a hedge word.
"""

from __future__ import annotations

import pytest

from network_assessment_azure_engine import AzureSubscriptionTopology, AzureTopology
from network_assessment_azure_engine.findings.enforcer import (
    ObservedStateEnforcer,
    ObservedStateViolation,
)
from network_assessment_azure_engine.findings.schema import (
    Finding,
    FindingSeverity,
    FrameworkMapping,
    ObservedState,
)
from network_assessment_azure_engine.rules import rule, rule_metadata
from network_assessment_azure_engine.rules.registry import evaluate_subscription

ENFORCER = ObservedStateEnforcer()
RULE_IDS = [m.id for m in rule_metadata()]
SUB = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def scratch_registry(monkeypatch):
    """An empty registry, so the registration tests leave the real one untouched."""
    monkeypatch.setattr("network_assessment_azure_engine.rules.registry.RULES", {})


def _meta(**overrides):
    base = {
        "id": "AZ-TEST-364",
        "title": "Test rule",
        "severity": FindingSeverity.LOW,
        "category": "Test",
        "version": 1,
        "learn_url": "https://learn.microsoft.com/azure/virtual-network/",
        "frameworks": (FrameworkMapping(framework="Test", control="T-1"),),
        "applies_to": "export",
        "evidence": "vnets[]",
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_every_remediation_and_framework_note_is_hedge_free(rule_id: str) -> None:
    meta = next(m for m in rule_metadata() if m.id == rule_id)
    assert ENFORCER.scan_text(meta.remediation or "") == [], (rule_id, meta.remediation)
    for mapping in meta.frameworks:
        note = mapping.alignment or ""
        assert ENFORCER.scan_text(note) == [], (rule_id, mapping.framework, note)


class TestRegistrationChecksTheNotes:
    def test_hedged_remediation_raises(self, scratch_registry):
        with pytest.raises(ObservedStateViolation, match="remediation"):
            rule(**_meta(remediation="Enable flow logs; traffic could be unmonitored."))

    def test_hedged_framework_note_raises(self, scratch_registry):
        hedged = FrameworkMapping(framework="Test", control="T-1", alignment="Zero hits suggests X")
        with pytest.raises(ObservedStateViolation, match=r"frameworks\[1\]\.alignment"):
            rule(**_meta(frameworks=(FrameworkMapping(framework="Test"), hedged)))

    def test_hedge_free_notes_register(self, scratch_registry):
        clean = FrameworkMapping(framework="Test", control="T-1", alignment="No traffic is seen")
        rule(**_meta(remediation="Route the spokes through the firewall.", frameworks=(clean,)))


class TestCustomerValuesAreNeverAPlainString:
    @pytest.mark.parametrize("values", ["hub-may-01", b"hub-may-01", ""])
    def test_scan_text_refuses_a_string(self, values):
        with pytest.raises(TypeError, match="customer_values"):
            ENFORCER.scan_text("Listener hub-may-01 has no WAF.", values)

    def test_refused_even_when_the_text_has_no_hedge_word(self):
        """The check runs before the early return, so a wrong caller fails on any text."""
        with pytest.raises(TypeError, match="customer_values"):
            ENFORCER.scan_text("Listener hub-01 has no WAF.", "hub-01")

    def test_validate_refuses_a_string(self):
        finding = Finding(
            rule_id="AZ-TEST-364",
            severity=FindingSeverity.LOW,
            title="t",
            observed_state=ObservedState(fact="Listener hub-01 has no WAF.", evidence_ref="e"),
        )
        with pytest.raises(TypeError, match="customer_values"):
            ENFORCER.validate(finding, "hub-01")

    def test_evaluate_subscription_refuses_a_string(self):
        sub = AzureSubscriptionTopology(subscription_id=SUB, tenant_id="t")
        topology = AzureTopology(engagement_id="hcw-sample", tenant_id="t", subscriptions=[sub])
        with pytest.raises(TypeError, match="customer_values"):
            evaluate_subscription(sub, topology, customer_values="hub-may-01")

    def test_a_one_item_set_still_excuses_the_identifier(self):
        """The supported way to pass one identifier."""
        text = "Listener hub-may-01 has no WAF."
        assert ENFORCER.scan_text(text, {"hub-may-01"}) == []
        assert ENFORCER.scan_text(text, ["hub-may-01"]) == []
        assert ENFORCER.scan_text(text) == ["may"]
