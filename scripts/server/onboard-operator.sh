#!/usr/bin/env bash
# onboard-operator.sh — add (or refresh) an operator on a RUNNING dashboard.
#
# Operator Linux users are created by the dashboard's user_data at CREATION time.
# AWS runs user_data only once at first boot, so adding an operator to an already-
# running dashboard cannot be done by editing operator_ssh_public_keys + applying
# (that change is intentionally ignored — see the instance lifecycle block). This
# helper does it live: it idempotently creates the operator's redteam-group Linux
# user + authorized_keys + scoped sudo, over the same full-sudo `ubuntu` path the
# setup script uses (ephemeral access via EC2 Instance Connect).
#
# Usage:  ./scripts/server/onboard-operator.sh <name> <path-to-their-ssh-pubkey> [<dashboard-eip>]
#   AWS_REGION    — defaults to your configured region (else eu-central-1)
#   ADMIN_SSH_KEY — your private key whose .pub is pushed for ubuntu (default ~/.ssh/id_ed25519)
set -euo pipefail

NAME="${1:-}"
KEYFILE="${2:-}"
DASH_IP="${3:-}"
AWS_REGION="${AWS_REGION:-$(aws configure get region 2>/dev/null || echo eu-central-1)}"
ADMIN_KEY="${ADMIN_SSH_KEY:-$HOME/.ssh/id_ed25519}"

if [ -z "$NAME" ] || [ -z "$KEYFILE" ]; then
    echo "usage: $(basename "$0") <name> <path-to-their-ssh-pubkey> [<dashboard-eip>]" >&2
    exit 1
fi
if ! echo "$NAME" | grep -qE '^[a-z][a-z0-9_-]{0,31}$'; then
    echo "[!] operator name must be lowercase, start with a letter, 1-32 chars of [a-z0-9_-]." >&2
    exit 1
fi
if [ ! -f "$KEYFILE" ]; then
    echo "[!] public key file not found: $KEYFILE" >&2
    exit 1
fi
PUBKEY="$(cat "$KEYFILE")"
if ! echo "$PUBKEY" | grep -qE '^ssh-(ed25519|rsa|ecdsa-sha2-nistp[0-9]+) '; then
    echo "[!] not an SSH public key: $KEYFILE" >&2
    exit 1
fi
if [ ! -f "${ADMIN_KEY}.pub" ]; then
    echo "[!] admin public key not found: ${ADMIN_KEY}.pub (set ADMIN_SSH_KEY)" >&2
    exit 1
fi

# Resolve the dashboard instance by the Name tag terraform sets.
INSTANCE_ID="$(aws ec2 describe-instances --region "$AWS_REGION" \
    --filters "Name=tag:Name,Values=redteam-dashboard-server" "Name=instance-state-name,Values=running" \
    --query 'Reservations[].Instances[].InstanceId' --output text 2>/dev/null | head -n1)"
if [ -z "$INSTANCE_ID" ] || [ "$INSTANCE_ID" = "None" ]; then
    echo "[!] no running redteam-dashboard-server found in $AWS_REGION." >&2
    exit 1
fi
if [ -z "$DASH_IP" ]; then
    DASH_IP="$(aws ec2 describe-instances --region "$AWS_REGION" --instance-ids "$INSTANCE_ID" \
        --query 'Reservations[].Instances[].PublicIpAddress' --output text)"
fi

# Ephemeral full-sudo access: push our key to `ubuntu` for ~60s via Instance Connect.
echo "[*] Requesting ubuntu access on $INSTANCE_ID ..."
aws ec2-instance-connect send-ssh-public-key --region "$AWS_REGION" \
    --instance-id "$INSTANCE_ID" --instance-os-user ubuntu \
    --ssh-public-key "file://${ADMIN_KEY}.pub" >/dev/null

# Transport the key base64-encoded so no shell metacharacters can break the remote.
KEY_B64="$(printf '%s' "$PUBKEY" | base64 | tr -d '\n')"

echo "[*] Provisioning operator '$NAME' on $DASH_IP (idempotent) ..."
ssh -i "$ADMIN_KEY" -o StrictHostKeyChecking=accept-new "ubuntu@$DASH_IP" "sudo bash -s" <<EOF
set -e
getent group redteam >/dev/null 2>&1 || groupadd -f redteam
if id "$NAME" >/dev/null 2>&1; then
  usermod -aG redteam "$NAME"
else
  useradd -m -s /bin/bash -G redteam "$NAME"
fi
install -d -m 700 -o "$NAME" -g "$NAME" "/home/$NAME/.ssh"
KEY=\$(printf '%s' '$KEY_B64' | base64 -d)
touch "/home/$NAME/.ssh/authorized_keys"
grep -qxF "\$KEY" "/home/$NAME/.ssh/authorized_keys" 2>/dev/null || printf '%s\n' "\$KEY" >> "/home/$NAME/.ssh/authorized_keys"
chmod 600 "/home/$NAME/.ssh/authorized_keys"
chown -R "$NAME":"$NAME" "/home/$NAME/.ssh"
# Scoped sudo — service management + terraform + logs only (mirrors user_data.sh).
printf '%s ALL=(ALL) NOPASSWD: /usr/bin/systemctl * dashboard, /usr/local/bin/terraform *, /usr/bin/journalctl *\n' "$NAME" > "/etc/sudoers.d/$NAME"
chmod 440 "/etc/sudoers.d/$NAME"
visudo -cf "/etc/sudoers.d/$NAME" >/dev/null
echo "operator $NAME ready (groups: \$(id -nG "$NAME"))"
EOF

echo "[*] Done. '$NAME' can now connect:"
echo "      ./scripts/server/connect-dashboard.sh $NAME@$DASH_IP"
echo "[*] If their source IP isn't already permitted, add it to dashboard_allowed_ips"
echo "    and re-apply (the security-group change applies live):"
echo "      terraform apply -var-file=../configs/dashboard.tfvars -target=module.dashboard_server"
