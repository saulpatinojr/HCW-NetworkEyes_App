"""Phase F — S3 Deployer.

Uploads all engagement deliverables to an S3 bucket and generates
pre-signed download URLs with configurable TTL.

Design contracts:
  - Content-type headers set per file extension (Gap #14)
  - CORS configuration applied to bucket on every publish run (Gap #13)
  - Pre-signed URL TTL is configurable with a hard cap of 7 days (Gap #11)
  - Upload progress reported via callback (Gap #15)
  - Credentials from environment / instance profile / STS — never hardcoded

Required IAM permissions for CNA-Publish role:
  s3:PutObject         — upload deliverables
  s3:PutBucketCors     — CORS configuration
  s3:GetObject         — pre-signed URL generation
  s3:DeleteObject      — retention cleanup (called by RetentionEngine)
  s3:ListBucket        — status checks
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from cna.delivery_portal.portal_generator import CONTENT_TYPES

logger = logging.getLogger("cna.portal.s3")

_MAX_PRESIGNED_TTL_SECONDS = 7 * 24 * 3600  # 7 days hard cap
_DEFAULT_PRESIGNED_TTL_SECONDS = 7 * 24 * 3600

_CORS_CONFIGURATION = {
    "CORSRules": [
        {
            "AllowedHeaders": ["*"],
            "AllowedMethods": ["GET"],
            "AllowedOrigins": ["*"],
            "ExposeHeaders": ["ETag", "Content-Disposition"],
            "MaxAgeSeconds": 3600,
        }
    ]
}


class S3Deployer:
    """Uploads deliverables to S3 and generates pre-signed URLs."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        region: str = "us-east-1",
        presigned_ttl_seconds: int = _DEFAULT_PRESIGNED_TTL_SECONDS,
    ):
        self._bucket = bucket
        self._prefix = prefix.rstrip("/")
        self._region = region
        self._ttl = min(presigned_ttl_seconds, _MAX_PRESIGNED_TTL_SECONDS)
        if presigned_ttl_seconds > _MAX_PRESIGNED_TTL_SECONDS:
            logger.warning(
                "Requested TTL %ds exceeds hard cap %ds. Capped at %ds.",
                presigned_ttl_seconds,
                _MAX_PRESIGNED_TTL_SECONDS,
                self._ttl,
            )
        self._client = self._make_client()

    @staticmethod
    def _make_client():
        try:
            import boto3

            return boto3.client("s3")
        except ImportError as err:
            raise ImportError(
                "boto3 is required for S3 deployment. Install with: pip install boto3"
            ) from err

    def _object_key(self, file_path: Path) -> str:
        return f"{self._prefix}/{file_path.name}" if self._prefix else file_path.name

    def _content_type(self, file_path: Path) -> str:
        return CONTENT_TYPES.get(file_path.suffix.lower(), "application/octet-stream")

    def configure_cors(self) -> None:
        """Apply CORS configuration to the bucket (required for browser downloads)."""
        self._client.put_bucket_cors(
            Bucket=self._bucket,
            CORSConfiguration=_CORS_CONFIGURATION,
        )
        logger.info("CORS configured on bucket: %s", self._bucket)

    def upload(
        self,
        file_path: Path,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> str:
        """Upload a single file. Returns S3 object key.

        progress_callback(bytes_transferred, total_bytes) called during upload.
        """
        key = self._object_key(file_path)
        content_type = self._content_type(file_path)
        size = file_path.stat().st_size

        extra_args = {"ContentType": content_type}

        if progress_callback:
            from boto3.s3.transfer import TransferConfig

            config = TransferConfig(multipart_threshold=8 * 1024 * 1024)

            def _callback(bytes_amount: int):
                progress_callback(bytes_amount, size)

            self._client.upload_file(
                str(file_path),
                self._bucket,
                key,
                ExtraArgs=extra_args,
                Callback=_callback,
                Config=config,
            )
        else:
            self._client.upload_file(
                str(file_path),
                self._bucket,
                key,
                ExtraArgs=extra_args,
            )

        logger.info("Uploaded: s3://%s/%s (%s, %d bytes)", self._bucket, key, content_type, size)
        return key

    def generate_presigned_url(self, object_key: str) -> str:
        """Generate a pre-signed GET URL. TTL capped at 7 days."""
        url = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": object_key},
            ExpiresIn=self._ttl,
        )
        logger.debug("Pre-signed URL generated for %s (TTL: %ds)", object_key, self._ttl)
        return url

    def delete_prefix(self, prefix: str) -> int:
        """Delete all objects under prefix. Used by RetentionEngine. Returns count deleted."""
        paginator = self._client.get_paginator("list_objects_v2")
        deleted = 0
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if objects:
                self._client.delete_objects(
                    Bucket=self._bucket,
                    Delete={"Objects": objects, "Quiet": True},
                )
                deleted += len(objects)
        logger.info(
            "RetentionEngine: deleted %d objects under s3://%s/%s", deleted, self._bucket, prefix
        )
        return deleted

    def upload_all(
        self,
        file_paths: list[Path],
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> dict[str, str]:
        """Upload all files and return {local_path_str: presigned_url}.

        progress_callback(filename, bytes_transferred, total_bytes)
        """
        self.configure_cors()
        signed_urls = {}
        for fp in file_paths:
            cb = (
                (lambda b, t, fp=fp: progress_callback(fp.name, b, t))
                if progress_callback
                else None
            )
            key = self.upload(fp, progress_callback=cb)
            signed_urls[str(fp)] = self.generate_presigned_url(key)
        return signed_urls
