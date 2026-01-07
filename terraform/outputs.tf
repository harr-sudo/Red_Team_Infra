# Terraform Outputs for Red Team Infrastructure
# =============================================================================
# Outputs organized by:
#   1. Deployment Information
#   2. CS Storage (S3)
#   3. VPC/Network
#   4. C2 Infrastructure
#   5. Bastion
#   6. Redirectors
#   7. GOAD (Phase 2)
#   8. Access Instructions
# =============================================================================

# =============================================================================
# 1. DEPLOYMENT INFORMATION
# =============================================================================

output "deployment_type" {
  description = "The deployment type that was used"
  value       = var.deployment_type
}

output "deployment_mode" {
  description = "Deployment mode details"
  value = {
    type             = var.deployment_type
    is_c2_only       = local.is_c2_only
    is_goad_only     = local.is_goad_only
    is_combined      = local.is_combined
    c2_mode          = local.c2_deployment_mode
    goad_lab         = local.goad_lab_type
    cs_on_jumpbox    = local.install_cs_on_jumpbox
  }
}

# =============================================================================
# 2. CS STORAGE (S3 Bucket)
# =============================================================================

output "cs_storage_bucket" {
  description = "S3 bucket for Cobalt Strike files"
  value       = length(module.cs_storage) > 0 ? module.cs_storage[0].bucket_name : null
}

output "cs_storage_upload_command" {
  description = "Command to upload CS archive to S3"
  value       = length(module.cs_storage) > 0 ? module.cs_storage[0].upload_command : null
}

output "cs_instance_profile" {
  description = "IAM instance profile for CS download"
  value       = length(module.cs_storage) > 0 ? module.cs_storage[0].instance_profile_name : null
}

# =============================================================================
# 3. VPC/NETWORK OUTPUTS
# =============================================================================

output "vpc_id" {
  description = "ID of the C2 VPC"
  value       = local.deploy_c2_infra ? module.vpc[0].vpc_id : null
}

output "vpc_cidr_block" {
  description = "CIDR block of the C2 VPC"
  value       = local.deploy_c2_infra ? module.vpc[0].vpc_cidr_block : null
}

output "public_subnet_ids" {
  description = "IDs of the public subnets"
  value       = local.deploy_c2_infra ? module.vpc[0].public_subnet_ids : []
}

output "private_subnet_ids" {
  description = "IDs of the private subnets"
  value       = local.deploy_c2_infra ? module.vpc[0].private_subnet_ids : []
}

# =============================================================================
# 4. C2 INFRASTRUCTURE OUTPUTS
# =============================================================================

# Security Groups
output "c2_team_server_security_group_id" {
  description = "ID of the C2 team server security group"
  value       = local.deploy_c2_infra ? module.security[0].c2_team_server_security_group_id : null
}

output "proxy_redirector_security_group_id" {
  description = "ID of the proxy/redirector security group"
  value       = local.deploy_c2_infra ? module.security[0].proxy_redirector_security_group_id : null
}

# C2 Deployment Mode
output "c2_deployment_mode" {
  description = "Actual C2 deployment mode being used"
  value       = local.c2_deployment_mode
}

# C2 Team Server Outputs (Single/Redundancy Mode)
output "c2_team_server_instance_ids" {
  description = "IDs of the C2 team server instances (single/redundancy mode)"
  value = local.deploy_c2_infra && (local.c2_deployment_mode == "single" || local.c2_deployment_mode == "redundancy") ? (
    length(module.c2_team_server) > 0 ? module.c2_team_server[0].c2_team_server_instance_ids : []
  ) : []
}

output "c2_team_server_private_ips" {
  description = "Private IP addresses of the C2 team server instances (single/redundancy mode)"
  value = local.deploy_c2_infra && (local.c2_deployment_mode == "single" || local.c2_deployment_mode == "redundancy") ? (
    length(module.c2_team_server) > 0 ? module.c2_team_server[0].c2_team_server_private_ips : []
  ) : []
}

# Primary C2 Server IP (for CS connection)
output "c2_server_primary_ip" {
  description = "Primary C2 server private IP (for Cobalt Strike connection)"
  value = local.deploy_c2_infra ? (
    local.c2_deployment_mode == "phases" ? (
      length(module.c2_phase_servers) > 0 ? values(module.c2_phase_servers)[0].first_server_private_ip : null
    ) : (
      length(module.c2_team_server) > 0 ? module.c2_team_server[0].first_server_private_ip : null
    )
  ) : null
}

# C2 Phase Server Outputs (Phase-Based Mode)
output "c2_phase_server_instance_ids" {
  description = "IDs of the C2 phase server instances (phases mode)"
  value = local.deploy_c2_infra && local.c2_deployment_mode == "phases" ? {
    for phase_name, module_instance in module.c2_phase_servers : phase_name => module_instance.c2_team_server_instance_ids[0]
  } : {}
}

