variable "project_name" {
  description = "Project name used in resource naming (mirrors Azure's var.project_name)"
  type        = string
  default     = "cna"
}

variable "environment" {
  description = "Deployment environment (dev or prod)"
  type        = string
  default     = "prod"
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "region_short" {
  description = "Short region code used in resource naming (mirrors Azure's var.region_short)"
  type        = string
  default     = "use1"
}

# ─── GitHub ───────────────────────────────────────────────────────────────────
variable "github_owner" {
  description = "GitHub organization/owner for the github provider and the OIDC deploy role."
  type        = string
  default     = "<GITHUB_OWNER_PLACEHOLDER>"
}

variable "github_repository" {
  description = "GitHub repository name (without owner) for the OIDC deploy role trust policy."
  type        = string
  default     = "<GITHUB_REPO_PLACEHOLDER>"
}

variable "github_token" {
  description = "GitHub token for the github provider."
  type        = string
  sensitive   = true
  default     = ""
}

# ─── Platform networking (consumed from the platform state) ───────────────────
variable "vpc_id" {
  description = "VPC ID from the platform environment."
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnet IDs from the platform environment (for the ALB)."
  type        = list(string)
  nullable    = false
}

variable "app_subnet_ids" {
  description = "Application subnet IDs from the platform environment (for the ECS tasks)."
  type        = list(string)
  nullable    = false
}

variable "database_subnet_ids" {
  description = "Database subnet IDs from the platform environment (for the RDS subnet group)."
  type        = list(string)
  nullable    = false
}

variable "alb_security_group_id" {
  description = "ALB security group ID from the platform environment."
  type        = string
}

variable "app_security_group_id" {
  description = "Application security group ID from the platform environment."
  type        = string
}

variable "database_security_group_id" {
  description = "Database security group ID from the platform environment."
  type        = string
}

# ─── Container images ─────────────────────────────────────────────────────────
variable "api_image" {
  description = "Container image for CNA API"
  type        = string
  default     = "docker.io/example-namespace/cna:api-latest"
}

variable "worker_image" {
  description = "Container image for CNA worker"
  type        = string
  default     = "docker.io/example-namespace/cna:worker-latest"
}

variable "web_image" {
  description = "Container image for CNA Web (Next.js 15)"
  type        = string
  default     = "docker.io/example-namespace/cna:web-latest"
}

# ─── Scaling / FinOps ─────────────────────────────────────────────────────────
variable "enable_scale_to_zero" {
  description = "Collapse all ECS service desired counts to 0 when idle. Dev cost saving; disabled in prod."
  type        = bool
  default     = false
}

# ─── Database ─────────────────────────────────────────────────────────────────
variable "db_admin_username" {
  description = "RDS master username."
  type        = string
  default     = "cnaadmin"
}

variable "db_admin_password" {
  description = "RDS master password."
  type        = string
  sensitive   = true
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.small"
}

variable "db_allocated_storage_gb" {
  description = "RDS initial allocated storage in GB."
  type        = number
  default     = 20
}

variable "postgres_major_version" {
  description = "PostgreSQL major version (e.g. \"16\")."
  type        = string
  default     = "16"
}

variable "db_multi_az" {
  description = "Enable Multi-AZ for RDS. Disabled in dev, enabled in prod."
  type        = bool
  default     = true
}

variable "db_backup_retention_days" {
  description = "RDS automated backup retention in days."
  type        = number
  default     = 7
}

variable "db_deletion_protection" {
  description = "Prevent accidental RDS deletion. Disabled in dev, enabled in prod."
  type        = bool
  default     = true
}

variable "db_skip_final_snapshot" {
  description = "Skip the final RDS snapshot on destroy. True in dev, false in prod."
  type        = bool
  default     = false
}

# ─── Secrets (Secrets Manager) ────────────────────────────────────────────────
variable "nextauth_secret" {
  description = "Auth.js JWT signing secret."
  type        = string
  sensitive   = true
}

variable "entra_client_secret" {
  description = "Entra ID OAuth client secret."
  type        = string
  sensitive   = true
}

variable "credential_encryption_key" {
  description = "Base64-encoded AES-256 key for encrypting stored credentials."
  type        = string
  sensitive   = true
}

variable "dockerhub_username" {
  description = "Docker Hub username for private image pulls. Empty disables the Docker Hub secret."
  type        = string
  default     = ""
}

variable "dockerhub_token" {
  description = "Docker Hub access token."
  type        = string
  sensitive   = true
  default     = ""
}

# ─── Application configuration (plain env) ────────────────────────────────────
variable "nextauth_url" {
  description = "Canonical URL for Auth.js callbacks (typically the CloudFront domain)."
  type        = string
  default     = ""
}

variable "entra_tenant_id" {
  description = "Entra ID tenant ID for SSO."
  type        = string
  default     = ""
}

variable "entra_client_id" {
  description = "Entra ID application client ID."
  type        = string
  default     = ""
}

variable "openai_endpoint" {
  description = "OpenAI-compatible endpoint URL."
  type        = string
  default     = ""
}

variable "openai_deployment" {
  description = "OpenAI model deployment name."
  type        = string
  default     = ""
}

# ─── TLS / edge ───────────────────────────────────────────────────────────────
variable "alb_certificate_arn" {
  description = "ACM certificate ARN (in var.region) for the ALB HTTPS listener. Null skips the HTTPS listener."
  type        = string
  default     = null
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN in us-east-1 for the CloudFront custom domain. Null uses the default CloudFront certificate."
  type        = string
  default     = null
}

variable "custom_domain_name" {
  description = "Custom domain (CNAME alias) for CloudFront. Empty uses the default CloudFront domain."
  type        = string
  default     = ""
}

variable "waf_override_action" {
  description = "WAF managed rule override action: \"none\" enforces, \"count\" only counts."
  type        = string
  default     = "none"
}

# ─── Identity / KMS ───────────────────────────────────────────────────────────
variable "kms_deletion_window_days" {
  description = "KMS key deletion window in days (7-30)."
  type        = number
  default     = 30
}

# ─── Observability ────────────────────────────────────────────────────────────
variable "log_retention_days" {
  description = "Retention, in days, for the ECS service log groups."
  type        = number
  default     = 30
}
