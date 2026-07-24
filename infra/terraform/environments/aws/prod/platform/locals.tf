locals {
  name_prefix = "${var.project_name}-${var.environment}-${var.region_short}"
  tags = {
    Environment = title(var.environment)
    CostCenter  = "CNA"
    Owner       = "cna-platform"
    Project     = var.project_name
    ManagedBy   = "terraform"
  }

  az_count = length(var.availability_zones)

  # One NAT gateway (dev cost saving) or one per AZ (prod HA). Private route
  # tables track the NAT count: a single shared table when single_nat_gateway,
  # otherwise one per AZ so each private subnet egresses via its zonal NAT.
  nat_gateway_count = var.single_nat_gateway ? 1 : local.az_count
}
