"""Renderers, the findings contract (section 9) and the public surface of the package."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys

from engine_fixtures import export_rows

import network_assessment_azure_engine as engine
from network_assessment_azure_engine import (
    RULES,
    RULES_VERSION,
    TOPOLOGY_MODEL_VERSION,
    AzureTopology,
    Finding,
    FindingsReport,
    ObservedState,
    Unknown,
    classify_topology,
    evaluate,
    normalize_resource_graph,
    render_json,
    render_markdown,
    rules_table,
)
from network_assessment_azure_engine.findings.schema import FINDINGS_SCHEMA_VERSION, FindingSeverity


def _report() -> tuple[AzureTopology, FindingsReport]:
    topology = normalize_resource_graph(export_rows())
    return topology, evaluate(topology)


class TestContract:
    def test_versions(self):
        assert TOPOLOGY_MODEL_VERSION == "1.4.0"
        assert RULES_VERSION == "2026.10.0"
        assert FINDINGS_SCHEMA_VERSION == "1.1.0"
        assert engine.__version__ == "0.1.0"

    def test_observed_state_carries_its_state(self):
        assert ObservedState(fact="f", evidence_ref="e").state == "observed"
        assert ObservedState(state="unknown", fact="f", evidence_ref="e").state == "unknown"

    def test_finding_serialises_camel_by_alias_and_snake_by_default(self):
        f = Finding(
            rule_id="AZ-NET-001",
            severity=FindingSeverity.LOW,
            title="t",
            account_id="s",
            observed_state="fact",
        )
        camel = f.model_dump(by_alias=True)
        assert (
            camel["subscriptionId"] == "s"
            and camel["ruleVersion"] == 1
            and "observedState" in camel
        )
        snake = f.model_dump()
        assert snake["account_id"] == "s" and snake["rule_version"] == 1
        assert f.observed_state.evidence_ref == ""  # string coercion kept

    def test_report_carries_versions_and_unknowns(self):
        _, report = _report()
        assert (
            report.rules_version == RULES_VERSION and report.model_version == TOPOLOGY_MODEL_VERSION
        )
        assert report.engagement_id is None
        assert all(isinstance(u, Unknown) for u in report.unknowns)
        live_only = {rid for rid, (meta, _) in RULES.items() if meta.applies_to == "live-only"}
        assert live_only <= {u.rule_id for u in report.unknowns}
        assert {
            "AZ-NET-020",
            "AZ-NET-022",
            "AZ-NET-027",
            "AZ-NET-030",
            "AZ-NET-031",
            "AZ-NET-014",
        } <= {f.rule_id for f in report.findings}
        # the firewall's policy says Deny: AZ-NET-003 must not fire on the Alert of the firewall itself
        assert "AZ-NET-003" not in {
            f.rule_id for f in report.findings if f.resource_id.endswith("hcw-sample-fw")
        }

    def test_old_checkpoint_shape_still_validates(self):
        """A 1.3.0 checkpoint carries engagement and tenant ids and no export fields."""
        topology = AzureTopology.model_validate(
            {
                "schema_version": "1.3.0",
                "engagement_id": "e",
                "tenant_id": "t",
                "subscriptions": [{"subscription_id": "s", "tenant_id": "t", "vnets": []}],
            }
        )
        assert topology.source == "discovery" and topology.has_properties is True
        assert topology.subscriptions[0].flow_logs == []

    def test_rules_table_shape(self):
        table = rules_table()
        assert len(table) == 45
        assert set(table[0]) == {
            "id",
            "title",
            "severity",
            "category",
            "version",
            "appliesTo",
            "evidence",
            "needsProperties",
            "description",
            "remediation",
            "learnUrl",
            "frameworks",
        }


class TestRenderers:
    def test_markdown_sections(self):
        topology, report = _report()
        md = render_markdown(
            report, classification=classify_topology(topology), warnings=topology.warnings
        )
        assert md.startswith("# Azure network assessment report")
        for heading in (
            "## Summary",
            "## Topology",
            "## Findings by severity",
            "## Rules this input cannot answer",
            "## Notice",
        ):
            assert heading in md
        assert f"Rules {RULES_VERSION}, model {TOPOLOGY_MODEL_VERSION}" in md
        assert "### CRITICAL · AZ-NET-020 ·" in md
        assert "| AZ-NET-008 | needs a live read" in md
        assert "[VERIFY]" in md

    def test_markdown_without_findings(self):
        empty = FindingsReport(
            rules_version="r",
            model_version="m",
            findings=[],
            total_count=0,
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            generated_at="now",
        )
        md = render_markdown(empty)
        assert "No finding was observed." in md and "Every registered rule was evaluated" in md

    def test_json_document(self):
        _, report = _report()
        doc = json.loads(render_json(report))
        assert (
            doc["rulesVersion"] == RULES_VERSION and doc["modelVersion"] == TOPOLOGY_MODEL_VERSION
        )
        assert doc["unknowns"] and {"ruleId", "reason"} == set(doc["unknowns"][0])
        assert doc["findings"][0]["observedState"]["state"] == "observed"
        assert "subscriptionId" in doc["findings"][0]


class TestSurface:
    def test_every_exported_name_resolves(self):
        for name in engine.__all__:
            assert getattr(engine, name) is not None, name

    def test_import_loads_no_cloud_sdk(self):
        code = "import sys, network_assessment_azure_engine; assert not [m for m in sys.modules if m == 'azure' or m.startswith('azure.')], 'azure imported'"
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr

    def test_discovery_guard(self, monkeypatch):
        from network_assessment_azure_engine import discovery

        monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
        try:
            discovery.require_azure_extra()
        except ImportError as exc:
            assert "network-assessment-azure-engine[azure]" in str(exc)
        else:
            raise AssertionError("expected ImportError without the extra")
