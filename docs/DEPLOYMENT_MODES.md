# C2 Deployment Modes

This document explains the three deployment modes available for C2 team servers.

> **Note**: For easier configuration, consider using `engagement_type` instead of manually setting `c2_deployment_mode`. See [Engagement Types Guide](./legacy/internal/ENGAGEMENT_TYPES.md) for details.

## Overview

The infrastructure supports three deployment modes to match different operational requirements:

1. **Single** - One C2 server (simple setup)
2. **Redundancy** - Multiple C2 servers (high availability)
3. **Phases** - One server per engagement phase (distributed operations)

## Deployment Modes

### 1. Single Mode

**Purpose**: Simple setup with one C2 server

**Configuration**:
```hcl
c2_deployment_mode = "single"
c2_server_count = 1  # Ignored in single mode (always 1)
```

**What Gets Deployed**:
- 1 C2 team server
- Named: `{project}-{env}-c2-team-server-1`
- Tagged: `Phase = "generic"`

**Use Cases**:
- Testing/development
- Small engagements
- Cost-sensitive deployments
- Simple proof-of-concept

**Cost**: ~$30/month (1x t3.medium)

### 2. Redundancy Mode

**Purpose**: High availability with multiple redundant C2 servers

**Configuration**:
```hcl
c2_deployment_mode = "redundancy"
c2_server_count = 2  # Or more
```

**What Gets Deployed**:
- Multiple C2 team servers (configurable count)
- Named: `{project}-{env}-c2-team-server-1`, `c2-team-server-2`, etc.
- Tagged: `Phase = "generic"`
- Distributed across availability zones

**Use Cases**:
- Production engagements
- High availability requirements
- Load distribution
- Failover scenarios

**Cost**: ~$60/month (2x t3.medium) or more

### 3. Phases Mode

**Purpose**: Distributed operations with dedicated servers per engagement phase

**Configuration**:
```hcl
c2_deployment_mode = "phases"

c2_phases = {
  staging = {
    enabled          = true
    instance_type    = "t3.medium"
    root_volume_size = 20
    user_data        = ""
    iam_instance_profile_name = ""
  }
  post-ex = {
    enabled          = true
    instance_type    = "t3.medium"
    root_volume_size = 20
    user_data        = ""
    iam_instance_profile_name = ""
  }
  long-haul = {
    enabled          = true
    instance_type    = "t3.medium"
    root_volume_size = 20
    user_data        = ""
    iam_instance_profile_name = ""
  }
}
```

**What Gets Deployed**:
- One C2 server per enabled phase
- Named: `{project}-{env}-c2-staging-server`, `c2-post-ex-server`, `c2-long-haul-server`
- Tagged: `Phase = "staging"`, `Phase = "post-ex"`, `Phase = "long-haul"`
- Each phase can have different instance types and configurations

**Phases**:
- **Staging**: Initial access phase
- **Post-Ex**: Post-exploitation phase
- **Long-Haul**: Persistence/long-term access phase

**Use Cases**:
- Distributed operations (Cobalt Strike pattern)
- Phase isolation for OpSec
- Different infrastructure per engagement phase
- Resilience (if one phase is discovered, others maintain access)

**Cost**: ~$90/month (3x t3.medium, one per phase)

## Comparison Table

| Feature | Single | Redundancy | Phases |
|---------|--------|------------|--------|
| **Servers Deployed** | 1 | 2+ (configurable) | 1 per phase (3 default) |
| **Naming** | `c2-team-server-1` | `c2-team-server-{n}` | `c2-{phase}-server` |
| **Phase Tagging** | `generic` | `generic` | `staging`, `post-ex`, `long-haul` |
| **Redundancy** | ❌ None | ✅ Yes | ✅ Per phase |
| **OpSec Isolation** | ❌ None | ⚠️ Limited | ✅ Full isolation |
| **Cost (monthly)** | ~$30 | ~$60+ | ~$90+ |
| **Use Case** | Testing/Dev | Production | Distributed Ops |

## Configuration Examples

### Example 1: Single Server
```hcl
c2_deployment_mode = "single"
c2_server_instance_type = "t3.medium"
```

### Example 2: Redundancy (3 servers)
```hcl
c2_deployment_mode = "redundancy"
c2_server_count = 3
c2_server_instance_type = "t3.medium"
```

