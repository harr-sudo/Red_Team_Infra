# Windows Attack Box - Detailed Architecture

## Overview

The **Windows Attack Box** is a standalone Terraform module (`terraform/modules/attack_box/`) providing a **Windows Server 2022 workstation** optimized for red team operations. It deploys across **all 11 deployment types** with automatic VPC-aware placement.

**Key Design Decisions:**
- **Standalone module** — not embedded in GOAD or C2 modules, reusable everywhere
- **S3 bootstrap pattern** — bypasses EC2's 16KB user_data limit for large init scripts
- **Static private IPs** — predictable addressing for SSH configs and documentation
- **Toggleable** — `enable_attack_box = true` (default), disable to save ~$50/month

## Module Location

```
terraform/modules/attack_box/
├── main.tf                              # Instance, NIC, S3 script upload
├── variables.tf                         # All input variables
├── outputs.tf                           # Instance ID, IP, password, RDP tunnel
└── scripts/
    ├── attack_box_bootstrap.ps1         # Lightweight bootstrap (< 16KB, user_data)
    └── attack_box_init.ps1              # Full init script (uploaded to S3)
```

## Deployment Across All Types

| Deployment Type | VPC | Subnet | Private IP | Access Via | Key Exchange |
|---|---|---|---|---|---|
| **c2-adhoc** | C2 VPC (10.0.0.0/16) | Private (10.0.10.0/24) | 10.0.10.50 | Bastion RDP tunnel | No |
| **c2-purple** | C2 VPC (10.0.0.0/16) | Private (10.0.10.0/24) | 10.0.10.50 | Bastion RDP tunnel | No |
| **c2-full** | C2 VPC (10.0.0.0/16) | Private (10.0.10.0/24) | 10.0.10.50 | Bastion RDP tunnel | No |
| **goad-mini** | GOAD VPC (192.168.56.0/24) | Private (192.168.56.0/26) | 192.168.56.50 | Jumpbox SSH tunnel | Yes (S3) |
| **goad-light** | GOAD VPC (192.168.56.0/24) | Private (192.168.56.0/26) | 192.168.56.50 | Jumpbox SSH tunnel | Yes (S3) |
| **goad-sccm** | GOAD VPC (192.168.56.0/24) | Private (192.168.56.0/26) | 192.168.56.50 | Jumpbox SSH tunnel | Yes (S3) |
| **goad-full** | GOAD VPC (192.168.56.0/24) | Private (192.168.56.0/26) | 192.168.56.50 | Jumpbox SSH tunnel | Yes (S3) |
| **goad-nha** | GOAD VPC (192.168.56.0/24) | Private (192.168.56.0/26) | 192.168.56.50 | Jumpbox SSH tunnel | Yes (S3) |
| **combined-adhoc-mini** | C2 VPC (10.0.0.0/16) | Private (10.0.10.0/24) | 10.0.10.50 | Bastion RDP tunnel | No |
| **combined-adhoc-light** | C2 VPC (10.0.0.0/16) | Private (10.0.10.0/24) | 10.0.10.50 | Bastion RDP tunnel | No |
| **combined-full-full** | C2 VPC (10.0.0.0/16) | Private (10.0.10.0/24) | 10.0.10.50 | Bastion RDP tunnel | No |

### VPC Placement Logic (from `main.tf`)

```hcl
# Network placement: C2 VPC for C2/combined, GOAD VPC for GOAD-only
subnet_id         = local.is_goad_only ? module.goad[0].private_subnet_id : module.vpc[0].private_subnet_ids[0]
security_group_id = local.is_goad_only ? module.goad[0].security_group_id : module.security[0].attack_box_security_group_id
private_ip        = local.is_goad_only ? "${local.goad_ip_range}.50" : local.attack_box_private_ip  # 10.0.10.50

# C2 Server connection (for CS Client shortcut on desktop)
c2_server_ip   = local.is_goad_only ? "${local.goad_ip_range}.40" : local.c2_server_private_ips[0]  # 10.0.10.10

# Key exchange (GOAD-only: S3-based SSH key exchange with jumpbox)
enable_key_exchange = local.is_goad_only
```

