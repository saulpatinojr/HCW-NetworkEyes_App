# Report Generation — Architecture

> Version: 1.0.0 | Status: Active | Date: 2026-03-05

---

## What This Engine Does

The report generation engine reads a completed `FindingsReport` from the EngagementStore
and produces all delivery artifacts: executive PDF, PPTX deck, regional EN report,
and (if enabled) regional JA report. It cannot run until `review_complete=True` is
set in the engagement state (DD-009 human review gate).

---

## Artifacts Produced

| Artifact | Format | Audience | Gate |
|---|---|---|---|
| Executive Report | PDF | Client executive | `review_complete=True` |
| PPTX Deck | PPTX | Client executive | `review_complete=True` |
| Regional Report (EN) | PDF | Client technical team | `review_complete=True` |
| Regional Report (JA) | PDF | Client technical team (Japan) | `ja_review_complete=True` |

---

## Output Path Structure

```
engagements/{engagement_id}/reports/
  executive/
    {engagement_id}_executive_report_{ISO_TIMESTAMP}.pdf
    {engagement_id}_executive_deck_{ISO_TIMESTAMP}.pptx
  regional/
    {engagement_id}_regional_report_en_{ISO_TIMESTAMP}.pdf
    {engagement_id}_regional_report_ja_{ISO_TIMESTAMP}.pdf
```

ISO timestamps in filenames implement DD-017: no ambiguity between report versions.

---

## Jinja2 Templates

| Template | Purpose |
|---|---|
| `executive_summary.j2` | 10-section executive report (Cover, Findings Summary, Top 5, Diagrams, Framework Alignment, Scope Notice) |
| `finding_detail.j2` | Per-finding detail page (observed state, evidence, severity, framework mapping, review status) |

All template variables are validated as non-null before rendering. The report engine
never renders with missing fields — it raises `ReportGenerationError` instead.

---

## Review Gate Enforcement (DD-009)

```python
# cna/core/persistence.py — enforced at report engine startup
if not engagement.review_complete:
    raise ReviewGateError(
        f"Engagement {engagement_id} has not been reviewed. "
        "Run: cna review complete --engagement-id {engagement_id}"
    )
```

The gate is a hard block — not a warning. Every report run against an unreviewed
engagement fails with a clear remediation instruction.

---

## JA Translation Gate (DD-015)

JA report generation is blocked by `ja_review_complete=False` in the same way.
The 4-step JA translation protocol is documented in
`documentation/policies/ja-translation-protocol.md`.
