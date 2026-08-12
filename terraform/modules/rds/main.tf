variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "db_security_group_id" { type = string }
variable "master_username" { type = string }
variable "db_name" { type = string }
variable "instance_class" { type = string }
variable "backup_retention_period" { type = number }

resource "aws_db_subnet_group" "main" {
  name       = "${var.environment}-aegis-db"
  subnet_ids = var.private_subnet_ids
}

resource "aws_db_instance" "main" {
  identifier                 = "${var.environment}-aegis"
  engine                     = "postgres"
  engine_version             = "16"
  instance_class             = var.instance_class
  allocated_storage          = 20
  storage_encrypted          = true
  db_name                    = var.db_name
  username                   = var.master_username
  manage_master_user_password = true
  vpc_security_group_ids     = [var.db_security_group_id]
  db_subnet_group_name       = aws_db_subnet_group.main.name
  publicly_accessible        = false
  backup_retention_period    = var.backup_retention_period
  skip_final_snapshot        = true
  deletion_protection        = false
}

resource "aws_secretsmanager_secret" "database_url" {
  name = "aegis/${var.environment}/rds-connection"
}

output "endpoint" { value = aws_db_instance.main.endpoint }
output "instance_id" { value = aws_db_instance.main.id }
output "database_url_secret_arn" { value = aws_secretsmanager_secret.database_url.arn }
