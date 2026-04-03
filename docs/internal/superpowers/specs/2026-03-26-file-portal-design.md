# File Portal Design Spec

**Date:** 2026-03-26
**Status:** Approved
**Scope:** Modular, secure file upload/download portal on C2 redirectors behind `/login`

---

## 1. Problem Statement

Red team operators need a way to upload, manage, and download files (payloads, reports, tools) through the redirector domains. The portal must be secure against brute force, injection, and scanning attacks, and visually blend with the decoy website theme so it appears to be a legitimate corporate employee portal.

## 2. Architecture

```
Internet -> nginx (443) -> /login, /portal/* -> proxy_pass -> Flask (127.0.0.1:8443)
                        -> /C2-URIs          -> proxy_pass -> C2 team server
                        -> everything else   -> decoy site (/var/www/html)
```

### Components (per redirector)

| Component | Role |
|---|---|
| nginx | SSL termination, rate limiting, routing `/login` and `/portal/*` to Flask |
| Flask micro-app | Auth, file CRUD, themed UI. Runs via gunicorn as systemd service on `127.0.0.1:8443` |
| File storage | `/var/www/uploads/` with subdirectories per organization folder |
| fail2ban | Watches auth log, bans IPs with repeated failures |

Flask listens on localhost only — never directly exposed to the internet.

**Multi-redirector note:** With `proxy_redirector_count = 2`, each redirector runs an independent Flask instance with its own local disk. Files uploaded to redirector-1 are NOT visible on redirector-2. To ensure operators always hit a single file store, the `www.` subdomain should point to only ONE redirector IP, while `api.` and the apex domain retain both IPs for C2 beacon redundancy. Operators access the portal via `https://www.<domain>/login`.

## 3. Authentication

### Login Flow

1. GET `/login` -> nginx proxies to Flask -> renders themed login page
2. POST `/login` with username + password -> Flask validates against bcrypt hash
3. Success -> generates session ID via `secrets.token_hex(32)`, stores in server-side dict with expiry, sets cookie
4. Failure -> generic "Invalid credentials" message, logs real client IP + timestamp to `/dev/shm/portal-auth.log`
5. All `/portal/*` routes check for valid session ID in server-side dict -> redirect to `/login` if missing/expired

### Credential Storage

- Single shared credential (one username/password for the red team)
- Username and password set via Terraform variables (`portal_username`, `portal_password`) marked `sensitive = true`
- Password hashed with bcrypt, stored in `/etc/portal/credentials`
- No database, no user table

### Password Length Enforcement

- Reject POST with 400 if password length exceeds 128 bytes (prevents CPU-based DoS via bcrypt hashing multi-megabyte payloads; bcrypt truncates at 72 bytes anyway)
- This check runs BEFORE bcrypt, as the very first validation in the login handler

### Timing-Safe Username Comparison

To prevent timing oracles that reveal whether a username is valid, always execute `bcrypt.checkpw()` even when the username is wrong:

```python
DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt())

if username != stored_username:
    bcrypt.checkpw(password.encode(), DUMMY_HASH)  # constant-time burn
    return "Invalid credentials"
if not bcrypt.checkpw(password.encode(), stored_hash):
    return "Invalid credentials"
```

### Session Management

- Session ID: `secrets.token_hex(32)` (256-bit cryptographic random)
- Stored server-side in a Python `dict` mapping `session_id -> {"issued_at": timestamp}`
- Cookie: opaque session ID string with `HttpOnly`, `Secure`, `SameSite=Strict` flags
- **Cookie `Domain` attribute MUST NOT be set.** When omitted, the browser scopes the cookie to the exact hostname only. This prevents the session cookie from leaking to other subdomains (e.g., `api.` which routes C2 beacon traffic to the team server). Flask config: `SESSION_COOKIE_DOMAIN = False` or simply omit. Operators should access the portal via a specific hostname (e.g., `www.domain.com/login`) that is different from the C2 FQDN (`api.domain.com`).
- Expiry: 30 minutes from login. Checked on every request.
- Logout: removes session ID from server-side dict AND deletes cookie. Captured cookies become immediately useless.
- App restart: all sessions invalidated (acceptable — single credential, users re-login)
- **Max concurrent sessions:** 50. New logins rejected with 503 if limit reached. Prevents session table exhaustion.
- **Lazy expiry purge:** on every request, expired sessions are removed from the dict. This bounds memory growth without a background thread.

### Why Not Signed Cookies

