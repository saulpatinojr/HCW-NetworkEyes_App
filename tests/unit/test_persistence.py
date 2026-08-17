"""Regression tests for EngagementStore (TODO.md T-410).

`EngagementStore` had no test file at all, which is how three separate
signature bugs survived a green suite:

  * `init()` and `save()` called `config.model_dump(mode="json", default=str)`.
    Pydantic v2's `model_dump` has no `default` parameter, so both raised
    `TypeError: BaseModel.model_dump() got an unexpected keyword argument
    'default'` — meaning an engagement could never be created or saved. The
    argument was redundant as well as invalid: `_atomic_write` already passes
    `default=str` to `json.dump`.
  * `write_audit_event` was called with an extra positional (fixed under T-402).
  * `write_discovery_checkpoint` was called with a keyword that is not a
    parameter (fixed earlier under T-410).

Every test here uses a **real** store on `tmp_path`. That is the point: the
existing suite mocks `EngagementStore`, and a `MagicMock` accepts any method
name, any keyword, and any arity, so none of the above could fail a test.
"""

from __future__ import annotations

import json

import pytest

from cna.core.engagement import EngagementConfig
from cna.core.persistence import EngagementStore


@pytest.fixture
def store(tmp_path):
    return EngagementStore(data_dir=tmp_path)


@pytest.fixture
def config():
    return EngagementConfig(
        engagement_id="test-20260305-0001",
        client_name="Acme Corp",
        client_slug="acme-corp",
        regions=["us-east-1", "eastus"],
    )


class TestInitAndSave:
    """`init()` / `save()` — both raised TypeError before this fix."""

    def test_init_creates_a_readable_state_file(self, store, config):
        engagement_dir = store.init(config)

        state = engagement_dir / store.ENGAGEMENT_FILE
        assert state.is_file(), "init() did not write the engagement state file"
        payload = json.loads(state.read_text())
        assert payload["engagement_id"] == config.engagement_id
        assert payload["client_name"] == "Acme Corp"
        assert payload["regions"] == ["us-east-1", "eastus"]

    def test_init_is_idempotent(self, store, config):
        """The docstring promises same id, same path, safe to retry."""
        first = store.init(config)
        second = store.init(config)
        assert first == second

    def test_save_then_load_round_trips(self, store, config):
        store.init(config)
        config.client_name = "Acme Corporation"
        store.save(config)

        assert store.load(config.engagement_id).client_name == "Acme Corporation"

    def test_state_is_json_serialisable_including_non_primitives(self, store, config):
        """`mode="json"` must render datetimes and enums, not leave objects behind.

        This is what the invalid `default=str` was reaching for; `mode="json"`
        already covers it, and `_atomic_write` passes `default=str` to json.dump
        as a backstop.
        """
        store.init(config)
        raw = (store.engagement_dir(config.engagement_id) / store.ENGAGEMENT_FILE).read_text()
        json.loads(raw)  # would raise if anything non-serialisable leaked through


class TestAuditEvent:
    """`write_audit_event(engagement_id, event)` — two parameters, not three."""

    def test_appends_one_jsonl_line_per_event(self, store, config):
        store.init(config)
        store.write_audit_event(config.engagement_id, {"type": "first", "cloud": "aws"})
        store.write_audit_event(config.engagement_id, {"type": "second", "cloud": "azure"})

        audit = store.engagement_dir(config.engagement_id) / store.AUDIT_LOG_FILE
        events = [json.loads(line) for line in audit.read_text().splitlines() if line.strip()]
        assert [e["type"] for e in events] == ["first", "second"]
        assert all("timestamp" in e for e in events), "the store must stamp each event"

    def test_rejects_the_old_three_argument_call(self, store, config):
        """Guards the T-402 regression: a cloud label passed positionally."""
        store.init(config)
        with pytest.raises(TypeError):
            store.write_audit_event(config.engagement_id, "aws", {"type": "access_denied"})


