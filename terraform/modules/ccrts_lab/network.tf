# CCRTS Lab Module - Network
# =============================================================================
# Self-contained VPC with one public subnet (for NAT egress) and one private
# subnet (for all lab hosts). The lab has NO direct internet ingress — operator
# access only flows from the dashboard VPC via VPC peering.
# =============================================================================

# =============================================================================
# VPC
# =============================================================================

resource "aws_vpc" "ccrts" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(local.base_tags, {
    Name = "${local.name_prefix}-vpc"
    Type = "CCRTS"
  })
}

# =============================================================================
# SUBNETS
# =============================================================================

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.ccrts.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = var.availability_zone
  map_public_ip_on_launch = false

  tags = merge(local.base_tags, {
    Name = "${local.name_prefix}-public-subnet"
    Tier = "Public"
  })
}

resource "aws_subnet" "private" {
  vpc_id            = aws_vpc.ccrts.id
  cidr_block        = var.private_subnet_cidr
  availability_zone = var.availability_zone

  tags = merge(local.base_tags, {
    Name = "${local.name_prefix}-private-subnet"
    Tier = "Private"
  })
}

# =============================================================================
# INTERNET GATEWAY
# =============================================================================

resource "aws_internet_gateway" "ccrts" {
  vpc_id = aws_vpc.ccrts.id

  tags = merge(local.base_tags, {
    Name = "${local.name_prefix}-igw"
  })
}

# =============================================================================
# NAT GATEWAY (for private subnet outbound — CREST AMIs, ELK images, updates)
# =============================================================================

resource "aws_eip" "nat" {
  domain = "vpc"

  tags = merge(local.base_tags, {
    Name = "${local.name_prefix}-nat-eip"
  })

  depends_on = [aws_internet_gateway.ccrts]
}

resource "aws_nat_gateway" "ccrts" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public.id

  tags = merge(local.base_tags, {
    Name = "${local.name_prefix}-nat-gw"
  })

  depends_on = [aws_internet_gateway.ccrts]
}

# =============================================================================
# ROUTE TABLES
# =============================================================================

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.ccrts.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.ccrts.id
  }

  tags = merge(local.base_tags, {
    Name = "${local.name_prefix}-public-rt"
    Tier = "Public"
  })
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.ccrts.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.ccrts.id
  }

  tags = merge(local.base_tags, {
    Name = "${local.name_prefix}-private-rt"
    Tier = "Private"
  })
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  subnet_id      = aws_subnet.private.id
  route_table_id = aws_route_table.private.id
}

# =============================================================================
# S3 VPC ENDPOINT (gateway) — keeps SSM Agent + any S3 fetches on the AWS
# private backbone; required for confused-deputy IAM conditions on shared S3.
# =============================================================================

resource "aws_vpc_endpoint" "s3" {
  vpc_id       = aws_vpc.ccrts.id
  service_name = "com.amazonaws.${var.aws_region}.s3"

  route_table_ids = [
    aws_route_table.public.id,
    aws_route_table.private.id,
  ]

  tags = merge(local.base_tags, {
    Name = "${local.name_prefix}-s3-endpoint"
  })
}
