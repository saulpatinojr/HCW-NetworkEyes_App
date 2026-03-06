# CNA Platform — Documentation Index

> Last updated: 2026-03-05 | Version: 1.1.0

---

## Start Here

| Document | Purpose |
|---|---|
| [`../README.md`](../README.md) | Platform overview, quick start, CI/CD workflows, security summary |
| [`deployment-guide.md`](deployment-guide.md) | Step-by-step first deployment (local setup → cloud permissions → secrets → tag → first engagement) |
| [`architecture/deployment-map.md`](architecture/deployment-map.md) | **Deployment status map** — what is deployed vs pending, CNA vs CNA-client boundary, remote connection map |
| [`secrets-reference.md`](secrets-reference.md) | Every environment variable and GitHub Secret explained |
| [`secrets-architecture.md`](secrets-architecture.md) | Three-tier secrets model, Key Vault, SSM, OIDC, rotation policy |

---

## Architecture

| Document | Purpose |
|---|---|
| [`architecture/overview.md`](architecture/overview.md) | Five-engine platform overview, three core guarantees |
| [`architecture/repo-structure.md`](architecture/repo-structure.md) | Full directory tree with descriptions |
| [`architecture/discovery-engine.md`](architecture/discovery-engine.md) | AWS + Azure discovery flows, IAM/RBAC, checkpoint format, resume |
| [`architecture/ai-analysis-engine.md`](architecture/ai-analysis-engine.md) | Finding rules, MCP recommendation engine, DD-003 separation boundary |
| [`architecture/report-generation.md`](architecture/report-generation.md) | Review gate, PDF/PPTX deliverables, JA translation protocol |
| [`architecture/delivery-portal.md`](architecture/delivery-portal.md) | Publish flow, S3/Blob, pre-signed URLs, retention |

---

## Design Decisions

| Document | Purpose |
|---|---|
| [`design/design-decisions.md`](design/design-decisions.md) | All 19 design decisions (DD-001 – DD-019) with status |

---

## CI/CD & Operations

| Document | Purpose |
|---|---|
| [`workflows-guide.md`](workflows-guide.md) | ci.yml, release.yml, cd-publish.yml — triggers, jobs, inputs |
| [`cicd-iac-report.md`](cicd-iac-report.md) | 18-gap CI/CD + IaC audit report |
| [`policies/secret-rotation-runbook.md`](policies/secret-rotation-runbook.md) | Step-by-step secret rotation for all platform secrets |

---

## Client Delivery

| Document | Purpose |
|---|---|
| [`client-packet/welcome-packet.md`](client-packet/welcome-packet.md) | Client-facing welcome and engagement overview |
| [`client-packet/environment-info-form.md`](client-packet/environment-info-form.md) | Pre-engagement environment questionnaire |
| [`client-packet/permission-grant-guide.md`](client-packet/permission-grant-guide.md) | Step-by-step guide for client to grant read-only access |

---

## Policies

| Document | Purpose |
|---|---|
| [`policies/data-handling-policy.md`](policies/data-handling-policy.md) | What is collected, stored, encrypted, retained, and deleted |
| [`policies/lz-scope-boundary.md`](policies/lz-scope-boundary.md) | Landing zone = Mermaid docs (not IaC) — client-facing explanation |
| [`policies/ja-translation-protocol.md`](policies/ja-translation-protocol.md) | JA report 4-step protocol, glossary, review gate |

---

## Development

| Document | Purpose |
|---|---|
| [`development/module-guide.md`](development/module-guide.md) | How to build and register a new assessment module |
| [`development/diagram-generation.md`](development/diagram-generation.md) | Diagram types and generation guide |
| [`phase-completion-log.md`](phase-completion-log.md) | Canonical record of all completed work (replaces root TODO files) |
