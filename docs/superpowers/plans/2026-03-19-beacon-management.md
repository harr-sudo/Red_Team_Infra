# Beacon Management (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable REST API on team servers and build a beacon management page in the web app that lists active beacons and allows interaction via console commands.

**Architecture:** The team server starts with `--experimental-db` and a second systemd service (`csrestapi`) exposes the REST API on port 50443. The operator establishes an SSH tunnel (`ssh -L 50443:<ts_ip>:50443 ubuntu@bastion`) and the Flask backend authenticates via JWT bearer token to proxy beacon data to the frontend. The frontend displays a connection status bar, deployment selector, beacon table, and console command interface.

**Tech Stack:** Terraform (HCL), Bash (systemd), Python/Flask, vanilla JS, Cobalt Strike REST API (OpenAPI 3.1.0)

**Known Limitations (Phase 1):**
- Multi-server deployments (redundancy/phases): tunnel connects to primary server only. User can manually adjust IP for other servers.
- Password is pre-set to `password` for ease of REST API auth. For real engagements, change post-deployment via the `set-password.sh` helper on the team server.
- Requires Cobalt Strike 4.12+ (the `rest-server/` directory must exist in the CS archive).

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `webapp/backend/routes/beacon.py` | Flask blueprint: beacon API routes (health, list, interact) |
| `webapp/backend/services/beacon_service.py` | REST API client: auth, token management, beacon operations |

### Modified Files
| File | Change |
|------|--------|
| `terraform/variables.tf` | Add `enable_cs_rest_api` variable |
| `terraform/modules/c2_team_server/variables.tf` | Add `enable_rest_api` variable |
| `terraform/modules/c2_team_server/main.tf` | Pass `enable_rest_api` to templatefile |
| `terraform/scripts/install_cobalt_strike.sh` | Add `--experimental-db` flag + csrestapi systemd service |
| `terraform/main.tf` | Pass `enable_cs_rest_api` to c2_team_server + security modules |
| `terraform/outputs.tf` | Add `rest_api_enabled` / `rest_api_port` to `cs_connection_info` |
| `terraform/modules/security/main.tf` | Add `aws_security_group_rule` for port 50443 from `bastion_sg` |
| `terraform/modules/security/variables.tf` | Add `enable_cs_rest_api` variable |
| `configs/terraform.tfvars.example` | Add `enable_cs_rest_api` example |
| `webapp/backend/app.py` | Register beacon blueprint |
| `webapp/backend/utils/config_parser.py` | Add `enable_cs_rest_api` to tfvars generation |
| `webapp/backend/routes/deploy.py` | Add `/api/deploy/active` endpoint |
| `webapp/frontend/index.html` | REST API toggle in config + full beacon page |
| `webapp/frontend/js/app.js` | Beacon page logic: connection, polling, interaction |
| `webapp/frontend/css/style.css` | Beacon table, connection bar, status badge styles |

---

## Chunk 1: Terraform Infrastructure

### Task 1: Add Terraform Variables

**Files:**
- Modify: `terraform/variables.tf` (after `cobalt_strike_license_secret_name` block, ~line 583)
- Modify: `terraform/modules/c2_team_server/variables.tf` (after last variable, end of file)

- [ ] **Step 1: Add root-level variable**

In `terraform/variables.tf`, after the `cobalt_strike_license_secret_name` variable block (~line 583), add:

```hcl
variable "enable_cs_rest_api" {
  description = "Enable Cobalt Strike REST API server (requires CS 4.12+). Starts team server with --experimental-db and runs csrestapi service on port 50443."
  type        = bool
  default     = false
}
```

- [ ] **Step 2: Add module-level variable**

In `terraform/modules/c2_team_server/variables.tf`, after the last variable (end of file), add:

```hcl
variable "enable_rest_api" {
  description = "Enable Cobalt Strike REST API (--experimental-db + csrestapi service)"
  type        = bool
  default     = false
}
```

- [ ] **Step 3: Update tfvars example**

In `configs/terraform.tfvars.example`, after the CS license section (~line 150), add:

```hcl
# Cobalt Strike REST API (requires CS 4.12+)
# Enables --experimental-db on team server and starts csrestapi service on port 50443.
# Required for beacon management via the web dashboard.
enable_cs_rest_api = false
```

- [ ] **Step 4: Verify**

Run: `cd terraform && terraform validate -var-file=../configs/terraform.tfvars.example`
Expected: Success (new variable has a default value)

- [ ] **Step 5: Commit**

```bash
git add terraform/variables.tf terraform/modules/c2_team_server/variables.tf configs/terraform.tfvars.example
git commit -m "feat: add enable_cs_rest_api terraform variable"
```

---

### Task 2: Update Bootstrap Script

**Files:**
- Modify: `terraform/scripts/install_cobalt_strike.sh:23-31` (template vars)
- Modify: `terraform/scripts/install_cobalt_strike.sh:1072-1090` (systemd service block)
- Modify: `terraform/scripts/install_cobalt_strike.sh:~1110` (after teamserver service start)
- Modify: `terraform/scripts/install_cobalt_strike.sh:1144` (set-password.sh sed)

Note: The script uses plain `echo` for logging — do NOT use `log_info`/`log_warn`/`log_success` (they are not defined).

- [ ] **Step 1: Add template variable**

At the top of `install_cobalt_strike.sh`, after line 31 (`CS_LICENSE_SECRET_NAME="${cs_license_secret_name}"`), add:

```bash
ENABLE_REST_API="${enable_rest_api}"
```

- [ ] **Step 2: Add --experimental-db to ExecStart**

Replace the systemd service creation block (lines 1072-1090). The key change is conditionally appending `--experimental-db`:

```bash
    # Determine if REST API flag is needed
    EXPERIMENTAL_DB_FLAG=""
    if [ "$ENABLE_REST_API" = "true" ]; then
        EXPERIMENTAL_DB_FLAG=" --experimental-db"
        echo "  REST API enabled: adding --experimental-db flag to team server"
    fi

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
```

