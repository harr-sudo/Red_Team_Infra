# VPC Module Outputs

output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.red_team_vpc.id
}

output "vpc_cidr_block" {
  description = "CIDR block of the VPC"
  value       = aws_vpc.red_team_vpc.cidr_block
}

output "public_subnet_ids" {
  description = "IDs of the public subnets"
  value       = aws_subnet.public_subnets[*].id
}

output "private_subnet_ids" {
  description = "IDs of the private subnets"
  value       = aws_subnet.private_subnets[*].id
}

output "internet_gateway_id" {
  description = "ID of the Internet Gateway"
  value       = aws_internet_gateway.red_team_igw.id
}

output "public_route_table_id" {
  description = "ID of the public route table"
  value       = aws_route_table.public_rt.id
}

output "private_route_table_id" {
  description = "ID of the private route table (if NAT Gateway enabled)"
  value       = var.enable_nat_gateway ? aws_route_table.private_rt[0].id : null
}

output "private_route_table_ids" {
  description = "List of private route table IDs (for VPC peering)"
  value       = var.enable_nat_gateway ? [aws_route_table.private_rt[0].id] : [aws_route_table.public_rt.id]
}

output "all_route_table_ids" {
  description = "All route table IDs in the VPC"
  value       = var.enable_nat_gateway ? [aws_route_table.public_rt.id, aws_route_table.private_rt[0].id] : [aws_route_table.public_rt.id]
}
