variable "name_prefix" {
  description = "Normalized name prefix for observability resources (e.g. cna-dev-use1)"
  type        = string
}

variable "tags" {
  description = "Tags applied to observability resources"
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "log_retention_days" {
  description = "Retention, in days, for the ECS service log groups."
  type        = number
  default     = 30
}

variable "kms_key_arn" {
  description = "Optional customer-managed KMS key ARN (from the identity module) for CloudWatch log group encryption. Null uses the default CloudWatch encryption."
  type        = string
  default     = null
}

variable "diagnostic_targets" {
  description = "Map of logical name => ARN for resources to wire diagnostics/alarms for. Mirrors Azure observability's diagnostic_targets contract; retained for interface parity."
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "sns_topic_arn" {
  description = "Existing SNS topic ARN for alarm notifications. When null, the module creates its own alarms topic."
  type        = string
  default     = null
}

variable "enable_alarms" {
  description = "Create the baseline CloudWatch metric alarms (ECS CPU/memory, RDS CPU/free storage, ALB 5XX)."
  type        = bool
  default     = true
}

variable "enable_dashboard" {
  description = "Create the platform CloudWatch dashboard."
  type        = bool
  default     = false
}

variable "alb_arn_suffix" {
  description = "ARN suffix of the ALB (e.g. app/cna-dev-use1-alb/abc123) used as the ALB 5XX alarm dimension. Null skips the ALB alarm. Supplied post-hoc because the ALB is created in the compute module, which deploys after observability."
  type        = string
  default     = null
}

variable "alarm_thresholds" {
  description = "Thresholds for the baseline alarms."
  type = object({
    ecs_cpu_percent         = optional(number, 85)
    ecs_memory_percent      = optional(number, 85)
    rds_cpu_percent         = optional(number, 85)
    rds_free_storage_bytes  = optional(number, 2147483648)
    rds_max_connections     = optional(number, 80)
    alb_5xx_count           = optional(number, 10)
    alb_latency_p99_seconds = optional(number, 5)
    api_error_count         = optional(number, 20)
    worker_error_count      = optional(number, 10)
  })
  default  = {}
  nullable = false
}

variable "enable_xray" {
  description = "Enable AWS X-Ray distributed tracing. Mirrors Azure Application Insights. When true, the module creates the X-Ray daemon log group and a platform sampling rule; the compute module adds the X-Ray sidecar container to each task definition."
  type        = bool
  default     = true
}

variable "xray_sampling_rate" {
  description = "X-Ray fixed sampling rate (0.0–1.0). 0.05 = 5% of requests traced."
  type        = number
  default     = 0.05

  validation {
    condition     = var.xray_sampling_rate >= 0 && var.xray_sampling_rate <= 1
    error_message = "xray_sampling_rate must be between 0.0 and 1.0."
  }
}

variable "enable_contributor_insights" {
  description = "Enable CloudWatch Contributor Insights (top-N analysis). Mirrors Azure App Insights top-contributor analytics."
  type        = bool
  default     = true
}
