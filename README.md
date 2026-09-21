# Cloud Network Assessment — this repository has moved

This was the project's original repository, the **Cloud Assessment Tool**, and until
2026-09-18 the **core** of the Cloud Network Assessment (CNA) platform. Its contents now live
in three repositories, each with a single owner and a clear boundary:

| Repository | Role | Audience |
|---|---|---|
| [`Work-Cloud_Network_Core`](https://github.com/saulpatinojr/Work-Cloud_Network_Core) | **Cloud Network Core** — the application code (`apps/`, `cna/`), the shared workers and services, the container-image builds and releases. Maintained centrally; every shared change lands here once and reaches both clouds through the images. | Internal |
| [`Work-Cloud_Network_Azure_Appliance`](https://github.com/saulpatinojr/Work-Cloud_Network_Azure_Appliance) | The **Azure** solution — Azure Terraform plus the deploy, update, drift and teardown workflows. | Customer-facing (Azure) |
| [`Work-Cloud_Network_AWS_Appliance`](https://github.com/saulpatinojr/Work-Cloud_Network_AWS_Appliance) | The **AWS** solution — AWS Terraform plus the same workflows. | Customer-facing (AWS) |

Customers consume the appliance that matches their cloud; nothing is deployed from the core.

## What happened to this repository

- **The full history was imported into the core.** `Work-Cloud_Network_Core` was created by
  merging this repository's `main` (last commit `5d3b914`) with its complete history, so every
  commit, `git blame` line and changelog reference resolves there. Nothing was rewritten.
- **The deployment layer had already left** for the two appliances (core `TODO.md` T-504 – T-508,
  2026-09-15).
- **This repository is archived.** It is kept read-only for its issues and pull requests, which
  the core's `CHANGELOG.md`, `REVIEW.md` and `CNA-0.90-updates.md` still link to by number. Do not
  open new issues or pull requests here — use the core for application work and the appliance for
  deployment work.
- **The Wiki** moved to the core's Wiki (core `REVIEW.md` → R-014).

The migration itself is recorded in the core's `TODO.md` → T-509 and `CHANGELOG.md` → Unreleased.
