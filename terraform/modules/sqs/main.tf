variable "environment" { type = string }
variable "queue_name" { type = string }

resource "aws_sqs_queue" "events_dlq" {
  name                      = "${var.queue_name}-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "events" {
  name                       = var.queue_name
  visibility_timeout_seconds = 60
  message_retention_seconds  = 86400
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.events_dlq.arn
    maxReceiveCount     = 5
  })
}

output "queue_arn" { value = aws_sqs_queue.events.arn }
output "queue_url" { value = aws_sqs_queue.events.url }
output "dlq_arn" { value = aws_sqs_queue.events_dlq.arn }
