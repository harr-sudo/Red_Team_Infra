# Cobalt Strike Deployment Automation

## Overview

Yes, it's **absolutely possible** to automate Cobalt Strike deployment. This document explains how to do it and what you need.

## Requirements

### What You Need

1. **Cobalt Strike License** - Valid license from HelpSystems/Rapid7
2. **Cobalt Strike Files** - The actual Cobalt Strike distribution:
   - `teamserver` (Linux executable)
   - `c2lint` (validation tool)
   - `cobaltstrike.jar` (main JAR file)
   - `agscript` (automation script runner)
   - Other supporting files
3. **Java Runtime** - Java 11 or later (required for Cobalt Strike)
4. **Configuration Files** - Teamserver config, profiles, listeners

### What You DON'T Need in Code

- ❌ **Actual Cobalt Strike binaries** - Cannot be stored in Git (licensing/legal)
- ❌ **License keys** - Should be stored securely (AWS Secrets Manager, etc.)

## Deployment Approaches

### Approach 1: Ansible Playbook (Recommended)

**How it works:**
- Ansible playbook installs Java, copies files, configures teamserver
- Cobalt Strike files stored separately (S3, secure location)
- Playbook retrieves files and deploys

**Pros:**
- ✅ Idempotent (can run multiple times safely)
- ✅ Version controlled (playbook, not binaries)
- ✅ Easy to update configuration
- ✅ Works with existing infrastructure

**Cons:**
- ⚠️ Requires Ansible setup
- ⚠️ Need to store files somewhere accessible

### Approach 2: User Data Scripts

**How it works:**
- EC2 user data script runs on instance launch
- Downloads Cobalt Strike from S3/secure location
- Installs and configures automatically

**Pros:**
- ✅ Automatic on instance creation
- ✅ No manual steps
- ✅ Works with Terraform

**Cons:**
- ⚠️ Harder to update after deployment
- ⚠️ Limited error handling
- ⚠️ User data has size limits

### Approach 3: Hybrid (User Data + Ansible)

**How it works:**
- User data installs prerequisites (Java, etc.)
- Ansible playbook handles Cobalt Strike deployment
- Best of both worlds

**Pros:**
- ✅ Fast initial setup
- ✅ Easy updates via Ansible
- ✅ Flexible configuration

**Cons:**
- ⚠️ More complex setup

## Detailed Implementation Options

### Option 1: Ansible Playbook with S3 Storage

**Architecture:**
```
S3 Bucket (encrypted)
  └── cobalt-strike/
      ├── teamserver
      ├── cobaltstrike.jar
      └── profiles/
          └── profile.profile

Ansible Playbook
  ├── Downloads from S3
  ├── Installs Java
  ├── Configures teamserver
  └── Starts service
```

**Steps:**
1. **Store Cobalt Strike in S3:**
   ```bash
   # Upload to encrypted S3 bucket
   aws s3 cp cobalt-strike.tar.gz s3://red-team-artifacts/cobalt-strike.tar.gz \
       --sse aws:kms --sse-kms-key-id <kms-key-id>
   ```

2. **Ansible Playbook:**
   ```yaml
   - name: Install Java
     yum:
       name: java-11-openjdk
       state: present
   
   - name: Download Cobalt Strike from S3
     aws_s3:
       bucket: red-team-artifacts
       object: cobalt-strike.tar.gz
       dest: /tmp/cobalt-strike.tar.gz
       mode: get
   
   - name: Extract Cobalt Strike
     unarchive:
       src: /tmp/cobalt-strike.tar.gz
       dest: /opt/
       remote_src: yes
   
   - name: Configure teamserver
     template:
       src: teamserver.conf.j2
       dest: /opt/cobaltstrike/teamserver.conf
   
   - name: Start teamserver service
     systemd:
       name: teamserver
       enabled: yes
       state: started
   ```

### Option 2: User Data Script with S3

**Terraform Configuration:**
```hcl
c2_server_user_data = <<-EOF
  #!/bin/bash
  # Install Java
  yum install -y java-11-openjdk
  
  # Download Cobalt Strike from S3
  aws s3 cp s3://red-team-artifacts/cobalt-strike.tar.gz /tmp/
  
  # Extract
  tar -xzf /tmp/cobalt-strike.tar.gz -C /opt/
  
  # Configure
  cat > /opt/cobaltstrike/teamserver.conf << EOL
  # Teamserver configuration
  EOL
  
  # Start service
  systemctl enable teamserver
  systemctl start teamserver
EOF
```

