locals {
  alb_origin_id = "alb"

  aliases = var.custom_domain_name != "" ? [var.custom_domain_name] : []

  # AWS-managed CloudFront policy IDs (stable, region-agnostic).
  cache_policy_caching_disabled_id     = "4135ea2d-6724-4b39-8f97-b06f7a2af13c" # CachingDisabled
  origin_request_all_viewer_no_host_id = "b689b0a8-53d0-4db6-b046-27b40a0e40a5" # AllViewerExceptHostHeader

  waf_managed_rules = [
    {
      name        = "aws-managed-common"
      priority    = 10
      rule_group  = "AWSManagedRulesCommonRuleSet"
      metric_name = "${var.name_prefix}-common-rules"
    },
    {
      name        = "aws-managed-known-bad-inputs"
      priority    = 20
      rule_group  = "AWSManagedRulesKnownBadInputsRuleSet"
      metric_name = "${var.name_prefix}-bad-inputs"
    },
    {
      name        = "aws-managed-sqli"
      priority    = 30
      rule_group  = "AWSManagedRulesSQLiRuleSet"
      metric_name = "${var.name_prefix}-sqli"
    },
  ]

  # Auth.js v5 paths that trigger false positives in WAF managed rules.
  # Mirrors Azure Front Door WAF's field-specific exclusions.
  auth_paths = ["/auth/*", "/api/auth/*"]
}
