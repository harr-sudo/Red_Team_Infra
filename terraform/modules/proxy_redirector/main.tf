# Proxy/Redirector Module
# Creates EC2 instances for proxy/redirector servers in public subnets
# These servers are pass-through only with no data storage

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Proxy/Redirector Instances
resource "aws_instance" "proxy_redirector" {
  count = var.proxy_redirector_count

  ami                    = var.ami_id
  instance_type          = var.instance_type
  key_name               = var.key_pair_name
  subnet_id              = var.public_subnet_ids[count.index % length(var.public_subnet_ids)]
  vpc_security_group_ids = [var.security_group_id]

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

  # User data for proxy configuration (pass-through setup)
  user_data = var.user_data != "" ? var.user_data : null

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-${var.environment}-proxy-redirector-${count.index + 1}"
      Type = "ProxyRedirector"
      Component = "ProxyInfrastructure"
      ServerNumber = count.index + 1
      DataStorage = "None"
      PassThrough = "True"
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
      Name = "${var.project_name}-${var.environment}-proxy-redirector-${count.index + 1}-eip"
      Type = "ElasticIP"
      Component = "ProxyInfrastructure"
    }
  )
}

