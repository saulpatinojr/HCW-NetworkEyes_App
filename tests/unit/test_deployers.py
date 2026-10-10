"""Unit tests for S3Deployer and AzureBlobDeployer — mock SDK, logic paths only."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cna.delivery_portal.azure_blob_deployer import (
    _MAX_SAS_TTL_HOURS,
    AzureBlobDeployer,
)
from cna.delivery_portal.s3_deployer import (
    _MAX_PRESIGNED_TTL_SECONDS,
    S3Deployer,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_s3_deployer(mock_client: MagicMock | None = None, **kwargs) -> S3Deployer:
    """Create S3Deployer by bypassing __init__ and injecting mock boto3 client."""
    deployer = S3Deployer.__new__(S3Deployer)
    deployer._bucket = kwargs.get("bucket", "test-bucket")
    deployer._prefix = kwargs.get("prefix", "")
    deployer._region = kwargs.get("region", "us-east-1")
    deployer._ttl = kwargs.get("ttl", _MAX_PRESIGNED_TTL_SECONDS)
    deployer._client = mock_client or MagicMock()
    return deployer


def _make_azure_deployer(mock_client: MagicMock | None = None, **kwargs) -> AzureBlobDeployer:
    """Create AzureBlobDeployer by bypassing __init__ and injecting mock SDK client."""
    deployer = AzureBlobDeployer.__new__(AzureBlobDeployer)
    deployer._account = kwargs.get("account", "cnatestaccount")
    deployer._container = kwargs.get("container", "test-container")
    deployer._ttl_hours = kwargs.get("ttl_hours", _MAX_SAS_TTL_HOURS)
    deployer._client = mock_client or MagicMock()
    return deployer


# ── S3Deployer — TTL capping in __init__ ──────────────────────────────────────


class TestS3DeployerTTLCap:
    def test_ttl_capped_at_max(self):
        with patch("cna.delivery_portal.s3_deployer.S3Deployer._make_client") as mock_mk:
            mock_mk.return_value = MagicMock()
            deployer = S3Deployer(
                bucket="bucket",
                presigned_ttl_seconds=_MAX_PRESIGNED_TTL_SECONDS + 9999,
            )
        assert deployer._ttl == _MAX_PRESIGNED_TTL_SECONDS

    def test_ttl_under_cap_unchanged(self):
        with patch("cna.delivery_portal.s3_deployer.S3Deployer._make_client") as mock_mk:
            mock_mk.return_value = MagicMock()
            deployer = S3Deployer(bucket="bucket", presigned_ttl_seconds=3600)
        assert deployer._ttl == 3600


# ── S3Deployer — _object_key ──────────────────────────────────────────────────


class TestS3DeployerObjectKey:
    def test_no_prefix(self):
        deployer = _make_s3_deployer(prefix="")
        assert deployer._object_key(Path("report.pdf")) == "report.pdf"

    def test_with_prefix(self):
        deployer = _make_s3_deployer(prefix="acme/2026-04-09")
        key = deployer._object_key(Path("report.pdf"))
        assert key == "acme/2026-04-09/report.pdf"

    def test_no_double_slash_with_rstripped_prefix(self):
        deployer = _make_s3_deployer()
        deployer._prefix = "engagements"  # already rstripped
        key = deployer._object_key(Path("report.pdf"))
        assert "//" not in key


# ── S3Deployer — _content_type ────────────────────────────────────────────────


class TestS3DeployerContentType:
    def test_pdf_content_type(self):
        deployer = _make_s3_deployer()
        assert deployer._content_type(Path("report.pdf")) == "application/pdf"

    def test_html_content_type(self):
        deployer = _make_s3_deployer()
        assert deployer._content_type(Path("preview.html")) == "text/html; charset=utf-8"

    def test_unknown_extension_falls_back(self):
        deployer = _make_s3_deployer()
        ct = deployer._content_type(Path("data.xyz123"))
        assert ct == "application/octet-stream"


# ── S3Deployer — configure_cors ───────────────────────────────────────────────


class TestS3DeployerConfigureCors:
    def test_calls_put_bucket_cors_with_correct_bucket(self):
        mock_client = MagicMock()
        deployer = _make_s3_deployer(mock_client=mock_client, bucket="my-bucket")
        deployer.configure_cors()
        mock_client.put_bucket_cors.assert_called_once()
        args, kwargs = mock_client.put_bucket_cors.call_args
        assert kwargs.get("Bucket", args[0] if args else None) == "my-bucket"

    def test_cors_config_has_get_method(self):
        mock_client = MagicMock()
        deployer = _make_s3_deployer(mock_client=mock_client)
        deployer.configure_cors()
        call_kwargs = mock_client.put_bucket_cors.call_args[1]
        rules = call_kwargs["CORSConfiguration"]["CORSRules"]
        assert any("GET" in rule.get("AllowedMethods", []) for rule in rules)


# ── S3Deployer — generate_presigned_url ───────────────────────────────────────


class TestS3DeployerPresignedUrl:
    def test_returns_url_from_boto3_client(self):
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = "https://s3.amazonaws.com/signed"
        deployer = _make_s3_deployer(mock_client=mock_client, bucket="my-bucket")
        url = deployer.generate_presigned_url("report.pdf")
        assert url == "https://s3.amazonaws.com/signed"

    def test_passes_correct_params_to_boto3(self):
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = "https://example.com"
        deployer = _make_s3_deployer(mock_client=mock_client, bucket="my-bucket", ttl=3600)
        deployer.generate_presigned_url("report.pdf")
        mock_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "my-bucket", "Key": "report.pdf"},
            ExpiresIn=3600,
        )


# ── S3Deployer — delete_prefix ────────────────────────────────────────────────


class TestS3DeployerDeletePrefix:
    def test_deletes_objects_across_pages(self):
        mock_client = MagicMock()
        paginator = MagicMock()
        mock_client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {"Contents": [{"Key": "prefix/file1.pdf"}, {"Key": "prefix/file2.html"}]},
            {"Contents": [{"Key": "prefix/file3.drawio"}]},
        ]
        deployer = _make_s3_deployer(mock_client=mock_client, bucket="my-bucket")
        count = deployer.delete_prefix("prefix/")
        assert count == 3
        assert mock_client.delete_objects.call_count == 2

    def test_handles_empty_pages_gracefully(self):
        mock_client = MagicMock()
        paginator = MagicMock()
        mock_client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [{"Contents": []}, {}]
        deployer = _make_s3_deployer(mock_client=mock_client)
        count = deployer.delete_prefix("empty-prefix/")
        assert count == 0
        mock_client.delete_objects.assert_not_called()


# ── S3Deployer — make_client raises ImportError when boto3 missing ─────────────


class TestS3DeployerMakeClientImportError:
    def test_raises_import_error_when_boto3_missing(self):
        with patch.dict("sys.modules", {"boto3": None}):
            with pytest.raises(ImportError, match="boto3"):
                S3Deployer(bucket="my-bucket")


# ── AzureBlobDeployer — TTL capping in __init__ ───────────────────────────────


class TestAzureBlobDeployerTTLCap:
    def test_ttl_capped_at_max(self):
        with patch("cna.delivery_portal.azure_blob_deployer.AzureBlobDeployer._make_client") as mk:
            mk.return_value = MagicMock()
            deployer = AzureBlobDeployer(
                account_name="account",
                container_name="container",
                sas_ttl_hours=_MAX_SAS_TTL_HOURS + 100,
            )
        assert deployer._ttl_hours == _MAX_SAS_TTL_HOURS

    def test_ttl_under_cap_unchanged(self):
        with patch("cna.delivery_portal.azure_blob_deployer.AzureBlobDeployer._make_client") as mk:
            mk.return_value = MagicMock()
            deployer = AzureBlobDeployer(
                account_name="account",
                container_name="container",
                sas_ttl_hours=24,
            )
        assert deployer._ttl_hours == 24


# ── AzureBlobDeployer — _content_type ────────────────────────────────────────


class TestAzureBlobDeployerContentType:
    def test_pdf_content_type(self):
        deployer = _make_azure_deployer()
        assert deployer._content_type(Path("report.pdf")) == "application/pdf"

    def test_html_content_type(self):
        deployer = _make_azure_deployer()
        assert deployer._content_type(Path("preview.html")) == "text/html; charset=utf-8"

    def test_unknown_extension_falls_back(self):
        deployer = _make_azure_deployer()
        ct = deployer._content_type(Path("data.xyz999"))
        assert ct == "application/octet-stream"


# ── AzureBlobDeployer — ensure_container ─────────────────────────────────────


class TestAzureBlobDeployerEnsureContainer:
    def test_creates_container_with_no_public_access(self):
        mock_client = MagicMock()
        container_client = MagicMock()
        mock_client.get_container_client.return_value = container_client
        deployer = _make_azure_deployer(mock_client=mock_client, container="test-container")
        deployer.ensure_container()
        container_client.create_container.assert_called_once_with(public_access=None)

    def test_handles_resource_exists_error_silently(self):
        from azure.core.exceptions import ResourceExistsError

        mock_client = MagicMock()
        container_client = MagicMock()
        container_client.create_container.side_effect = ResourceExistsError("exists")
        mock_client.get_container_client.return_value = container_client
        deployer = _make_azure_deployer(mock_client=mock_client)
        deployer.ensure_container()  # Must not raise


# ── AzureBlobDeployer — delete_container ─────────────────────────────────────


class TestAzureBlobDeployerDeleteContainer:
    def test_calls_delete_on_container_client(self):
        mock_client = MagicMock()
        container_client = MagicMock()
        mock_client.get_container_client.return_value = container_client
        deployer = _make_azure_deployer(mock_client=mock_client, container="test-container")
        deployer.delete_container()
        container_client.delete_container.assert_called_once()


# ── AzureBlobDeployer — _make_client raises ImportError when SDK missing ──────


class TestAzureBlobDeployerMakeClientImportError:
    def test_raises_import_error_when_sdk_missing(self):
        with patch.dict("sys.modules", {"azure.identity": None, "azure.storage.blob": None}):
            with pytest.raises(ImportError, match="azure-storage-blob"):
                AzureBlobDeployer(account_name="acct", container_name="container")
