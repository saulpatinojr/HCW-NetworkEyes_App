locals {
  instance_identifier = "${var.name_prefix}-psql"
  subnet_group_name   = "${var.name_prefix}-db-subnet-group"
}
