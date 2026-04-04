# Automated SSH Key Distribution with Ansible

## Overview

This guide explains how SSH keys are automatically distributed to all Linux instances using Ansible after infrastructure deployment.

## How It Works

### Process Flow

```
1. Infrastructure Deployed (Terraform)
   ↓
2. Generate Ansible Inventory (from Terraform outputs)
   ↓
3. Generate SSH Key on Jump Box (if needed)
   ↓
4. Distribute Public Key to All Instances (Ansible)
   ↓
5. SSH Access Ready!
```

## Quick Start

### After Infrastructure Deployment

1. **Generate Ansible inventory:**
   ```bash
   ./scripts/utilities/generate-inventory.sh
   ```

2. **Setup and distribute SSH keys:**
   ```bash
   ./scripts/utilities/setup-ssh-keys.sh
   ```

That's it! The script will:
- Generate SSH key on jump box (if needed)
- Distribute public key to all C2 servers and proxies
- Test connectivity

## Manual Process

### Step 1: Generate Ansible Inventory

```bash
cd Red_Team_Infra
./scripts/utilities/generate-inventory.sh
```

This creates `ansible/inventory/hosts.yml` from Terraform outputs.

### Step 2: Generate SSH Key (If Needed)

**On jump box (WSL2):**
```bash
# Generate key
ssh-keygen -t rsa -b 4096 -f ~/.ssh/red-team-jumpbox-key -N ""

# View public key
cat ~/.ssh/red-team-jumpbox-key.pub
```

### Step 3: Distribute Keys via Ansible

**From jump box (WSL2) or any machine with Ansible:**
```bash
cd Red_Team_Infra/ansible

# Set public key path
export SSH_PUBLIC_KEY_FILE=~/.ssh/red-team-jumpbox-key.pub

# Run playbook
ansible-playbook -i inventory/hosts.yml playbooks/distribute-ssh-keys.yml
```

## Automated Script

### Using the Setup Script

The `setup-ssh-keys.sh` script automates everything:

```bash
./scripts/utilities/setup-ssh-keys.sh
```

