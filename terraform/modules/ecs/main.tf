variable "environment" { type = string }
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
variable "evidence_bucket_arn" { type = string }
variable "events_queue_arn" { type = string }

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
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate.placeholder.arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
}

# Placeholder cert — replace with validated ACM cert before deploy
resource "aws_acm_certificate" "placeholder" {
  domain_name       = "placeholder.aegis.local"
  validation_method = "DNS"
  lifecycle {
    create_before_destroy = true
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

  container_definitions = jsonencode([
    {
      name  = "aegis-backend"
      image = "REPLACE_WITH_ECR_IMAGE"
      portMappings = [{ containerPort = 8000, protocol = "tcp" }]
      secrets = [
        { name = "DATABASE_URL", valueFrom = var.database_url_secret_arn },
        { name = "SECRET_KEY", valueFrom = var.jwt_secret_arn }
      ]
      environment = [
        { name = "ENVIRONMENT", value = var.environment }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = "/ecs/${var.environment}-aegis"
          awslogs-region        = "us-east-1"
          awslogs-stream-prefix = "backend"
        }
      }
    }
  ])
}

resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${var.environment}-aegis"
  retention_in_days = 14
}

output "cluster_name" { value = aws_ecs_cluster.main.name }
output "alb_arn" { value = aws_lb.main.arn }
output "alb_arn_suffix" { value = aws_lb.main.arn_suffix }
output "alb_dns_name" { value = aws_lb.main.dns_name }
