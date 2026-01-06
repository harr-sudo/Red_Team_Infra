# C2 Team Server Module Outputs

output "c2_team_server_instance_ids" {
  description = "IDs of the C2 team server instances"
  value       = aws_instance.c2_team_server[*].id
}

output "c2_team_server_private_ips" {
  description = "Private IP addresses of the C2 team server instances"
  value       = aws_instance.c2_team_server[*].private_ip
}

output "c2_team_server_elastic_ips" {
  description = "Elastic IP addresses of the C2 team server instances (if enabled)"
  value       = var.enable_elastic_ips ? aws_eip.c2_team_server_eip[*].public_ip : []
}