- [ ] **Step 3: Add csrestapi systemd service**

After the teamserver service enable/start block (~line 1110), add the REST API service:

```bash
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
```

- [ ] **Step 4: Update set-password.sh helper**

At line 1144 in the set-password.sh heredoc, replace the sed command and restart block with:

```bash
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
```

- [ ] **Step 5: Commit**

```bash
git add terraform/scripts/install_cobalt_strike.sh
git commit -m "feat: add --experimental-db and csrestapi systemd service to bootstrap"
```

---

### Task 3: Wire Terraform Module

**Files:**
- Modify: `terraform/modules/c2_team_server/main.tf:25-35` (templatefile vars)
- Modify: `terraform/main.tf:351-395` (c2_team_server module call)
- Modify: `terraform/main.tf:401-449` (c2_phase_servers module call)

- [ ] **Step 1: Add to templatefile vars**

In `terraform/modules/c2_team_server/main.tf`, in the templatefile call (~line 25-35), add after `cs_license_secret_name`:

```hcl
    enable_rest_api            = var.enable_rest_api
```

- [ ] **Step 2: Pass to single/redundancy module**

In `terraform/main.tf`, in the `c2_team_server` module block (~line 351-395), add after the `cs_license_secret_name` line:

```hcl
  enable_rest_api        = var.enable_cs_rest_api
```

- [ ] **Step 3: Pass to phase-based module**

In `terraform/main.tf`, in the `c2_phase_servers` module block (~line 401-449), add after the `cs_license_secret_name` line:

```hcl
  enable_rest_api        = var.enable_cs_rest_api
```

- [ ] **Step 4: Verify**

Run: `cd terraform && terraform validate -var-file=../configs/terraform.tfvars.example`
Expected: Success

- [ ] **Step 5: Commit**

```bash
git add terraform/modules/c2_team_server/main.tf terraform/main.tf
git commit -m "feat: wire enable_rest_api through terraform module chain"
```

---

### Task 4: Update Security Groups and Outputs

**Files:**
- Modify: `terraform/modules/security/main.tf` (add `aws_security_group_rule`)
- Modify: `terraform/modules/security/variables.tf` (add variable)
- Modify: `terraform/main.tf` (pass variable to security module)
- Modify: `terraform/outputs.tf:362-380` (cs_connection_info)

- [ ] **Step 1: Add variable to security module**

In `terraform/modules/security/variables.tf`, add:

```hcl
variable "enable_cs_rest_api" {
  description = "Enable REST API port (50443) access from bastion to C2 servers"
  type        = bool
  default     = false
}
```

- [ ] **Step 2: Add security group rule**

In `terraform/modules/security/main.tf`, near the existing `aws_security_group_rule.c2_from_bastion` rule (~line 166), add a new rule resource following the same pattern:

```hcl
resource "aws_security_group_rule" "c2_rest_api_from_bastion" {
  count                    = var.enable_cs_rest_api ? 1 : 0
  type                     = "ingress"
  from_port                = 50443
  to_port                  = 50443
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.bastion_sg.id
  security_group_id        = aws_security_group.c2_team_server_sg.id
  description              = "CS REST API from bastion (SSH tunnel)"
}
```

Note: Uses `aws_security_group.bastion_sg.id` (not `bastion[0]`) and `aws_security_group_rule` resource (not inline `dynamic "ingress"`), matching the existing pattern.

- [ ] **Step 3: Pass variable to security module**

In `terraform/main.tf`, in the security module call, add:

```hcl
  enable_cs_rest_api = var.enable_cs_rest_api
```

- [ ] **Step 4: Update cs_connection_info output**

In `terraform/outputs.tf`, update the `cs_connection_info` output (~line 362-380) to include REST API info:

```hcl
output "cs_connection_info" {
  description = "Cobalt Strike connection information"
  value = {
    host = local.is_goad_only ? (
      local.deploy_goad && length(module.goad) > 0 ? module.goad[0].jumpbox_public_ip : null
      ) : (
      local.deploy_c2_infra ? (
        local.c2_deployment_mode == "phases" ? (
          length(module.c2_phase_servers) > 0 ? values(module.c2_phase_servers)[0].first_server_private_ip : null
          ) : (
          length(module.c2_team_server) > 0 ? module.c2_team_server[0].first_server_private_ip : null
        )
      ) : null
    )
    port             = var.c2_server_port
    rest_api_enabled = var.enable_cs_rest_api
    rest_api_port    = var.enable_cs_rest_api ? 50443 : null
    method           = local.is_goad_only ? "direct" : "ssh_tunnel"
  }
  sensitive = true
}
```

- [ ] **Step 5: Commit**

```bash
git add terraform/modules/security/main.tf terraform/modules/security/variables.tf terraform/main.tf terraform/outputs.tf
git commit -m "feat: add REST API security group rule and connection info output"
```

---

## Chunk 2: Backend Service

### Task 5: Create Beacon Service

**Files:**
- Create: `webapp/backend/services/beacon_service.py`

This service handles all communication with the Cobalt Strike REST API through the SSH tunnel.

- [ ] **Step 1: Create the service file**

