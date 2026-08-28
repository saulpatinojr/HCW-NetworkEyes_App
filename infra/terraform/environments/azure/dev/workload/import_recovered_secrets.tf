# One-time state-recovery imports (2026-08-28 dev rebuild).
#
# The dev Terraform state was destroyed with the tfstate storage account in the
# July sandbox sweep. On the rebuild, the azurerm provider's
# recover_soft_deleted_key_vaults recovered cna-dev-scus-kv2 — including the
# four secrets below, which came back with their pre-sweep versions. A fresh
# state cannot create them ("already exists ... needs to be imported"), and
# deleting them instead would wedge the names for the 90-day soft-delete
# retention, because this vault has purge protection enabled (see providers.tf).
#
# Import blocks are the codified fix: declarative, processed at plan time (so
# they work through 211's plan/apply flow), and ignored once the resource is in
# state, so they are safe to leave. They can be removed after the environment
# has had a clean apply. The version GUIDs are the recovered versions reported
# by the failed apply; Terraform updates each secret to the configured value in
# the same apply if it differs.

import {
  to = module.runtime.azurerm_key_vault_secret.database_url
  id = "https://cna-dev-scus-kv2.vault.azure.net/secrets/cna-database-url/37a4029c91b34d699d011ce73cffc7ac"
}

import {
  to = module.runtime.azurerm_key_vault_secret.nextauth_secret
  id = "https://cna-dev-scus-kv2.vault.azure.net/secrets/cna-nextauth-secret/d9efe7a64a344d868d326e9abe8fd201"
}

import {
  to = module.runtime.azurerm_key_vault_secret.entra_client_secret
  id = "https://cna-dev-scus-kv2.vault.azure.net/secrets/cna-entra-client-secret/42da9434358e4ddd946cd99ff7d1f12e"
}

import {
  to = module.runtime.azurerm_key_vault_secret.credential_encryption_key
  id = "https://cna-dev-scus-kv2.vault.azure.net/secrets/cna-credential-encryption-key/1ebad1e593c64f55a420bbfa3acdd8ce"
}
