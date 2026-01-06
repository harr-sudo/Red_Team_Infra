# Naming Conventions

This document outlines the naming conventions used throughout the Terraform infrastructure code.

## Resource Naming Pattern

All resources follow a consistent naming pattern:

```
{project_name}-{environment}-{resource_type}-{identifier}
```

### Examples:
- `red-team-infra-dev-vpc`
- `red-team-infra-dev-c2-team-server-1`
- `red-team-infra-dev-proxy-redirector-2`
- `red-team-infra-dev-public-subnet-1`

## Module Naming

### Module Directory Names:
- `vpc` - VPC and networking components
- `security` - Security groups
- `c2_team_server` - C2 team server instances
- `proxy_redirector` - Proxy/redirector instances

### Module Resource Names:
- Use descriptive, component-specific names
- Include resource type in the name
- Use underscores for module-internal resources

## Variable Naming

### Pattern:
- Use `snake_case` for all variables
- Prefix with component name when component-specific
- Use descriptive names that indicate purpose

### Examples:
- `c2_server_count` - Number of C2 servers
- `proxy_redirector_instance_type` - Instance type for proxies
- `management_cidr_blocks` - CIDR blocks for management access
- `enable_nat_gateway` - Boolean flag for NAT Gateway

## Output Naming

### Pattern:
- Use `snake_case`
- Include component name
- Be descriptive of what is returned

### Examples:
- `c2_team_server_instance_ids` - List of C2 server instance IDs
- `proxy_redirector_public_ips` - List of proxy public IPs
- `vpc_cidr_block` - VPC CIDR block

## Tag Naming

### Standard Tags:
- `Name` - Full resource name (matches resource name)
- `Type` - Resource type (e.g., "VPC", "C2TeamServer", "ProxyRedirector")
- `Component` - Component category (e.g., "C2Infrastructure", "ProxyInfrastructure")
- `Project` - Project name
- `Environment` - Environment (dev, staging, prod)
- `ManagedBy` - Management tool (Terraform)
- `Owner` - Owner/team name

### Component-Specific Tags:
- `Tier` - Network tier (Public, Private)
- `ServerNumber` - Server number for instances
- `DataStorage` - Data storage policy (e.g., "None" for proxies)
- `PassThrough` - Pass-through indicator (e.g., "True" for proxies)

## Security Group Naming

### Pattern:
```
{project_name}-{environment}-{component}-sg
```

### Examples:
- `red-team-infra-dev-c2-team-server-sg`
- `red-team-infra-dev-proxy-redirector-sg`

## Subnet Naming

### Pattern:
```
{project_name}-{environment}-{tier}-subnet-{number}
```

### Examples:
- `red-team-infra-dev-public-subnet-1`
- `red-team-infra-dev-private-subnet-2`

## Instance Naming

### Pattern:
```
{project_name}-{environment}-{component}-{number}
```

### Examples:
- `red-team-infra-dev-c2-team-server-1`
- `red-team-infra-dev-proxy-redirector-2`

## Route Table Naming

### Pattern:
```
{project_name}-{environment}-{tier}-rt
```

### Examples:
- `red-team-infra-dev-public-rt`
- `red-team-infra-dev-private-rt`

## Internet Gateway Naming

### Pattern:
```
{project_name}-{environment}-igw
```

### Example:
- `red-team-infra-dev-igw`

## Elastic IP Naming

### Pattern:
```
{project_name}-{environment}-{component}-{number}-eip
```

### Examples:
- `red-team-infra-dev-proxy-redirector-1-eip`
- `red-team-infra-dev-c2-team-server-1-eip` (if enabled)

## File Naming

### Terraform Files:
- `main.tf` - Main configuration
- `variables.tf` - Variable definitions
- `outputs.tf` - Output definitions
- `versions.tf` - Provider versions (if separate)

### Module Files:
- Each module has: `main.tf`, `variables.tf`, `outputs.tf`

## Best Practices

1. **Consistency**: Always use the same pattern across all resources
2. **Descriptiveness**: Names should clearly indicate what the resource is
3. **Environment Separation**: Always include environment in names
4. **Component Identification**: Include component type in names
5. **Numbering**: Use sequential numbers (1, 2, 3...) for multiple instances
6. **No Abbreviations**: Use full words (e.g., "redirector" not "rdr")
7. **Lowercase**: Use lowercase for all resource names (AWS requirement)
8. **Hyphens**: Use hyphens in resource names (AWS-friendly)
9. **Underscores**: Use underscores in variable/output names (Terraform convention)

## Naming Examples by Component

### VPC Resources:
```
red-team-infra-dev-vpc
red-team-infra-dev-igw
red-team-infra-dev-public-subnet-1
red-team-infra-dev-private-subnet-1
red-team-infra-dev-public-rt
```

### C2 Team Servers:
```
red-team-infra-dev-c2-team-server-1
red-team-infra-dev-c2-team-server-2
red-team-infra-dev-c2-team-server-sg
```

### Proxy/Redirectors:
```
red-team-infra-dev-proxy-redirector-1
red-team-infra-dev-proxy-redirector-2
red-team-infra-dev-proxy-redirector-sg
red-team-infra-dev-proxy-redirector-1-eip
```

## Variable Naming Examples

### Count Variables:
- `c2_server_count`
- `proxy_redirector_count`

### Instance Type Variables:
- `c2_server_instance_type`
- `proxy_redirector_instance_type`

### AMI Variables:
- `c2_server_ami_id`
- `proxy_redirector_ami_id`

### Volume Size Variables:
- `c2_server_root_volume_size`
- `proxy_redirector_root_volume_size`

## Output Naming Examples

### Instance Outputs:
- `c2_team_server_instance_ids`
- `proxy_redirector_instance_ids`

### IP Address Outputs:
- `c2_team_server_private_ips`
- `proxy_redirector_public_ips`
- `proxy_redirector_private_ips`

### Network Outputs:
- `vpc_id`
- `public_subnet_ids`
- `private_subnet_ids`

### Security Group Outputs:
- `c2_team_server_security_group_id`
- `proxy_redirector_security_group_id`

## Summary

All naming follows these principles:
1. **Clear and Descriptive**: Names clearly indicate purpose
2. **Consistent Pattern**: Same pattern used throughout
3. **Environment Aware**: Environment included in all names
4. **Component Specific**: Component type included in names
5. **AWS Compatible**: Follows AWS naming requirements
6. **Terraform Compatible**: Follows Terraform conventions

This ensures:
- Easy identification of resources in AWS Console
- Clear understanding of resource purpose
- Simple filtering and searching
- Consistent tagging and organization
- Easy troubleshooting and maintenance

