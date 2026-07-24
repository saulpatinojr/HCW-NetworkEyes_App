variable "name_prefix" {
  description = "Normalized name prefix for edge/security resources (e.g. cna-dev-use1)"
  type        = string
}

variable "tags" {
  description = "Tags applied to edge/security resources"
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "alb_dns_name" {
  description = "ALB DNS name (from the compute module) used as the CloudFront custom origin."
  type        = string
}

variable "waf_override_action" {
  description = "Override action applied to each managed rule group: \"none\" enforces the rules, \"count\" only counts matches."
  type        = string
  default     = "none"

  validation {
    condition     = contains(["none", "count"], var.waf_override_action)
    error_message = "waf_override_action must be either \"none\" or \"count\"."
  }
}

variable "enable_cloudfront" {
  description = "Create the CloudFront distribution and its static-site bucket policy."
  type        = bool
  default     = true
}

variable "cloudfront_price_class" {
  description = "CloudFront price class (edge-location footprint)."
  type        = string
  default     = "PriceClass_100"
}

variable "custom_domain_name" {
  description = "Custom domain (CNAME alias) for the distribution. Empty string uses the default CloudFront domain."
  type        = string
  default     = ""
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN in us-east-1 for the custom domain. Null uses the default CloudFront certificate. The certificate is created and validated externally (spec §12.2)."
  type        = string
  default     = null
}

variable "static_site_bucket_id" {
  description = "Static-site S3 bucket name (from the storage module) for the CloudFront OAC bucket policy."
  type        = string
}

variable "static_site_bucket_arn" {
  description = "Static-site S3 bucket ARN (from the storage module) for the CloudFront OAC bucket policy."
  type        = string
}
