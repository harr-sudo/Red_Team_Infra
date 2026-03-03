# VPC Module - Main Configuration
# Creates VPC, subnets, Internet Gateway, and route tables

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# VPC
resource "aws_vpc" "red_team_vpc" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-${var.environment}-vpc"
      Type = "VPC"
    }
  )
}

# Internet Gateway
resource "aws_internet_gateway" "red_team_igw" {
  vpc_id = aws_vpc.red_team_vpc.id

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-${var.environment}-igw"
      Type = "InternetGateway"
    }
  )
}

# Public Subnets
resource "aws_subnet" "public_subnets" {
  count = length(var.public_subnet_cidrs)

  vpc_id                  = aws_vpc.red_team_vpc.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-${var.environment}-public-subnet-${count.index + 1}"
      Type = "PublicSubnet"
      Tier = "Public"
    }
  )
}

# Private Subnets
resource "aws_subnet" "private_subnets" {
  count = length(var.private_subnet_cidrs)

  vpc_id            = aws_vpc.red_team_vpc.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-${var.environment}-private-subnet-${count.index + 1}"
      Type = "PrivateSubnet"
      Tier = "Private"
    }
  )
}

# =============================================================================
# MANAGEMENT SUBNETS (Bastion Isolation - OPSEC)
# =============================================================================
# Separates the bastion/jump box from the DMZ where redirectors live.
# If a redirector is compromised, the attacker cannot pivot to the management
# bastion on the same subnet. Management subnet has its own route table and NACLs.

resource "aws_subnet" "management_subnets" {
  count = length(var.management_subnet_cidrs)

  vpc_id                  = aws_vpc.red_team_vpc.id
  cidr_block              = var.management_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index % length(var.availability_zones)]
  map_public_ip_on_launch = true # Bastion needs public IP for operator RDP/SSH

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-${var.environment}-management-subnet-${count.index + 1}"
      Type = "ManagementSubnet"
      Tier = "Management"
    }
  )
}

# Public Route Table
resource "aws_route_table" "public_rt" {
  vpc_id = aws_vpc.red_team_vpc.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.red_team_igw.id
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-${var.environment}-public-rt"
      Type = "RouteTable"
      Tier = "Public"
    }
  )
}

# Public Route Table Associations
resource "aws_route_table_association" "public_rta" {
  count = length(aws_subnet.public_subnets)

  subnet_id      = aws_subnet.public_subnets[count.index].id
  route_table_id = aws_route_table.public_rt.id
}

# =============================================================================
# MANAGEMENT ROUTE TABLE
# =============================================================================
# Separate from the DMZ public route table. Both use the IGW, but separation
# allows different NACLs and isolates management traffic from operational traffic.

resource "aws_route_table" "management_rt" {
  count  = length(var.management_subnet_cidrs) > 0 ? 1 : 0
  vpc_id = aws_vpc.red_team_vpc.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.red_team_igw.id
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-${var.environment}-management-rt"
      Type = "RouteTable"
      Tier = "Management"
    }
  )
}

resource "aws_route_table_association" "management_rta" {
  count = length(aws_subnet.management_subnets)

  subnet_id      = aws_subnet.management_subnets[count.index].id
  route_table_id = aws_route_table.management_rt[0].id
}

# Private Route Table
# Always created — private subnets need their own route table for VPC-internal routing.
# When NAT gateway is enabled, a route to the NAT gateway is added for outbound internet.
# When NAT gateway is disabled, private subnets can only communicate within the VPC.
resource "aws_route_table" "private_rt" {
  vpc_id = aws_vpc.red_team_vpc.id

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-${var.environment}-private-rt"
      Type = "RouteTable"
      Tier = "Private"
    }
  )
}

# Private Route Table Associations
resource "aws_route_table_association" "private_rta" {
  count = length(aws_subnet.private_subnets)

  subnet_id      = aws_subnet.private_subnets[count.index].id
  route_table_id = aws_route_table.private_rt.id
}

