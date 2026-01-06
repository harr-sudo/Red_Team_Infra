# Red Team Infrastructure - High-Level Plan

## Overview
This project aims to create a scalable, replicable red team infrastructure on AWS that can be quickly deployed, configured, and torn down. The infrastructure will support various red team operations including command and control (C2), persistence mechanisms, data exfiltration, and operational security.

## Architecture Principles

### 1. Infrastructure as Code (IaC)
- **Primary Tool**: Terraform (recommended for multi-cloud flexibility) or AWS CloudFormation
- **Benefits**: Version control, repeatability, easy teardown, documentation as code
- **Structure**: Modular Terraform configurations for different components

### 2. Configuration Management
- **Primary Tool**: Ansible (agentless, simple, powerful)
- **Alternative**: Cloud-init scripts, AWS Systems Manager (SSM)
- **Purpose**: Automated software installation, configuration, hardening

### 3. Automation & Orchestration
- **Deployment Scripts**: Bash/Python scripts for orchestration
- **CI/CD**: GitHub Actions or GitLab CI for automated deployments
- **State Management**: Terraform state stored in S3 with DynamoDB locking

## AWS Infrastructure Components

### Core Services
1. **VPC & Networking**
   - Isolated VPC with public/private subnets
   - NAT Gateway for outbound connectivity
   - Security groups with least privilege
   - VPC Flow Logs for monitoring

2. **Compute Resources**
   - EC2 instances (various sizes based on role)
   - Auto Scaling Groups for resilience
   - Spot Instances for cost optimization (where applicable)
   - Dedicated instances for isolation (if required)

3. **Storage**
   - S3 buckets for data storage (encrypted)
   - EBS volumes for persistent storage
   - EFS for shared file systems (if needed)

4. **Identity & Access Management**
   - IAM roles with least privilege
   - Separate roles for different components
   - MFA for console access
   - Service accounts for automation

5. **Monitoring & Logging**
   - CloudWatch Logs for centralized logging
   - CloudWatch Metrics for monitoring
   - CloudTrail for API auditing
   - VPC Flow Logs for network traffic

6. **Security Services**
   - AWS WAF (if using Application Load Balancer)
   - AWS Shield (DDoS protection)
   - Secrets Manager for sensitive data
   - KMS for encryption keys

### Red Team Specific Components

1. **Command & Control (C2) Infrastructure**
   - C2 servers (Cobalt Strike, Sliver, etc.)
   - Redirectors (CloudFront, ALB, or dedicated EC2)
   - Domain fronting capabilities

2. **Operational Infrastructure**
   - Phishing infrastructure (mail servers, landing pages)
   - Data collection points
   - Exfiltration endpoints
   - Persistence mechanisms

3. **Supporting Services**
   - DNS servers (Route53)
   - Certificate management (ACM)
   - Load balancers (ALB/NLB)

## Directory Structure

```
Red_Team_Infra/
├── README.md
├── PLAN.md (this file)
├── terraform/
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── modules/
│   │   ├── vpc/
│   │   ├── ec2/
│   │   ├── security/
│   │   └── networking/
│   └── environments/
│       ├── dev/
│       ├── staging/
│       └── prod/
├── ansible/
│   ├── playbooks/
│   │   ├── base-setup.yml
│   │   ├── c2-setup.yml
│   │   ├── redirector-setup.yml
│   │   └── hardening.yml
│   ├── roles/
│   │   ├── common/
│   │   ├── c2-server/
│   │   └── redirector/
│   └── inventory/
│       ├── hosts.yml
│       └── group_vars/
├── scripts/
│   ├── deployment/
│   │   ├── deploy.sh
│   │   ├── destroy.sh
│   │   └── update.sh
│   ├── configuration/
│   │   ├── setup-c2.sh
│   │   ├── setup-redirector.sh
│   │   └── configure-ssl.sh
│   └── utilities/
│       ├── health-check.sh
│       ├── backup.sh
│       └── cleanup.sh
├── configs/
│   ├── terraform.tfvars.example
│   ├── ansible.cfg
│   └── ssh/
│       └── config.example
├── docs/
│   ├── architecture.md
│   ├── deployment-guide.md
│   └── operational-procedures.md
└── .gitignore
```

## Deployment Strategy

### Phase 1: Foundation
1. Set up AWS account structure
2. Configure IAM roles and policies
3. Create base VPC and networking
4. Set up S3 bucket for Terraform state
5. Configure CloudWatch logging

### Phase 2: Core Infrastructure
1. Deploy EC2 instances
2. Configure security groups
3. Set up load balancers (if needed)
4. Configure DNS (Route53)

### Phase 3: Application Layer
1. Install base software (Ansible)
2. Configure C2 infrastructure
3. Set up redirectors
4. Configure SSL/TLS certificates

### Phase 4: Security Hardening
1. Apply security configurations
2. Enable logging and monitoring
3. Configure backup procedures
4. Document operational procedures

## Automation Scripts

### Deployment Scripts (`scripts/deployment/`)

