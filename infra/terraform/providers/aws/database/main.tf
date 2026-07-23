# RDS DB subnet group — requires subnets in at least two AZs.
resource "aws_db_subnet_group" "this" {
  name       = local.db_subnet_group_name
  subnet_ids = var.subnet_ids

  tags = merge(var.tags, { Name = local.db_subnet_group_name })
}

# PostgreSQL on RDS — private, VPC-integrated, no public access.
# Equivalent to Azure PostgreSQL Flexible Server with delegated subnet.
resource "aws_db_instance" "this" {
  identifier             = local.db_instance_id
  engine                 = "postgres"
  engine_version         = var.postgres_major_version
  instance_class         = var.instance_class
  allocated_storage      = var.allocated_storage_gb
  storage_type           = "gp3"
  storage_encrypted      = var.storage_encrypted
  kms_key_id             = var.kms_key_id
  db_name                = local.db_name
  username               = var.admin_username
  password               = var.admin_password
  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = var.security_group_ids
  multi_az               = var.multi_az
  backup_retention_period = var.backup_retention_days
  deletion_protection    = var.deletion_protection
  skip_final_snapshot    = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : "${local.db_instance_id}-final"
  publicly_accessible    = false
  auto_minor_version_upgrade = true
  copy_tags_to_snapshot  = true
  tags                   = var.tags

  lifecycle {
    ignore_changes = [
      # Password rotation is handled outside Terraform via Secrets Manager.
      password,
    ]
  }
}
