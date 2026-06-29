# 0003 — Manage the NextAuth redirect URI in bootstrap, not the deploy

- **Status:** Accepted (2026-06-29)
- **Deciders:** CNA platform
- **Related:** issue #101

## Context

The deploy workflow had a "Sync Entra app web URLs" step that read the Front Door
host and ran `az ad app show/update --id "$AZURE_CLIENT_ID"` to set the NextAuth
redirect URI. It failed the job with `Insufficient privileges`, and was masked with
`continue-on-error: true`. Two defects:

1. **Wrong object.** `AZURE_CLIENT_ID` is the **deploy service principal's** client
   id, so the step edited the deploy identity's own redirect URIs — not the NextAuth
   sign-in app (`CNA Assessment Tool`). Microsoft guidance is explicit:
   *"Always add redirect URIs to the application object only. Never add redirect URI
   values to a service principal"* — they can be wiped on the next app↔SP sync.
   (learn.microsoft.com/entra/identity-platform/reply-url)
2. **Missing privilege by design.** The deploy SPs (Main/Dev/Prod) are least-privilege
   and were intentionally granted **no** Microsoft Graph app-management rights. Azure's
   Zero-Trust app-registration guidance says to keep automation privileges minimal and
   app owners few. Granting the deploy SP `Application.ReadWrite.OwnedBy` would expand
   the blast radius of a compromised deploy identity.

Separately, the Front Door hostname is **stable per environment**, so the redirect URI
is effectively static — it does not need to be mutated on every deploy.

## Decision

**The Graph-capable bootstrap (`scripts/Initialize-CnaGitHubSecrets.ps1`) is the single
authoritative manager of the NextAuth redirect URI**, set on the **application object**
of the app it already owns. The deploy stays least-privilege and never calls Graph.

- Removed the `az ad app update` step from `211-deploy-azure-split.yml`. It is replaced
  by a privilege-free informational step that prints the exact redirect URI
  (`https://<frontdoor-host>/api/auth/callback/microsoft-entra-id`).
- The bootstrap already sets that URI on the NextAuth app (idempotent, on the
  application object, correct callback path). Terraform writes the real Front Door host
  to the `CNA_NEXTAUTH_URL` repository variable on first deploy; **re-running the
  bootstrap** after that deploy applies the redirect URI. Comments in the bootstrap now
  document this loop and point here.

## Consequences

- **Good:** correct object (application, not SP), correct app (NextAuth, not deploy
  identity), and the deploy identity keeps least privilege — no Graph rights added.
- **Good:** the deploy can no longer fail on this step (the replacement only echoes).
- **Trade-off / operational note:** on a greenfield deploy the redirect URI is set on
  the **second** bootstrap run (the first deploy must exist before the Front Door host
  is known). This is acceptable because the host is stable; once set it rarely changes.

## Alternatives considered

- **Grant the deploy SP Graph `Application.ReadWrite.OwnedBy` + make it an owner**, and
  fix the step to target the NextAuth app — rejected: expands the deploy identity's
  privilege against least-privilege intent.
- **Codify the NextAuth app + redirect URIs with the `azuread` Terraform provider** in
  a separate admin-run identity stack — viable longer-term and more declarative, but
  rejected for now to avoid importing/owning the app registration in Terraform state
  and to keep the change scoped. Revisit if app-registration config grows.
