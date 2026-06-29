# 0005 — Container image pull: ACR + managed identity (replacing Docker Hub)

- **Status:** Accepted (2026-06-29). **Foundation implemented** 2026-06-29 (ACR +
  AcrPull, non-breaking). **Pipeline cutover pending** a topology decision (below).
- **Deciders:** CNA platform
- **Related:** issue #103; SME review (2026-06-29)

## Context

The Container Apps pull their images from **Docker Hub** using a registry
**username + password** (`container_registry_username` /
`container_registry_password`, sourced from `DOCKERHUB_NAMESPACE` /
`DOCKERHUB_TOKEN`). The same Docker Hub credentials are also injected into the
Container Apps as a registry secret.

Azure's recommended pattern is **Azure Container Registry (ACR) with managed-identity
pull** (`AcrPull` role on the app's identity), which removes long-lived registry
credentials entirely and keeps image traffic on the Azure backbone (optionally via a
private endpoint), consistent with the rest of the platform's managed-identity posture.

Note: the Docker Hub credential is an **organization-level** PAT (broader blast
radius than a personal token), which strengthens the case for removing it.

## Decision

**Adopt ACR + managed-identity pull**, landed in two stages so the atomic,
live-only-verifiable pipeline switch is isolated:

**Stage 1 — Foundation (implemented).** New `providers/azure/registry` module
(`azurerm_container_registry`, SKU **Basic**, `admin_enabled = false`, public
endpoint) wired into dev + prod workload, with **`AcrPull`** granted to the three
app system identities and the UAI (for the migration/probe Jobs). Docker Hub remains
the active pull path, so this is non-breaking. The registry login server is exposed
as a workload output.

**Stage 2 — Pipeline cutover (pending).** Atomic switch: compute `registry` block to
managed-identity pull (drop `container-registry-password`), `200-build-images.yml`
gains Azure OIDC + `az acr login` and pushes to ACR, the build manifest + `211`
image defaults + migration/probe-job registry blocks (`--registry-identity`) move to
ACR refs, the deploy/build identity gains **`AcrPush`**, the egress firewall swaps the
Docker Hub FQDNs for the ACR host, and the `DOCKERHUB_TOKEN` org PAT is removed.

### Open decision blocking Stage 2 — registry topology

Today **one** Docker Hub namespace serves **both** dev and prod (one image set). The
foundation created a **per-environment** ACR. Stage 2 must pick:

- **Per-environment ACR** (as built): the build pushes to each environment's ACR;
  prod pulls only from the prod ACR (stronger isolation). Requires the build workflow
  to target the right ACR per environment and `AcrPush` scoped per registry.
- **Single shared ACR** (e.g. in a shared/platform RG): faithfully mirrors the current
  one-image-source model; both environments pull from it. Simpler build, but dev and
  prod share a registry.

Plus the first-deploy ordering (ACR must exist before the first push): resolve via the
repo's existing pattern — the build workflow `az acr create`s idempotently and
Terraform **adopts** it with an `import` block (mirrors the `github_actions_variable`
adoption already in the workload root).

## Consequences

- **Stage 1 (now):** ACR exists with AcrPull wired; no change to the running deploy.
- **Stage 2 (when cut over):** the org Docker Hub PAT is eliminated end-to-end; image
  pull aligns with the platform's managed-identity model; pull traffic is intra-Azure.
- **Deferred:** Premium ACR + private endpoint (image traffic fully off the public
  endpoint) — a later hardening step, mirroring the KV PE work in ADR-0004.

## Alternatives considered

- **Keep Docker Hub** — rejected: an unrotated org-level credential, the last
  username/password path on an otherwise managed-identity platform.
- **Keep Docker Hub but move to managed-identity/OIDC pull** — not possible; MI pull is
  an ACR capability.
