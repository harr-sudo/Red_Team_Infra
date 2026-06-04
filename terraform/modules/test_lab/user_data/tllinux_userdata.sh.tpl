#!/bin/bash
# =============================================================================
# Test Lab — Linux Member First-Boot (tllinux01)
# =============================================================================
# Minimal cloud-init. Ansible (testlab_linux.yml) installs Docker, configures
# the docker-socket-exposed bolt-on, and applies the DVWA-lite payload later.
# =============================================================================
set -euxo pipefail

LOG=/var/log/testlab-userdata.log
exec > >(tee -a "$LOG") 2>&1
echo "=== Test Lab ${hostname} first-boot ==="
echo "Started: $(date -u +%FT%TZ)"

# -----------------------------------------------------------------------------
# Hostname
# -----------------------------------------------------------------------------
hostnamectl set-hostname "${hostname}"
if ! grep -q "${hostname}" /etc/hosts; then
    echo "127.0.1.1 ${hostname}" >> /etc/hosts
fi

# -----------------------------------------------------------------------------
# Wait for NAT egress (NAT GW may not be ready instantly on first boot)
# -----------------------------------------------------------------------------
for i in $(seq 1 30); do
    if curl -sS --connect-timeout 3 http://archive.ubuntu.com >/dev/null 2>&1; then
        echo "Network ready after $i attempts"
        break
    fi
    echo "Waiting for NAT egress ($i/30)..."
    sleep 10
done

# -----------------------------------------------------------------------------
# Base packages: Python (so Ansible can drive this host), qemu-guest-agent,
# curl. Docker is installed later by Ansible because the bolt-ons depend on a
# specific socket exposure.
# -----------------------------------------------------------------------------
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip \
    qemu-guest-agent \
    curl ca-certificates gnupg

systemctl enable --now qemu-guest-agent || true

# -----------------------------------------------------------------------------
# Point DNS at tldc01 for testlab.local resolution. Linux is not domain-joined
# but bolt-ons may need to resolve domain-controller names.
# -----------------------------------------------------------------------------
mkdir -p /etc/systemd/resolved.conf.d
cat > /etc/systemd/resolved.conf.d/testlab.conf <<EOF
[Resolve]
DNS=${dc_private_ip}
Domains=~testlab.local
EOF
systemctl restart systemd-resolved || true

echo "First-boot setup complete: $(date -u +%FT%TZ)"
