variable "name_prefix" {
  description = "Normalized name prefix for compute resources (e.g. cna-dev-use1)"
  type        = string
}

variable "tags" {
  description = "Tags applied to compute resources"
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "aws_region" {
  description = "AWS region — used for the awslogs log configuration region."
  type        = string
}

# ─── Networking (from the platform environment) ───────────────────────────────
variable "vpc_id" {
  description = "VPC ID for the ALB target groups."
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnet IDs for the internet-facing ALB."
  type        = list(string)
  nullable    = false
}

variable "app_subnet_ids" {
  description = "Application (private) subnet IDs for the ECS Fargate tasks."
  type        = list(string)
  nullable    = false
}

variable "alb_security_group_id" {
  description = "Security group ID for the ALB."
  type        = string
}

variable "app_security_group_id" {
  description = "Security group ID for the ECS tasks."
  type        = string
}

# ─── Identity (from the identity module) ──────────────────────────────────────
variable "task_execution_role_arn" {
  description = "ECS task execution role ARN (image pull, log write, secret fetch)."
  type        = string
}

variable "task_role_arn" {
  description = "ECS task role ARN (application identity)."
  type        = string
}

# ─── TLS ──────────────────────────────────────────────────────────────────────
variable "alb_certificate_arn" {
  description = "ACM certificate ARN (in the ALB's region) for the HTTPS listener. Null skips the HTTPS listener and the API path rule. The certificate is created and validated externally — this module never mints one (spec §12.2)."
  type        = string
  default     = null
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

# ─── Task sizing ──────────────────────────────────────────────────────────────
variable "api_cpu" {
  description = "CPU units for the API task (1024 = 1 vCPU)."
  type        = number
  default     = 512
}

variable "api_memory" {
  description = "Memory (MiB) for the API task."
  type        = number
  default     = 1024
}

variable "worker_cpu" {
  description = "CPU units for the worker task (1024 = 1 vCPU)."
  type        = number
  default     = 512
}

variable "worker_memory" {
  description = "Memory (MiB) for the worker task."
  type        = number
  default     = 1024
}

variable "web_cpu" {
  description = "CPU units for the web task (1024 = 1 vCPU)."
  type        = number
  default     = 512
}

variable "web_memory" {
  description = "Memory (MiB) for the web task."
  type        = number
  default     = 1024
}

# ─── Scaling ──────────────────────────────────────────────────────────────────
variable "api_min_count" {
  description = "Baseline desired task count for the API service."
  type        = number
  default     = 1
}

variable "worker_min_count" {
  description = "Baseline desired task count for the worker service."
  type        = number
  default     = 1
}

variable "web_min_count" {
  description = "Baseline desired task count for the web service."
  type        = number
  default     = 1
}

variable "enable_scale_to_zero" {
  description = "Override desired_count to 0 for all services. Major cost saving for idle dev environments; not recommended for prod (cold-start latency)."
  type        = bool
  default     = false
}

# ─── Ingress ports ────────────────────────────────────────────────────────────
variable "api_target_port" {
  description = "Container/target-group port for the API service."
  type        = number
  default     = 8080
}

variable "web_target_port" {
  description = "Container/target-group port for the web service (Next.js)."
  type        = number
  default     = 3000
}

# ─── Environment + secrets ────────────────────────────────────────────────────
variable "api_environment" {
  description = "Plain environment variables for the API container. Map key is the env var name."
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "worker_environment" {
  description = "Plain environment variables for the worker container. Map key is the env var name."
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "web_environment" {
  description = "Plain environment variables for the web container. Map key is the env var name."
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "api_secrets" {
  description = "Secret-backed env vars for the API container. Map key is the env var name, value is the Secrets Manager secret ARN."
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "worker_secrets" {
  description = "Secret-backed env vars for the worker container. Map key is the env var name, value is the Secrets Manager secret ARN."
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "web_secrets" {
  description = "Secret-backed env vars for the web container. Map key is the env var name, value is the Secrets Manager secret ARN."
  type        = map(string)
  default     = {}
  nullable    = false
}

# ─── Logging ──────────────────────────────────────────────────────────────────
variable "api_log_group_name" {
  description = "CloudWatch log group name for the API service (owned by the observability module)."
  type        = string
}

variable "worker_log_group_name" {
  description = "CloudWatch log group name for the worker service (owned by the observability module)."
  type        = string
}

variable "web_log_group_name" {
  description = "CloudWatch log group name for the web service (owned by the observability module)."
  type        = string
}

# ─── Private registry ─────────────────────────────────────────────────────────
variable "dockerhub_secret_arn" {
  description = "Secrets Manager ARN holding Docker Hub credentials for private image pulls. Null omits repositoryCredentials. Supplied by the runtime module."
  type        = string
  default     = null
}
