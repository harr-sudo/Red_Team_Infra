# DNS Module - Route 53 Configuration for C2 Infrastructure
# =============================================================================
# Creates Route 53 hosted zone and DNS records for C2 domains
# The user provides their own domain - this module creates the DNS records
# pointing to the redirector infrastructure
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
# LOCAL VALUES
# =============================================================================

locals {
  # Parse domain parts
  domain_parts = split(".", var.primary_domain_name)

  # Build subdomain FQDNs
  c2_fqdn  = var.c2_subdomain != "" ? "${var.c2_subdomain}.${var.primary_domain_name}" : var.primary_domain_name
  www_fqdn = var.www_subdomain != "" ? "${var.www_subdomain}.${var.primary_domain_name}" : "www.${var.primary_domain_name}"
  cdn_fqdn = var.cdn_subdomain != "" ? "${var.cdn_subdomain}.${var.primary_domain_name}" : "cdn.${var.primary_domain_name}"
}

# =============================================================================
# ROUTE 53 HOSTED ZONE
# =============================================================================

# Option 1: Create a new hosted zone (if user wants AWS to manage DNS)
resource "aws_route53_zone" "c2_domain" {
  count = var.create_hosted_zone ? 1 : 0

  name    = var.primary_domain_name
  comment = "Managed by Terraform - ${var.project_name} C2 Infrastructure"

  tags = merge(var.tags, {
    Name      = "${var.project_name}-${var.environment}-dns-zone"
    Component = "DNS"
    Domain    = var.primary_domain_name
  })
}

# Option 2: Use existing hosted zone (if user already has domain in Route 53)
data "aws_route53_zone" "existing" {
  count = var.create_hosted_zone ? 0 : 1

  name         = var.primary_domain_name
  private_zone = false
}

locals {
  # Use created zone or existing zone
  zone_id = var.create_hosted_zone ? aws_route53_zone.c2_domain[0].zone_id : data.aws_route53_zone.existing[0].zone_id
}

# =============================================================================
# DNS RECORDS - A Records pointing to Redirectors
# =============================================================================

# Primary C2 subdomain -> Redirector(s)
# Skipped when domain fronting is enabled (CloudFront alias records used instead)
resource "aws_route53_record" "c2_primary" {
  count = length(var.redirector_ips) > 0 && !var.enable_domain_fronting ? 1 : 0

  zone_id         = local.zone_id
  name            = local.c2_fqdn
  type            = "A"
  ttl             = var.dns_ttl
  allow_overwrite = true

  # When file portal is enabled, pin to first redirector for consistent file store
  records = var.enable_file_portal ? [var.redirector_ips[0]] : var.redirector_ips
}

# WWW subdomain -> Redirector(s) (for web traffic blending)
# Skipped when domain fronting is enabled (CloudFront alias records used instead)
resource "aws_route53_record" "www" {
  count = length(var.redirector_ips) > 0 && var.enable_www_subdomain && !var.enable_domain_fronting ? 1 : 0

  zone_id         = local.zone_id
  name            = local.www_fqdn
  type            = "A"
  ttl             = var.dns_ttl
  allow_overwrite = true

  # When file portal is enabled, www points to first redirector only for consistent file store
  records = var.enable_file_portal ? [var.redirector_ips[0]] : var.redirector_ips
}

# CDN subdomain -> Redirector(s) (for CDN-style traffic)
# Skipped when domain fronting is enabled (CloudFront alias records used instead)
resource "aws_route53_record" "cdn" {
  count = length(var.redirector_ips) > 0 && var.enable_cdn_subdomain && !var.enable_domain_fronting ? 1 : 0

  zone_id         = local.zone_id
  name            = local.cdn_fqdn
  type            = "A"
  ttl             = var.dns_ttl
  allow_overwrite = true

  records = var.enable_file_portal ? [var.redirector_ips[0]] : var.redirector_ips
}

# Root domain -> Redirector(s) (apex/naked domain)
# Skipped when domain fronting is enabled (CloudFront alias records used instead)
resource "aws_route53_record" "apex" {
  count = length(var.redirector_ips) > 0 && var.enable_apex_record && !var.enable_domain_fronting ? 1 : 0

  zone_id         = local.zone_id
  name            = var.primary_domain_name
  type            = "A"
  ttl             = var.dns_ttl
  allow_overwrite = true

  records = var.enable_file_portal ? [var.redirector_ips[0]] : var.redirector_ips
}

# =============================================================================
# BACKUP DOMAIN RECORDS (if backup domains provided)
# =============================================================================

# For each backup domain, create records pointing to redirectors
# Skipped when domain fronting is enabled (backup domains become CloudFront aliases instead)
resource "aws_route53_record" "backup_domains" {
  for_each = var.create_backup_domain_records && !var.enable_domain_fronting ? toset(var.backup_domains) : toset([])

  zone_id         = local.zone_id
  name            = each.value
  type            = "CNAME"
  ttl             = var.dns_ttl
  allow_overwrite = true

  records = [local.c2_fqdn] # Point to primary C2 FQDN
}

# =============================================================================
# TXT RECORDS (for domain verification, SPF, etc.)
# =============================================================================

# SPF record to help with email reputation (makes domain look more legitimate)
resource "aws_route53_record" "spf" {
  count = var.enable_spf_record ? 1 : 0

  zone_id         = local.zone_id
  name            = var.primary_domain_name
  type            = "TXT"
  ttl             = 3600
  allow_overwrite = true

  records = ["v=spf1 -all"] # Deny all email (we're not sending email)
}

# DMARC record (complements SPF)
resource "aws_route53_record" "dmarc" {
  count = var.enable_dmarc_record ? 1 : 0

  zone_id         = local.zone_id
  name            = "_dmarc.${var.primary_domain_name}"
  type            = "TXT"
  ttl             = 3600
  allow_overwrite = true

  records = ["v=DMARC1; p=reject; sp=reject; adkim=s; aspf=s;"]
}

