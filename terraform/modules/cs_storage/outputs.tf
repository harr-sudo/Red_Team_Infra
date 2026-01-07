# CS Storage Module - Outputs
# =============================================================================

output "bucket_name" {
  description = "Name of the S3 bucket for CS files"
  value       = aws_s3_bucket.cs_files.id
}

output "bucket_arn" {
  description = "ARN of the S3 bucket"
  value       = aws_s3_bucket.cs_files.arn
}

output "bucket_domain_name" {
  description = "Domain name of the S3 bucket"
  value       = aws_s3_bucket.cs_files.bucket_domain_name
}

output "iam_role_arn" {
  description = "ARN of the IAM role for CS download"
  value       = aws_iam_role.cs_download.arn
}

output "iam_role_name" {
  description = "Name of the IAM role"
  value       = aws_iam_role.cs_download.name
}

output "instance_profile_arn" {
  description = "ARN of the instance profile"
  value       = aws_iam_instance_profile.cs_download.arn
}

output "instance_profile_name" {
  description = "Name of the instance profile (use this for EC2 instances)"
  value       = aws_iam_instance_profile.cs_download.name
}

output "upload_command" {
  description = "Example command to upload CS archive to S3"
  value       = "aws s3 cp cobaltstrike.tar.gz s3://${aws_s3_bucket.cs_files.id}/"
}

