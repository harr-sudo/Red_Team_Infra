# Tools Repository Integration Plan

## Overview

Create a centralized tools repository that is automatically deployed to infrastructure and accessible to operators from their home laptops.

## Goals

1. **Centralized Tool Storage**: Single source of truth for all red team tools
2. **Automated Deployment**: Tools automatically downloaded during infrastructure deployment
3. **Easy Access**: Operators can access tools from home laptops
4. **Version Control**: Track tool updates and changes
5. **Security**: Private repository with controlled access

## Architecture

### Repository Structure

```
red-team-tools/                    # Private Git repository
├── README.md                       # Tool documentation
├── .gitignore                      # Exclude binaries, sensitive files
├── tools/                          # Organized tool directories
│   ├── c2/                         # C2 frameworks
│   │   ├── cobalt-strike/
│   │   ├── empire/
│   │   └── ...
│   ├── post-exploitation/          # Post-exploitation tools
│   │   ├── mimikatz/
│   │   ├── bloodhound/
│   │   └── ...
│   ├── network/                    # Network tools
│   │   ├── nmap/
│   │   ├── wireshark/
│   │   └── ...
│   ├── utilities/                  # Utility scripts
│   │   ├── persistence/
│   │   ├── privilege-escalation/
│   │   └── ...
│   └── custom/                     # Custom tools/scripts
│       ├── scripts/
│       └── payloads/
└── docs/                           # Tool documentation
    ├── installation/
    └── usage/
```

### Deployment Locations

**Option 1: Jump Box Only (Recommended)**
- Clone repository to jump box: `C:\Tools\` (Windows) or `/opt/tools/` (WSL2)
- Operators access via RDP/SSH to jump box
- **Pros**: Centralized, easier to manage, single point of access
- **Cons**: Requires jump box access

**Option 2: Jump Box + C2 Servers**
- Clone to jump box: `C:\Tools\` or `/opt/tools/`
- Clone to C2 servers: `/opt/tools/`
- **Pros**: Tools available on all servers
- **Cons**: More storage, more maintenance

**Option 3: Jump Box + S3 Sync**
- Clone to jump box
- Sync to S3 bucket
- Operators download from S3
- **Pros**: Direct access without jump box
- **Cons**: Additional S3 costs, sync complexity

## Implementation Approach

### Phase 1: Repository Setup

1. **Create Private Git Repository**
   - GitHub/GitLab private repository
   - Initial tool structure
   - Documentation and README

2. **Access Control**
   - Private repository (team access only)
   - SSH keys or personal access tokens for cloning
   - IAM roles for AWS access (if using S3)

### Phase 2: Deployment Integration

**Method A: Ansible Playbook (Recommended)**
- Create Ansible playbook: `ansible/playbooks/deploy-tools-repo.yml`
- Runs after infrastructure deployment
- Clones repository to target hosts
- Handles authentication (SSH keys, tokens)

**Method B: User Data Script**
- Add to EC2 user data
- Clones repository on instance startup
- Requires credentials in user data (less secure)

**Method C: Hybrid Approach**
- User data installs Git and credentials
- Ansible playbook clones and updates repository
- Best of both worlds

### Phase 3: Client Access Methods

**Method 1: Direct Git Clone (Primary)**
- Operators clone repository directly to their laptops
- Requires Git and repository access
- **Command**: `git clone git@github.com:org/red-team-tools.git`
- **Pros**: Direct access, version control, easy updates
- **Cons**: Requires Git setup and credentials

**Method 2: Jump Box Access (Secondary)**
- Operators RDP/SSH to jump box
- Tools available at `C:\Tools\` or `/opt/tools/`
- **Pros**: No local setup needed
- **Cons**: Requires jump box connection

**Method 3: S3 Download (Tertiary)**
- Tools synced to S3 bucket
- Operators download via AWS CLI or web interface
- **Command**: `aws s3 sync s3://red-team-tools/ ./tools/`
- **Pros**: Direct download, no Git needed
- **Cons**: Manual sync, no version control

**Method 4: Web Interface (Optional)**
- Simple web server on jump box
- Browse and download tools via browser
- **Pros**: User-friendly, no CLI needed
- **Cons**: Additional setup, security considerations