**What it does:**
1. ✅ Checks prerequisites (Ansible, jq, ssh-keygen)
2. ✅ Generates Ansible inventory (if needed)
3. ✅ Generates SSH key (if doesn't exist)
4. ✅ Distributes keys to all instances
5. ✅ Tests SSH connectivity

## Ansible Playbook Details

### Playbook: `distribute-ssh-keys.yml`

**Location:** `ansible/playbooks/distribute-ssh-keys.yml`

**Features:**
- ✅ Adds SSH public key to `authorized_keys`
- ✅ Supports single or multiple keys
- ✅ Sets correct permissions
- ✅ Works for all Linux instances

**Usage:**
```bash
# Single key from file
ansible-playbook -i inventory/hosts.yml playbooks/distribute-ssh-keys.yml \
    -e "ssh_public_key_file=~/.ssh/id_rsa.pub"

# Single key from content
ansible-playbook -i inventory/hosts.yml playbooks/distribute-ssh-keys.yml \
    -e "ssh_public_key_content='ssh-rsa AAAAB3NzaC1yc2E...'"

# Multiple keys (comma-separated files)
ansible-playbook -i inventory/hosts.yml playbooks/distribute-ssh-keys.yml \
    -e "ssh_public_keys=~/.ssh/key1.pub,~/.ssh/key2.pub"
```

## Inventory Generation

### Automatic Generation

The `generate-inventory.sh` script creates inventory from Terraform outputs:

```bash
./scripts/utilities/generate-inventory.sh
```

**Generated inventory structure:**
```yaml
all:
  children:
    c2_team_servers:
      hosts:
        c2-server-1:
          ansible_host: 10.0.10.5
          ansible_user: ec2-user
        c2-server-2:
          ansible_host: 10.0.11.5
          ansible_user: ec2-user
    
    proxy_redirectors:
      hosts:
        proxy-1:
          ansible_host: 54.123.45.67
          ansible_user: ec2-user
```

### Manual Inventory

You can also create inventory manually in `ansible/inventory/hosts.yml`.

## Multiple Operators

### Adding Multiple Keys

**Option 1: Multiple keys in one run**
```bash
ansible-playbook -i inventory/hosts.yml playbooks/distribute-ssh-keys.yml \
    -e "ssh_public_keys=~/.ssh/operator1.pub,~/.ssh/operator2.pub,~/.ssh/operator3.pub"
```

**Option 2: Run playbook multiple times**
```bash
# Add operator 1's key
ansible-playbook -i inventory/hosts.yml playbooks/distribute-ssh-keys.yml \
    -e "ssh_public_key_file=~/.ssh/operator1.pub"

# Add operator 2's key
ansible-playbook -i inventory/hosts.yml playbooks/distribute-ssh-keys.yml \
    -e "ssh_public_key_file=~/.ssh/operator2.pub"
```

**Option 3: Collect all public keys first**
```bash
# Collect all public keys
cat ~/.ssh/operator1.pub ~/.ssh/operator2.pub > /tmp/all-keys.pub

# Distribute
ansible-playbook -i inventory/hosts.yml playbooks/distribute-ssh-keys.yml \
    -e "ssh_public_key_file=/tmp/all-keys.pub"
```

## From Jump Box (WSL2)

### Complete Workflow

1. **RDP to jump box:**
   ```bash
   mstsc /v:bastion-public-ip
   ```

2. **Open WSL2:**
   ```powershell
   wsl
   ```

3. **Clone or copy project to WSL2:**
   ```bash
   # If project is on Windows, access via /mnt/c/
   cd /mnt/c/Users/Administrator/Desktop/Red_Team_Infra
   
   # Or clone from GitHub
   git clone https://github.com/your-org/Red_Team_Infra.git
   cd Red_Team_Infra
   ```

4. **Generate and distribute keys:**
   ```bash
   ./scripts/utilities/setup-ssh-keys.sh
   ```

5. **SSH to C2 servers:**
   ```bash
   # Now you can SSH without specifying key (if using SSH config)
   ssh ec2-user@c2-server-1-private-ip
   ```

## SSH Config Setup

### Create SSH Config for Easy Access

**On jump box WSL2:**
```bash
cat >> ~/.ssh/config << 'EOF'
Host c2-*
    User ec2-user
    IdentityFile ~/.ssh/red-team-jumpbox-key
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null

Host c2-server-1
    HostName 10.0.10.5

Host c2-server-2
    HostName 10.0.11.5

Host proxy-1
    HostName 54.123.45.67
    User ec2-user
    IdentityFile ~/.ssh/red-team-jumpbox-key
EOF

chmod 600 ~/.ssh/config
```

**Then SSH easily:**
```bash
ssh c2-server-1
ssh c2-server-2
ssh proxy-1
```

## Integration with Deployment

### Automatic Key Distribution

The deployment script now includes a note about key distribution:

```bash
./scripts/deployment/deploy.sh
# After deployment, you'll see:
# "To distribute SSH keys automatically, run:"
# "  ./scripts/utilities/setup-ssh-keys.sh"
```

### Full Automated Workflow

1. **Deploy infrastructure:**
   ```bash
   ./scripts/deployment/deploy.sh
   ```

2. **Distribute SSH keys:**
   ```bash
   ./scripts/utilities/setup-ssh-keys.sh
   ```

3. **Access instances:**
   ```bash
   ssh c2-server-1  # Using SSH config
   ```

## Verification

### Test Connectivity

**Using Ansible:**
```bash
cd ansible
ansible all -i inventory/hosts.yml -m ping
```

**Using SSH directly:**
```bash
# Test C2 server
ssh -i ~/.ssh/red-team-jumpbox-key ec2-user@c2-private-ip "echo 'Connected!'"

# Test proxy
ssh -i ~/.ssh/red-team-jumpbox-key ec2-user@proxy-public-ip "echo 'Connected!'"
```

## Troubleshooting

### Issue: "Permission denied (publickey)"

**Causes:**
- Key not distributed yet
- Wrong key file
- Wrong user

**Solutions:**
1. Run key distribution playbook:
   ```bash
   ansible-playbook -i inventory/hosts.yml playbooks/distribute-ssh-keys.yml
   ```

2. Verify key exists:
   ```bash
   cat ~/.ssh/red-team-jumpbox-key.pub
   ```

3. Check user:
   ```bash
   # Amazon Linux uses 'ec2-user'
   ansible-playbook -i inventory/hosts.yml playbooks/distribute-ssh-keys.yml \
       -e "ssh_user=ec2-user"
   ```

### Issue: "Host key verification failed"

**Solution:**
```bash
# Remove known_hosts entry
ssh-keygen -R <instance-ip>

# Or use Ansible with host_key_checking disabled (already in ansible.cfg)
```

### Issue: "Cannot connect to instances"

**Check:**
1. Security groups allow SSH from jump box
2. Instances are running
3. Network connectivity

**Test:**
```bash
# Ping test
ansible all -i inventory/hosts.yml -m ping

# Check specific host
ansible c2-server-1 -i inventory/hosts.yml -m ping -vvv
```

## Security Considerations

### Key Storage

- ✅ **Private keys**: Only on jump box (WSL2)
- ✅ **Permissions**: `600` (owner read/write only)
- ✅ **Never commit**: Keys in `.gitignore`
- ✅ **Rotation**: Rotate keys every 90 days

### Key Distribution

- ✅ **Public keys only**: Only public keys distributed
- ✅ **Ansible encryption**: Ansible uses SSH (encrypted)
- ✅ **Audit trail**: Ansible logs show key distribution

### Best Practices

1. **Use separate keys per operator** (if multiple operators)
2. **Rotate keys regularly** (automated rotation possible)
3. **Revoke keys** when operators leave
4. **Monitor access** via CloudTrail (if using SSM)

## Advanced: Key Rotation

### Rotate Keys Automatically

```bash
#!/bin/bash
# rotate-keys.sh

# Generate new key
ssh-keygen -t rsa -b 4096 -f ~/.ssh/red-team-jumpbox-key-new -N ""

# Distribute new key
ansible-playbook -i inventory/hosts.yml playbooks/distribute-ssh-keys.yml \
    -e "ssh_public_key_file=~/.ssh/red-team-jumpbox-key-new.pub"

# Test new key
ansible all -i inventory/hosts.yml -m ping

# If successful, replace old key
mv ~/.ssh/red-team-jumpbox-key ~/.ssh/red-team-jumpbox-key-old
mv ~/.ssh/red-team-jumpbox-key-new ~/.ssh/red-team-jumpbox-key
mv ~/.ssh/red-team-jumpbox-key-new.pub ~/.ssh/red-team-jumpbox-key.pub

# Remove old key from instances (optional)
# ansible all -i inventory/hosts.yml -m authorized_key \
#     -a "user=ec2-user key='$(cat ~/.ssh/red-team-jumpbox-key-old.pub)' state=absent"
```

## Server Mode SSH Keys

When running the dashboard in server mode, SSH key management works differently from the local/Ansible approach described above. The dashboard server has its own keypair and uses SSM to distribute it — no Ansible required.

### How It Works

- The dashboard server generates its own Ed25519 keypair at `/opt/redteam/.ssh/id_ed25519` during initial setup
- The public key is pushed to all deployed instances via AWS SSM (`AWS-RunShellScript` / `AWS-RunPowerShellScript`), adding it to each instance's `authorized_keys`
- The operator's private key **never leaves their laptop** — it is only used to SSH into the dashboard server itself
- The dashboard's Terminal tab uses the server's keypair to provide in-browser SSH access to all infrastructure instances (team servers, redirectors, bastion, jumpbox)
- The server keypair is separate from any operator keys or the AWS EC2 key pair used at launch

### Migrated Deployments

If infrastructure was originally deployed in local mode and later migrated to server mode, the server's public key must be added to existing instances after the fact:

```bash
# The setup script handles this automatically via SSM:
# For each instance, it runs:
aws ssm send-command --instance-ids <id> --region <region> \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["echo \"<server-public-key>\" >> /home/ubuntu/.ssh/authorized_keys"]'
```

This means the server can SSH to all instances without the operator needing to distribute keys manually or run Ansible playbooks.

### Key Differences: Local vs Server Mode

| Aspect | Local Mode | Server Mode |
|--------|-----------|-------------|
| Key generation | Jump box or operator laptop | Dashboard server (`/opt/redteam/.ssh/`) |
| Distribution method | Ansible playbook | AWS SSM (no Ansible needed) |
| Operator private key | On laptop, used for SSH | On laptop, used only to reach dashboard |
| Instance access | SSH from jump box / bastion | Terminal tab in browser (via server keypair) |

## Summary

✅ **Automated SSH key distribution** via Ansible (local mode) or SSM (server mode)
✅ **One script** handles everything: `setup-ssh-keys.sh` (local) or `setup-dashboard.sh` (server)
✅ **Multiple keys supported** for multiple operators
✅ **Works from jump box** (WSL2) or any machine
✅ **Easy to use** - just run the script after deployment

**Workflow (Local Mode):**
1. Deploy infrastructure
2. Run `setup-ssh-keys.sh`
3. SSH to any instance easily!

**Workflow (Server Mode):**
1. Deploy infrastructure from dashboard
2. Server keypair is auto-distributed via SSM
3. Use Terminal tab for in-browser SSH to any instance

