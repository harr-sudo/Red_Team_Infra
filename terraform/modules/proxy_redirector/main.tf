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

  # Determine SSL provider (support both new and legacy variable)
  effective_ssl_provider = var.ssl_provider != "letsencrypt" ? var.ssl_provider : (var.use_letsencrypt ? "letsencrypt" : var.ssl_provider)

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
    hostname          = "redirector-ubuntu"
  }) : null

  # Final user_data: custom > redirector script > none
  final_user_data = var.user_data != "" ? var.user_data : (
    local.use_redirector_script ? local.redirector_user_data : null
  )
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

  # Disable detailed monitoring
  monitoring = var.enable_detailed_monitoring

  # IAM role for instance (if provided)
  iam_instance_profile = var.iam_instance_profile_name != "" ? var.iam_instance_profile_name : null

  # User data for proxy configuration
  user_data = local.final_user_data

  tags = merge(
    var.tags,
    {
      Name         = "${var.project_name}-${var.environment}-redirector-ubuntu-${count.index + 1}"
      Type         = "ProxyRedirector"
      Component    = "ProxyInfrastructure"
      ServerNumber = count.index + 1
      DataStorage  = "None"
      PassThrough  = "True"
      Domain       = var.primary_domain != "" ? var.primary_domain : "none"
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

