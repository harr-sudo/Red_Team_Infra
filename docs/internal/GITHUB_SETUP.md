# GitHub Integration Guide

This guide explains the benefits of using GitHub for this project and how to set it up.

## Benefits of GitHub Integration

### 1. **Version Control**
- Track all changes to infrastructure code
- Roll back to previous versions if needed
- See who made what changes and when
- Maintain a complete history of your infrastructure

### 2. **Collaboration**
- Share infrastructure code with team members securely
- Review changes before deployment (pull requests)
- Assign tasks and track issues
- Maintain multiple environments (dev, staging, prod)

### 3. **Backup and Recovery**
- Automatic backup of all code and configurations
- Easy recovery if local files are lost
- Access from anywhere with proper authentication

### 4. **CI/CD Integration**
- Automate deployments with GitHub Actions
- Run tests before deploying
- Automated infrastructure validation
- Scheduled deployments

### 5. **Documentation**
- Keep documentation alongside code
- Easy to update and maintain
- Version-controlled documentation
- Wiki and discussions for team knowledge

### 6. **Security**
- Private repositories for sensitive code
- Access control and permissions
- Audit logs of all repository activity
- Integration with security scanning tools

### 7. **Best Practices**
- Industry standard for Infrastructure as Code
- Easy onboarding for new team members
- Professional development workflow
- Integration with other tools (Terraform Cloud, etc.)

## Setting Up GitHub

### Step 1: Install GitHub CLI (Optional but Recommended)

```bash
# Check if installed
gh --version

# Install (macOS)
brew install gh

# Install (Linux)
# Follow instructions at: https://cli.github.com/manual/installation
```

### Step 2: Authenticate with GitHub

```bash
# Login to GitHub
gh auth login

# Follow the prompts:
# 1. Choose GitHub.com
# 2. Choose your preferred authentication method (browser or token)
# 3. Complete authentication
```

### Step 3: Verify Authentication

```bash
# Check authentication status
gh auth status

# You should see:
# ✓ Logged in to github.com as <your-username>
```

### Step 4: Create a Private Repository

#### Option A: Using GitHub CLI

```bash
cd Red_Team_Infra

# Create private repository
gh repo create Red_Team_Infra \
    --private \
    --description "Scalable, replicable red team infrastructure for AWS" \
    --source=. \
    --remote=origin \
    --push
```

#### Option B: Using GitHub Web Interface

1. Go to https://github.com/new
2. Repository name: `Red_Team_Infra`
3. Description: "Scalable, replicable red team infrastructure for AWS"
4. Select **Private**
5. **DO NOT** initialize with README, .gitignore, or license (we already have these)
6. Click "Create repository"
7. Follow the instructions to push existing code:

```bash
cd Red_Team_Infra

# Initialize git (if not already done)
git init

# Add remote
git remote add origin https://github.com/YOUR-USERNAME/Red_Team_Infra.git

# Add all files
git add .

# Commit
git commit -m "Initial commit: Red Team Infrastructure setup"

# Push to GitHub
git branch -M main
git push -u origin main
```

### Step 5: Verify Repository Setup

```bash
# Check remote
git remote -v

# Should show:
# origin  https://github.com/YOUR-USERNAME/Red_Team_Infra.git (fetch)
# origin  https://github.com/YOUR-USERNAME/Red_Team_Infra.git (push)
```

## Git Workflow Best Practices

### Initial Setup

```bash
# Configure git user (if not already done)
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

### Daily Workflow

```bash
# Check status
git status

# Add changes
git add .

# Commit with descriptive message
git commit -m "Description of changes"

# Push to GitHub
git push
```

### Branching Strategy

For team collaboration:

```bash
# Create feature branch
git checkout -b feature/new-c2-setup

# Make changes and commit
git add .
git commit -m "Add new C2 setup script"

# Push branch
git push -u origin feature/new-c2-setup

# Create pull request (via GitHub web or CLI)
gh pr create --title "Add new C2 setup script" --body "Description of changes"
```

## Security Considerations

### 1. Never Commit Secrets

The `.gitignore` file is configured to exclude:
- `terraform.tfvars` (contains sensitive configuration)
- SSH keys (`.pem`, `.key` files)
- AWS credentials
- Ansible vault passwords
- Any files with `.secret` extension

**Always verify before committing:**
```bash
# Check what will be committed
git status

# Review changes
git diff
```

### 2. Use GitHub Secrets for CI/CD

If setting up GitHub Actions, use GitHub Secrets for:
- AWS credentials
- API keys
- Passwords
- Other sensitive data

### 3. Repository Access Control

- Use private repositories
- Limit access to authorized team members only
- Use branch protection rules for main branch
- Require pull request reviews

### 4. Regular Audits

- Review repository access regularly
- Check commit history for accidental secret commits
- Use GitHub's security features (Dependabot, secret scanning)

## GitHub Actions Integration (Future)

Once set up, you can add CI/CD workflows:

```yaml
# .github/workflows/deploy.yml
name: Deploy Infrastructure

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2
      - name: Terraform Init
        run: terraform init
      - name: Terraform Validate
        run: terraform validate
```

## Troubleshooting

### Issue: "Repository not found"
**Solution**: Check repository name and your access permissions

### Issue: "Authentication failed"
**Solution**: Re-authenticate with `gh auth login`

### Issue: "Permission denied"
**Solution**: Check SSH keys or use HTTPS with personal access token

### Issue: "Large file warning"
**Solution**: Use Git LFS for large files or exclude them from repository

## Next Steps

After setting up GitHub:

1. ✅ Add team members as collaborators
2. ✅ Set up branch protection rules
3. ✅ Configure GitHub Actions (optional)
4. ✅ Set up issue templates
5. ✅ Create project board for tracking

## Summary

GitHub integration provides:
- ✅ Version control and history
- ✅ Secure collaboration
- ✅ Automated backups
- ✅ CI/CD capabilities
- ✅ Professional workflow

**Recommendation**: Yes, integrate with GitHub privately. The benefits far outweigh the minimal setup effort, especially for team collaboration and maintaining infrastructure as code best practices.

