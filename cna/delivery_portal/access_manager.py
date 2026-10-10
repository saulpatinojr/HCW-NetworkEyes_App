"""Phase F — Access Manager.

Manages pre-signed URL and SAS token generation, TTL enforcement,
and access link records for each published engagement.

Responsibilities:
  - Record every access link issued (URL, TTL, issued_at, expires_at, cloud)
  - Enforce TTL hard cap (7 days) regardless of caller-requested TTL
  - Provide `is_expired()` check for `cna publish status`
  - Write access record to EngagementStore for audit trail
  - Never store actual pre-signed URL in the store (security) — only metadata
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

logger = logging.getLogger("cna.portal.access")

_MAX_TTL_HOURS = 7 * 24  # 7 days — hard cap
_DEFAULT_TTL_HOURS = 7 * 24

CloudProvider = Literal["aws", "azure"]


@dataclass
class AccessRecord:
    """Metadata record for an issued access link (URL never stored)."""

    engagement_id: str
    cloud: CloudProvider
    issued_at: str
    expires_at: str
    ttl_hours: int
    storage_location: str  # s3://bucket/prefix or https://account.blob.core.windows.net/container
    deliverable_count: int

    def is_expired(self) -> bool:
        """True if access link has passed its expiry time."""
        expiry = datetime.fromisoformat(self.expires_at)
        return datetime.now(UTC) >= expiry

    def hours_remaining(self) -> float:
        """Hours until expiry. Negative if already expired."""
        expiry = datetime.fromisoformat(self.expires_at)
        delta = expiry - datetime.now(UTC)
        return delta.total_seconds() / 3600

    def to_dict(self) -> dict:
        return {
            "engagement_id": self.engagement_id,
            "cloud": self.cloud,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "ttl_hours": self.ttl_hours,
            "storage_location": self.storage_location,
            "deliverable_count": self.deliverable_count,
        }


class AccessManager:
    """Issues and tracks access links for engagement deliverables."""

    @staticmethod
    def compute_expiry(ttl_hours: int) -> tuple[str, str, int]:
        """Compute issued_at, expires_at, effective_ttl_hours (capped at 7 days).

        Returns (issued_at_iso, expires_at_iso, effective_ttl_hours)
        """
        effective_ttl = min(ttl_hours, _MAX_TTL_HOURS)
        if ttl_hours > _MAX_TTL_HOURS:
            logger.warning(
                "Requested TTL %dh exceeds hard cap %dh. Capped.", ttl_hours, _MAX_TTL_HOURS
            )
        now = datetime.now(UTC)
        expiry = now + timedelta(hours=effective_ttl)
        return now.isoformat(), expiry.isoformat(), effective_ttl

    @staticmethod
    def build_record(
        engagement_id: str,
        cloud: CloudProvider,
        storage_location: str,
        deliverable_count: int,
        ttl_hours: int = _DEFAULT_TTL_HOURS,
    ) -> AccessRecord:
        """Build an AccessRecord for an issued link set."""
        issued_at, expires_at, effective_ttl = AccessManager.compute_expiry(ttl_hours)
        record = AccessRecord(
            engagement_id=engagement_id,
            cloud=cloud,
            issued_at=issued_at,
            expires_at=expires_at,
            ttl_hours=effective_ttl,
            storage_location=storage_location,
            deliverable_count=deliverable_count,
        )
        logger.info(
            "Access record issued: %s | %s | expires %s | %d deliverables",
            engagement_id,
            cloud,
            expires_at,
            deliverable_count,
        )
        return record
