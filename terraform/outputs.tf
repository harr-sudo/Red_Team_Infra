# Terraform Outputs for Red Team Infrastructure

# VPC Outputs
output "vpc_id" {
  description = "ID of the VPC"
  value       = module.vpc.vpc_id
}

output "vpc_cidr_block" {
  description = "CIDR block of the VPC"
  value       = module.vpc.vpc_cidr_block
}

output "public_subnet_ids" {
  description = "IDs of the public subnets"
  value       = module.vpc.public_subnet_ids
}

output "private_subnet_ids" {
  description = "IDs of the private subnets"
  value       = module.vpc.private_subnet_ids
}

# Security Group Outputs
output "c2_team_server_security_group_id" {
  description = "ID of the C2 team server security group"
  value       = module.security.c2_team_server_security_group_id
}

output "proxy_redirector_security_group_id" {
  description = "ID of the proxy/redirector security group"
  value       = module.security.proxy_redirector_security_group_id
}

# Deployment Mode Output (for reference)
output "c2_deployment_mode" {
  description = "Actual C2 deployment mode being used (may be auto-configured from engagement_type)"
  value       = local.c2_deployment_mode
}

# C2 Team Server Outputs (Single/Redundancy Mode)
output "c2_team_server_instance_ids" {
  description = "IDs of the C2 team server instances (single/redundancy mode)"
  value       = local.c2_deployment_mode == "single" || local.c2_deployment_mode == "redundancy" ? (length(module.c2_team_server) > 0 ? module.c2_team_server[0].c2_team_server_instance_ids : []) : []
}

output "c2_team_server_private_ips" {
  description = "Private IP addresses of the C2 team server instances (single/redundancy mode)"
  value       = local.c2_deployment_mode == "single" || local.c2_deployment_mode == "redundancy" ? (length(module.c2_team_server) > 0 ? module.c2_team_server[0].c2_team_server_private_ips : []) : []
}

# C2 Phase Server Outputs (Phase-Based Mode)
output "c2_phase_server_instance_ids" {
  description = "IDs of the C2 phase server instances (phases mode)"
  value = local.c2_deployment_mode == "phases" ? {
    for phase_name, module_instance in module.c2_phase_servers : phase_name => module_instance.c2_team_server_instance_ids[0]
  } : {}
}

output "c2_phase_server_private_ips" {
  description = "Private IP addresses of the C2 phase server instances (phases mode)"
  value = local.c2_deployment_mode == "phases" ? {
    for phase_name, module_instance in module.c2_phase_servers : phase_name => module_instance.c2_team_server_private_ips[0]
  } : {}
}

# Combined C2 Server Output (for convenience)
output "c2_servers" {
  description = "All C2 servers (unified output for all deployment modes)"
  value = local.c2_deployment_mode == "phases" ? {
    for phase_name, module_instance in module.c2_phase_servers : phase_name => {
      instance_id = module_instance.c2_team_server_instance_ids[0]
      private_ip  = module_instance.c2_team_server_private_ips[0]
      phase       = phase_name
    }
  } : (local.c2_deployment_mode == "single" || local.c2_deployment_mode == "redundancy" ? {
    for idx, instance_id in (length(module.c2_team_server) > 0 ? module.c2_team_server[0].c2_team_server_instance_ids : []) : "server-${idx + 1}" => {
      instance_id = instance_id
      private_ip  = length(module.c2_team_server) > 0 ? module.c2_team_server[0].c2_team_server_private_ips[idx] : null
      phase       = "generic"
    }
  } : {})
}

# Proxy/Redirector Outputs
output "proxy_redirector_instance_ids" {
  description = "IDs of the proxy/redirector instances"
  value       = module.proxy_redirector.proxy_redirector_instance_ids
}

output "proxy_redirector_public_ips" {
  description = "Public IP addresses of the proxy/redirector instances"
  value       = module.proxy_redirector.proxy_redirector_public_ips
}

output "proxy_redirector_private_ips" {
  description = "Private IP addresses of the proxy/redirector instances"
  value       = module.proxy_redirector.proxy_redirector_private_ips
}

# Connection Information (for Ansible inventory generation)
output "ansible_inventory" {
  description = "Ansible inventory information"
  value = {
    c2_team_servers = local.c2_deployment_mode == "phases" ? [
      for phase_name, module_instance in module.c2_phase_servers : {
        name         = "${var.project_name}-${var.environment}-c2-${phase_name}-server"
        ansible_host = module_instance.c2_team_server_private_ips[0]
        ansible_user = "ec2-user"
        phase        = phase_name
      }
    ] : (local.c2_deployment_mode == "single" || local.c2_deployment_mode == "redundancy" ? [
      for idx, ip in (length(module.c2_team_server) > 0 ? module.c2_team_server[0].c2_team_server_private_ips : []) : {
        name         = "${var.project_name}-${var.environment}-c2-team-server-${idx + 1}"
        ansible_host = ip
        ansible_user = "ec2-user"
        phase        = "generic"
      }
    ] : [])
    proxy_redirectors = [
      for idx, ip in module.proxy_redirector.proxy_redirector_public_ips : {
        name         = "${var.project_name}-${var.environment}-proxy-redirector-${idx + 1}"
        ansible_host = ip
        ansible_user = "ec2-user"
      }
    ]
  }
}

