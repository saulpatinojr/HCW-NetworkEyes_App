variable "api_image" {
  description = "Container image for CNA API (docker.io/example-namespace/cna:api-latest)"
  type        = string
  default     = "docker.io/example-namespace/cna:api-latest"
}

variable "worker_image" {
  description = "Container image for CNA worker (docker.io/example-namespace/cna:worker-latest)"
  type        = string
  default     = "docker.io/example-namespace/cna:worker-latest"
}

variable "web_image" {
  description = "Container image for CNA web (docker.io/example-namespace/cna:web-latest)"
  type        = string
  default     = "docker.io/example-namespace/cna:web-latest"
}

variable "tenant_id" {
  description = "Azure tenant ID"
  type        = string
  default     = "00000000-0000-0000-0000-000000000000"
}

variable "location" {
  description = "Azure region for CNA Platform deployment"
  type        = string
  default     = "southcentralus"
}

variable "region_short" {
  description = "Short region code used in resource names (e.g. scus, eus2, wus2)"
  type        = string
  default     = "scus"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "Project name prefix"
  type        = string
  default     = "cna"
}

# ─── PostgreSQL ────────────────────────────────────────────────────────────────
variable "postgres_admin_username" {
  description = "PostgreSQL administrator username"
  type        = string
  default     = "cnaadmin"
}

variable "postgres_admin_password" {
  description = "PostgreSQL administrator password — set from GitHub Secret CNA_POSTGRES_ADMIN_PASSWORD"
  type        = string
  sensitive   = true
}

# ─── Entra ID (Azure AD) ───────────────────────────────────────────────────────
variable "entra_client_id" {
  description = "Entra ID (Azure AD) application client ID for NextAuth Entra provider"
  type        = string
}

variable "entra_client_secret" {
  description = "Entra ID OAuth2 client secret — set from GitHub Secret CNA_ENTRA_CLIENT_SECRET"
  type        = string
  sensitive   = true
}

# ─── Container Registry ───────────────────────────────────────────────────────
variable "container_registry_username" {
  description = "Username for private container registry image pulls."
  type        = string
  default     = ""
}

variable "container_registry_password" {
  description = "Token or password for private container registry image pulls. Set from GitHub Secret DOCKERHUB_TOKEN for Docker Hub."
  type        = string
  sensitive   = true
}

# ─── NextAuth ─────────────────────────────────────────────────────────────────
variable "nextauth_secret" {
  description = "NextAuth.js JWT signing secret — generate with: openssl rand -base64 32"
  type        = string
  sensitive   = true
}

variable "nextauth_url" {
  description = "Canonical URL of the cna-web deployment (used by NextAuth for callbacks)"
  type        = string
  default     = "https://cna.example.com"
}

variable "web_ingress_ip_security_restrictions" {
  description = "Optional web ingress IP restrictions for direct-origin hardening."
  type = list(object({
    name             = string
    action           = string
    ip_address_range = string
    description      = optional(string)
  }))
  default = []
}

# ─── Credential encryption ────────────────────────────────────────────────────
variable "credential_encryption_key" {
  description = "Base64-encoded 32-byte AES-256 key for encrypting SP client secrets at rest. Generate with: openssl rand -base64 32"
  type        = string
  sensitive   = true
}

# ─── AI Engine + MCP configuration ────────────────────────────────────────────
variable "ai_engine_default" {
  description = "Default global GenAI engine when no database setting exists. Azure OpenAI (gpt-chat-latest on the AIServices account) is the only supported engine; Anthropic/Claude on Foundry is not available in this tenant and was removed (see docs/adr/0001)."
  type        = string
  default     = "azure-openai"

  validation {
    condition     = contains(["azure-openai"], var.ai_engine_default)
    error_message = "ai_engine_default must be azure-openai."
  }
}

variable "foundry_location" {
  description = "Azure region for the Foundry/AIServices account. Defaults to eastus2 (model + capacity availability); override per environment if needed."
  type        = string
  default     = "eastus2"
}

# ─── Azure OpenAI (default engine) ────────────────────────────────────────────
# Points at the gpt-chat-latest deployment on the Foundry/AIServices account.
# Auth is AAD/managed-identity only (key auth is disabled on the account), which
# the app's AzureOpenAI client already uses via DefaultAzureCredential. The
# endpoint is the base host; the AzureOpenAI SDK appends the openai/deployment path.
variable "azure_openai_endpoint" {
  description = "Azure OpenAI base endpoint host for the web app (no /openai/v1 suffix; the SDK appends it)."
  type        = string
  default     = "https://cna-dev-eus2-aif2.services.ai.azure.com"
}

variable "azure_openai_deployment" {
  description = "Azure OpenAI deployment name."
  type        = string
  default     = "gpt-chat-latest"
}

variable "azure_openai_api_version" {
  description = "Azure OpenAI API version."
  type        = string
  default     = "2024-12-01-preview"
}

variable "azure_mcp_endpoint" {
  description = "Azure MCP server endpoint surfaced in cna-web."
  type        = string
  default     = ""
}

variable "azure_mcp_transport" {
  description = "Azure MCP server transport."
  type        = string
  default     = "streamable-http"
}

variable "aws_mcp_endpoint" {
  description = "AWS MCP server endpoint surfaced in cna-web."
  type        = string
  default     = ""
}

variable "aws_mcp_transport" {
  description = "AWS MCP server transport."
  type        = string
  default     = "streamable-http"
}

variable "drawio_mcp_url" {
  description = "draw.io MCP endpoint surfaced in cna-web."
  type        = string
  default     = ""
}

variable "secret_expiration_date" {
  description = "RFC3339 expiry for Terraform-managed KV secrets. Must satisfy Enforce-GR-KeyVault (max 90 days from now). Computed dynamically in CI via 'date -u -d +90days'."
  type        = string
  default     = "2026-09-20T23:59:59Z"
}
variable "tfstate_resource_group" {
  type    = string
  default = "rg-cna-dev-scus-tfstate"
}

variable "tfstate_storage_account" {
  type    = string
  default = "stcna0512f9tfstate"
}

variable "tfstate_container" {
  type    = string
  default = "tfstate"
}
variable "frontdoor_certificate_pfx_path" {
  description = "File path to the PFX certificate for Front Door"
  type        = string
  default     = null
}

variable "frontdoor_certificate_pfx_password" {
  description = "Password for the PFX certificate"
  type        = string
  sensitive   = true
  default     = null
}

# ─── GitHub ───────────────────────────────────────────────────────────────────
variable "github_owner" {
  description = "GitHub organization or user owning the repository"
  type        = string
}

variable "github_repository" {
  description = "GitHub repository name (without owner)"
  type        = string
}

variable "github_token" {
  description = "GitHub PAT with permissions to manage repository variables"
  type        = string
  sensitive   = true
}