```python
"""
Cobalt Strike REST API client service.

Manages JWT authentication, health checking, and beacon operations
through an SSH tunnel to the team server's REST API (port 50443).
"""

import time
import requests
import urllib3

# Disable SSL warnings for self-signed certs on localhost tunnel
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class BeaconService:
    """Client for the Cobalt Strike REST API."""

    def __init__(self):
        self.base_url = "https://localhost:50443"
        self.token = None
        self.token_expires_at = 0
        self.username = "csrestapi"
        self.password = "password"
        self.token_duration_ms = 3600000  # 1 hour
        self.session = requests.Session()
        self.session.verify = False  # Self-signed cert through SSH tunnel
        self.session.timeout = 10

    def configure(self, password=None, port=None):
        """Update connection settings."""
        if password:
            self.password = password
        if port:
            self.base_url = f"https://localhost:{port}"
        # Clear cached token when config changes
        self.token = None
        self.token_expires_at = 0

    def _authenticate(self):
        """Authenticate and obtain JWT bearer token."""
        try:
            resp = self.session.post(
                f"{self.base_url}/api/auth/login",
                json={
                    "username": self.username,
                    "password": self.password,
                    "durationMs": self.token_duration_ms,
                },
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            self.token = data.get("access_token")
            # Refresh 5 minutes before expiry
            self.token_expires_at = time.time() + (self.token_duration_ms / 1000) - 300
            self.session.headers["Authorization"] = f"Bearer {self.token}"
            return True
        except Exception:
            self.token = None
            self.token_expires_at = 0
            return False

    def _ensure_auth(self):
        """Ensure we have a valid token, re-authenticating if needed."""
        if not self.token or time.time() >= self.token_expires_at:
            return self._authenticate()
        return True

    def health_check(self):
        """Check if REST API is reachable and authenticated.

        Returns dict with status, authenticated, and error fields.
        """
        result = {"reachable": False, "authenticated": False, "error": None}

        # Check if REST API port is reachable
        try:
            self.session.get(f"{self.base_url}/api/v1", timeout=5)
            result["reachable"] = True
        except requests.exceptions.ConnectionError:
            result["error"] = "Connection refused. Is the SSH tunnel running?"
            return result
        except requests.exceptions.Timeout:
            result["error"] = "Connection timed out"
            return result
        except Exception as e:
            result["error"] = str(e)
            return result

        # Check authentication
        if self._ensure_auth():
            result["authenticated"] = True
        else:
            result["error"] = "Authentication failed. Check team server password."

        return result

    def list_beacons(self):
        """List all active beacons."""
        if not self._ensure_auth():
            return {"success": False, "error": "Not authenticated"}

        try:
            resp = self.session.get(f"{self.base_url}/api/v1/beacons")
            resp.raise_for_status()
            beacons = resp.json()
            return {"success": True, "beacons": beacons}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_beacon(self, bid):
        """Get details for a specific beacon."""
        if not self._ensure_auth():
            return {"success": False, "error": "Not authenticated"}

        try:
            resp = self.session.get(f"{self.base_url}/api/v1/beacons/{bid}")
            resp.raise_for_status()
            return {"success": True, "beacon": resp.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def console_command(self, bid, command):
        """Execute a console command on a beacon.

        This is equivalent to typing a command in the Beacon console.
        """
        if not self._ensure_auth():
            return {"success": False, "error": "Not authenticated"}

        try:
            resp = self.session.post(
                f"{self.base_url}/api/v1/beacons/{bid}/consoleCommand",
                json={"input": command},
            )
            resp.raise_for_status()
            return {"success": True, "result": resp.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_beacon_tasks(self, bid):
        """Get task summary for a beacon."""
        if not self._ensure_auth():
            return {"success": False, "error": "Not authenticated"}

        try:
            resp = self.session.get(
                f"{self.base_url}/api/v1/beacons/{bid}/tasks/summary"
            )
            resp.raise_for_status()
            return {"success": True, "tasks": resp.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_task_detail(self, task_id):
        """Get detailed output for a specific task."""
        if not self._ensure_auth():
            return {"success": False, "error": "Not authenticated"}

        try:
            resp = self.session.get(f"{self.base_url}/api/v1/tasks/{task_id}")
            resp.raise_for_status()
            return {"success": True, "task": resp.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def set_sleep(self, bid, sleep_time, jitter=0):
        """Set beacon sleep time and jitter."""
        if not self._ensure_auth():
            return {"success": False, "error": "Not authenticated"}

        try:
            resp = self.session.post(
                f"{self.base_url}/api/v1/beacons/{bid}/state/sleepTime",
                json={"sleepTime": sleep_time, "jitter": jitter},
            )
            resp.raise_for_status()
            return {"success": True, "result": resp.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}


# Singleton instance
beacon_service = BeaconService()
```

- [ ] **Step 2: Commit**

```bash
git add webapp/backend/services/beacon_service.py
git commit -m "feat: add beacon service for CS REST API communication"
```

---

### Task 6: Create Beacon Routes

**Files:**
- Create: `webapp/backend/routes/beacon.py`

Note: Follow existing project conventions — blueprint variable is `bp`, routes use `url_prefix` set during registration.

- [ ] **Step 1: Create the routes file**

```python
"""
Beacon management API routes.

Proxies requests to the Cobalt Strike REST API through the beacon service.
Registered with url_prefix='/api/beacon' in app.py.
"""

from flask import Blueprint, jsonify, request
from webapp.backend.services.beacon_service import beacon_service

bp = Blueprint("beacon", __name__)


@bp.route("/health", methods=["GET"])
def health():
    """Check REST API connection health."""
    result = beacon_service.health_check()
    status = "connected" if result["authenticated"] else (
        "reachable" if result["reachable"] else "disconnected"
    )
    return jsonify({"status": status, **result})


@bp.route("/configure", methods=["POST"])
def configure():
    """Configure REST API connection settings."""
    data = request.get_json() or {}
    password = data.get("password")
    port = data.get("port")

    beacon_service.configure(password=password, port=port)

    # Immediately check health with new config
    result = beacon_service.health_check()
    return jsonify({
        "success": result["authenticated"],
        "health": result,
    })


@bp.route("/list", methods=["GET"])
def list_beacons():
    """List all active beacons."""
    result = beacon_service.list_beacons()
    return jsonify(result)


@bp.route("/<bid>", methods=["GET"])
def get_beacon(bid):
    """Get beacon details."""
    result = beacon_service.get_beacon(bid)
    return jsonify(result)


@bp.route("/<bid>/command", methods=["POST"])
def console_command(bid):
    """Execute a console command on a beacon."""
    data = request.get_json() or {}
    command = data.get("command", "").strip()

    if not command:
        return jsonify({"success": False, "error": "No command provided"}), 400

    result = beacon_service.console_command(bid, command)
    return jsonify(result)


@bp.route("/<bid>/tasks", methods=["GET"])
def get_tasks(bid):
    """Get beacon task summary."""
    result = beacon_service.get_beacon_tasks(bid)
    return jsonify(result)


@bp.route("/task/<task_id>", methods=["GET"])
def get_task_detail(task_id):
    """Get detailed task output."""
    result = beacon_service.get_task_detail(task_id)
    return jsonify(result)


@bp.route("/<bid>/sleep", methods=["POST"])
def set_sleep(bid):
    """Set beacon sleep time."""
    data = request.get_json() or {}
    sleep_time = data.get("sleepTime")
    jitter = data.get("jitter", 0)

    if sleep_time is None:
        return jsonify({"success": False, "error": "sleepTime required"}), 400

    result = beacon_service.set_sleep(bid, sleep_time, jitter)
    return jsonify(result)
```

