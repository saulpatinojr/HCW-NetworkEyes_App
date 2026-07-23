locals {
  use_custom_domain    = var.custom_domain_name != ""
  use_acm_cert         = local.use_custom_domain && var.acm_certificate_arn != null
  cloudfront_origin_id = "${var.name_prefix}-alb-origin"
  create_cloudfront    = var.enable_cloudfront && var.alb_dns_name != null
}
