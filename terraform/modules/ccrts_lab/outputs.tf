# CCRTS Lab Module - Outputs
# =============================================================================
# Tunnel command templates use ${dashboard_eip} as a placeholder so the
# dashboard module / webapp can substitute the operator-facing EIP at render
# time without this module having to know about the dashboard's EIP at plan time.
# =============================================================================

# =============================================================================
# Network outputs (consumed by VPC peering + dashboard wiring)
# =============================================================================

output "vpc_id" {
  description = "ID of the CCRTS lab VPC"
  value       = aws_vpc.ccrts.id
}

output "vpc_cidr" {
  description = "CIDR block of the CCRTS lab VPC"
  value       = aws_vpc.ccrts.cidr_block
}

output "public_subnet_id" {
  description = "ID of the public subnet (NAT)"
  value       = aws_subnet.public.id
}

output "private_subnet_id" {
  description = "ID of the private subnet (lab hosts)"
  value       = aws_subnet.private.id
}

output "route_table_ids" {
  description = "Route table IDs (used by VPC peering to add cross-VPC routes)"
  value       = [aws_route_table.public.id, aws_route_table.private.id]
}

# =============================================================================
# Operator access — tunnel commands templated with ${dashboard_eip} placeholder
# =============================================================================
# The dashboard module (or the webapp) replaces ${dashboard_eip} with the real
# operator-facing EIP. Using a literal placeholder keeps these outputs static
# and avoids cross-module data dependencies.

output "kali_ssh_tunnel_cmd" {
  description = "SSH tunnel to reach Kali (forward 2222 -> kali:22 via dashboard EIP)"
  value       = "ssh -L 2222:${local.ip_range}.20:22 ubuntu@$${dashboard_eip}"
}

output "windows_rdp_tunnel_cmd" {
  description = "SSH tunnel to reach the Windows workstation RDP (3389)"
  value       = "ssh -L 3389:${local.ip_range}.30:3389 ubuntu@$${dashboard_eip}"
}

output "dc_winrm_tunnel_cmd" {
  description = "SSH tunnel to reach the AD DC WinRM (5985/5986) — ccrts-full only"
  value       = var.lab_size == "ccrts-full" ? "ssh -L 5985:${local.ip_range}.40:5985 -L 5986:${local.ip_range}.40:5986 ubuntu@$${dashboard_eip}" : null
}

output "ad_workstation_winrm_tunnel_cmd" {
  description = "SSH tunnel to reach the AD workstation WinRM — ccrts-full only"
  value       = var.lab_size == "ccrts-full" ? "ssh -L 15985:${local.ip_range}.41:5985 -L 15986:${local.ip_range}.41:5986 ubuntu@$${dashboard_eip}" : null
}

output "kibana_tunnel_cmd" {
  description = "SSH tunnel to reach Kibana (forward 5601 -> elk:5601)"
  value       = "ssh -L 5601:${local.ip_range}.50:5601 ubuntu@$${dashboard_eip}"
}

# =============================================================================
# Inventory
# =============================================================================

output "lab_vms" {
  description = "List of lab VMs ({hostname, ip, role, os, instance_type})"
  value       = concat(local.base_vms, local.ad_vm_summary)
}

output "instance_ids" {
  description = "Map of hostname -> instance ID"
  value = merge(
    {
      kali       = aws_instance.kali.id
      windows-ws = aws_instance.windows_workstation.id
      elk        = aws_instance.elk.id
    },
    { for k, v in aws_instance.ad : local.ad_vms[k].hostname => v.id }
  )
}

# =============================================================================
# Credentials (SENSITIVE)
# =============================================================================

output "credentials" {
  description = "Lab admin credentials (sensitive). Lab posture — these are not vault-grade."
  sensitive   = true
  value = {
    windows_workstation_admin = {
      username = "Administrator"
      password = var.windows_admin_password
    }
    domain_admin = var.lab_size == "ccrts-full" ? {
      username = "CCRTS\\Administrator"
      password = var.dc_admin_password
      domain   = "ccrts.local"
    } : null
    domain_low_priv = var.lab_size == "ccrts-full" ? {
      username = "CCRTS\\jdoe"
      password = var.low_priv_password
      domain   = "ccrts.local"
    } : null
  }
}

# =============================================================================
# Access Instructions (multi-line string for the dashboard UI)
# =============================================================================

output "access_instructions" {
  description = "How to reach the CCRTS lab through the dashboard"
  value = join("\n", concat(
    [
      "=== CCRTS Lab (${var.lab_size}) ===",
      "All ingress flows THROUGH the dashboard server — no direct internet exposure on lab hosts.",
      "Replace <dashboard-eip> with the dashboard server's EIP.",
      "",
      "--- Kali Attacker (${local.ip_range}.20) ---",
      "ssh -L 2222:${local.ip_range}.20:22 ubuntu@<dashboard-eip>",
      "  then: ssh -p 2222 kali@localhost",
      "",
      "--- Windows Workstation (${local.ip_range}.30) ---",
      "ssh -L 3389:${local.ip_range}.30:3389 ubuntu@<dashboard-eip>",
      "  then: RDP to localhost:3389 (Administrator / <see credentials>)",
      "",
      "--- ELK / Kibana (${local.ip_range}.50:5601) ---",
      "ssh -L 5601:${local.ip_range}.50:5601 ubuntu@<dashboard-eip>",
      "  then: http://localhost:5601",
    ],
    var.lab_size == "ccrts-full" ? [
      "",
      "--- AD DC dc01.ccrts.local (${local.ip_range}.40) ---",
      "ssh -L 13389:${local.ip_range}.40:3389 ubuntu@<dashboard-eip>",
      "  then: RDP to localhost:13389 (CCRTS\\Administrator)",
      "",
      "--- AD Workstation ad-ws01 (${local.ip_range}.41) ---",
      "ssh -L 23389:${local.ip_range}.41:3389 ubuntu@<dashboard-eip>",
      "  then: RDP to localhost:23389 (CCRTS\\jdoe / Welcome1!)",
    ] : []
  ))
}

# =============================================================================
# Deployment Summary
# =============================================================================
# `category: "ccrts-only"` is the signal the frontend uses to hide bolt-ons +
# operations sub-pills for this deployment family.

output "deployment_summary" {
  description = "Summary of the CCRTS lab deployment"
  value = {
    category    = "ccrts-only"
    lab_size    = var.lab_size
    vpc_id      = aws_vpc.ccrts.id
    vpc_cidr    = aws_vpc.ccrts.cidr_block
    region      = var.aws_region
    host_count  = length(local.base_vms) + length(local.ad_vms)
    ad_enabled  = var.lab_size == "ccrts-full"
    domain      = var.lab_size == "ccrts-full" ? "ccrts.local" : null
    kali_ami    = local.kali_ami_id
    windows_ami = local.windows_ami_id
    ami_source  = var.crest_ami_source_region
    elk_version = "8.19.0"
  }
}
