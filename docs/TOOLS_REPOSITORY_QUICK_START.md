# Tools Repository Quick Start

## Repository Created! ✅

The tools repository has been created at:
**https://github.com/harr-sudo/red-team-tools**

## Next Steps

### 1. Set Up Authentication (Choose One Method)

#### Option A: Personal Access Token (Recommended for Multiple Users)

Each team member creates their own PAT:

```bash
# 1. Create PAT on GitHub:
#    GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
#    - Name: "Red Team Tools Access"
#    - Scopes: repo (full control)
#    - Copy the token (ghp_...)

# 2. Set in terraform.tfvars:
#    tools_repo_url         = "https://github.com/harr-sudo/red-team-tools.git"
#    tools_repo_https_token = "ghp_YOUR_TOKEN_HERE"
#
#    Terraform stores the token in AWS Secrets Manager automatically.
#    Instances fetch it at runtime via IAM role -- never stored in S3 scripts.
```

#### Option B: Deploy Key (Single Key for Deployment)

```bash
# 1. Generate SSH key:
ssh-keygen -t ed25519 -C "red-team-tools-deploy" -f ~/.ssh/red-team-tools-deploy

# 2. Add public key to repository:
#    Repository → Settings → Deploy keys → Add deploy key
#    Key: cat ~/.ssh/red-team-tools-deploy.pub

# 3. Store private key in AWS SSM:
aws ssm put-parameter \
    --name "/red-team/tools-repo-ssh-key" \
    --type "SecureString" \
    --value "$(cat ~/.ssh/red-team-tools-deploy)" \
    --region eu-central-1 \
    --overwrite

# 4. Update terraform.tfvars:
#    tools_repo_url = "git@github.com:harr-sudo/red-team-tools.git"
#    tools_repo_ssh_key = "/red-team/tools-repo-ssh-key"
```

### 2. Add Team Members

```bash
# Add collaborators to repository
gh repo add-collaborator harr-sudo/red-team-tools USERNAME --permission write
```

### 3. Configure terraform.tfvars

```hcl
# Tools Repository Configuration
tools_repo_url = "https://github.com/harr-sudo/red-team-tools.git"
tools_repo_branch = "main"
tools_repo_https_token = "ghp_YOUR_TOKEN_HERE"  # Stored in Secrets Manager automatically
# OR
tools_repo_ssh_key = "/red-team/tools-repo-ssh-key"  # For deploy key
```

### 4. Deploy Infrastructure

Tools will be automatically cloned to jump box during deployment:
- **Windows**: `C:\Tools\`
- **WSL2**: `/opt/tools/`

### 5. Access Tools

**From Jump Box:**
- RDP → `C:\Tools\`
- SSH → WSL2 → `/opt/tools/`

**From Laptop:**
```bash
# Clone repository directly
git clone https://github.com/harr-sudo/red-team-tools.git ~/tools
```

## Repository Structure

```
red-team-tools/
├── tools/
│   ├── c2/                    # C2 frameworks
│   ├── post-exploitation/     # Post-exploitation tools
│   ├── network/               # Network tools
│   ├── utilities/             # Utility scripts
│   └── custom/               # Custom tools
└── docs/                      # Tool documentation
```

## Adding Tools

1. Clone repository: `git clone https://github.com/harr-sudo/red-team-tools.git`
2. Add tools to appropriate directory
3. Commit and push: `git add . && git commit -m "Add tool" && git push`
4. Tools will be updated on jump box on next deployment

## Full Documentation

See [Tools Repository Setup Guide](./TOOLS_REPOSITORY_SETUP.md) for complete instructions.

