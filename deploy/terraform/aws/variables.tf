variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "tinker_backend" {
  description = "Tinker observability backend (cloudwatch | gcp | azure | grafana | datadog | elastic)"
  type        = string
  default     = "cloudwatch"
}

variable "cluster_name" {
  description = "ECS cluster name"
  type        = string
  default     = "tinker"
}

variable "image_tag" {
  description = "Docker image tag to deploy"
  type        = string
  default     = "latest"
}

variable "subnet_ids" {
  description = "VPC subnet IDs for the ECS service (private subnets recommended)"
  type        = list(string)
}

variable "security_group_ids" {
  description = "Security group IDs for the ECS service"
  type        = list(string)
}

variable "tinker_api_keys_hash" {
  description = "SHA-256 hash of the Tinker API key (stored in Secrets Manager separately)"
  type        = string
  sensitive   = true
  default     = ""
}
