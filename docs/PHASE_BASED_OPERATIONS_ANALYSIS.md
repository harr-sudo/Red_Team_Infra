# Phase-Based Distributed Operations Analysis

This document analyzes the current infrastructure's support for phase-based distributed operations (as shown in the Cobalt Strike distributed operations diagram).

## Distributed Operations Pattern

### Concept
**Dedicated team servers for each phase of an engagement:**
- **Staging** - Initial access phase
- **Post-Ex** - Post-exploitation phase  
- **Long Haul** - Persistence/long-term access phase

### Benefits
- **Resilience**: If one phase is discovered/blocked, other channels maintain access
- **OpSec**: Isolation between phases reduces correlation
- **Operational Flexibility**: Different infrastructure per engagement phase

## Current Architecture Analysis

### ✅ What We Have

1. **Multiple C2 Servers**
   - Configurable count (`c2_server_count = 2`)
   - Can deploy multiple servers
   - Redundancy support

2. **Modular Design**
   - Separate C2 team server module
   - Easy to extend
   - Configurable per-server settings

3. **Tagging System**
   - Resource tagging in place
   - Can add phase tags

### ❌ What's Missing for Phase-Based Operations

1. **Phase Differentiation**
   - Current: All servers are generic (`c2-team-server-1`, `c2-team-server-2`)
   - Needed: Phase-specific naming (`c2-staging-server`, `c2-postex-server`, `c2-longhaul-server`)

2. **Phase-Specific Configuration**
   - Current: Single configuration for all C2 servers
   - Needed: Per-phase configuration (instance types, counts, user data)

3. **Phase Tagging**
   - Current: Generic tags (`Type = "C2TeamServer"`)
   - Needed: Phase tags (`Phase = "Staging"`, `Phase = "PostEx"`, `Phase = "LongHaul"`)

4. **Phase-Based Deployment**
   - Current: Deploy all servers at once
   - Needed: Deploy servers per phase (optional phases)

5. **Phase-Specific Security Groups**
   - Current: Single security group for all C2 servers
   - Needed: Optional phase-specific security groups for isolation

6. **Phase-Specific Domains**
   - Current: Generic domain configuration
   - Needed: Per-phase domain assignment

## Architecture Gap

### Current Flow:
```
Target → Proxy → Firewall → [Generic C2 Servers] → Operator
```

### Needed Flow (Phase-Based):
```
Target → Proxy → Firewall → [Staging Server] → Operator
                    ↓
              [Post-Ex Server] → Operator
                    ↓
              [Long Haul Server] → Operator
```

## What Would Need to Be Added

### 1. Phase Configuration Structure

**New Variable Structure:**
```hcl
# Phase-based C2 server configuration
c2_phases = {
  staging = {
    enabled = true
    server_count = 1
    instance_type = "t3.medium"
    user_data = ""  # Phase-specific setup
  }
  post_ex = {
    enabled = true
    server_count = 1
    instance_type = "t3.medium"
    user_data = ""
  }
  long_haul = {
    enabled = true
    server_count = 1
    instance_type = "t3.medium"
    user_data = ""
  }
}
```

### 2. Modified C2 Server Module

**Changes Needed:**
- Accept phase name as parameter
- Phase-specific naming: `{project}-{env}-c2-{phase}-server-{n}`
- Phase-specific tags: `Phase = "{phase}"`
- Phase-specific user data
- Optional phase-specific security groups

### 3. Multiple Module Instantiations

**In main.tf:**
```hcl
# Staging Phase
module "c2_staging" {
  source = "./modules/c2_team_server"
  phase = "staging"
  # ... phase-specific config
}

# Post-Ex Phase
module "c2_post_ex" {
  source = "./modules/c2_team_server"
  phase = "post-ex"
  # ... phase-specific config
}

# Long Haul Phase
module "c2_long_haul" {
  source = "./modules/c2_team_server"
  phase = "long-haul"
  # ... phase-specific config
}
```

### 4. Phase-Specific Outputs

**Outputs Needed:**
- Per-phase instance IDs
- Per-phase private IPs
- Per-phase connection info
- Phase-based Ansible inventory

### 5. Domain Assignment Per Phase

**Domain Configuration:**
- Staging: Use primary domain or staging subdomain
- Post-Ex: Use backup domain 1
- Long Haul: Use backup domain 2

## Implementation Approach

### Option 1: Modify Existing Module (Recommended)
- Add `phase` parameter to C2 team server module
- Use `for_each` or multiple module calls for phases
- Maintain backward compatibility

### Option 2: New Phase-Based Module
- Create new `c2_phase_server` module
- Keep existing module for generic deployments
- More flexible but more code

### Option 3: Terraform Workspaces
- Use workspaces for different phases
- Deploy phases separately
- More complex but maximum isolation

## Current Capabilities vs. Requirements

| Requirement | Current Status | Gap |
|------------|----------------|-----|
| Multiple C2 servers | ✅ Supported | None |
| Phase-specific naming | ❌ Not supported | Need phase parameter |
| Phase-specific config | ❌ Not supported | Need phase config structure |
| Phase isolation | ⚠️ Partial | Same security group for all |
| Phase-specific domains | ❌ Not supported | Need domain assignment logic |
| Phase-based deployment | ❌ Not supported | Need conditional deployment |
| Phase tagging | ❌ Not supported | Need phase tags |

## Workaround (Current Architecture)

**Can be done manually:**
1. Deploy infrastructure multiple times with different `project_name` or `environment`
2. Manually tag servers with phase names
3. Configure C2 framework to use different servers per phase
4. Use different domains per phase manually

**Limitations:**
- Not automated
- Not scalable
- Manual management overhead
- No infrastructure-level phase isolation

## Recommended Implementation

### Phase 1: Add Phase Support to Module
1. Add `phase` variable to C2 team server module
2. Update naming to include phase
3. Add phase tags
4. Maintain backward compatibility

### Phase 2: Phase Configuration
1. Add phase configuration structure to variables
2. Support per-phase settings
3. Enable/disable phases

### Phase 3: Multiple Phase Deployment
1. Use `for_each` for phase modules
2. Conditional deployment per phase
3. Phase-specific outputs

### Phase 4: Phase Isolation
1. Optional phase-specific security groups
2. Phase-specific domain assignment
3. Enhanced isolation

## Summary

### Current State:
- ✅ Can deploy multiple C2 servers
- ✅ Modular architecture supports extension
- ❌ No phase differentiation
- ❌ No phase-based configuration
- ❌ No phase-specific naming/tagging

### To Support Phase-Based Operations:
1. **Add phase parameter** to C2 server module
2. **Create phase configuration** structure
3. **Deploy multiple module instances** (one per phase)
4. **Add phase-specific outputs** and inventory
5. **Optional**: Phase-specific security groups and domains

### Estimated Effort:
- **Small Change**: Add phase parameter and naming (~1-2 hours)
- **Medium Change**: Full phase configuration support (~4-6 hours)
- **Large Change**: Complete phase-based architecture with isolation (~1-2 days)

The current architecture **can support** phase-based operations with manual configuration, but **does not natively support** automated phase-based deployment. The modular design makes it relatively straightforward to add this capability.

