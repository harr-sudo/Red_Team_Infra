# Bastion Module Outputs

output "bastion_instance_id" {
  description = "ID of the bastion instance"
  value       = aws_instance.bastion.id
}

output "bastion_public_ip" {
  description = "Public IP address of the bastion (Elastic IP)"
  value       = aws_eip.bastion_eip.public_ip
}

output "bastion_private_ip" {
  description = "Private IP address of the bastion"
  value       = aws_instance.bastion.private_ip
}

output "bastion_rdp_connection" {
  description = "RDP connection string"
  value       = "mstsc /v:${aws_eip.bastion_eip.public_ip}"
}

output "bastion_windows_password" {
  description = "Windows administrator password (retrieved from AWS if not provided)"
  value       = var.windows_admin_password != "" ? "Password provided via variable" : "Retrieve password using: aws ec2 get-password-data --instance-id ${aws_instance.bastion.id} --priv-launch-key key.pem"
  sensitive   = true
}

output "bastion_wsl2_info" {
  description = "Information about WSL2 setup"
  value       = "WSL2 with Ubuntu will be available after first login. Open PowerShell and run: wsl"
}

