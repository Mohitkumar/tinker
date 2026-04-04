terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ── ECR repository ─────────────────────────────────────────────────────────────

resource "aws_ecr_repository" "tinker" {
  name                 = "tinker"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# ── IAM — task role (read-only observability) ──────────────────────────────────

resource "aws_iam_role" "tinker_task" {
  name = "tinker-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "tinker_readonly" {
  name = "TinkerReadOnly"
  role = aws_iam_role.tinker_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:StartQuery", "logs:GetQueryResults",
          "logs:DescribeLogGroups", "logs:FilterLogEvents", "logs:GetLogEvents",
        ]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["cloudwatch:GetMetricData", "cloudwatch:ListMetrics", "cloudwatch:DescribeAlarms"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["xray:GetTraceSummaries", "xray:BatchGetTraces"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = "arn:aws:secretsmanager:${var.aws_region}:*:secret:tinker/*"
      },
    ]
  })
}

resource "aws_iam_role" "tinker_execution" {
  name = "tinker-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.tinker_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# ── CloudWatch log group ───────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "tinker" {
  name              = "/ecs/tinker"
  retention_in_days = 30
}

# ── ECS cluster ───────────────────────────────────────────────────────────────

resource "aws_ecs_cluster" "tinker" {
  name = var.cluster_name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

# ── ECS task definition ───────────────────────────────────────────────────────

data "aws_caller_identity" "current" {}

resource "aws_ecs_task_definition" "tinker" {
  family                   = "tinker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  task_role_arn            = aws_iam_role.tinker_task.arn
  execution_role_arn       = aws_iam_role.tinker_execution.arn

  container_definitions = jsonencode([{
    name  = "tinker"
    image = "${aws_ecr_repository.tinker.repository_url}:${var.image_tag}"

    portMappings = [{ containerPort = 8000, protocol = "tcp" }]

    environment = [
      { name = "TINKER_BACKEND",     value = var.tinker_backend },
      { name = "AWS_REGION",         value = var.aws_region },
      { name = "TINKER_SERVER_PORT", value = "8000" },
    ]

    secrets = [
      {
        name      = "ANTHROPIC_API_KEY"
        valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:tinker/anthropic-api-key"
      },
      {
        name      = "TINKER_API_KEYS"
        valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:tinker/api-keys"
      },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.tinker.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "tinker"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health')\""]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 15
    }
  }])
}

# ── ECS service ───────────────────────────────────────────────────────────────

resource "aws_ecs_service" "tinker" {
  name            = "tinker"
  cluster         = aws_ecs_cluster.tinker.id
  task_definition = aws_ecs_task_definition.tinker.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = var.security_group_ids
    assign_public_ip = false
  }

  # Uncomment to attach an ALB target group
  # load_balancer {
  #   target_group_arn = aws_lb_target_group.tinker.arn
  #   container_name   = "tinker"
  #   container_port   = 8000
  # }
}
