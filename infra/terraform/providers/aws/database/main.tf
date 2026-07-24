# =============================================================================
# Database — RDS for PostgreSQL (source: migrate/rds.tf). Mirrors the Azure
# PostgreSQL Flexible Server module.
# =============================================================================

resource "aws_db_subnet_group" "this" {
  name       = local.subnet_group_name
  subnet_ids = var.subnet_ids

  tags = merge(var.tags, { Name = local.subnet_group_name })
}

resource "aws_db_instance" "this" {
  identifier = local.instance_identifier

  engine         = "postgres"
  engine_version = var.postgres_major_version
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage_gb
  max_allocated_storage = var.allocated_storage_gb * 2
  storage_type          = "gp3"
  storage_encrypted     = var.storage_encrypted
  kms_key_id            = var.kms_key_id

  db_name  = var.db_name
  username = var.admin_username
  password = var.admin_password
  port     = 5432

  multi_az               = var.multi_az
  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = var.security_group_ids
  publicly_accessible    = false

  backup_retention_period = var.backup_retention_days
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:30-sun:05:30"

  deletion_protection       = var.deletion_protection
  skip_final_snapshot       = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : "${local.instance_identifier}-final"

  enabled_cloudwatch_logs_exports = ["postgresql"]
  auto_minor_version_upgrade      = true
  copy_tags_to_snapshot           = true

  tags = merge(var.tags, { Name = local.instance_identifier })

  lifecycle {
    ignore_changes = [password]
  }
}
