# Security Groups Module Outputs

output "c2_team_server_security_group_id" {
  description = "ID of the C2 team server security group"
  value       = aws_security_group.c2_team_server_sg.id
}

output "proxy_redirector_security_group_id" {
  description = "ID of the proxy/redirector security group"
  value       = aws_security_group.proxy_redirector_sg.id
}