## Architecture: C2/Combined Mode

```
C2 VPC (10.0.0.0/16)
├── Management Subnet (10.0.0.0/24)
│   └── Bastion Host (10.0.0.10, EIP)  ← Operator RDP entry point
│
├── Private Subnet (10.0.10.0/24) — NO public IPs
│   ├── C2 Team Server (10.0.10.10)    ← CS Team Server (port 50050)
│   └── Attack Box (10.0.10.50)        ← Windows workstation
│
└── Security Group: attack_box_sg
    Ingress: RDP 3389 + SSH 22 from bastion_sg only
    Egress: All outbound (0.0.0.0/0)
```

**Operator Access:**
```bash
# Option 1: RDP tunnel through bastion
ssh -i key.pem -L 3390:10.0.10.50:3389 ubuntu@<bastion-eip>
mstsc /v:localhost:3390   # Login: Administrator / <password from terraform output>

# Option 2: From bastion RDP session, open RDP to 10.0.10.50
```

## Architecture: GOAD-Only Mode

```
GOAD VPC (192.168.56.0/24)
├── Public Subnet (192.168.56.64/26)
│   └── Jumpbox (192.168.56.100, EIP)  ← SSH gateway
│
├── Private Subnet (192.168.56.0/26)
│   ├── Team Server (192.168.56.40)    ← CS Team Server
│   ├── Attack Box (192.168.56.50)     ← Windows workstation
│   └── AD VMs (192.168.56.10-23)      ← Domain controllers
│
└── Security Group: goad_sg (shared)
    Ingress: All traffic within VPC CIDR + SSH/RDP from management CIDRs
    Egress: HTTP, HTTPS, DNS, ICMP, internal
```

**Operator Access:**
```bash
# Option 1: RDP tunnel through jumpbox
ssh -i goad-jumpbox.pem -L 3389:192.168.56.50:3389 ubuntu@<jumpbox-eip>
mstsc /v:localhost:3389   # Login: Administrator / <password>

# Option 2: CS Client tunnel (run CS on your laptop)
ssh -i goad-jumpbox.pem -L 50050:192.168.56.40:50050 ubuntu@<jumpbox-eip>
# Then connect CS Client to localhost:50050
```

### GOAD Key Exchange (S3-Based)

In GOAD-only mode, the attack box and jumpbox exchange SSH keys via S3 for passwordless internal access:

```
Jumpbox (Ubuntu):
  1. Generates Ed25519 key pair during bootstrap
  2. Uploads public key to: s3://<bucket>/keys/<project>/jumpbox_internal.pub
  3. Downloads attack box public key from S3 → adds to authorized_keys

Attack Box (Windows):
  1. Downloads jumpbox public key from S3 (retries 60x, 10s intervals)
  2. Installs to C:\ProgramData\ssh\administrators_authorized_keys
  3. Generates Ed25519 key pair for outbound SSH
  4. Uploads public key to: s3://<bucket>/keys/<project>/attackbox_internal.pub
```

After key exchange completes, from the attack box:
```powershell
# SSH config auto-created — just type:
ssh teamserver   # Connects to 192.168.56.40

# Or from WSL:
ssh ubuntu@192.168.56.40
```

## Instance Specification

| Property | Value |
|---|---|
| **AMI** | Windows Server 2022 Full Base (latest, auto-detected) |
| **Instance Type** | t2.large (default — 8GB RAM for CS Client + tools) |
| **Root Volume** | 100GB gp3, encrypted, delete on termination |
| **Network Interface** | Dedicated ENI with static private IP |
| **IAM Profile** | C2 or GOAD instance profile (S3 access for CS + scripts) |
| **Monitoring** | Configurable (default: basic) |
| **Public IP** | None (private subnet only) |

## S3 Bootstrap Pattern

The full init script (`attack_box_init.ps1`) exceeds EC2's 16KB user_data limit. The module uses a two-stage bootstrap:

