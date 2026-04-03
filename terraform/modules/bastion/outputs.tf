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

output "bastion_ssh_command" {
  description = "SSH connection command for bastion host"
  value       = "ssh -i ~/.ssh/key.pem ubuntu@${aws_eip.bastion_eip.public_ip}"
}
