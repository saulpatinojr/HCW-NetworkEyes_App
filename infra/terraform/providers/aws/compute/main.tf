# NOTE: The ECS cluster, task definitions, and services live here.
# CloudWatch log groups for each service are created in this module
# so platform-owned observability resources are managed in the same
# state that creates the workload — no cross-state dependency.

# ─── ECS Cluster ──────────────────────────────────────────────────────────────

resource "aws_ecs_cluster" "this" {
  name = local.cluster_name
  tags = var.tags

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name       = aws_ecs_cluster.this.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    base              = 1
    weight            = 1
  }
}

# ─── CloudWatch log groups ────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${local.cluster_name}/api"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${local.cluster_name}/worker"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "web" {
  name              = "/ecs/${local.cluster_name}/web"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

# ─── Task definitions ─────────────────────────────────────────────────────────

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.cluster_name}-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.task_role_arn
  tags                     = var.tags

  container_definitions = jsonencode([{
    name      = "cna-api"
    image     = var.api_image
    essential = true

    portMappings = [{
      containerPort = var.api_target_port
      protocol      = "tcp"
    }]

    environment = [for k, v in var.api_environment : { name = k, value = v }]
    secrets     = [for k, v in var.api_secrets : { name = k, valueFrom = v }]

    healthCheck = {
      command     = ["CMD-SHELL", "curl -sf http://localhost:${var.api_target_port}/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }
  }])
}

# ─── cna-worker ───────────────────────────────────────────────────────────────
# Background job processor. No HTTP ingress — processes discovery, analysis,
# and delivery pipelines asynchronously. Equivalent to the Azure cna-worker
# Container App.

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.cluster_name}-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.task_role_arn
  tags                     = var.tags

  container_definitions = jsonencode([{
    name      = "cna-worker"
    image     = var.worker_image
    essential = true

    environment = [for k, v in var.worker_environment : { name = k, value = v }]
    secrets     = [for k, v in var.worker_secrets : { name = k, valueFrom = v }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.worker.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }
  }])
}

# ─── cna-web ──────────────────────────────────────────────────────────────────
# Next.js frontend + API routes. Public face of the CNA platform.
# CloudFront terminates TLS and WAF here. Port 3000.
# Equivalent to the Azure cna-web Container App behind Front Door.

resource "aws_ecs_task_definition" "web" {
  family                   = "${local.cluster_name}-web"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.web_cpu
  memory                   = var.web_memory
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.task_role_arn
  tags                     = var.tags

  container_definitions = jsonencode([{
    name      = "cna-web"
    image     = var.web_image
    essential = true

    portMappings = [{
      containerPort = var.web_target_port
      protocol      = "tcp"
    }]

    environment = [for k, v in var.web_environment : { name = k, value = v }]
    secrets     = [for k, v in var.web_secrets : { name = k, valueFrom = v }]

    healthCheck = {
      command     = ["CMD-SHELL", "curl -sf http://localhost:${var.web_target_port}/api/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.web.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }
  }])
}

# ─── ALB ──────────────────────────────────────────────────────────────────────

resource "aws_lb" "this" {
  name               = "${var.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_security_group_id]
  subnets            = var.public_subnet_ids
  tags               = var.tags
}

resource "aws_lb_target_group" "web" {
  name        = "${var.name_prefix}-tg-web"
  port        = var.web_target_port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/api/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
  }

  tags = var.tags
}

# HTTP → HTTPS redirect listener (always created).
resource "aws_lb_listener" "http_redirect" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# HTTPS listener — created only when an ACM certificate is provided.
resource "aws_lb_listener" "https" {
  count             = var.alb_certificate_arn != null ? 1 : 0
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.alb_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }
}

# ─── ECS Services ─────────────────────────────────────────────────────────────

resource "aws_ecs_service" "api" {
  name            = local.api_service_name
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.api.arn
  launch_type     = "FARGATE"
  desired_count   = var.enable_scale_to_zero ? 0 : var.api_min_count
  tags            = var.tags

  network_configuration {
    subnets          = var.app_subnet_ids
    security_groups  = [var.app_security_group_id]
    assign_public_ip = false
  }

  lifecycle {
    # Desired count is managed externally (auto-scaling / deploy pipeline).
    ignore_changes = [desired_count]
  }
}

resource "aws_ecs_service" "worker" {
  name            = local.worker_service_name
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.worker.arn
  launch_type     = "FARGATE"
  desired_count   = var.enable_scale_to_zero ? 0 : var.worker_min_count
  tags            = var.tags

  network_configuration {
    subnets          = var.app_subnet_ids
    security_groups  = [var.app_security_group_id]
    assign_public_ip = false
  }

  lifecycle {
    ignore_changes = [desired_count]
  }
}

resource "aws_ecs_service" "web" {
  name            = local.web_service_name
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.web.arn
  launch_type     = "FARGATE"
  desired_count   = var.enable_scale_to_zero ? 0 : var.web_min_count
  tags            = var.tags

  network_configuration {
    subnets          = var.app_subnet_ids
    security_groups  = [var.app_security_group_id]
    assign_public_ip = false
  }

  dynamic "load_balancer" {
    for_each = var.alb_certificate_arn != null ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.web.arn
      container_name   = "cna-web"
      container_port   = var.web_target_port
    }
  }

  lifecycle {
    ignore_changes = [desired_count]
  }

  depends_on = [aws_lb_listener.https]
}
