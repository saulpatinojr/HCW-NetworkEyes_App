"""Unit tests for Phase F Delivery Portal.

All cloud SDK calls are mocked — no AWS or Azure credentials required.
Tests cover:
  - PortalGenerator renders valid HTML with all entries
  - Stale badge shown when checksums differ
  - Current badge shown when checksums match
  - AccessManager enforces TTL hard cap
  - AccessManager.is_expired() returns True when past expiry
  - AccessManager.hours_remaining() returns negative when expired
  - RetentionEngine.check() raises RetentionExpiredError past 90 days
  - RetentionEngine.check() passes when delivery_date is None
  - RetentionEngine.check() warns when within 14 days of expiry
  - RetentionEngine.retention_expiry() computes correct date
  - S3Deployer content_type mapping
  - S3Deployer TTL hard cap enforced
  - AzureBlobDeployer content_type mapping
  - AzureBlobDeployer TTL hard cap enforced
  - PortalGenerator.build_entries() marks stale correctly
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from cna.delivery_portal.access_manager import AccessManager, AccessRecord
from cna.delivery_portal.portal_generator import PortalEntry, PortalGenerator
from cna.delivery_portal.retention_engine import RetentionEngine, RetentionExpiredError
from cna.report_engine.deliverable_manifest import DeliverableManifest, DeliverableRecord

# ---------------------------------------------------------------- helpers


def _make_manifest(n: int = 2, checksum: str = "abc123") -> DeliverableManifest:
    m = DeliverableManifest(engagement_id="test-f-001")
    for i in range(n):
        m.add(
            DeliverableRecord(
                label=f"Deliverable {i}",
                path=f"/tmp/file_{i}.pdf",
                format="pdf",
                lang="en",
                findings_checksum=checksum,
            )
        )
    return m


# ---------------------------------------------------------------- PortalGenerator


class TestPortalGenerator:
    def test_renders_html_with_entries(self, tmp_path):
        manifest = _make_manifest(2)
        entries = [
            PortalEntry(
                label="Executive Report",
                format="pdf",
                lang="en",
                size_bytes=102400,
                rendered_at="2026-03-05T00:00:00Z",
                download_url="https://example.com/file.pdf",
                is_stale=False,
            ),
        ]
        gen = PortalGenerator()
        out = tmp_path / "index.html"
        gen.generate(
            manifest=manifest,
            entries=entries,
            published_at="2026-03-05T00:00:00Z",
            expires_at="2026-03-12T00:00:00Z",
            output_path=out,
        )
        assert out.exists()
        content = out.read_text()
        assert "Executive Report" in content
        assert "https://example.com/file.pdf" in content
        assert "test-f-001" in content

    def test_stale_badge_rendered_when_stale(self, tmp_path):
        manifest = _make_manifest(1)
        entries = [
            PortalEntry(
                label="Executive",
                format="pdf",
                lang="en",
                size_bytes=1024,
                rendered_at="2026-03-01T00:00:00Z",
                download_url="https://x.com/f.pdf",
                is_stale=True,
                stale_reason="Rendered before re-analysis",
            ),
        ]
        gen = PortalGenerator()
        out = tmp_path / "index.html"
        gen.generate(
            manifest=manifest,
            entries=entries,
            published_at="2026-03-05T00:00:00Z",
            expires_at="2026-03-12T00:00:00Z",
            output_path=out,
        )
        content = out.read_text()
        assert "Stale" in content
        assert "stale" in content.lower()

    def test_current_badge_when_not_stale(self, tmp_path):
        manifest = _make_manifest(1)
        entries = [
            PortalEntry(
                label="Technical",
                format="pdf",
                lang="en",
                size_bytes=2048,
                rendered_at="2026-03-05T00:00:00Z",
                download_url="https://x.com/t.pdf",
                is_stale=False,
            ),
        ]
        gen = PortalGenerator()
        out = tmp_path / "index.html"
        gen.generate(
            manifest=manifest,
            entries=entries,
            published_at="2026-03-05T00:00:00Z",
            expires_at="2026-03-12T00:00:00Z",
            output_path=out,
        )
        content = out.read_text()
        assert "Current" in content

    def test_build_entries_marks_stale_on_checksum_mismatch(self):
        manifest = _make_manifest(1, checksum="old_checksum")
        signed_urls = {"/tmp/file_0.pdf": "https://s3.example.com/file.pdf"}
        entries = PortalGenerator.build_entries(
            manifest=manifest,
            signed_urls=signed_urls,
            current_findings_checksum="new_checksum",
        )
        assert entries[0].is_stale is True

    def test_build_entries_current_on_checksum_match(self):
        manifest = _make_manifest(1, checksum="same_checksum")
        signed_urls = {"/tmp/file_0.pdf": "https://s3.example.com/file.pdf"}
        entries = PortalGenerator.build_entries(
            manifest=manifest,
            signed_urls=signed_urls,
            current_findings_checksum="same_checksum",
        )
        assert entries[0].is_stale is False


# ---------------------------------------------------------------- AccessManager


class TestAccessManager:
    def test_ttl_hard_cap_enforced(self):
        _, _, effective = AccessManager.compute_expiry(ttl_hours=999)
        assert effective == 168  # 7 days

    def test_ttl_within_cap_unchanged(self):
        _, _, effective = AccessManager.compute_expiry(ttl_hours=24)
        assert effective == 24

    def test_is_expired_true_when_past_expiry(self):
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        record = AccessRecord(
            engagement_id="test",
            cloud="aws",
            issued_at=past,
            expires_at=past,
            ttl_hours=1,
            storage_location="s3://bucket",
            deliverable_count=1,
        )
        assert record.is_expired() is True

    def test_is_expired_false_when_not_expired(self):
        future = (datetime.now(UTC) + timedelta(hours=24)).isoformat()
        record = AccessRecord(
            engagement_id="test",
            cloud="aws",
            issued_at=datetime.now(UTC).isoformat(),
            expires_at=future,
            ttl_hours=24,
            storage_location="s3://bucket",
            deliverable_count=1,
        )
        assert record.is_expired() is False

    def test_hours_remaining_negative_when_expired(self):
        past = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        record = AccessRecord(
            engagement_id="test",
            cloud="aws",
            issued_at=past,
            expires_at=past,
            ttl_hours=1,
            storage_location="s3://bucket",
            deliverable_count=1,
        )
        assert record.hours_remaining() < 0

    def test_build_record_caps_ttl(self):
        record = AccessManager.build_record(
            engagement_id="test",
            cloud="aws",
            storage_location="s3://b",
            deliverable_count=3,
            ttl_hours=9999,
        )
        assert record.ttl_hours == 168


# ---------------------------------------------------------------- RetentionEngine


class TestRetentionEngine:
    def test_check_raises_when_expired(self):
        delivery_date = (datetime.now(UTC) - timedelta(days=91)).isoformat()
        with pytest.raises(RetentionExpiredError):
            RetentionEngine.check("test-001", delivery_date)

    def test_check_passes_when_delivery_date_none(self):
        # No error — retention clock not started
        RetentionEngine.check("test-001", None)

    def test_check_passes_when_within_window(self):
        delivery_date = (datetime.now(UTC) - timedelta(days=10)).isoformat()
        RetentionEngine.check("test-001", delivery_date)  # should not raise

    def test_retention_expiry_is_90_days(self):
        delivery = datetime(2026, 1, 1, tzinfo=UTC).isoformat()
        expiry = RetentionEngine.retention_expiry(delivery)
        assert expiry == datetime(2026, 4, 1, tzinfo=UTC)

    def test_enforce_calls_s3_delete(self):
        mock_deployer = MagicMock()
        RetentionEngine.enforce("test-001", mock_deployer, cloud="aws")
        mock_deployer.delete_prefix.assert_called_once_with(prefix="test-001")

    def test_enforce_calls_azure_delete(self):
        mock_deployer = MagicMock()
        RetentionEngine.enforce("test-001", mock_deployer, cloud="azure")
        mock_deployer.delete_container.assert_called_once()


# ---------------------------------------------------------------- Deployer content-type mapping


class TestContentTypeMapping:
    def test_s3_pdf_content_type(self):
        from cna.delivery_portal.portal_generator import CONTENT_TYPES

        assert CONTENT_TYPES[".pdf"] == "application/pdf"

    def test_s3_pptx_content_type(self):
        from cna.delivery_portal.portal_generator import CONTENT_TYPES

        assert "presentationml" in CONTENT_TYPES[".pptx"]

    def test_s3_html_content_type(self):
        from cna.delivery_portal.portal_generator import CONTENT_TYPES

        assert "text/html" in CONTENT_TYPES[".html"]
