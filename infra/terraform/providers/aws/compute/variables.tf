variable "name_prefix" {
  description = "Normalized name prefix for compute resources"
  type        = string
}

variable "tags" {
  description = "Tags applied to compute resources"
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "aws_region" {
  description = "AWS region used for CloudWatch log group ARNs"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID for target group and ALB"
  type        = string
}

variable "app_subnet_ids" {
  description = "Subnet IDs for ECS service network configuration (private app subnets)"
  type        = list(string)
  nullable    = false
}

variable "public_subnet_ids" {
  description = "Subnet IDs for the ALB (public subnets)"
  type        = list(string)
  nullable    = false
}

variable "app_security_group_id" {
  description = "Security group ID for ECS task containers"
  type        = string
}

variable "alb_security_group_id" {
  description = "Security group ID for the ALB"
  type        = string
}

variable "task_execution_role_arn" {
  description = "ARN of the ECS task execution IAM role"
  type        = string
}

variable "task_role_arn" {
  description = "ARN of the ECS task IAM role granted to running containers"
  type        = string
}

variable "alb_certificate_arn" {
  description = "ACM certificate ARN for the HTTPS ALB listener. If null, only the HTTP redirect listener is created."
  type        = string
  default     = null
}

variable "log_retention_days" {
  description = "CloudWatch log group retention in days"
  type        = number
  default     = 30
}

# ─── Scale to zero (FinOps) ───────────────────────────────────────────────────

variable "enable_scale_to_zero" {
  description = "Set desired_count to 0 for all services. Equivalent to Azure Container Apps scale-to-zero. Useful for dev to eliminate idle compute cost."
  type        = bool
  default     = false
  nullable    = false
}

# ─── API service ──────────────────────────────────────────────────────────────

variable "api_image" {
  description = "Container image URI for the cna-api service"
  type        = string
}

variable "api_target_port" {
  description = "Container port for cna-api"
  type        = number
  default     = 8000
}

variable "api_cpu" {
  description = "Fargate CPU units for cna-api task (256 = 0.25 vCPU)"
  type        = number
  default     = 512
}

variable "api_memory" {
  description = "Fargate memory in MiB for cna-api task"
  type        = number
  default     = 1024
}

variable "api_min_count" {
  description = "Minimum number of cna-api task instances"
  type        = number
  default     = 1
}

variable "api_environment" {
  description = "Plain-text environment variables for cna-api"
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "api_secrets" {
  description = "Map of env var name to Secrets Manager secret ARN (or ARN with JSON key) for cna-api"
  type        = map(string)
  default     = {}
  nullable    = false
}

# ─── Worker service ───────────────────────────────────────────────────────────

variable "worker_image" {
  description = "Container image URI for the cna-worker service"
  type        = string
}

variable "worker_cpu" {
  description = "Fargate CPU units for cna-worker task (256 = 0.25 vCPU)"
  type        = number
  default     = 512
}

variable "worker_memory" {
  description = "Fargate memory in MiB for cna-worker task"
  type        = number
  default     = 1024
}

variable "worker_min_count" {
  description = "Minimum number of cna-worker task instances"
  type        = number
  default     = 1
}

variable "worker_environment" {
  description = "Plain-text environment variables for cna-worker"
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "worker_secrets" {
  description = "Map of env var name to Secrets Manager secret ARN (or ARN with JSON key) for cna-worker"
  type        = map(string)
  default     = {}
  nullable    = false
}

# ─── Web service ──────────────────────────────────────────────────────────────

variable "web_image" {
  description = "Container image URI for the cna-web service"
  type        = string
}

variable "web_target_port" {
  description = "Container port for cna-web"
  type        = number
  default     = 3000
}

variable "web_cpu" {
  description = "Fargate CPU units for cna-web task (256 = 0.25 vCPU)"
  type        = number
  default     = 512
}

variable "web_memory" {
  description = "Fargate memory in MiB for cna-web task"
  type        = number
  default     = 1024
}

variable "web_min_count" {
  description = "Minimum number of cna-web task instances"
  type        = number
  default     = 1
}

variable "web_environment" {
  description = "Plain-text environment variables for cna-web"
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "web_secrets" {
  description = "Map of env var name to Secrets Manager secret ARN (or ARN with JSON key) for cna-web"
  type        = map(string)
  default     = {}
  nullable    = false
}
