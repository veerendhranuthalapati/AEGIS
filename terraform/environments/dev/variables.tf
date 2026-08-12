variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "project_name" {
  type    = string
  default = "aegis"
}

variable "vpc_cidr" {
  type    = string
  default = "10.10.0.0/16"
}

variable "availability_zones" {
  type    = list(string)
  default = ["us-east-1a", "us-east-1b"]
}

variable "db_master_username" {
  type    = string
  default = "aegis_admin"
}

variable "db_name" {
  type    = string
  default = "aegis"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_backup_retention_days" {
  type    = number
  default = 7
}

variable "db_deletion_protection" {
  type        = bool
  default     = false
  description = "Set true for production before first apply"
}

variable "db_skip_final_snapshot" {
  type        = bool
  default     = true
  description = "Set false for production before first apply"
}

variable "acm_certificate_arn" {
  type        = string
  description = "Validated ACM certificate for the public ALB hostname"
  default     = "REPLACE_WITH_ACM_CERTIFICATE_ARN"
}

variable "backend_image" {
  type        = string
  description = "ECR image URI for the AEGIS backend task"
  default     = "REPLACE_WITH_ECR_IMAGE"
}

variable "worker_image" {
  type        = string
  description = "ECR image URI for the correlation worker (usually same as backend)"
  default     = "REPLACE_WITH_ECR_IMAGE"
}

variable "app_environment" {
  type        = string
  description = "Value for the AEGIS ENVIRONMENT env var (use production for prod stacks)"
  default     = "development"
}

output "vpc_id" {
  value = module.network.vpc_id
}

output "alb_dns_name" {
  value = module.ecs.alb_dns_name
}

output "rds_endpoint" {
  value     = module.rds.endpoint
  sensitive = true
}

output "rds_master_user_secret_arn" {
  value     = module.rds.master_user_secret_arn
  sensitive = true
}

output "database_url_secret_arn" {
  value     = module.rds.database_url_secret_arn
  sensitive = true
}

output "evidence_bucket" {
  value = module.s3.bucket_name
}

output "events_queue_url" {
  value = module.sqs.queue_url
}

output "jwt_secret_arn" {
  value     = module.iam.jwt_secret_arn
  sensitive = true
}
