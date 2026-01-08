# VPC Peering Module - Main Configuration
# =============================================================================
# Creates VPC peering connection between C2 VPC and GOAD VPC
# Updates route tables in both VPCs to allow cross-VPC communication
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
# VPC PEERING CONNECTION
# =============================================================================

resource "aws_vpc_peering_connection" "c2_to_goad" {
  vpc_id      = var.c2_vpc_id
  peer_vpc_id = var.goad_vpc_id
  auto_accept = true # Same account, same region

  accepter {
    allow_remote_vpc_dns_resolution = true
  }

  requester {
    allow_remote_vpc_dns_resolution = true
  }

  tags = merge(var.tags, {
    Name      = "${var.project_name}-c2-to-goad-peering"
    Type      = "VPCPeering"
    Component = "Combined"
  })
}

# =============================================================================
# ROUTE TABLE UPDATES - C2 VPC to GOAD VPC
# =============================================================================

# Add route to GOAD VPC from each C2 route table
resource "aws_route" "c2_to_goad" {
  count = length(var.c2_route_table_ids)

  route_table_id            = var.c2_route_table_ids[count.index]
  destination_cidr_block    = var.goad_cidr
  vpc_peering_connection_id = aws_vpc_peering_connection.c2_to_goad.id
}

# =============================================================================
# ROUTE TABLE UPDATES - GOAD VPC to C2 VPC
# =============================================================================

# Add route to C2 VPC from each GOAD route table
resource "aws_route" "goad_to_c2" {
  count = length(var.goad_route_table_ids)

  route_table_id            = var.goad_route_table_ids[count.index]
  destination_cidr_block    = var.c2_cidr
  vpc_peering_connection_id = aws_vpc_peering_connection.c2_to_goad.id
}

