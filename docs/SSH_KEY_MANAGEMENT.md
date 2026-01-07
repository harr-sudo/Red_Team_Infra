# SSH Key Management for Infrastructure Access

## Overview

This document explains SSH key requirements and automation options for accessing infrastructure components from the jump box.

## Current Setup

### SSH Key Requirements

**Yes, you need SSH keys**, but there are several approaches to manage them:

1. **Single Key Pair** - One key pair for all Linux instances (current setup)
2. **Automated Key Distribution** - Keys automatically copied to instances
3. **AWS Systems Manager** - No SSH keys needed (alternative)
4. **Key Rotation** - Automated key management

## How It Currently Works

### Key Pair Configuration

All EC2 instances (C2 servers, proxy/redirectors) use the **same AWS key pair**:

```hcl
key_pair_name = "red-team-keypair"  # Set in terraform.tfvars
```

This key pair:
- ✅ Must exist in AWS before deployment
- ✅ Used by all Linux instances
- ✅ Private key needed for SSH access

### Access Flow

```
Home → RDP → Jump Box (Windows)
              ↓
          WSL2 (Ubuntu)
              ↓
          SSH → C2 Servers (using key.pem)
```

**From WSL2 on jump box:**
```bash
ssh ec2-user@c2-private-ip -i ~/.ssh/key.pem
```

## SSH Key Options

### Option 1: Single Key Pair (Current - Simple)

**How it works:**
- One AWS key pair created manually
- Private key stored on jump box (WSL2)
- Same key used for all instances

**Setup:**
1. **Create key pair in AWS:**
   ```bash
   aws ec2 create-key-pair --key-name red-team-keypair --query 'KeyMaterial' --output text > key.pem
   chmod 600 key.pem
   ```

2. **Copy to jump box:**
   - RDP to jump box
   - Copy key to WSL2: `cp /mnt/c/path/to/key.pem ~/.ssh/`
   - Set permissions: `chmod 600 ~/.ssh/key.pem`

3. **SSH to C2 servers:**
   ```bash
   ssh ec2-user@c2-private-ip -i ~/.ssh/key.pem
   ```

**Pros:**
- ✅ Simple setup
- ✅ One key to manage
- ✅ Works immediately

**Cons:**
- ⚠️ Manual key distribution
- ⚠️ Key rotation requires manual steps
- ⚠️ Single point of failure (if key compromised)

---

### Option 2: Automated Key Distribution (Recommended)

**How it works:**
- Use Ansible or user data scripts
- Automatically copy public keys to instances
- Multiple keys can be authorized

**Implementation:**

**A. Via Ansible (After Deployment):**
```yaml
# ansible/playbooks/setup-ssh-keys.yml
- name: Setup SSH keys
  hosts: all
  tasks:
    - name: Add operator SSH keys
      authorized_key:
        user: ec2-user
        key: "{{ item }}"
      with_file:
        - ~/.ssh/id_rsa.pub
        - ~/.ssh/operator2.pub
```

**B. Via User Data Script:**
```bash
#!/bin/bash
# Add to terraform.tfvars: c2_server_user_data

# Public keys to authorize (from S3, Secrets Manager, or hardcoded)
PUBLIC_KEYS=(
  "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ... operator1@jumpbox"
  "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ... operator2@jumpbox"
)

# Add keys to authorized_keys
for key in "${PUBLIC_KEYS[@]}"; do
  echo "$key" >> ~ec2-user/.ssh/authorized_keys
done

chmod 600 ~ec2-user/.ssh/authorized_keys
chown ec2-user:ec2-user ~ec2-user/.ssh/authorized_keys
```

**C. Via AWS Secrets Manager:**
```bash
#!/bin/bash
# Retrieve public keys from AWS Secrets Manager
PUBLIC_KEY=$(aws secretsmanager get-secret-value \
    --secret-id red-team-ssh-keys \
    --query SecretString --output text | jq -r '.public_key')

echo "$PUBLIC_KEY" >> ~ec2-user/.ssh/authorized_keys
```

**Pros:**
- ✅ Automated setup
- ✅ Multiple keys supported
- ✅ Easy key rotation
- ✅ Keys stored securely (Secrets Manager)

