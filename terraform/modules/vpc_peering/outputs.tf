# VPC Peering Module - Outputs
# =============================================================================

output "peering_connection_id" {
  description = "ID of the VPC peering connection"
  value       = aws_vpc_peering_connection.c2_to_goad.id
}

output "peering_connection_status" {
  description = "Status of the VPC peering connection"
  value       = aws_vpc_peering_connection.c2_to_goad.accept_status
}

output "c2_to_goad_routes" {
  description = "Route IDs for C2 to GOAD routes"
  value       = aws_route.c2_to_goad[*].id
}

output "goad_to_c2_routes" {
  description = "Route IDs for GOAD to C2 routes"
  value       = aws_route.goad_to_c2[*].id
}

