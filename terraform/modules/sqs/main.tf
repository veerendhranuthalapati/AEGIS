variable "environment" { type = string }
variable "queue_name" { type = string }

resource "aws_sqs_queue" "events" {
  name                       = var.queue_name
  visibility_timeout_seconds = 60
  message_retention_seconds  = 86400
  sqs_managed_sse_enabled    = true
}

output "queue_arn" { value = aws_sqs_queue.events.arn }
output "queue_url" { value = aws_sqs_queue.events.url }
