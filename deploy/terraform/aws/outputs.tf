output "ecr_repository_url" {
  description = "ECR repository URL — use this as the image.repository in tinker-values.yaml"
  value       = aws_ecr_repository.tinker.repository_url
}

output "task_role_arn" {
  description = "ARN of the ECS task role (tinker-task)"
  value       = aws_iam_role.tinker_task.arn
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.tinker.name
}

output "log_group_name" {
  description = "CloudWatch log group for Tinker server logs"
  value       = aws_cloudwatch_log_group.tinker.name
}