- [ ] **Step 2: Commit**

```bash
git add webapp/backend/routes/beacon.py
git commit -m "feat: add beacon management API routes"
```

---

### Task 7: Register Blueprint, Config Parser, and Active Deployment Endpoint

**Files:**
- Modify: `webapp/backend/app.py` (register blueprint)
- Modify: `webapp/backend/utils/config_parser.py` (add REST API to tfvars)
- Modify: `webapp/backend/routes/deploy.py` (add `/api/deploy/active` endpoint)

- [ ] **Step 1: Register beacon blueprint**

In `webapp/backend/app.py`, find where other blueprints are registered (lines 33-42) and add, following the existing pattern:

```python
from webapp.backend.routes import beacon
app.register_blueprint(beacon.bp, url_prefix='/api/beacon')
```

- [ ] **Step 2: Add REST API to config parser**

In `webapp/backend/utils/config_parser.py`, in the `generate_tfvars()` method, find the Cobalt Strike Configuration section (~line 172) and add `enable_cs_rest_api` to the keys list:

```python
'Cobalt Strike Configuration': ['cobalt_strike_archive_s3_path', 'cs_teamserver_password', 'cs_teamserver_port', 'cobalt_strike_license_secret_name', 'enable_cs_rest_api'],
```

- [ ] **Step 3: Add active deployment endpoint**

In `webapp/backend/routes/deploy.py`, add this endpoint. Note: `json` and `os` are already imported (lines 11, 14). Use `project_root` (line 19) for path resolution:

```python
@bp.route("/active", methods=["GET"])
def get_active_deployment():
    """Get the most recent successful deployment's state."""
    state_dir = os.path.join(str(project_root), "logs", "deployment_state")

    if not os.path.isdir(state_dir):
        return jsonify({"success": False, "error": "No deployments found"})

    # Find most recent successful deployment
    latest = None
    latest_time = 0
    for fname in os.listdir(state_dir):
        if not fname.endswith(".state.json"):
            continue
        fpath = os.path.join(state_dir, fname)
        try:
            with open(fpath) as f:
                state = json.load(f)
            if state.get("status") == "success" and state.get("completed_at", 0) > latest_time:
                latest = state
                latest_time = state["completed_at"]
        except (json.JSONDecodeError, IOError):
            continue

    if not latest:
        return jsonify({"success": False, "error": "No successful deployment found"})

    return jsonify({"success": True, "deployment": latest})
```

- [ ] **Step 4: Commit**

```bash
git add webapp/backend/app.py webapp/backend/utils/config_parser.py webapp/backend/routes/deploy.py
git commit -m "feat: register beacon blueprint, config parser, and active deployment endpoint"
```

---

## Chunk 3: Frontend UI

### Task 8: Config Page — REST API Toggle

**Files:**
- Modify: `webapp/frontend/index.html` (after CS License section, ~line 954)
- Modify: `webapp/frontend/js/app.js` (saveConfig ~line 2803, loadConfig, toggle handler)

- [ ] **Step 1: Add REST API toggle to config page**

In `webapp/frontend/index.html`, after the CS License Activation section (~line 954), add:

```html
<!-- REST API Configuration -->
<div class="form-group" id="rest-api-group" style="margin-top: 16px;">
    <label class="form-label">
        REST API (Beacon Management)
        <span class="label-hint">Requires Cobalt Strike 4.12+</span>
    </label>
    <div class="toggle-row" style="display: flex; align-items: center; gap: 12px; margin-top: 8px;">
        <label class="toggle-switch">
            <input type="checkbox" id="enable-rest-api" name="enable-rest-api">
            <span class="toggle-slider"></span>
        </label>
        <span style="color: var(--text-secondary);">Enable REST API for beacon management dashboard</span>
    </div>
    <div id="rest-api-info" class="status-display info" style="display: none; margin-top: 12px;">
        <strong>What this does:</strong> Starts the team server with <code>--experimental-db</code> and runs the <code>csrestapi</code> service on port 50443. After deployment, use the Beacon tab to manage beacons.
        <br><br>
        <strong>Password:</strong> The team server password will be pre-set to <code>password</code> for REST API authentication. Change it post-deployment for real engagements via <code>/opt/cobaltstrike/set-password.sh</code>.
    </div>
</div>
```

- [ ] **Step 2: Add toggle behavior in JS**

In `webapp/frontend/js/app.js`, find where CS config radio buttons are handled and add:

```javascript
// REST API toggle behavior
const restApiToggle = document.getElementById('enable-rest-api');
const restApiInfo = document.getElementById('rest-api-info');
if (restApiToggle) {
    restApiToggle.addEventListener('change', function() {
        restApiInfo.style.display = this.checked ? 'block' : 'none';

        // When REST API enabled, auto-set password to 'password' in preset mode
        if (this.checked) {
            const presetRadio = document.querySelector('input[name="cs-pw-mode"][value="preset"]');
            const passwordInput = document.getElementById('cs-preset-password');
            if (presetRadio) presetRadio.checked = true;
            if (passwordInput) {
                passwordInput.value = 'password';
                presetRadio.dispatchEvent(new Event('change'));
            }
        }
    });
}
```

- [ ] **Step 3: Include in saveConfig()**

In the `saveConfig()` function (~line 2803-2931), find where CS config values are collected and add:

