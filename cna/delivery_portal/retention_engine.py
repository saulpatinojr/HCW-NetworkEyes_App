"""Phase F — Retention Engine.

Enforces the 90-day engagement data retention policy (DD-019).

Design:
  - `RetentionEngine.check()` raises `RetentionExpiredError` if the engagement
    is past its 90-day retention window. Called at the start of every
    `cna publish` run to prevent re-publishing expired engagements.
  - `RetentionEngine.enforce()` deletes all remote storage objects for an
    engagement (S3 prefix or Azure Blob container).
  - Retention window: 90 days from the engagement `delivery_date` recorded in
    EngagementStore. If `delivery_date` is not set, retention clock has not started.
  - Deletion is logged to the EngagementStore audit trail before execution.
  - Local engagement files are NOT deleted by this engine — only remote storage.
    Local cleanup is a separate operator step documented in the data handling policy.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

logger = logging.getLogger("cna.portal.retention")

_RETENTION_DAYS = 90
_RETENTION_WARNING_DAYS = 14


class RetentionExpiredError(RuntimeError):
    """Raised when an engagement has passed its 90-day retention window (DD-019)."""

    pass


class RetentionEngine:
    """Checks and enforces 90-day engagement data retention."""

    @staticmethod
    def retention_expiry(delivery_date: str) -> datetime:
        """Compute retention expiry from ISO 8601 delivery_date string."""
        delivered = datetime.fromisoformat(delivery_date)
        if delivered.tzinfo is None:
            delivered = delivered.replace(tzinfo=UTC)
        return delivered + timedelta(days=_RETENTION_DAYS)

    @staticmethod
    def check(engagement_id: str, delivery_date: str | None) -> None:
        """DD-019: Raise RetentionExpiredError if past 90-day window.

        If delivery_date is None, retention clock has not started — no error.
        Call this at the START of cna publish before any upload.
        """
        if delivery_date is None:
            logger.debug("[%s] Retention clock not started (delivery_date not set).", engagement_id)
            return

        expiry = RetentionEngine.retention_expiry(delivery_date)
        now = datetime.now(UTC)

        if now >= expiry:
            raise RetentionExpiredError(
                f"Engagement {engagement_id}: retention window expired on "
                f"{expiry.isoformat()}. Data must be permanently deleted per "
                f"data handling policy (DD-019). "
                f"See documentation/policies/data-handling-policy.md"
            )

        days_remaining = (expiry - now).days
        if days_remaining <= _RETENTION_WARNING_DAYS:
            logger.warning(
                "[%s] Retention window expires in %d days (%s). Schedule data deletion.",
                engagement_id,
                days_remaining,
                expiry.date(),
            )
        else:
            logger.info(
                "[%s] Retention OK. %d days remaining (expires %s).",
                engagement_id,
                days_remaining,
                expiry.date(),
            )

    @staticmethod
    def enforce(
        engagement_id: str,
        deployer,  # S3Deployer or AzureBlobDeployer
        cloud: str,
    ) -> None:
        """Delete all remote storage for an engagement (DD-019 enforcement).

        Call this when the retention window has expired.
        Logs deletion before executing — irreversible operation.
        """
        logger.warning(
            "RETENTION ENFORCEMENT: Deleting all remote storage for [%s] on %s.",
            engagement_id,
            cloud,
        )
        if cloud == "aws":
            deployer.delete_prefix(prefix=engagement_id)
        elif cloud == "azure":
            deployer.delete_container()
        else:
            raise ValueError(f"Unknown cloud provider: {cloud!r}")
        logger.info("RETENTION ENFORCEMENT COMPLETE: [%s] on %s.", engagement_id, cloud)
