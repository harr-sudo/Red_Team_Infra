# Domain Requirements and Prerequisites

This document outlines the domain requirements for the Red Team C2 infrastructure, including primary domains, backup domains, and DNS configuration.

## Overview

Domains are **essential prerequisites** for the C2 infrastructure, especially for:
- CDN/Domain fronting (traffic obfuscation)
- SSL/TLS certificates
- Professional appearance (legitimate-looking infrastructure)
- Redundancy and failover

## Domain Requirements

### 1. Primary Domain

**Purpose**: Main domain for C2 infrastructure

**Requirements**:
- Must be registered and active
- Should be a legitimate-looking domain (not obviously suspicious)
- Must support DNS management (Route53 or external DNS)
- Should have privacy protection enabled (if available)

**Recommended Characteristics**:
- Generic business-sounding name
- Common TLD (.com, .net, .org)
- Not tied to your organization (if possible)
- Easy to remember and type

**Example**: `example-business-services.com`

### 2. Backup/Fallback Domains

**Purpose**: Redundancy and operational security

**Requirements**:
- **Minimum**: 2-3 backup domains
- Should be registered from different registrars (if possible)
- Different TLDs recommended (.com, .net, .org)
- Same DNS management capabilities

**Why Multiple Domains?**:
- **Redundancy**: If one domain is flagged/blocked, switch to backup
- **Phase Rotation**: Use different domains per engagement phase
- **OpSec**: Spread infrastructure across multiple domains
- **Resilience**: Domain takedown doesn't kill entire infrastructure

**Example Backup Domains**:
- `backup-domain-1.com`
- `backup-domain-2.net`
- `backup-domain-3.org`

### 3. Subdomain Strategy

**Purpose**: Organize different infrastructure components

**Recommended Subdomains**:
- `c2.example.com` - C2 team server endpoint
- `www.example.com` - Public-facing (for domain fronting)
- `api.example.com` - API endpoint (if needed)
- `mail.example.com` - Email infrastructure (if needed)
- `cdn.example.com` - CDN endpoint

**Note**: Subdomains are managed via DNS, not separate domain purchases.

## Domain Registration Considerations

### Registrar Selection

**Recommended Registrars**:
- **Namecheap** - Good privacy protection, reasonable prices
- **Google Domains** - Simple interface, good DNS management
- **Cloudflare** - Excellent DNS, privacy-focused
- **Route53** - AWS-native, integrates well with infrastructure

**Considerations**:
- Privacy protection availability
- DNS management capabilities
- Transfer policies
- Pricing
- Support for multiple domains

### Privacy Protection

**Why Important**:
- Hide registrant information from WHOIS
- Protect operational security
- Prevent domain correlation

**Recommendation**: Enable privacy protection on all domains

### Domain Registration Best Practices

1. **Use Different Registrars**: Don't register all domains from same registrar
2. **Different Payment Methods**: Use different payment methods if possible
3. **Privacy Protection**: Enable on all domains
4. **Auto-Renewal**: Enable to prevent accidental expiration
5. **Documentation**: Keep track of all domains, registrars, and credentials

## DNS Management

### Option 1: AWS Route53 (Recommended)

**Advantages**:
- Native AWS integration
- Easy Terraform automation
- Reliable and fast
- Good for CloudFront integration

**Cost**: ~$0.50/month per hosted zone + DNS queries

**Setup**:
1. Create hosted zone in Route53
2. Update nameservers at domain registrar
3. Configure DNS records via Terraform

### Option 2: External DNS Provider

**Options**:
- Cloudflare (free tier available)
- Namecheap DNS
- Google Cloud DNS
- Other DNS providers

**Considerations**:
- May require manual DNS record management
- Less integrated with AWS services
- May need separate automation

## SSL/TLS Certificates

### AWS Certificate Manager (ACM)

**Requirements**:
- Domain must be validated
- DNS validation required
- Free certificates
- Auto-renewal

**Process**:
1. Request certificate in ACM
2. Validate via DNS (add CNAME record)
3. Certificate automatically issued
4. Use with CloudFront/ALB

### Certificate Coverage

**Recommendations**:
- Certificate for primary domain
- Wildcard certificate: `*.example.com` (covers all subdomains)
- Certificates for backup domains

## Domain Configuration Variables

### Required Variables

Add to `terraform.tfvars`:

