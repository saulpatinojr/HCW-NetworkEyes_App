output "cluster_id" {
  description = "ECS cluster ID"
  value       = aws_ecs_cluster.this.id
}

output "cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.this.name
}

output "alb_arn" {
  description = "ARN of the Application Load Balancer"
  value       = aws_lb.this.arn
}

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = aws_lb.this.dns_name
}

output "api_service_name" {
  description = "ECS service name for cna-api"
  value       = aws_ecs_service.api.name
}

output "worker_service_name" {
  description = "ECS service name for cna-worker"
  value       = aws_ecs_service.worker.name
}

output "web_service_name" {
  description = "ECS service name for cna-web"
  value       = aws_ecs_service.web.name
}

output "web_target_group_arn" {
  description = "ARN of the cna-web ALB target group"
  value       = aws_lb_target_group.web.arn
}
