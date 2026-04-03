#!/bin/bash
set -euo pipefail

exec > /var/log/dashboard-bootstrap.log 2>&1
echo "=== Dashboard bootstrap started at $(date) ==="

# Set hostname
hostnamectl set-hostname redteam-dashboard

# System packages
apt-get update -y
apt-get install -y python3 python3-pip python3-venv jq unzip curl

# Terraform
TERRAFORM_VERSION="1.9.8"
curl -fsSL "https://releases.hashicorp.com/terraform/$${TERRAFORM_VERSION}/terraform_$${TERRAFORM_VERSION}_linux_amd64.zip" -o /tmp/terraform.zip
unzip -o /tmp/terraform.zip -d /usr/local/bin/
rm /tmp/terraform.zip
terraform --version

# AWS CLI v2
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
unzip -o /tmp/awscliv2.zip -d /tmp/
/tmp/aws/install --update
rm -rf /tmp/aws /tmp/awscliv2.zip
aws --version

# Create shared group — operators and the service user share this
groupadd -f redteam

# Create dedicated service user (Flask runs as this, not root)
useradd -r -s /usr/sbin/nologin -d /opt/redteam -g redteam dashboard

# Create operator Linux users (all in redteam group)
%{ for name, key in operator_keys ~}
if ! id "${name}" &>/dev/null; then
  useradd -m -s /bin/bash -G redteam "${name}"
  mkdir -p /home/${name}/.ssh
  echo "${key}" > /home/${name}/.ssh/authorized_keys
  chmod 700 /home/${name}/.ssh
  chmod 600 /home/${name}/.ssh/authorized_keys
  chown -R ${name}:${name} /home/${name}/.ssh
  # Scoped sudo — service management + terraform + logs only
  echo "${name} ALL=(ALL) NOPASSWD: /usr/bin/systemctl * dashboard, /usr/local/bin/terraform *, /usr/bin/journalctl *" > /etc/sudoers.d/${name}
fi
%{ endfor ~}

# Install SSM agent for remote management fallback
snap install amazon-ssm-agent --classic 2>/dev/null || true
systemctl enable snap.amazon-ssm-agent.amazon-ssm-agent.service 2>/dev/null || true

# Create project directories
mkdir -p /opt/redteam/{uploads,uploads_client,uploads_tools,logs,configs}

# Write backend config for Terraform S3 state
cat > /opt/redteam/backend.hcl <<'BACKEND'
bucket         = "${s3_bucket}"
key            = "infrastructure/terraform.tfstate"
region         = "${aws_region}"
encrypt        = true
dynamodb_table = "${dynamodb_table}"
BACKEND

# Set ownership and permissions LAST (after all files are written)
chown -R dashboard:redteam /opt/redteam
chmod 2775 /opt/redteam
find /opt/redteam -type d -exec chmod 2775 {} \;
find /opt/redteam -type f -exec chmod 664 {} \;

echo "=== Dashboard bootstrap completed at $(date) ==="