### Option 3: Secure File Transfer (SCP/SFTP)

**How it works:**
- Store Cobalt Strike files on jump box or secure server
- Ansible playbook uses `synchronize` or `copy` module
- Transfers files securely via SSH

**Ansible Playbook:**
```yaml
- name: Copy Cobalt Strike files
  synchronize:
    src: /secure/path/cobalt-strike/
    dest: /opt/cobaltstrike/
    mode: pull
    delete: no
```

### Option 4: AWS Systems Manager Parameter Store / Secrets Manager

**How it works:**
- Store Cobalt Strike as base64-encoded archive in Secrets Manager
- Ansible retrieves and decodes
- More secure than S3 (fine-grained access control)

**Ansible Playbook:**
```yaml
- name: Get Cobalt Strike from Secrets Manager
  aws_secretsmanager:
    name: red-team/cobalt-strike-archive
    secret_type: binary
  register: cs_secret

- name: Decode and extract
  unarchive:
    src: "{{ cs_secret.secret_binary | b64decode }}"
    dest: /opt/
```

## What Files You Need

### Cobalt Strike Distribution

**Required files:**
- `teamserver` - Main teamserver executable
- `cobaltstrike.jar` - Core JAR file
- `c2lint` - Profile validation tool
- `agscript` - Automation scripting tool
- `update` - Update utility
- `cobaltstrike.auth` - License file (if using file-based auth)

**Optional but recommended:**
- `profiles/` - Malleable C2 profiles
- `scripts/` - Aggressor scripts
- `logs/` - Logging configuration

### Configuration Files

**Teamserver configuration:**
- Hostname/IP
- Port (default: 50050)
- Password
- License key (or auth file)
- Profile selection

**Malleable C2 profiles:**
- HTTP/HTTPS profiles
- DNS profiles
- Custom profiles

## Security Considerations

### File Storage

**Options (from most to least secure):**
1. **AWS Secrets Manager** - Encrypted, access controlled
2. **S3 with KMS encryption** - Encrypted at rest
3. **Encrypted S3 bucket** - Server-side encryption
4. **Jump box storage** - Local encrypted storage
5. **❌ Never in Git** - Cannot commit binaries

### Access Control

- ✅ Use IAM roles for S3/Secrets Manager access
- ✅ Restrict access to red team operators only
- ✅ Enable CloudTrail logging
- ✅ Use separate AWS account if possible

### License Management

- ✅ Store license keys in Secrets Manager
- ✅ Use IAM authentication (preferred over file-based)
- ✅ Rotate credentials regularly

## Implementation Example

### Complete Ansible Playbook Structure

```
ansible/
├── playbooks/
│   └── deploy-cobalt-strike.yml
├── roles/
│   └── cobalt-strike/
│       ├── tasks/
│       │   └── main.yml
│       ├── templates/
│       │   ├── teamserver.service.j2
│       │   └── teamserver.conf.j2
│       └── vars/
│           └── main.yml
└── files/
    └── (no Cobalt Strike files - stored externally)
```

### Playbook Tasks

**Main tasks:**
1. Install Java 11
2. Create Cobalt Strike directory
3. Download from S3/Secrets Manager
4. Extract files
5. Set permissions
6. Configure teamserver
7. Create systemd service
8. Start and enable service
9. Configure firewall rules
10. Verify deployment

## Deployment Workflow

### Step-by-Step Process

1. **Prepare Cobalt Strike:**
   ```bash
   # Package Cobalt Strike
   tar -czf cobalt-strike.tar.gz cobaltstrike/
   
   # Upload to secure storage
   aws s3 cp cobalt-strike.tar.gz s3://red-team-artifacts/ \
       --sse aws:kms
   ```

2. **Configure Ansible:**
   ```yaml
   # ansible/group_vars/c2_team_servers.yml
   cobalt_strike:
     s3_bucket: red-team-artifacts
     s3_key: cobalt-strike.tar.gz
     install_path: /opt/cobaltstrike
     teamserver_port: 50050
     teamserver_password: "{{ vault_cs_password }}"
   ```

3. **Run Deployment:**
   ```bash
   # Deploy infrastructure
   ./scripts/deployment/deploy.sh
   
   # Deploy Cobalt Strike
   ansible-playbook -i inventory/hosts.yml \
       playbooks/deploy-cobalt-strike.yml
   ```

## Alternative: Pre-built AMI

### Custom AMI Approach

