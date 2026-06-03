# Domain Fronting Module - CloudFront CDN Proxy for C2 Traffic
# =============================================================================
# Creates a CloudFront distribution in front of redirectors to:
# - Hide redirector IPs behind CloudFront CDN IPs
# - Make C2 traffic appear as normal CDN traffic
# - Enable domain fronting (beacon connects to front domain, Host header
#   routes to our distribution)
# - Support domain rotation via backup domain aliases
#
# CRITICAL C2 SETTINGS:
# - Caching is FULLY DISABLED (cached responses break beacon callbacks)
# - ALL headers, cookies, and query strings are forwarded to origin
# - All HTTP methods are allowed (beacons use GET, POST, and potentially others)
# - HTTPS-only origin communication
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
  c2_fqdn  = "${var.c2_subdomain}.${var.primary_domain_name}"
  www_fqdn = "${var.www_subdomain}.${var.primary_domain_name}"
  cdn_fqdn = "${var.cdn_subdomain}.${var.primary_domain_name}"

  # Build the full list of CloudFront aliases (all domains on one distribution)
  # Primary domain subdomains
  primary_aliases = compact([
    local.c2_fqdn,
    var.enable_www_subdomain ? local.www_fqdn : null,
    var.enable_cdn_subdomain ? local.cdn_fqdn : null,
    var.enable_apex_record ? var.primary_domain_name : null,
  ])

  # All aliases = primary subdomains + backup domains
  all_aliases = concat(local.primary_aliases, var.backup_domains)

  # Primary domain subdomains that need Route 53 alias records
  # (backup domains may not be in our Route 53, so handled separately)
  primary_alias_map = {
    for alias in local.primary_aliases : alias => alias
  }
}

# =============================================================================
# CLOUDFRONT DISTRIBUTION
# =============================================================================
# Single distribution with all domains as aliases.
# This allows instant domain rotation — just change the CS profile to use
# a different alias, no infrastructure change needed.

resource "aws_cloudfront_distribution" "c2" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${var.project_name}-${var.environment} C2 domain fronting"
  aliases             = local.all_aliases
  price_class         = "PriceClass_100" # EU/US edges only (cheapest, matches allowed regions)
  wait_for_deployment = false            # CloudFront takes 15-30 min — don't block Terraform

  # ==========================================================================
  # ORIGIN: Existing redirector(s)
  # ==========================================================================

  origin {
    domain_name = var.origin_ips[0]
    origin_id   = "redirector-primary"

    custom_origin_config {
      http_port  = 80
      https_port = 443
      # HTTP-only: CloudFront cannot do TLS hostname verification against a raw IP origin.
      # The redirector's Let's Encrypt cert matches the domain, not the IP, causing TLS mismatch → 502.
      # Edge-to-viewer traffic is still HTTPS; beacon payloads are encrypted within the C2 protocol.
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]

      # Extended timeouts for C2 (long-polling beacons, sleep intervals)
      origin_read_timeout      = 60
      origin_keepalive_timeout = 60
    }
  }

  # ==========================================================================
  # DEFAULT CACHE BEHAVIOR: NO CACHING, FORWARD EVERYTHING
  # ==========================================================================
  # CRITICAL: Every request must reach the origin. Cached responses cause
  # beacons to receive stale commands or fail entirely.

  default_cache_behavior {
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "redirector-primary"
    viewer_protocol_policy = "redirect-to-https"
    compress               = false # C2 traffic has its own encoding

    # Disable caching entirely
    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0

    # Forward ALL headers, cookies, and query strings to origin
    # C2 beacons use custom headers and cookies for communication
    forwarded_values {
      query_string = true
      headers      = ["*"]

      cookies {
        forward = "all"
      }
    }
  }

  # ==========================================================================
  # SSL/TLS: ACM certificate (provisioned in us-east-1)
  # ==========================================================================

  viewer_certificate {
    acm_certificate_arn      = var.acm_certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  # No geographic restrictions
  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  tags = merge(var.tags, {
    Name      = "${var.project_name}-${var.environment}-cf-c2"
    Component = "DomainFronting"
  })
}

# =============================================================================
# DNS RECORDS - Route 53 alias records for primary domain subdomains
# =============================================================================
# These point primary domain subdomains to CloudFront instead of redirector IPs.
# Backup domains may be hosted outside Route 53, so they are not created here —
# operators must manually create CNAME records pointing to the CloudFront domain.

resource "aws_route53_record" "cf_alias" {
  for_each = local.primary_alias_map

  zone_id = var.route53_zone_id
  name    = each.value
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.c2.domain_name
    zone_id                = aws_cloudfront_distribution.c2.hosted_zone_id
    evaluate_target_health = false
  }
}
