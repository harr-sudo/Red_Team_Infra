# C2 Infrastructure Architecture Review

This document reviews the proposed C2 Infrastructure Architecture diagram and compares it to the current project state.

## Architecture Overview

The diagram outlines a three-tier C2 infrastructure with the following flow:

```
C2 Team Servers → Firewall → Proxy → CDN/Domain Fronting → Internet → Target/Compromised Host
```

## Component Analysis

### 1. C2 Infrastructure Layer

#### **C2 Team Servers**
**Diagram Shows:**
- **C2 Team Server 1**: Primary server
- **C2 Team Server 2**: Redundancy/backup
- **C2 Team Server N Per Phase**: Phase-specific servers for operational security

**Current Project State:**
- ✅ **Planned** in PLAN.md (C2 servers mentioned)
- ✅ **Directory structure** exists (`ansible/roles/c2-server/`)
- ✅ **Ansible playbook** planned (`ansible/playbooks/c2-setup.yml`)
- ✅ **Script** planned (`scripts/configuration/setup-c2.sh`)
- ❌ **Not implemented** in Terraform yet
- ❌ **No redundancy strategy** defined in current config

**Gap Analysis:**
- Need to support multiple C2 servers (primary + redundancy)
- Need phase-based server rotation capability
- Current config only defines 2 generic EC2 instances
- No differentiation between C2 servers and other infrastructure

**Recommendations:**
- Add `c2_server_count` variable (default: 2, configurable)
- Add `c2_server_instance_type` (may need more resources than t3.medium)
- Implement C2 server module separate from generic EC2
- Support per-phase server deployment

#### **Firewall**
**Diagram Shows:**
- Firewall between C2 servers and proxy
- Acts as security boundary

**Current Project State:**
- ✅ **Security Groups** planned (basic firewall rules)
- ✅ **Security module** directory exists (`terraform/modules/security/`)
- ❌ **No dedicated firewall** component
- ❌ **No explicit firewall rules** for C2 traffic

**Gap Analysis:**
- AWS Security Groups provide firewall functionality
- Need explicit security group rules for C2 traffic
- May need Network ACLs for additional layer
- Should implement allow/deny lists

**Recommendations:**
- Implement security groups with explicit C2 rules
- Consider AWS Network Firewall for advanced filtering
- Implement allow-listing on security groups
- Document firewall rules clearly

#### **Proxy (Pass-Through Only)**
**Diagram Shows:**
- **Critical Feature**: "No Data Storage" / "Pass-through Only"
- Positioned between Firewall and CDN
- Acts as traffic relay without logging/storage

**Current Project State:**
- ✅ **Redirector** mentioned in PLAN.md
- ✅ **Directory structure** exists (`ansible/roles/redirector/`)
- ✅ **Ansible playbook** planned (`ansible/playbooks/redirector-setup.yml`)
- ✅ **Script** planned (`scripts/configuration/setup-redirector.sh`)
- ❌ **Not implemented** in Terraform
- ❌ **No proxy-specific configuration** defined

**Gap Analysis:**
- Proxy is a critical OpSec component
- Need to ensure no data persistence
- Should be separate from C2 servers
- Need to configure for pass-through only

**Recommendations:**
- Create dedicated proxy/redirector module
- Use ephemeral storage (no EBS persistence)
- Configure proxy software (e.g., Apache mod_rewrite, Nginx) for pass-through
- Implement logging disablement
- Use separate security group for proxy

### 2. Internet / CDN Layer

#### **CDN / Domain Fronting**
**Diagram Shows:**
- CDN for traffic obfuscation
- Domain fronting capabilities
- Critical for OpSec

**Current Project State:**
- ✅ **Mentioned** in PLAN.md ("Domain fronting capabilities")
- ✅ **CloudFront** mentioned in networking module plans
- ❌ **Not implemented** in Terraform
- ❌ **No domain fronting configuration**

**Gap Analysis:**
- CloudFront is AWS's CDN service
- Domain fronting requires specific configuration
- Need Route53 for DNS
- Need SSL/TLS certificates (ACM)

**Recommendations:**
- Implement CloudFront distribution module
- Configure for domain fronting (if still viable)
- Set up Route53 hosted zones
- Request ACM certificates
- Document domain fronting setup (legal/technical considerations)