**Cons:**
- ⚠️ Requires initial setup
- ⚠️ Needs Ansible or user data configuration

---

### Option 3: AWS Systems Manager Session Manager (No Keys!)

**How it works:**
- No SSH keys needed
- Access via AWS CLI/Console
- Works from anywhere with AWS credentials

**Setup:**

1. **Install SSM Agent** (already on Amazon Linux 2):
   ```bash
   # Already installed, just needs IAM role
   ```

2. **Attach IAM Role to instances:**
   ```hcl
   # In terraform.tfvars
   c2_server_iam_instance_profile_name = "SSMInstanceProfile"
   ```

3. **Access from jump box:**
   ```bash
   # From WSL2 on jump box
   aws ssm start-session --target i-1234567890abcdef0
   ```

4. **Port forwarding for C2 client:**
   ```bash
   aws ssm start-session \
       --target i-1234567890abcdef0 \
       --document-name AWS-StartPortForwardingSession \
       --parameters '{"portNumber":["50050"],"localPortNumber":["50050"]}'
   ```

**Pros:**
- ✅ No SSH keys needed
- ✅ Audit trail in CloudTrail
- ✅ Works from anywhere
- ✅ No open SSH ports

**Cons:**
- ⚠️ Requires IAM roles
- ⚠️ AWS CLI dependency
- ⚠️ Different workflow than traditional SSH

---

### Option 4: SSH Key Rotation (Advanced)

**How it works:**
- Automated key generation
- Regular key rotation
- Keys stored in AWS Secrets Manager

**Implementation:**

1. **Generate keys automatically:**
   ```bash
   # Script to generate and rotate keys
   ssh-keygen -t rsa -b 4096 -f ~/.ssh/red-team-key -N ""
   ```

2. **Store in Secrets Manager:**
   ```bash
   aws secretsmanager create-secret \
       --name red-team-ssh-private-key \
       --secret-string file://~/.ssh/red-team-key
   ```

3. **Distribute via Ansible:**
   ```yaml
   - name: Rotate SSH keys
     authorized_key:
       user: ec2-user
       state: present
       key: "{{ lookup('aws_secretsmanager', 'red-team-ssh-public-key') }}"
   ```

**Pros:**
- ✅ Automated rotation
- ✅ Secure key storage
- ✅ Compliance-friendly

**Cons:**
- ⚠️ Complex setup
- ⚠️ Requires automation infrastructure

---

## Recommended Approach

### For Quick Setup: Option 1 (Single Key)

**Best for:**
- Small teams
- Quick deployments
- Simple operations

**Steps:**
1. Create one key pair in AWS
2. Copy private key to jump box WSL2
3. Use same key for all instances

### For Production: Option 2 + Option 3 (Hybrid)

**Best for:**
- Multiple operators
- Long-term operations
- Security compliance

**Setup:**
1. **SSH keys for direct access** (Option 2 - automated distribution)
2. **SSM for audit trail** (Option 3 - IAM roles)
3. **Both methods available** - operators choose

---

## Automation Scripts

### Script 1: Setup SSH Keys on Jump Box

```bash
#!/bin/bash
# setup-jumpbox-keys.sh

# Copy SSH key to WSL2
cp /mnt/c/Users/Administrator/Downloads/key.pem ~/.ssh/red-team-key.pem
chmod 600 ~/.ssh/red-team-key.pem

# Add to SSH config
cat >> ~/.ssh/config << EOF
Host c2-*
    User ec2-user
    IdentityFile ~/.ssh/red-team-key.pem
    StrictHostKeyChecking no
EOF

# Test connection
ssh -i ~/.ssh/red-team-key.pem ec2-user@c2-private-ip
```

### Script 2: Distribute Keys via Ansible

```yaml
# ansible/playbooks/distribute-keys.yml
- name: Distribute SSH keys to all instances
  hosts: all
  vars:
    operator_keys:
      - "{{ lookup('file', '~/.ssh/id_rsa.pub') }}"
      - "{{ lookup('file', '~/.ssh/operator2.pub') }}"
  
  tasks:
    - name: Ensure .ssh directory exists
      file:
        path: ~/.ssh
        state: directory
        mode: '0700'
    
    - name: Add operator SSH keys
      authorized_key:
        user: ec2-user
        key: "{{ item }}"
        state: present
      loop: "{{ operator_keys }}"
```

