# SSH Key Management Architecture

![SSH Key Management Architecture](../../generated-diagrams/ssh-key-architecture.png)

## Overview

The project uses a layered SSH key architecture with three categories of keys. Private keys for inter-instance communication are generated on the hosts themselves and never pass through Terraform or the AWS API.

## Key Categories

### Category A: Operator External Key (User Access)

The operator's own SSH key (ed25519 or RSA) is registered as an AWS key pair via `var.user_public_key`. The private key never enters Terraform state.

```
Operator laptop → public key → terraform.tfvars → aws_key_pair → EC2 instances
                  private key stays on operator's laptop
```

**Used by:** All Linux instances (C2 team servers, proxy redirectors, bastion, GOAD jumpbox)

### Category B: Windows Instance Key (Auto-Generated RSA)

Terraform generates a 4096-bit RSA key pair for Windows instances. AWS requires RSA for Windows AMI password decryption.

```hcl
resource "tls_private_key" "windows" {
  algorithm = "RSA"
  rsa_bits  = 4096
}
```

**Security note:** The private key IS stored in Terraform state (inherent limitation). The web app uses it to decrypt the EC2Launch v2 auto-generated Administrator password.

**Used by:** Attack Box (Windows Server 2022), Bastion (Windows Server)

### Category C: Host-Generated Internal Keys (Inter-Instance)

Private keys are generated on the host at boot time and exchanged via S3. This is the most secure approach — private keys never leave their host.

| Key | Algorithm | Generated On | Public Key Shared Via |
|-----|-----------|-------------|----------------------|
| Jumpbox internal | ed25519 | Jumpbox cloud-init | S3 `keys/{id}/jumpbox_internal.pub` |
| Attack box internal | ed25519 | Attack box PowerShell | S3 `keys/{id}/attackbox_internal.pub` |
| Attack box WSL | ed25519 | Attack box WSL init | S3 `keys/{id}/wsl_attackbox_internal.pub` |

## S3 Key Exchange Flow (GOAD-Only Mode)

The S3-based key exchange only activates for GOAD-only deployments (`enable_key_exchange = true`). C2/combined deployments skip this entirely — the attack box accesses C2 servers via bastion SSH tunnels instead.

### Sequence

```
1. Jumpbox boots first
   ├── Generates ed25519 key pair locally
   ├── Uploads PUBLIC key to S3: keys/{id}/jumpbox_internal.pub
   └── Writes status beacon: status/{id}/jumpbox-ready

2. Team Server polls S3 (10s intervals, up to 10 min)
   ├── Downloads jumpbox_internal.pub from S3
   ├── Appends to /home/ubuntu/.ssh/authorized_keys
   └── Later: downloads attackbox keys too

3. Attack Box polls S3 (10s intervals, up to 10 min)
   ├── Downloads jumpbox_internal.pub from S3
   ├── Generates own ed25519 key pair locally
   ├── Uploads PUBLIC key to S3: keys/{id}/attackbox_internal.pub
   └── WSL also uploads: keys/{id}/wsl_attackbox_internal.pub
```

### S3 Prefix Structure

```
{project}-deploy-files-{hex}/
  keys/{project}/
    jumpbox_internal.pub        ← Written by jumpbox
    attackbox_internal.pub      ← Written by attack box
    wsl_attackbox_internal.pub  ← Written by attack box WSL
  status/{project}/
    jumpbox-ready               ← Readiness beacon
```

### S3 Lifecycle

- `keys/` objects auto-expire after **7 days** (only needed during bootstrap)
- `status/` objects auto-expire after **7 days**
- All objects removed on `terraform destroy` (`force_destroy = true`)

## SSH Hardening

All Linux instances apply these SSH settings via their init scripts:

| Setting | Value | Reason |
|---------|-------|--------|
| `PermitRootLogin` | `no` | Prevent direct root access |
| `PasswordAuthentication` | `no` | Key-only authentication |
| `MaxAuthTries` | `3` | Limit brute force attempts |
| `MaxSessions` | `10` | Reasonable session limit |
| `ClientAliveInterval` | `300` | 5-minute keepalive |
| `ClientAliveCountMax` | `2` | Disconnect after 10 min idle |
| `AllowAgentForwarding` | `yes` | Required for SSH agent through bastion |
| `AllowTcpForwarding` | `yes` | Required for port forwarding to C2 |
| `X11Forwarding` | `no` | Not needed, reduces attack surface |

## IAM Permissions for Key Exchange

Key exchange uses the same IAM roles as S3 file access (see [IAM Security](./iam-security.md)):

| Action | Resource | Role |
|--------|----------|------|
| `s3:PutObject` | `keys/*` | GOAD role (jumpbox, attack box upload their public keys) |
| `s3:GetObject` | `keys/*` | GOAD role (team server, attack box download peer keys) |
| `s3:PutObject` | `status/*` | GOAD role (jumpbox writes readiness beacon) |
| `s3:ListBucket` | Bucket (prefix: `keys/*`, `status/*`) | GOAD role |

All conditioned on `SourceVpc = GOAD VPC` + `SecureTransport = true`.

## Ansible Playbooks (Supplementary)

These are manual-use tools, not part of the automated bootstrap:

| Playbook | Purpose |
|----------|---------|
| `ansible/playbooks/distribute-ssh-keys.yml` | Add SSH public keys to target hosts via `authorized_key` module |
| `ansible/playbooks/setup-jumpbox-keys.yml` | Generate RSA key on jumpbox (older approach, superseded by S3 exchange) |
| `scripts/utilities/setup-ssh-keys.sh` | CLI wrapper: generates key + calls Ansible |

## Operator Access Methods

| Target | Method | Key Used |
|--------|--------|----------|
| Bastion (Windows) | RDP to public IP | Windows RSA key (password decryption) |
| C2 Team Server | `ssh -L 50050:c2_ip:50050 ubuntu@bastion_ip` | Operator external key |
| GOAD Jumpbox | SSH to public IP | Operator external key |
| Attack Box (C2 mode) | RDP via bastion tunnel | Windows RSA key |
| Attack Box (GOAD mode) | RDP to public IP / SSH via jumpbox | Windows RSA key / internal key |

## Related Files

| File | Purpose |
|------|---------|
| `terraform/main.tf` (lines 214-250) | Key pair resources (`deployer`, `windows`) |
| `terraform/modules/goad/scripts/jumpbox_init.sh` | Jumpbox key generation + S3 upload |
| `terraform/modules/goad/scripts/teamserver_init.sh` | Team server key polling from S3 |
| `terraform/modules/attack_box/scripts/attack_box_init.ps1` | Attack box key exchange (Phase 7) |
| `terraform/modules/deployment_storage/main.tf` | SSH key exchange IAM policies |
| `ansible/playbooks/distribute-ssh-keys.yml` | Manual key distribution |
