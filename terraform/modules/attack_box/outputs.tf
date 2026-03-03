# Attack Box Module - Outputs
# =============================================================================

output "instance_id" {
  description = "Attack box EC2 instance ID"
  value       = aws_instance.attack_box.id
}

output "private_ip" {
  description = "Attack box private IP address"
  value       = aws_instance.attack_box.private_ip
}

output "admin_password" {
  description = "Attack box Windows Administrator password"
  value       = local.admin_password
  sensitive   = true
}

output "rdp_tunnel_command" {
  description = "SSH tunnel command for RDP access (use port 3390 to avoid bastion conflict)"
  value       = "ssh -L 3390:${aws_instance.attack_box.private_ip}:3389 -i <key> ubuntu@<bastion_or_jumpbox_ip>"
}
