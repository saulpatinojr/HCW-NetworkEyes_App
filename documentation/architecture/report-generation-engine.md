# CNA Platform — Report Generation Engine

> Version: 1.0.0 | Status: ACTIVE | Date: 2026-03-05

---

## Overview

The report generation engine consumes the `FindingsReport` written by the
analysis engine and produces all client-facing deliverables. It is the last
code-heavy component before the delivery portal (see `delivery-portal.md`).

---

## Data Flow

```
EngagementStore
  findings/report.json          ─┬
  (review_complete must = True)  │
                                 ▼
                        RenderPipeline.run()
                         │
                         ├─ DD-009 review gate check  ← raises ReviewGateError
                         │
                         ├─ HtmlPreviewRenderer       → {id}_preview.html
                         ├─ ExecutiveReportRenderer   → {id}_executive.pdf
                         ├─ TechnicalReportRenderer   → {id}_technical.pdf
                         ├─ PresentationDeckBuilder   → {id}_deck.pptx
                         ├─ RegionalReportRenderer EN → {id}_regional_en.pdf
                         └─ RegionalReportRenderer JA → {id}_regional_ja.pdf
                              │
                              └─ DD-015 JA gate check ← raises JaReviewGateError
                         │
                         ▼
                        DeliverableManifest
                        EngagementStore.write_deliverable_manifest()
                        engagements/{id}/deliverables/manifest.json
                         │
                         ▼
                        Delivery Portal reads manifest.json
```

---

## Design Contracts (All Enforced in Code)

| Contract | Where Enforced | What Happens on Violation |
|---|---|---|
| DD-009: `review_complete=True` required before any rendering | `RenderPipeline._enforce_review_gate()` — first check before any file creation | `ReviewGateError` raised — zero files written |
| DD-015: JA reports require native speaker sign-off | `RenderPipeline._enforce_ja_gate()` + second check in `RegionalReportRenderer.render()` | `JaReviewGateError` raised — JA file never written |
| DD-013: Deliverable staleness detection | `DeliverableManifest.checksum()` stored per record | Delivery portal compares checksum to current report; marks stale if different |
| DD-017: Output files are timestamp-stamped | `RenderPipeline._filename()` — all outputs include ISO 8601 timestamp | Two renders always produce distinct filenames with full traceability |

---

## Output Formats

| Format | Renderer | Template | PDF Toolchain |
|---|---|---|---|
| HTML Preview | `HtmlPreviewRenderer` | `html_preview.j2` | None — pure Jinja2 |
| Executive PDF | `ExecutiveReportRenderer` | `executive_report.j2` | WeasyPrint (optional) |
| Technical PDF | `TechnicalReportRenderer` | `technical_report.j2` | WeasyPrint (optional) |
| Regional EN | `RegionalReportRenderer(lang='en')` | `regional_report_en.j2` | WeasyPrint (optional) |
| Regional JA | `RegionalReportRenderer(lang='ja')` | `regional_report_ja.j2` | WeasyPrint (optional) |
| PPTX Deck | `PresentationDeckBuilder` | — (python-pptx) | None |

**Graceful degradation:** If WeasyPrint or python-pptx is not installed, the
renderer logs a warning and skips that format. HTML is always written. No
renderer raises on missing optional dependencies.

---

## PPTX Deck Structure (10 Sections)

1. Cover — engagement ID, date, author
2. Engagement Overview — scope, platforms
3. Methodology — discovery approach, data handling
4. Executive Summary — finding counts by severity
5. Critical Findings — one slide per CRITICAL (max 10)
6. High Findings — one slide per HIGH (max 10)
7. Key Recommendations — top 5 prioritised by severity
8. Architecture Diagrams — placeholder linking diagram engine output
9. Remediation Roadmap — 0–30 / 30–90 / 90–180 day buckets
10. Appendix — full finding catalog table

---

## CLI Usage

```bash
# Full render (requires review_complete=True)
cna report generate --engagement-id acme-20260305-a3f2

# HTML only — no PDF toolchain needed
cna report generate --engagement-id acme-20260305-a3f2 --skip-pdf

# Include JA regional report (requires native speaker sign-off)
cna report generate \
  --engagement-id acme-20260305-a3f2 \
  --regional-ja --ja-review-complete

# Pre-review HTML preview (does NOT require review_complete=True)
cna report preview --engagement-id acme-20260305-a3f2

# Mark findings reviewed (enables cna report generate)
cna review complete --engagement-id acme-20260305-a3f2
```

---

## Review Workflow

```
cna analyze → FindingsReport (review_complete=False)
     │
     ▼
cna report preview   ← inspect findings before sign-off
     │
     ▼
Manual review of findings/report.json
     │
     ▼
cna review complete  ← sets review_complete=True, stamps reviewer + timestamp
     │
     ▼
cna report generate  ← full PDF + PPTX + regional output
     │
     ▼
cna publish          ← delivery portal upload
```
