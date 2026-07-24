# =============================================================================
# Platform networking — authored inline per environment (NOT a reusable module),
# mirroring the Azure platform env. Source: migrate/vpc.tf, migrate/security_groups.tf.
# =============================================================================

# ─── VPC + Internet Gateway ───────────────────────────────────────────────────
resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "${local.name_prefix}-vpc" }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = { Name = "${local.name_prefix}-igw" }
}

# ─── Subnets ──────────────────────────────────────────────────────────────────
resource "aws_subnet" "public" {
  count                   = length(var.subnet_public_cidrs)
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.subnet_public_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = false

  tags = { Name = "${local.name_prefix}-public-${var.availability_zones[count.index]}" }
}

resource "aws_subnet" "app" {
  count             = length(var.subnet_app_cidrs)
  vpc_id            = aws_vpc.this.id
  cidr_block        = var.subnet_app_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = { Name = "${local.name_prefix}-app-${var.availability_zones[count.index]}" }
}

resource "aws_subnet" "database" {
  count             = length(var.subnet_database_cidrs)
  vpc_id            = aws_vpc.this.id
  cidr_block        = var.subnet_database_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = { Name = "${local.name_prefix}-db-${var.availability_zones[count.index]}" }
}

# ─── NAT gateways ─────────────────────────────────────────────────────────────
resource "aws_eip" "nat" {
  count  = local.nat_gateway_count
  domain = "vpc"

  tags = { Name = "${local.name_prefix}-nat-eip-${count.index}" }
}

resource "aws_nat_gateway" "this" {
  count         = local.nat_gateway_count
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id

  tags       = { Name = "${local.name_prefix}-nat-${count.index}" }
  depends_on = [aws_internet_gateway.this]
}

# ─── Route tables ─────────────────────────────────────────────────────────────
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = { Name = "${local.name_prefix}-rt-public" }
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  count  = local.nat_gateway_count
  vpc_id = aws_vpc.this.id

  tags = { Name = "${local.name_prefix}-rt-private-${count.index}" }
}

resource "aws_route" "private_nat" {
  count                  = local.nat_gateway_count
  route_table_id         = aws_route_table.private[count.index].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[count.index].id
}

resource "aws_route_table_association" "app" {
  count          = length(aws_subnet.app)
  subnet_id      = aws_subnet.app[count.index].id
  route_table_id = aws_route_table.private[var.single_nat_gateway ? 0 : count.index].id
}

resource "aws_route_table_association" "database" {
  count          = length(aws_subnet.database)
  subnet_id      = aws_subnet.database[count.index].id
  route_table_id = aws_route_table.private[var.single_nat_gateway ? 0 : count.index].id
}

# ─── Security groups (no inline rules; standalone rule resources per spec §12.5) ─
resource "aws_security_group" "alb" {
  name_prefix = "${local.name_prefix}-alb-"
  vpc_id      = aws_vpc.this.id
  description = "ALB - allow HTTP/HTTPS inbound from the internet"

  tags = { Name = "${local.name_prefix}-sg-alb" }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group" "app" {
  name_prefix = "${local.name_prefix}-app-"
  vpc_id      = aws_vpc.this.id
  description = "ECS tasks - allow traffic from the ALB"

  tags = { Name = "${local.name_prefix}-sg-app" }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group" "database" {
  name_prefix = "${local.name_prefix}-db-"
  vpc_id      = aws_vpc.this.id
  description = "RDS - allow PostgreSQL from the app tier only"

  tags = { Name = "${local.name_prefix}-sg-db" }

  lifecycle {
    create_before_destroy = true
  }
}

# ALB ingress: HTTP + HTTPS from the internet.
resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  security_group_id = aws_security_group.alb.id
  description       = "HTTPS from the internet"
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "alb_http" {
  security_group_id = aws_security_group.alb.id
  description       = "HTTP from the internet (redirected to HTTPS)"
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "alb_all" {
  security_group_id = aws_security_group.alb.id
  description       = "All outbound"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

# App ingress: all traffic from the ALB security group.
resource "aws_vpc_security_group_ingress_rule" "app_from_alb" {
  security_group_id            = aws_security_group.app.id
  description                  = "All from the ALB"
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "-1"
}

resource "aws_vpc_security_group_egress_rule" "app_all" {
  security_group_id = aws_security_group.app.id
  description       = "All outbound"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

# Database ingress: PostgreSQL from the app security group only.
resource "aws_vpc_security_group_ingress_rule" "database_from_app" {
  security_group_id            = aws_security_group.database.id
  description                  = "PostgreSQL from the app tier"
  referenced_security_group_id = aws_security_group.app.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "database_all" {
  security_group_id = aws_security_group.database.id
  description       = "All outbound"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

# ─── VPC Flow Logs ────────────────────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "flow" {
  name              = "/vpc/flow-logs/${local.name_prefix}"
  retention_in_days = var.flow_log_retention_days

  tags = { Name = "${local.name_prefix}-flow-logs" }
}

data "aws_iam_policy_document" "flow_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["vpc-flow-logs.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "flow" {
  name               = "${local.name_prefix}-vpc-flow-logs"
  assume_role_policy = data.aws_iam_policy_document.flow_assume.json

  tags = { Name = "${local.name_prefix}-vpc-flow-logs" }
}

data "aws_iam_policy_document" "flow_permissions" {
  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
    ]
    resources = ["${aws_cloudwatch_log_group.flow.arn}:*"]
  }
}

resource "aws_iam_role_policy" "flow" {
  name   = "${local.name_prefix}-vpc-flow-logs"
  role   = aws_iam_role.flow.id
  policy = data.aws_iam_policy_document.flow_permissions.json
}

resource "aws_flow_log" "this" {
  iam_role_arn         = aws_iam_role.flow.arn
  log_destination      = aws_cloudwatch_log_group.flow.arn
  log_destination_type = "cloud-watch-logs"
  traffic_type         = "ALL"
  vpc_id               = aws_vpc.this.id

  tags = { Name = "${local.name_prefix}-flow-log" }
}
