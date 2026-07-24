locals {
  # A single artifacts bucket with per-purpose key prefixes (raw-artifacts/,
  # normalized-artifacts/, deliverables/) rather than four buckets — mirrors the
  # single Azure storage account with four blob containers. The static-site
  # bucket is separate because it is served through CloudFront via OAC.
  artifacts_bucket_name   = "${var.name_prefix}-artifacts-${random_id.bucket_suffix.hex}"
  static_site_bucket_name = "${var.name_prefix}-static-${random_id.bucket_suffix.hex}"
}