### Example 3: Phases (Custom Configuration)
```hcl
c2_deployment_mode = "phases"

c2_phases = {
  staging = {
    enabled          = true
    instance_type    = "t3.small"   # Smaller for staging
    root_volume_size = 20
    user_data        = ""           # Staging-specific setup
  }
  post-ex = {
    enabled          = true
    instance_type    = "t3.medium"   # Standard for post-ex
    root_volume_size = 30           # Larger volume
    user_data        = ""
  }
  long-haul = {
    enabled          = true
    instance_type    = "t3.large"   # Larger for long-term
    root_volume_size = 50            # Much larger volume
    user_data        = ""            # Long-haul specific setup
  }
}
```

### Example 4: Phases (Disable One Phase)
```hcl
c2_deployment_mode = "phases"

c2_phases = {
  staging = {
    enabled = true
    # ... config
  }
  post-ex = {
    enabled = false  # Disable this phase
    # ... config (ignored when disabled)
  }
  long-haul = {
    enabled = true
    # ... config
  }
}
```

## Outputs

### Single/Redundancy Mode Outputs:
```json
{
  "c2_team_server_instance_ids": ["i-123...", "i-456..."],
  "c2_team_server_private_ips": ["10.0.10.5", "10.0.11.5"]
}
```

### Phases Mode Outputs:
```json
{
  "c2_phase_server_instance_ids": {
    "staging": "i-123...",
    "post-ex": "i-456...",
    "long-haul": "i-789..."
  },
  "c2_phase_server_private_ips": {
    "staging": "10.0.10.5",
    "post-ex": "10.0.11.5",
    "long-haul": "10.0.10.6"
  }
}
```

### Unified Output (All Modes):
```json
{
  "c2_servers": {
    "staging": {
      "instance_id": "i-123...",
      "private_ip": "10.0.10.5",
      "phase": "staging"
    },
    "post-ex": {
      "instance_id": "i-456...",
      "private_ip": "10.0.11.5",
      "phase": "post-ex"
    }
  }
}
```

## Ansible Inventory

The `ansible_inventory` output automatically adapts to the deployment mode:

**Single/Redundancy Mode**:
```yaml
c2_team_servers:
  - name: red-team-infra-dev-c2-team-server-1
    ansible_host: 10.0.10.5
    phase: generic
```

**Phases Mode**:
```yaml
c2_team_servers:
  - name: red-team-infra-dev-c2-staging-server
    ansible_host: 10.0.10.5
    phase: staging
  - name: red-team-infra-dev-c2-post-ex-server
    ansible_host: 10.0.11.5
    phase: post-ex
  - name: red-team-infra-dev-c2-long-haul-server
    ansible_host: 10.0.10.6
    phase: long-haul
```

## Switching Between Modes

### From Single to Redundancy:
1. Change `c2_deployment_mode = "redundancy"`
2. Set `c2_server_count = 2` (or more)
3. Run `terraform apply`

### From Redundancy to Phases:
1. Change `c2_deployment_mode = "phases"`
2. Configure `c2_phases` block
3. Run `terraform apply`
4. **Note**: Existing servers will be destroyed and recreated

### From Phases to Single/Redundancy:
1. Change `c2_deployment_mode = "single"` or `"redundancy"`
2. Run `terraform apply`
3. **Note**: Phase servers will be destroyed and replaced

⚠️ **Warning**: Switching modes will destroy and recreate C2 servers. Plan accordingly!

## Best Practices

### Single Mode:
- Use for development/testing only
- Not recommended for production

### Redundancy Mode:
- Use for production engagements
- Deploy at least 2 servers
- Distribute across availability zones

### Phases Mode:
- Use for distributed operations
- Match Cobalt Strike distributed operations pattern
- Configure different instance types per phase if needed
- Use phase-specific user data for different C2 configurations
- Consider assigning different domains to different phases

## Engagement Type Integration

Instead of manually configuring deployment modes, you can use `engagement_type`:

- **`engagement_type = "adhoc"`** → Auto-configures `single` mode
- **`engagement_type = "purple-team"`** → Auto-configures `redundancy` mode
- **`engagement_type = "full-red-team"`** → Auto-configures `phases` mode

See [Engagement Types Guide](./legacy/internal/ENGAGEMENT_TYPES.md) for complete details.

## Summary

- **Single**: 1 server, simple setup, low cost
- **Redundancy**: Multiple servers, high availability, medium cost
- **Phases**: 1 server per phase, distributed operations, higher cost but maximum OpSec

Choose the mode that best fits your operational requirements, or use `engagement_type` for automatic configuration!

