# File Portal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a modular, secure file upload/download portal to C2 redirectors, toggled via Terraform and configurable through the deployment webapp UI.

**Architecture:** Flask micro-app behind nginx on each redirector, served via gunicorn on localhost:8443. nginx proxies `/login` and `/portal/*` to Flask. Auth uses bcrypt + server-side sessions. All portal code is inlined into `setup_redirector.sh` and conditionally deployed when `enable_file_portal = true`.

**Tech Stack:** Terraform (HCL), Bash, Python/Flask, gunicorn, bcrypt, nginx, fail2ban, vanilla JS/HTML/CSS

**Spec:** `docs/superpowers/specs/2026-03-26-file-portal-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `terraform/variables.tf` | Modify (~line 600) | Add root-level portal variables |
| `terraform/main.tf` | Modify (lines 459-484) | Pass portal vars to proxy_redirector module |
| `terraform/modules/proxy_redirector/variables.tf` | Modify (after line 182) | Add module-level portal variables |
| `terraform/modules/proxy_redirector/main.tf` | Modify (lines 26-39) | Add portal vars to templatefile() |
| `terraform/scripts/setup_redirector.sh` | Modify (after line 2123) | Add conditional portal deployment block |
| `configs/terraform.tfvars.example` | Modify | Add example portal config |
| `webapp/backend/utils/config_parser.py` | Modify (lines 168-183) | Add portal section to sections dict |
| `webapp/backend/utils/validators.py` | Modify (after line 241) | Add portal config validation |
| `webapp/frontend/index.html` | Modify (after line 452) | Add portal config UI section |
| `webapp/frontend/js/app.js` | Modify (3 locations) | Config save, load, deployment type visibility |

---

### Task 1: Terraform Variable Plumbing

**Files:**
- Modify: `terraform/variables.tf:~600`
- Modify: `terraform/modules/proxy_redirector/variables.tf:183`
- Modify: `terraform/modules/proxy_redirector/main.tf:26-39`
- Modify: `terraform/main.tf:459-484`
- Modify: `configs/terraform.tfvars.example`

- [ ] **Step 1: Add root-level variables to `terraform/variables.tf`**

Add before the Monitoring Configuration section (~line 591). Follow the existing pattern (description, type, default, sensitive):

```hcl
# =============================================================================
# File Portal Configuration
# =============================================================================

variable "enable_file_portal" {
  description = "Enable the /login file portal on redirectors for secure file sharing"
  type        = bool
  default     = false
}

variable "portal_username" {
  description = "Portal login username (only used if enable_file_portal = true)"
  type        = string
  default     = "operator"
  sensitive   = true
}

variable "portal_password" {
  description = "Portal login password (only used if enable_file_portal = true)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "portal_session_timeout" {
  description = "Portal session timeout in minutes"
  type        = number
  default     = 30
}
```

- [ ] **Step 2: Add module-level variables to `terraform/modules/proxy_redirector/variables.tf`**

Append after the `decoy_theme` variable (after line 182):

```hcl
# =============================================================================
# File Portal Configuration
# =============================================================================

variable "enable_file_portal" {
  description = "Enable the /login file portal on redirectors"
  type        = bool
  default     = false
}

variable "portal_username" {
  description = "Portal login username"
  type        = string
  default     = "operator"
  sensitive   = true
}

variable "portal_password" {
  description = "Portal login password"
  type        = string
  default     = ""
  sensitive   = true
}

variable "portal_session_timeout" {
  description = "Portal session timeout in minutes"
  type        = number
  default     = 30
}
```

- [ ] **Step 3: Add portal vars to templatefile() in `terraform/modules/proxy_redirector/main.tf`**

In the `templatefile()` call (lines 26-39), add after the `decoy_theme` parameter:

```hcl
    enable_file_portal     = var.enable_file_portal ? "true" : "false"
    portal_username        = var.portal_username
    portal_password        = var.portal_password
    portal_session_timeout = var.portal_session_timeout
