output "artifacts_bucket_id" {
  description = "Name (ID) of the artifacts S3 bucket. Passed to compute as CNA_STORAGE_BUCKET."
  value       = aws_s3_bucket.artifacts.id
}

output "artifacts_bucket_arn" {
  description = "ARN of the artifacts S3 bucket."
  value       = aws_s3_bucket.artifacts.arn
}

output "static_site_bucket_id" {
  description = "Name (ID) of the static-site S3 bucket. Passed to the security module for the CloudFront OAC bucket policy."
  value       = aws_s3_bucket.static_site.id
}

output "static_site_bucket_arn" {
  description = "ARN of the static-site S3 bucket. Passed to the security module for the CloudFront OAC bucket policy."
  value       = aws_s3_bucket.static_site.arn
}