# NAT Gateway (optional — provides outbound internet for private subnets)
# Required if C2 servers need to download packages (apt-get) or reach external services.
# Without NAT, private subnets are VPC-internal only (redirector traffic still works via VPC routing).
resource "aws_eip" "nat_eip" {
  count  = var.enable_nat_gateway ? 1 : 0
  domain = "vpc"

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-${var.environment}-nat-eip"
      Type = "NATGateway"
    }
  )
}

resource "aws_nat_gateway" "nat_gw" {
  count         = var.enable_nat_gateway ? 1 : 0
  allocation_id = aws_eip.nat_eip[0].id
  subnet_id     = aws_subnet.public_subnets[0].id

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-${var.environment}-nat-gw"
      Type = "NATGateway"
    }
  )

  depends_on = [aws_internet_gateway.red_team_igw]
}

resource "aws_route" "private_nat_route" {
  count                  = var.enable_nat_gateway ? 1 : 0
  route_table_id         = aws_route_table.private_rt.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.nat_gw[0].id
}

# =============================================================================
# NETWORK ACLs (Optional - Defense in Depth)
# =============================================================================
# NACLs are stateless — both inbound AND outbound rules are required.
# These provide subnet-level firewall rules on top of security groups.
# Disabled by default (enable_nacls = false) to avoid breaking existing deployments.

# -----------------------------------------------------------------------------
# Management Tier NACL — Bastion access only from operator IPs
# -----------------------------------------------------------------------------
resource "aws_network_acl" "management_nacl" {
  count  = var.enable_nacls && length(var.management_subnet_cidrs) > 0 ? 1 : 0
  vpc_id = aws_vpc.red_team_vpc.id

  subnet_ids = aws_subnet.management_subnets[*].id

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-${var.environment}-management-nacl"
      Type = "NetworkACL"
      Tier = "Management"
    }
  )
}

# Management NACL: Allow SSH inbound from operator CIDRs
resource "aws_network_acl_rule" "mgmt_inbound_ssh" {
  count          = var.enable_nacls && length(var.management_subnet_cidrs) > 0 ? length(var.management_cidr_blocks) : 0
  network_acl_id = aws_network_acl.management_nacl[0].id
  rule_number    = 100 + count.index
  egress         = false
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = var.management_cidr_blocks[count.index]
  from_port      = var.ssh_port
  to_port        = var.ssh_port
}

# Management NACL: Allow RDP inbound from operator CIDRs
resource "aws_network_acl_rule" "mgmt_inbound_rdp" {
  count          = var.enable_nacls && length(var.management_subnet_cidrs) > 0 ? length(var.management_cidr_blocks) : 0
  network_acl_id = aws_network_acl.management_nacl[0].id
  rule_number    = 200 + count.index
  egress         = false
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = var.management_cidr_blocks[count.index]
  from_port      = 3389
  to_port        = 3389
}

# Management NACL: Allow ephemeral ports inbound (return traffic from VPC + internet)
resource "aws_network_acl_rule" "mgmt_inbound_ephemeral" {
  count          = var.enable_nacls && length(var.management_subnet_cidrs) > 0 ? 1 : 0
  network_acl_id = aws_network_acl.management_nacl[0].id
  rule_number    = 900
  egress         = false
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
  from_port      = 1024
  to_port        = 65535
}

# Management NACL: Allow all outbound to VPC (SSH to C2 servers, redirectors)
resource "aws_network_acl_rule" "mgmt_outbound_vpc" {
  count          = var.enable_nacls && length(var.management_subnet_cidrs) > 0 ? 1 : 0
  network_acl_id = aws_network_acl.management_nacl[0].id
  rule_number    = 100
  egress         = true
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = var.vpc_cidr
  from_port      = 1
  to_port        = 65535
}

# Management NACL: Allow HTTPS outbound (package updates, AWS APIs)
resource "aws_network_acl_rule" "mgmt_outbound_https" {
  count          = var.enable_nacls && length(var.management_subnet_cidrs) > 0 ? 1 : 0
  network_acl_id = aws_network_acl.management_nacl[0].id
  rule_number    = 200
  egress         = true
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
  from_port      = 443
  to_port        = 443
}

