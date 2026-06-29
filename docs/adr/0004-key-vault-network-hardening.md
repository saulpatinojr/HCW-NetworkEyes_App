# 0004 — Key Vault network hardening (private-endpoint-only target)

- **Status:** Accepted (2026-06-29) — target state; implementation tracked by a
  follow-up issue
- **Deciders:** CNA platform
- **Related:** best-practice review (this PR); follow-up issue #102 "Key Vault:
  disable public network access (PE-only) with a VNet-joined deploy agent"

## Context

The workload Key Vault (`infra/terraform/providers/azure/identity/main.tf`) is created
with:

```hcl
public_network_access_enabled = true
network_acls {
  bypass         = "AzureServices"
  default_action = "Allow"   # <- least secure
}
```

It already has a **private endpoint** (in the security module) and uses RBAC
authorization. But `default_action = "Allow"` means the vault accepts data-plane
traffic from any network, which contradicts the Microsoft Key Vault security baseline
and the Azure Verified Module default (`default_action = "Deny"`).

The reason it was left open: **Terraform writes and reads KV secrets over the data
plane** during `apply` (the `runtime` module's `azurerm_key_vault_secret` resources)
and during `plan` refresh (drift workflows). The CI runs on **GitHub-hosted runners**,
which:

- are **not** on Microsoft's Key Vault *trusted services* list (so `bypass =
  AzureServices` does not admit them), and
- have **ephemeral public egress IPs**, so pinning them in `network_acls.ip_rules`
  via Terraform causes **perpetual drift** and breaks any run whose runner IP isn't
  allow-listed.

## Decision

**Target best-practice posture:** disable public network access and use **private
endpoints only** (`public_network_access_enabled = false`, `default_action = "Deny"`),
with secret provisioning performed by a **VNet-joined deploy agent** (a self-hosted
GitHub runner in the workload VNet, or an in-VNet job) so the data-plane writes reach
the vault over the private endpoint / Microsoft backbone.

**This PR does not flip the setting.** Doing so blindly would break every deploy and
drift job (data-plane secret read/write from public runners would be denied), and the
change is only verifiable against a live environment. It is therefore deferred to a
dedicated, testable follow-up issue, with this ADR recording the decision.

## Consequences

- **Good (when implemented):** the vault is unreachable from the public internet;
  all data-plane traffic flows over Private Link. Matches the KV security baseline's
  most-restrictive tier.
- **Cost / effort:** requires standing up a VNet-joined deploy agent (or moving secret
  creation into an in-VNet job). This is the real work captured by the follow-up issue.
- **Interim posture:** the vault keeps `default_action = "Allow"` until the VNet agent
  exists. RBAC authorization still gates every data-plane operation, so access is not
  open — only the *network* is.

## Alternatives considered

- **`default_action = Deny` + allow-list the ephemeral runner IP in Terraform** — the
  approach originally sketched; rejected: ephemeral IPs cause perpetual drift and
  break runs whose IP isn't listed.
- **`default_action = Deny` + imperative `az keyvault network-rule add/remove` window
  around KV ops, with `lifecycle { ignore_changes = [network_acls] }`** — a valid
  *interim workaround* that hardens without a VNet agent, but it still uses public
  egress, touches three workflows (211 apply, 350/360 drift), and is only verifiable on
  a live run. Documented here as the fallback if PE-only is not yet feasible.
- **Stable egress (NAT gateway / fixed IP) allow-listed in `ip_rules`** — works only
  once a stable deploy egress exists; folded into the follow-up issue's options.