## Detailed Implementation

### 1. Repository Configuration

**Terraform Variables** (`terraform/variables.tf`):
```hcl
variable "tools_repo_url" {
  description = "Git repository URL for tools"
  type        = string
  default     = ""
}

variable "tools_repo_branch" {
  description = "Git branch to clone"
  type        = string
  default     = "main"
}

variable "tools_repo_ssh_key" {
  description = "SSH private key for Git access (stored in SSM)"
  type        = string
  default     = ""
}

variable "tools_deployment_location" {
  description = "Where to deploy tools: 'jumpbox', 'all-servers', 'jumpbox-and-servers'"
  type        = string
  default     = "jumpbox"
}
```

**Configuration** (`configs/terraform.tfvars.example`):
```hcl
# Tools Repository Configuration
tools_repo_url = "git@github.com:org/red-team-tools.git"  # Private repo URL
tools_repo_branch = "main"
tools_deployment_location = "jumpbox"  # Options: jumpbox, all-servers, jumpbox-and-servers
```

### 2. Ansible Playbook

**File**: `ansible/playbooks/deploy-tools-repo.yml`

```yaml
---
- name: Deploy Tools Repository
  hosts: "{{ target_hosts | default('bastion') }}"
  become: yes
  vars:
    tools_repo_url: "{{ lookup('env', 'TOOLS_REPO_URL') | default('', true) }}"
    tools_repo_branch: "{{ lookup('env', 'TOOLS_REPO_BRANCH') | default('main', true) }}"
    tools_dir: "{{ 'C:\\Tools' if ansible_os_family == 'Windows' else '/opt/tools' }}"
    tools_ssh_key: "{{ lookup('env', 'TOOLS_REPO_SSH_KEY') | default('', true) }}"
  
  tasks:
    - name: Ensure tools directory exists (Linux)
      file:
        path: "{{ tools_dir }}"
        state: directory
        mode: '0755'
      when: ansible_os_family != 'Windows'
    
    - name: Ensure tools directory exists (Windows)
      win_file:
        path: "{{ tools_dir }}"
        state: directory
      when: ansible_os_family == 'Windows'
    
    - name: Setup SSH key for Git (Linux)
      copy:
        content: "{{ tools_ssh_key }}"
        dest: "~/.ssh/id_rsa_tools"
        mode: '0600'
      when: ansible_os_family != 'Windows' and tools_ssh_key != ''
    
    - name: Setup SSH key for Git (Windows)
      win_copy:
        content: "{{ tools_ssh_key }}"
        dest: "C:\\Users\\Administrator\\.ssh\\id_rsa_tools"
      when: ansible_os_family == 'Windows' and tools_ssh_key != ''
    
    - name: Clone tools repository (Linux)
      git:
        repo: "{{ tools_repo_url }}"
        dest: "{{ tools_dir }}"
        version: "{{ tools_repo_branch }}"
        key_file: "~/.ssh/id_rsa_tools"
        update: yes
      when: ansible_os_family != 'Windows'
    
    - name: Clone tools repository (Windows)
      win_git:
        repo: "{{ tools_repo_url }}"
        dest: "{{ tools_dir }}"
        version: "{{ tools_repo_branch }}"
        update: yes
      when: ansible_os_family == 'Windows'
```

### 3. Deployment Script Integration

**Update**: `scripts/deployment/deploy.sh`

Add after infrastructure deployment:
```bash
# Deploy tools repository
if [ -n "$TOOLS_REPO_URL" ]; then
    log_info "Deploying tools repository..."
    ansible-playbook -i ansible/inventory/hosts.yml \
        ansible/playbooks/deploy-tools-repo.yml \
        -e "target_hosts=${TOOLS_DEPLOYMENT_LOCATION:-bastion}"
fi
```

### 4. Client Access Setup

**Documentation**: `docs/TOOLS_REPOSITORY_ACCESS.md`

**For Direct Git Clone:**
```bash
# Setup SSH key for repository access
ssh-keygen -t ed25519 -C "your-email@example.com" -f ~/.ssh/id_rsa_tools

# Add public key to GitHub/GitLab
cat ~/.ssh/id_rsa_tools.pub

# Clone repository
git clone git@github.com:org/red-team-tools.git ~/tools

# Update tools
cd ~/tools && git pull
```

