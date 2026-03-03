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
  description = "ID of the private route table"
  value       = aws_route_table.private_rt.id
}

output "private_route_table_ids" {
  description = "List of private route table IDs (for VPC peering)"
  value       = [aws_route_table.private_rt.id]
}

output "management_subnet_ids" {
  description = "IDs of the management subnets (bastion isolation)"
  value       = aws_subnet.management_subnets[*].id
}

output "management_route_table_id" {
  description = "ID of the management route table (null if no management subnets)"
  value       = length(aws_route_table.management_rt) > 0 ? aws_route_table.management_rt[0].id : null
}

output "all_route_table_ids" {
  description = "All route table IDs in the VPC (public, private, management)"
  value = concat(
    [aws_route_table.public_rt.id, aws_route_table.private_rt.id],
    length(aws_route_table.management_rt) > 0 ? [aws_route_table.management_rt[0].id] : []
  )
}

output "nat_gateway_id" {
  description = "ID of the NAT Gateway (if enabled)"
  value       = var.enable_nat_gateway ? aws_nat_gateway.nat_gw[0].id : null
}

output "nat_gateway_public_ip" {
  description = "Public IP of the NAT Gateway (if enabled)"
  value       = var.enable_nat_gateway ? aws_eip.nat_eip[0].public_ip : null
}