class TestDiscoveryCheckpoints:
    """`write_discovery_checkpoint(engagement_id, platform, account_or_sub_id, data)`."""

    def test_writes_and_lists_a_checkpoint(self, store, config):
        store.init(config)
        path = store.write_discovery_checkpoint(
            config.engagement_id, "aws", "aws_123456789012_us-east-1", {"region": "us-east-1"}
        )

        assert path.is_file()
        assert json.loads(path.read_text())["region"] == "us-east-1"
        assert store.list_completed_checkpoints(config.engagement_id, "aws")

    def test_sanitises_slashes_and_dashes_in_the_id(self, store, config):
        store.init(config)
        path = store.write_discovery_checkpoint(
            config.engagement_id, "azure", "sub/one-two", {"ok": True}
        )
        assert path.name == "azure_sub_one_two.json"

    def test_rejects_the_old_account_id_keyword(self, store, config):
        """Guards the T-410 regression that broke every AWS region checkpoint."""
        store.init(config)
        with pytest.raises(TypeError):
            store.write_discovery_checkpoint(
                config.engagement_id, "aws", account_id="aws_1_us-east-1", data={}
            )

    def test_checkpoints_are_scoped_per_platform(self, store, config):
        store.init(config)
        store.write_discovery_checkpoint(config.engagement_id, "aws", "acct-1", {})
        store.write_discovery_checkpoint(config.engagement_id, "azure", "sub-1", {})

        assert len(store.list_completed_checkpoints(config.engagement_id, "aws")) == 1
        assert len(store.list_completed_checkpoints(config.engagement_id, "azure")) == 1


class TestReportWrites:
    """`write_findings_report` / `write_deliverable_manifest` (TODO.md T-412).

    Both were called by `AnalysisEngine.run()` and `RenderPipeline.run()` but did
    not exist on the class, so each engine raised `AttributeError` at the point
    it tried to persist its result.
    """

    def test_findings_report_lands_under_reports(self, store, config):
        store.init(config)
        path = store.write_findings_report(
            config.engagement_id, {"total_count": 2, "findings": [{"rule_id": "AZ-COST-001"}]}
        )

        assert path == (
            store.engagement_dir(config.engagement_id)
            / store.REPORTS_DIR
            / store.FINDINGS_REPORT_FILE
        )
        assert json.loads(path.read_text())["total_count"] == 2

    def test_findings_report_serialises_non_primitives(self, store, config):
        """`FindingsReport.model_dump()` keeps enums and datetimes as objects."""
        from datetime import UTC, datetime

        from cna.core.findings_schema import FindingSeverity

        store.init(config)
        path = store.write_findings_report(
            config.engagement_id,
            {"severity": FindingSeverity.CRITICAL, "generated_at": datetime.now(UTC)},
        )
        json.loads(path.read_text())  # `_atomic_write(default=str)` is the backstop

    def test_deliverable_manifest_round_trips(self, store, config):
        store.init(config)
        manifest = {
            "engagement_id": config.engagement_id,
            "records": [{"label": "Executive Report", "format": "pdf"}],
        }
        path = store.write_deliverable_manifest(
            engagement_id=config.engagement_id, manifest=manifest
        )

        assert path.name == store.DELIVERABLE_MANIFEST_FILE
        assert json.loads(path.read_text()) == manifest

    def test_both_writes_are_idempotent(self, store, config):
        store.init(config)
        store.write_findings_report(config.engagement_id, {"total_count": 1})
        second = store.write_findings_report(config.engagement_id, {"total_count": 9})
        assert json.loads(second.read_text())["total_count"] == 9

    def test_writes_create_the_reports_dir_when_init_was_skipped(self, store, config):
        """RenderPipeline may run against a directory built by another process."""
        path = store.write_deliverable_manifest(
            engagement_id=config.engagement_id, manifest={"records": []}
        )
        assert path.is_file()
