variable "environment" { type = string }
variable "aws_region" { type = string }
variable "acm_certificate_arn" {
  type        = string
  description = "Validated ACM certificate ARN for the public hostname (replace before deploy)"
}
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "public_subnet_ids" { type = list(string) }
variable "alb_security_group_id" { type = string }
variable "ecs_security_group_id" { type = string }
variable "task_execution_role_arn" { type = string }
variable "task_role_arn" { type = string }
variable "worker_task_role_arn" { type = string }
variable "database_url_secret_arn" { type = string }
variable "jwt_secret_arn" { type = string }
variable "backend_image" {
  type        = string
  description = "ECR image URI for the AEGIS backend container"
  default     = "REPLACE_WITH_ECR_IMAGE"
}
variable "worker_image" {
  type        = string
  description = "ECR image URI for the correlation worker (same image, different command)"
  default     = "REPLACE_WITH_ECR_IMAGE"
}
variable "app_environment" {
  type        = string
  description = "AEGIS ENVIRONMENT setting (development | production)"
  default     = "development"
}

resource "aws_ecs_cluster" "main" {
  name = "${var.environment}-aegis"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_lb" "main" {
  name               = "${var.environment}-aegis-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_security_group_id]
  subnets            = var.public_subnet_ids
}

resource "aws_lb_target_group" "backend" {
  name        = "${var.environment}-aegis-api"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"
  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    matcher             = "200"
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.acm_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
}

locals {
  backend_container = {
    name  = "aegis-backend"
    image = var.backend_image
    user  = "10001:10001"
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    secrets = [
      { name = "DATABASE_URL", valueFrom = var.database_url_secret_arn },
      { name = "SECRET_KEY", valueFrom = var.jwt_secret_arn }
    ]
    environment = [
      { name = "ENVIRONMENT", value = var.app_environment },
      { name = "AEGIS_IN_PROCESS_WORKER", value = "false" }
    ]
    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health')\""]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 15
    }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.ecs.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "backend"
      }
    }
  }

  worker_container = {
    name    = "aegis-worker"
    image   = var.worker_image
    user    = "10001:10001"
    command = ["python", "-m", "app.worker.main"]
    secrets = [
      { name = "DATABASE_URL", valueFrom = var.database_url_secret_arn },
      { name = "SECRET_KEY", valueFrom = var.jwt_secret_arn }
    ]
    environment = [
      { name = "ENVIRONMENT", value = var.app_environment }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.ecs.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "worker"
      }
    }
  }
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.environment}-aegis-backend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.task_role_arn
  container_definitions    = jsonencode([local.backend_container])
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.environment}-aegis-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.worker_task_role_arn
  container_definitions    = jsonencode([local.worker_container])
}

resource "aws_ecs_service" "backend" {
  name            = "${var.environment}-aegis-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = 2
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.ecs_security_group_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "aegis-backend"
    container_port   = 8000
  }

  # Replace placeholder image and ACM ARN before first deploy.
  depends_on = [aws_lb_listener.https]
}

resource "aws_ecs_service" "worker" {
  name            = "${var.environment}-aegis-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.ecs_security_group_id]
    assign_public_ip = false
  }
}

resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${var.environment}-aegis"
  retention_in_days = 14
}

output "cluster_name" { value = aws_ecs_cluster.main.name }
output "alb_arn" { value = aws_lb.main.arn }
output "alb_arn_suffix" { value = aws_lb.main.arn_suffix }
output "alb_dns_name" { value = aws_lb.main.dns_name }
output "backend_service_name" { value = aws_ecs_service.backend.name }
output "worker_service_name" { value = aws_ecs_service.worker.name }
