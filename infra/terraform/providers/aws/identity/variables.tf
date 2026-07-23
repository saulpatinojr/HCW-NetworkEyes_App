variable "name_prefix" {
  description = "Normalized name prefix for identity resources"
  type        = string
}

variable "tags" {
  description = "Tags applied to identity resources"
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "kms_deletion_window_days" {
  description = "Number of days before a scheduled KMS key deletion completes. Minimum 7, maximum 30."
  type        = number
  default     = 7
}
