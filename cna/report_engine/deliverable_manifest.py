"""Phase E — Deliverable Manifest.

Records every output file produced by the render pipeline for an engagement.
Written to EngagementStore at the end of every render run.
Consumed by Phase F delivery portal to build the download inventory.

DD-013: Deliverable staleness detection.
  Each record stores the findings_report checksum at render time.
  Phase F compares this checksum against the current report; if different,
  the portal marks the deliverable as stale and prompts a re-render.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class DeliverableRecord:
    label: str  # human-readable: "Executive Report (PDF)"
    path: str  # absolute path to output file
    format: str  # "pdf", "html", "pptx"
    lang: str  # "en", "ja"
    rendered_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    findings_checksum: str | None = None  # SHA-256 of FindingsReport JSON at render time
    size_bytes: int | None = None
    # C4 audience tag (set when this record came from the diagram pipeline).
    # One of: "executive", "architect", "engineer", or None for non-diagram
    # artefacts. See cna.diagram_engine.c4_layering.AUDIENCE_BY_LAYER.
    audience: str | None = None

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "path": self.path,
            "format": self.format,
            "lang": self.lang,
            "rendered_at": self.rendered_at,
            "findings_checksum": self.findings_checksum,
            "size_bytes": self.size_bytes,
            "audience": self.audience,
        }


@dataclass
class DeliverableManifest:
    engagement_id: str
    records: list[DeliverableRecord] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def add(self, record: DeliverableRecord) -> None:
        """Add a rendered file record. Populates size_bytes if file exists."""
        path = Path(record.path)
        if path.exists():
            record.size_bytes = path.stat().st_size
        self.records.append(record)

    def to_dict(self) -> dict:
        return {
            "engagement_id": self.engagement_id,
            "created_at": self.created_at,
            "total_deliverables": len(self.records),
            "records": [r.to_dict() for r in self.records],
        }

    @classmethod
    def checksum(cls, report_json: str) -> str:
        """SHA-256 of the FindingsReport JSON — used for staleness detection (DD-013)."""
        return hashlib.sha256(report_json.encode()).hexdigest()
