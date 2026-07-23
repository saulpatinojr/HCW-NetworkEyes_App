# Deploy order (no circular dependencies):
#   1. module.identity — KMS key, IAM roles (no module deps; uses data sources for account ID)
#   2. module.database — RDS PostgreSQL (depends on identity for KMS key)
#   3. module.compute  — ECS Fargate, ALB (depends on identity for task roles)
#   4. module.security — WAF, CloudFront (depends on compute for ALB ARN/DNS)
#
# This mirrors the Azure pattern: identity (Key Vault + MI) → compute
# (Container Apps) → security (Front Door + WAF).

module "identity" {
  source = "../../../../providers/aws/identity"

  name_prefix              = local.name_prefix
  tags                     = local.tags
  kms_deletion_window_days = 30
}

module "database" {
  source = "../../../../providers/aws/database"

  name_prefix        = local.name_prefix
  tags               = local.tags
  subnet_ids         = var.database_subnet_ids
  security_group_ids = [var.database_security_group_id]
  admin_password     = var.db_admin_password
  instance_class     = var.db_instance_class
  kms_key_id         = module.identity.kms_key_arn

  # Prod hardening: Multi-AZ, 30-day retention, deletion protection, final snapshot.
  multi_az              = true
  backup_retention_days = 30
  deletion_protection   = true
  skip_final_snapshot   = false
}

module "compute" {
  source = "../../../../providers/aws/compute"

  name_prefix             = local.name_prefix
  tags                    = local.tags
  aws_region              = var.region
  vpc_id                  = var.vpc_id
  app_subnet_ids          = var.app_subnet_ids
  public_subnet_ids       = var.public_subnet_ids
  app_security_group_id   = var.app_security_group_id
  alb_security_group_id   = var.alb_security_group_id
  task_execution_role_arn = module.identity.task_execution_role_arn
  task_role_arn           = module.identity.task_role_arn
  alb_certificate_arn     = var.alb_certificate_arn
  enable_scale_to_zero    = var.enable_scale_to_zero

  api_image    = var.api_image
  worker_image = var.worker_image
  web_image    = var.web_image

  # Prod: minimum one replica per service.
  api_min_count    = 1
  worker_min_count = 1
  web_min_count    = 1

  log_retention_days = 90

  api_environment = {
    ENVIRONMENT = var.environment
  }

  worker_environment = {
    ENVIRONMENT = var.environment
  }

  web_environment = {
    ENVIRONMENT = var.environment
  }
}

module "security" {
  source = "../../../../providers/aws/security"

  name_prefix         = local.name_prefix
  tags                = local.tags
  alb_arn             = module.compute.alb_arn
  alb_dns_name        = module.compute.alb_dns_name
  waf_override_action = var.waf_override_action
  enable_cloudfront   = true
  custom_domain_name  = var.custom_domain_name
  acm_certificate_arn = var.acm_certificate_arn
}
