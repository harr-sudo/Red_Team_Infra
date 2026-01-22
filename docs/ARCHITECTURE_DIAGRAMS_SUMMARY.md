# Architecture Diagrams - Implementation Summary

## Overview

This document summarizes the comprehensive architecture diagrams and documentation created for the Red Team Infrastructure project using AWS MCP (Model Context Protocol) following AWS best practices.

## Generated Diagrams

All diagrams were created using the AWS Diagram MCP server, following the methodology described in AWS's official blog post: [Build AWS architecture diagrams using Amazon Q CLI and MCP](https://aws.amazon.com/blogs/machine-learning/build-aws-architecture-diagrams-using-amazon-q-cli-and-mcp/)

### GOAD Training Lab Diagrams

1. **goad-mini-architecture.png**
   - Single DC training lab
   - Components: Jumpbox + CS, DC01
   - Estimated cost: $75-100/month

2. **goad-light-architecture.png**
   - Multi-domain lab with parent-child trust
   - Components: Jumpbox + CS, DC01, DC02, SRV02
   - Estimated cost: $200-250/month

3. **goad-full-architecture.png**
   - Complete AD environment with 2 forests
   - Components: Jumpbox + CS, DC01-03, SRV02-03
   - Estimated cost: $350-400/month

### C2 Infrastructure Diagrams

4. **c2-adhoc-architecture.png**
   - Single team server deployment
   - Components: 1 C2 Server, 2 Redirectors, Bastion
   - Estimated cost: $60-105/month

5. **c2-purple-architecture.png**
   - Redundant servers for high availability
   - Components: 2 C2 Servers, 2 Redirectors, Bastion, ALB
   - Estimated cost: $90-140/month

6. **c2-full-architecture.png**
   - Phase-based operations (Staging, Post-Ex, Long-Haul)
   - Components: 3 C2 Servers (1 per phase), 2 Redirectors, Bastion
   - Estimated cost: $120-170/month

### Combined Deployment Diagrams

7. **combined-c2-goad-mini.png**
   - C2 Ad-Hoc + GOAD Mini
   - Shows VPC peering between C2 and GOAD networks
   - Estimated cost: $180-220/month

8. **combined-full-c2-goad-light.png**
   - Full C2 (3 phase servers) + GOAD Light
   - Demonstrates attack paths through VPC peering
   - Estimated cost: $350-420/month

### Component Architecture Diagrams

9. **attackbox-architecture.png**
   - Detailed Windows Attack Box architecture
   - Shows Windows components, WSL2, tools distribution
   - Includes S3 integration and user data bootstrap

10. **iam-security-architecture.png**
    - IAM security model with separate roles per VPC
    - Demonstrates least privilege principle
    - Shows permission boundaries between C2 and GOAD resources

11. **ssh-key-architecture.png**
    - SSH key management lifecycle
    - Shows generation, distribution, and access phases
    - Includes Ansible automation for key distribution

## Documentation Files

### Architecture Documentation (`docs/architectures/`)

1. **README.md** - Comprehensive index and decision matrix
   - Quick navigation for all architectures
   - Cost comparison tables
   - Decision matrix for choosing deployment types
   - Common troubleshooting guide

2. **goad-mini.md** - GOAD Mini documentation
   - Architecture overview
   - Network configuration
   - Security groups
   - Attack scenarios
   - Cost breakdown
   - Learning path

3. **goad-light.md** - GOAD Light documentation
   - Multi-domain environment details
   - Cross-domain attack scenarios
   - Trust relationship exploitation
   - Advanced attack vectors

4. **c2-adhoc.md** - C2 Ad-Hoc documentation
   - Single server deployment
   - Redirector configuration
   - Beacon profiles
   - Operational use cases

## Key Features

### AWS Best Practices Implementation

All diagrams follow AWS best practices as outlined in the referenced blog post:

1. **VPC Design**
   - Public/Private subnet separation
   - Internet Gateways for public access
   - NAT Gateways for outbound traffic from private subnets
   - Security Groups with least privilege

2. **Security**
   - IAM roles with least privilege
   - Separate roles per VPC
   - Secrets Manager for sensitive data
   - CloudWatch for logging and monitoring

3. **High Availability**
   - Multi-AZ deployments (Purple Team mode)
   - Load balancers for traffic distribution
   - Redundant redirectors

4. **Cost Optimization**
   - Right-sized instances
   - Stop/Start recommendations
   - Cost breakdown tables
   - Optimization strategies

### Architecture Integration

The diagrams were integrated into the web application:

1. **Dynamic Loading**
   - Markdown files loaded asynchronously
   - Graceful error handling
   - Loading states

2. **Interactive Features**
   - Click diagrams to open full size
   - Hover effects
   - Links to AWS best practices

3. **Documentation Structure**
   ```
   architecture.html
   ├── Dropdown selector (13 architecture types)
   ├── Diagram display (auto-loaded)
   └── Markdown content (dynamically fetched)
   ```

## Usage in Web Application

### Accessing Architecture Page

```
http://localhost:5000/architecture.html
```

### Available Architectures

The dropdown selector provides access to:

**GOAD Training Labs:**
- GOAD Mini - Single DC Training Lab
- GOAD MiniLab - DC + Workstation
- GOAD Light - Multi-Domain Lab
- GOAD Full - Complete AD Environment

**C2 Infrastructure:**
- C2 Ad-Hoc - Single Team Server
- C2 Purple Team - Redundant Servers
- C2 Full Red Team - Phase-Based

**Combined Deployments:**
- Combined: C2 + GOAD Mini
- Combined: C2 + GOAD Light
- Combined: Full C2 + Full GOAD