### Script 3: Automated Key Rotation

```bash
#!/bin/bash
# rotate-ssh-keys.sh

# Generate new key
ssh-keygen -t rsa -b 4096 -f /tmp/new-key -N ""

# Store in Secrets Manager
aws secretsmanager put-secret-value \
    --secret-id red-team-ssh-private-key \
    --secret-string file:///tmp/new-key

aws secretsmanager put-secret-value \
    --secret-id red-team-ssh-public-key \
    --secret-string file:///tmp/new-key.pub

# Distribute via Ansible
ansible-playbook ansible/playbooks/rotate-keys.yml \
    -e new_public_key="$(cat /tmp/new-key.pub)"

# Remove old key from instances
# (via Ansible playbook)
```

---

## Answer to Your Question

### Do you need SSH keys for each machine?

**Short answer:** No, you can use **one key pair for all Linux instances**.

**Current setup:**
- ✅ One AWS key pair (`red-team-keypair`)
- ✅ Used by all C2 servers and proxy/redirectors
- ✅ Private key stored on jump box WSL2
- ✅ Same key works for all instances

### Can keys be automated?

**Yes, absolutely!** Several options:

1. **User Data Scripts** - Automatically add public keys on instance launch
2. **Ansible Playbooks** - Distribute keys after deployment
3. **AWS Secrets Manager** - Store and retrieve keys securely
4. **AWS Systems Manager** - No keys needed (alternative)

---

## Quick Setup Guide

### Minimal Setup (One Key)

1. **Create key pair:**
   ```bash
   aws ec2 create-key-pair --key-name red-team-keypair \
       --query 'KeyMaterial' --output text > key.pem
   chmod 600 key.pem
   ```

2. **Set in terraform.tfvars:**
   ```hcl
   key_pair_name = "red-team-keypair"
   ```

3. **After deployment, copy to jump box:**
   - RDP to jump box
   - Copy key to WSL2: `cp /mnt/c/path/to/key.pem ~/.ssh/`
   - `chmod 600 ~/.ssh/key.pem`

4. **SSH to any C2 server:**
   ```bash
   ssh ec2-user@c2-private-ip -i ~/.ssh/key.pem
   ```

### Automated Setup (Recommended)

1. **Generate key on jump box:**
   ```bash
   # In WSL2
   ssh-keygen -t rsa -b 4096 -f ~/.ssh/red-team-key -N ""
   ```

2. **Add public key to user data:**
   ```hcl
   c2_server_user_data = <<-EOF
     #!/bin/bash
     echo "ssh-rsa AAAAB3NzaC1yc2E... operator@jumpbox" >> ~ec2-user/.ssh/authorized_keys
   EOF
   ```

3. **Or use Ansible after deployment:**
   ```bash
   ansible-playbook ansible/playbooks/setup-ssh-keys.yml
   ```

---

## Security Best Practices

### Key Management

1. **Store private keys securely:**
   - ✅ On jump box only (WSL2)
   - ✅ Permissions: `600` (owner read/write only)
   - ✅ Never commit to Git
   - ✅ Use AWS Secrets Manager for production

2. **Key rotation:**
   - Rotate keys every 90 days
   - Use automated rotation scripts
   - Update all instances simultaneously

3. **Multiple keys:**
   - Each operator can have their own key
   - Add all public keys to `authorized_keys`
   - Revoke keys when operators leave

4. **Alternative: Use SSM:**
   - No keys needed
   - Better audit trail
   - More secure (no open ports)

---

## Summary

**Current Answer:**
- ✅ **One key pair** for all Linux instances
- ✅ **Same key** works for C2 servers and proxies
- ✅ **Copy key to jump box** WSL2 after deployment
- ✅ **SSH from WSL2** to any instance

**Automation Options:**
- ✅ **User data scripts** - Add keys on launch
- ✅ **Ansible playbooks** - Distribute after deployment
- ✅ **AWS Secrets Manager** - Store keys securely
- ✅ **AWS Systems Manager** - No keys needed (alternative)

**Recommendation:**
- **Quick setup**: One key, manual copy to jump box
- **Production**: Automated key distribution + SSM as backup

The key management can be fully automated if desired!

