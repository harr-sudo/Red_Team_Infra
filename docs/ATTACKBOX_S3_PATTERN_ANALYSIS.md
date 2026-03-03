# Attack Box S3 Pattern - Deployment Analysis

> **Updated**: February 2026 — Reflects standalone attack box module (`terraform/modules/attack_box/`)

## When is the Attack Box Deployed?

The Attack Box is now a **standalone module** deployed across **all 11 deployment types** when:

```hcl
var.enable_attack_box = true  # default: true
```

### Deployment Logic (from main.tf):

```hcl
deploy_attack_box = var.enable_attack_box  # line 84
```

The standalone module (`terraform/modules/attack_box/`) is instantiated at the root level with `count = local.deploy_attack_box ? 1 : 0`. VPC placement is determined by deployment type:

- **C2-only / Combined**: C2 VPC private subnet (10.0.10.0/24), IP 10.0.10.50
- **GOAD-only**: GOAD VPC private subnet (192.168.56.0/26), IP 192.168.56.50

## When is the S3 Bucket Available?

The `cs_storage` module (which creates the S3 bucket) is deployed when:

```hcl
count = var.cobalt_strike_archive_s3_path != "" || local.deploy_c2_infra || local.is_goad_only ? 1 : 0
```

This means the S3 bucket is created when **ANY** of:
1. Cobalt Strike archive path is provided
2. C2 infrastructure is being deployed (`c2-*` or `combined-*` deployment types)
3. GOAD-only mode is active (`goad-*` deployment types)

Since all 11 deployment types match at least one condition, the S3 bucket is **always available**.

## Analysis: Will the S3 Pattern Always Work?

### YES - The S3 bucket will ALWAYS be available when the attack box is deployed

**Reason:**
- Attack box deploys when: `var.enable_attack_box = true` (any deployment type)
- S3 bucket deploys when: any of c2/goad/combined or CS archive path provided
- All 11 deployment types trigger S3 bucket creation
- Therefore: If attack box deploys → S3 bucket is guaranteed to exist

### Verification from standalone module (attack_box/main.tf):

```hcl
resource "aws_s3_object" "attack_box_init_script" {
  count = local.use_s3_bootstrap ? 1 : 0  # true when deployment_bucket != ""
  bucket = var.deployment_bucket
  key    = "${var.deployment_id}/scripts/attack_box_init.ps1"
  # ...
}
```

The S3 upload is conditional on `deployment_bucket != ""`, which is passed from root `main.tf`:

```hcl
deployment_bucket = length(module.cs_storage) > 0 ? module.cs_storage[0].bucket_name : ""
```

### IAM Profile Selection

The module automatically selects the correct IAM profile based on deployment type:

```hcl
iam_instance_profile_name = length(module.cs_storage) > 0 ? (
  local.is_goad_only ? module.cs_storage[0].instance_profile_name_goad : module.cs_storage[0].instance_profile_name_c2
) : ""
```

- **C2/Combined**: Uses C2 instance profile (VPC-restricted to C2 VPC)
- **GOAD-only**: Uses GOAD instance profile (VPC-restricted to GOAD VPC, includes `s3:PutObject` for key exchange)

## Edge Case Analysis

### Scenario 1: User doesn't provide `cobalt_strike_archive_s3_path`
- **Result**: Still works
- **Why**: Deployment type condition (`local.deploy_c2_infra || local.is_goad_only`) ensures bucket is created

### Scenario 2: User disables attack box (`enable_attack_box = false`)
- **Result**: No issue
- **Why**: Module count = 0, no S3 script upload, no instance created

### Scenario 3: C2-only deployment (c2-adhoc)
- **Result**: Works
- **Why**: Attack box placed in C2 VPC private subnet, uses C2 IAM profile, S3 bucket created by `local.deploy_c2_infra`

### Scenario 4: GOAD-only deployment (goad-mini)
- **Result**: Works
- **Why**: Attack box placed in GOAD VPC, uses GOAD IAM profile with `s3:PutObject` for key exchange

### Scenario 5: Combined deployment (combined-adhoc-mini)
- **Result**: Works
- **Why**: Attack box placed in C2 VPC (not GOAD VPC), key exchange disabled, uses C2 IAM profile

## Deployment Mode Breakdown

| Deployment Type | Attack Box? | VPC | S3 Bucket? | Key Exchange? | Works? |
|----------------|-------------|-----|------------|---------------|--------|
| `c2-adhoc` | Yes | C2 (10.0.10.50) | Yes | No | **YES** |
| `c2-purple` | Yes | C2 (10.0.10.50) | Yes | No | **YES** |
| `c2-full` | Yes | C2 (10.0.10.50) | Yes | No | **YES** |
| `goad-mini` | Yes | GOAD (192.168.56.50) | Yes | Yes | **YES** |
| `goad-light` | Yes | GOAD (192.168.56.50) | Yes | Yes | **YES** |
| `goad-sccm` | Yes | GOAD (192.168.56.50) | Yes | Yes | **YES** |
| `goad-full` | Yes | GOAD (192.168.56.50) | Yes | Yes | **YES** |
| `goad-nha` | Yes | GOAD (192.168.56.50) | Yes | Yes | **YES** |
| `combined-adhoc-mini` | Yes | C2 (10.0.10.50) | Yes | No | **YES** |
| `combined-adhoc-light` | Yes | C2 (10.0.10.50) | Yes | No | **YES** |
| `combined-full-full` | Yes | C2 (10.0.10.50) | Yes | No | **YES** |

## Conclusion

The S3 download pattern works for **ALL 11 deployment scenarios**.

The standalone module guarantees that:
1. The S3 bucket is created whenever the attack box is deployed (all deployment types trigger bucket creation)
2. The correct IAM profile is selected (C2 or GOAD, VPC-restricted)
3. The S3 script upload is conditional on bucket availability
4. The bootstrap script retries downloads 5x with 10-second delays
5. GOAD key exchange is only enabled for GOAD-only deployments

See [Attack Box Architecture](./architectures/attackbox.md) for full documentation.
