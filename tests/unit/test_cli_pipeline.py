"""End-to-end CLI pipeline tests (TODO.md T-412).

The registered `cna` commands were stubs that printed "Phase X: TODO" while
the real implementations sat unwired in `cna/cli/*.py` behind
NotImplementedError guards. These tests drive the now-wired registry with
`click.testing.CliRunner` against a real `EngagementStore` on `tmp_path` —
no mocks, no network: init → seeded discovery checkpoints → analyze →
review complete → report generate → publish status, plus every friendly
gate in between.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from cna.cli.main import cli
from cna.core.persistence import EngagementStore
from cna.core.topology_schema import (
    AzureNSG,
    AzureSubnet,
    AzureSubscriptionTopology,
    NSGSecurityRule,
    VNet,
)

ENGAGEMENT_ID = "acme-20260828-0001"
TENANT_ID = "11111111-1111-1111-1111-111111111111"
SUB_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path


@pytest.fixture
def store(data_dir):
    return EngagementStore(data_dir=data_dir)


def invoke(runner, data_dir, *args):
    return runner.invoke(cli, [*args, "--data-dir", str(data_dir)], catch_exceptions=False)


def seed_azure_checkpoint(store):
    """One subscription with an any-source SSH allow — enough to yield findings."""
    sub = AzureSubscriptionTopology(
        subscription_id=SUB_ID,
        subscription_name="acme-prod",
        tenant_id=TENANT_ID,
        vnets=[
            VNet(
                id="/subscriptions/sub1/vnets/vnet1",
                name="vnet1",
                location="eastus",
                resource_group="rg1",
                subscription_id=SUB_ID,
                address_space=["10.0.0.0/16"],
                subnets=[
                    AzureSubnet(id="/sub1/vnet1/s1", name="default", address_prefix="10.0.1.0/24")
                ],
            )
        ],
        nsgs=[
            AzureNSG(
                id="/subscriptions/sub1/nsgs/nsg1",
                name="nsg1",
                location="eastus",
                resource_group="rg1",
                security_rules=[
                    NSGSecurityRule(
                        name="allow-ssh-any",
                        priority=100,
                        direction="Inbound",
                        access="Allow",
                        protocol="*",
                        source_address_prefix="*",
                        destination_port_range="22",
                    )
                ],
            )
        ],
    )
    store.write_discovery_checkpoint(
        ENGAGEMENT_ID, "azure", SUB_ID, json.loads(sub.model_dump_json())
    )


def init_engagement(runner, data_dir):
    return invoke(
        runner,
        data_dir,
        "init",
        "--client",
        "Acme Corp",
        "--engagement-id",
        ENGAGEMENT_ID,
    )


def run_analyze(runner, data_dir):
    return invoke(
        runner,
        data_dir,
        "analyze",
        "--engagement-id",
        ENGAGEMENT_ID,
        "--azure",
        "--no-recommendations",
    )


def complete_review(runner, data_dir):
    return invoke(
        runner,
        data_dir,
        "review",
        "complete",
        "--engagement-id",
        ENGAGEMENT_ID,
        "--operator",
        "test-op",
    )


class TestInit:
    def test_creates_engagement_state_on_disk(self, runner, data_dir, store):
        result = init_engagement(runner, data_dir)

        assert result.exit_code == 0
        assert ENGAGEMENT_ID in result.output
        config = store.load(ENGAGEMENT_ID)
        assert config.client_name == "Acme Corp"
        assert config.client_slug == "acme-corp"

    def test_is_idempotent(self, runner, data_dir):
        assert init_engagement(runner, data_dir).exit_code == 0
        assert init_engagement(runner, data_dir).exit_code == 0


class TestAnalyze:
    def test_fails_friendly_without_checkpoints(self, runner, data_dir):
        init_engagement(runner, data_dir)

        result = run_analyze(runner, data_dir)

        assert result.exit_code == 1
        assert "Run `cna discover azure` first" in result.output

    def test_requires_a_platform_flag(self, runner, data_dir):
        result = invoke(runner, data_dir, "analyze", "--engagement-id", ENGAGEMENT_ID)

        assert result.exit_code == 1
        assert "--aws or --azure" in result.output

    def test_writes_findings_report_from_checkpoints(self, runner, data_dir, store):
        init_engagement(runner, data_dir)
        seed_azure_checkpoint(store)

        result = run_analyze(runner, data_dir)

        assert result.exit_code == 0
        report = store.load_findings_report(ENGAGEMENT_ID)
        assert report.total_count > 0
        assert report.review_complete is False


class TestReviewComplete:
    def test_fails_friendly_without_findings_report(self, runner, data_dir):
        init_engagement(runner, data_dir)

        result = complete_review(runner, data_dir)

        assert result.exit_code == 1
        assert "Run `cna analyze` first" in result.output

    def test_signs_off_report_and_audits(self, runner, data_dir, store):
        init_engagement(runner, data_dir)
        seed_azure_checkpoint(store)
        run_analyze(runner, data_dir)

        result = complete_review(runner, data_dir)

        assert result.exit_code == 0
        report = store.load_findings_report(ENGAGEMENT_ID)
        assert report.review_complete is True
        assert all(f.human_reviewed for f in report.findings)
        assert store.load(ENGAGEMENT_ID).review_complete is True
        audit_lines = [
            json.loads(line)
            for line in (store.engagement_dir(ENGAGEMENT_ID) / store.AUDIT_LOG_FILE)
            .read_text()
            .splitlines()
        ]
        assert any(
            e["type"] == "review_complete" and e["operator"] == "test-op" for e in audit_lines
        )

    def test_second_run_is_a_noop(self, runner, data_dir, store):
        init_engagement(runner, data_dir)
        seed_azure_checkpoint(store)
        run_analyze(runner, data_dir)
        complete_review(runner, data_dir)

        result = complete_review(runner, data_dir)

        assert result.exit_code == 0
        assert "already complete" in result.output


class TestReport:
    def test_generate_fails_friendly_without_findings(self, runner, data_dir):
        init_engagement(runner, data_dir)

        result = invoke(runner, data_dir, "report", "generate", "--engagement-id", ENGAGEMENT_ID)

        assert result.exit_code == 1
        assert "Run `cna analyze` first" in result.output

    def test_generate_is_blocked_before_review(self, runner, data_dir, store):
        """DD-009: the render pipeline refuses an unreviewed report."""
        init_engagement(runner, data_dir)
        seed_azure_checkpoint(store)
        run_analyze(runner, data_dir)

        result = invoke(
            runner,
            data_dir,
            "report",
            "generate",
            "--engagement-id",
            ENGAGEMENT_ID,
            "--skip-pdf",
            "--no-pptx",
        )

        assert result.exit_code == 1
        assert "Review gate blocked render" in result.output

    def test_preview_works_before_review(self, runner, data_dir, store):
        init_engagement(runner, data_dir)
        seed_azure_checkpoint(store)
        run_analyze(runner, data_dir)

        result = invoke(runner, data_dir, "report", "preview", "--engagement-id", ENGAGEMENT_ID)

        assert result.exit_code == 0
        assert "(pre-review)" in result.output
        preview = data_dir / ENGAGEMENT_ID / "deliverables" / f"{ENGAGEMENT_ID}_preview.html"
        assert preview.is_file()

    def test_generate_after_review_writes_manifest_under_data_dir(self, runner, data_dir, store):
        init_engagement(runner, data_dir)
        seed_azure_checkpoint(store)
        run_analyze(runner, data_dir)
        complete_review(runner, data_dir)

        result = invoke(
            runner,
            data_dir,
            "report",
            "generate",
            "--engagement-id",
            ENGAGEMENT_ID,
            "--skip-pdf",
            "--no-pptx",
        )

        assert result.exit_code == 0
        manifest = store.load_deliverable_manifest(ENGAGEMENT_ID)
        assert manifest["records"], "render produced no deliverables"
        for record in manifest["records"]:
            # Regression: the pipeline used to hardcode ./engagements and
            # ignore --data-dir.
            assert str(data_dir) in record["path"]


class TestPublishStatus:
    def test_fails_friendly_before_any_publish(self, runner, data_dir):
        init_engagement(runner, data_dir)

        result = invoke(runner, data_dir, "publish", "status", "--engagement-id", ENGAGEMENT_ID)

        assert result.exit_code == 1
        assert "Run `cna publish run` first" in result.output

    def test_reads_back_a_written_access_record(self, runner, data_dir, store):
        from cna.delivery_portal.access_manager import AccessManager

        init_engagement(runner, data_dir)
        record = AccessManager.build_record(
            engagement_id=ENGAGEMENT_ID,
            cloud="azure",
            storage_location="https://acct.blob.core.windows.net/cont",
            deliverable_count=2,
            ttl_hours=24,
        )
        store.write_access_record(engagement_id=ENGAGEMENT_ID, record=record.to_dict())

        result = invoke(runner, data_dir, "publish", "status", "--engagement-id", ENGAGEMENT_ID)

        assert result.exit_code == 0
        assert "Portal active" in result.output
        assert store.get_delivery_date(ENGAGEMENT_ID) == record.issued_at
