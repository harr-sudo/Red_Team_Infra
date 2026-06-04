# Terraform Outputs for Red Team Infrastructure
# =============================================================================
# Outputs organized by:
#   1. Deployment Information
#   2. CS Storage (S3)
#   3. VPC/Network
#   4. C2 Infrastructure
#   5. Attack Box
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
    type          = var.deployment_type
    is_c2_only    = local.is_c2_only
    is_goad_only  = local.is_goad_only
    is_combined   = local.is_combined
    c2_mode       = local.c2_deployment_mode
    goad_lab      = local.goad_lab_type
    cs_on_jumpbox = local.install_goad_teamserver
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

output "management_subnet_ids" {
  description = "IDs of the management subnets (bastion isolation)"
  value       = local.deploy_c2_infra ? module.vpc[0].management_subnet_ids : []
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
        for idx, instance_id in(length(module.c2_team_server) > 0 ? module.c2_team_server[0].c2_team_server_instance_ids : []) : "server-${idx + 1}" => {
          instance_id = instance_id
          private_ip  = length(module.c2_team_server) > 0 ? module.c2_team_server[0].c2_team_server_private_ips[idx] : null
          phase       = "generic"
        }
      } : {}
    )
  ) : {}
}

# =============================================================================
# 5. ATTACK BOX OUTPUTS (Windows Workstation)
# =============================================================================

output "attack_box_instance_id" {
  description = "Attack box EC2 instance ID"
  value       = local.deploy_attack_box && length(module.attack_box) > 0 ? module.attack_box[0].instance_id : null
}

output "attack_box_private_ip" {
  description = "Attack box private IP address"
  value       = local.deploy_attack_box && length(module.attack_box) > 0 ? module.attack_box[0].private_ip : null
}

output "attack_box_admin_password" {
  description = "Attack box Windows Administrator password"
  value       = local.deploy_attack_box && length(module.attack_box) > 0 ? module.attack_box[0].admin_password : null
  sensitive   = true
}

