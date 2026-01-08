# SSL/TLS Configuration Guide

This guide explains how SSL certificates are configured and managed for the C2 redirector infrastructure.

## Overview

The Red Team Infrastructure supports two SSL certificate providers for the proxy redirectors:

| Provider | Pros | Cons |
|----------|------|------|
| **Let's Encrypt** (Recommended) | Free, trusted by browsers, auto-renewal | Requires DNS to be configured first |
| **Self-Signed** | Works immediately, no external dependencies | Browser warnings, not trusted |

## Let's Encrypt (Recommended)

### How It Works

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Let's Encrypt Automation Flow                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. DEPLOYMENT                                                               │
│     └─ Redirector EC2 instance launches                                      │
│     └─ Self-signed certificate created (temporary)                           │
│     └─ Nginx starts with self-signed cert                                    │
│     └─ C2 traffic works immediately (with browser warning)                   │
│                                                                              │
│  2. DNS CHECK (Every 5 minutes)                                              │
│     └─ Systemd timer runs /opt/ssl-scripts/auto-request-cert.sh             │
│     └─ Checks: dig +short api.yourdomain.com == server's public IP          │
│     └─ If DNS not ready: logs status, waits for next check                  │
│                                                                              │
│  3. CERTIFICATE REQUEST (When DNS Ready)                                     │
│     └─ Certbot requests certificate via HTTP-01 challenge                    │
│     └─ Let's Encrypt validates domain ownership                              │
│     └─ Certificate installed in /etc/letsencrypt/live/                       │
│     └─ Nginx automatically reloaded with trusted cert                        │
│     └─ Timer disabled (certificate obtained)                                 │
│                                                                              │
│  4. AUTO-RENEWAL                                                             │
│     └─ Cron job runs: certbot renew --quiet                                 │
│     └─ Certificates renewed before 90-day expiry                             │
│     └─ Admin receives email warnings if renewal fails                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Configuration

In the web app **Configuration** page, set:

| Field | Value | Description |
|-------|-------|-------------|
| SSL Provider | `Let's Encrypt` | Select from dropdown |
| Admin Email | `admin@yourcompany.com` | **Required** - receives expiry warnings |
| Auto-Retry | ✅ Checked | Auto-request cert when DNS propagates |

### Post-Deployment Steps

1. **Update DNS** - After deployment, copy the AWS name servers from Terraform output and update your domain registrar

2. **Wait for DNS Propagation** - Can take 15 minutes to 48 hours
   ```bash
   # Check if DNS is propagated
   dig +short api.yourdomain.com
   # Should return the redirector's public IP
   ```

3. **Monitor Certificate Request** - SSH into redirector and check:
   ```bash
   # Check SSL status
   cat /opt/ssl-status.json
   
   # Watch auto-request logs
   tail -f /var/log/ssl-auto-request.log
   
   # Check timer status
   systemctl status ssl-auto-request.timer
   ```

4. **Verify Certificate** - Once obtained:
   ```bash
   # Check certificate
   sudo certbot certificates
   
   # Test HTTPS
   curl -v https://api.yourdomain.com/health
   ```

### SSL Status File

The redirector maintains status in `/opt/ssl-status.json`:

```json
{
    "status": "valid",
    "message": "Let's Encrypt certificate active",
    "cert_type": "letsencrypt",
    "expiry": "2024-06-15T12:00:00Z",
    "domain": "api.yourdomain.com",
    "provider": "letsencrypt",
    "last_updated": "2024-03-15T10:30:00Z",
    "public_ip": "1.2.3.4"
}
```

Status values:
- `valid` - Let's Encrypt certificate active
- `waiting_dns` - Waiting for DNS to propagate
- `pending` - Certificate request in progress or failed (will retry)
- `self-signed` - Using self-signed certificate
- `disabled` - SSL disabled
- `manual_required` - Auto-retry disabled, manual action needed

### Manual Certificate Request

If auto-retry is disabled or you want to manually request:

```bash
# SSH into redirector
ssh -i your-key.pem ubuntu@redirector-ip

# Request certificate manually
sudo certbot --nginx -d api.yourdomain.com -d yourdomain.com -d www.yourdomain.com \
    --non-interactive --agree-tos --email admin@yourcompany.com

# Reload nginx
sudo systemctl reload nginx
```

### Troubleshooting

#### DNS Not Resolving

```bash
# Check what DNS resolves to
dig +short api.yourdomain.com

# Check server's public IP
curl -s https://api.ipify.org

# They should match
```

#### Certificate Request Failed

```bash
# Check certbot logs
sudo cat /var/log/letsencrypt/letsencrypt.log

# Common issues:
# - Port 80 blocked (check security group)
# - DNS not propagated yet
# - Rate limit exceeded (wait 1 hour)
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

- ⚠️ Browsers will show security warnings
- ⚠️ Some EDR/security tools may flag as suspicious
- ⚠️ Not suitable for production red team operations

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
| `ssl_auto_retry` | bool | `true` | Auto-retry cert request when DNS ready |
| `enable_ssl_certificate` | bool | `true` | Enable SSL on redirectors |

Example `terraform.tfvars`:

```hcl
ssl_provider           = "letsencrypt"
admin_email            = "admin@yourcompany.com"
ssl_auto_retry         = true
enable_ssl_certificate = true
```

