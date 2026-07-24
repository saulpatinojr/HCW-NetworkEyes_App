# =============================================================================
# Storage — artifacts + static-site S3 buckets (source: migrate/s3.tf).
# Mirrors the Azure storage account (one account, four containers).
# =============================================================================

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# ─── Artifacts bucket ─────────────────────────────────────────────────────────
resource "aws_s3_bucket" "artifacts" {
  bucket = local.artifacts_bucket_name

  tags = merge(var.tags, { Name = "${var.name_prefix}-artifacts" })
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    id     = "raw-artifacts-tiering"
    status = "Enabled"

    filter {
      prefix = "raw-artifacts/"
    }

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    expiration {
      days = var.raw_artifact_retention_days
    }
  }

  rule {
    id     = "deliverables-tiering"
    status = "Enabled"

    filter {
      prefix = "deliverables/"
    }

    transition {
      days          = var.deliverable_retention_days
      storage_class = "STANDARD_IA"
    }
  }
}

# ─── Static-site bucket (served via CloudFront OAC) ───────────────────────────
# The bucket policy granting CloudFront read access lives in the security module
# so the distribution ARN can be referenced without creating a cycle (spec §4).
resource "aws_s3_bucket" "static_site" {
  bucket = local.static_site_bucket_name

  tags = merge(var.tags, { Name = "${var.name_prefix}-static" })
}

# Left with SSE-S3 (the S3 default), NOT SSE-KMS: CloudFront OAC reads would
# otherwise need kms:Decrypt on the customer-managed key, adding key-policy
# coupling. Matches migrate/s3.tf, where the static bucket is unencrypted-by-KMS.
resource "aws_s3_bucket_public_access_block" "static_site" {
  bucket                  = aws_s3_bucket.static_site.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
