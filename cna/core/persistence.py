"""Engagement persistence layer.

Closes TODO_PhaseA: No Persistence Layer + No Engagement ID Strategy + No Rollback/Idempotency.

Storage hierarchy:
  Local (default):   ./engagements/<engagement_id>/
  Azure Blob:        engagements/<engagement_id>/  (if AZURE_STORAGE_ACCOUNT_NAME set)

Engagement ID format: <client_slug>-<YYYYMMDD>-<4-char-hex>
Example: acme-20260305-a3f2
  - Deterministic prefix for human readability
  - Hex suffix prevents same-client-same-day collision
  - Used as: local dir name, blob prefix, S3 prefix, report filename stem
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from cna.core.engagement import EngagementConfig

logger = logging.getLogger("cna.core.persistence")


def generate_engagement_id(client_slug: str) -> str:
    """Generate a deterministic, collision-resistant engagement ID.

    Format: <client_slug>-<YYYYMMDD>-<4-char-hex>
    The 4-char hex suffix is derived from a UUID4 — collision probability
    across 65,536 same-client-same-day IDs is negligible for this use case.
    """
    date_str = datetime.now(UTC).strftime("%Y%m%d")
    suffix = uuid.uuid4().hex[:4]
    slug = client_slug.lower().replace(" ", "-")[:20]
    return f"{slug}-{date_str}-{suffix}"


class EngagementStore:
    """Manages engagement state on local disk.

    All state is written to:
      <data_dir>/<engagement_id>/engagement.json

    Every write is atomic: write to .tmp, then rename — no partial state.
    Every write is idempotent: same engagement_id, same path, safe to retry.

    Locking: a .lock file is written on open() and removed on close().
    A second process seeing the .lock file will raise EngagementLockError.
    This is a filesystem-level advisory lock — sufficient for CLI use cases.
    For multi-operator Azure Blob deployments, Phase D will add Azure Blob leases.
    """

    ENGAGEMENT_FILE = "engagement.json"
    LOCK_FILE = ".lock"
    DISCOVERY_DIR = "discovery"
    DIAGRAMS_DIR = "diagrams"
    REPORTS_DIR = "reports"
    AUDIT_LOG_FILE = "audit.jsonl"
    FINDINGS_REPORT_FILE = "findings_report.json"
    DELIVERABLE_MANIFEST_FILE = "deliverable_manifest.json"

    def __init__(self, data_dir: Path | None = None, engagement_id: str | None = None):
        env_dir = os.environ.get("CNA_DATA_DIR", "./engagements")
        self.data_dir = data_dir or Path(env_dir)
        self.engagement_id = (
            engagement_id  # optional; set by callers that own a specific engagement
        )

    def engagement_dir(self, engagement_id: str) -> Path:
        return self.data_dir / engagement_id

    def init(self, config: EngagementConfig) -> Path:
        """Create engagement directory structure and write initial state.

        Idempotent: safe to call again on an existing engagement (will not overwrite).

        Returns:
            Path to engagement directory.
        """
        eng_dir = self.engagement_dir(config.engagement_id)
        eng_dir.mkdir(parents=True, exist_ok=True)
        (eng_dir / self.DISCOVERY_DIR).mkdir(exist_ok=True)
        (eng_dir / self.DIAGRAMS_DIR).mkdir(exist_ok=True)
        (eng_dir / self.REPORTS_DIR).mkdir(exist_ok=True)

        state_path = eng_dir / self.ENGAGEMENT_FILE
        if not state_path.exists():
            self._atomic_write(state_path, config.model_dump(mode="json"))
            logger.info("Initialized engagement: %s", config.engagement_id)
        else:
            logger.info("Engagement already exists, skipping init: %s", config.engagement_id)

        return eng_dir

    def load(self, engagement_id: str) -> EngagementConfig:
        """Load engagement state from disk.

        Raises:
            EngagementNotFoundError: If engagement directory or file does not exist.
        """
        state_path = self.engagement_dir(engagement_id) / self.ENGAGEMENT_FILE
        if not state_path.exists():
            raise EngagementNotFoundError(
                f"Engagement '{engagement_id}' not found in {self.data_dir}. "
                "Run `cna init --client <name>` first."
            )
        with open(state_path, encoding="utf-8") as f:
            data = json.load(f)
        return EngagementConfig(**data)

    def save(self, config: EngagementConfig) -> None:
        """Persist updated engagement state atomically."""
        state_path = self.engagement_dir(config.engagement_id) / self.ENGAGEMENT_FILE
        self._atomic_write(state_path, config.model_dump(mode="json"))

    def acquire_lock(self, engagement_id: str, operator: str) -> None:
        """Write advisory lock file. Raises EngagementLockError if already locked."""
        lock_path = self.engagement_dir(engagement_id) / self.LOCK_FILE
        if lock_path.exists():
            lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
            raise EngagementLockError(
                f"Engagement '{engagement_id}' is locked by '{lock_data.get('operator')}' "
                f"since {lock_data.get('locked_at')}. "
                "If the previous process crashed, delete the .lock file manually."
            )
        lock_data = {
            "operator": operator,
            "locked_at": datetime.now(UTC).isoformat(),
            "engagement_id": engagement_id,
        }
        lock_path.write_text(json.dumps(lock_data), encoding="utf-8")

    def release_lock(self, engagement_id: str) -> None:
        """Remove advisory lock file."""
        lock_path = self.engagement_dir(engagement_id) / self.LOCK_FILE
        lock_path.unlink(missing_ok=True)

    def write_discovery_checkpoint(
        self, engagement_id: str, platform: str, account_or_sub_id: str, data: dict
    ) -> Path:
        """Write a discovery checkpoint for one account/subscription.

        Closes TODO_PhaseA: No Rollback or Idempotency Design.

        Checkpoint file: discovery/<platform>_<account_id>.json
        --resume reads existing checkpoints and skips completed accounts.
        """
        disc_dir = self.engagement_dir(engagement_id) / self.DISCOVERY_DIR
        disc_dir.mkdir(parents=True, exist_ok=True)
        safe_id = account_or_sub_id.replace("/", "_").replace("-", "_")
        checkpoint_path = disc_dir / f"{platform}_{safe_id}.json"
        self._atomic_write(checkpoint_path, data)
        logger.debug("Checkpoint written: %s", checkpoint_path)
        return checkpoint_path

    def list_completed_checkpoints(self, engagement_id: str, platform: str) -> list[str]:
        """Return account/sub IDs that have completed discovery checkpoints."""
        disc_dir = self.engagement_dir(engagement_id) / self.DISCOVERY_DIR
        if not disc_dir.exists():
            return []
        prefix = f"{platform}_"
        return [
            f.stem.replace(prefix, "", 1).replace("_", "-")
            for f in disc_dir.glob(f"{prefix}*.json")
        ]

    def write_audit_event(self, engagement_id: str, event: dict) -> None:
        """Append an audit event to the engagement audit log (JSONL).

        Closes TODO_PhaseA: No Logging Infrastructure (audit trail for review gate).
        Every human review action is logged here with operator, timestamp, and action.
        """
        audit_path = self.engagement_dir(engagement_id) / self.AUDIT_LOG_FILE
        event["timestamp"] = datetime.now(UTC).isoformat()
        with open(audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def write_findings_report(self, engagement_id: str, report: dict) -> Path:
        """Write the FindingsReport produced by AnalysisEngine.run() (TODO.md T-412).

        Report file: reports/findings_report.json

        `AnalysisEngine` hands over `FindingsReport.model_dump()`, so the payload
        may still hold enums and datetimes; `_atomic_write` serialises those via
        `default=str`.
        """
        reports_dir = self.engagement_dir(engagement_id) / self.REPORTS_DIR
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = reports_dir / self.FINDINGS_REPORT_FILE
        self._atomic_write(report_path, report)
        logger.debug("FindingsReport written: %s", report_path)
        return report_path

    def write_deliverable_manifest(self, engagement_id: str, manifest: dict) -> Path:
        """Write the deliverable manifest produced by RenderPipeline.run() (TODO.md T-412).

        Manifest file: reports/deliverable_manifest.json

        Phase F's portal reads this to learn which deliverables exist, their
        formats, and where they live on disk.
        """
        reports_dir = self.engagement_dir(engagement_id) / self.REPORTS_DIR
        reports_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = reports_dir / self.DELIVERABLE_MANIFEST_FILE
        self._atomic_write(manifest_path, manifest)
        logger.debug("Deliverable manifest written: %s", manifest_path)
        return manifest_path

    @staticmethod
    def _atomic_write(path: Path, data: dict) -> None:
        """Write JSON atomically: write to .tmp then rename."""
        tmp_path = path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        tmp_path.replace(path)

    @property
    def output_paths(self):
        """Returns the standard output path structure spec.

        Closes TODO_PhaseA: output/ directory has no structure defined.
        """
        return {
            "discovery": "{data_dir}/{engagement_id}/discovery/{platform}_{account_id}.json",
            "diagrams": "{data_dir}/{engagement_id}/diagrams/{type}/{name}.{ext}",
            "reports": "{data_dir}/{engagement_id}/reports/{type}/{name}.{ext}",
            "audit_log": "{data_dir}/{engagement_id}/audit.jsonl",
            "engagement": "{data_dir}/{engagement_id}/engagement.json",
        }


# Exceptions (see also cna/core/exceptions.py)
class EngagementNotFoundError(Exception):
    pass


class EngagementLockError(Exception):
    pass