```
Stage 1: EC2 User Data (< 16KB)
  attack_box_bootstrap.ps1 → Runs at instance launch
    1. Downloads attack_box_init.ps1 from S3 (retries 5x)
    2. Executes the full init script

Stage 2: S3 Upload (Terraform)
  aws_s3_object.attack_box_init_script → Uploads templated script to:
    s3://<deployment_bucket>/<project_name>/scripts/attack_box_init.ps1
```

The bootstrap only needs 3 variables (bucket, deployment_id, region). All other configuration is templated into the S3 script.

### Lifecycle Protection

```hcl
lifecycle {
  ignore_changes = [user_data]
}
```

Script changes don't trigger instance recreation. Use `terraform taint` to force rebuild when needed.

## Init Script Phases

The init script (`attack_box_init.ps1`) runs 8 phases:

### Phase 1: Remove Server Bloat
- Disable Server Manager auto-start
- Disable IE Enhanced Security Configuration
- Optimize for foreground programs (not background services)
- Stop unnecessary server services (W3SVC, MSSQLSERVER, etc.)

### Phase 2: Disable Windows Defender
- Registry keys: DisableAntiSpyware, DisableAntiVirus, DisableRealtimeMonitoring
- PowerShell cmdlets: Set-MpPreference for all protection types
- Exclusion paths: `C:\Tools`, `C:\Payloads`, `C:\CobaltStrike`
- Stop and disable WinDefend, WdNisSvc, WdBoot, WdFilter, Sense services

### Phase 3: System Configuration
- Set hostname to `attackbox-windows`
- Create directory structure: `C:\Tools`, `C:\Payloads`, `C:\CobaltStrike`, `.ssh`
- Set Administrator password (auto-generated 30-char or user-provided)
- Enable Remote Desktop (RDP)
- Install and start OpenSSH Server
- Install Chocolatey package manager
- Install tools via Chocolatey: Git, 7-Zip, Python 3, Java 17, AWS CLI, Windows Terminal

### Phase 4: Clone Red Team Tools Repository
- Clones `tools_repo_url` (default: `https://github.com/harr-sudo/red-team-tools.git`) to `C:\Tools`
- Falls back to cloning PowerSploit individually if no repo URL provided

### Phase 5: Install Cobalt Strike Client from S3
- Downloads CS archive from `cs_client_s3_path` (same S3 path as CS server archive)
- Auto-detects format (ZIP or tar.gz) and extracts to `C:\CobaltStrike`
- Finds `cobaltstrike.jar` and creates launch batch file
- Creates desktop shortcut "Cobalt Strike Client"

### Phase 6: WSL2 Setup
- Enables Windows Subsystem for Linux feature
- Enables Virtual Machine Platform
- Sets WSL default to version 1 (more compatible with EC2, no nested virt required)
- Installs Ubuntu (finalizes on first login)

### Phase 7: SSH Key Exchange (GOAD Only)
- Only runs when `enable_key_exchange = true`
- Downloads jumpbox public key from S3 (retries 60x, 10s intervals)
- Installs to `C:\ProgramData\ssh\administrators_authorized_keys`
- Generates Ed25519 key pair for outbound connections
- Uploads public key to S3 for jumpbox to download

### Phase 8: Desktop Shortcuts & SSH Config
- Creates SSH config for C2 server (`Host teamserver ts c2`)
- Creates `ATTACK-BOX-INFO.txt` on desktop with connection details
- Creates Payloads and Tools desktop shortcuts
- Writes completion marker to `init_status.txt`

## Directory Layout on Attack Box

```
C:\
├── CobaltStrike\           ← CS Client installation
│   ├── cobaltstrike.jar
│   ├── Launch-CS-Client.bat
│   └── status.txt          ← "CS_CLIENT_INSTALLED" marker
│
├── Tools\                   ← Red team tools (GitHub repo clone)
│   ├── PowerSploit\
│   ├── SharpTools\
│   └── ...
│
├── Payloads\                ← Empty — operator stages payloads here
│
├── Users\Administrator\
│   ├── Desktop\
│   │   ├── Cobalt Strike Client.lnk
│   │   ├── Payloads.lnk
│   │   ├── Tools.lnk
│   │   ├── ATTACK-BOX-INFO.txt
│   │   └── Deployment-Logs-Scripts\
│   │       ├── bootstrap.log
│   │       ├── attackbox-init.log
│   │       ├── attack_box_init_main.ps1
│   │       └── init_status.txt
│   └── .ssh\
│       ├── config           ← SSH config for teamserver alias
│       └── attackbox_internal_key[.pub]  ← GOAD mode only
│
└── ProgramData\ssh\
    └── administrators_authorized_keys    ← GOAD mode only
```

