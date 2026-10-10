"""Unit tests for critical finding escalation engine (DD-016)."""

from cna.core.escalation_engine import CriticalFindingEscalationEngine


def test_no_false_positives_on_empty_resource():
    engine = CriticalFindingEscalationEngine()
    engine.evaluate({}, "ec2", "aws")
    assert len(engine.critical_log) == 0


def test_unknown_service_no_escalation():
    engine = CriticalFindingEscalationEngine()
    engine.evaluate({"id": "sg-123"}, "unknown_service", "aws")
    assert len(engine.critical_log) == 0


def test_azure_platform_uses_azure_triggers():
    engine = CriticalFindingEscalationEngine()
    engine.evaluate({"id": "nsg-001"}, "nsg", "azure")
    # _matches returns False in Phase A — no escalation yet
    assert len(engine.critical_log) == 0
