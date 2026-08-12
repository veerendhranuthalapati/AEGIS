variable "environment" { type = string }
variable "bucket_name" { type = string }

resource "aws_s3_bucket" "evidence" {
  bucket = var.bucket_name
}

resource "aws_s3_bucket_public_access_block" "evidence" {
  bucket                  = aws_s3_bucket.evidence.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

output "bucket_name" { value = aws_s3_bucket.evidence.id }
output "bucket_arn" { value = aws_s3_bucket.evidence.arn }