output "c2_phase_server_private_ips" {
  description = "Private IP addresses of the C2 phase server instances (phases mode)"
  value = local.deploy_c2_infra && local.c2_deployment_mode == "phases" ? {
    for phase_name, module_instance in module.c2_phase_servers : phase_name => module_instance.c2_team_server_private_ips[0]
  } : {}
}

# Combined C2 Server Output (unified for all modes)
output "c2_servers" {
  description = "All C2 servers (unified output for all deployment modes)"
  value = local.deploy_c2_infra ? (
    local.c2_deployment_mode == "phases" ? {
      for phase_name, module_instance in module.c2_phase_servers : phase_name => {
        instance_id = module_instance.c2_team_server_instance_ids[0]
        private_ip  = module_instance.c2_team_server_private_ips[0]
        phase       = phase_name
      }
    } : (
      local.c2_deployment_mode == "single" || local.c2_deployment_mode == "redundancy" ? {
        for idx, instance_id in (length(module.c2_team_server) > 0 ? module.c2_team_server[0].c2_team_server_instance_ids : []) : "server-${idx + 1}" => {
          instance_id = instance_id
          private_ip  = length(module.c2_team_server) > 0 ? module.c2_team_server[0].c2_team_server_private_ips[idx] : null
          phase       = "generic"
        }
      } : {}
    )
  ) : {}
}

# =============================================================================
# 5. BASTION/JUMP BOX OUTPUTS
# =============================================================================

output "bastion_public_ip" {
  description = "Public IP address of the bastion host"
  value       = local.deploy_bastion && var.enable_bastion && length(module.bastion) > 0 ? module.bastion[0].bastion_public_ip : null
}

output "bastion_private_ip" {
  description = "Private IP address of the bastion host"
  value       = local.deploy_bastion && var.enable_bastion && length(module.bastion) > 0 ? module.bastion[0].bastion_private_ip : null
}

output "bastion_rdp_connection" {
  description = "RDP connection command"
  value       = local.deploy_bastion && var.enable_bastion && length(module.bastion) > 0 ? module.bastion[0].bastion_rdp_connection : null
}

output "bastion_windows_password_info" {
  description = "Information about retrieving Windows password"
  value       = local.deploy_bastion && var.enable_bastion && length(module.bastion) > 0 ? module.bastion[0].bastion_windows_password : null
  sensitive   = true
}

# =============================================================================
# 6. PROXY/REDIRECTOR OUTPUTS
# =============================================================================

output "proxy_redirector_instance_ids" {
  description = "IDs of the proxy/redirector instances"
  value       = local.deploy_redirectors && length(module.proxy_redirector) > 0 ? module.proxy_redirector[0].proxy_redirector_instance_ids : []
}

output "proxy_redirector_public_ips" {
  description = "Public IP addresses of the proxy/redirector instances"
  value       = local.deploy_redirectors && length(module.proxy_redirector) > 0 ? module.proxy_redirector[0].proxy_redirector_public_ips : []
}

output "proxy_redirector_private_ips" {
  description = "Private IP addresses of the proxy/redirector instances"
  value       = local.deploy_redirectors && length(module.proxy_redirector) > 0 ? module.proxy_redirector[0].proxy_redirector_private_ips : []
}

# =============================================================================
# 7. GOAD LAB OUTPUTS
# =============================================================================

output "goad_deployed" {
  description = "Whether GOAD lab was deployed"
  value       = local.deploy_goad
}

output "goad_lab_type" {
  description = "GOAD lab type that was deployed"
  value       = local.goad_lab_type
}

output "goad_vpc_id" {
  description = "ID of the GOAD VPC"
  value       = local.deploy_goad && length(module.goad) > 0 ? module.goad[0].vpc_id : null
}

output "goad_jumpbox_public_ip" {
  description = "GOAD jumpbox public IP"
  value       = local.deploy_goad && length(module.goad) > 0 ? module.goad[0].jumpbox_public_ip : null
}

output "goad_jumpbox_private_ip" {
  description = "GOAD jumpbox private IP"
  value       = local.deploy_goad && length(module.goad) > 0 ? module.goad[0].jumpbox_private_ip : null
}

output "goad_jumpbox_ssh_command" {
  description = "SSH command to connect to GOAD jumpbox"
  value       = local.deploy_goad && length(module.goad) > 0 ? module.goad[0].jumpbox_ssh_command : null
}

output "goad_jumpbox_ssh_private_key" {
  description = "SSH private key for GOAD jumpbox"
  value       = local.deploy_goad && length(module.goad) > 0 ? module.goad[0].jumpbox_ssh_private_key : null
  sensitive   = true
}

output "goad_lab_vms" {
  description = "GOAD lab VM details"
  value       = local.deploy_goad && length(module.goad) > 0 ? module.goad[0].lab_vms : []
}

output "goad_windows_vm_ips" {
  description = "Private IPs of GOAD Windows VMs"
  value       = local.deploy_goad && length(module.goad) > 0 ? module.goad[0].windows_vm_private_ips : {}
}

output "goad_credentials" {
  description = "GOAD lab credentials information"
  value       = local.deploy_goad && length(module.goad) > 0 ? module.goad[0].credentials : null
}