```javascript
config.enable_cs_rest_api = document.getElementById('enable-rest-api')?.checked || false;
```

- [ ] **Step 4: Include in loadConfig()**

In the config loading function, add:

```javascript
const restApiToggle = document.getElementById('enable-rest-api');
if (restApiToggle) {
    restApiToggle.checked = config.enable_cs_rest_api === true || config.enable_cs_rest_api === 'true';
    restApiToggle.dispatchEvent(new Event('change'));
}
```

- [ ] **Step 5: Commit**

```bash
git add webapp/frontend/index.html webapp/frontend/js/app.js
git commit -m "feat: add REST API toggle to configuration page"
```

---

### Task 9: Beacon Page — Connection Bar + Beacon Table

**Files:**
- Modify: `webapp/frontend/index.html:1311-1326` (replace beacon placeholder)
- Modify: `webapp/frontend/css/style.css` (beacon styles)

- [ ] **Step 1: Replace beacon page placeholder**

Replace the entire beacon tab-page content (lines 1312-1326) with:

```html
<div class="tab-page" data-page="beacon">
    <h2>Beacon Management</h2>

    <!-- Connection Status Bar -->
    <div class="section-card" id="beacon-connection-bar">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div style="display: flex; align-items: center; gap: 12px;">
                <span class="beacon-status-dot" id="beacon-status-dot"></span>
                <span id="beacon-status-text" style="font-weight: 500;">Checking connection...</span>
            </div>
            <div style="display: flex; gap: 8px;">
                <button class="btn btn-sm" id="beacon-reconnect-btn" onclick="BEACON.checkHealth()" style="display: none;">Reconnect</button>
                <button class="btn btn-sm btn-secondary" id="beacon-refresh-btn" onclick="BEACON.refreshBeacons()" style="display: none;">Refresh</button>
            </div>
        </div>

        <!-- REST API not enabled message -->
        <div id="beacon-not-enabled" style="display: none; margin-top: 16px;">
            <div class="status-display warning">
                REST API is not enabled for the active deployment. Enable it in the <strong>Configuration</strong> tab and redeploy.
            </div>
        </div>

        <!-- SSH Tunnel Instructions (shown when disconnected) -->
        <div id="beacon-tunnel-instructions" style="display: none; margin-top: 16px;">
            <p style="color: var(--text-muted); margin-bottom: 8px; font-size: 0.9em;">
                Run this SSH tunnel command in a separate terminal to connect:
            </p>
            <div class="output-display" id="beacon-tunnel-cmd" style="margin: 0; padding: 12px; font-size: 0.85em; cursor: pointer; position: relative;" onclick="BEACON.copyTunnelCmd()">
                <span id="beacon-tunnel-cmd-text">ssh -L 50443:&lt;team_server_ip&gt;:50443 ubuntu@&lt;bastion_ip&gt; -i ~/.ssh/key</span>
                <span style="position: absolute; right: 12px; top: 50%; transform: translateY(-50%); color: var(--text-muted); font-size: 0.8em;">click to copy</span>
            </div>
            <p style="color: var(--text-muted); margin-top: 8px; font-size: 0.85em;">
                Then click <strong>Reconnect</strong> above once the tunnel is established.
            </p>
        </div>
    </div>

    <!-- Beacon Table -->
    <div class="section-card" id="beacon-table-section" style="display: none;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
            <h3 style="margin: 0;">Active Beacons</h3>
            <span id="beacon-count" class="badge badge-info" style="font-size: 0.85em;">0 beacons</span>
        </div>
        <div class="table-responsive">
            <table class="beacon-table" id="beacon-table">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>User</th>
                        <th>Computer</th>
                        <th>Internal IP</th>
                        <th>OS</th>
                        <th>PID</th>
                        <th>Sleep</th>
                        <th>Last Seen</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="beacon-table-body">
                </tbody>
            </table>
        </div>
        <div id="beacon-empty-state" style="display: none; text-align: center; padding: 40px 20px; color: var(--text-muted);">
            <p>No active beacons. Waiting for callbacks...</p>
        </div>
    </div>

    <!-- Beacon Interaction Panel (shown when a beacon is selected) -->
    <div class="section-card" id="beacon-interact-panel" style="display: none;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
            <h3 style="margin: 0;">
                Interact — <span id="interact-beacon-label" style="color: var(--gold-muted);"></span>
            </h3>
            <button class="btn btn-sm btn-secondary" onclick="BEACON.closeInteract()">Close</button>
        </div>

        <!-- Console Command Input -->
        <div style="display: flex; gap: 8px; margin-bottom: 12px;">
            <input type="text" id="beacon-command-input" class="form-input" placeholder="Enter beacon command (e.g., shell whoami, ls, sleep 5 50)" style="flex: 1; font-family: 'SF Mono', 'Consolas', monospace; font-size: 0.9em;"
                   onkeydown="if(event.key==='Enter') BEACON.sendCommand()">
            <button class="btn btn-sm" onclick="BEACON.sendCommand()">Send</button>
        </div>

        <!-- Command Output -->
        <div class="output-display" id="beacon-command-output" style="min-height: 200px; max-height: 400px;">
            <span style="color: var(--text-muted);">Select a beacon and enter a command above.</span>
        </div>
    </div>
</div>
```

- [ ] **Step 2: Add beacon CSS styles**

In `webapp/frontend/css/style.css`, add at the end of the file. Uses existing custom properties from palette.css (`--bg-card-hover`, `--border`, etc.):