output "attack_box_rdp_tunnel" {
  description = "SSH tunnel command for RDP to attack box through the dashboard server"
  value       = local.deploy_attack_box && length(module.attack_box) > 0 ? module.attack_box[0].rdp_tunnel_command : null
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
# 6b. FILE PORTAL
# =============================================================================

output "file_portal_info" {
  description = "File portal connection details (when enabled)"
  value = var.enable_file_portal && local.deploy_redirectors && length(module.proxy_redirector) > 0 ? {
    enabled  = true
    url      = var.primary_domain_name != "" ? "https://www.${var.primary_domain_name}/login" : "https://${module.proxy_redirector[0].proxy_redirector_public_ips[0]}/login"
    username = var.portal_username
    password = var.portal_password
    } : {
    enabled  = false
    url      = null
    username = null
    password = null
  }
  sensitive = true
}

# =============================================================================
# 6c. DOMAIN FRONTING OUTPUTS (CloudFront)
# =============================================================================

output "domain_fronting_enabled" {
  description = "Whether domain fronting (CloudFront) is enabled"
  value       = local.deploy_domain_fronting
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = local.deploy_domain_fronting && length(module.domain_fronting) > 0 ? module.domain_fronting[0].cloudfront_distribution_id : null
}

output "cloudfront_domain_name" {
  description = "CloudFront domain name (d123abc.cloudfront.net) - use as Host header in CS profile"
  value       = local.deploy_domain_fronting && length(module.domain_fronting) > 0 ? module.domain_fronting[0].cloudfront_domain_name : null
}

output "cloudfront_aliases" {
  description = "All domains configured as CloudFront aliases (available for domain rotation)"
  value       = local.deploy_domain_fronting && length(module.domain_fronting) > 0 ? module.domain_fronting[0].cloudfront_aliases : []
}

output "cloudfront_status" {
  description = "CloudFront distribution deployment status"
  value       = local.deploy_domain_fronting && length(module.domain_fronting) > 0 ? module.domain_fronting[0].cloudfront_status : null
}

# =============================================================================
# 6c. DNS OUTPUTS
# =============================================================================

output "dns_nameservers" {
  description = "Route 53 nameservers for domain registrar configuration"
  value       = local.deploy_c2_infra && var.primary_domain_name != "" && length(module.dns) > 0 ? module.dns[0].zone_name_servers : []
}

output "dns_domain" {
  description = "Primary domain name configured for DNS"
  value       = local.deploy_c2_infra && var.primary_domain_name != "" && length(module.dns) > 0 ? module.dns[0].primary_domain : null
}

output "dns_records" {
  description = "DNS records created (FQDNs pointing to redirectors)"
  value       = local.deploy_c2_infra && var.primary_domain_name != "" && length(module.dns) > 0 ? module.dns[0].all_fqdns : []
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

# SECURITY: Private key output REMOVED - users provide their own key
# Old output "goad_jumpbox_ssh_private_key" has been removed for security.
# Users must use their own private key (matching the public key they provided).

output "goad_jumpbox_connection_info" {
  description = "GOAD jumpbox connection information (use your own private key)"
  value       = local.deploy_goad && length(module.goad) > 0 ? module.goad[0].jumpbox_connection_info : null
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
  sensitive   = true
}

output "goad_domain_info" {
  description = "GOAD domain information"
  value       = local.deploy_goad && length(module.goad) > 0 ? module.goad[0].domain_info : null
}

output "goad_teamserver_private_ip" {
  description = "GOAD Team Server private IP"
  value       = local.deploy_goad && length(module.goad) > 0 ? module.goad[0].teamserver_private_ip : null
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
    port             = var.c2_server_port # CS client management port (50050)
    rest_api_enabled = var.enable_cs_rest_api
    rest_api_port    = var.enable_cs_rest_api ? 50443 : null
    method           = local.is_goad_only ? "direct" : "ssh_tunnel"
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
      "1. SSH to the dashboard server: ssh -i key.pem ubuntu@${length(module.dashboard_server) > 0 ? module.dashboard_server[0].dashboard_public_ip : "<dashboard-eip>"}",
      "2. Create an SSH tunnel through the dashboard server to the C2 server",
      "3. Connect CS client through tunnel",
      "4. GOAD VMs accessible via VPC peering from C2 servers",
      "5. Jumpbox IP: ${local.deploy_goad && length(module.goad) > 0 ? module.goad[0].jumpbox_public_ip : "N/A"}"
    ]
    } : local.deploy_c2_infra ? {
    type = "c2-only"
    steps = [
      "1. SSH to the dashboard server: ssh -i key.pem ubuntu@${length(module.dashboard_server) > 0 ? module.dashboard_server[0].dashboard_public_ip : "<dashboard-eip>"}",
      "2. SSH tunnel: ssh -L 50050:<c2_private_ip>:50050 -i <key> ubuntu@<dashboard-eip>",
      "3. Connect CS client to localhost:50050",
      "4. Redirectors: ${local.deploy_redirectors && length(module.proxy_redirector) > 0 ? join(", ", module.proxy_redirector[0].proxy_redirector_public_ips) : "N/A"}"
    ]
    } : {
    type  = "none"
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
        for idx, ip in(length(module.c2_team_server) > 0 ? module.c2_team_server[0].c2_team_server_private_ips : []) : {
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

# =============================================================================
# 9. Dashboard Server (Optional)
# =============================================================================

output "dashboard_public_ip" {
  description = "Dashboard server public IP"
  value       = length(module.dashboard_server) > 0 ? module.dashboard_server[0].dashboard_public_ip : ""
}

output "dashboard_instance_id" {
  description = "Dashboard server EC2 instance ID"
  value       = length(module.dashboard_server) > 0 ? module.dashboard_server[0].dashboard_instance_id : ""
}

output "dashboard_vpc_id" {
  description = "Dashboard server VPC ID"
  value       = length(module.dashboard_server) > 0 ? module.dashboard_server[0].dashboard_vpc_id : ""
}

output "dashboard_tfstate_bucket" {
  description = "S3 bucket for Terraform state"
  value       = length(module.dashboard_server) > 0 ? module.dashboard_server[0].tfstate_bucket : ""
}

# =============================================================================
# Test Lab Outputs
# =============================================================================

output "test_lab_enabled" {
  description = "True when the optional in-VPC test lab was provisioned"
  value       = local.enable_test_lab
}

output "test_lab_subnet_id" {
  description = "ID of the test lab private subnet (empty when test lab is disabled)"
  value       = length(module.test_lab) > 0 ? module.test_lab[0].subnet_id : ""
}

output "test_lab_host_inventory" {
  description = "Map of hostname -> { private_ip, role, os_family, instance_id } for the test lab hosts (empty when disabled)"
  value       = length(module.test_lab) > 0 ? module.test_lab[0].host_inventory : {}
}
