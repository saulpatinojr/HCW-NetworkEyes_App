variable "name_prefix" {
  description = "Normalized name prefix for identity resources (e.g. cna-dev-use1)"
  type        = string
}

variable "tags" {
  description = "Tags applied to identity resources"
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "environment" {
  description = "Deployment environment (dev or prod)"
  type        = string
}

variable "project_name" {
  description = "Project name used for tag-scoped deploy permissions (matches the Project default tag)"
  type        = string
}

variable "kms_deletion_window_days" {
  description = "Waiting period, in days, before the customer-managed KMS key is deleted after destroy (7-30)."
  type        = number
  default     = 30

  validation {
    condition     = var.kms_deletion_window_days >= 7 && var.kms_deletion_window_days <= 30
    error_message = "kms_deletion_window_days must be between 7 and 30."
  }
}

variable "github_owner" {
  description = "GitHub organization or user that owns the repository allowed to assume the deploy role via OIDC."
  type        = string
}

variable "github_repository" {
  description = "GitHub repository name (without owner) allowed to assume the deploy role via OIDC."
  type        = string
}

variable "task_bedrock_policy_json" {
  description = "Optional IAM policy JSON (produced by the ai module) granting the ECS task role Bedrock InvokeModel access. When null, no Bedrock policy is attached to the task role."
  type        = string
  default     = null
}

variable "enable_xray" {
  description = "Attach X-Ray write permissions to the ECS task role. Mirrors Azure Application Insights auto-instrumentation."
  type        = bool
  default     = true
}