```css
/* ===== Beacon Management Page ===== */

.beacon-status-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--text-muted);
    display: inline-block;
    transition: background 0.3s ease;
}

.beacon-status-dot.connected {
    background: var(--success-text);
    box-shadow: 0 0 6px var(--success-text);
}

.beacon-status-dot.reachable {
    background: var(--warning-text);
    box-shadow: 0 0 6px var(--warning-text);
}

.beacon-status-dot.disconnected {
    background: var(--danger-text);
    box-shadow: 0 0 6px var(--danger-text);
}

.beacon-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9em;
}

.beacon-table thead th {
    text-align: left;
    padding: 10px 12px;
    color: var(--text-muted);
    font-weight: 500;
    font-size: 0.85em;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
}

.beacon-table tbody tr {
    cursor: pointer;
    transition: background 0.15s ease;
}

.beacon-table tbody tr:hover {
    background: var(--bg-card-hover);
}

.beacon-table tbody tr.selected {
    background: var(--info-bg);
    border-left: 3px solid var(--brand-light);
}

.beacon-table tbody td {
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    color: var(--text-primary);
    white-space: nowrap;
}

.beacon-table .beacon-id {
    font-family: 'SF Mono', 'Consolas', monospace;
    font-size: 0.85em;
    color: var(--gold-muted);
}

.beacon-table .beacon-admin {
    color: var(--danger-text);
    font-weight: 600;
}

.beacon-table .beacon-last-seen {
    color: var(--text-muted);
    font-size: 0.85em;
}

.beacon-table .beacon-last-seen.stale {
    color: var(--warning-text);
}

.beacon-table .beacon-last-seen.dead {
    color: var(--danger-text);
}

.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 0.8em;
    font-weight: 500;
}

.badge-info {
    background: var(--info-bg);
    color: var(--info-text);
    border: 1px solid var(--info-border);
}

.table-responsive {
    overflow-x: auto;
}
```

- [ ] **Step 3: Commit**

```bash
git add webapp/frontend/index.html webapp/frontend/css/style.css
git commit -m "feat: build beacon page with connection bar, table, and interaction panel"
```

---

### Task 10: Beacon Page JavaScript

**Files:**
- Modify: `webapp/frontend/js/app.js` (add BEACON object and all logic)

- [ ] **Step 1: Add BEACON namespace**

In `webapp/frontend/js/app.js`, add the BEACON object after the APP object initialization. All beacon data is HTML-escaped via `escapeHtml()` to prevent XSS from beacon metadata:

```javascript
// ===== Beacon Management =====
const BEACON = {
    pollInterval: null,
    selectedBid: null,
    connectionStatus: 'disconnected', // disconnected | reachable | connected
    tunnelCmd: '',
    restApiEnabled: null, // null = unknown, true/false from deployment

    init() {
        this.loadTunnelCommand();
        this.startHealthPoll();
    },

    async loadTunnelCommand() {
        try {
            const resp = await fetch('/api/deploy/active');
            if (!resp.ok) return;
            const data = await resp.json();
            if (data.success && data.deployment) {
                const outputs = data.deployment.output || {};
                const csInfo = outputs.cs_connection_info?.value;
                const bastionIp = outputs.bastion_public_ip?.value;
                const tsIp = csInfo?.host;

                // Check if REST API was enabled for this deployment
                if (csInfo && csInfo.rest_api_enabled === false) {
                    this.restApiEnabled = false;
                    document.getElementById('beacon-not-enabled').style.display = 'block';
                    document.getElementById('beacon-tunnel-instructions').style.display = 'none';
                    return;
                }
                this.restApiEnabled = csInfo?.rest_api_enabled || null;

                if (tsIp && bastionIp) {
                    const keyPath = outputs.ssh_key_path?.value || '~/.ssh/red_team_key';
                    this.tunnelCmd = `ssh -L 50443:${tsIp}:50443 ubuntu@${bastionIp} -i ${keyPath}`;
                    const cmdEl = document.getElementById('beacon-tunnel-cmd-text');
                    if (cmdEl) cmdEl.textContent = this.tunnelCmd;
                }
            }
        } catch (e) {
            // Silent fail — user can still manually set up tunnel
        }
    },

    async checkHealth() {
        if (this.restApiEnabled === false) return null;
        try {
            const resp = await fetch('/api/beacon/health');
            const data = await resp.json();
            this.updateConnectionStatus(data.status, data.error);
            return data;
        } catch (e) {
            this.updateConnectionStatus('disconnected', 'Backend unreachable');
            return null;
        }
    },

    updateConnectionStatus(status, error) {
        this.connectionStatus = status;
        const dot = document.getElementById('beacon-status-dot');
        const text = document.getElementById('beacon-status-text');
        const tunnelInstr = document.getElementById('beacon-tunnel-instructions');
        const reconnectBtn = document.getElementById('beacon-reconnect-btn');
        const refreshBtn = document.getElementById('beacon-refresh-btn');
        const tableSection = document.getElementById('beacon-table-section');

        if (!dot || !text) return;

        dot.className = 'beacon-status-dot';

        if (status === 'connected') {
            dot.classList.add('connected');
            text.textContent = 'Connected to REST API';
            text.style.color = 'var(--success-text)';
            tunnelInstr.style.display = 'none';
            reconnectBtn.style.display = 'none';
            refreshBtn.style.display = 'inline-block';
            tableSection.style.display = 'block';
            this.refreshBeacons();
        } else if (status === 'reachable') {
            dot.classList.add('reachable');
            text.textContent = 'Reachable but auth failed' + (error ? `: ${error}` : '');
            text.style.color = 'var(--warning-text)';
            tunnelInstr.style.display = 'none';
            reconnectBtn.style.display = 'inline-block';
            refreshBtn.style.display = 'none';
            tableSection.style.display = 'none';
        } else {
            dot.classList.add('disconnected');
            text.textContent = error || 'Disconnected';
            text.style.color = 'var(--danger-text)';
            tunnelInstr.style.display = 'block';
            reconnectBtn.style.display = 'inline-block';
            refreshBtn.style.display = 'none';
            tableSection.style.display = 'none';
        }
    },

    startHealthPoll() {
        if (this.pollInterval) clearInterval(this.pollInterval);
        this.pollInterval = setInterval(() => {
            if (this.connectionStatus === 'connected') {
                this.refreshBeacons();
            } else {
                this.checkHealth();
            }
        }, 20000);
        this.checkHealth();
    },

    stopHealthPoll() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    },

    async refreshBeacons() {
        try {
            const resp = await fetch('/api/beacon/list');
            const data = await resp.json();
            if (!data.success) {
                this.checkHealth();
                return;
            }
            this.renderBeaconTable(data.beacons || []);
        } catch (e) {
            this.checkHealth();
        }
    },

    renderBeaconTable(beacons) {
        const tbody = document.getElementById('beacon-table-body');
        const countEl = document.getElementById('beacon-count');
        const emptyState = document.getElementById('beacon-empty-state');
        const table = document.getElementById('beacon-table');
        if (!tbody) return;

        countEl.textContent = `${beacons.length} beacon${beacons.length !== 1 ? 's' : ''}`;

        if (beacons.length === 0) {
            tbody.innerHTML = '';
            table.style.display = 'none';
            emptyState.style.display = 'block';
            return;
        }

        table.style.display = 'table';
        emptyState.style.display = 'none';

        // Escape ALL beacon data to prevent XSS from beacon metadata
        tbody.innerHTML = beacons.map(b => {
            const isAdmin = b.isAdmin ? ' *' : '';
            const userClass = b.isAdmin ? 'beacon-admin' : '';
            const lastSeen = this.formatLastSeen(b.lastCheckin || b.last);
            const lastSeenClass = this.getLastSeenClass(b.lastCheckin || b.last, b.sleep);
            const selected = b.bid === this.selectedBid ? 'selected' : '';
            const sleepStr = b.sleep ? `${Math.round(b.sleep / 1000)}s` : '\u2014';
            const jitterStr = b.jitter ? ` (${b.jitter}%)` : '';
            const eBid = this.escapeHtml(b.bid || '\u2014');
            const eUser = this.escapeHtml(b.user || '\u2014');
            const eComputer = this.escapeHtml(b.computer || '\u2014');
            const eInternal = this.escapeHtml(b.internal || '\u2014');
            const eOs = this.escapeHtml(b.os || '\u2014');
            const ePid = this.escapeHtml(String(b.pid || '\u2014'));
            const label = `${eUser}@${eComputer}`;

            return `<tr class="${selected}" data-bid="${eBid}" onclick="BEACON.selectBeacon('${eBid}', '${label}')">
                <td class="beacon-id">${eBid}</td>
                <td class="${userClass}">${eUser}${isAdmin}</td>
                <td>${eComputer}</td>
                <td>${eInternal}</td>
                <td>${eOs}</td>
                <td>${ePid}</td>
                <td>${sleepStr}${jitterStr}</td>
                <td class="beacon-last-seen ${lastSeenClass}">${lastSeen}</td>
                <td><button class="btn btn-sm" onclick="event.stopPropagation(); BEACON.selectBeacon('${eBid}', '${label}')">Interact</button></td>
            </tr>`;
        }).join('');
    },

    formatLastSeen(timestamp) {
        if (!timestamp) return '\u2014';
        const now = Date.now();
        const ts = typeof timestamp === 'number' ? timestamp : new Date(timestamp).getTime();
        const diffSec = Math.floor((now - ts) / 1000);
        if (diffSec < 60) return `${diffSec}s ago`;
        if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
        if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
        return `${Math.floor(diffSec / 86400)}d ago`;
    },

    getLastSeenClass(timestamp, sleepMs) {
        if (!timestamp) return 'dead';
        const now = Date.now();
        const ts = typeof timestamp === 'number' ? timestamp : new Date(timestamp).getTime();
        const diffMs = now - ts;
        const threshold = (sleepMs || 60000) * 3;
        if (diffMs > threshold * 5) return 'dead';
        if (diffMs > threshold) return 'stale';
        return '';
    },

    selectBeacon(bid, label) {
        this.selectedBid = bid;
        const panel = document.getElementById('beacon-interact-panel');
        const labelEl = document.getElementById('interact-beacon-label');
        const output = document.getElementById('beacon-command-output');
        const input = document.getElementById('beacon-command-input');

        if (panel) panel.style.display = 'block';
        if (labelEl) labelEl.textContent = `${label} (${bid})`;
        if (output) output.innerHTML = `<span style="color: var(--text-muted);">Interacting with beacon ${bid}. Enter a command above.</span>`;
        if (input) input.focus();

        document.querySelectorAll('.beacon-table tbody tr').forEach(tr => tr.classList.remove('selected'));
        document.querySelectorAll('.beacon-table tbody tr').forEach(tr => {
            if (tr.dataset.bid === bid) tr.classList.add('selected');
        });
    },

    closeInteract() {
        this.selectedBid = null;
        const panel = document.getElementById('beacon-interact-panel');
        if (panel) panel.style.display = 'none';
        document.querySelectorAll('.beacon-table tbody tr').forEach(tr => tr.classList.remove('selected'));
    },

    async sendCommand() {
        const input = document.getElementById('beacon-command-input');
        const output = document.getElementById('beacon-command-output');
        const command = input?.value?.trim();
        if (!command || !this.selectedBid) return;

        output.innerHTML += `\n<span style="color: var(--gold-muted);">beacon&gt;</span> ${this.escapeHtml(command)}\n`;
        input.value = '';

        try {
            const resp = await fetch(`/api/beacon/${this.selectedBid}/command`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command }),
            });
            const data = await resp.json();
            if (data.success) {
                const taskId = data.result?.taskId;
                if (taskId) {
                    output.innerHTML += `<span style="color: var(--text-muted);">[*] Task ${taskId} queued</span>\n`;
                    this.pollTaskOutput(taskId, output);
                } else {
                    output.innerHTML += `<span style="color: var(--success-text);">[+] Command sent</span>\n`;
                }
            } else {
                output.innerHTML += `<span style="color: var(--danger-text);">[-] ${this.escapeHtml(data.error || 'Command failed')}</span>\n`;
            }
        } catch (e) {
            output.innerHTML += `<span style="color: var(--danger-text);">[-] Error: ${this.escapeHtml(e.message)}</span>\n`;
        }
        output.scrollTop = output.scrollHeight;
    },

    async pollTaskOutput(taskId, outputEl, attempts = 0) {
        // Bail if connection dropped or max attempts reached
        if (this.connectionStatus !== 'connected' || attempts > 30) {
            if (attempts > 30) {
                outputEl.innerHTML += `<span style="color: var(--warning-text);">[!] Task ${taskId} — timed out waiting for output</span>\n`;
            }
            return;
        }

        const delay = attempts < 5 ? 2000 : 5000;
        await new Promise(r => setTimeout(r, delay));

        try {
            const resp = await fetch(`/api/beacon/task/${taskId}`);
            const data = await resp.json();
            if (data.success && data.task) {
                const status = data.task.taskStatus || data.task.status;
                if (status === 'OutputReceived' || status === 'Completed') {
                    const results = data.task.result || data.task.results || [];
                    if (results.length > 0) {
                        results.forEach(r => {
                            outputEl.innerHTML += `${this.escapeHtml(typeof r === 'string' ? r : JSON.stringify(r))}\n`;
                        });
                    }
                    outputEl.scrollTop = outputEl.scrollHeight;
                    return;
                }
            }
        } catch (e) { /* retry */ }

        this.pollTaskOutput(taskId, outputEl, attempts + 1);
    },

    escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    },

    copyTunnelCmd() {
        if (this.tunnelCmd) {
            navigator.clipboard.writeText(this.tunnelCmd);
            const el = document.getElementById('beacon-tunnel-cmd');
            if (el) {
                el.style.borderColor = 'var(--success-border)';
                setTimeout(() => { el.style.borderColor = ''; }, 1500);
            }
        }
    },
};
```

