# ACM Certificate Module - SSL/TLS for C2 Infrastructure
# =============================================================================
# Provisions SSL certificates via AWS Certificate Manager
# Certificates are validated via DNS (Route 53)
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
# ACM CERTIFICATE
# =============================================================================

resource "aws_acm_certificate" "c2_cert" {
  domain_name       = var.primary_domain_name
  validation_method = "DNS"

  # Include all subdomains in the certificate (SAN - Subject Alternative Names)
  subject_alternative_names = compact([
    "*.${var.primary_domain_name}", # Wildcard for all subdomains
    var.c2_subdomain != "" ? "${var.c2_subdomain}.${var.primary_domain_name}" : null,
    var.www_subdomain != "" ? "${var.www_subdomain}.${var.primary_domain_name}" : null,
    var.cdn_subdomain != "" ? "${var.cdn_subdomain}.${var.primary_domain_name}" : null,
  ])

  tags = merge(var.tags, {
    Name      = "${var.project_name}-${var.environment}-c2-cert"
    Component = "SSL"
    Domain    = var.primary_domain_name
  })

  lifecycle {
    create_before_destroy = true
  }
}

# =============================================================================
# DNS VALIDATION RECORDS
# =============================================================================

# Create DNS records for certificate validation
resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.c2_cert.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = var.route53_zone_id
}

# =============================================================================
# CERTIFICATE VALIDATION
# =============================================================================

resource "aws_acm_certificate_validation" "c2_cert" {
  certificate_arn         = aws_acm_certificate.c2_cert.arn
  validation_record_fqdns = [for record in aws_route53_record.cert_validation : record.fqdn]

  timeouts {
    create = "30m" # DNS propagation can take time
  }
}

