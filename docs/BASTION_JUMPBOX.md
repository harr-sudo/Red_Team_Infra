# Bastion/Jump Box - Windows Server with WSL2

## Overview

The infrastructure includes a **dedicated Windows Server jump box (bastion host)** with **WSL2 (Ubuntu)** for easy management access to C2 servers.

## Why Windows Server with WSL2?

### Benefits

1. **RDP Access** - Familiar Windows Remote Desktop for management
2. **WSL2 Ubuntu** - Linux environment for SSH access to C2 servers
3. **Best of Both Worlds** - Windows GUI + Linux command line
4. **Dedicated Access** - Separated from operational infrastructure
5. **Easy Setup** - Automated WSL2 installation via user data script

## Architecture

```
Home (RDP) → Bastion (Windows Server, Public Subnet)
                ↓
            WSL2 (Ubuntu)
                ↓
            SSH → C2 Servers (Private Subnets)
```

## Configuration

### Enable/Disable

In `terraform.tfvars`:
```hcl
enable_bastion = true  # Set to false to disable
```

### Instance Specifications

| Property | Default | Configurable |
|----------|---------|--------------|
| **OS** | Windows Server 2022 | Yes (`bastion_ami_id`) |
| **Instance Type** | `t3.medium` | Yes (`bastion_instance_type`) |
| **vCPU** | 2 | Based on instance type |
| **RAM** | 4 GB | Based on instance type |
| **Storage** | 30 GB | Yes (`bastion_root_volume_size`) |
| **Elastic IP** | Always enabled | Automatic |
| **WSL2** | Enabled | Automatic via user data |

### Windows Password

**Option 1: Retrieve from AWS (Recommended)**
```hcl
windows_admin_password = ""  # Leave empty
```

After deployment, retrieve password:
```bash
aws ec2 get-password-data \
    --instance-id i-1234567890abcdef0 \
    --priv-launch-key ~/.ssh/key.pem
```

**Option 2: Set Custom Password**
```hcl
windows_admin_password = "YourSecurePassword123!"
```

⚠️ **Security Note**: If setting password, use AWS Secrets Manager or environment variables, not plain text in files.

## Access Methods

### 1. RDP Access (Windows Management)

**From Windows:**
```bash
mstsc /v:bastion-public-ip
```

**From Mac/Linux:**
- Use Microsoft Remote Desktop app
- Or use `rdesktop` or `xfreerdp`

**Connection Details:**
- **Server**: `bastion-public-ip` (from Terraform outputs)
- **Username**: `Administrator`
- **Password**: Retrieved from AWS or set in variables

### 2. SSH Access via WSL2 (Linux Environment)

**After RDP into bastion:**

1. **Open PowerShell** (as Administrator)
2. **Launch WSL2:**
   ```powershell
   wsl
   ```
3. **First time setup** (if needed):
   ```bash
   # Create user account (first time only)
   # Follow prompts to set username and password
   ```

4. **SSH to C2 servers:**
   ```bash
   # From WSL2 Ubuntu
   ssh ec2-user@private-c2-ip -i /mnt/c/path/to/key.pem
   ```

### 3. SSH Tunnel for C2 Client Access

**From WSL2 on bastion:**
```bash
# Create SSH tunnel
ssh -L 50050:private-c2-ip:50050 ec2-user@private-c2-ip -i key.pem

# Then connect C2 client to localhost:50050
```

**Or from home through bastion:**
```bash
# SSH tunnel through bastion
ssh -L 50050:private-c2-ip:50050 Administrator@bastion-public-ip

# Then in RDP session, use WSL2 to connect
```

## WSL2 Setup

### Automatic Installation

The user data script automatically:
- ✅ Enables WSL feature
- ✅ Enables Virtual Machine Platform
- ✅ Installs WSL2 kernel update
- ✅ Sets WSL2 as default version
- ✅ Attempts to install Ubuntu (may need manual step)

### Manual Steps (If Needed)

**If Ubuntu doesn't auto-install:**

1. **Open PowerShell as Administrator**
2. **Install Ubuntu:**
   ```powershell
   wsl --install -d Ubuntu
   ```
3. **Or use winget:**
   ```powershell
   winget install Canonical.Ubuntu.2204.LTS
   ```

