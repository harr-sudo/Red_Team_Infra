# SSL/TLS Configuration Guide

This guide explains how SSL certificates are configured and managed for the C2 redirector infrastructure.

## Overview

The Red Team Infrastructure supports two SSL certificate providers for the proxy redirectors:

| Provider | Pros | Cons |
|----------|------|------|
| **Let's Encrypt** (Recommended) | Free, trusted by browsers, auto-renewal | Requires Route53 hosted zone + IAM permissions |
| **Self-Signed** | Works immediately, no external dependencies | Browser warnings, not trusted |

## Let's Encrypt (Recommended)

### How It Works — DNS-01 Validation via Route53

We use **DNS-01 validation** instead of HTTP-01 because C2 deployments typically have **multiple redirectors behind round-robin DNS** (multiple A records for the same domain). HTTP-01 fails in this setup because Let's Encrypt's validation request could hit the wrong server. DNS-01 validates by creating a TXT record in Route53 — it doesn't matter which server runs certbot.

**Key point:** DNS-01 does NOT require the domain to resolve to the redirector. It validates via a TXT record in Route53, so certificates can be obtained even before you update nameservers at your registrar.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                Let's Encrypt Automation Flow (DNS-01)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. DEPLOYMENT                                                              │
│     └─ Redirector EC2 instance launches with IAM instance profile           │
│     └─ python3-certbot-dns-route53 installed via apt                        │
│     └─ Self-signed certificate created (temporary)                          │
│     └─ Nginx starts with self-signed cert                                   │
│     └─ C2 traffic works immediately (with browser warning)                  │
│                                                                             │
│  2. DNS-01 CERTIFICATE REQUEST (Immediate at boot)                          │
│     └─ Certbot uses --dns-route53 plugin (no HTTP challenge needed)         │
│     └─ Uses IAM role credentials to create _acme-challenge TXT record       │
│     └─ Let's Encrypt validates the TXT record → proves domain ownership     │
│     └─ Certificate installed in /etc/letsencrypt/live/                      │
│     └─ Nginx config updated to use Let's Encrypt cert, then reloaded       │
│                                                                             │
│  3. FALLBACK (If first attempt fails)                                       │
│     └─ IAM role may not be ready yet at boot (eventual consistency)         │
│     └─ Systemd timer retries certbot every 5 minutes                        │
│     └─ No DNS resolution gate — retries certbot directly each time          │
│     └─ Timer disabled once certificate is obtained                          │
│                                                                             │
│  4. AUTO-RENEWAL                                                            │
│     └─ Cron job runs: certbot renew (uses same DNS-01 method)              │
│     └─ Certificates renewed before 90-day expiry                            │
│     └─ Nginx reloaded automatically after renewal                           │
│     └─ Admin receives email warnings if renewal fails                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why DNS-01 Instead of HTTP-01?

| Challenge Type | How It Works | Round-Robin DNS | Multi-Redirector |
|---------------|-------------|-----------------|------------------|
| **HTTP-01** | LE connects to port 80, server must serve a file | Breaks — request hits random server | Only 1 server gets the cert |
| **DNS-01** | LE checks a TXT record in Route53 | Works perfectly | All servers can get their own cert independently |

### Prerequisites (Automatic)

These are all handled automatically by Terraform and the bootstrap script. Listed here for troubleshooting:

| Requirement | How It's Provisioned | What Breaks Without It |
|-------------|---------------------|----------------------|
| **IAM instance profile** on redirector EC2 | `iam_instance_profile` in `proxy_redirector` module, using C2 role from `deployment_storage` | `Unable to locate credentials` — certbot can't authenticate to Route53 |
| **Route53 IAM permissions** on the C2 role | Dynamic statements in `deployment_storage` when `enable_route53_dns_validation = true` | `AccessDenied` on `route53:ListHostedZones` |
| **`python3-certbot-dns-route53`** package | Installed via apt in `setup_redirector.sh` | `The requested dns-route53 plugin does not appear to be installed` |
| **Route53 hosted zone** for the domain | Created by the `dns` module when `primary_domain_name` is set | Certbot can't find the hosted zone to create TXT records |

### IAM Permissions (Automatic)

