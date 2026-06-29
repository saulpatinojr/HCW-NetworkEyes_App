data "azurerm_resource_group" "this" {
  name = "rg-${local.name_prefix}"
}

data "azurerm_virtual_network" "platform" {
  name                = "${local.name_prefix}-vnet"
  resource_group_name = data.azurerm_resource_group.this.name
}

data "azurerm_subnet" "container_apps_infra" {
  name                 = "${local.name_prefix}-snet-aca"
  virtual_network_name = data.azurerm_virtual_network.platform.name
  resource_group_name  = data.azurerm_resource_group.this.name
}

data "azurerm_subnet" "private_endpoints" {
  name                 = "${local.name_prefix}-snet-pe"
  virtual_network_name = data.azurerm_virtual_network.platform.name
  resource_group_name  = data.azurerm_resource_group.this.name
}

data "azurerm_subnet" "database" {
  name                 = "${local.name_prefix}-snet-db"
  virtual_network_name = data.azurerm_virtual_network.platform.name
  resource_group_name  = data.azurerm_resource_group.this.name
}

# Log Analytics workspace lives in the platform landing zone (created there so
# firewall/NSG/flow-log diagnostics stay in the same state as their resources).
# The workload reads it for Container App + app-level diagnostics.
data "azurerm_log_analytics_workspace" "platform" {
  name                = "${local.name_prefix}-log"
  resource_group_name = data.azurerm_resource_group.this.name
}

module "storage" {
  source              = "../../../../providers/azure/storage"
  resource_group_name = data.azurerm_resource_group.this.name
  location            = data.azurerm_resource_group.this.location
  name_prefix         = local.name_prefix
  tags                = local.tags

  # GZRS satisfies the curated Checkov geo-replication gate (CKV_AZURE_206).
  replication_type            = "GZRS"
  raw_artifact_retention_days = 30 # move to Cool after 30 days, auto-delete after 365
  deliverable_retention_days  = 90
}

module "identity" {
  source              = "../../../../providers/azure/identity"
  resource_group_name = data.azurerm_resource_group.this.name
  location            = data.azurerm_resource_group.this.location
  name_prefix         = local.name_prefix
  tenant_id           = var.tenant_id
  tags                = local.tags

  # Tenant policy requires purge protection on all Key Vaults (new and prod).
  # 90-day retention is paired with purge protection per Azure best practice.
  # NOTE: once purge protection is on, vault name is reserved for 90 days after
  # deletion — increment key_vault_name_suffix on next full teardown.
  key_vault_soft_delete_retention_days = 90
  key_vault_purge_protection_enabled   = true
  key_vault_name_suffix                = "2"
}

module "compute" {
  source                               = "../../../../providers/azure/compute"
  resource_group_name                  = data.azurerm_resource_group.this.name
  location                             = data.azurerm_resource_group.this.location
  name_prefix                          = local.name_prefix
  api_image                            = var.api_image
  worker_image                         = var.worker_image
  web_image                            = var.web_image
  container_apps_internal_only         = false
  container_apps_public_network_access = "Disabled"
  container_app_environment_workload_profiles = [{
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }]
  infrastructure_subnet_id             = data.azurerm_subnet.container_apps_infra.id
  web_ingress_ip_security_restrictions = var.web_ingress_ip_security_restrictions
  container_registry_username          = var.container_registry_username
  container_registry_password          = var.container_registry_password
  tags                                 = local.tags

  # FinOps: scale to zero when idle — no charge for idle Container Apps
  enable_scale_to_zero       = true
  log_analytics_workspace_id = data.azurerm_log_analytics_workspace.platform.id

  # ── Plain env vars injected at container start ──────────────────────────────
  api_env_vars = {
    CNA_STORAGE_ACCOUNT_NAME = module.storage.storage_account_name
  }

  worker_env_vars = {
    CNA_STORAGE_ACCOUNT_NAME = module.storage.storage_account_name
  }

  web_env_vars = {
    NEXTAUTH_URL                        = var.nextauth_url
    AUTH_TRUST_HOST                     = "true"
    AZURE_AD_TENANT_ID                  = var.tenant_id
    AZURE_AD_CLIENT_ID                  = var.entra_client_id
    CNA_API_INTERNAL_URL                = "http://${local.name_prefix}-ca-api"
    AZURE_STORAGE_ACCOUNT_NAME          = module.storage.storage_account_name
    AZURE_STORAGE_CONTAINER_ENGAGEMENTS = "raw-artifacts"
    CNA_AI_ENGINE_DEFAULT               = var.ai_engine_default
    AZURE_OPENAI_ENDPOINT               = var.azure_openai_endpoint
    AZURE_OPENAI_DEPLOYMENT             = var.azure_openai_deployment
    AZURE_OPENAI_API_VERSION            = var.azure_openai_api_version
    CNA_AZURE_MCP_ENDPOINT              = var.azure_mcp_endpoint
    CNA_AZURE_MCP_TRANSPORT             = var.azure_mcp_transport
    CNA_AWS_MCP_ENDPOINT                = var.aws_mcp_endpoint
    CNA_AWS_MCP_TRANSPORT               = var.aws_mcp_transport
    CNA_DRAWIO_MCP_URL                  = var.drawio_mcp_url
  }

