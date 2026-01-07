# C2 Team Server Module Outputs
# =============================================================================

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

output "c2_team_server_public_ips" {
  description = "Public IP addresses (if in public subnet or EIP attached)"
  value       = var.enable_elastic_ips ? aws_eip.c2_team_server_eip[*].public_ip : aws_instance.c2_team_server[*].public_ip
}

output "cs_installed" {
  description = "Whether Cobalt Strike was configured to be installed"
  value       = local.use_cs_script
}

output "first_server_private_ip" {
  description = "Private IP of the first C2 server (for convenience)"
  value       = length(aws_instance.c2_team_server) > 0 ? aws_instance.c2_team_server[0].private_ip : null
}
