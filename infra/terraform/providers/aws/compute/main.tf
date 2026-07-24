# =============================================================================
# Compute — ECS Fargate cluster, task definitions, services, and the ALB
# (source: migrate/ecs.tf, migrate/alb.tf). Mirrors the Azure compute module
# (Container Apps + built-in ingress). The ALB lives here because ingress is a
# compute concern, matching Container Apps' internal ingress.
# =============================================================================

# ─── ECS cluster ──────────────────────────────────────────────────────────────
resource "aws_ecs_cluster" "this" {
  name = local.cluster_name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = merge(var.tags, { Name = local.cluster_name })
}

resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name       = aws_ecs_cluster.this.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 1
  }
}

# ─── Task definitions ─────────────────────────────────────────────────────────
resource "aws_ecs_task_definition" "api" {
  family                   = local.api_service_name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.task_role_arn

  container_definitions = jsonencode([
    merge(
      {
        name         = local.api_container_name
        image        = var.api_image
        essential    = true
        portMappings = [{ containerPort = var.api_target_port, protocol = "tcp" }]
        environment  = local.api_environment
        secrets      = local.api_secrets

        logConfiguration = {
          logDriver = "awslogs"
          options = {
            "awslogs-group"         = var.api_log_group_name
            "awslogs-region"        = var.aws_region
            "awslogs-stream-prefix" = "api"
          }
        }

        healthCheck = {
          command     = ["CMD-SHELL", "curl -f http://localhost:${var.api_target_port}/health || exit 1"]
          interval    = 30
          timeout     = 5
          retries     = 3
          startPeriod = 60
        }
      },
      local.repository_credentials != null ? { repositoryCredentials = local.repository_credentials } : {}
    )
  ])

  tags = merge(var.tags, { Name = local.api_service_name })
}

resource "aws_ecs_task_definition" "worker" {
  family                   = local.worker_service_name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.task_role_arn

  container_definitions = jsonencode([
    merge(
      {
        name        = local.worker_container_name
        image       = var.worker_image
        essential   = true
        environment = local.worker_environment
        secrets     = local.worker_secrets

        logConfiguration = {
          logDriver = "awslogs"
          options = {
            "awslogs-group"         = var.worker_log_group_name
            "awslogs-region"        = var.aws_region
            "awslogs-stream-prefix" = "worker"
          }
        }
      },
      local.repository_credentials != null ? { repositoryCredentials = local.repository_credentials } : {}
    )
  ])

  tags = merge(var.tags, { Name = local.worker_service_name })
}

resource "aws_ecs_task_definition" "web" {
  family                   = local.web_service_name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.web_cpu
  memory                   = var.web_memory
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.task_role_arn

  container_definitions = jsonencode([
    merge(
      {
        name         = local.web_container_name
        image        = var.web_image
        essential    = true
        portMappings = [{ containerPort = var.web_target_port, protocol = "tcp" }]
        environment  = local.web_environment
        secrets      = local.web_secrets

        logConfiguration = {
          logDriver = "awslogs"
          options = {
            "awslogs-group"         = var.web_log_group_name
            "awslogs-region"        = var.aws_region
            "awslogs-stream-prefix" = "web"
          }
        }

        healthCheck = {
          command     = ["CMD-SHELL", "curl -f http://localhost:${var.web_target_port}/api/health || exit 1"]
          interval    = 30
          timeout     = 5
          retries     = 3
          startPeriod = 60
        }
      },
      local.repository_credentials != null ? { repositoryCredentials = local.repository_credentials } : {}
    )
  ])

  tags = merge(var.tags, { Name = local.web_service_name })
}

# ─── Application Load Balancer ────────────────────────────────────────────────
resource "aws_lb" "this" {
  name               = "${var.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_security_group_id]
  subnets            = var.public_subnet_ids

  tags = merge(var.tags, { Name = "${var.name_prefix}-alb" })
}

resource "aws_lb_target_group" "web" {
  name        = "${var.name_prefix}-web"
  port        = var.web_target_port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/api/health"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-tg-web" })
}

resource "aws_lb_target_group" "api" {
  name        = "${var.name_prefix}-api"
  port        = var.api_target_port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/health"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-tg-api" })
}

# ─── Listeners ────────────────────────────────────────────────────────────────
resource "aws_lb_listener" "http" {
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

resource "aws_lb_listener" "https" {
  count             = local.https_enabled ? 1 : 0
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

# Route the API paths to the API target group.
resource "aws_lb_listener_rule" "api" {
  count        = local.https_enabled ? 1 : 0
  listener_arn = aws_lb_listener.https[0].arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = ["/api/v1/*", "/health", "/metrics", "/chat", "/reports/*"]
    }
  }
}

# ─── Services ─────────────────────────────────────────────────────────────────
resource "aws_ecs_service" "api" {
  name            = local.api_service_name
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = local.api_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.app_subnet_ids
    security_groups  = [var.app_security_group_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = local.api_container_name
    container_port   = var.api_target_port
  }

  # desired_count is managed by application autoscaling / scale-to-zero, not by
  # Terraform, once the service is running.
  lifecycle {
    ignore_changes = [desired_count]
  }

  depends_on = [aws_lb_listener.https]
}

resource "aws_ecs_service" "worker" {
  name            = local.worker_service_name
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = local.worker_desired_count
  launch_type     = "FARGATE"

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
  desired_count   = local.web_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.app_subnet_ids
    security_groups  = [var.app_security_group_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.web.arn
    container_name   = local.web_container_name
    container_port   = var.web_target_port
  }

  lifecycle {
    ignore_changes = [desired_count]
  }

  depends_on = [aws_lb_listener.https]
}
