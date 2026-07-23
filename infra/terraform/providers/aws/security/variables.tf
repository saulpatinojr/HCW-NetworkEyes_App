variable "name_prefix" {
  description = "Normalized name prefix for security resources"
  type        = string
}

variable "tags" {
  description = "Tags applied to security resources"
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "alb_arn" {
  description = "ARN of the ALB to associate with the regional WAF WebACL. If null, the WebACL is created but not associated."
  type        = string
  default     = null
}

variable "waf_override_action" {
  description = "Override action for managed rule groups: 'none' lets rules use their default action (Block); 'count' enables detection mode for initial rollout."
  type        = string
  default     = "none"

  validation {
    condition     = contains(["none", "count"], var.waf_override_action)
    error_message = "waf_override_action must be 'none' or 'count'."
  }
}

variable "enable_cloudfront" {
  description = "Whether to create a CloudFront distribution in front of the ALB."
  type        = bool
  default     = true
  nullable    = false
}

variable "alb_dns_name" {
  description = "DNS name of the ALB used as the CloudFront origin. Required when enable_cloudfront is true."
  type        = string
  default     = null
}

variable "cloudfront_price_class" {
  description = "CloudFront price class. PriceClass_100 covers US and EU PoPs."
  type        = string
  default     = "PriceClass_100"
}

variable "custom_domain_name" {
  description = "Optional custom domain name (CNAME) for the CloudFront distribution. Leave empty to use the default *.cloudfront.net domain."
  type        = string
  default     = ""
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN (must be in us-east-1) for the CloudFront distribution. Required when custom_domain_name is set."
  type        = string
  default     = null
}
