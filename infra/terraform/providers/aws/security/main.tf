# =============================================================================
# Security (edge) — WAF, CloudFront, OAC, static-site bucket policy
# (source: migrate/cloudfront.tf). Mirrors the Azure security module (Front Door
# + WAF). The WAF is CLOUDFRONT-scoped and therefore created in us-east-1 via
# the aws.us_east_1 provider alias (spec §12.3).
# =============================================================================

# ─── WAFv2 web ACL (CLOUDFRONT scope, us-east-1) ──────────────────────────────
resource "aws_wafv2_web_acl" "platform" {
  provider    = aws.us_east_1
  name        = "${var.name_prefix}-waf"
  description = "CNA platform edge WAF"
  scope       = "CLOUDFRONT"

  default_action {
    allow {}
  }

  dynamic "rule" {
    for_each = { for r in local.waf_managed_rules : r.name => r }

    content {
      name     = rule.value.name
      priority = rule.value.priority

      override_action {
        dynamic "none" {
          for_each = var.waf_override_action == "none" ? [1] : []
          content {}
        }
        dynamic "count" {
          for_each = var.waf_override_action == "count" ? [1] : []
          content {}
        }
      }

      statement {
        managed_rule_group_statement {
          name        = rule.value.rule_group
          vendor_name = "AWS"
        }
      }

      visibility_config {
        sampled_requests_enabled   = true
        cloudwatch_metrics_enabled = true
        metric_name                = rule.value.metric_name
      }
    }
  }

  visibility_config {
    sampled_requests_enabled   = true
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.name_prefix}-waf"
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-waf" })
}

# ─── Origin Access Control for the static-site bucket ─────────────────────────
resource "aws_cloudfront_origin_access_control" "static" {
  name                              = "${var.name_prefix}-static-oac"
  description                       = "OAC for the ${var.name_prefix} static-site bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# ─── CloudFront distribution ──────────────────────────────────────────────────
resource "aws_cloudfront_distribution" "platform" {
  count = var.enable_cloudfront ? 1 : 0

  enabled         = true
  is_ipv6_enabled = true
  comment         = "${var.name_prefix} platform CDN"
  price_class     = var.cloudfront_price_class
  web_acl_id      = aws_wafv2_web_acl.platform.arn
  aliases         = local.aliases

  origin {
    domain_name = var.alb_dns_name
    origin_id   = local.alb_origin_id

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    allowed_methods          = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods           = ["GET", "HEAD"]
    target_origin_id         = local.alb_origin_id
    viewer_protocol_policy   = "redirect-to-https"
    compress                 = true
    cache_policy_id          = local.cache_policy_caching_disabled_id
    origin_request_policy_id = local.origin_request_all_viewer_no_host_id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = var.acm_certificate_arn == null
    acm_certificate_arn            = var.acm_certificate_arn
    ssl_support_method             = var.acm_certificate_arn != null ? "sni-only" : null
    minimum_protocol_version       = var.acm_certificate_arn != null ? "TLSv1.2_2021" : "TLSv1"
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-cdn" })
}

# ─── Static-site bucket policy (CloudFront OAC read access) ───────────────────
# Lives here (not in storage) so the distribution ARN can be referenced without
# creating a storage -> security cycle (spec §4).
data "aws_iam_policy_document" "static_site" {
  count = var.enable_cloudfront ? 1 : 0

  statement {
    sid     = "AllowCloudFrontOacRead"
    effect  = "Allow"
    actions = ["s3:GetObject"]
    resources = [
      "${var.static_site_bucket_arn}/*",
    ]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.platform[0].arn]
    }
  }
}

resource "aws_s3_bucket_policy" "static_site" {
  count  = var.enable_cloudfront ? 1 : 0
  bucket = var.static_site_bucket_id
  policy = data.aws_iam_policy_document.static_site[0].json
}