The session ID is a random lookup key with no payload to decode or tamper with. Security comes from 256-bit randomness being computationally infeasible to brute force. No third-party crypto libraries needed. Server-side revocation works perfectly.

## 4. Security Layers

### Rate Limiting (nginx)

These `limit_req_zone` directives go in the `http {}` context (in `/etc/nginx/nginx.conf` or before the `server {}` block), not inside location blocks:

```nginx
limit_req_zone $binary_remote_addr zone=login:5m rate=5r/m;    # 5 login attempts/min per IP
limit_req_zone $binary_remote_addr zone=portal:10m rate=30r/m;  # 30 req/min for file ops
```

### fail2ban

- Watches `/dev/shm/portal-auth.log` for failed login lines (tmpfs — lost on reboot, no forensic persistence)
- 5 failures in 10 minutes -> IP banned for 30 minutes via iptables
- Separate jail from any existing fail2ban config
- **IP logging:** Flask MUST log the real client IP from `request.environ.get('HTTP_X_REAL_IP')`, which nginx sets to `$remote_addr` (the actual TCP peer address). Do NOT use `request.remote_addr` or `request.access_route[0]` — these can be spoofed via `X-Forwarded-For` headers, allowing attackers to evade bans or get legitimate operators banned.
- Do NOT enable Werkzeug's `ProxyFix` middleware, or if used, configure with `x_for=0` so it does not trust forwarded headers for the IP.

### CSRF Protection

CSRF is not applied to `/login` POST — the login form has no pre-existing session to bind a token to, and exploiting CSRF on a login form requires the attacker to already know the credential (making it moot).

CSRF is applied to all authenticated `/portal/*` mutating endpoints (upload, folder create, delete):
- On authenticated page load: generate a CSRF token via `secrets.token_hex(32)`, store it in the server-side session dict
- Token embedded in the portal page as a `<meta>` tag, attached to all fetch/XHR requests as an `X-CSRF-Token` header
- On POST/DELETE: Flask checks `X-CSRF-Token` header matches the session's stored token. Rejects with 403 if mismatched.
- Token regenerated on each full page load, bound to the session ID
- **All mutating requests MUST use JavaScript fetch/XHR.** No HTML form `action` posts are supported. The upload endpoint rejects requests that do not include the `X-CSRF-Token` header.

### Security Headers (all portal responses)

```
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Strict-Transport-Security: max-age=31536000; includeSubDomains
Referrer-Policy: no-referrer
Permissions-Policy: camera=(), microphone=(), geolocation=()
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; form-action 'self'
```

### Path Traversal Protection

- All filenames sanitized with `werkzeug.utils.secure_filename()`
- **After `secure_filename()`, reject with 400 if the result is an empty string** (edge case: inputs like `../../../` return `""`)
- Folder names validated against `^[a-zA-Z0-9_-]+$` regex
- All file paths resolved with `os.path.realpath()` and verified to be within `/var/www/uploads/`
- No symlink following

### Flask Error Handling

- `app.debug = False` and `app.config['PROPAGATE_EXCEPTIONS'] = False` — prevents Werkzeug debugger exposure
- Custom error handler for 500 returns the same decoy-themed page as 404 — no framework information leakage

## 5. File Management

### Directory Structure

```
/var/www/uploads/
├── Org-A/
│   ├── payload.bin
│   └── report.pdf
├── Org-B/
│   └── screenshot.png
└── upload/               # Default folder if no org selected
```

### nginx Upload Protection

Nginx MUST NOT serve `/var/www/uploads/` directly. Add to the nginx config:

```nginx
location /uploads/ {
    deny all;
    return 404;
}
```

All file downloads go through Flask's `send_file()`. This prevents any future nginx misconfiguration from exposing uploads.

### API Endpoints (all require valid session)

| Method | Path | Action |
|---|---|---|
| GET | `/portal/` | Main file manager UI |
| GET | `/portal/api/files?folder=Org-A&sort=modified` | List files as JSON |
| GET | `/portal/api/folders` | List organization folders |
| POST | `/portal/api/folders` | Create new folder |
| POST | `/portal/api/upload` | Upload file(s) via multipart/form-data |
| GET | `/portal/api/download/<folder>/<filename>` | Download a file |
| DELETE | `/portal/api/files/<folder>/<filename>` | Delete a file |

### Session Check Enforcement

Authentication MUST be enforced via a `before_request` handler on the portal Flask blueprint, not via per-route decorators:

```python
@portal_bp.before_request
def require_auth():
    if request.endpoint == 'portal.login' or request.endpoint == 'portal.login_post':
        return  # Login routes are public
    session_id = request.cookies.get('session_id')
    if not session_id or session_id not in sessions or is_expired(sessions[session_id]):
        return redirect('/login')
```

This ensures every `/portal/*` route is protected by default. Forgetting a decorator on a new route cannot create an unauthenticated endpoint.

### File Operations

- **Upload:** Drag/drop or click-to-browse. Multiple files at once. 100MB max enforced at nginx (`client_max_body_size 100M`) and Flask level. Flask checks available disk space before writing — rejects with HTTP 507 `{"error": "Storage full"}` when less than 2GB free or when total uploads exceed the aggregate storage cap (default 5GB, configurable). **Filename collision:** if a file with the same name exists in the target folder, reject with HTTP 409 `{"error": "File already exists"}`. Operator must delete the old file first.
- **List:** Filename, size (human-readable), last modified date. Sortable by name or date. Grouped by folder.
- **Download:** Direct file download via Flask `send_file()` with `Content-Disposition: attachment` header.
- **Delete:** Confirmation prompt in UI. Physically removes file from disk.
- **Folders:** Create and view only. No rename or delete (prevents accidental data loss). Names sanitized to alphanumeric + hyphens.

## 6. Deployment

### Terraform Variables

```hcl
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

**Password validation:** The bootstrap script checks `if [ -z "$PORTAL_PASSWORD" ]; then echo "ERROR: portal_password must be set"; exit 1; fi` before proceeding. This catches the case where `enable_file_portal = true` but password is left empty.

### Terraform Variable Plumbing

The full variable chain:

1. Root `variables.tf` — defines `enable_file_portal`, `portal_username`, `portal_password`, `portal_session_timeout`
2. Root `main.tf` — passes them to the `proxy_redirector` module invocation
3. `modules/proxy_redirector/variables.tf` — declares matching input variables
4. `modules/proxy_redirector/main.tf` — adds them to the `templatefile()` call for `setup_redirector.sh`
5. `setup_redirector.sh` — references as `${enable_file_portal}`, `${portal_username}`, `${portal_password}`, `${portal_session_timeout}`

### Bootstrap (within setup_redirector.sh)

When `enable_file_portal = true`, the redirector bootstrap script:

1. Installs dependencies: `pip3 install 'flask==3.1.*' 'bcrypt==4.2.*' 'gunicorn==23.*'`
2. Writes Flask app to `/opt/portal/app.py`
3. Writes themed HTML templates to `/opt/portal/templates/`
4. Hashes password with bcrypt, writes username + hash to `/etc/portal/credentials`
5. Creates systemd service (`portal.service`) running gunicorn on `127.0.0.1:8443` as `www-data`
6. Adds `/login`, `/portal/`, and `/uploads/` (deny) location blocks to nginx config
7. Exempts `/login` and `/portal/` from the server-level `blocked_agent` check (see nginx section)
8. Configures fail2ban jail for `/dev/shm/portal-auth.log`
9. Creates `/var/www/uploads/upload/` with `www-data` ownership
10. Adds logrotate config for `/dev/shm/portal-auth.log` (every 10 minutes via cron, keep 1 rotation, shred old files)
11. Reloads nginx, starts portal service

### Systemd Service

```ini
[Unit]
Description=File Portal
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/portal
ExecStart=/usr/bin/gunicorn --bind 127.0.0.1:8443 --workers 1 --threads 2 --timeout 120 app:app
Restart=always
Environment=PORTAL_CONFIG=/etc/portal/credentials