- [ ] **Step 2: Hook into page navigation**

In the `loadPageContent()` function (~line 216-266), update the beacon case (~line 254):

```javascript
case 'beacon':
    BEACON.init();
    break;
```

And in `navigateTo()`, before changing `currentPage`, add cleanup:

```javascript
// Stop beacon polling when leaving beacon page
if (APP.currentPage === 'beacon') {
    BEACON.stopHealthPoll();
}
```

- [ ] **Step 3: Commit**

```bash
git add webapp/frontend/js/app.js
git commit -m "feat: add beacon page JavaScript with health polling and command interaction"
```

---

## Chunk 4: Verification

### Task 11: End-to-End User Flow Verification

- [ ] **Step 1: Verify Terraform**

```bash
cd terraform
terraform validate -var-file=../configs/terraform.tfvars.example
terraform plan -var-file=../configs/terraform.tfvars.example -var='enable_cs_rest_api=true'
```

Verify:
- `--experimental-db` appears in the team server user_data
- csrestapi systemd service is created
- `aws_security_group_rule.c2_rest_api_from_bastion` exists
- `cs_connection_info` includes `rest_api_enabled` and `rest_api_port`

- [ ] **Step 2: Verify Web App Starts**

```bash
cd webapp && python3 backend/app.py
```

Verify:
- No import errors
- Beacon blueprint registered (check startup logs for `/api/beacon/` routes)
- `http://127.0.0.1:5000` loads without errors

- [ ] **Step 3: Verify Config Page**

1. Open http://127.0.0.1:5000 → Configuration tab
2. Scroll to Cobalt Strike section
3. Toggle "Enable REST API" — verify:
   - Info box appears (using `.status-display.info` styling)
   - Password mode auto-switches to "preset" with "password" pre-filled
4. Save config → verify `enable_cs_rest_api = true` in `configs/terraform.tfvars`

- [ ] **Step 4: Verify Beacon Page (Disconnected State)**

1. Click Beacon tab
2. Verify connection bar shows "Disconnected" with red dot
3. Verify SSH tunnel command is displayed (placeholder IPs if no deployment exists)
4. Verify "Reconnect" button is visible
5. Verify beacon table is hidden
6. If no REST API deployment: verify "REST API not enabled" warning shows

- [ ] **Step 5: Verify API Endpoints**

```bash
# Health check (should return disconnected — no tunnel)
curl -s http://127.0.0.1:5000/api/beacon/health | python3 -m json.tool

# Active deployment (should return no deployment or deployment info)
curl -s http://127.0.0.1:5000/api/deploy/active | python3 -m json.tool
```

- [ ] **Step 6: Final Commit**

```bash
git add -A
git commit -m "feat: beacon management phase 1 — REST API integration with health polling and console commands"
```

---

## User Flow Summary

```
1. CONFIGURE
   └─ Configuration tab → enable "REST API" toggle
      └─ Password auto-set to "password", mode to "preset"
      └─ Save config → enable_cs_rest_api = true in tfvars

2. DEPLOY
   └─ Deployment tab → deploy as normal
      └─ Team server starts with --experimental-db
      └─ csrestapi service starts on port 50443 (after 15s delay)
      └─ Security group allows 50443 from bastion

3. CONNECT
   └─ Beacon tab → shows "Disconnected" with SSH tunnel command
      └─ Command auto-populated from deployment outputs:
         ssh -L 50443:<ts_private_ip>:50443 ubuntu@<bastion_ip> -i <key_path>
      └─ User runs command in separate terminal
      └─ Clicks "Reconnect" (or waits for 20s auto-poll)

4. MONITOR
   └─ Status dot turns green → "Connected to REST API"
      └─ Beacon table appears, auto-refreshes every 20s
      └─ Shows: ID, User, Computer, IP, OS, PID, Sleep, Last Seen

5. INTERACT
   └─ Click beacon row or "Interact" button
      └─ Interaction panel opens with console command input
      └─ Type command (e.g., "shell whoami") → Send
      └─ Task ID returned, output polled and displayed
      └─ Multiple commands accumulate in output panel
      └─ Connection drop detected → polling stops, status reverts

EDGE CASES HANDLED:
- REST API not enabled → warning message with instructions
- CS < 4.12 (no rest-server dir) → bootstrap logs warning, skips
- SSH tunnel drops → health poll detects within 20s, UI reverts
- JWT token expires → auto-refreshes 5 min before expiry
- Multi-server deployment → tunnels to primary server (known limitation)
```