# Management NACL: Allow ephemeral ports outbound (return traffic to operator)
resource "aws_network_acl_rule" "mgmt_outbound_ephemeral" {
  count          = var.enable_nacls && length(var.management_subnet_cidrs) > 0 ? 1 : 0
  network_acl_id = aws_network_acl.management_nacl[0].id
  rule_number    = 900
  egress         = true
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
  from_port      = 1024
  to_port        = 65535
}

# -----------------------------------------------------------------------------
# DMZ Tier NACL — Redirectors: internet-facing HTTP/HTTPS, limited internal access
# -----------------------------------------------------------------------------
resource "aws_network_acl" "dmz_nacl" {
  count  = var.enable_nacls ? 1 : 0
  vpc_id = aws_vpc.red_team_vpc.id

  subnet_ids = aws_subnet.public_subnets[*].id

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-${var.environment}-dmz-nacl"
      Type = "NetworkACL"
      Tier = "DMZ"
    }
  )
}

# DMZ NACL: Allow HTTP inbound from internet (redirector traffic)
resource "aws_network_acl_rule" "dmz_inbound_http" {
  count          = var.enable_nacls ? 1 : 0
  network_acl_id = aws_network_acl.dmz_nacl[0].id
  rule_number    = 100
  egress         = false
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
  from_port      = 80
  to_port        = 80
}

# DMZ NACL: Allow HTTPS inbound from internet (redirector traffic)
resource "aws_network_acl_rule" "dmz_inbound_https" {
  count          = var.enable_nacls ? 1 : 0
  network_acl_id = aws_network_acl.dmz_nacl[0].id
  rule_number    = 110
  egress         = false
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
  from_port      = 443
  to_port        = 443
}

# DMZ NACL: Allow SSH inbound from management subnet (admin access to redirectors)
resource "aws_network_acl_rule" "dmz_inbound_ssh_from_mgmt" {
  count          = var.enable_nacls && length(var.management_subnet_cidrs) > 0 ? length(var.management_subnet_cidrs) : 0
  network_acl_id = aws_network_acl.dmz_nacl[0].id
  rule_number    = 200 + count.index
  egress         = false
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = var.management_subnet_cidrs[count.index]
  from_port      = var.ssh_port
  to_port        = var.ssh_port
}

# DMZ NACL: Allow SSH inbound from operator CIDRs (fallback when no management subnet)
resource "aws_network_acl_rule" "dmz_inbound_ssh_from_operator" {
  count          = var.enable_nacls && length(var.management_subnet_cidrs) == 0 ? length(var.management_cidr_blocks) : 0
  network_acl_id = aws_network_acl.dmz_nacl[0].id
  rule_number    = 200 + count.index
  egress         = false
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = var.management_cidr_blocks[count.index]
  from_port      = var.ssh_port
  to_port        = var.ssh_port
}

# DMZ NACL: Allow ephemeral ports inbound (return traffic)
resource "aws_network_acl_rule" "dmz_inbound_ephemeral" {
  count          = var.enable_nacls ? 1 : 0
  network_acl_id = aws_network_acl.dmz_nacl[0].id
  rule_number    = 900
  egress         = false
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
  from_port      = 1024
  to_port        = 65535
}

# DMZ NACL: Allow C2 port outbound to private subnets (forward to team server)
resource "aws_network_acl_rule" "dmz_outbound_c2" {
  count          = var.enable_nacls ? length(var.private_subnet_cidrs) : 0
  network_acl_id = aws_network_acl.dmz_nacl[0].id
  rule_number    = 100 + count.index
  egress         = true
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = var.private_subnet_cidrs[count.index]
  from_port      = var.c2_server_port
  to_port        = var.c2_server_port
}

# DMZ NACL: Allow HTTPS outbound (Let's Encrypt, package updates)
resource "aws_network_acl_rule" "dmz_outbound_https" {
  count          = var.enable_nacls ? 1 : 0
  network_acl_id = aws_network_acl.dmz_nacl[0].id
  rule_number    = 200
  egress         = true
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
  from_port      = 443
  to_port        = 443
}

# DMZ NACL: Allow HTTP outbound (Let's Encrypt ACME challenge)
resource "aws_network_acl_rule" "dmz_outbound_http" {
  count          = var.enable_nacls ? 1 : 0
  network_acl_id = aws_network_acl.dmz_nacl[0].id
  rule_number    = 210
  egress         = true
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
  from_port      = 80
  to_port        = 80
}