[Install]
WantedBy=multi-user.target
```

### nginx Location Blocks

```nginx
# Block direct access to uploads directory
location /uploads/ {
    deny all;
    return 404;
}

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
```

**Key changes from initial design:**
- `X-Forwarded-For` set to `$remote_addr` (replaces, not appends) — prevents spoofing
- `Connection ""` header added — prevents connection upgrade/close forwarding
- Explicit `proxy_connect_timeout`, `proxy_read_timeout`, `proxy_send_timeout` — kills stalled connections

### Blocked Agent Exemption

The existing server-level `if ($blocked_agent)` check blocks `curl`, Python, and other user agents useful for portal automation. The portal must be exempted. Add a `map` in the `http {}` context:

```nginx
map $uri $portal_path {
    ~^/login   1;
    ~^/portal/ 1;
    default    0;
}
```

Then modify the server-level blocked agent check:

```nginx
# Original: if ($blocked_agent) { return 200 "..."; }
# New: skip for portal paths
set $block_check "${blocked_agent}${portal_path}";
if ($block_check = "10") {
    return 200 "<!DOCTYPE html>...";
}
```

This allows operators to use `curl`, Python scripts, or other tools to interact with the portal API while still blocking scanners from the decoy site and C2 paths.

### Modularity

- Enabled/disabled via single boolean `enable_file_portal`
- Theme-aware: reads `DECOY_THEME` variable, renders matching branded login (Meridian Financial employee portal, Plexura admin panel, etc.)
- Adding a new theme = adding a new HTML template block
- No changes to existing C2 routing, decoy site, SSL, or security groups

## 7. UI Design

### Login Page (`/login`)

- Matches decoy site branding (Meridian = corporate navy/gold, Plexura = tech blue/white)
- Centered login card with company logo, "Employee Portal" subtitle, username + password fields, sign-in button
- Indistinguishable from a real corporate intranet login
- Generic error on failure — no indication it's a file portal

### File Manager (`/portal/`)

- Top bar: company logo, "Document Portal" title, logout button
- Left sidebar: organization folder list + "New Folder" button
- Main area: file table (Name, Size, Modified Date columns)
- Column headers clickable to sort
- Drag/drop overlay on file table — "Drop files here to upload"
- "Browse Files" button as alternative to drag/drop
- Upload progress bar for large files
- Delete button per row with confirmation modal
- Download by clicking filename
- Responsive (functional on mobile, optimized for desktop)
- Vanilla JS — no frameworks, consistent with existing webapp frontend
- HTML/CSS/JS inlined into bootstrap script (same pattern as decoy website)

## 8. OPSEC Considerations

### Auth Log vs No-Persistence Principle

The redirector is designed as a "no data persistence" pass-through. The portal introduces auth logging for fail2ban, which creates a tension:

- **Solution:** Auth log is stored on tmpfs (`/dev/shm/portal-auth.log`) — exists only in RAM, lost on reboot
- **Retention:** Logrotate runs every 10 minutes via cron, keeps only 1 rotation, shreds old files. This matches fail2ban's `findtime` of 10 minutes — fail2ban only needs the most recent window.
- **Trade-off:** If the redirector is seized while running, the last 10 minutes of login attempts (IPs + timestamps) are recoverable from RAM. This is accepted as necessary for brute force protection.

### Cookie Isolation from C2 Traffic

Session cookies MUST NOT leak to C2 beacon traffic. Enforced by:
1. Cookie `Domain` attribute is not set — browser scopes to exact hostname only
2. Operators access portal via a hostname (e.g., `www.`) different from the C2 FQDN (`api.`)
3. Even if an operator's browser visits the C2 subdomain, the cookie is not sent

See Section 3 (Session Management) for full details.

## 9. DNS Configuration for Portal Access

When using multiple redirectors (`proxy_redirector_count >= 2`), the `www.` subdomain must point to a **single redirector IP** to ensure operators always hit the same file store. Other subdomains retain all redirector IPs for C2 traffic redundancy:

| Subdomain | IPs | Purpose |
|---|---|---|
| `www.<domain>` | Redirector-1 only | Portal access (`/login`) + decoy site |
| `api.<domain>` | All redirectors | C2 beacon traffic (round-robin) |
| `<domain>` (apex) | All redirectors | Decoy site + C2 fallback |
| `cdn.<domain>` | All redirectors | Decoy site + C2 fallback |

If redirector-1 gets burned by the SOC, update the `www.` record to redirector-2's IP. Files on the burned redirector are lost (acceptable — it's compromised).

**Gunicorn worker model:** The portal uses `--workers 1 --threads 2` (not multiple workers) because sessions are stored in an in-memory Python dict. Multiple workers would have independent session dicts, causing session loss when requests hit different workers.

## 10. Disk Volume Sizing

The redirector's default `root_volume_size` is 8 GB. With the portal enabled and 100MB upload limit, this can fill up during an engagement. When `enable_file_portal = true`, the bootstrap documentation should recommend increasing `proxy_redirector_root_volume_size` to at least 20 GB. The Flask app enforces an aggregate storage cap of 5GB (configurable) and rejects uploads when less than 2GB free.

## 11. Webapp UI Integration

The file portal configuration integrates into the existing deployment webapp following established patterns.

### UI Form Fields (webapp/frontend/index.html)

A new "File Portal Configuration" section, visible only for C2 and Combined deployment types (since those have redirectors):

- **Checkbox:** `enable-file-portal` — toggles the feature on/off
- **Text input:** `portal-username` — defaults to "operator"
- **Password input:** `portal-password` — leave empty to auto-generate
- **Sub-options** (username, password) grayed out when checkbox is unchecked, same pattern as domain fronting options

### Section Visibility

The file portal section is shown/hidden based on deployment type in `updateDeploymentType()`:

```javascript
const supportsFilePortal = ['c2-adhoc', 'c2-purple', 'c2-full',
    'combined-adhoc-mini', 'combined-adhoc-light', 'combined-full-full'].includes(deploymentType);
