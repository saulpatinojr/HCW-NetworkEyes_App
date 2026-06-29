variable "resource_group_name" {
  description = "Resource group for the Azure Container Registry."
  type        = string
}

variable "location" {
  description = "Azure region for the registry."
  type        = string
}

variable "name_prefix" {
  description = "Normalized name prefix (e.g. cna-dev-scus). The registry name is derived from this (ACR names are alphanumeric only)."
  type        = string
}

variable "sku" {
  description = "ACR SKU. Basic is sufficient for managed-identity pull over the public endpoint with a firewall allowlist; Premium is required for a private endpoint (tracked as a later follow-up)."
  type        = string
  default     = "Basic"

  validation {
    condition     = contains(["Basic", "Standard", "Premium"], var.sku)
    error_message = "sku must be Basic, Standard, or Premium."
  }
}

variable "name_suffix" {
  description = "Optional suffix to disambiguate the globally-unique ACR name (e.g. on recreate after a soft-delete reservation)."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags applied to the registry."
  type        = map(string)
  default     = {}
}