### First Time WSL2 Setup

1. **Launch WSL2:**
   ```powershell
   wsl
   ```

2. **Create user account** (follow prompts)

3. **Update system:**
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

4. **Install SSH client** (if not already installed):
   ```bash
   sudo apt install openssh-client -y
   ```

5. **Copy SSH keys** (from Windows to WSL2):
   ```bash
   # Keys in Windows: C:\Users\Administrator\.ssh\
   # Access from WSL2: /mnt/c/Users/Administrator/.ssh/
   cp /mnt/c/Users/Administrator/.ssh/key.pem ~/.ssh/
   chmod 600 ~/.ssh/key.pem
   ```

## Security Configuration

### Security Group Rules

**Inbound:**
- **RDP (3389)**: From management CIDR blocks only
- **SSH (22)**: From management CIDR blocks only (for OpenSSH server)

**Outbound:**
- **All traffic**: Allowed (for SSH to C2 servers, internet access, etc.)

### C2 Server Access

C2 servers allow SSH from:
- ✅ Bastion security group (primary method)
- ✅ Management CIDR blocks (fallback)

This means you can SSH from WSL2 on bastion directly to C2 servers!

## Usage Workflow

### Daily Access Pattern

1. **RDP to bastion** from home
   ```
   mstsc /v:bastion-public-ip
   ```

2. **Open WSL2** in RDP session
   ```powershell
   wsl
   ```

3. **SSH to C2 servers** from WSL2
   ```bash
   ssh ec2-user@c2-private-ip -i ~/.ssh/key.pem
   ```

4. **Or create SSH tunnel** for C2 client
   ```bash
   ssh -L 50050:c2-private-ip:50050 ec2-user@c2-private-ip -i ~/.ssh/key.pem
   ```

### C2 Client Access

**Option 1: Through Bastion WSL2**
- RDP to bastion
- Open WSL2
- Create SSH tunnel
- Connect C2 client to `localhost:50050`

**Option 2: Port Forward Through RDP**
- RDP to bastion with port forwarding
- Use WSL2 to create tunnel
- Connect from home machine

## Cost

**Monthly Cost (24/7):**
- **t3.medium Windows Server**: ~$30/month
- **30 GB EBS storage**: ~$2.40/month
- **Elastic IP**: Free (if attached)
- **Total**: ~$32-35/month

## Advantages Over Proxy/Redirector Access

| Feature | Bastion | Proxy/Redirector |
|---------|---------|------------------|
| **Purpose** | Management access | Operational traffic |
| **OS** | Windows Server | Linux |
| **RDP** | ✅ Yes | ❌ No |
| **WSL2** | ✅ Yes | ❌ No |
| **SSH** | ✅ Via WSL2 | ✅ Direct |
| **Separation** | ✅ Dedicated | ⚠️ Shared with ops |
| **Security** | ✅ Isolated | ⚠️ Mixed purpose |

## Troubleshooting

### WSL2 Not Working

**Check WSL status:**
```powershell
wsl --status
```

**Reinstall WSL2:**
```powershell
wsl --unregister Ubuntu
wsl --install -d Ubuntu
```

### Can't SSH to C2 Servers

**Check security groups:**
- C2 servers must allow SSH from bastion security group
- Verify bastion security group ID is in C2 server ingress rules

**Test connectivity:**
```bash
# From WSL2
ping c2-private-ip
telnet c2-private-ip 22
```

### RDP Connection Issues

**Check Windows Firewall:**
- RDP port (3389) should be open
- Security group must allow RDP from your IP

**Verify password:**
```bash
aws ec2 get-password-data --instance-id i-xxx --priv-launch-key key.pem
```

## Terraform Outputs

After deployment, get connection info:

```bash
terraform output bastion_public_ip
terraform output bastion_rdp_connection
terraform output bastion_wsl2_info
```

## Summary

✅ **Windows Server jump box** with WSL2 provides:
- RDP for Windows management
- WSL2 Ubuntu for Linux/SSH access
- Dedicated, secure access point
- Easy SSH to C2 servers
- Clean separation from operational infrastructure

**Perfect for operators who want:**
- Familiar Windows environment
- Linux command-line tools
- Easy access to C2 infrastructure
- Professional management setup

