"""Phase F — Azure Blob Storage Deployer.

Uploads all engagement deliverables to Azure Blob Storage and generates
SAS tokens with configurable TTL.

Design contracts:
  - Uses DefaultAzureCredential — consistent with Phase C auth pattern (auth.py)
  - Content-type headers set per file extension (Gap #14)
  - SAS token TTL configurable with hard cap of 7 days (Gap #11)
  - Upload progress reported via callback (Gap #15)
  - Container-level public access is DISABLED — all access via SAS token only

Required Azure RBAC:
  Storage Blob Data Contributor — on the storage account or container
  (Storage Blob Data Reader is insufficient — write access required for upload)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cna.delivery_portal.portal_generator import CONTENT_TYPES

logger = logging.getLogger("cna.portal.azure_blob")

_MAX_SAS_TTL_HOURS = 7 * 24  # 7 days hard cap
_DEFAULT_SAS_TTL_HOURS = 7 * 24


class AzureBlobDeployer:
    """Uploads deliverables to Azure Blob Storage and generates SAS tokens."""

    def __init__(
        self,
        account_name: str,
        container_name: str,
        sas_ttl_hours: int = _DEFAULT_SAS_TTL_HOURS,
    ):
        self._account = account_name
        self._container = container_name
        self._ttl_hours = min(sas_ttl_hours, _MAX_SAS_TTL_HOURS)
        if sas_ttl_hours > _MAX_SAS_TTL_HOURS:
            logger.warning(
                "SAS TTL %dh exceeds hard cap %dh. Capped.", sas_ttl_hours, _MAX_SAS_TTL_HOURS
            )
        self._client = self._make_client()

    def _make_client(self):
        try:
            from azure.identity import DefaultAzureCredential
            from azure.storage.blob import BlobServiceClient

            credential = DefaultAzureCredential()
            account_url = f"https://{self._account}.blob.core.windows.net"
            return BlobServiceClient(account_url=account_url, credential=credential)
        except ImportError as err:
            raise ImportError(
                "azure-storage-blob and azure-identity are required for Azure Blob deployment. "
                "Install with: pip install azure-storage-blob azure-identity"
            ) from err

    def _content_type(self, file_path: Path) -> str:
        return CONTENT_TYPES.get(file_path.suffix.lower(), "application/octet-stream")

    def ensure_container(self) -> None:
        """Create container if it doesn't exist. Public access is DISABLED."""
        from azure.core.exceptions import ResourceExistsError

        container_client = self._client.get_container_client(self._container)
        try:
            container_client.create_container(public_access=None)  # no public access
            logger.info("Created container: %s (private)", self._container)
        except ResourceExistsError:
            logger.debug("Container already exists: %s", self._container)

    def upload(
        self,
        file_path: Path,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> str:
        """Upload file to blob. Returns blob name."""
        blob_name = file_path.name
        content_type = self._content_type(file_path)
        size = file_path.stat().st_size

        from azure.storage.blob import ContentSettings

        container_client = self._client.get_container_client(self._container)
        blob_client = container_client.get_blob_client(blob_name)

        with file_path.open("rb") as data:
            blob_client.upload_blob(
                data,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
            )

        if progress_callback:
            progress_callback(
                size, size
            )  # Azure SDK doesn't expose chunk callbacks; signal complete

        logger.info(
            "Uploaded: %s/%s (%s, %d bytes)", self._container, blob_name, content_type, size
        )
        return blob_name

    def generate_sas_token(self, blob_name: str) -> str:
        """Generate a SAS token URL for a blob. TTL capped at 7 days."""
        from azure.storage.blob import (
            BlobSasPermissions,
            UserDelegationKey,
            generate_blob_sas,
        )

        expiry = datetime.now(UTC) + timedelta(hours=self._ttl_hours)
        start = datetime.now(UTC) - timedelta(minutes=5)  # clock skew tolerance

        # User delegation key — no storage account key required
        udk: UserDelegationKey = self._client.get_user_delegation_key(
            key_start_time=start,
            key_expiry_time=expiry,
        )

        sas = generate_blob_sas(
            account_name=self._account,
            container_name=self._container,
            blob_name=blob_name,
            user_delegation_key=udk,
            permission=BlobSasPermissions(read=True),
            expiry=expiry,
            start=start,
        )
        url = f"https://{self._account}.blob.core.windows.net/{self._container}/{blob_name}?{sas}"
        logger.debug("SAS token generated for %s (TTL: %dh)", blob_name, self._ttl_hours)
        return url

    def delete_container(self) -> None:
        """Delete the entire container. Used by RetentionEngine for 90-day cleanup."""
        container_client = self._client.get_container_client(self._container)
        container_client.delete_container()
        logger.info("RetentionEngine: deleted container %s", self._container)

    def upload_all(
        self,
        file_paths: list[Path],
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> dict[str, str]:
        """Upload all files and return {local_path_str: sas_url}."""
        self.ensure_container()
        sas_urls = {}
        for fp in file_paths:
            cb = (
                (lambda b, t, fp=fp: progress_callback(fp.name, b, t))
                if progress_callback
                else None
            )
            blob_name = self.upload(fp, progress_callback=cb)
            sas_urls[str(fp)] = self.generate_sas_token(blob_name)
        return sas_urls
