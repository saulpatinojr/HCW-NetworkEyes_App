locals {
  db_subnet_group_name = "${var.name_prefix}-db-sng"
  db_instance_id       = "${var.name_prefix}-psql"
  db_name              = "cna"
}
