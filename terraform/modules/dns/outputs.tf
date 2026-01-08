# DNS Module Outputs
# =============================================================================

output "zone_id" {
  description = "Route 53 hosted zone ID"
  value       = local.zone_id
}

output "zone_name_servers" {
  description = "Name servers for the hosted zone (user needs to point their domain registrar here)"
  value       = var.create_hosted_zone ? aws_route53_zone.c2_domain[0].name_servers : []
}

output "primary_domain" {
  description = "Primary domain name"
  value       = var.primary_domain_name
}

output "c2_fqdn" {
  description = "Fully qualified domain name for C2 traffic"
  value       = local.c2_fqdn
}

output "www_fqdn" {
  description = "Fully qualified domain name for www subdomain"
  value       = local.www_fqdn
}

output "cdn_fqdn" {
  description = "Fully qualified domain name for CDN subdomain"
  value       = local.cdn_fqdn
}

output "all_fqdns" {
  description = "All FQDNs created for this domain"
  value = compact([
    local.c2_fqdn,
    var.enable_www_subdomain ? local.www_fqdn : "",
    var.enable_cdn_subdomain ? local.cdn_fqdn : "",
    var.enable_apex_record ? var.primary_domain_name : ""
  ])
}

output "dns_records" {
  description = "Map of DNS record names to their IPs"
  value = {
    c2_subdomain = length(var.redirector_ips) > 0 ? {
      fqdn    = local.c2_fqdn
      type    = "A"
      records = var.redirector_ips
    } : null
    www = length(var.redirector_ips) > 0 && var.enable_www_subdomain ? {
      fqdn    = local.www_fqdn
      type    = "A"
      records = var.redirector_ips
    } : null
    cdn = length(var.redirector_ips) > 0 && var.enable_cdn_subdomain ? {
      fqdn    = local.cdn_fqdn
      type    = "A"
      records = var.redirector_ips
    } : null
    apex = length(var.redirector_ips) > 0 && var.enable_apex_record ? {
      fqdn    = var.primary_domain_name
      type    = "A"
      records = var.redirector_ips
    } : null
  }
}

output "nameserver_instructions" {
  description = "Instructions for the user to configure their domain registrar"
  value = var.create_hosted_zone ? join("\n", [
    "============================================================",
    "IMPORTANT: DNS Configuration Required",
    "============================================================",
    "",
    "To complete your domain setup, update your domain registrar",
    "with the following name servers:",
    "",
    join("\n", aws_route53_zone.c2_domain[0].name_servers),
    "",
    "This may take up to 48 hours to propagate globally.",
    "============================================================"
  ]) : "Using existing hosted zone - no additional configuration needed."
}