**How it works:**
- Create custom AMI with Cobalt Strike pre-installed
- Use AMI ID in Terraform configuration
- Faster deployment (no installation step)

**Pros:**
- ✅ Fastest deployment
- ✅ No download step needed
- ✅ Consistent configuration

**Cons:**
- ⚠️ AMI contains licensed software (compliance considerations)
- ⚠️ Harder to update
- ⚠️ Larger AMI size

## Automation Scripts

### Deployment Script

```bash
#!/bin/bash
# deploy-cobalt-strike.sh

# 1. Upload Cobalt Strike to S3 (if not already there)
aws s3 cp cobalt-strike.tar.gz s3://red-team-artifacts/ \
    --sse aws:kms

# 2. Run Ansible playbook
ansible-playbook -i ansible/inventory/hosts.yml \
    ansible/playbooks/deploy-cobalt-strike.yml \
    --vault-password-file ~/.ansible-vault-pass

# 3. Verify deployment
ansible c2_team_servers -i ansible/inventory/hosts.yml \
    -m shell -a "systemctl status teamserver"
```

## Configuration Management

### Teamserver Configuration

**Template file:**
```ini
# teamserver.conf.j2
TEAMSERVER_HOST={{ ansible_default_ipv4.address }}
TEAMSERVER_PORT={{ teamserver_port | default(50050) }}
TEAMSERVER_PASSWORD={{ vault_teamserver_password }}
COBALTSTRIKE_PROFILE={{ cs_profile | default('jquery') }}
```

### Systemd Service

**Service file:**
```ini
[Unit]
Description=Cobalt Strike Teamserver
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/opt/cobaltstrike
ExecStart=/opt/cobaltstrike/teamserver {{ teamserver_host }} {{ teamserver_password }} {{ profile_path }}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Updating Cobalt Strike

### Update Process

1. **Download new version** to secure storage
2. **Run Ansible playbook** with update flag
3. **Restart teamserver** service
4. **Verify** deployment

**Ansible playbook:**
```yaml
- name: Update Cobalt Strike
  when: update_cs | default(false)
  # Download new version
  # Backup current version
  # Extract new version
  # Restart service
```

## Integration with Existing Infrastructure

### Using Existing Ansible Setup

**After infrastructure deployment:**
```bash
# 1. Infrastructure is deployed
./scripts/deployment/deploy.sh

# 2. SSH keys are distributed
./scripts/utilities/setup-ssh-keys.sh

# 3. Deploy Cobalt Strike
ansible-playbook -i ansible/inventory/hosts.yml \
    ansible/playbooks/deploy-cobalt-strike.yml
```

### Phase-Based Deployment

**For phases mode:**
- Deploy different profiles per phase
- Staging: Testing profile
- Post-ex: Post-exploitation profile
- Long-haul: Long-term profile

**Ansible inventory groups:**
```yaml
c2_team_servers:
  children:
    staging_servers:
      hosts:
        c2-staging-server:
          cs_profile: staging.profile
    post_ex_servers:
      hosts:
        c2-post-ex-server:
          cs_profile: post-ex.profile
```

## Legal and Compliance

### Important Considerations

1. **License Compliance:**
   - ✅ Valid Cobalt Strike license required
   - ✅ Cannot redistribute binaries
   - ✅ Store files securely (not in public repos)

2. **Authorized Use:**
   - ✅ Only deploy for authorized engagements
   - ✅ Follow engagement scope
   - ✅ Document deployments

3. **Storage:**
   - ✅ Encrypt at rest
   - ✅ Control access (IAM)
   - ✅ Audit access (CloudTrail)

## Summary

### Yes, It's Possible!

**What you need:**
- ✅ Cobalt Strike license
- ✅ Cobalt Strike files (stored securely, not in Git)
- ✅ Java runtime
- ✅ Configuration files

**How to automate:**
1. **Store files** in S3/Secrets Manager (encrypted)
2. **Use Ansible** to download, install, configure
3. **Or use user data** for automatic deployment
4. **Or create custom AMI** with pre-installed CS

**Best approach:**
- **Ansible playbook** with S3/Secrets Manager storage
- **Idempotent** deployment (can run multiple times)
- **Version controlled** (playbook, not binaries)
- **Easy updates** and configuration changes

**The automation handles:**
- Java installation
- File download/extraction
- Configuration
- Service setup
- Firewall rules
- Verification

**You just need to:**
- Provide Cobalt Strike files (store securely)
- Configure playbook variables
- Run the playbook

The infrastructure is ready - you just need to add the Cobalt Strike deployment automation!

