output "waf_web_acl_arn" {
  description = "ARN of the CloudFront-scoped WAFv2 web ACL."
  value       = aws_wafv2_web_acl.platform.arn
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name, or null when CloudFront is disabled."
  value       = one(aws_cloudfront_distribution.platform[*].domain_name)
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID, or null when CloudFront is disabled."
  value       = one(aws_cloudfront_distribution.platform[*].id)
}

output "cloudfront_distribution_arn" {
  description = "CloudFront distribution ARN, or null when CloudFront is disabled."
  value       = one(aws_cloudfront_distribution.platform[*].arn)
}
