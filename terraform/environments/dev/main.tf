terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "aegis"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

module "network" {
  source = "../../modules/network"

  environment        = var.environment
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
}

module "iam" {
  source = "../../modules/iam"

  environment = var.environment
  project     = "aegis"
}

module "rds" {
  source = "../../modules/rds"

  environment             = var.environment
  vpc_id                  = module.network.vpc_id
  private_subnet_ids      = module.network.private_subnet_ids
  db_security_group_id    = module.network.rds_security_group_id
  master_username         = var.db_master_username
  db_name                 = var.db_name
  instance_class          = var.db_instance_class
  backup_retention_period = var.db_backup_retention_days
}

module "s3" {
  source = "../../modules/s3"

  environment = var.environment
  bucket_name = "${var.project_name}-${var.environment}-evidence"
}

module "sqs" {
  source = "../../modules/sqs"

  environment = var.environment
  queue_name  = "${var.project_name}-${var.environment}-events"
}

module "ecs" {
  source = "../../modules/ecs"

  environment          = var.environment
  vpc_id               = module.network.vpc_id
  private_subnet_ids   = module.network.private_subnet_ids
  public_subnet_ids    = module.network.public_subnet_ids
  alb_security_group_id = module.network.alb_security_group_id
  ecs_security_group_id = module.network.ecs_security_group_id
  task_execution_role_arn = module.iam.ecs_execution_role_arn
  task_role_arn           = module.iam.ecs_task_role_arn
  worker_task_role_arn    = module.iam.worker_task_role_arn
  database_url_secret_arn = module.rds.database_url_secret_arn
  jwt_secret_arn          = module.iam.jwt_secret_arn
  evidence_bucket_arn     = module.s3.bucket_arn
  events_queue_arn        = module.sqs.queue_arn
}

module "waf" {
  source = "../../modules/waf"

  environment = var.environment
  alb_arn     = module.ecs.alb_arn
}

module "monitoring" {
  source = "../../modules/monitoring"

  environment   = var.environment
  ecs_cluster   = module.ecs.cluster_name
  alb_arn_suffix = module.ecs.alb_arn_suffix
  rds_instance_id = module.rds.instance_id
}
