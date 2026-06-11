"""Phase F — Portal Generator.

Builds a self-contained static HTML delivery portal for a single engagement.
The portal is a single `index.html` file that lists all deliverables from
the DeliverableManifest with download links, staleness badges, and metadata.

Design:
  - Zero JavaScript dependencies — pure HTML + inline CSS
  - Staleness badge: shown when deliverable checksum != current FindingsReport checksum
  - Download links are pre-signed URLs (S3) or SAS tokens (Azure Blob) injected at publish time
  - Portal file itself is uploaded alongside deliverables
  - Print-ready: @media print styles included

DD-013: Staleness detection.
  Each DeliverableRecord stores findings_checksum at render time.
  PortalGenerator computes current FindingsReport checksum and compares.
  Stale records get a visible warning badge in the portal HTML.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from jinja2 import BaseLoader, Environment

from cna.report_engine.deliverable_manifest import DeliverableManifest

logger = logging.getLogger("cna.portal.generator")

_BYTES_PER_UNIT = 1024

# MIME types per extension — must be set on every uploaded file (Gap #14)
CONTENT_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".html": "text/html; charset=utf-8",
    ".json": "application/json",
}


@dataclass
class PortalEntry:
    """A single deliverable entry in the portal download table."""

    label: str
    format: str
    lang: str
    size_bytes: int | None
    rendered_at: str
    download_url: str  # pre-signed URL or SAS token injected at publish
    is_stale: bool = False  # DD-013: True if rendered before last analysis run
    stale_reason: str = ""  # human-readable explanation


_PORTAL_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CNA Delivery Portal — {{ engagement_id }}</title>
<style>
  :root {
    --primary: #1565C0; --bg: #F5F5F5; --card: #FFFFFF;
    --text: #212121; --muted: #757575;
    --stale-bg: #FFF8E1; --stale-border: #F9A825;
    --ok-bg: #E8F5E9; --ok-border: #43A047;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', Arial, sans-serif; background: var(--bg);
         color: var(--text); padding: 2.5rem; }
  header { border-bottom: 3px solid var(--primary); padding-bottom: 1rem;
           margin-bottom: 2rem; }
  h1 { color: var(--primary); font-size: 1.8rem; }
  .meta { color: var(--muted); font-size: 0.85rem; margin-top: 0.25rem; }
  .expiry-banner { background: #FFF3E0; border-left: 4px solid #F57C00;
    padding: 0.75rem 1rem; border-radius: 4px; margin-bottom: 1.5rem;
    font-size: 0.9rem; }
  table { width: 100%; border-collapse: collapse; background: var(--card);
          border-radius: 8px; overflow: hidden;
          box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  th { background: var(--primary); color: white; padding: 0.75rem 1rem;
       text-align: left; font-size: 0.85rem; text-transform: uppercase;
       letter-spacing: 0.04em; }
  td { padding: 0.75rem 1rem; border-bottom: 1px solid #E0E0E0;
       font-size: 0.9rem; }
  tr:last-child td { border-bottom: none; }
  .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px;
           font-size: 0.75rem; font-weight: 700; text-transform: uppercase; }
  .badge-stale { background: var(--stale-bg); color: #795548;
                 border: 1px solid var(--stale-border); }
  .badge-current { background: var(--ok-bg); color: #2E7D32;
                   border: 1px solid var(--ok-border); }
  .badge-format-pdf  { background: #E3F2FD; color: #1565C0; }
  .badge-format-pptx { background: #F3E5F5; color: #6A1B9A; }
  .badge-format-html { background: #E8F5E9; color: #2E7D32; }
  a.dl-link { color: var(--primary); font-weight: 600;
              text-decoration: none; }
  a.dl-link:hover { text-decoration: underline; }
  .size { color: var(--muted); font-size: 0.8rem; }
  footer { margin-top: 2rem; font-size: 0.8rem; color: var(--muted);
           border-top: 1px solid #E0E0E0; padding-top: 1rem; }
  @media print { body { padding: 0; background: white; }
                 table { box-shadow: none; } }
</style>
</head>
<body>
<header>
  <h1>Cloud Network Assessment — Delivery Portal</h1>
  <p class="meta">Engagement: <strong>{{ engagement_id }}</strong>
    &nbsp;|&nbsp; Published: {{ published_at }}
    &nbsp;|&nbsp; Expires: {{ expires_at }}
  </p>
</header>

{% if has_stale %}
<div class="expiry-banner">
  ⚠ <strong>One or more deliverables are stale.</strong>
  The findings report was re-analyzed after these files were rendered.
  Re-run <code>cna report generate</code> and <code>cna publish</code> to refresh.
</div>
{% endif %}

<table>
  <thead>
    <tr>
      <th>Deliverable</th>
      <th>Format</th>
      <th>Language</th>
      <th>Rendered</th>
      <th>Size</th>
      <th>Status</th>
      <th>Download</th>
    </tr>
  </thead>
  <tbody>
    {% for entry in entries %}
    <tr>
      <td>{{ entry.label }}</td>
      <td><span class="badge badge-format-{{ entry.format }}">{{ entry.format | upper }}</span></td>
      <td>{{ entry.lang | upper }}</td>
      <td>{{ entry.rendered_at }}</td>
      <td class="size">{{ entry.size_bytes | filesizeformat if entry.size_bytes else '—' }}</td>
      <td>
        {% if entry.is_stale %}
        <span class="badge badge-stale" title="{{ entry.stale_reason }}">Stale</span>
        {% else %}
        <span class="badge badge-current">✓ Current</span>
        {% endif %}
      </td>
      <td><a class="dl-link" href="{{ entry.download_url }}">Download</a></td>
    </tr>
    {% endfor %}
  </tbody>
</table>

<footer>
  Prepared by Saul Patino Jr. — AWS SA Professional | Azure Solutions Architect Expert<br>
  Engagement data will be permanently deleted 90 days after delivery per data handling policy.
</footer>
</body>
</html>
"""


