variable "region" {
  description = "AWS region for CNA platform deployment"
  type        = string
  default     = "us-east-1"
}

variable "region_short" {
  description = "Short region code used in resource names"
  type        = string
  default     = "use1"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "prod"
}

variable "project_name" {
  description = "Project name prefix"
  type        = string
  default     = "cna"
}

# ─── Network inputs (from platform state) ────────────────────────────────────

variable "vpc_id" {
  description = "VPC ID from the platform landing zone"
  type        = string
}

variable "app_subnet_ids" {
  description = "Private application subnet IDs from the platform landing zone"
  type        = list(string)
  nullable    = false
}

variable "public_subnet_ids" {
  description = "Public subnet IDs from the platform landing zone"
  type        = list(string)
  nullable    = false
}

variable "database_subnet_ids" {
  description = "Private database subnet IDs from the platform landing zone"
  type        = list(string)
  nullable    = false
}

variable "app_security_group_id" {
  description = "Application (ECS) security group ID from the platform landing zone"
  type        = string
}

variable "alb_security_group_id" {
  description = "ALB security group ID from the platform landing zone"
  type        = string
}

variable "database_security_group_id" {
  description = "Database (RDS) security group ID from the platform landing zone"
  type        = string
}

# ─── Database ────────────────────────────────────────────────────────────────

variable "db_admin_password" {
  description = "Master password for the RDS PostgreSQL instance — supply from CI/CD secret"
  type        = string
  sensitive   = true
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t4g.medium"
}

# ─── Compute images ──────────────────────────────────────────────────────────

variable "api_image" {
  description = "Container image URI for cna-api"
  type        = string
}

variable "worker_image" {
  description = "Container image URI for cna-worker"
  type        = string
}

variable "web_image" {
  description = "Container image URI for cna-web"
  type        = string
}

variable "alb_certificate_arn" {
  description = "ACM certificate ARN for the HTTPS ALB listener."
  type        = string
  default     = null
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN (us-east-1) for CloudFront. Required when custom_domain_name is set."
  type        = string
  default     = null
}

variable "custom_domain_name" {
  description = "Optional custom domain for CloudFront."
  type        = string
  default     = ""
}

variable "enable_scale_to_zero" {
  description = "Set desired_count to 0 for all ECS services. Always false for prod."
  type        = bool
  default     = false
  nullable    = false
}

variable "waf_override_action" {
  description = "WAF managed rule override: 'none' (block) or 'count' (detect only). Defaults to 'none' in prod."
  type        = string
  default     = "none"
}
