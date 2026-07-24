output "api_log_group_name" {
  description = "CloudWatch log group name for the API service. Passed to the compute module."
  value       = aws_cloudwatch_log_group.api.name
}

output "worker_log_group_name" {
  description = "CloudWatch log group name for the worker service. Passed to the compute module."
  value       = aws_cloudwatch_log_group.worker.name
}

output "web_log_group_name" {
  description = "CloudWatch log group name for the web service. Passed to the compute module."
  value       = aws_cloudwatch_log_group.web.name
}

output "log_group_arns" {
  description = "Map of service => CloudWatch log group ARN."
  value = {
    api    = aws_cloudwatch_log_group.api.arn
    worker = aws_cloudwatch_log_group.worker.arn
    web    = aws_cloudwatch_log_group.web.arn
  }
}

output "dashboard_name" {
  description = "CloudWatch dashboard name, or null when the dashboard is disabled."
  value       = one(aws_cloudwatch_dashboard.platform[*].dashboard_name)
}

output "alarms_topic_arn" {
  description = "SNS topic ARN used for alarm notifications (module-created or supplied), or null when no topic is in use."
  value       = local.alarms_topic_arn
}
