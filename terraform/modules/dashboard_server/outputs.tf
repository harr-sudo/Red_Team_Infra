output "dashboard_public_ip" {
  description = "Dashboard server public IP (EIP)"
  value       = aws_eip.dashboard.public_ip
}

output "dashboard_instance_id" {
  description = "Dashboard EC2 instance ID"
  value       = aws_instance.dashboard.id
}

output "dashboard_vpc_id" {
  description = "Dashboard VPC ID (for peering with deployment VPCs)"
  value       = aws_vpc.dashboard.id
}

output "dashboard_vpc_cidr" {
  description = "Dashboard VPC CIDR"
  value       = aws_vpc.dashboard.cidr_block
}

output "dashboard_sg_id" {
  description = "Dashboard security group ID"
  value       = aws_security_group.dashboard.id
}

output "tfstate_bucket" {
  description = "S3 bucket name for Terraform state"
  value       = aws_s3_bucket.tfstate.id
}

output "tflock_table" {
  description = "DynamoDB table for Terraform state locking"
  value       = aws_dynamodb_table.tflock.name
}
