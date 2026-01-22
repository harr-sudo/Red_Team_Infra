# GOAD Module - Attack Box Scripts Storage
# =============================================================================
# Stores large initialization scripts in S3 to bypass EC2 user_data size limits
#
# IAM Permissions:
# - The GOAD instance profile (cs_download_goad) already has s3:GetObject 
#   permissions for the entire deployment bucket
# - See terraform/modules/cs_storage/main.tf for IAM policy details
# =============================================================================

# Upload the full attackbox init script to S3
resource "aws_s3_object" "attackbox_init_script" {
  count = var.install_cobalt_strike && var.deployment_bucket != "" ? 1 : 0

  bucket = var.deployment_bucket
  key    = "${var.deployment_id}/scripts/attackbox_init.ps1"
  
  # Template the script with variables
  content = templatefile("${path.module}/scripts/attackbox_init.ps1", {
    teamserver_ip      = "${var.ip_range}.40"
    teamserver_port    = "50050"
    admin_password     = local.attackbox_password
    deployment_bucket  = var.deployment_bucket
    deployment_id      = var.deployment_id
    aws_region         = var.aws_region
    hostname           = "attackbox-windows"
    cs_client_s3_path  = var.cs_client_s3_path
  })
  
  content_type = "text/plain"

  tags = merge(var.tags, {
    Name = "${var.project_name}-${local.lab_identifier}-attackbox-init-script"
    Lab  = local.lab_identifier
    Role = "AttackBox"
  })
}
