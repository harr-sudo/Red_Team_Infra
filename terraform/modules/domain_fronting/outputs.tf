# Domain Fronting Module Outputs
# =============================================================================

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = aws_cloudfront_distribution.c2.id
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name (e.g., d123abc.cloudfront.net). Use this as the Host header value in CS malleable profile."
  value       = aws_cloudfront_distribution.c2.domain_name
}

output "cloudfront_arn" {
  description = "CloudFront distribution ARN"
  value       = aws_cloudfront_distribution.c2.arn
}

output "cloudfront_status" {
  description = "CloudFront distribution deployment status"
  value       = aws_cloudfront_distribution.c2.status
}

output "cloudfront_aliases" {
  description = "All domains configured as CloudFront aliases (available for domain rotation)"
  value       = local.all_aliases
}

output "dns_records" {
  description = "Route 53 alias records created for primary domain subdomains"
  value       = { for k, v in aws_route53_record.cf_alias : k => v.fqdn }
}
