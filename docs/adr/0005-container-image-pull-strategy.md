# 0005 — Container image pull: keep Docker Hub (ACR evaluated and declined)

- **Status:** Accepted (2026-06-29). ACR + managed-identity pull was evaluated under
  #103 and **declined** — Docker Hub is retained.
- **Deciders:** CNA platform
- **Related:** issue #103 (closed, won't-do); SME review (2026-06-29)

## Context

The Container Apps pull their images from **Docker Hub** using a registry
**username + password** — `container_registry_username` / `container_registry_password`,
sourced from the `DOCKERHUB_NAMESPACE` variable and an **organization-level**
`DOCKERHUB_TOKEN` PAT. That credential is also materialized as a Container App
registry secret on the three apps and passed to the migration/probe Jobs.

Azure's recommended pattern is **Azure Container Registry (ACR) with managed-identity
pull** (`AcrPull` on the app identity), which removes the registry credential entirely
and keeps image traffic on the Azure backbone, consistent with the rest of the
platform's managed-identity posture (Storage, Key Vault, Azure OpenAI, ARM are all
MI/OIDC).

An SME review assessed the switch. Its conclusion: the **only material benefit** is
removing the org-level PAT; everything else is consistency/polish. The change is an
**atomic, live-only-verifiable** pipeline cutover (build → push → pull → RBAC →
deploy) touching ~8 files, and adds an ACR (~$5/mo Basic).

## Decision

**Keep Docker Hub. Do not adopt ACR at this time.**

The applications are private, RBAC/OIDC gates every other access path, and the
Docker Hub PAT is an organization token that is managed and rotated. The residual
risk of one well-scoped registry credential is acceptable, and it does not justify an
atomic cutover of the build/deploy pipeline (only verifiable on a live run) plus the
ongoing ACR cost.

A short-lived `providers/azure/registry` foundation (an idle ACR + `AcrPull`) was
prototyped and then **reverted** (PR #106 closed unmerged) — an unused registry is
pure cost/clutter without the cutover.

## Consequences

- **Now:** no change; the working Docker Hub deploy is untouched; no new cost.
- **Standing debt (accepted):** the org-level `DOCKERHUB_TOKEN` remains a long-lived
  credential — it must be kept rotated and access-scoped. It is the only
  username/password path left on an otherwise managed-identity platform.

## Revisit if

- A **private-endpoint image path** (image traffic fully off the public internet) or a
  stricter **supply-chain** posture becomes a requirement, or
- Docker Hub rate limits / availability / third-party risk start to bite, or
- the org PAT becomes hard to govern.

At that point, reopen with the SME's plan: ACR (Basic now, Premium + private endpoint
if needed), `AcrPull` to the app identities + UAI, `AcrPush` to the build identity,
build pushes to ACR via `az acr login`, and removal of the `DOCKERHUB_TOKEN`.

## Alternatives considered

- **Adopt ACR + managed identity now** — declined: the only real gain (removing the
  org PAT) does not outweigh an atomic, unverifiable-locally pipeline cutover and the
  added cost, given the apps are private and RBAC/OIDC already gate every other path.
- **Keep Docker Hub but move to managed-identity/OIDC pull** — not possible;
  managed-identity pull is an ACR capability, not a Docker Hub one.
