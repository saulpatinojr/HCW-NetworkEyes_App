module "network" {
  source = "../../../../providers/aws/network"

  name_prefix           = local.name_prefix
  tags                  = local.tags
  vpc_cidr              = var.vpc_cidr
  availability_zones    = var.availability_zones
  subnet_public_cidrs   = var.subnet_public_cidrs
  subnet_app_cidrs      = var.subnet_app_cidrs
  subnet_database_cidrs = var.subnet_database_cidrs
}