output "goad_domain_info" {
  description = "GOAD domain information"
  value       = local.deploy_goad && length(module.goad) > 0 ? module.goad[0].domain_info : null
}

# =============================================================================
# 7b. VPC PEERING OUTPUTS (Combined Mode)
# =============================================================================

output "vpc_peering_connection_id" {
  description = "ID of the VPC peering connection (combined mode only)"
  value       = local.deploy_vpc_peering && length(module.vpc_peering) > 0 ? module.vpc_peering[0].peering_connection_id : null
}

# =============================================================================
# 8. COBALT STRIKE CONNECTION INFO
# =============================================================================

output "cs_connection_info" {
  description = "Cobalt Strike connection information"
  value = {
    host = local.is_goad_only ? (
      local.deploy_goad && length(module.goad) > 0 ? module.goad[0].jumpbox_public_ip : null
    ) : (
      local.deploy_c2_infra ? (
        local.c2_deployment_mode == "phases" ? (
          length(module.c2_phase_servers) > 0 ? values(module.c2_phase_servers)[0].first_server_private_ip : null
        ) : (
          length(module.c2_team_server) > 0 ? module.c2_team_server[0].first_server_private_ip : null
        )
      ) : null
    )
    port   = var.cs_teamserver_port
    method = local.is_goad_only ? "direct" : "ssh_tunnel"
  }
  sensitive = true
}

# =============================================================================
# 9. ACCESS INSTRUCTIONS
# =============================================================================

output "access_instructions" {
  description = "Step-by-step access instructions for the deployment"
  value = local.is_goad_only ? {
    type = "goad-only"
    steps = local.deploy_goad && length(module.goad) > 0 ? [
      "1. Connect Cobalt Strike client to ${module.goad[0].jumpbox_public_ip}:50050",
      "2. SSH to jumpbox: ssh -i goad-jumpbox.pem goad@${module.goad[0].jumpbox_public_ip}",
      "3. From jumpbox, access Windows VMs via RDP or WinRM",
      "4. Run Ansible to provision AD: cd /opt/goad && ansible-playbook main.yml"
    ] : [
      "1. GOAD not deployed - check deployment_type",
    ]
  } : local.is_combined ? {
    type = "combined"
    steps = [
      "1. RDP to bastion: ${local.deploy_bastion && var.enable_bastion && length(module.bastion) > 0 ? module.bastion[0].bastion_public_ip : "N/A"}",
      "2. Create SSH tunnel through bastion to C2 server",
      "3. Connect CS client through tunnel",
      "4. GOAD VMs accessible via VPC peering from C2 servers",
      "5. Jumpbox IP: ${local.deploy_goad && length(module.goad) > 0 ? module.goad[0].jumpbox_public_ip : "N/A"}"
    ]
  } : local.deploy_c2_infra ? {
    type = "c2-only"
    steps = [
      "1. RDP to bastion: ${local.deploy_bastion && var.enable_bastion && length(module.bastion) > 0 ? module.bastion[0].bastion_public_ip : "N/A"}",
      "2. SSH tunnel: ssh -L 50050:<c2_private_ip>:50050 -i <key> ubuntu@<bastion_ip>",
      "3. Connect CS client to localhost:50050",
      "4. Redirectors: ${local.deploy_redirectors && length(module.proxy_redirector) > 0 ? join(", ", module.proxy_redirector[0].proxy_redirector_public_ips) : "N/A"}"
    ]
  } : {
    type = "none"
    steps = ["No infrastructure deployed"]
  }
}

# =============================================================================
# 10. ANSIBLE INVENTORY (for configuration management)
# =============================================================================

output "ansible_inventory" {
  description = "Ansible inventory information"
  value = local.deploy_c2_infra ? {
    c2_team_servers = local.c2_deployment_mode == "phases" ? [
      for phase_name, module_instance in module.c2_phase_servers : {
        name         = "${var.project_name}-${var.environment}-c2-${phase_name}-server"
        ansible_host = module_instance.c2_team_server_private_ips[0]
        ansible_user = "ubuntu"
        phase        = phase_name
      }
    ] : (local.c2_deployment_mode == "single" || local.c2_deployment_mode == "redundancy" ? [
      for idx, ip in (length(module.c2_team_server) > 0 ? module.c2_team_server[0].c2_team_server_private_ips : []) : {
        name         = "${var.project_name}-${var.environment}-c2-team-server-${idx + 1}"
        ansible_host = ip
        ansible_user = "ubuntu"
        phase        = "generic"
      }
    ] : [])
    proxy_redirectors = local.deploy_redirectors && length(module.proxy_redirector) > 0 ? [
      for idx, ip in module.proxy_redirector[0].proxy_redirector_public_ips : {
        name         = "${var.project_name}-${var.environment}-proxy-redirector-${idx + 1}"
        ansible_host = ip
        ansible_user = "ubuntu"
      }
    ] : []
  } : {
    c2_team_servers   = []
    proxy_redirectors = []
  }
}
