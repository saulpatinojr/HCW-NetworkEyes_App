# 0005 — Container image pull: Docker Hub now, ACR + managed identity later

- **Status:** Accepted (2026-06-29) — interim decision; target state tracked by a
  follow-up issue
- **Deciders:** CNA platform
- **Related:** best-practice review (this PR); follow-up issue #103 "Adopt ACR +
  managed identity for Container Apps image pull"

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

## Decision

**Keep Docker Hub + credentials for now; adopt ACR + managed identity as a follow-up.**

Switching registries is an architecture change (provision ACR, push images to it in
the build workflow, grant `AcrPull`, update Container App registry config, and
optionally add an ACR private endpoint + DNS). It is out of scope for the current
issue-resolution + best-practice PR and warrants its own change with its own
validation.

## Consequences

- **Good (now):** no change risk to the working deploy; this PR stays scoped.
- **Debt:** long-lived Docker Hub credentials remain in GitHub secrets and as a
  Container App registry secret — a standing credential to rotate and protect.
- **Target (follow-up):** ACR + `AcrPull` via managed identity eliminates the
  registry password, aligns image pull with the platform's identity model, and allows
  private-endpoint image traffic.

## Alternatives considered

- **Switch to ACR + managed identity in this PR** — rejected: too large and
  untestable here; couples a registry migration with unrelated fixes.
- **Keep Docker Hub but move to a managed-identity/OIDC pull** — not supported for
  Docker Hub; managed-identity pull is an ACR capability.