**For Jump Box Access:**
```bash
# RDP to jump box
# Tools available at: C:\Tools\ (Windows) or /opt/tools/ (WSL2)

# Or SSH to jump box
ssh Administrator@<jump-box-ip>
cd /opt/tools  # In WSL2
```

**For S3 Download:**
```bash
# Configure AWS credentials
aws configure

# Download tools
aws s3 sync s3://red-team-tools/ ~/tools/
```

### 5. S3 Sync (Optional)

**Ansible Playbook**: `ansible/playbooks/sync-tools-to-s3.yml`

```yaml
---
- name: Sync Tools Repository to S3
  hosts: localhost
  vars:
    tools_dir: "/opt/tools"
    s3_bucket: "red-team-tools"
  
  tasks:
    - name: Sync tools to S3
      aws_s3:
        bucket: "{{ s3_bucket }}"
        mode: push
        file_root: "{{ tools_dir }}"
        permission: private
```

## Security Considerations

1. **Repository Access**
   - Private repository only
   - SSH keys or personal access tokens
   - Rotate credentials regularly

2. **Credential Storage**
   - Store SSH keys in AWS Systems Manager Parameter Store
   - Use IAM roles for S3 access
   - Never commit credentials to Git

3. **Access Control**
   - Limit repository access to authorized team members
   - Audit access logs
   - Use branch protection rules

4. **Tool Validation**
   - Verify tool integrity (checksums)
   - Scan for malware before adding
   - Document tool sources

## File Structure

```
Red_Team_Infra/
├── ansible/
│   └── playbooks/
│       ├── deploy-tools-repo.yml      # NEW: Deploy tools repository
│       └── sync-tools-to-s3.yml       # NEW: Sync to S3 (optional)
├── docs/
│   ├── TOOLS_REPOSITORY_PLAN.md       # This file
│   └── TOOLS_REPOSITORY_ACCESS.md     # NEW: Client access guide
├── terraform/
│   └── variables.tf                   # UPDATE: Add tools repo variables
└── configs/
    └── terraform.tfvars.example       # UPDATE: Add tools repo config
```

## Implementation Steps

### Step 1: Create Tools Repository
1. Create private GitHub/GitLab repository
2. Set up initial structure
3. Add initial tools and documentation
4. Configure access control

### Step 2: Add Terraform Variables
1. Add tools repository variables to `terraform/variables.tf`
2. Update `configs/terraform.tfvars.example`
3. Add variables to Terraform modules if needed

### Step 3: Create Ansible Playbook
1. Create `ansible/playbooks/deploy-tools-repo.yml`
2. Support both Windows (jump box) and Linux (C2 servers)
3. Handle authentication (SSH keys, tokens)

### Step 4: Integrate with Deployment
1. Update `scripts/deployment/deploy.sh`
2. Add tools deployment step
3. Update `scripts/utilities/generate-inventory.sh` if needed

### Step 5: Create Documentation
1. Create `docs/TOOLS_REPOSITORY_ACCESS.md`
2. Document all access methods
3. Add to README.md

### Step 6: Optional Enhancements
1. S3 sync playbook (if using S3)
2. Web interface on jump box (if needed)
3. Automated tool updates (cron job)

## Recommended Approach

**Primary Method**: Direct Git Clone
- Operators clone repository to their laptops
- Easy updates with `git pull`
- Full version control

**Secondary Method**: Jump Box Access
- Tools available on jump box
- Access via RDP/SSH
- No local setup needed

**Deployment**: Ansible Playbook
- Runs after infrastructure deployment
- Clones to jump box (and optionally C2 servers)
- Handles authentication securely

## Next Steps

1. **Review and approve plan**
2. **Create tools repository** (separate repo)
3. **Implement Terraform variables**
4. **Create Ansible playbook**
5. **Integrate with deployment**
6. **Test and document**

## Questions to Consider

1. **Repository Location**: GitHub, GitLab, or self-hosted?
2. **Deployment Scope**: Jump box only, or all servers?
3. **Access Method**: Direct Git clone, jump box, S3, or all?
4. **Tool Updates**: Manual or automated?
5. **Security**: How to handle sensitive tools?

