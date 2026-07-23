# =============================================================================
# ECS Cluster + Services (equivalent to Azure Container Apps)
# =============================================================================

resource "aws_ecs_cluster" "main" {
  name = "${local.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${local.name_prefix}"
  retention_in_days = 30
}

# ─── API Service ──────────────────────────────────────────────────────────────
resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name_prefix}-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name  = "cna-api"
    image = var.api_image
    portMappings = [{ containerPort = 8080, protocol = "tcp" }]

    repositoryCredentials = var.dockerhub_username != "" ? {
      credentialsParameter = aws_secretsmanager_secret.dockerhub[0].arn
    } : null

    environment = [
      { name = "CNA_STORAGE_BUCKET", value = aws_s3_bucket.artifacts.id },
      { name = "AWS_REGION", value = var.aws_region },
      { name = "OPENAI_ENDPOINT", value = var.openai_endpoint },
      { name = "OPENAI_DEPLOYMENT", value = var.openai_deployment },
    ]

    secrets = [
      { name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.database_url.arn },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "api"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
  }])
}

resource "aws_ecs_service" "api" {
  name            = "${local.name_prefix}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "cna-api"
    container_port   = 8080
  }

  depends_on = [aws_lb_listener.https]
}

# ─── Worker Service ───────────────────────────────────────────────────────────
resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.name_prefix}-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name  = "cna-worker"
    image = var.worker_image

    repositoryCredentials = var.dockerhub_username != "" ? {
      credentialsParameter = aws_secretsmanager_secret.dockerhub[0].arn
    } : null

    environment = [
      { name = "CNA_STORAGE_BUCKET", value = aws_s3_bucket.artifacts.id },
      { name = "AWS_REGION", value = var.aws_region },
      { name = "OPENAI_ENDPOINT", value = var.openai_endpoint },
      { name = "OPENAI_DEPLOYMENT", value = var.openai_deployment },
    ]

    secrets = [
      { name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.database_url.arn },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "worker"
      }
    }
  }])
}

resource "aws_ecs_service" "worker" {
  name            = "${local.name_prefix}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }
}

# ─── Web Service (Next.js) ────────────────────────────────────────────────────
resource "aws_ecs_task_definition" "web" {
  family                   = "${local.name_prefix}-web"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.web_cpu
  memory                   = var.web_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name  = "cna-web"
    image = var.web_image
    portMappings = [{ containerPort = 3000, protocol = "tcp" }]

    repositoryCredentials = var.dockerhub_username != "" ? {
      credentialsParameter = aws_secretsmanager_secret.dockerhub[0].arn
    } : null

    environment = [
      { name = "NEXTAUTH_URL", value = var.nextauth_url },
      { name = "AUTH_TRUST_HOST", value = "true" },
      { name = "AZURE_AD_TENANT_ID", value = var.entra_tenant_id },
      { name = "AZURE_AD_CLIENT_ID", value = var.entra_client_id },
      { name = "CNA_API_INTERNAL_URL", value = "http://${local.name_prefix}-api.${local.name_prefix}:8080" },
      { name = "CNA_STORAGE_BUCKET", value = aws_s3_bucket.artifacts.id },
      { name = "AWS_REGION", value = var.aws_region },
      { name = "OPENAI_ENDPOINT", value = var.openai_endpoint },
      { name = "OPENAI_DEPLOYMENT", value = var.openai_deployment },
    ]

    secrets = [
      { name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.database_url.arn },
      { name = "AUTH_SECRET", valueFrom = aws_secretsmanager_secret.nextauth_secret.arn },
      { name = "AZURE_AD_CLIENT_SECRET", valueFrom = aws_secretsmanager_secret.entra_client_secret.arn },
      { name = "CREDENTIAL_ENCRYPTION_KEY", valueFrom = aws_secretsmanager_secret.credential_encryption_key.arn },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "web"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:3000/api/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
  }])
}

resource "aws_ecs_service" "web" {
  name            = "${local.name_prefix}-web"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.web.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.web.arn
    container_name   = "cna-web"
    container_port   = 3000
  }

  depends_on = [aws_lb_listener.https]
}