# DMZ NACL: Allow ephemeral ports outbound (return traffic to clients)
resource "aws_network_acl_rule" "dmz_outbound_ephemeral" {
  count          = var.enable_nacls ? 1 : 0
  network_acl_id = aws_network_acl.dmz_nacl[0].id
  rule_number    = 900
  egress         = true
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
  from_port      = 1024
  to_port        = 65535
}

# -----------------------------------------------------------------------------
# Private Tier NACL — C2 servers: accept from DMZ, SSH from management, NAT outbound
# -----------------------------------------------------------------------------
resource "aws_network_acl" "private_nacl" {
  count  = var.enable_nacls ? 1 : 0
  vpc_id = aws_vpc.red_team_vpc.id

  subnet_ids = aws_subnet.private_subnets[*].id

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-${var.environment}-private-nacl"
      Type = "NetworkACL"
      Tier = "Private"
    }
  )
}

# Private NACL: Allow C2 port inbound from DMZ subnets (redirector → team server)
resource "aws_network_acl_rule" "private_inbound_c2" {
  count          = var.enable_nacls ? length(var.public_subnet_cidrs) : 0
  network_acl_id = aws_network_acl.private_nacl[0].id
  rule_number    = 100 + count.index
  egress         = false
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = var.public_subnet_cidrs[count.index]
  from_port      = var.c2_server_port
  to_port        = var.c2_server_port
}

# Private NACL: Allow SSH inbound from management subnet
resource "aws_network_acl_rule" "private_inbound_ssh_from_mgmt" {
  count          = var.enable_nacls && length(var.management_subnet_cidrs) > 0 ? length(var.management_subnet_cidrs) : 0
  network_acl_id = aws_network_acl.private_nacl[0].id
  rule_number    = 200 + count.index
  egress         = false
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = var.management_subnet_cidrs[count.index]
  from_port      = var.ssh_port
  to_port        = var.ssh_port
}

# Private NACL: Allow SSH inbound from DMZ (fallback when no management subnet)
resource "aws_network_acl_rule" "private_inbound_ssh_from_dmz" {
  count          = var.enable_nacls && length(var.management_subnet_cidrs) == 0 ? length(var.public_subnet_cidrs) : 0
  network_acl_id = aws_network_acl.private_nacl[0].id
  rule_number    = 200 + count.index
  egress         = false
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = var.public_subnet_cidrs[count.index]
  from_port      = var.ssh_port
  to_port        = var.ssh_port
}

# Private NACL: Allow ephemeral ports inbound (return traffic from NAT gateway)
resource "aws_network_acl_rule" "private_inbound_ephemeral" {
  count          = var.enable_nacls ? 1 : 0
  network_acl_id = aws_network_acl.private_nacl[0].id
  rule_number    = 900
  egress         = false
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
  from_port      = 1024
  to_port        = 65535
}

# Private NACL: Allow HTTPS outbound (via NAT gateway for package updates, S3)
resource "aws_network_acl_rule" "private_outbound_https" {
  count          = var.enable_nacls ? 1 : 0
  network_acl_id = aws_network_acl.private_nacl[0].id
  rule_number    = 100
  egress         = true
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
  from_port      = 443
  to_port        = 443
}

# Private NACL: Allow HTTP outbound (via NAT gateway for apt-get)
resource "aws_network_acl_rule" "private_outbound_http" {
  count          = var.enable_nacls ? 1 : 0
  network_acl_id = aws_network_acl.private_nacl[0].id
  rule_number    = 110
  egress         = true
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
  from_port      = 80
  to_port        = 80
}

# Private NACL: Allow ephemeral ports outbound (return traffic to DMZ/management)
resource "aws_network_acl_rule" "private_outbound_ephemeral" {
  count          = var.enable_nacls ? 1 : 0
  network_acl_id = aws_network_acl.private_nacl[0].id
  rule_number    = 900
  egress         = true
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
  from_port      = 1024
  to_port        = 65535
}

