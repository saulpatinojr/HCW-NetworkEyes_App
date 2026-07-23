variable "name_prefix" {
  description = "Normalized name prefix for database resources"
  type        = string
}

variable "tags" {
  description = "Tags applied to database resources"
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "subnet_ids" {
  description = "Subnet IDs for the RDS DB subnet group (must span at least two AZs)"
  type        = list(string)
  nullable    = false
}

variable "security_group_ids" {
  description = "Security group IDs to attach to the RDS instance"
  type        = list(string)
  nullable    = false
}

variable "admin_username" {
  description = "Master username for the RDS PostgreSQL instance"
  type        = string
  default     = "cnaadmin"
}

variable "admin_password" {
  description = "Master password for the RDS PostgreSQL instance — supply from Secrets Manager or GitHub Secret"
  type        = string
  sensitive   = true
}

variable "instance_class" {
  description = "RDS instance class. Use db.t4g.micro for dev, db.t4g.medium or larger for prod."
  type        = string
  default     = "db.t4g.micro"
}

variable "allocated_storage_gb" {
  description = "Initial allocated storage in GiB"
  type        = number
  default     = 20
}

variable "postgres_major_version" {
  description = "PostgreSQL major engine version"
  type        = string
  default     = "16"
}

variable "multi_az" {
  description = "Enable Multi-AZ deployment for high availability. Recommended true for prod — without it, an AZ failure has no automatic failover."
  type        = bool
  default     = false
  nullable    = false
}

variable "backup_retention_days" {
  description = "Number of days to retain automated backups. Use 7 for dev, 30 for prod (compliance minimum)."
  type        = number
  default     = 7
}

variable "deletion_protection" {
  description = "Enable deletion protection. Recommended true for prod to prevent accidental permanent deletion."
  type        = bool
  default     = false
  nullable    = false
}

variable "skip_final_snapshot" {
  description = "Skip final snapshot on deletion. Set false for prod to avoid accidental data loss."
  type        = bool
  default     = true
  nullable    = false
}

variable "storage_encrypted" {
  description = "Enable storage encryption at rest."
  type        = bool
  default     = true
  nullable    = false
}

variable "kms_key_id" {
  description = "KMS key ARN for RDS storage encryption. If null, the AWS-managed RDS key is used."
  type        = string
  default     = null
}