## Security Groups

### C2/Combined Mode: `attack_box_sg`

Defined in `terraform/modules/security/main.tf`:

```yaml
Inbound:
  - Port 3389 (RDP): from bastion_sg only
  - Port 22 (SSH): from bastion_sg only

Outbound:
  - All traffic: 0.0.0.0/0
```

The attack box can only be reached from the bastion host. No direct internet access inbound.

### GOAD Mode: `goad_sg` (shared)

Defined in `terraform/modules/goad/security.tf`:

```yaml
Inbound:
  - All protocols: from GOAD VPC CIDR (internal communication)
  - Port 22 (SSH): from management CIDRs
  - Port 3389 (RDP): from management CIDRs
  - Port 5985-5986 (WinRM): from management CIDRs

Outbound:
  - HTTP (80), HTTPS (443), DNS (53): 0.0.0.0/0
  - ICMP: 0.0.0.0/0
  - All protocols: within GOAD VPC CIDR
```

The GOAD security group is shared by all VMs (jumpbox, team server, attack box, AD VMs) and allows full internal communication.

## Terraform Variables

### Root-Level Variables (`terraform/variables.tf`)

| Variable | Type | Default | Description |
|---|---|---|---|
| `enable_attack_box` | bool | `true` | Deploy the attack box (set false to save costs) |
| `attack_box_instance_type` | string | `"t2.large"` | EC2 instance type |
| `attack_box_root_volume_size` | number | `100` | Root volume GB |
| `attack_box_admin_password` | string (sensitive) | `""` | Windows password (empty = auto-generate) |

### Module Variables (passed from `main.tf`)

| Variable | Source | Notes |
|---|---|---|
| `subnet_id` | VPC module (C2 or GOAD) | Auto-selected based on deployment type |
| `security_group_id` | Security module (C2) or GOAD module | Auto-selected |
| `private_ip` | locals | `10.0.10.50` (C2) or `192.168.56.50` (GOAD) |
| `c2_server_ip` | locals | `10.0.10.10` (C2) or `192.168.56.40` (GOAD) |
| `deployment_bucket` | cs_storage module | S3 bucket for scripts + CS files |
| `iam_instance_profile_name` | cs_storage module | C2 or GOAD profile (VPC-restricted) |
| `enable_key_exchange` | locals | `true` for GOAD-only, `false` otherwise |
| `tools_repo_url` | root variable | Git repo for red team tools |

## Terraform Outputs

| Output | Value | Notes |
|---|---|---|
| `attack_box_instance_id` | EC2 instance ID | |
| `attack_box_private_ip` | `10.0.10.50` or `192.168.56.50` | Depends on deployment type |
| `attack_box_admin_password` | 30-char auto-generated or user-provided | Sensitive |
| `attack_box_rdp_tunnel` | `ssh -L 3390:<ip>:3389 ...` | Uses port 3390 (avoids bastion 3389 conflict) |

## IAM Permissions

The attack box uses the same IAM instance profile as other instances in its VPC:

**C2/Combined mode** — `cs_storage` module's C2 instance profile:
- `s3:GetObject` on deployment bucket (scripts, CS files)
- VPC-restricted via `aws:SourceVpc` condition

**GOAD mode** — `cs_storage` module's GOAD instance profile:
- `s3:GetObject` + `s3:PutObject` on deployment bucket (scripts, CS files, key exchange)
- VPC-restricted via `aws:SourceVpc` condition

GOAD mode needs `s3:PutObject` for uploading the attack box's SSH public key during key exchange.

## Cost Breakdown

| Resource | Type | Cost/Month |
|---|---|---|
| EC2 Instance | t2.large (24/7) | ~$50 |
| EBS Volume | 100GB gp3 | ~$8 |
| **Total** | | **~$58** |

