variable "name_prefix" {
  description = "Normalized name prefix for storage resources (e.g. cna-dev-use1)"
  type        = string
}

variable "tags" {
  description = "Tags applied to storage resources"
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "kms_key_arn" {
  description = "ARN of the customer-managed KMS key (from the identity module) used for S3 server-side encryption."
  type        = string
}

variable "raw_artifact_retention_days" {
  description = "Days before raw-artifacts/ objects expire. Objects transition to STANDARD_IA after 30 days."
  type        = number
  default     = 365
}

variable "deliverable_retention_days" {
  description = "Days before deliverables/ objects transition to STANDARD_IA. Deliverables are retained indefinitely (no expiration)."
  type        = number
  default     = 90
}
