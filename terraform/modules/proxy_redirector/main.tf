# Proxy/Redirector Module
# Creates EC2 instances for proxy/redirector servers in public subnets
# These servers are pass-through only with no data storage
# Can be configured with nginx for domain-based C2 traffic routing

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# =============================================================================
# LOCAL VALUES
# =============================================================================

locals {
  # Determine if we should use the domain redirector script
  use_redirector_script = var.primary_domain != "" && var.c2_server_ip != "" && var.user_data == ""

  effective_ssl_provider = var.ssl_provider

  # Generate user_data from template if using redirector script
  redirector_user_data = local.use_redirector_script ? templatefile("${path.root}/scripts/setup_redirector.sh", {
    primary_domain    = var.primary_domain
    c2_subdomain      = var.c2_subdomain
    c2_server_ip      = var.c2_server_ip
    c2_server_port    = var.c2_server_port
    enable_ssl        = var.enable_ssl ? "true" : "false"
    ssl_provider      = local.effective_ssl_provider
    ssl_auto_retry    = var.ssl_auto_retry ? "true" : "false"
    admin_email       = var.admin_email
    malleable_profile = var.malleable_profile
    custom_c2_uris    = var.custom_c2_uris
    decoy_theme            = var.decoy_theme
    enable_file_portal     = var.enable_file_portal ? "true" : "false"
    portal_username        = var.portal_username
    portal_password        = var.portal_password
    portal_session_timeout = var.portal_session_timeout
    hostname               = "redirector-ubuntu"
  }) : null

  # Use S3 bootstrap when enabled and redirector script is active
  use_s3_bootstrap = var.enable_s3_bootstrap && local.use_redirector_script

  # Bootstrap user_data: small script that installs AWS CLI then downloads setup from S3
  # AWS CLI is NOT pre-installed on Ubuntu 22.04 AMIs (unlike Amazon Linux)
  bootstrap_user_data = local.use_s3_bootstrap ? "#!/bin/bash\nBUILD_LOG=/var/log/redirector-bootstrap.log\nexec > >(tee -a $BUILD_LOG) 2>&1\necho '=== Redirector Bootstrap ==='\necho \"Started: $(date)\"\necho \"Instance: $(TOKEN=$(curl -s -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 21600' 2>/dev/null); curl -s -H \"X-aws-ec2-metadata-token: $TOKEN\" http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null || echo unknown)\"\nset -e\nexport DEBIAN_FRONTEND=noninteractive\n# Wait for network connectivity (gateway may take a moment after instance boot)\necho 'Waiting for network connectivity...'\nfor i in $(seq 1 30); do\n  if curl -s --connect-timeout 3 http://archive.ubuntu.com > /dev/null 2>&1; then\n    echo \"Network ready after $${i} attempts\"\n    break\n  fi\n  if [ $${i} -eq 30 ]; then\n    echo 'ERROR: Network not available after 5 minutes.'\n    echo \"FAILED: $(date)\" >> $BUILD_LOG\n    exit 1\n  fi\n  echo \"Attempt $${i}/30 - waiting for gateway...\"\n  sleep 10\ndone\necho 'Installing AWS CLI...'\napt-get update -qq && apt-get install -y -qq awscli > /dev/null 2>&1\necho 'Downloading setup script from S3...'\naws s3 cp 's3://${var.deployment_bucket}/${var.deployment_id}/scripts/setup_redirector.sh' /tmp/setup_redirector.sh --region ${var.aws_region}\nchmod +x /tmp/setup_redirector.sh\necho 'Running setup script...'\n/tmp/setup_redirector.sh\necho \"Bootstrap completed: $(date)\" >> $BUILD_LOG\n" : null

  # Final user_data: custom > S3 bootstrap > inline redirector script > none
  final_user_data = var.user_data != "" ? var.user_data : (
    local.use_s3_bootstrap ? local.bootstrap_user_data : (
      local.use_redirector_script ? local.redirector_user_data : null
    )
  )
}

# =============================================================================
# UPLOAD SETUP SCRIPT TO S3 (bypasses 16KB EC2 user_data limit)
# =============================================================================

resource "aws_s3_object" "redirector_setup_script" {
  count = local.use_s3_bootstrap ? 1 : 0

  bucket       = var.deployment_bucket
  key          = "${var.deployment_id}/scripts/setup_redirector.sh"
  content      = local.redirector_user_data
  content_type = "text/plain"

  tags = merge(var.tags, {
    Name      = "${var.project_name}-${var.environment}-redirector-setup-script"
    Component = "Network"
  })
}

# Proxy/Redirector Instances
resource "aws_instance" "proxy_redirector" {
  count = var.proxy_redirector_count

  ami                    = var.ami_id
  instance_type          = var.instance_type
  key_name               = var.key_pair_name
  subnet_id              = var.public_subnet_ids[count.index % length(var.public_subnet_ids)]
  vpc_security_group_ids = [var.security_group_id]
  private_ip             = length(var.private_ips) > count.index ? var.private_ips[count.index] : null

  # Ephemeral storage only - no persistent EBS volumes
  # This enforces the "no data storage" requirement
  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_size
    encrypted             = true
    delete_on_termination = true
  }

  # Require IMDSv2 (prevents SSRF-based credential theft from instance metadata)
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  # Disable detailed monitoring
  monitoring = var.enable_detailed_monitoring

  # IAM role for instance (if provided)
  iam_instance_profile = var.iam_instance_profile_name != "" ? var.iam_instance_profile_name : null

  # User data for proxy configuration
  user_data = local.final_user_data

  # Ensure S3 script is uploaded before instance launches
  depends_on = [aws_s3_object.redirector_setup_script]

  tags = merge(
    var.tags,
    {
      Name         = "${var.project_name}-${var.environment}-redirector-ubuntu-${count.index + 1}"
      Type         = "Proxy"
      Component    = "Network"
      ServerNumber = count.index + 1
    }
  )
}

# Elastic IPs for proxy/redirector servers (needed for public access)
resource "aws_eip" "proxy_redirector_eip" {
  count = var.proxy_redirector_count

  domain   = "vpc"
  instance = aws_instance.proxy_redirector[count.index].id

  tags = merge(
    var.tags,
    {
      Name      = "${var.project_name}-${var.environment}-redirector-ubuntu-${count.index + 1}-eip"
      Type      = "ElasticIP"
      Component = "ProxyInfrastructure"
    }
  )
}