  # ── Secret-backed env vars (reference Container App secrets by name) ─────────
  web_secret_env_vars = {
    DATABASE_URL              = "database-url"
    AUTH_SECRET               = "nextauth-secret" # Auth.js v5 canonical name (was NEXTAUTH_SECRET)
    AZURE_AD_CLIENT_SECRET    = "entra-client-secret"
    CREDENTIAL_ENCRYPTION_KEY = "credential-encryption-key"
  }

  # cna-api needs DATABASE_URL to read/write discovery jobs and findings.
  api_secret_env_vars = {
    DATABASE_URL = "database-url"
  }

  # ── Key Vault secret references ──────────────────────────────────────────────
  # Versionless URIs — Azure auto-refreshes the injected value within 30 minutes
  # when a new KV secret version is created (rotation, credential change, etc.).
  # The user-assigned managed identity (key_vault_reference_identity_id) must have
  # Key Vault Secrets User on the vault; Key Vault Secrets Officer covers this.
  container_app_kv_secrets = {
    "database-url"              = "${module.identity.key_vault_uri}secrets/cna-database-url"
    "nextauth-secret"           = "${module.identity.key_vault_uri}secrets/cna-nextauth-secret"
    "entra-client-secret"       = "${module.identity.key_vault_uri}secrets/cna-entra-client-secret"
    "credential-encryption-key" = "${module.identity.key_vault_uri}secrets/cna-credential-encryption-key"
  }
  key_vault_reference_identity_id = module.identity.managed_identity_id

  # depends_on ensures KV secrets (created by module.runtime) exist before
  # Container Apps reference them. Without this, a fresh deploy would race.
  depends_on = [module.runtime]
}

module "ai" {
  source              = "../../../../providers/azure/ai"
  resource_group_name = data.azurerm_resource_group.this.name
  location            = data.azurerm_resource_group.this.location
  name_prefix         = local.name_prefix
  tags                = local.tags

  environment      = var.environment
  foundry_location = var.foundry_location
  # DEV-ONLY suffix bump (-aif -> -aif2): the prior cna-dev-eus2-aif account is
  # soft-deleted and its name is reserved, which 409s on recreate. Bumping the
  # name sidesteps the soft-delete graveyard without a manual purge. See
  # docs/dev-deploy-workarounds.md — REVERT to "cna-dev-eus2-aif" once the ghost
  # is purged or its retention lapses. Prod (cna-prod-eus2-aif) is NOT bumped.
  foundry_account_name = "cna-dev-eus2-aif2"
  foundry_project_name = "cna-dev-eus2-aif2-proj"
}


module "runtime" {
  source                        = "../../../../providers/azure/runtime"
  resource_group_name           = data.azurerm_resource_group.this.name
  storage_account_id            = module.storage.storage_account_id
  key_vault_id                  = module.identity.key_vault_id
  managed_identity_principal_id = module.identity.managed_identity_principal_id
  database_url                  = module.database.connection_string
  nextauth_secret               = var.nextauth_secret
  entra_client_secret           = var.entra_client_secret
  credential_encryption_key     = var.credential_encryption_key
  secret_expiration_date        = var.secret_expiration_date
}

# ─── Container App RBAC ───────────────────────────────────────────────────────
# Each Container App uses its system-assigned managed identity via
# DefaultAzureCredential. All required role assignments are declared here so
# Terraform owns the full identity surface — no manual az role assignment calls.

# Storage: web uploads deliverables; api + worker read/write raw artifacts.
resource "azurerm_role_assignment" "web_storage_blob_data_contributor" {
  scope                = module.storage.storage_account_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = module.compute.web_principal_id
}

resource "azurerm_role_assignment" "api_storage_blob_data_contributor" {
  scope                = module.storage.storage_account_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = module.compute.api_principal_id
}

resource "azurerm_role_assignment" "worker_storage_blob_data_contributor" {
  scope                = module.storage.storage_account_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = module.compute.worker_principal_id
}

resource "azurerm_role_assignment" "web_foundry_user" {
  scope                = module.ai.foundry_account_id
  role_definition_name = "Cognitive Services User"
  principal_id         = module.compute.web_principal_id
}

resource "azurerm_role_assignment" "api_foundry_user" {
  scope                = module.ai.foundry_account_id
  role_definition_name = "Cognitive Services User"
  principal_id         = module.compute.api_principal_id
}

resource "azurerm_role_assignment" "uai_foundry_user" {
  scope                = module.ai.foundry_account_id
  role_definition_name = "Cognitive Services User"
  principal_id         = module.identity.managed_identity_principal_id
}


