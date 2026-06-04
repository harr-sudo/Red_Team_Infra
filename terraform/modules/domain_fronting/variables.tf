# Domain Fronting Module Variables
# =============================================================================
# CloudFront CDN proxy for C2 traffic - hides redirector IPs behind CloudFront
# =============================================================================

variable "primary_domain_name" {
  description = "Primary domain name (e.g., example.com)"
  type        = string
}

variable "c2_subdomain" {
  description = "C2 subdomain prefix (e.g., 'api' creates api.example.com)"
  type        = string
  default     = "api"
}

variable "www_subdomain" {
  description = "WWW subdomain prefix"
  type        = string
  default     = "www"
}

variable "cdn_subdomain" {
  description = "CDN subdomain prefix"
  type        = string
  default     = "cdn"
}

variable "backup_domains" {
  description = "Backup domains for rotation. Added as CloudFront aliases with valid SSL. If primary is burned, switch CS profile to a backup domain instantly."
  type        = list(string)
  default     = []
}

variable "origin_ips" {
  description = "Public IP addresses of the redirector servers (CloudFront origins)"
  type        = list(string)
}

variable "acm_certificate_arn" {
  description = "ARN of the ACM certificate in us-east-1 for CloudFront"
  type        = string
}

variable "route53_zone_id" {
  description = "Route 53 hosted zone ID for creating alias records"
  type        = string
}

variable "enable_www_subdomain" {
  description = "Include www subdomain as a CloudFront alias"
  type        = bool
  default     = true
}

variable "enable_cdn_subdomain" {
  description = "Include cdn subdomain as a CloudFront alias"
  type        = bool
  default     = true
}

variable "enable_apex_record" {
  description = "Include apex domain as a CloudFront alias"
  type        = bool
  default     = true
}

variable "project_name" {
  description = "Name of the project"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