When `ssl_provider = "letsencrypt"` and a domain is configured, Terraform automatically:

1. **Attaches the C2 IAM instance profile** to redirector EC2 instances
2. **Adds Route53 permissions** to the C2 role policy:
   - `route53:ChangeResourceRecordSets` — create/delete the `_acme-challenge` TXT record
   - `route53:ListHostedZones` — discover the correct hosted zone
   - `route53:GetChange` — wait for DNS propagation confirmation

These are scoped to the C2 VPC role and only granted when Let's Encrypt is enabled.

### Configuration

In the web app **Configuration** page, set:

| Field | Value | Description |
|-------|-------|-------------|
| SSL Provider | `Let's Encrypt` | Select from dropdown |
| Admin Email | `admin@yourcompany.com` | **Required** - receives expiry warnings |
| Auto-Retry | Checked | Auto-request cert every 5 minutes until success |

### Post-Deployment

1. **Certificate is requested automatically at boot** — no manual action needed if IAM is configured correctly

2. **Update DNS at registrar** — Copy the AWS nameservers from Terraform output and update your domain registrar. This is needed for DNS resolution (so beacons can reach your redirectors), but NOT needed for certificate issuance.

3. **Monitor via web app** — The Deployment Manager has an **SSL & DNS Status** section that shows certificate status for each redirector, fetched via SSH. Click **Refresh** to get the latest.

4. **Monitor via SSH** (optional):
   ```bash
   # Check SSL status
   cat /opt/ssl-status.json

   # Watch auto-request logs
   tail -f /var/log/ssl-auto-request.log

   # Check timer status (disabled = cert obtained)
   systemctl status ssl-auto-request.timer
   ```

5. **Verify certificate** (optional):
   ```bash
   sudo certbot certificates
   ```

### SSL Status File

The redirector maintains status in `/opt/ssl-status.json`:

```json
{
    "status": "valid",
    "message": "Let's Encrypt certificate active (DNS-01)",
    "cert_type": "letsencrypt",
    "expiry": "Jun  7 15:41:27 2026 GMT",
    "domain": "api.yourdomain.com",
    "provider": "letsencrypt",
    "last_updated": "2026-03-09T16:45:29+00:00",
    "public_ip": "1.2.3.4"
}
```

Status values:
- `valid` - Let's Encrypt certificate active
- `pending` - Certificate request failed, will retry every 5 minutes
- `self-signed` - Using self-signed certificate
- `disabled` - SSL disabled
- `manual_required` - Auto-retry disabled, manual action needed

### DNS Toggle (Redirector IP Rotation)

The web app **SSL & DNS Status** section includes a **DNS toggle** for each redirector. This is used when the blue team burns (blocklists) a redirector IP:

1. **Toggle OFF** a burned redirector — removes its IP from the Route53 A record
2. Beacons continue resolving the domain to the remaining active redirector(s)
3. **Toggle ON** to re-add the IP when safe (or after rotating to a new IP)

The toggle prevents disabling the last active redirector. DNS changes propagate based on TTL (typically 60-300 seconds).

**Verification:** Run from the **target network** (via beacon shell), not the operator's laptop:
```bash
dig +short api.yourdomain.com
```
The blue team's blocklist affects the target estate's DNS, not the operator's home network.

### Manual Certificate Request

If auto-retry is disabled or you want to manually request:

```bash
# SSH into redirector
ssh -i your-key.pem ubuntu@redirector-ip

# Verify IAM credentials are available
aws sts get-caller-identity

# Request certificate manually using DNS-01 via Route53
sudo certbot certonly --dns-route53 -d api.yourdomain.com \
    --non-interactive --agree-tos --email admin@yourcompany.com

# Update nginx to use the new cert
sudo sed -i "s|ssl_certificate .*|ssl_certificate /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;|" /etc/nginx/sites-available/c2-redirector
sudo sed -i "s|ssl_certificate_key .*|ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;|" /etc/nginx/sites-available/c2-redirector
sudo nginx -t && sudo systemctl reload nginx
```

### Troubleshooting

#### "Unable to locate credentials"

The redirector EC2 instance has no IAM instance profile attached.