module "security" {
  frontdoor_certificate_pfx_path     = var.frontdoor_certificate_pfx_path
  frontdoor_certificate_pfx_password = var.frontdoor_certificate_pfx_password
  source                             = "../../../../providers/azure/security"
  resource_group_name                = data.azurerm_resource_group.this.name
  location                           = data.azurerm_resource_group.this.location
  name_prefix                        = local.name_prefix
  key_vault_id                       = module.identity.key_vault_id
  key_vault_name                     = module.identity.key_vault_name
  managed_identity_principal_id      = module.identity.managed_identity_principal_id
  managed_identity_id                = module.identity.managed_identity_id
  managed_identity_client_id         = module.identity.managed_identity_client_id
  api_container_app_id               = module.compute.api_id
  api_container_app_fqdn             = module.compute.api_fqdn
  web_container_app_id               = module.compute.web_id
  web_container_app_fqdn             = module.compute.web_fqdn
  container_app_environment_id       = module.compute.container_app_environment_id
  worker_container_app_id            = module.compute.worker_id
  frontdoor_private_link_enabled     = true
  virtual_network_id                 = data.azurerm_virtual_network.platform.id
  private_endpoint_subnet_id         = data.azurerm_subnet.private_endpoints.id
  storage_account_id                 = module.storage.storage_account_id
  storage_account_name               = module.storage.storage_account_name
  foundry_account_id                 = module.ai.foundry_account_id
}

# App-level diagnostics only. Firewall/NSG diagnostics and VNet flow logs are
# owned by the platform landing zone (where those resources live).
module "observability" {
  source                               = "../../../../providers/azure/observability"
  log_analytics_workspace_id           = data.azurerm_log_analytics_workspace.platform.id
  log_analytics_workspace_workspace_id = data.azurerm_log_analytics_workspace.platform.workspace_id
  log_analytics_workspace_location     = data.azurerm_log_analytics_workspace.platform.location
  diagnostic_setting_name_prefix       = local.name_prefix
  resource_group_name                  = data.azurerm_resource_group.this.name
  location                             = data.azurerm_resource_group.this.location
  tags                                 = local.tags

  diagnostic_targets = {
    frontdoor_profile          = module.security.frontdoor_profile_id
    container_apps_environment = module.compute.container_app_environment_id
    container_app_web          = module.compute.web_id
    container_app_api          = module.compute.api_id
    container_app_worker       = module.compute.worker_id
    key_vault                  = module.identity.key_vault_id
    storage_account            = module.storage.storage_account_id
    postgres_server            = module.database.server_id
    foundry_account            = module.ai.foundry_account_id
  }
}



# ─── Database ─────────────────────────────────────────────────────────────────
# PostgreSQL Flexible Server with VNet delegation (not private endpoint).
# The postgres private DNS zone is created in the security module and its ID
# is passed here. The server itself must be created AFTER the DNS zone + link.
module "database" {
  source                       = "../../../../providers/azure/database"
  resource_group_name          = data.azurerm_resource_group.this.name
  location                     = data.azurerm_resource_group.this.location
  name_prefix                  = local.name_prefix
  db_subnet_id                 = data.azurerm_subnet.database.id
  postgres_private_dns_zone_id = module.security.postgres_private_dns_zone_id
  admin_username               = var.postgres_admin_username
  admin_password               = var.postgres_admin_password
  tags                         = local.tags

  # Strict parity with prod: dev accepts higher cost so the deployment gate is uniform.
  sku_name                     = "GP_Standard_D2s_v3"
  storage_mb                   = 65536
  backup_retention_days        = 30
  geo_redundant_backup_enabled = true
}

# ─── GitHub Repository Variables ──────────────────────────────────────────────
# Pushing Terraform outputs back to the repository via the GitHub provider
# eliminates the need for the CI/CD pipeline to mutate repository state.

resource "github_actions_variable" "cna_nextauth_url" {
  repository    = var.github_repository
  variable_name = "CNA_NEXTAUTH_URL"
  value         = "https://${module.security.frontdoor_endpoint_host_name}"
}

resource "github_actions_variable" "key_vault_name" {
  repository    = var.github_repository
  variable_name = "KEY_VAULT_NAME"
  value         = module.identity.key_vault_name
}

# Adopt the placeholder variables seeded by Initialize-CnaGitHubSecrets.ps1, which
# runs before any Terraform. Without these imports Terraform's CREATE hits a 409
# ("Variable already exists") because the repository-scoped github_actions_variable
# does not upsert on create (unlike the env-scoped sibling fixed in provider
# PR #2758). On apply Terraform imports the existing variable, then the same apply
# updates it to its real post-deploy value. ID format is "repository:NAME" per the
# provider's buildID/parseID2 (colon separator). var.github_repository is the bare
# repo name (211 passes ${GITHUB_REPOSITORY#*/}). The targets always pre-exist
# because the bootstrap script seeds them first, so there is no import-missing risk.
import {
  to = github_actions_variable.cna_nextauth_url
  id = "${var.github_repository}:CNA_NEXTAUTH_URL"
}

import {
  to = github_actions_variable.key_vault_name
  id = "${var.github_repository}:KEY_VAULT_NAME"
}
