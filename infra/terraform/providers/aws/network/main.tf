resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, { Name = "${var.name_prefix}-vpc" })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.name_prefix}-igw" })
}

# ─── Subnets ──────────────────────────────────────────────────────────────────

resource "aws_subnet" "public" {
  count                   = local.az_count
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.subnet_public_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = false

  tags = merge(var.tags, { Name = "${var.name_prefix}-snet-pub-${count.index + 1}" })
}

resource "aws_subnet" "app" {
  count             = local.az_count
  vpc_id            = aws_vpc.this.id
  cidr_block        = var.subnet_app_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = merge(var.tags, { Name = "${var.name_prefix}-snet-app-${count.index + 1}" })
}

resource "aws_subnet" "database" {
  count             = local.az_count
  vpc_id            = aws_vpc.this.id
  cidr_block        = var.subnet_database_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = merge(var.tags, { Name = "${var.name_prefix}-snet-db-${count.index + 1}" })
}

# ─── NAT Gateways (one per AZ for per-AZ failover) ───────────────────────────

resource "aws_eip" "nat" {
  count  = local.az_count
  domain = "vpc"

  tags = merge(var.tags, { Name = "${var.name_prefix}-eip-nat-${count.index + 1}" })

  depends_on = [aws_internet_gateway.this]
}

resource "aws_nat_gateway" "this" {
  count         = local.az_count
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id

  tags = merge(var.tags, { Name = "${var.name_prefix}-ngw-${count.index + 1}" })

  depends_on = [aws_internet_gateway.this]
}

# ─── Route tables ─────────────────────────────────────────────────────────────

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-rt-pub" })
}

resource "aws_route_table_association" "public" {
  count          = local.az_count
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# One private route table per AZ so each AZ routes through its own NAT Gateway.
resource "aws_route_table" "private" {
  count  = local.az_count
  vpc_id = aws_vpc.this.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.this[count.index].id
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-rt-priv-${count.index + 1}" })
}

resource "aws_route_table_association" "app" {
  count          = local.az_count
  subnet_id      = aws_subnet.app[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

resource "aws_route_table_association" "database" {
  count          = local.az_count
  subnet_id      = aws_subnet.database[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

# ─── Security groups ──────────────────────────────────────────────────────────

# ALB security group — accepts HTTPS/HTTP from internet, forwards to app tasks.
resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-sg-alb"
  description = "Security group for the Application Load Balancer"
  vpc_id      = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.name_prefix}-sg-alb" })
}

resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  security_group_id = aws_security_group.alb.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  description       = "Allow HTTPS from internet"
}

resource "aws_vpc_security_group_ingress_rule" "alb_http" {
  security_group_id = aws_security_group.alb.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
  description       = "Allow HTTP from internet (redirect to HTTPS)"
}

resource "aws_vpc_security_group_egress_rule" "alb_to_app" {
  security_group_id            = aws_security_group.alb.id
  referenced_security_group_id = aws_security_group.app.id
  ip_protocol                  = "-1"
  description                  = "Allow all traffic from ALB to app security group"
}

# App security group — ECS task containers.
resource "aws_security_group" "app" {
  name        = "${var.name_prefix}-sg-app"
  description = "Security group for ECS application tasks"
  vpc_id      = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.name_prefix}-sg-app" })
}

resource "aws_vpc_security_group_ingress_rule" "app_from_alb" {
  security_group_id            = aws_security_group.app.id
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "-1"
  description                  = "Allow all traffic from ALB"
}

resource "aws_vpc_security_group_egress_rule" "app_all_outbound" {
  security_group_id = aws_security_group.app.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "Allow all outbound traffic from app tasks"
}

# Database security group — RDS PostgreSQL.
resource "aws_security_group" "database" {
  name        = "${var.name_prefix}-sg-db"
  description = "Security group for RDS PostgreSQL"
  vpc_id      = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.name_prefix}-sg-db" })
}

resource "aws_vpc_security_group_ingress_rule" "database_from_app" {
  security_group_id            = aws_security_group.database.id
  referenced_security_group_id = aws_security_group.app.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "Allow PostgreSQL from app security group"
}