#### `deploy.sh`
- Main orchestration script
- Validates prerequisites (AWS CLI, Terraform, Ansible)
- Runs Terraform to create infrastructure
- Waits for instances to be ready
- Runs Ansible playbooks for configuration
- Outputs connection information

#### `destroy.sh`
- Safely tears down infrastructure
- Confirms before destruction
- Cleans up resources in correct order
- Preserves logs if needed

#### `update.sh`
- Updates existing infrastructure
- Runs Terraform plan/apply
- Updates configurations via Ansible
- Zero-downtime updates where possible

### Configuration Scripts (`scripts/configuration/`)

#### `setup-c2.sh`
- Installs and configures C2 framework
- Sets up team server
- Configures listeners
- Generates payloads

#### `setup-redirector.sh`
- Configures redirector instances
- Sets up domain fronting (if applicable)
- Configures SSL termination
- Sets up logging

#### `configure-ssl.sh`
- Requests SSL certificates via ACM
- Configures certificate deployment
- Sets up certificate rotation

### Utility Scripts (`scripts/utilities/`)

#### `health-check.sh`
- Checks infrastructure health
- Validates connectivity
- Tests services
- Reports status

#### `backup.sh`
- Backs up critical configurations
- Exports Terraform state
- Backs up Ansible inventories
- Stores backups in S3

#### `cleanup.sh`
- Removes temporary files
- Cleans up old logs
- Removes unused resources
- Maintains hygiene

## Technology Stack

### Infrastructure
- **Terraform**: Infrastructure provisioning
- **Ansible**: Configuration management
- **AWS CLI**: AWS service interaction
- **jq**: JSON processing in scripts

### Scripting Languages
- **Bash**: Primary scripting language for orchestration
- **Python**: Complex automation tasks, API interactions
- **YAML**: Configuration files (Ansible, CloudFormation)

### Tools & Frameworks
- **Git**: Version control
- **Docker** (optional): Containerization for consistent environments
- **Packer** (optional): AMI creation for custom images

## Security Considerations

1. **Secrets Management**
   - Use AWS Secrets Manager or Parameter Store
   - Never commit secrets to Git
   - Rotate credentials regularly

2. **Access Control**
   - Use IAM roles, not access keys where possible
   - Implement least privilege
   - Enable MFA for all users

3. **Network Security**
   - Private subnets for sensitive resources
   - Security groups with minimal required ports
   - Network ACLs for additional layer

4. **Logging & Monitoring**
   - Comprehensive logging of all activities
   - Alerting on suspicious activities
   - Regular log review

5. **Compliance**
   - Follow AWS Well-Architected Framework
   - Implement proper tagging for cost tracking
   - Document all changes

## Scalability Features

1. **Auto Scaling**
   - Auto Scaling Groups for dynamic scaling
   - Target tracking policies
   - Scheduled scaling for predictable workloads

2. **Multi-Region Support**
   - Terraform modules support multiple regions
   - Route53 for global load balancing
   - Cross-region replication for resilience

3. **Environment Separation**
   - Separate Terraform workspaces/environments
   - Isolated VPCs per environment
   - Environment-specific configurations

## Replication Strategy

1. **Version Control**
   - All code in Git repository
   - Tagged releases for stable versions
   - Branching strategy for development

2. **Documentation**
   - Comprehensive README files
   - Architecture diagrams
   - Runbooks for common tasks

3. **Templates**
   - Terraform modules for reusability
   - Ansible roles for common configurations
   - Example configuration files

4. **Automation**
   - One-command deployment
   - Automated testing
   - CI/CD pipelines

## Cost Optimization

1. **Resource Sizing**
   - Right-size instances based on actual needs
   - Use Spot Instances where appropriate
   - Reserved Instances for predictable workloads

2. **Lifecycle Management**
   - Auto-shutdown during non-operational hours
   - Cleanup unused resources
   - Regular cost reviews

3. **Monitoring**
   - Cost alerts via CloudWatch
   - Tagging for cost allocation
   - Regular cost optimization reviews

## Next Steps

1. **Immediate Actions**
   - [ ] Set up Git repository structure
   - [ ] Create base Terraform configuration
   - [ ] Set up AWS account and IAM structure
   - [ ] Create initial Ansible playbooks

2. **Short Term**
   - [ ] Implement VPC module
   - [ ] Create EC2 instance configurations
   - [ ] Develop deployment scripts
   - [ ] Set up CI/CD pipeline

3. **Medium Term**
   - [ ] Implement C2 infrastructure automation
   - [ ] Create monitoring and alerting
   - [ ] Develop operational runbooks
   - [ ] Implement backup and recovery

4. **Long Term**
   - [ ] Multi-region support
   - [ ] Advanced automation
   - [ ] Performance optimization
   - [ ] Advanced security features

## Notes

- All infrastructure should be ephemeral and easily recreatable
- Follow infrastructure as code best practices
- Maintain detailed documentation
- Regular security audits and updates
- Test disaster recovery procedures regularly