#### **Internet / External**
**Diagram Shows:**
- Public internet connection
- Final hop before target

**Current Project State:**
- ✅ **Internet Gateway** planned in VPC module
- ✅ **Public subnets** configured
- ✅ **Basic networking** structure exists

**Gap Analysis:**
- Internet Gateway is standard VPC component
- Already accounted for in current design

**Recommendations:**
- Ensure Internet Gateway is implemented in VPC module
- Document public IP allocation strategy

### 3. Target Environment

#### **Compromised Host**
**Diagram Shows:**
- Target/victim compromised host
- Endpoint of C2 communication

**Current Project State:**
- ❌ **Not part of infrastructure** (external to AWS)
- ✅ **Documented** as operational target

**Gap Analysis:**
- This is the target, not part of infrastructure
- No changes needed

## Security Guardrails (From Diagram)

### 1. **Allow Listing on Proxy**
**Diagram Requirement:**
- Implement allow list on proxy
- Example: Only allow target email addresses for phishing

**Current Project State:**
- ❌ **Not implemented**
- ❌ **No allow-list configuration**

**Recommendations:**
- Implement proxy allow-list configuration
- Use Ansible for proxy rule management
- Store allow-lists in configuration files (not in Git)
- Document allow-list management procedures

### 2. **Domain Limitation**
**Diagram Requirement:**
- Guardrails to limit operations to specific authorized domains

**Current Project State:**
- ❌ **Not implemented**
- ❌ **No domain validation**

**Recommendations:**
- Implement domain validation in proxy configuration
- Use security groups to restrict outbound connections
- Document authorized domains in configuration
- Add validation scripts

## Traffic Flow Analysis

### **Proposed Flow:**
```
C2 Team Servers → Firewall → Proxy → CDN/Domain Fronting → Internet → Target
```

### **AWS Implementation Mapping:**

1. **C2 Team Servers**: EC2 instances in private subnets (recommended)
2. **Firewall**: Security Groups + Network ACLs
3. **Proxy**: EC2 instances in public subnets (or separate VPC)
4. **CDN/Domain Fronting**: CloudFront distribution
5. **Internet**: Internet Gateway (already planned)
6. **Target**: External (not in AWS)

### **Network Architecture Recommendations:**

```
┌─────────────────────────────────────────────────┐
│ Private Subnets (10.0.10.0/24, 10.0.11.0/24)   │
│  - C2 Team Server 1                              │
│  - C2 Team Server 2                              │
│  - C2 Team Server N (per phase)                 │
│  - Security Groups (Firewall rules)              │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ Public Subnets (10.0.1.0/24, 10.0.2.0/24)      │
│  - Proxy/Redirector Instances                    │
│  - No persistent storage                          │
│  - Pass-through only                             │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ AWS Services                                     │
│  - CloudFront Distribution                       │
│  - Route53 DNS                                   │
│  - ACM Certificates                              │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ Internet → Target Environment                   │
└─────────────────────────────────────────────────┘
```

## Implementation Gaps Summary

### **Critical Missing Components:**

1. ❌ **C2 Server Module** - Not implemented
   - Need dedicated module for C2 servers
   - Support for multiple servers
   - Phase-based deployment

2. ❌ **Proxy/Redirector Module** - Not implemented
   - Dedicated proxy instances
   - Pass-through configuration
   - No data storage enforcement

3. ❌ **CloudFront/CDN Module** - Not implemented
   - CloudFront distribution
   - Domain fronting configuration
   - SSL/TLS termination

4. ❌ **Security Guardrails** - Not implemented
   - Allow-listing on proxy
   - Domain validation
   - Traffic filtering rules

5. ❌ **Redundancy Strategy** - Not defined
   - Multiple C2 servers
   - Phase-based rotation
   - Failover mechanisms

### **Partially Implemented:**

1. ⚠️ **Firewall** - Security groups planned but not implemented
2. ⚠️ **Networking** - Basic structure exists, needs CDN integration
3. ⚠️ **DNS** - Route53 mentioned but not implemented

### **Well Planned:**

1. ✅ **VPC Structure** - Public/private subnets defined
2. ✅ **Basic EC2** - Instance configuration exists
3. ✅ **Automation** - Terraform + Ansible approach aligns
4. ✅ **Documentation** - Good foundation for expansion

## Cost Implications

### **Additional Resources Needed:**

