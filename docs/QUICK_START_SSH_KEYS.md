# Quick Start: Automated SSH Key Distribution

## After Infrastructure Deployment

### Step 1: Generate Ansible Inventory

```bash
./scripts/utilities/generate-inventory.sh
```

This creates `ansible/inventory/hosts.yml` from Terraform outputs.

### Step 2: Distribute SSH Keys

**Option A: Automated Script (Recommended)**
```bash
./scripts/utilities/setup-ssh-keys.sh
```

**Option B: Manual Ansible**
```bash
cd ansible
ansible-playbook -i inventory/hosts.yml playbooks/distribute-ssh-keys.yml \
    -e "ssh_public_key_file=~/.ssh/red-team-jumpbox-key.pub"
```

## That's It!

After running the script, you can SSH to any instance from the jump box:

```bash
# From WSL2 on jump box
ssh ec2-user@c2-server-1-private-ip -i ~/.ssh/red-team-jumpbox-key
```

## What the Script Does

1. ✅ Generates SSH key on jump box (if needed)
2. ✅ Generates Ansible inventory (if needed)
3. ✅ Distributes public key to all instances
4. ✅ Tests connectivity

## Multiple Operators

To add multiple keys:

```bash
ansible-playbook -i inventory/hosts.yml playbooks/distribute-ssh-keys.yml \
    -e "ssh_public_keys=~/.ssh/operator1.pub,~/.ssh/operator2.pub"
```

See [Ansible SSH Keys Guide](./ANSIBLE_SSH_KEYS.md) for complete details.