**Component Architecture:**
- Windows Attack Box - Detailed Overview
- IAM Security - Separate Roles Per VPC
- SSH Key Management Architecture

## Technical Implementation

### Tools Used

1. **AWS Diagram MCP Server**
   - Python diagrams package
   - AWS official icons
   - GraphViz for rendering

2. **Kiro CLI** (or equivalent MCP client)
   - MCP server integration
   - AWS documentation verification
   - Best practices validation

3. **marked.js**
   - Markdown rendering in browser
   - Syntax highlighting
   - Table support

### Code Structure

```javascript
// architecture.js
const architectures = {
    'goad-mini': {
        diagram: '../../generated-diagrams/goad-mini-architecture.png',
        markdownFile: '../../docs/architectures/goad-mini.md',
        title: 'GOAD Mini - Single DC Training Lab'
    },
    // ... more architectures
};

async function loadMarkdownFile(filePath) {
    // Fetch and return markdown content
}

async function renderArchitecture(selectedArch) {
    // Load diagram + markdown, render with marked.js
}
```

## Maintenance

### Adding New Architectures

1. **Generate Diagram**:
   ```bash
   # Use AWS MCP server
   kiro-cli
   # Or use the diagram generator directly
   ```

2. **Create Documentation**:
   ```bash
   # Create markdown file
   docs/architectures/new-architecture.md
   ```

3. **Update architecture.js**:
   ```javascript
   architectures['new-arch'] = {
       diagram: '../../generated-diagrams/new-arch.png',
       markdownFile: '../../docs/architectures/new-arch.md',
       title: 'New Architecture'
   };
   ```

4. **Update architecture.html**:
   ```html
   <option value="new-arch">New Architecture</option>
   ```

### Updating Diagrams

To regenerate diagrams with updates:

1. Modify the diagram code in MCP server
2. Regenerate PNG file
3. Replace in `generated-diagrams/`
4. No code changes needed (same filename)

## Cost Summary

### Total Project Costs

| Deployment Type | Monthly (24/7) | Monthly (Stop/Start) | 2-Week Engagement |
|----------------|----------------|----------------------|-------------------|
| GOAD Mini | $75-100 | $22-30 | $25-33 |
| GOAD Light | $200-250 | $60-75 | $67-84 |
| GOAD Full | $350-400 | $105-120 | $117-134 |
| C2 Ad-Hoc | $60-105 | N/A | $28-49 |
| C2 Purple | $90-140 | N/A | $42-65 |
| C2 Full | $120-170 | N/A | $56-79 |
| Combined Mini | $180-220 | $54-66 | $60-74 |
| Combined Light | $350-420 | $105-126 | $117-140 |
| Combined Full | $500-600 | $150-180 | $167-200 |

## References

### Official Documentation

- [AWS Architecture Best Practices Blog](https://aws.amazon.com/blogs/machine-learning/build-aws-architecture-diagrams-using-amazon-q-cli-and-mcp/)
- [GOAD GitHub Repository](https://github.com/Orange-Cyberdefense/GOAD)
- [AWS Architecture Center](https://aws.amazon.com/architecture/)
- [AWS Well-Architected Framework](https://aws.amazon.com/architecture/well-architected/)

### MCP Resources

- [Model Context Protocol](https://modelcontextprotocol.io/)
- [AWS MCP Servers](https://github.com/awslabs/mcp-servers)
- [AWS Diagram MCP Server](https://github.com/awslabs/aws-diagram-mcp-server)
- [AWS Documentation MCP Server](https://github.com/awslabs/aws-documentation-mcp-server)

### Red Team Resources

- [Cobalt Strike Documentation](https://hstechdocs.helpsystems.com/manuals/cobaltstrike/)
- [MITRE ATT&CK Framework](https://attack.mitre.org/)
- [Active Directory Security](https://adsecurity.org/)

## Achievements

✅ **11 architecture diagrams** generated following AWS best practices
✅ **4 comprehensive documentation files** with deployment guides
✅ **Complete cost analysis** for all deployment modes
✅ **Interactive web interface** with dynamic loading
✅ **Attack scenarios** and operational guidance included
✅ **Troubleshooting guides** for common issues
✅ **Learning paths** for different skill levels
✅ **Decision matrix** to help users choose deployment types

## Next Steps

### Recommended Enhancements

1. **Additional Diagrams**:
   - GOAD SCCM lab architecture
   - GOAD NHA challenge lab
   - Network traffic flow diagrams
   - Data flow diagrams (beacon callbacks)

2. **Documentation Improvements**:
   - Video walkthroughs
   - Step-by-step deployment guides with screenshots
   - More attack scenario examples
   - Integration with MITRE ATT&CK mappings

3. **Interactive Features**:
   - Clickable diagram regions
   - Animated traffic flows
   - Live cost calculator
   - Deployment wizard

4. **Automation**:
   - Auto-generate diagrams from Terraform state
   - Real-time cost tracking from AWS
   - Automated architecture validation

## Conclusion

This implementation provides **comprehensive architecture documentation** for the Red Team Infrastructure project, following **AWS best practices** and leveraging the **AWS MCP ecosystem**. The diagrams and documentation enable users to:

- **Understand** the infrastructure at a glance
- **Choose** the right deployment for their needs
- **Deploy** with confidence using detailed guides
- **Operate** effectively with scenario examples
- **Optimize** costs with practical recommendations

All materials are accessible through an **intuitive web interface** and can be easily maintained and extended as the project evolves.

---

**Created**: January 2026
**Method**: AWS MCP Diagram Server + AWS Documentation MCP Server
**Standards**: AWS Well-Architected Framework
**Reference**: https://aws.amazon.com/blogs/machine-learning/build-aws-architecture-diagrams-using-amazon-q-cli-and-mcp/