```

- [ ] **Step 4: Pass portal vars from root `terraform/main.tf` to module**

In the `module "proxy_redirector"` block (lines 459-484), add after the existing parameters (before the closing `}`):

```hcl
  # File Portal
  enable_file_portal     = var.enable_file_portal
  portal_username        = var.portal_username
  portal_password        = var.portal_password
  portal_session_timeout = var.portal_session_timeout
```

- [ ] **Step 5: Add example values to `configs/terraform.tfvars.example`**

Add a new section:

```hcl
# =============================================================================
# File Portal Configuration (Optional)
# =============================================================================
# Deploys a secure file sharing portal on redirectors at /login
# NOTE: When enabled, increase proxy_redirector_root_volume_size to at least 20 (GB)
# enable_file_portal    = false
# portal_username       = "operator"
# portal_password       = "YourSecurePassword123"
# portal_session_timeout = 30
```

- [ ] **Step 6: Validate Terraform config**

Run: `cd terraform && terraform validate -var-file=../configs/terraform.tfvars`
Expected: `Success! The configuration is valid.`

- [ ] **Step 7: Commit**

```bash
git add terraform/variables.tf terraform/main.tf terraform/modules/proxy_redirector/variables.tf terraform/modules/proxy_redirector/main.tf configs/terraform.tfvars.example
git commit -m "feat: add Terraform variable plumbing for file portal"
```

---

### Task 2: Flask Portal Application (inlined in setup_redirector.sh)

This is the core portal — the Flask app that handles auth, sessions, file CRUD, and serves the themed UI. It gets written to `/opt/portal/app.py` by the bootstrap script.

**Files:**
- Modify: `terraform/scripts/setup_redirector.sh` (after line 2123, before SSL section)

- [ ] **Step 1: Add portal variables to the script header**

After line 39 (`HOSTNAME="${hostname}"`), add:

```bash
ENABLE_FILE_PORTAL="${enable_file_portal}"
PORTAL_USERNAME="${portal_username}"
PORTAL_PASSWORD="${portal_password}"
PORTAL_SESSION_TIMEOUT="${portal_session_timeout}"
```

- [ ] **Step 2: Add the portal deployment block**

After line 2123 (`write_step_status 3 "Decoy Website" "ok"`), add the conditional portal block. This is a large section — it writes the Flask app, templates, systemd service, nginx config, and fail2ban jail. The full block is wrapped in:

```bash
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
    mkdir -p /var/www/uploads/unsorted
    chown -R www-data:www-data /var/www/uploads
    mkdir -p /etc/portal

    # Generate bcrypt hash and write credentials (password via stdin to avoid shell injection)
    PORTAL_HASH=$(echo -n "$PORTAL_PASSWORD" | python3 -c "import sys, bcrypt; pw=sys.stdin.buffer.read(); print(bcrypt.hashpw(pw, bcrypt.gensalt()).decode())")
    cat > /etc/portal/credentials << CREDEOF
${PORTAL_USERNAME}
${PORTAL_HASH}
CREDEOF
    chmod 600 /etc/portal/credentials
    chown www-data:www-data /etc/portal/credentials

    # Write Flask application
    cat > /opt/portal/app.py << 'APPEOF'
```

The Flask app.py content follows (see Step 3).

- [ ] **Step 3: Write the Flask application content**

The Flask app (`/opt/portal/app.py`) inlined inside the heredoc. Key components:

```python
import os
import re
import time
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
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; form-action 'self'"
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
    folder = request.args.get('folder', 'unsorted')
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
    folder = request.form.get('folder', 'unsorted')
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
```

The `PLACEHOLDER_*` template strings are replaced by the setup script with the actual themed HTML (see Task 3).

- [ ] **Step 4: Write the systemd service, fail2ban jail, logrotate, and nginx config additions**

After the app.py heredoc, continue the setup script with:

```bash
    # Write systemd service
    cat > /etc/systemd/system/portal.service << 'SVCEOF'
