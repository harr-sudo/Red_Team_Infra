# ACM Certificate Module Variables
# =============================================================================

variable "primary_domain_name" {
  description = "Primary domain name for the certificate"
  type        = string
}

variable "c2_subdomain" {
  description = "C2 subdomain to include in certificate"
  type        = string
  default     = "api"
}

variable "www_subdomain" {
  description = "WWW subdomain to include in certificate"
  type        = string
  default     = "www"
}

variable "cdn_subdomain" {
  description = "CDN subdomain to include in certificate"
  type        = string
  default     = "cdn"
}

variable "route53_zone_id" {
  description = "Route 53 hosted zone ID for DNS validation"
  type        = string
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

