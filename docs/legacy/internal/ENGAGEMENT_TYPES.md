# Engagement Types

This document explains the different engagement types and how they automatically configure the infrastructure deployment.

## Overview

The infrastructure supports three engagement types that automatically configure the appropriate deployment mode:

1. **Adhoc** - One-off tests throughout the year
2. **Purple Team** - Purple team exercises
3. **Full Red Team** - Full red team engagement

## Engagement Types

### 1. Adhoc (`engagement_type = "adhoc"`)

**Purpose**: One-off tests and quick assessments throughout the year

**Auto-Configuration**:
- **Deployment Mode**: `single`
- **C2 Servers**: 1 server
- **Use Case**: Quick tests, proof-of-concepts, simple assessments

**Configuration Example**:
```hcl
engagement_type = "adhoc"
# Automatically sets: c2_deployment_mode = "single"
```

**What Gets Deployed**:
- 1 C2 team server
- 2 Proxy/redirector servers (standard)
- Minimal infrastructure

**Cost**: ~$60/month (1 C2 server + proxies)

**Best For**:
- Quick security tests
- Proof-of-concept deployments
- Training exercises
- Cost-sensitive engagements

### 2. Purple Team (`engagement_type = "purple-team"`)

**Purpose**: Purple team exercises with collaboration between red and blue teams

**Auto-Configuration**:
- **Deployment Mode**: `redundancy`
- **C2 Servers**: 2+ servers (configurable via `c2_server_count`)
- **Use Case**: Collaborative exercises, controlled testing

**Configuration Example**:
```hcl
engagement_type = "purple-team"
c2_server_count = 2  # Can be increased for more redundancy
# Automatically sets: c2_deployment_mode = "redundancy"
```

**What Gets Deployed**:
- 2+ C2 team servers (redundant)
- 2 Proxy/redirector servers
- High availability setup

**Cost**: ~$90/month (2 C2 servers + proxies)

**Best For**:
- Purple team exercises
- Collaborative security testing
- Controlled red team scenarios
- Exercises requiring redundancy

### 3. Full Red Team (`engagement_type = "full-red-team"`)

**Purpose**: Full red team engagement with distributed operations

**Auto-Configuration**:
- **Deployment Mode**: `phases`
- **C2 Servers**: 1 server per engagement phase (staging, post-ex, long-haul)
- **Use Case**: Full red team operations, distributed C2 infrastructure

**Configuration Example**:
```hcl
engagement_type = "full-red-team"
# Automatically sets: c2_deployment_mode = "phases"
# Deploys: 3 C2 servers (one per phase)
```

**What Gets Deployed**:
- 1 C2 staging server
- 1 C2 post-ex server
- 1 C2 long-haul server
- 2 Proxy/redirector servers
- Phase-based distributed infrastructure

**Cost**: ~$120/month (3 C2 servers + proxies)

**Best For**:
- Full red team engagements
- Distributed operations (Cobalt Strike pattern)
- Long-term engagements
- Phase-isolated infrastructure

## Auto-Configuration Mapping

| Engagement Type | Deployment Mode | C2 Servers | Use Case |
|----------------|-----------------|------------|----------|
| `adhoc` | `single` | 1 | One-off tests |
| `purple-team` | `redundancy` | 2+ | Purple team exercises |
| `full-red-team` | `phases` | 3 (one per phase) | Full red team engagement |

## Configuration Examples

### Example 1: Adhoc Engagement
```hcl
engagement_type = "adhoc"
# That's it! Infrastructure auto-configures for single server
```

### Example 2: Purple Team Exercise
```hcl
engagement_type = "purple-team"
c2_server_count = 3  # Optional: increase redundancy
# Infrastructure auto-configures for redundancy mode
```

### Example 3: Full Red Team Engagement
```hcl
engagement_type = "full-red-team"

# Optional: Customize phase configurations
c2_phases = {
  staging = {
    enabled = true
    instance_type = "t3.medium"
    # ... phase-specific config
  }
  post-ex = {
    enabled = true
    instance_type = "t3.medium"
    # ... phase-specific config
  }
  long-haul = {
    enabled = true
    instance_type = "t3.large"  # Larger for long-term
    # ... phase-specific config
  }
}
```

## Manual Override

You can override the auto-configuration by explicitly setting `c2_deployment_mode`:

```hcl
engagement_type = "purple-team"  # Would normally set redundancy mode
c2_deployment_mode = "phases"    # But we override to phases mode
```

## Tags

When `engagement_type` is set, it's automatically added to resource tags:

```json
{
  "EngagementType": "adhoc",
  "Project": "RedTeamInfra",
  "Environment": "dev",
  ...
}
```

This helps with:
- Resource organization
- Cost tracking per engagement type
- Infrastructure management
- Reporting

## Cost Comparison

| Engagement Type | Monthly Cost | Servers |
|----------------|--------------|---------|
| Adhoc | ~$60 | 1 C2 + 2 Proxy |
| Purple Team | ~$90 | 2 C2 + 2 Proxy |
| Full Red Team | ~$120 | 3 C2 + 2 Proxy |

## Best Practices

### Adhoc Engagements:
- Use for quick tests only
- Destroy infrastructure after use
- Minimal configuration needed

### Purple Team Exercises:
- Use redundancy mode for reliability
- May need 2-3 C2 servers depending on exercise scope
- Keep infrastructure for duration of exercise

### Full Red Team Engagements:
- Always use phases mode
- Configure phase-specific settings
- Plan for long-term infrastructure
- Consider phase-specific domains

## Summary

**Engagement Types** provide a simple way to configure infrastructure:
- **Adhoc**: Quick, single server setup
- **Purple Team**: Redundant, collaborative setup
- **Full Red Team**: Distributed, phase-based setup

Simply set `engagement_type` and the infrastructure auto-configures appropriately!

