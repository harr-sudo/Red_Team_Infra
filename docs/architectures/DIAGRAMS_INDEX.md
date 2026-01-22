# Architecture Diagrams Quick Reference

## All Generated Diagrams

This page provides a visual index of all architecture diagrams generated for the Red Team Infrastructure project.

---

## GOAD Training Labs

### GOAD Mini - Single DC Training Lab
![GOAD Mini](../../generated-diagrams/goad-mini-architecture.png)
**Cost**: $75-100/month | **VMs**: 2 | **Domains**: 1
[📖 Full Documentation](./goad-mini.md)

---

### GOAD Light - Multi-Domain Lab
![GOAD Light](../../generated-diagrams/goad-light-architecture.png)
**Cost**: $200-250/month | **VMs**: 4 | **Domains**: 2
[📖 Full Documentation](./goad-light.md)

---

### GOAD Full - Complete AD Environment
![GOAD Full](../../generated-diagrams/goad-full-architecture.png)
**Cost**: $350-400/month | **VMs**: 6 | **Domains**: 3
[📖 Full Documentation](./goad-light.md)

---

## C2 Infrastructure

### C2 Ad-Hoc - Single Team Server
![C2 Ad-Hoc](../../generated-diagrams/c2-adhoc-architecture.png)
**Cost**: $60-105/month | **C2 Servers**: 1 | **Redirectors**: 2
[📖 Full Documentation](./c2-adhoc.md)

---

### C2 Purple Team - Redundant Servers
![C2 Purple](../../generated-diagrams/c2-purple-architecture.png)
**Cost**: $90-140/month | **C2 Servers**: 2 | **High Availability**: ✅
[📖 Full Documentation](./c2-adhoc.md)

---

### C2 Full Red Team - Phase-Based Operations
![C2 Full](../../generated-diagrams/c2-full-architecture.png)
**Cost**: $120-170/month | **C2 Servers**: 3 (Phases) | **Advanced OpSec**: ✅
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

### Windows Attack Box - Detailed Architecture
![Attack Box](../../generated-diagrams/attackbox-architecture.png)
**Features**: Windows Server 2022 + WSL2, Tools Repository, RDP Access
[📖 Full Documentation](./goad-mini.md)

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

**Last Updated**: January 2026
