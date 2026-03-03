# DNS Module Variables
# =============================================================================

# =============================================================================
# DOMAIN CONFIGURATION
# =============================================================================

variable "primary_domain_name" {
  description = "Primary domain name for C2 infrastructure (e.g., example.com). User must own this domain."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{0,61}[a-z0-9]?\\.[a-z]{2,}$", var.primary_domain_name))
    error_message = "Domain name must be a valid domain (e.g., example.com)"
  }
}

variable "backup_domains" {
  description = "List of backup domain names for redundancy"
  type        = list(string)
  default     = []
}

variable "c2_subdomain" {
  description = "Subdomain prefix for C2 servers (e.g., 'api' creates api.example.com)"
  type        = string
  default     = "api"
}

variable "www_subdomain" {
  description = "Subdomain prefix for web redirectors"
  type        = string
  default     = "www"
}

variable "cdn_subdomain" {
  description = "Subdomain prefix for CDN-style redirectors"
  type        = string
  default     = "cdn"
}

# =============================================================================
# HOSTED ZONE CONFIGURATION
# =============================================================================

variable "create_hosted_zone" {
  description = "Whether to create a new Route 53 hosted zone. Set to false if domain is already in Route 53."
  type        = bool
  default     = true
}

variable "dns_ttl" {
  description = "TTL for DNS records in seconds. Lower = faster failover, higher = less DNS queries"
  type        = number
  default     = 300 # 5 minutes - good balance for C2
}

# =============================================================================
# RECORD CONFIGURATION
# =============================================================================

variable "redirector_ips" {
  description = "List of redirector public IP addresses to point DNS records to"
  type        = list(string)
  default     = []
}

variable "enable_www_subdomain" {
  description = "Create www subdomain record"
  type        = bool
  default     = true
}

variable "enable_cdn_subdomain" {
  description = "Create cdn subdomain record"
  type        = bool
  default     = true
}

variable "enable_apex_record" {
  description = "Create apex/root domain record (naked domain)"
  type        = bool
  default     = true
}

variable "create_backup_domain_records" {
  description = "Create CNAME records for backup domains"
  type        = bool
  default     = true
}

variable "enable_domain_fronting" {
  description = "Whether domain fronting is enabled. When true, A records for subdomains and backup domain CNAMEs are NOT created (the domain_fronting module creates CloudFront alias records instead)."
  type        = bool
  default     = false
}

# =============================================================================
# EMAIL/REPUTATION RECORDS
# =============================================================================

variable "enable_spf_record" {
  description = "Create SPF record (helps domain look legitimate)"
  type        = bool
  default     = true
}

variable "enable_dmarc_record" {
  description = "Create DMARC record (helps domain look legitimate)"
  type        = bool
  default     = true
}

# =============================================================================
# PROJECT CONFIGURATION
# =============================================================================

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