1. **C2 Servers** (2-3 instances):
   - t3.medium or larger: ~$30-60/month each
   - Total: ~$90-180/month

2. **Proxy/Redirector Instances** (2 instances):
   - t3.small or t3.medium: ~$15-30/month each
   - Total: ~$30-60/month

3. **CloudFront Distribution**:
   - Data transfer: ~$0.085/GB (first 10TB)
   - Requests: ~$0.0075/10,000 requests
   - Estimated: ~$10-50/month (depending on traffic)

4. **Route53 Hosted Zone**:
   - $0.50/month per hosted zone
   - DNS queries: ~$0.40 per million queries
   - Estimated: ~$1-5/month

5. **ACM Certificates**:
   - Free (included with CloudFront)

**Total Additional Cost**: ~$131-295/month on top of base infrastructure

**Total Infrastructure Cost**: ~$193-357/month (base + C2 infrastructure)

## Security Considerations

### **OpSec Requirements from Diagram:**

1. ✅ **No Data Storage on Proxy** - Must enforce
2. ✅ **Traffic Obfuscation** - CDN/Domain fronting
3. ✅ **Redundancy** - Multiple servers, phase rotation
4. ✅ **Guardrails** - Allow-listing, domain validation

### **AWS Security Best Practices:**

1. **Network Isolation**:
   - C2 servers in private subnets
   - Proxy in public subnets
   - Security groups with least privilege

2. **Encryption**:
   - TLS/SSL for all communications
   - EBS encryption for C2 servers
   - S3 encryption for any storage

3. **Monitoring**:
   - CloudWatch for instance monitoring
   - VPC Flow Logs (with caution - OpSec consideration)
   - CloudTrail for API auditing

4. **Access Control**:
   - IAM roles with least privilege
   - MFA for console access
   - SSH key management

## Recommendations for Implementation

### **Phase 1: Foundation** (Current State)
- ✅ VPC and basic networking
- ✅ Security groups structure
- ✅ Basic EC2 instances

### **Phase 2: C2 Infrastructure** (Next Priority)
1. Implement C2 server module
   - Support multiple servers
   - Private subnet placement
   - Appropriate instance sizing

2. Implement proxy/redirector module
   - Public subnet placement
   - Ephemeral storage only
   - Pass-through configuration

3. Configure security groups
   - C2 server rules
   - Proxy rules
   - Allow-list enforcement

### **Phase 3: CDN and Obfuscation**
1. Implement CloudFront module
   - Distribution configuration
   - Origin setup (proxy)
   - SSL/TLS configuration

2. Implement Route53 module
   - Hosted zone
   - DNS records
   - Domain validation

3. Configure domain fronting (if applicable)

### **Phase 4: Guardrails and Automation**
1. Implement allow-list management
2. Domain validation
3. Automated deployment scripts
4. Phase-based server rotation

### **Phase 5: Monitoring and Maintenance**
1. CloudWatch integration
2. Health checks
3. Automated backups (C2 configs only)
4. Logging strategy (OpSec-aware)

## Alignment with Current Project

### **What Aligns Well:**
- ✅ Terraform for IaC
- ✅ Ansible for configuration
- ✅ Modular structure
- ✅ Automation scripts
- ✅ Documentation approach

### **What Needs Addition:**
- ❌ C2-specific modules
- ❌ Proxy/redirector infrastructure
- ❌ CloudFront integration
- ❌ Security guardrails
- ❌ Redundancy mechanisms

### **What Needs Modification:**
- ⚠️ Current EC2 module too generic
- ⚠️ Need role-specific instances (C2 vs Proxy)
- ⚠️ Security groups need C2-specific rules
- ⚠️ Network architecture needs refinement

## Conclusion

The diagram presents a **well-architected C2 infrastructure** with strong OpSec considerations. The current project has a **solid foundation** but needs significant expansion to match the diagram's requirements.

**Key Takeaways:**
1. The architecture is feasible with AWS services
2. Current project structure supports this architecture
3. Need to implement C2-specific modules
4. Proxy pass-through requirement is critical
5. Security guardrails are essential
6. Cost will increase significantly with full implementation

**Next Steps:**
1. Review and approve architecture
2. Prioritize implementation phases
3. Begin with C2 server and proxy modules
4. Implement security guardrails early
5. Test in isolated environment first