class PortalGenerator:
    """Generates the static portal index.html from a manifest + signed URLs."""

    def generate(
        self,
        manifest: DeliverableManifest,
        entries: list[PortalEntry],
        published_at: str,
        expires_at: str,
        output_path: Path,
    ) -> Path:
        """Render portal HTML and write to output_path. Returns path."""
        env = Environment(loader=BaseLoader(), autoescape=True)
        # Jinja2 filesizeformat filter
        env.filters["filesizeformat"] = self._filesizeformat
        template = env.from_string(_PORTAL_TEMPLATE)

        has_stale = any(e.is_stale for e in entries)
        html = template.render(
            engagement_id=manifest.engagement_id,
            published_at=published_at,
            expires_at=expires_at,
            entries=entries,
            has_stale=has_stale,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        logger.info(
            "Portal index written: %s (%d entries, stale=%s)", output_path, len(entries), has_stale
        )
        return output_path

    @staticmethod
    def _filesizeformat(value: int) -> str:
        """Human-readable file size."""
        for unit in ["B", "KB", "MB", "GB"]:
            if value < _BYTES_PER_UNIT:
                return f"{value:.0f} {unit}"
            value /= _BYTES_PER_UNIT
        return f"{value:.1f} TB"

    @staticmethod
    def build_entries(
        manifest: DeliverableManifest,
        signed_urls: dict[str, str],
        current_findings_checksum: str,
    ) -> list[PortalEntry]:
        """Build PortalEntry list from manifest records + signed URLs.

        signed_urls: mapping of record.path -> pre-signed URL or SAS token
        current_findings_checksum: SHA-256 of current FindingsReport JSON (DD-013)
        """
        entries = []
        for record in manifest.records:
            is_stale = (
                record.findings_checksum is not None
                and record.findings_checksum != current_findings_checksum
            )
            entries.append(
                PortalEntry(
                    label=record.label,
                    format=record.format,
                    lang=record.lang,
                    size_bytes=record.size_bytes,
                    rendered_at=record.rendered_at,
                    download_url=signed_urls.get(record.path, "#"),
                    is_stale=is_stale,
                    stale_reason=(
                        "Rendered before latest analysis run. Re-generate reports."
                        if is_stale
                        else ""
                    ),
                )
            )
        return entries