document.getElementById('file-portal-section').style.display = supportsFilePortal ? 'block' : 'none';
```

GOAD-only deployments have no redirectors, so no portal option.

### Data Flow

```
UI form (index.html)
  -> app.js gathers form values (saveConfig)
  -> POST /api/config (config.py validates & saves)
  -> config_parser.py converts to terraform.tfvars HCL format
  -> terraform.tfvars written to disk
  -> POST /api/deploy triggers terraform apply
  -> Terraform passes vars to proxy_redirector module
  -> setup_redirector.sh conditionally deploys the portal
```

### Files to Modify

| File | Change |
|---|---|
| `webapp/frontend/index.html` | Add file portal form section with checkbox + inputs |
| `webapp/frontend/js/app.js` | Add config gathering (~line 7238), config loading (~line 6305), deployment type visibility toggle |
| `webapp/backend/utils/config_parser.py` | Add `'File Portal Configuration': ['enable_file_portal', 'portal_username', 'portal_password']` to sections dict |
| `webapp/backend/utils/validators.py` | Add `validate_file_portal_config()` — require username when enabled, password >= 8 chars if provided |
| `terraform/variables.tf` | Add variable declarations |
| `configs/terraform.tfvars.example` | Add example values |
| `terraform/modules/proxy_redirector/variables.tf` | Add module-level input variables |
| `terraform/modules/proxy_redirector/main.tf` | Add to `templatefile()` call |
| `terraform/scripts/setup_redirector.sh` | Add conditional portal deployment block |

## 12. What This Design Does NOT Include

- Multi-user accounts or audit trails (single shared credential)
- S3 sync or cross-redirector file sharing (local disk only)
- Account lockout (rate limiting + fail2ban handle abuse)
- IP allowlisting (operators access from varying locations)
- File type restrictions (any type accepted)
- Nested folders within org folders (flat structure per org)
- Folder rename or deletion
- File rename (re-upload if needed)

## 13. Security Review Summary

All findings from the security code review have been incorporated into this spec:

| Severity | Finding | Resolution |
|---|---|---|
| HIGH | Subdomain cookie leakage to C2 traffic | Cookie `Domain` not set; exact-host scoping (Section 3) |
| HIGH | fail2ban bypass via X-Forwarded-For spoofing | `X-Forwarded-For` set to `$remote_addr` (replace, not append); Flask logs from `X-Real-IP` only (Section 4, 6) |
| HIGH | Auth log contradicts OPSEC no-persistence | tmpfs at `/dev/shm/`, 10-min retention with shredding (Section 8) |
| HIGH | Server-level `blocked_agent` intercepts portal | URI-based map exempts `/login` and `/portal/` (Section 6) |
| MEDIUM | Session check via decorators (easy to miss) | `before_request` handler on blueprint (Section 5) |
| MEDIUM | Unbounded session dict | Max 50 sessions + lazy expiry purge (Section 3) |
| MEDIUM | `secure_filename()` empty string edge case | Reject with 400 if empty (Section 4) |
| MEDIUM | Upload filename collision undefined | Reject with 409 (Section 5) |
| MEDIUM | Unpinned pip dependencies | Pinned versions: flask==3.1.*, bcrypt==4.2.*, gunicorn==23.* (Section 6) |
| MEDIUM | Disk exhaustion via uploads | 5GB aggregate cap + 2GB free threshold (Section 5, 9) |
| LOW | Timing oracle on username | Constant-time bcrypt burn on wrong username (Section 3) |
| LOW | Password length DoS via bcrypt | 128-byte max before bcrypt (Section 3) |
| LOW | Flask dev server in production | gunicorn with 1 worker + 2 threads (Section 6) |
| LOW | Missing proxy timeouts and Connection header | Added to all location blocks (Section 6) |
| LOW | No nginx direct-serve block for uploads | `location /uploads/ { deny all; }` (Section 5, 6) |
| LOW | Flask error page information leakage | debug=False, custom 500 handler (Section 4) |