[Unit]
Description=File Portal
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/portal
ExecStart=/usr/bin/gunicorn --bind 127.0.0.1:8443 --workers 2 --timeout 120 app:app
Restart=always
Environment=PORTAL_CONFIG=/etc/portal/credentials
Environment=PORTAL_SESSION_TIMEOUT=PLACEHOLDER_TIMEOUT

[Install]
WantedBy=multi-user.target
SVCEOF
    # Replace timeout placeholder
    sed -i "s/PLACEHOLDER_TIMEOUT/${PORTAL_SESSION_TIMEOUT}/" /etc/systemd/system/portal.service

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
    location /login {
        limit_req zone=login burst=3 nodelay;
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
    'set $block_check "${blocked_agent}${portal_path}";\n        if ($block_check = "10") {',
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
```

- [ ] **Step 5: Verify the script is syntactically valid**

Run: `bash -n terraform/scripts/setup_redirector.sh`
Expected: No output (no syntax errors)

- [ ] **Step 6: Commit**

```bash
git add terraform/scripts/setup_redirector.sh
git commit -m "feat: add file portal Flask app and infrastructure to redirector bootstrap"
```

---

### Task 3: Themed HTML Templates (Meridian Financial + Plexura)

The login page, portal page, and error page must match the decoy site branding. Templates are injected into the Flask app's `PLACEHOLDER_*` strings by the setup script via Python string replacement.

**Files:**
- Modify: `terraform/scripts/setup_redirector.sh` (within the portal deployment block from Task 2)

**NOTE:** This task produces ~500-1000 lines of themed HTML/CSS/JS per theme. Use the `@superpowers:frontend-design` skill to author the full template code. The templates must meet these requirements:

**Login template requirements:**
- Match decoy site branding (Meridian = navy #1a1a2e / gold #c9a84c, Plexura = tech blue #2196F3 / white)
- Centered login card: company logo/name, "Employee Portal" subtitle, username + password fields, sign-in button
- Generic error message: `{% if error %}<div class="error">Invalid credentials</div>{% endif %}` (Jinja2 via `render_template_string`)
- Indistinguishable from a real corporate intranet login — no hint this is a file portal
- Mobile-responsive

**Portal template requirements:**
- Top bar: company logo, "Document Portal" title, logout button (links to `/portal/logout`)
- Left sidebar: folder list loaded via `fetch('/portal/api/folders')`, "New Folder" button with name prompt
- Main area: file table with columns (Name, Size, Modified Date), clickable headers to sort
- Drag/drop overlay: listen for `dragover`/`drop` events on file table area, show "Drop files here" overlay
- "Browse Files" `<input type="file" multiple>` as alternative
- Upload: `fetch('/portal/api/upload', {method: 'POST', headers: {'X-CSRF-Token': csrfToken}, body: formData})`
- Upload progress bar using `XMLHttpRequest` with `upload.onprogress`
- Delete: button per row, confirmation modal before `fetch('/portal/api/files/{folder}/{name}', {method: 'DELETE', headers: {'X-CSRF-Token': csrfToken}})`
- Download: `<a href="/portal/api/download/{folder}/{name}">` on filename
- CSRF token from `<meta name="csrf-token" content="{{ csrf_token }}">`, read by JS on page load
- All API calls include `X-CSRF-Token` header
- Vanilla JS only (no frameworks)
- **CSP note:** The app sets `style-src 'self'`. If templates use inline `<style>` tags or `style=""` attributes, update the CSP to `style-src 'self' 'unsafe-inline'` in the `@app.after_request` handler. Alternatively, use a nonce-based approach.
- **Escaping note:** Templates are injected into Python single-triple-quoted strings (`'''`). Avoid `'''` sequences in the HTML. Use double quotes for all HTML attributes.

**Error template requirements:**
- Same branded look, generic "Page Not Found" message
- Used for both 404 and 500 (no information leakage)
- Accepts `{{ code }}` variable but always shows the same generic message

- [ ] **Step 1: Write template injection script**

After the `app.py` heredoc close, add a theme-conditional block that uses Python to replace the `PLACEHOLDER_*` strings:

```bash
    # Inject themed templates based on DECOY_THEME
    if [ "$DECOY_THEME" = "meridian-financial" ]; then
        python3 << 'TEMPLATEEOF'
# Read app.py and replace placeholder template strings
with open('/opt/portal/app.py') as f:
    content = f.read()

LOGIN_HTML = r"""<!DOCTYPE html>
<html>
... FULL MERIDIAN FINANCIAL LOGIN HTML HERE (authored by frontend-design skill) ...
</html>"""

PORTAL_HTML = r"""<!DOCTYPE html>
<html>
... FULL MERIDIAN FINANCIAL PORTAL HTML HERE (authored by frontend-design skill) ...
</html>"""

ERROR_HTML = r"""<!DOCTYPE html>
<html>
... FULL MERIDIAN FINANCIAL ERROR PAGE HTML HERE ...
</html>"""

content = content.replace('PLACEHOLDER_LOGIN_TEMPLATE', LOGIN_HTML.replace("\\", "\\\\").replace("'''", "\\'\\'\\'"))
content = content.replace('PLACEHOLDER_PORTAL_TEMPLATE', PORTAL_HTML.replace("\\", "\\\\").replace("'''", "\\'\\'\\'"))
content = content.replace('PLACEHOLDER_ERROR_TEMPLATE', ERROR_HTML.replace("\\", "\\\\").replace("'''", "\\'\\'\\'"))

with open('/opt/portal/app.py', 'w') as f:
    f.write(content)
print("Meridian Financial templates injected")
TEMPLATEEOF

    elif [ "$DECOY_THEME" = "plexura" ]; then
        python3 << 'TEMPLATEEOF'
# Same pattern, Plexura branding (blue/white)
with open('/opt/portal/app.py') as f:
    content = f.read()

LOGIN_HTML = r"""<!DOCTYPE html>
... FULL PLEXURA LOGIN HTML HERE (authored by frontend-design skill) ...
</html>"""

PORTAL_HTML = r"""<!DOCTYPE html>
... FULL PLEXURA PORTAL HTML HERE (authored by frontend-design skill) ...
</html>"""

ERROR_HTML = r"""<!DOCTYPE html>
... FULL PLEXURA ERROR PAGE HTML HERE ...
</html>"""

content = content.replace('PLACEHOLDER_LOGIN_TEMPLATE', LOGIN_HTML.replace("\\", "\\\\").replace("'''", "\\'\\'\\'"))
content = content.replace('PLACEHOLDER_PORTAL_TEMPLATE', PORTAL_HTML.replace("\\", "\\\\").replace("'''", "\\'\\'\\'"))
content = content.replace('PLACEHOLDER_ERROR_TEMPLATE', ERROR_HTML.replace("\\", "\\\\").replace("'''", "\\'\\'\\'"))

with open('/opt/portal/app.py', 'w') as f:
    f.write(content)
print("Plexura templates injected")
TEMPLATEEOF
    fi
```

- [ ] **Step 2: Author Meridian Financial templates using `@superpowers:frontend-design` skill**

Fill in the `LOGIN_HTML`, `PORTAL_HTML`, and `ERROR_HTML` strings for the meridian-financial theme. Reference the existing Meridian Financial decoy website in `setup_redirector.sh` (lines 661-1407) for brand colors, fonts, and layout patterns.

- [ ] **Step 3: Author Plexura templates using `@superpowers:frontend-design` skill**

Fill in the templates for the plexura theme. Reference the existing Plexura decoy website in `setup_redirector.sh` (lines 1409-2118).

- [ ] **Step 4: Commit**

```bash
git add terraform/scripts/setup_redirector.sh
git commit -m "feat: add themed HTML templates for file portal (Meridian + Plexura)"
```

---

### Task 4: Webapp UI — Config Parser and Validator

**Files:**
- Modify: `webapp/backend/utils/config_parser.py:168-183`
- Modify: `webapp/backend/utils/validators.py:153-241`

- [ ] **Step 1: Add portal section to config_parser.py sections dict**

In the `sections` dict (lines 168-183), add a new entry after `'Proxy/Redirector Configuration'`:

```python
'File Portal Configuration': ['enable_file_portal', 'portal_username', 'portal_password', 'portal_session_timeout'],
```

The existing `_format_value()` method already handles bools, strings, and numbers correctly.

- [ ] **Step 2: Add portal validation to validators.py**

Add a new static method to `ConfigValidator` class (after line 241):

```python
@staticmethod
def validate_file_portal_config(config: Dict) -> Tuple[bool, List[str]]:
    """Validate file portal configuration."""
    errors = []
    enable = config.get('enable_file_portal', False)
    if not enable:
        return True, errors

    username = config.get('portal_username', '').strip()
    if not username:
        errors.append("portal_username is required when file portal is enabled")
    elif len(username) < 3:
        errors.append("portal_username must be at least 3 characters")
    elif not re.match(r'^[a-zA-Z0-9_-]+$', username):
        errors.append("portal_username can only contain alphanumeric characters, hyphens, and underscores")

    password = config.get('portal_password', '').strip()
    if not password:
        errors.append("portal_password is required when file portal is enabled")
    elif len(password) < 8:
        errors.append("portal_password must be at least 8 characters")

    timeout = config.get('portal_session_timeout', 30)
    if not isinstance(timeout, (int, float)) or timeout < 1 or timeout > 1440:
        errors.append("portal_session_timeout must be between 1 and 1440 minutes")

    return len(errors) == 0, errors
```

- [ ] **Step 3: Wire validation into `validate_config()`**

In the `validate_config()` method, add before the return statement (~line 241):

```python
# Validate file portal configuration
fp_valid, fp_errors = ConfigValidator.validate_file_portal_config(config)
if not fp_valid:
    errors.extend(fp_errors)
```

- [ ] **Step 4: Commit**

```bash
git add webapp/backend/utils/config_parser.py webapp/backend/utils/validators.py
git commit -m "feat: add file portal config parsing and validation"
```

---

### Task 5: Webapp UI — Frontend Form and JavaScript

**Files:**
- Modify: `webapp/frontend/index.html` (after line 452)
- Modify: `webapp/frontend/js/app.js` (3 locations)

- [ ] **Step 1: Add HTML form section to index.html**

Insert after line 452 (after domain fronting section, before attack box section):

```html
<!-- File Portal Configuration Section -->
<div id="file-portal-section" class="section-card" style="display: none;">
    <h3>File Portal</h3>
    <p>Deploy a secure file sharing portal on redirectors. Accessible at <code>/login</code> on your redirector domain. Themed to match your decoy website.</p>

    <div class="form-group">
        <label style="display: flex; align-items: center; gap: 10px; cursor: pointer;">
            <input type="checkbox" id="enable-file-portal" style="width: 18px; height: 18px;">
            <span>Enable File Portal</span>
        </label>
    </div>

    <div id="file-portal-options" style="opacity: 0.5; pointer-events: none;">
        <div class="form-group">
            <label for="portal-username">Portal Username:</label>
            <input type="text" id="portal-username" value="operator" placeholder="operator">
        </div>

        <div class="form-group">
            <label for="portal-password">Portal Password:</label>
            <input type="password" id="portal-password" placeholder="Enter a strong password">
            <small style="color: var(--text-secondary);">Minimum 8 characters. Required when portal is enabled.</small>
        </div>

        <div class="form-group">
            <label for="portal-session-timeout">Session Timeout (minutes):</label>
            <input type="number" id="portal-session-timeout" value="30" min="1" max="1440">
            <small style="color: var(--text-secondary);">Sessions expire after this many minutes of inactivity. Default: 30.</small>
        </div>
    </div>
</div>
```

- [ ] **Step 2: Add checkbox toggle logic to app.js**

Find the section where event listeners are set up for checkboxes (near the domain fronting checkbox listener). Add:

```javascript
// File Portal checkbox toggle
const fpCheckbox = document.getElementById('enable-file-portal');
if (fpCheckbox) {
    fpCheckbox.addEventListener('change', (e) => {
        const options = document.getElementById('file-portal-options');
        if (options) {
            options.style.opacity = e.target.checked ? '1' : '0.5';
            options.style.pointerEvents = e.target.checked ? 'auto' : 'none';
        }
    });
}
```

- [ ] **Step 3: Add config gathering in saveConfig() (~line 7238)**

Add to the config object being built:

```javascript
// File Portal
enable_file_portal: document.getElementById('enable-file-portal')?.checked ?? false,
portal_username: document.getElementById('portal-username')?.value?.trim() || 'operator',
portal_password: document.getElementById('portal-password')?.value || '',
portal_session_timeout: parseInt(document.getElementById('portal-session-timeout')?.value) || 30,
```

- [ ] **Step 4: Add config loading in loadConfig() (~line 6305)**

Add to the config restoration section:

```javascript
// Restore file portal settings
const fpCheckbox = document.getElementById('enable-file-portal');
if (fpCheckbox) {
    fpCheckbox.checked = config.enable_file_portal === true;
    const fpOptions = document.getElementById('file-portal-options');
    if (fpOptions) {
        fpOptions.style.opacity = fpCheckbox.checked ? '1' : '0.5';
        fpOptions.style.pointerEvents = fpCheckbox.checked ? 'auto' : 'none';
    }
}
if (config.portal_username) {
    const el = document.getElementById('portal-username');
    if (el) el.value = config.portal_username;
}
if (config.portal_password) {
    const el = document.getElementById('portal-password');
    if (el) el.value = config.portal_password;
}
if (config.portal_session_timeout) {
    const el = document.getElementById('portal-session-timeout');
    if (el) el.value = config.portal_session_timeout;
}
```

- [ ] **Step 5: Add deployment type visibility in updateDeploymentType() (~line 6933)**

Add alongside the existing section visibility toggles:

```javascript
// File Portal — only for deployments with redirectors (C2 and Combined)
const supportsFilePortal = ['c2-adhoc', 'c2-purple', 'c2-full',
    'combined-adhoc-mini', 'combined-adhoc-light', 'combined-full-full'].includes(deploymentType);
const fpSection = document.getElementById('file-portal-section');
if (fpSection) {
    fpSection.style.display = supportsFilePortal ? 'block' : 'none';
}
```

- [ ] **Step 6: Test in both themes**

Open `http://127.0.0.1:5000`, verify:
1. File Portal section appears only for C2/Combined deployment types
2. File Portal section is hidden for GOAD-only types
3. Checkbox toggles the username/password fields
4. Config saves and restores correctly (save, reload page, verify values persist)

- [ ] **Step 7: Commit**

```bash
git add webapp/frontend/index.html webapp/frontend/js/app.js
git commit -m "feat: add file portal configuration to deployment webapp UI"
```

---

### Task 6: Integration Testing

Manual validation of the full pipeline.

- [ ] **Step 1: Start the webapp and verify UI**

Run: `./webapp/start.sh`

Verify at `http://127.0.0.1:5000`:
- Select `c2-adhoc` deployment type
- File Portal section is visible
- Check "Enable File Portal", enter username + password
- Save config
- Verify `configs/terraform.tfvars` contains `enable_file_portal = true`, `portal_username`, `portal_password`

- [ ] **Step 2: Validate Terraform**

Run: `cd terraform && terraform validate -var-file=../configs/terraform.tfvars`
Expected: `Success! The configuration is valid.`

Run: `terraform plan -var-file=../configs/terraform.tfvars` (dry run)
Verify the portal variables are accepted without errors.

- [ ] **Step 3: Verify setup_redirector.sh syntax**

Run: `bash -n terraform/scripts/setup_redirector.sh`
Expected: No output (clean syntax)

- [ ] **Step 4: Commit integration test results**

If any fixes were needed during testing, commit them:

```bash
git add -u
git commit -m "fix: integration test fixes for file portal"
```
