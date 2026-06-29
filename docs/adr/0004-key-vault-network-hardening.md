# 0004 — Key Vault network hardening (deny-by-default; PE-only deferred)

- **Status:** Accepted (2026-06-29); **deny-by-default implemented** 2026-06-29
  (issue #102). Literal public-access-disabled (PE-only) remains a separate later item.
- **Deciders:** CNA platform
- **Related:** issue #102; SME review (2026-06-29)

## Context

The workload Key Vault (`infra/terraform/providers/azure/identity/main.tf`) holds
high-value material: the database connection string, the Auth.js signing secret, the
Entra OAuth client secret, and the AES-256 credential-encryption key. It already has a
**private endpoint** (security module) and uses **RBAC authorization**
(`rbac_authorization_enabled = true`), so a data-plane operation always requires an
Entra token holding a Key Vault role — regardless of network position.

It was nonetheless created with `network_acls.default_action = "Allow"`, i.e. the
data-plane *endpoint* was reachable from any network. RBAC means this did not expose
secret **values**, but it left a public network attack surface (leaked-token replay
reachable from anywhere, exposure of the auth/throttling layer) and failed the
Microsoft Key Vault security baseline (NS-2) and Well-Architected guidance, both of
which call for `default_action = Deny` when a private endpoint exists.

**Correcting the original premise.** An earlier draft of this ADR (and issue #102)
claimed the flip was blocked because CI ran on *GitHub-hosted runners with ephemeral
IPs*. That is **not the case** — all workflows run `runs-on: self-hosted`, and
`211-deploy-azure-split.yml` already implements an imperative "open a deny-by-default
firewall window, add the runner IP, remove it afterwards" pattern around the Terraform
apply (the data-plane secret writes in the `runtime` module).

The real defect was a **Terraform/runtime conflict**: the module declared
`default_action = "Allow"` with no `lifecycle.ignore_changes`, so every `terraform
apply` reverted the imperatively-set `Deny` back to `Allow`. The 211 hardening was
therefore a no-op between deploys, and the 350/360 drift jobs would perpetually try to
reconcile it.

## Decision

Make **deny-by-default** the Terraform-managed steady state and stop the two layers
from fighting:

- `infra/terraform/providers/azure/identity/main.tf`: `network_acls.default_action =
  "Deny"` (keep `bypass = "AzureServices"` for the Front Door cert path), and
  `lifecycle { ignore_changes = [network_acls[0].ip_rules] }` so the transient runner
  IP added by the workflows does not show as drift. `default_action`/`bypass` remain
  Terraform-managed and drift-detected.
- `public_network_access_enabled` **stays `true`**: the self-hosted runner reaches the
  vault over the *public* endpoint through the temporary IP allow-rule, so literal
  "Disabled" is mutually exclusive with the public-runner window. The runner today is an
  external VPS, not VNet-joined.
- Drift workflows `350-drift-dev.yml` / `360-drift-prod.yml` gained the same
  "add runner IP before the workload plan / remove on `always()`" steps (they refresh
  KV secret resources over the data plane and previously had no window).

The Container Apps are unaffected — they reach the vault over the existing private
endpoint via the user-assigned managed identity, independent of `default_action`.

**Deferred (separate, later):** literal `public_network_access = Disabled` (true
PE-only), which requires moving the deploy runner **into the workload VNet** (self-hosted
runner on a VNet-joined VM/VMSS, or an in-VNet secret-provisioning job). Tracked as a
follow-up under #102.

## Consequences

- **Good:** the vault denies public traffic by default in steady state; the only public
  reach is the brief, self-removing runner window during deploy/drift. Satisfies the
  KV firewall baseline (CKV_AZURE_109). Fixes the perpetual-drift / no-op bug.
- **Residual:** `public_network_access` is still `Enabled` (CKV_AZURE_189 skip retained)
  because the runner is not VNet-joined. The window is short and the IP is removed on
  `always()`, but it is a real (if small) exposure until the VNet-runner work lands.
- **Verification (live):** after a 211 dev run, `az keyvault show` reports
  `defaultAction=Deny` with the runner IP removed; a 350 dev run reads secrets during
  plan and reports **no** `network_acls` drift; a secret read from an unlisted public IP
  returns `Forbidden`.

## Alternatives considered

- **`default_action = Deny` + allow-list a runner IP *in Terraform*** — rejected:
  even with self-hosted runners the IP can rotate, and a TF-managed `ip_rules` fights
  the imperative window. `ignore_changes` on `ip_rules` is the correct split.
- **PE-only now (public access Disabled) + VNet-joined runner** — the true
  best-practice end-state; deferred because the runner is currently an external VPS and
  the move is non-trivial infra work, separately testable.