Set `enable_attack_box = false` to skip this component and save costs.

## Troubleshooting

### Init Script Didn't Run

```powershell
# Check bootstrap log (did it download the main script?)
type C:\Users\Administrator\Desktop\Deployment-Logs-Scripts\bootstrap.log

# Check main init log
type C:\Users\Administrator\Desktop\Deployment-Logs-Scripts\attackbox-init.log

# Check completion marker
type C:\Users\Administrator\Desktop\Deployment-Logs-Scripts\init_status.txt
# Should say: INIT_COMPLETE
```

### CS Client Not Installed

```powershell
# Check if CS was downloaded from S3
type C:\CobaltStrike\status.txt
# Should say: CS_CLIENT_INSTALLED

# Verify CS jar exists
dir C:\CobaltStrike\*.jar /s

# Check the init log for Phase 5 errors
findstr "PHASE 5" C:\Users\Administrator\Desktop\Deployment-Logs-Scripts\attackbox-init.log
```

### Cannot RDP to Attack Box

```bash
# Verify the SSH tunnel is active
ssh -i key.pem -L 3390:10.0.10.50:3389 ubuntu@<bastion-eip>

# Check security group allows RDP from bastion
aws ec2 describe-security-groups --group-ids <attack-box-sg-id>

# Verify the instance is running
aws ec2 describe-instances --instance-ids <attack-box-id> --query 'Reservations[].Instances[].State.Name'
```

### GOAD Key Exchange Failed (GOAD Mode Only)

```powershell
# Check if jumpbox key was downloaded
dir C:\ProgramData\ssh\administrators_authorized_keys

# Check if attack box key was uploaded to S3
aws s3 ls s3://<bucket>/keys/<project>/attackbox_internal.pub

# Check init log for Phase 7 errors
findstr "PHASE 7" C:\Users\Administrator\Desktop\Deployment-Logs-Scripts\attackbox-init.log
```

### Tools Repository Not Cloned

```powershell
# Check if C:\Tools has contents
dir C:\Tools

# Check init log for Phase 4
findstr "PHASE 4" C:\Users\Administrator\Desktop\Deployment-Logs-Scripts\attackbox-init.log

# Manual clone if needed
git clone https://github.com/harr-sudo/red-team-tools.git C:\Tools
```

### Force Rebuild

```bash
# The lifecycle block prevents script-change rebuilds. To force:
cd terraform
terraform taint 'module.attack_box[0].aws_instance.attack_box'
terraform apply
```

## Migration from GOAD-Embedded Attack Box

The attack box was previously embedded in `terraform/modules/goad/attackbox.tf`. It has been migrated to a standalone module:

| Old (Embedded) | New (Standalone) |
|---|---|
| `modules/goad/attackbox.tf` | `modules/attack_box/main.tf` |
| `modules/goad/attackbox_scripts.tf` | S3 upload in `modules/attack_box/main.tf` |
| `modules/goad/scripts/attackbox_init.ps1` | `modules/attack_box/scripts/attack_box_init.ps1` |
| `modules/goad/scripts/attackbox_bootstrap.ps1` | `modules/attack_box/scripts/attack_box_bootstrap.ps1` |
| GOAD-only deployment | ALL 11 deployment types |
| GOAD VPC only | C2 VPC or GOAD VPC (auto-selected) |
| GOAD security group only | Dedicated attack_box_sg (C2) or goad_sg (GOAD) |

The GOAD module outputs still reference the attack box IP (`credentials.attackbox.ip = 192.168.56.50`) and access instructions, but the actual instance is now managed by the standalone module at the root level.

## References

- [C2 Ad-Hoc Architecture](./c2-adhoc.md) — Attack box in C2 VPC context
- [GOAD Mini Architecture](./goad-mini.md) — Attack box in GOAD VPC context
- [S3 Security Architecture](../S3_CONFUSED_DEPUTY_FIX.md) — IAM roles and S3 bucket policies
- [SSH Key Management](../SSH_KEY_MANAGEMENT.md) — Key exchange patterns