```bash
# Verify on the redirector
aws sts get-caller-identity
# Should return the C2 role ARN. If it says "Unable to locate credentials":

# Fix: Attach the instance profile via AWS CLI (from your laptop)
aws ec2 associate-iam-instance-profile \
    --instance-id i-XXXXX \
    --iam-instance-profile Name=YOUR-PROJECT-cs-download-c2-profile \
    --region YOUR-REGION
```

#### "AccessDenied on route53:ListHostedZones"

The IAM role exists but doesn't have Route53 permissions. This means `enable_route53_dns_validation` wasn't applied.

```bash
# Fix: Apply just the IAM policy
cd terraform
terraform apply -var-file=../configs/terraform.tfvars \
    -target='module.cs_storage[0].aws_iam_role_policy.cs_download_c2[0]'
```

#### "dns-route53 plugin does not appear to be installed"

The certbot Route53 plugin wasn't installed during bootstrap.

```bash
# Fix: Install on the redirector
sudo apt-get update && sudo apt-get install -y python3-certbot-dns-route53
```

#### Certificate Request Failed (General)

```bash
# Check certbot logs for the specific error
sudo cat /var/log/letsencrypt/letsencrypt.log

# Check auto-retry logs
tail -20 /var/log/ssl-auto-request.log

# Common causes:
# - IAM role not ready yet at boot (eventual consistency — retries fix this)
# - Route53 hosted zone not found (check domain is configured in Route53)
# - Rate limit exceeded (wait 1 hour, LE allows 5 certs per domain per week)
```

#### Timer Not Running

```bash
# Check timer status
systemctl status ssl-auto-request.timer

# Enable and start if needed
sudo systemctl enable ssl-auto-request.timer
sudo systemctl start ssl-auto-request.timer
```

---

## Self-Signed Certificates

### When to Use

- Testing/development environments
- Internal-only deployments
- When DNS cannot be configured
- Immediate deployment without waiting for DNS

### Configuration

In the web app **Configuration** page, set:

| Field | Value |
|-------|-------|
| SSL Provider | `Self-Signed` |

### Limitations

- Browsers will show security warnings
- Some EDR/security tools may flag as suspicious
- Not suitable for production red team operations

### Certificate Details

Self-signed certificates are generated with:
- **Validity**: 365 days
- **Key Size**: RSA 2048-bit
- **Subject**: CN=api.yourdomain.com, O=CloudSync Solutions, C=US

---

## Security Considerations

### OPSEC Best Practices

1. **Use Let's Encrypt** - Trusted certificates look more legitimate
2. **Use aged domains** - Domains registered 6+ months ago have better reputation
3. **Get domain categorized** - Submit to web filter vendors as "Business/Technology"
4. **Monitor certificate expiry** - Set up alerts for the admin email

### Certificate Fingerprinting

Be aware that TLS certificates can be fingerprinted:
- Certificate serial number
- Issuer (Let's Encrypt vs self-signed)
- Subject Alternative Names (SANs)

Let's Encrypt certificates are common and blend in better than self-signed.

---

## Files and Locations

| File | Description |
|------|-------------|
| `/etc/nginx/ssl/server.crt` | SSL certificate (self-signed or symlink) |
| `/etc/nginx/ssl/server.key` | SSL private key |
| `/etc/letsencrypt/live/<domain>/` | Let's Encrypt certificates |
| `/opt/ssl-status.json` | Current SSL status |
| `/opt/ssl-scripts/auto-request-cert.sh` | Auto-request script |
| `/opt/ssl-scripts/ssl-config.env` | SSL configuration |
| `/var/log/ssl-auto-request.log` | Auto-request logs |
| `/var/log/letsencrypt/` | Certbot logs |

---

## Terraform Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ssl_provider` | string | `letsencrypt` | SSL provider: `letsencrypt` or `self-signed` |
| `admin_email` | string | `""` | Email for Let's Encrypt notifications |
| `ssl_auto_retry` | bool | `true` | Auto-retry cert request every 5 minutes |
| `enable_ssl_certificate` | bool | `true` | Enable SSL on redirectors |

Example `terraform.tfvars`:

```hcl
ssl_provider           = "letsencrypt"
admin_email            = "admin@yourcompany.com"
ssl_auto_retry         = true
enable_ssl_certificate = true
```
