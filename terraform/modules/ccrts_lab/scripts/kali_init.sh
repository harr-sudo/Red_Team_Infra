#!/bin/bash
# =============================================================================
# CCRTS Lab — Kali Attacker First-Boot
# =============================================================================
# CREST AMI ships with most tooling already in place. This script just sets
# the hostname and makes sure sshd is up so the dashboard SSH jump can reach
# us. Ingress is already restricted by the kali security group to the
# dashboard VPC CIDR (and optional peered C2 VPC).
# =============================================================================
set -euxo pipefail

LOG=/var/log/ccrts-kali-init.log
exec > >(tee -a "$LOG") 2>&1
echo "=== CCRTS Kali ${hostname} first-boot $(date -u +%FT%TZ) ==="

# -----------------------------------------------------------------------------
# Hostname
# -----------------------------------------------------------------------------
hostnamectl set-hostname "${hostname}" || true
if ! grep -q "${hostname}" /etc/hosts; then
    echo "127.0.1.1 ${hostname}" >> /etc/hosts
fi

# -----------------------------------------------------------------------------
# Make sure sshd is enabled + running. CREST AMI normally has this on, but
# belt-and-braces.
# -----------------------------------------------------------------------------
systemctl enable ssh || true
systemctl start ssh || true

# -----------------------------------------------------------------------------
# Marker for the dashboard "Host Setup Checker" feature
# -----------------------------------------------------------------------------
mkdir -p /var/lib/ccrts
echo "ccrts-kali-init: ok $(date -u +%FT%TZ)" > /var/lib/ccrts/init.status

echo "=== CCRTS Kali first-boot complete $(date -u +%FT%TZ) ==="
