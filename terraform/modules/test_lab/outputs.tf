# Test Lab Module Outputs
# =============================================================================
# host_inventory is the contract the Ansible inventory writer +
# bolton_facts_service consume to learn about lab hosts.
# =============================================================================

output "subnet_id" {
  description = "ID of the new test lab private subnet inside the C2 VPC"
  value       = aws_subnet.test_lab.id
}

output "subnet_cidr" {
  description = "CIDR of the test lab private subnet"
  value       = aws_subnet.test_lab.cidr_block
}

output "host_inventory" {
  description = "Map of hostname -> { private_ip, role, os_family, instance_id }. Consumed by the Ansible inventory generator + the bolton facts service."
  value = {
    tldc01 = {
      private_ip  = aws_instance.windows["tldc01"].private_ip
      role        = "domain_controller"
      os_family   = "windows"
      instance_id = aws_instance.windows["tldc01"].id
    }
    tlms01 = {
      private_ip  = aws_instance.windows["tlms01"].private_ip
      role        = "member_server"
      os_family   = "windows"
      instance_id = aws_instance.windows["tlms01"].id
    }
    tlws01 = {
      private_ip  = aws_instance.windows["tlws01"].private_ip
      role        = "workstation"
      os_family   = "windows"
      instance_id = aws_instance.windows["tlws01"].id
    }
    tllinux01 = {
      private_ip  = aws_instance.tllinux01.private_ip
      role        = "linux_member"
      os_family   = "linux"
      instance_id = aws_instance.tllinux01.id
    }
  }
}

output "security_group_ids" {
  description = "Map of hostname -> per-host security group ID (excludes the shared fabric SG)"
  value = {
    tldc01    = aws_security_group.tldc01.id
    tlms01    = aws_security_group.tlms01.id
    tlws01    = aws_security_group.tlws01.id
    tllinux01 = aws_security_group.tllinux01.id
  }
}

output "fabric_security_group_id" {
  description = "Shared intra-lab security group every host belongs to"
  value       = aws_security_group.test_lab_fabric.id
}

output "iam_instance_profile_name" {
  description = "Name of the SSM-enabled IAM instance profile attached to every lab host"
  value       = aws_iam_instance_profile.test_lab.name
}
