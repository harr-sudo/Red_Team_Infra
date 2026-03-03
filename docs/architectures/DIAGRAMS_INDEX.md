# Architecture Diagrams Quick Reference

## All Generated Diagrams

This page provides a visual index of all architecture diagrams generated for the Red Team Infrastructure project.

---

## GOAD Training Labs

### GOAD Mini - Single DC Training Lab (1 DC)
![GOAD Mini](../../generated-diagrams/goad-mini-architecture.png)
**Cost**: $75-100/month | **VMs**: 1 DC | **Domain**: sevenkingdoms.local | **IPs**: .10 (DC), .40 (TS), .50 (AB), .100 (JB)
[📖 Full Documentation](./goad-mini.md)

---

### GOAD Light - Multi-Domain Lab (2 DCs + 1 Server)
![GOAD Light](../../generated-diagrams/goad-light-architecture.png)
**Cost**: $150-200/month | **VMs**: 3 (2 DC + 1 SRV) | **Domains**: sevenkingdoms.local + north.sevenkingdoms.local | **Parent-Child Trust**
[📖 Full Documentation](./goad-light.md)

---

### GOAD SCCM - Configuration Manager Lab (DC + srv01 + srv02 + ws01)
![GOAD SCCM](../../generated-diagrams/goad-sccm-architecture.png)
**Cost**: $180-230/month | **VMs**: 4 (dc01 + srv01/SCCM + srv02/SQL + ws01/Client) | **Domain**: sccm.lab | **IPs**: .10, .11, .12, .13

---

### GOAD Full - Complete AD Environment (3 DCs + 2 Servers)
![GOAD Full](../../generated-diagrams/goad-full-architecture.png)
**Cost**: $200-250/month | **VMs**: 5 (3 DC + 2 SRV) | **Forests**: sevenkingdoms.local + essos.local | **Forest + Parent-Child Trusts**
[📖 Full Documentation](./goad-full.md)

---

### GOAD NHA - Network Hacking Academy (dc01 + dc02 + srv01-srv03)
![GOAD NHA](../../generated-diagrams/goad-nha-architecture.png)
**Cost**: $200-250/month | **VMs**: 5 (dc01 + dc02 + srv01 + srv02 + srv03) | **Domains**: ninja.hack + academy.ninja.lan | **IPs**: .10, .20-.23

---

## C2 Infrastructure

### C2 Ad-Hoc - Single Team Server (Standard)
![C2 Ad-Hoc](../../generated-diagrams/c2-adhoc-architecture.png)
**Cost**: $160-192/month | **C2 Servers**: 1 | **Redirectors**: 2 | **Attack Box**: 1 | **SSL**: Let's Encrypt or Self-Signed
[📖 Full Documentation](./c2-adhoc.md)

---

### C2 Ad-Hoc - Domain Fronting Mode (Optional)
![C2 Ad-Hoc Domain Fronting](../../generated-diagrams/c2-adhoc-domain-fronting.png)
**Cost**: +$10-50/month | **CloudFront**: Hides redirector IPs | **SSL**: ACM (auto, free)
[📖 Full Documentation](./c2-adhoc.md#ssltls-options)

---

### C2 Purple Team - Redundant Servers
![C2 Purple](../../generated-diagrams/c2-purple-architecture.png)
**Cost**: $190-230/month | **C2 Servers**: 2 | **Attack Box**: 1 | **High Availability**: ✅
[📖 Full Documentation](./c2-adhoc.md)

---

### C2 Full Red Team - Phase-Based Operations
![C2 Full](../../generated-diagrams/c2-full-architecture.png)
**Cost**: $220-260/month | **C2 Servers**: 3 (Phases) | **Attack Box**: 1 | **Advanced OpSec**: ✅
[📖 Full Documentation](./c2-adhoc.md)

---

## Combined Deployments

### Combined: C2 + GOAD Mini
![Combined Mini](../../generated-diagrams/combined-c2-goad-mini.png)
**Cost**: $180-220/month | **VPC Peering**: ✅
[📖 Full Documentation](./goad-mini.md)

---

### Combined: Full C2 + GOAD Light
![Combined Full](../../generated-diagrams/combined-full-c2-goad-light.png)
**Cost**: $350-420/month | **Complete Training Environment**: ✅
[📖 Full Documentation](./goad-light.md)

---

## Component Architectures

### Windows Attack Box - Standalone Module Architecture
![Attack Box](../../generated-diagrams/attackbox-architecture.png)
**Features**: Windows Server 2022 + WSL2, CS Client, Tools Repository, RDP Access | **All 12 Deployment Types**
[📖 Full Documentation](./attackbox.md)

---

### IAM Security - Separate Roles Per VPC
![IAM Security](../../generated-diagrams/iam-security-architecture.png)
**Security**: Least Privilege, Separate Roles, Permission Boundaries
[📖 Full Documentation](./README.md)

---

### SSH Key Management Architecture
![SSH Keys](../../generated-diagrams/ssh-key-architecture.png)
**Automation**: Ansible Distribution, Secure Storage, Access Control
[📖 Full Documentation](../SSH_KEY_MANAGEMENT.md)

---

### SSL/TLS Options Comparison
![SSL Options](../../generated-diagrams/ssl-options-comparison.png)
**Options**: Let's Encrypt (standard), Domain Fronting + ACM (advanced), Self-Signed (testing only)
[📖 Full Documentation](./c2-adhoc.md#ssltls-options)

---

## Diagram Generation

All diagrams were generated using:
- **AWS Diagram MCP Server** - Official AWS tool
- **AWS Best Practices** - Following [this guide](https://aws.amazon.com/blogs/machine-learning/build-aws-architecture-diagrams-using-amazon-q-cli-and-mcp/)
- **GraphViz** - Professional diagram rendering
- **AWS Official Icons** - Latest icon set

---

## Quick Navigation

- [📚 Documentation Index](./README.md)
- [💰 Cost Comparison](./README.md#cost-comparison-matrix)
- [🎯 Decision Matrix](./README.md#decision-matrix)
- [🔧 Troubleshooting](./README.md#support--troubleshooting)

---

**Last Updated**: February 2026
