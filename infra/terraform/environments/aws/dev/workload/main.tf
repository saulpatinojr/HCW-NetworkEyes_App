# =============================================================================
# Workload — wires the eight AWS provider modules. Platform networking outputs
# are consumed as var.* (fed from the platform state). Terraform resolves the
# actual apply order from the dependency graph; the logical order mirrors the
# Azure workload: identity/ai -> storage/database/observability -> runtime ->
# compute -> security.
# =============================================================================

# ─── AI (Bedrock policy document; consumed by identity) ───────────────────────
module "ai" {
  source = "../../../../providers/aws/ai"

  name_prefix = local.name_prefix
  tags        = local.tags
}

# ─── Identity (KMS, ECS roles, GitHub OIDC) ───────────────────────────────────
module "identity" {
  source = "../../../../providers/aws/identity"

  name_prefix              = local.name_prefix
  tags                     = local.tags
  environment              = var.environment
  project_name             = var.project_name
  kms_deletion_window_days = var.kms_deletion_window_days
  github_owner             = var.github_owner
  github_repository        = var.github_repository
  task_bedrock_policy_json = module.ai.task_bedrock_policy_json
}

# ─── Storage (S3 artifacts + static-site) ─────────────────────────────────────
module "storage" {
  source = "../../../../providers/aws/storage"

  name_prefix = local.name_prefix
  tags        = local.tags
  kms_key_arn = module.identity.kms_key_arn
}

# ─── Database (RDS PostgreSQL) ────────────────────────────────────────────────
module "database" {
  source = "../../../../providers/aws/database"

  name_prefix            = local.name_prefix
  tags                   = local.tags
  subnet_ids             = var.database_subnet_ids
  security_group_ids     = [var.database_security_group_id]
  admin_username         = var.db_admin_username
  admin_password         = var.db_admin_password
  instance_class         = var.db_instance_class
  allocated_storage_gb   = var.db_allocated_storage_gb
  postgres_major_version = var.postgres_major_version
  multi_az               = var.db_multi_az
  backup_retention_days  = var.db_backup_retention_days
  deletion_protection    = var.db_deletion_protection
  skip_final_snapshot    = var.db_skip_final_snapshot
  kms_key_id             = module.identity.kms_key_arn
}

# ─── Observability (CloudWatch log groups + alarms) ───────────────────────────
module "observability" {
  source = "../../../../providers/aws/observability"

  name_prefix        = local.name_prefix
  tags               = local.tags
  log_retention_days = var.log_retention_days
  kms_key_arn        = module.identity.kms_key_arn
}

# ─── Runtime (Secrets Manager) ────────────────────────────────────────────────
module "runtime" {
  source = "../../../../providers/aws/runtime"

  name_prefix               = local.name_prefix
  tags                      = local.tags
  environment               = var.environment
  db_endpoint               = module.database.endpoint
  db_username               = var.db_admin_username
  db_password               = var.db_admin_password
  db_name                   = module.database.db_name
  nextauth_secret           = var.nextauth_secret
  entra_client_secret       = var.entra_client_secret
  credential_encryption_key = var.credential_encryption_key
  dockerhub_username        = var.dockerhub_username
  dockerhub_token           = var.dockerhub_token
}

# ─── Compute (ECS Fargate + ALB) ──────────────────────────────────────────────
module "compute" {
  source = "../../../../providers/aws/compute"

  name_prefix = local.name_prefix
  tags        = local.tags
  aws_region  = var.region

  vpc_id                = var.vpc_id
  public_subnet_ids     = var.public_subnet_ids
  app_subnet_ids        = var.app_subnet_ids
  alb_security_group_id = var.alb_security_group_id
  app_security_group_id = var.app_security_group_id

  task_execution_role_arn = module.identity.task_execution_role_arn
  task_role_arn           = module.identity.task_role_arn

  alb_certificate_arn  = var.alb_certificate_arn
  enable_scale_to_zero = var.enable_scale_to_zero

  api_image    = var.api_image
  worker_image = var.worker_image
  web_image    = var.web_image

  api_log_group_name    = module.observability.api_log_group_name
  worker_log_group_name = module.observability.worker_log_group_name
  web_log_group_name    = module.observability.web_log_group_name

  dockerhub_secret_arn = module.runtime.dockerhub_secret_arn

  api_environment = {
    CNA_STORAGE_BUCKET = module.storage.artifacts_bucket_id
    AWS_REGION         = var.region
    OPENAI_ENDPOINT    = var.openai_endpoint
    OPENAI_DEPLOYMENT  = var.openai_deployment
  }

  worker_environment = {
    CNA_STORAGE_BUCKET = module.storage.artifacts_bucket_id
    AWS_REGION         = var.region
    OPENAI_ENDPOINT    = var.openai_endpoint
    OPENAI_DEPLOYMENT  = var.openai_deployment
  }

  web_environment = {
    NEXTAUTH_URL       = var.nextauth_url
    AUTH_TRUST_HOST    = "true"
    AZURE_AD_TENANT_ID = var.entra_tenant_id
    AZURE_AD_CLIENT_ID = var.entra_client_id
    CNA_STORAGE_BUCKET = module.storage.artifacts_bucket_id
    AWS_REGION         = var.region
    OPENAI_ENDPOINT    = var.openai_endpoint
    OPENAI_DEPLOYMENT  = var.openai_deployment
  }

  api_secrets = {
    DATABASE_URL = module.runtime.database_url_secret_arn
  }

  worker_secrets = {
    DATABASE_URL = module.runtime.database_url_secret_arn
  }

  web_secrets = {
    DATABASE_URL              = module.runtime.database_url_secret_arn
    AUTH_SECRET               = module.runtime.nextauth_secret_arn
    AZURE_AD_CLIENT_SECRET    = module.runtime.entra_client_secret_arn
    CREDENTIAL_ENCRYPTION_KEY = module.runtime.credential_encryption_key_secret_arn
  }
}

# ─── Security (edge: WAF us-east-1 + CloudFront + OAC) ────────────────────────
module "security" {
  source = "../../../../providers/aws/security"

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  name_prefix            = local.name_prefix
  tags                   = local.tags
  alb_dns_name           = module.compute.alb_dns_name
  waf_override_action    = var.waf_override_action
  custom_domain_name     = var.custom_domain_name
  acm_certificate_arn    = var.acm_certificate_arn
  static_site_bucket_id  = module.storage.static_site_bucket_id
  static_site_bucket_arn = module.storage.static_site_bucket_arn
}
