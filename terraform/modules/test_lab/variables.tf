# Test Lab Module Variables
# =============================================================================
# Test lab is an extension to an existing c2-* deployment. It sits in the SAME
# VPC as the C2 deployment (no new VPC, no new NAT, no new IGW). The 4 lab
# hosts live on a fresh private subnet inside the C2 VPC, reusing the C2's
# private route table for NAT egress.
# =============================================================================

variable "project_name" {
  description = "Project name (used to tag and name lab resources)"
  type        = string
}

variable "aws_region" {
  description = "AWS region the lab is deployed into"
  type        = string
}

variable "vpc_id" {
  description = "ID of the existing C2 VPC the test lab subnet will be created inside"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block of the existing C2 VPC (used for intra-VPC SG sanity rules)"
  type        = string
}

variable "subnet_cidr" {
  description = "CIDR of the new private subnet for test lab hosts. Must be a /24 inside the C2 VPC CIDR and must not overlap the standard C2 subnets."
  type        = string
  default     = "10.0.20.0/24"

  validation {
    condition     = can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}/24$", var.subnet_cidr))
    error_message = "subnet_cidr must be a valid IPv4 /24 CIDR (e.g. 10.0.20.0/24)."
  }

  validation {
    condition = !contains(
      [
        "10.0.0.0/24",  # management (bastion)
        "10.0.1.0/24",  # DMZ redirector 1
        "10.0.2.0/24",  # DMZ redirector 2
        "10.0.10.0/24", # private C2 1
        "10.0.11.0/24", # private C2 2
      ],
      var.subnet_cidr,
    )
    error_message = "subnet_cidr must not collide with the standard C2 subnets (10.0.0.0/24, 10.0.1.0/24, 10.0.2.0/24, 10.0.10.0/24, 10.0.11.0/24)."
  }
}

variable "availability_zone" {
  description = "AZ to place the test lab subnet in. Should match the C2 private subnet AZ to avoid cross-AZ data transfer charges from bastion/jumpbox traffic."
  type        = string
}

variable "c2_private_route_table_id" {
  description = "ID of the C2 VPC's existing private route table. The new test lab subnet is associated with it so it reuses the C2 NAT Gateway for outbound."
  type        = string
}

variable "c2_bastion_sg_id" {
  description = "Source SG allowed to reach the test lab (the dashboard server). Empty/null is tolerated — the RDP/SSH ingress rules are skipped when no source SG is wired."
  type        = string
  default     = null
}

variable "c2_jumpbox_sg_id" {
  description = "Source SG ID for WinRM ingress to lab hosts. Only set in combined-* deployments; Phase 1 leaves this null because c2-* deployments have no GOAD jumpbox."
  type        = string
  default     = null
}

variable "key_pair_name" {
  description = "Name of the existing AWS key pair to associate with lab instances (matches operator's primary deployment key)"
  type        = string
}

variable "tags" {
  description = "Tags to merge onto every lab resource"
  type        = map(string)
  default     = {}
}

variable "size" {
  description = "Lab size variant. Only 'mini' (4 hosts) is supported in Phase 1."
  type        = string
  default     = "mini"

  validation {
    condition     = contains(["mini"], var.size)
    error_message = "Only 'mini' is supported in Phase 1 (4 hosts: tldc01, tlms01, tlws01, tllinux01)."
  }
}

# =============================================================================
# Lab credentials — INTENTIONALLY WEAK + INTENTIONALLY NOT SENSITIVE.
# The whole point of the test lab is to be vulnerable. These passwords are
# documented in the catalog descriptors and treated as public knowledge — not
# stored in Secrets Manager.
# =============================================================================

variable "default_admin_password" {
  description = "Weak Administrator password baked into the lab. Public-knowledge — do NOT reuse outside the test lab."
  type        = string
  default     = "Password1!"
  sensitive   = false
}

variable "ansible_user_password" {
  description = "Password for the 'ansible' user on every Windows lab host (used by the WinRM continuity playbooks)."
  type        = string
  default     = "Ansible123!"
  sensitive   = false
}

# =============================================================================
# Instance sizing — sensible defaults from the spec, overridable later.
# =============================================================================

variable "windows_server_instance_type" {
  description = "EC2 instance type for the Windows Server 2022 hosts (tldc01, tlms01)"
  type        = string
  default     = "t3.medium"
}

variable "windows_workstation_instance_type" {
  description = "EC2 instance type for the Windows 11 Pro workstation (tlws01)"
  type        = string
  default     = "t3.small"
}

variable "linux_instance_type" {
  description = "EC2 instance type for the Ubuntu 22.04 host (tllinux01)"
  type        = string
  default     = "t3.small"
}

variable "root_volume_size" {
  description = "Root EBS volume size in GiB for all lab hosts"
  type        = number
  default     = 50
}
