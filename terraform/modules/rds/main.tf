variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "db_security_group_id" { type = string }
variable "master_username" { type = string }
variable "db_name" { type = string }
variable "instance_class" { type = string }
variable "backup_retention_period" { type = number }
variable "deletion_protection" {
  type    = bool
  default = false
}
variable "skip_final_snapshot" {
  type    = bool
  default = true
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.environment}-aegis-db"
  subnet_ids = var.private_subnet_ids
}

resource "aws_db_instance" "main" {
  identifier                  = "${var.environment}-aegis"
  engine                      = "postgres"
  engine_version              = "16"
  instance_class              = var.instance_class
  allocated_storage           = 20
  storage_encrypted           = true
  db_name                     = var.db_name
  username                    = var.master_username
  manage_master_user_password = true
  vpc_security_group_ids      = [var.db_security_group_id]
  db_subnet_group_name        = aws_db_subnet_group.main.name
  publicly_accessible         = false
  backup_retention_period     = var.backup_retention_period
  skip_final_snapshot       = var.skip_final_snapshot
  deletion_protection         = var.deletion_protection
  multi_az                    = false
}

# Application DATABASE_URL secret (value populated post-provision — see AWS_DEPLOYMENT.md).
# Password material lives in the RDS-managed master user secret; do not embed passwords here.
resource "aws_secretsmanager_secret" "database_url" {
  name        = "aegis/${var.environment}/rds-connection"
  description = "Full asyncpg DATABASE_URL for AEGIS ECS tasks"
}

output "endpoint" { value = aws_db_instance.main.endpoint }
output "instance_id" { value = aws_db_instance.main.id }
output "database_url_secret_arn" { value = aws_secretsmanager_secret.database_url.arn }
output "master_user_secret_arn" {
  value       = aws_db_instance.main.master_user_secret[0].secret_arn
  description = "RDS-managed master password secret (JSON with username/password)"
}