```hcl
# Primary Domain Configuration
primary_domain_name = "example-business-services.com"
primary_domain_hosted_zone_id = ""  # Route53 hosted zone ID

# Backup Domains
backup_domains = [
  {
    domain_name = "backup-domain-1.com"
    hosted_zone_id = ""
  },
  {
    domain_name = "backup-domain-2.net"
    hosted_zone_id = ""
  }
]

# Subdomain Configuration
c2_subdomain = "c2"
www_subdomain = "www"
cdn_subdomain = "cdn"

# DNS Configuration
dns_provider = "route53"  # route53, cloudflare, external
enable_dns_validation = true
```

## Pre-Deployment Checklist

### Before Infrastructure Deployment:

- [ ] **Register Primary Domain**
  - [ ] Choose registrar
  - [ ] Enable privacy protection
  - [ ] Set up auto-renewal
  - [ ] Document credentials

- [ ] **Register Backup Domains** (2-3 minimum)
  - [ ] Different registrars (if possible)
  - [ ] Different TLDs
  - [ ] Privacy protection enabled
  - [ ] Document all domains

- [ ] **Set Up DNS Management**
  - [ ] Create Route53 hosted zones (if using Route53)
  - [ ] Update nameservers at registrar
  - [ ] Verify DNS propagation
  - [ ] Test DNS resolution

- [ ] **Plan Subdomain Strategy**
  - [ ] Decide on subdomain naming
  - [ ] Document subdomain purposes
  - [ ] Plan DNS record structure

- [ ] **Prepare for SSL/TLS**
  - [ ] Understand ACM validation process
  - [ ] Plan certificate requests
  - [ ] Prepare DNS validation records

## Domain Costs

### Registration Costs (Annual):

- **Primary Domain**: $10-15/year (.com)
- **Backup Domain 1**: $10-15/year
- **Backup Domain 2**: $10-15/year
- **Backup Domain 3**: $10-15/year (optional)

**Total Annual Cost**: ~$30-60/year for 2-3 domains

### DNS Costs (Monthly):

- **Route53 Hosted Zone**: $0.50/month per zone
- **Route53 DNS Queries**: ~$0.40 per million queries
- **Estimated Monthly**: $1-5/month (depending on traffic)

### SSL/TLS Costs:

- **ACM Certificates**: Free (included with AWS)

**Total Monthly Cost**: ~$1-5/month for DNS

## Operational Security Considerations

### Domain OpSec:

1. **Registrar Diversity**: Use different registrars for backup domains
2. **Payment Method Diversity**: Use different payment methods if possible
3. **Privacy Protection**: Always enable WHOIS privacy
4. **Domain Age**: Older domains look more legitimate
5. **Content Strategy**: Domains should have some legitimate-looking content

### Domain Rotation:

- **Phase-Based**: Use different domains per engagement phase
- **Time-Based**: Rotate domains periodically
- **Incident-Based**: Switch domains if one is flagged

### Domain Monitoring:

- Monitor domain expiration dates
- Set up renewal reminders
- Monitor DNS resolution
- Track domain reputation

## Integration with Infrastructure

### Terraform Integration:

Domains will be integrated via:
1. **Route53 Module** (to be implemented)
   - Hosted zone creation
   - DNS record management
   - Subdomain configuration

2. **ACM Module** (to be implemented)
   - Certificate requests
   - DNS validation
   - Certificate deployment

3. **CloudFront Module** (to be implemented)
   - Distribution configuration
   - Domain association
   - SSL/TLS termination

## Documentation Requirements

### Document the Following:

1. **Domain Inventory**:
   - Domain names
   - Registrars
   - Registration dates
   - Expiration dates
   - Nameservers

2. **DNS Configuration**:
   - Hosted zone IDs
   - DNS provider
   - Nameserver records
   - DNS record structure

3. **Credentials**:
   - Registrar accounts
   - DNS provider accounts
   - Access keys (if applicable)

**⚠️ Security Note**: Store credentials securely (AWS Secrets Manager, password manager), NOT in Git!

## Next Steps

1. **Immediate**: Register primary domain and 2-3 backup domains
2. **Before Deployment**: Set up Route53 hosted zones
3. **During Deployment**: Configure DNS records via Terraform
4. **Post-Deployment**: Request SSL/TLS certificates
5. **Ongoing**: Monitor domains and DNS resolution

## Summary

**Required Before Deployment**:
- ✅ Primary domain registered
- ✅ 2-3 backup domains registered
- ✅ DNS management set up (Route53 recommended)
- ✅ Privacy protection enabled
- ✅ Auto-renewal configured

**Estimated Costs**:
- Annual: $30-60 (domain registration)
- Monthly: $1-5 (DNS management)

**Time Required**:
- Domain registration: 15-30 minutes
- DNS setup: 30-60 minutes
- Total: ~1-2 hours

Domains are **critical prerequisites** and should be obtained before infrastructure deployment!

