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

data "aws_caller_identity" "current" {}

locals {
  events_queue_name = "${var.project_name}-${var.environment}-events"
  evidence_bucket   = "${var.project_name}-${var.environment}-evidence"
}

module "network" {
  source = "../../modules/network"

  environment        = var.environment
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
}

module "rds" {
  source = "../../modules/rds"

  environment             = var.environment
  private_subnet_ids      = module.network.private_subnet_ids
  db_security_group_id    = module.network.rds_security_group_id
  master_username         = var.db_master_username
  db_name                 = var.db_name
  instance_class          = var.db_instance_class
  backup_retention_period = var.db_backup_retention_days
  deletion_protection     = var.db_deletion_protection
  skip_final_snapshot     = var.db_skip_final_snapshot
}

module "s3" {
  source = "../../modules/s3"

  environment = var.environment
  bucket_name = local.evidence_bucket
}

module "sqs" {
  source = "../../modules/sqs"

  environment = var.environment
  queue_name  = local.events_queue_name
}

module "iam" {
  source = "../../modules/iam"

  environment             = var.environment
  project                 = var.project_name
  aws_region              = var.aws_region
  aws_account_id          = data.aws_caller_identity.current.account_id
  database_url_secret_arn = module.rds.database_url_secret_arn
  events_queue_name       = local.events_queue_name
  evidence_bucket_name    = local.evidence_bucket
}

module "ecs" {
  source = "../../modules/ecs"

  environment             = var.environment
  aws_region              = var.aws_region
  acm_certificate_arn     = var.acm_certificate_arn
  vpc_id                  = module.network.vpc_id
  private_subnet_ids      = module.network.private_subnet_ids
  public_subnet_ids       = module.network.public_subnet_ids
  alb_security_group_id   = module.network.alb_security_group_id
  ecs_security_group_id   = module.network.ecs_security_group_id
  task_execution_role_arn = module.iam.ecs_execution_role_arn
  task_role_arn           = module.iam.ecs_task_role_arn
  worker_task_role_arn    = module.iam.worker_task_role_arn
  database_url_secret_arn = module.rds.database_url_secret_arn
  jwt_secret_arn          = module.iam.jwt_secret_arn
  backend_image           = var.backend_image
  worker_image            = var.worker_image
  app_environment         = var.app_environment
}

module "waf" {
  source = "../../modules/waf"

  environment = var.environment
  alb_arn     = module.ecs.alb_arn
}

module "monitoring" {
  source = "../../modules/monitoring"

  environment       = var.environment
  ecs_cluster       = module.ecs.cluster_name
  alb_arn_suffix    = module.ecs.alb_arn_suffix
  rds_instance_id   = module.rds.instance_id
  events_queue_name = local.events_queue_name
}
