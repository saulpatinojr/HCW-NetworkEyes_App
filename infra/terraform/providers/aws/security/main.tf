# ─── WAF ──────────────────────────────────────────────────────────────────────
# Regional WAF WebACL — protects the ALB.
# Equivalent to Azure Front Door WAF policy with DefaultRuleSet.

resource "aws_wafv2_web_acl" "platform" {
  name        = "${var.name_prefix}-waf"
  description = "CNA platform WAF — protects the ALB with AWS managed rule sets"
  scope       = "REGIONAL"
  tags        = var.tags

  default_action {
    allow {}
  }

  # AWS Managed Rules: Core Rule Set — OWASP Top 10 baseline
  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 10

    dynamic "override_action" {
      for_each = [var.waf_override_action]
      content {
        dynamic "none" {
          for_each = override_action.value == "none" ? [1] : []
          content {}
        }
        dynamic "count" {
          for_each = override_action.value == "count" ? [1] : []
          content {}
        }
      }
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${replace(var.name_prefix, "-", "")}CommonRuleSet"
      sampled_requests_enabled   = true
    }
  }

  # AWS Managed Rules: Known Bad Inputs
  rule {
    name     = "AWSManagedRulesKnownBadInputsRuleSet"
    priority = 20

    dynamic "override_action" {
      for_each = [var.waf_override_action]
      content {
        dynamic "none" {
          for_each = override_action.value == "none" ? [1] : []
          content {}
        }
        dynamic "count" {
          for_each = override_action.value == "count" ? [1] : []
          content {}
        }
      }
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${replace(var.name_prefix, "-", "")}KnownBadInputs"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${replace(var.name_prefix, "-", "")}WAF"
    sampled_requests_enabled   = true
  }
}

# Associate WAF WebACL with the ALB when an ARN is provided.
resource "aws_wafv2_web_acl_association" "alb" {
  count        = var.alb_arn != null ? 1 : 0
  resource_arn = var.alb_arn
  web_acl_arn  = aws_wafv2_web_acl.platform.arn
}

# ─── CloudFront ───────────────────────────────────────────────────────────────
# CDN distribution terminating TLS and forwarding to the ALB.
# Equivalent to Azure Front Door (CDN profile + endpoint + origin group).

resource "aws_cloudfront_distribution" "platform" {
  count = local.create_cloudfront ? 1 : 0

  enabled             = true
  is_ipv6_enabled     = true
  comment             = "CNA platform CDN — ${var.name_prefix}"
  price_class         = var.cloudfront_price_class
  wait_for_deployment = false
  tags                = var.tags

  aliases = local.use_custom_domain ? [var.custom_domain_name] : []

  origin {
    domain_name = var.alb_dns_name
    origin_id   = local.cloudfront_origin_id

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    allowed_methods  = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = local.cloudfront_origin_id

    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    # Managed CachingDisabled policy — appropriate for ALB/dynamic-origin traffic
    cache_policy_id = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"

    # Managed AllViewerExceptHostHeader policy — forwards all viewer headers except Host
    origin_request_policy_id = "b689b0a8-53d0-40ab-baf2-68738e2966ac"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn            = local.use_acm_cert ? var.acm_certificate_arn : null
    cloudfront_default_certificate = !local.use_acm_cert
    ssl_support_method             = local.use_acm_cert ? "sni-only" : null
    minimum_protocol_version       = local.use_acm_cert ? "TLSv1.2_2021" : "TLSv1"
  }
}
