locals {
  name_prefix = "${var.project_name}-${var.environment}-${var.region_short}"

  tags = {
    Environment = title(var.environment)
    CostCenter  = "CNA"
    Owner       = "cna-platform"
    Project     = var.project_name
    ManagedBy   = "terraform"
  }
}
