# GOAD Module - Network Configuration
# =============================================================================
# Creates VPC, subnets, gateways, and route tables for GOAD lab
# =============================================================================

# =============================================================================
# VPC
# =============================================================================

resource "aws_vpc" "goad" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(var.tags, {
    Name = "${var.project_name}-${local.lab_identifier}-vpc"
    Lab  = local.lab_identifier
    Type = "GOAD"
  })
}

# =============================================================================
# SUBNETS
# =============================================================================

# Public subnet (for jumpbox)
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.goad.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = var.availability_zone
  map_public_ip_on_launch = true

  tags = merge(var.tags, {
    Name = "${var.project_name}-${local.lab_identifier}-public-subnet"
    Lab  = local.lab_identifier
    Tier = "Public"
  })
}

# Private subnet (for AD VMs)
resource "aws_subnet" "private" {
  vpc_id            = aws_vpc.goad.id
  cidr_block        = var.private_subnet_cidr
  availability_zone = var.availability_zone

  tags = merge(var.tags, {
    Name = "${var.project_name}-${local.lab_identifier}-private-subnet"
    Lab  = local.lab_identifier
    Tier = "Private"
  })
}

# =============================================================================
# INTERNET GATEWAY
# =============================================================================

resource "aws_internet_gateway" "goad" {
  vpc_id = aws_vpc.goad.id

  tags = merge(var.tags, {
    Name = "${var.project_name}-${local.lab_identifier}-igw"
    Lab  = local.lab_identifier
  })
}

# =============================================================================
# NAT GATEWAY (for private subnet internet access)
# =============================================================================

resource "aws_eip" "nat" {
  domain = "vpc"

  tags = merge(var.tags, {
    Name = "${var.project_name}-${local.lab_identifier}-nat-eip"
    Lab  = local.lab_identifier
  })

  depends_on = [aws_internet_gateway.goad]
}

resource "aws_nat_gateway" "goad" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public.id

  tags = merge(var.tags, {
    Name = "${var.project_name}-${local.lab_identifier}-nat-gw"
    Lab  = local.lab_identifier
  })

  depends_on = [aws_internet_gateway.goad]
}

# =============================================================================
# ROUTE TABLES
# =============================================================================

# Public route table
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.goad.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.goad.id
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-${local.lab_identifier}-public-rt"
    Lab  = local.lab_identifier
    Tier = "Public"
  })
}

# Private route table (through NAT)
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.goad.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.goad.id
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-${local.lab_identifier}-private-rt"
    Lab  = local.lab_identifier
    Tier = "Private"
  })
}

# Route table associations
resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  subnet_id      = aws_subnet.private.id
  route_table_id = aws_route_table.private.id
}

# =============================================================================
# S3 VPC ENDPOINT (Gateway) — Required for IAM Confused Deputy Protection
# =============================================================================
# Without this, S3 requests go through NAT Gateway and lose VPC context,
# causing IAM policy conditions on aws:SourceVpc to deny access.
# The S3 Gateway endpoint routes S3 traffic through the AWS private network,
# preserving the VPC ID in the request context. This is FREE (no hourly charges).
#
# Required for: deployment_storage module IAM roles (confused deputy protection)

resource "aws_vpc_endpoint" "s3" {
  vpc_id       = aws_vpc.goad.id
  service_name = "com.amazonaws.${var.aws_region}.s3"

  # Associate with ALL route tables so every subnet can reach S3 via the endpoint
  route_table_ids = [
    aws_route_table.public.id,
    aws_route_table.private.id
  ]

  tags = merge(var.tags, {
    Name = "${var.project_name}-${local.lab_identifier}-s3-endpoint"
    Lab  = local.lab_identifier
  })
}

