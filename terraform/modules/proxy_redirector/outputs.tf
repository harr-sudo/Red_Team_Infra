# Proxy/Redirector Module Outputs

output "proxy_redirector_instance_ids" {
  description = "IDs of the proxy/redirector instances"
  value       = aws_instance.proxy_redirector[*].id
}

output "proxy_redirector_public_ips" {
  description = "Public IP addresses of the proxy/redirector instances"
  value       = aws_eip.proxy_redirector_eip[*].public_ip
}

output "proxy_redirector_private_ips" {
  description = "Private IP addresses of the proxy/redirector instances"
  value       = aws_instance.proxy_redirector[*].private_ip
}

