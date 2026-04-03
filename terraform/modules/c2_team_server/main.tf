# C2 Team Server Module
# =============================================================================
# Creates EC2 instances for C2 team servers in private subnets
# Uses centralized Cobalt Strike installation script
# =============================================================================

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# =============================================================================
# Local Values
# =============================================================================

locals {
  # Determine if we should use the centralized CS script
  use_cs_script = var.cobalt_strike_s3_path != "" && var.user_data == ""

  # Generate user_data from template if using CS script
  cs_user_data = local.use_cs_script ? templatefile("${path.root}/scripts/install_cobalt_strike.sh", {
    cs_archive_s3_path = var.cobalt_strike_s3_path
    cs_password        = var.cs_teamserver_password
    server_role        = "c2_server"
    hostname           = var.phase != "" ? "c2-${var.phase}-ubuntu" : "c2-teamserver-ubuntu"
    primary_domain         = var.primary_domain
    c2_subdomain           = var.c2_subdomain
    malleable_profile        = var.malleable_profile
    custom_profile_content   = var.custom_profile_content
    cs_license_secret_name   = var.cs_license_secret_name
    enable_rest_api            = var.enable_rest_api
  }) : null

  # Use S3 bootstrap when enabled and CS script is active
  use_s3_bootstrap = var.enable_s3_bootstrap && local.use_cs_script

  # Bootstrap user_data: small script that installs AWS CLI then downloads setup from S3
  # AWS CLI is NOT pre-installed on Ubuntu 22.04 AMIs (unlike Amazon Linux)
  bootstrap_user_data = local.use_s3_bootstrap ? "#!/bin/bash\nBUILD_LOG=/var/log/c2-bootstrap.log\nexec > >(tee -a $BUILD_LOG) 2>&1\necho '=== C2 Team Server Bootstrap ==='\necho \"Started: $(date)\"\necho \"Instance: $(TOKEN=$(curl -s -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 21600' 2>/dev/null); curl -s -H \"X-aws-ec2-metadata-token: $TOKEN\" http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null || echo unknown)\"\nset -e\nexport DEBIAN_FRONTEND=noninteractive\n# Wait for network connectivity (NAT Gateway may take a moment after instance boot)\necho 'Waiting for network connectivity...'\nfor i in $(seq 1 30); do\n  if curl -s --connect-timeout 3 http://archive.ubuntu.com > /dev/null 2>&1; then\n    echo \"Network ready after $${i} attempts\"\n    break\n  fi\n  if [ $${i} -eq 30 ]; then\n    echo 'ERROR: Network not available after 5 minutes. NAT Gateway may not be configured.'\n    echo \"FAILED: $(date)\" >> $BUILD_LOG\n    exit 1\n  fi\n  echo \"Attempt $${i}/30 - waiting for NAT Gateway...\"\n  sleep 10\ndone\necho 'Installing AWS CLI...'\napt-get update -qq && apt-get install -y -qq awscli > /dev/null 2>&1\necho 'Downloading setup script from S3...'\naws s3 cp 's3://${var.deployment_bucket}/${var.deployment_id}/scripts/install_cobalt_strike.sh' /tmp/install_cobalt_strike.sh --region ${var.aws_region}\nchmod +x /tmp/install_cobalt_strike.sh\necho 'Running setup script...'\n/tmp/install_cobalt_strike.sh\necho \"Bootstrap completed: $(date)\" >> $BUILD_LOG\n" : null

  # Final user_data: custom > S3 bootstrap > inline CS script > none
  final_user_data = var.user_data != "" ? var.user_data : (
    local.use_s3_bootstrap ? local.bootstrap_user_data : (
      local.use_cs_script ? local.cs_user_data : null
    )
  )
}

# =============================================================================
# UPLOAD SETUP SCRIPT TO S3 (bypasses 16KB EC2 user_data limit)
# =============================================================================

resource "aws_s3_object" "c2_setup_script" {
  count = local.use_s3_bootstrap ? 1 : 0

  bucket       = var.deployment_bucket
  key          = "${var.deployment_id}/scripts/install_cobalt_strike.sh"
  content      = local.cs_user_data
  content_type = "text/plain"

  tags = merge(var.tags, {
    Name      = "${var.project_name}-${var.environment}-c2-setup-script"
    Component = "Backend"
  })
}

# =============================================================================
# C2 Team Server Instances
# =============================================================================

resource "aws_instance" "c2_team_server" {
  count = var.c2_server_count

  ami                    = var.ami_id
  instance_type          = var.instance_type
  key_name               = var.key_pair_name
  subnet_id              = var.private_subnet_ids[count.index % length(var.private_subnet_ids)]
  vpc_security_group_ids = [var.security_group_id]
  private_ip             = length(var.private_ips) > count.index ? var.private_ips[count.index] : null

  # Root volume - encrypted and deleted on termination
  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_size
    encrypted             = true
    delete_on_termination = true

    tags = merge(var.tags, {
      Name = var.phase != "" ? "${var.project_name}-${var.environment}-c2-${var.phase}-ubuntu-root" : "${var.project_name}-${var.environment}-c2-server-ubuntu-${count.index + 1}-root"
    })
  }

  # Require IMDSv2 (prevents SSRF-based credential theft from instance metadata)
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  # CloudWatch monitoring
  monitoring = var.enable_detailed_monitoring

  # IAM role for S3 access (CS download)
  iam_instance_profile = var.iam_instance_profile_name != "" ? var.iam_instance_profile_name : null

  # User data for Cobalt Strike installation
  user_data = local.final_user_data

  # Ensure S3 script is uploaded before instance launches
  depends_on = [aws_s3_object.c2_setup_script]

  tags = merge(
    var.tags,
    {
      Name         = var.phase != "" ? "${var.project_name}-${var.environment}-c2-${var.phase}-ubuntu" : "${var.project_name}-${var.environment}-c2-teamserver-ubuntu-${count.index + 1}"
      Type         = "Server"
      Component    = "Backend"
      ServerNumber = count.index + 1
      Phase        = var.phase != "" ? var.phase : "generic"
    }
  )

  # Note: Do NOT use create_before_destroy — static private_ip assignment
  # means AWS rejects the new instance while the old one still holds the IP.
  # Use `terraform taint` to force replacement when needed.
}

# =============================================================================
# Elastic IPs (Optional - typically not needed in private subnets)
# =============================================================================

resource "aws_eip" "c2_team_server_eip" {
  count = var.enable_elastic_ips ? var.c2_server_count : 0

  domain   = "vpc"
  instance = aws_instance.c2_team_server[count.index].id

  tags = merge(
    var.tags,
    {
      Name      = var.phase != "" ? "${var.project_name}-${var.environment}-c2-${var.phase}-ubuntu-eip" : "${var.project_name}-${var.environment}-c2-teamserver-ubuntu-${count.index + 1}-eip"
      Type      = "ElasticIP"
      Component = "C2Infrastructure"
      Phase     = var.phase != "" ? var.phase : "generic"
    }
  )
}
