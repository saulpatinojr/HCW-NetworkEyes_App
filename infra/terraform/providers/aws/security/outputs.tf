output "waf_web_acl_arn" {
  description = "ARN of the WAF WebACL associated with the ALB"
  value       = aws_wafv2_web_acl.platform.arn
}

output "cloudfront_domain_name" {
  description = "Default CloudFront domain name (*.cloudfront.net). Empty string when enable_cloudfront is false."
  value       = local.create_cloudfront ? aws_cloudfront_distribution.platform[0].domain_name : ""
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID. Empty string when enable_cloudfront is false."
  value       = local.create_cloudfront ? aws_cloudfront_distribution.platform[0].id : ""
}
