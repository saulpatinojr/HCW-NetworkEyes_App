# =============================================================================
# Observability — ECS log groups + baseline alarms (source: the /ecs/* groups in
# migrate/ecs.tf). Mirrors the Azure observability module. Created BEFORE the
# compute module, which consumes the three log-group names.
# =============================================================================

# ─── ECS service log groups ───────────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "api" {
  name              = local.api_log_group_name
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn

  tags = merge(var.tags, { Name = "${var.name_prefix}-api-logs" })
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = local.worker_log_group_name
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn

  tags = merge(var.tags, { Name = "${var.name_prefix}-worker-logs" })
}

resource "aws_cloudwatch_log_group" "web" {
  name              = local.web_log_group_name
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn

  tags = merge(var.tags, { Name = "${var.name_prefix}-web-logs" })
}

# ─── Alarm notification topic ─────────────────────────────────────────────────
# Created only when the caller does not supply an existing topic ARN.
resource "aws_sns_topic" "alarms" {
  count = var.sns_topic_arn == null ? 1 : 0
  name  = "${var.name_prefix}-alarms"

  tags = merge(var.tags, { Name = "${var.name_prefix}-alarms" })
}

# ─── ECS alarms (per service) ─────────────────────────────────────────────────
resource "aws_cloudwatch_metric_alarm" "ecs_cpu" {
  for_each = local.alarm_services

  alarm_name          = "${each.value}-cpu-high"
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.alarm_thresholds.ecs_cpu_percent
  evaluation_periods  = 3
  period              = 300
  statistic           = "Average"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    ClusterName = local.cluster_name
    ServiceName = each.value
  }

  tags = merge(var.tags, { Name = "${each.value}-cpu-high" })
}

resource "aws_cloudwatch_metric_alarm" "ecs_memory" {
  for_each = local.alarm_services

  alarm_name          = "${each.value}-memory-high"
  namespace           = "AWS/ECS"
  metric_name         = "MemoryUtilization"
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.alarm_thresholds.ecs_memory_percent
  evaluation_periods  = 3
  period              = 300
  statistic           = "Average"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    ClusterName = local.cluster_name
    ServiceName = each.value
  }

  tags = merge(var.tags, { Name = "${each.value}-memory-high" })
}

# ─── RDS alarms ───────────────────────────────────────────────────────────────
resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  count = var.enable_alarms ? 1 : 0

  alarm_name          = "${local.db_instance_id}-cpu-high"
  namespace           = "AWS/RDS"
  metric_name         = "CPUUtilization"
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.alarm_thresholds.rds_cpu_percent
  evaluation_periods  = 3
  period              = 300
  statistic           = "Average"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    DBInstanceIdentifier = local.db_instance_id
  }

  tags = merge(var.tags, { Name = "${local.db_instance_id}-cpu-high" })
}

resource "aws_cloudwatch_metric_alarm" "rds_free_storage" {
  count = var.enable_alarms ? 1 : 0

  alarm_name          = "${local.db_instance_id}-free-storage-low"
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  comparison_operator = "LessThanThreshold"
  threshold           = var.alarm_thresholds.rds_free_storage_bytes
  evaluation_periods  = 1
  period              = 300
  statistic           = "Average"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    DBInstanceIdentifier = local.db_instance_id
  }

  tags = merge(var.tags, { Name = "${local.db_instance_id}-free-storage-low" })
}

# ─── ALB alarm ────────────────────────────────────────────────────────────────
# Gated on alb_arn_suffix because the ALB lives in the compute module (deployed
# after observability); wire the suffix back in once compute has applied.
resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  count = var.enable_alarms && var.alb_arn_suffix != null ? 1 : 0

  alarm_name          = "${var.name_prefix}-alb-5xx-high"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_ELB_5XX_Count"
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.alarm_thresholds.alb_5xx_count
  evaluation_periods  = 1
  period              = 300
  statistic           = "Sum"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    LoadBalancer = var.alb_arn_suffix
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-alb-5xx-high" })
}

# ─── Dashboard (optional) ─────────────────────────────────────────────────────
resource "aws_cloudwatch_dashboard" "platform" {
  count          = var.enable_dashboard ? 1 : 0
  dashboard_name = "${var.name_prefix}-platform"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "ECS CPU Utilization"
          region = data.aws_region.current.name
          view   = "timeSeries"
          metrics = [
            for svc in values(local.services) :
            ["AWS/ECS", "CPUUtilization", "ClusterName", local.cluster_name, "ServiceName", svc]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "RDS CPU Utilization"
          region = data.aws_region.current.name
          view   = "timeSeries"
          metrics = [
            ["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", local.db_instance_id]
          ]
        }
      },
    ]
  })
}

data "aws_region" "current" {}
