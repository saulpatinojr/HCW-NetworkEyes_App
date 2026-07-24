variable "name_prefix" {
  description = "Normalized name prefix for database resources (e.g. cna-dev-use1)"
  type        = string
}

variable "tags" {
  description = "Tags applied to database resources"
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "subnet_ids" {
  description = "Database subnet IDs (from the platform networking) for the DB subnet group."
  type        = list(string)
  nullable    = false
}

variable "security_group_ids" {
  description = "Security group IDs (from the platform networking) attached to the RDS instance."
  type        = list(string)
  nullable    = false
}

variable "db_name" {
  description = "Initial database name."
  type        = string
  default     = "cna"
}

variable "admin_username" {
  description = "Master username for the PostgreSQL instance."
  type        = string
  default     = "cnaadmin"
}

variable "admin_password" {
  description = "Master password for the PostgreSQL instance."
  type        = string
  sensitive   = true
}

variable "instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.small"
}

variable "allocated_storage_gb" {
  description = "Initial allocated storage in GB. max_allocated_storage is set to twice this for storage autoscaling."
  type        = number
  default     = 20
}

variable "postgres_major_version" {
  description = "PostgreSQL MAJOR version only (e.g. \"16\"). AWS selects the latest supported minor; auto_minor_version_upgrade keeps it current."
  type        = string
  default     = "16"
}

variable "multi_az" {
  description = "Enable Multi-AZ for the RDS instance. Enabled in prod, disabled in dev."
  type        = bool
  default     = false
}

variable "backup_retention_days" {
  description = "Automated backup retention in days."
  type        = number
  default     = 7
}

variable "deletion_protection" {
  description = "Prevent accidental deletion of the RDS instance. Enabled in prod, disabled in dev."
  type        = bool
  default     = false
}

variable "skip_final_snapshot" {
  description = "Skip the final snapshot on destroy. True in dev, false in prod."
  type        = bool
  default     = true
}

variable "storage_encrypted" {
  description = "Encrypt RDS storage at rest with the customer-managed KMS key."
  type        = bool
  default     = true
}

variable "kms_key_id" {
  description = "ARN of the customer-managed KMS key (from the identity module) used for storage encryption. Null falls back to the default aws/rds key."
  type        = string
  default     = null
}
