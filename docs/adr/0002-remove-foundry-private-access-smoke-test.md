# 0002 — Remove the Foundry private-access smoke test

- **Status:** Accepted (2026-06-29)
- **Deciders:** CNA platform
- **Related:** issues #98, #99; [ADR-0001](0001-remove-anthropic-foundry-claude-path.md)

## Context

`scripts/ci/validate_foundry_private_access.sh` ran a Container Apps **Job** inside
the VNet after each deploy to (a) confirm the Foundry host resolved through the
private endpoint and (b) make a live inference call to the `/anthropic/v1/messages`
endpoint using a user-assigned managed identity (UAI) token.

Two problems made it pure friction:

1. **#98 — wrong target.** It called the Anthropic endpoint, which has no model
   behind it (see [ADR-0001](0001-remove-anthropic-foundry-claude-path.md)). Even a
   perfect run could never get a 200.
2. **#99 — UAI token HTTP 500.** The job's identity REST endpoint returned `500
   ("unexpected error fetching AAD token")` on every attempt. Evidence pointed at a
   Container Apps **Consumption-profile Job** not surfacing the user-assigned identity
   to the running execution the way a Container **App** does — i.e. a Job-vs-App
   identity-binding gap, not an RBAC problem (RBAC would be 403, and the UAI did hold
   `Cognitive Services User`).

The step was already `continue-on-error: true`, so it no longer blocked the deploy —
but it remained dead weight that always failed.

## Decision

**Delete the smoke test entirely** — the script and its workflow step — rather than
repoint it at Azure OpenAI.

- Removed `scripts/ci/validate_foundry_private_access.sh`.
- Removed the "Validate Foundry private DNS and managed identity inference" step from
  `211-deploy-azure-split.yml`, the now-orphan `managed_identity_client_id` export,
  and the `FOUNDRY_PRIVATE_ACCESS_VALIDATION` evidence wiring (script + manifest keys).

## Consequences

- **Good:** #98 and #99 are resolved at the source. The UAI token-500 only ever
  occurred inside this Job; with the Job gone, it cannot recur. The deploy no longer
  carries an always-failing step.
- **Coverage note:** the app's own managed-identity calls (Key Vault references, Azure
  OpenAI via `DefaultAzureCredential`) run on Container **Apps** with a system-assigned
  identity and are unaffected by the Job-specific binding gap. Private DNS resolution
  of the shared Foundry private endpoint is still exercised by normal app traffic.
- **Trade-off:** no dedicated post-deploy assertion that inference works end-to-end.
  Acceptable — the application exercises the inference path in normal use, and a
  lightweight Azure OpenAI reachability check can be added later if desired.

## Alternatives considered

- **Repoint to Azure OpenAI `/openai/v1` and fix the UAI binding** (match the web
  app's dual SystemAssigned+UserAssigned identity) — rejected for now: more code to
  carry, still Job-specific identity complexity, and the value (a synthetic check) is
  low versus the app's real traffic.
- **Leave it non-blocking** — rejected: dead code that always fails is noise.
