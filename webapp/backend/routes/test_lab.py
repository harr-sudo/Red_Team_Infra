"""
Test Lab API Routes — provisioning + status for the bolt-on validation lab.

Spec: docs/internal/TESTLAB_DESIGN.md

The terraform module at terraform/modules/test_lab/ stands up 4 EC2 hosts
inside the C2 VPC (tldc01 DC, tlms01 member server, tlws01 workstation,
tllinux01 standalone Linux). This route file owns the dashboard wiring:

  - POST /api/test_lab/provision/<project>  → write inventory + secrets
        to the jumpbox, kick off the Ansible playbook chain.
  - GET  /api/test_lab/status/<project>     → poll remote PID + exit-code
        sentinel; returns running / success / failed / idle.
  - GET  /api/test_lab/hosts/<project>      → return the 4-host inventory
        out of terraform state for the bolt-on UI.

Mirrors the pattern in webapp/backend/routes/goad.py (paramiko SSH to the
jumpbox, nohup'd Ansible, PID-tracked status). The bolt-on facts service
reads from this module's hosts endpoint when ``enable_test_lab=true``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

import yaml
from flask import Blueprint, jsonify

bp = Blueprint("test_lab", __name__, url_prefix="/api/test_lab")

# ---------------------------------------------------------------------------
# Constants — kept in sync with terraform/modules/test_lab/outputs.tf and
# the Ansible playbooks at ansible/playbooks/testlab/.
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STATE_DIR = PROJECT_ROOT / "logs" / "deployment_state"
CONFIGS_DIR = PROJECT_ROOT / "configs"
TERRAFORM_DIR = PROJECT_ROOT / "terraform"
TESTLAB_WORKSPACE = PROJECT_ROOT / "logs" / "testlab_workspace"

# Where the inventory + secrets land on the jumpbox. The playbooks expect
# these exact paths (see ansible/playbooks/testlab/testlab_join.yml).
REMOTE_LAB_DIR = "/home/ubuntu/test_lab"
REMOTE_INVENTORY_PATH = f"{REMOTE_LAB_DIR}/inventory.yml"
REMOTE_SECRETS_PATH = f"{REMOTE_LAB_DIR}/secrets.yml"
REMOTE_LOG_PATH = f"{REMOTE_LAB_DIR}/provision.log"
REMOTE_EXITCODE_PATH = f"{REMOTE_LAB_DIR}/last_exit_code"
REMOTE_PIDFILE_PATH = f"{REMOTE_LAB_DIR}/provision.pid"

# Hardcoded weak creds — intentional per the design spec. These exist in
# the catalog because every bolt-on that targets the lab needs to know
# them; storing them in Secrets Manager would imply they're secret and
# they're explicitly not.
TESTLAB_DOMAIN = "testlab.local"
TESTLAB_NETBIOS = "TESTLAB"
TESTLAB_ANSIBLE_USER = "ansible"
TESTLAB_ANSIBLE_PASSWORD = "Ansible123!"
TESTLAB_DOMAIN_ADMIN_PASSWORD = "Password1!"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state_file_for(project: str) -> Path:
    """Resolve the per-project state.json path (no traversal — name only)."""
    safe = re.sub(r"[^A-Za-z0-9_\-]", "_", project)
    return STATE_DIR / f"{safe}.state.json"


def _tfvars_for(project: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_\-]", "_", project)
    return CONFIGS_DIR / f"{safe}.tfvars"


def _read_state(project: str) -> dict | None:
    path = _state_file_for(project)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _read_tfvars_flag(project: str, key: str) -> str | None:
    """Tiny grep-style tfvars reader — pulls one scalar value by key.

    Doesn't pull in ConfigParser because we only need two booleans here
    and ConfigParser does a full sweep + has surprising fallbacks for
    list parsing. Returns the raw string value (`true`, `false`, `"…"`).
    """
    path = _tfvars_for(project)
    if not path.exists():
        return None
    try:
        content = path.read_text()
    except OSError:
        return None
    # Match: key = value  (value may be quoted or bare)
    match = re.search(
        rf'^\s*{re.escape(key)}\s*=\s*(?P<val>"[^"]*"|\S+)', content, re.MULTILINE
    )
    if not match:
        return None
    return match.group("val").strip().strip('"')


def _test_lab_enabled(project: str) -> bool:
    """True iff the project's tfvars has enable_test_lab=true."""
    raw = _read_tfvars_flag(project, "enable_test_lab")
    return (raw or "").lower() == "true"


def _test_lab_subnet_cidr(project: str) -> str:
    raw = _read_tfvars_flag(project, "test_lab_subnet_cidr")
    return raw or "10.0.20.0/24"


def _read_host_inventory_from_state(state: dict) -> dict | None:
    """Extract the test_lab module's host_inventory output from state JSON.

    The state file mirrors `terraform output -json`, so we read
    output.test_lab_host_inventory.value when present.
    """
    outputs = state.get("output") or {}
    block = outputs.get("test_lab_host_inventory")
    if not isinstance(block, dict):
        return None
    val = block.get("value")
    if isinstance(val, dict) and val:
        return val
    return None


def _fetch_host_inventory_via_terraform() -> dict | None:
    """Last-resort path — query `terraform output` directly. Used when the
    state.json doesn't yet carry the test_lab_host_inventory output (e.g.
    the operator Applied with the flag but the state file was written by
    an older deploy_service version)."""
    try:
        result = subprocess.run(
            ["terraform", "output", "-json", "test_lab_host_inventory"],
            cwd=str(TERRAFORM_DIR),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) and data else None


def _resolve_jumpbox_ip(state: dict) -> str | None:
    """Pull the GOAD jumpbox public IP from the state.json outputs.

    For goad/combined deployments we prefer goad_jumpbox_public_ip and try
    the other jumpbox output keys in order.
    """
    outputs = state.get("output") or {}
    for key in (
        "goad_jumpbox_public_ip",
        "goad_jumpbox_ip",
        "jumpbox_public_ip",
        "jumpbox_ip",
    ):
        block = outputs.get(key)
        if isinstance(block, dict):
            val = block.get("value")
            if isinstance(val, str) and val.strip():
                return val.strip()
        elif isinstance(block, str) and block.strip():
            return block.strip()
    return None


def _ssh_key_path() -> str:
    """Best-effort: honor TESTLAB_SSH_KEY env override, else default to the
    operator's id_ed25519. Same fallback chain as goad.py."""
    override = os.environ.get("TESTLAB_SSH_KEY")
    if override:
        return os.path.expanduser(override)
    return os.path.expanduser("~/.ssh/id_ed25519")


def _build_inventory_yaml(host_inventory: dict) -> str:
    """Render the Ansible inventory YAML the testlab playbooks expect.

    Group layout is locked by ansible/playbooks/testlab/*.yml:
      - domain_controllers   → tldc01
      - member_servers       → tlms01
      - workstations         → tlws01
      - linux_members        → tllinux01

    Windows hosts get WinRM/NTLM/5985 connection vars; the Linux host
    gets SSH with the jumpbox key.
    """
    groups: dict[str, dict] = {
        "domain_controllers": {"hosts": {}},
        "member_servers": {"hosts": {}},
        "workstations": {"hosts": {}},
        "linux_members": {"hosts": {}},
    }

    role_to_group = {
        "domain_controller": "domain_controllers",
        "member_server": "member_servers",
        "workstation": "workstations",
        "linux_member": "linux_members",
    }

    for hostname, meta in host_inventory.items():
        if not isinstance(meta, dict):
            continue
        group = role_to_group.get(str(meta.get("role", "")).lower())
        if not group:
            continue
        private_ip = meta.get("private_ip")
        if not private_ip:
            continue
        host_entry: dict[str, object] = {"ansible_host": private_ip}
        if meta.get("os_family") == "windows":
            host_entry.update(
                {
                    "ansible_user": TESTLAB_ANSIBLE_USER,
                    "ansible_password": "{{ vault_ansible_password }}",
                    "ansible_connection": "winrm",
                    "ansible_winrm_transport": "ntlm",
                    "ansible_port": 5985,
                    "ansible_winrm_server_cert_validation": "ignore",
                }
            )
        else:
            host_entry.update(
                {
                    "ansible_user": "ubuntu",
                    "ansible_connection": "ssh",
                    "ansible_python_interpreter": "/usr/bin/python3",
                    "ansible_ssh_common_args": "-o StrictHostKeyChecking=no",
                }
            )
        groups[group]["hosts"][hostname] = host_entry

    inventory = {
        "all": {
            "vars": {
                "testlab_domain": TESTLAB_DOMAIN,
                "testlab_netbios": TESTLAB_NETBIOS,
            },
            "children": groups,
        }
    }
    return yaml.safe_dump(inventory, sort_keys=False, default_flow_style=False)


def _build_secrets_yaml() -> str:
    """The vault file lives next to inventory.yml on the jumpbox.

    Per spec the creds are intentionally weak + public — we still ship
    them through a separate file so the playbooks can ref them via the
    standard ``vault_*`` pattern (and so a future encrypted-vault swap
    doesn't require playbook surgery).
    """
    return yaml.safe_dump(
        {
            "vault_ansible_password": TESTLAB_ANSIBLE_PASSWORD,
            "vault_domain_admin_password": TESTLAB_DOMAIN_ADMIN_PASSWORD,
        },
        sort_keys=True,
        default_flow_style=False,
    )


def _ssh_cmd(jumpbox_ip: str, key_path: str, remote_cmd: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10",
            "-i", key_path,
            f"ubuntu@{jumpbox_ip}",
            remote_cmd,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _scp_text_to_jumpbox(
    jumpbox_ip: str,
    key_path: str,
    remote_path: str,
    content: str,
    timeout: int = 60,
) -> subprocess.CompletedProcess:
    """Write `content` to `remote_path` on the jumpbox. Uses an SSH stdin
    pipe rather than scp so we don't have to materialize a tempfile."""
    return subprocess.run(
        [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10",
            "-i", key_path,
            f"ubuntu@{jumpbox_ip}",
            f"mkdir -p {REMOTE_LAB_DIR} && cat > {remote_path} && chmod 600 {remote_path}",
        ],
        input=content,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@bp.route("/hosts/<project>", methods=["GET"])
def get_hosts(project: str):
    """Return the test lab host inventory for a project.

    Shape:
        { success: bool, hosts: [
            { name, role, os_family, private_ip, instance_id }, ...
        ]}
    """
    # 2026-05-22 — demo deployment serves canned test-lab hosts so the
    # Manage pane + Bolt-ons rail item render fully in showcase mode.
    from webapp.backend.services import demo_data_service
    if demo_data_service.is_demo_project(project):
        return jsonify({
            "success": True, "enabled": True,
            "hosts": [
                {"name": h["name"], "role": h["role"],
                 "os_family": "windows" if "windows" in h["os"].lower() else "linux",
                 "private_ip": h["ip"], "instance_id": f"i-0demo{h['name']}"}
                for h in demo_data_service.lab_hosts()
            ],
            "is_demo": True,
        })

    state = _read_state(project)
    if state is None:
        return jsonify({"success": False, "error": f"No deployment state for '{project}'"}), 404

    if not _test_lab_enabled(project):
        return jsonify(
            {
                "success": True,
                "enabled": False,
                "hosts": [],
                "message": "enable_test_lab is false for this project",
            }
        )

    host_inventory = _read_host_inventory_from_state(state)
    if host_inventory is None:
        host_inventory = _fetch_host_inventory_via_terraform()
    if not host_inventory:
        return jsonify(
            {
                "success": True,
                "enabled": True,
                "hosts": [],
                "message": "Test lab enabled but host_inventory not yet available — has terraform apply completed?",
            }
        )

    hosts = []
    for name, meta in host_inventory.items():
        if not isinstance(meta, dict):
            continue
        hosts.append(
            {
                "name": name,
                "role": meta.get("role"),
                "os_family": meta.get("os_family"),
                "private_ip": meta.get("private_ip"),
                "instance_id": meta.get("instance_id"),
            }
        )
    # Stable order so the UI doesn't flicker between requests
    hosts.sort(key=lambda h: h.get("name") or "")
    return jsonify({"success": True, "enabled": True, "hosts": hosts})


@bp.route("/provision/<project>", methods=["POST"])
def provision(project: str):
    """Kick off Ansible provisioning on the jumpbox.

    1. Verifies the project exists + test lab is enabled.
    2. Builds inventory.yml + secrets.yml from terraform outputs.
    3. SSHes to the jumpbox, writes both files under /home/ubuntu/test_lab/.
    4. Re-runs are allowed only when no provision is currently active —
       a stale PID file is fine, an actively-running playbook gets a 409.
    5. Launches ansible-playbook under nohup; records remote PID locally.

    Returns {success, pid, log_path}.
    """
    state = _read_state(project)
    if state is None:
        return jsonify({"success": False, "error": f"No deployment state for '{project}'"}), 404
    if not _test_lab_enabled(project):
        return jsonify({"success": False, "error": "enable_test_lab is false for this project"}), 400

    host_inventory = _read_host_inventory_from_state(state) or _fetch_host_inventory_via_terraform()
    if not host_inventory:
        return jsonify(
            {
                "success": False,
                "error": "test_lab_host_inventory not in terraform outputs — apply may still be in flight",
            }
        ), 409

    jumpbox_ip = _resolve_jumpbox_ip(state)
    if not jumpbox_ip:
        return jsonify(
            {
                "success": False,
                "error": "Could not resolve jumpbox IP from deployment outputs",
            }
        ), 500

    key_path = _ssh_key_path()
    if not os.path.exists(key_path):
        return jsonify(
            {
                "success": False,
                "error": f"SSH key not found at {key_path}. Set TESTLAB_SSH_KEY or distribute the operator key.",
            }
        ), 500

    # Concurrency guard — check whether a prior provision is still running.
    # We do this BEFORE writing files so a re-run that's blocked doesn't
    # clobber the in-flight playbook's inventory state.
    try:
        check = _ssh_cmd(
            jumpbox_ip,
            key_path,
            f"if [ -f {REMOTE_PIDFILE_PATH} ] && kill -0 $(cat {REMOTE_PIDFILE_PATH}) 2>/dev/null; "
            f"then echo BUSY; else echo IDLE; fi",
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Timed out reaching jumpbox"}), 504
    if check.returncode != 0:
        return jsonify(
            {
                "success": False,
                "error": "Cannot SSH to jumpbox",
                "stderr": (check.stderr or "").strip(),
            }
        ), 502
    if check.stdout.strip() == "BUSY":
        return jsonify(
            {
                "success": False,
                "error": "A provisioning run is already in progress — wait for it to finish or call /status to monitor.",
            }
        ), 409

    inventory_yaml = _build_inventory_yaml(host_inventory)
    secrets_yaml = _build_secrets_yaml()

    try:
        inv_result = _scp_text_to_jumpbox(jumpbox_ip, key_path, REMOTE_INVENTORY_PATH, inventory_yaml)
        if inv_result.returncode != 0:
            return jsonify(
                {
                    "success": False,
                    "error": "Failed to write inventory.yml to jumpbox",
                    "stderr": (inv_result.stderr or "").strip(),
                }
            ), 500
        sec_result = _scp_text_to_jumpbox(jumpbox_ip, key_path, REMOTE_SECRETS_PATH, secrets_yaml)
        if sec_result.returncode != 0:
            return jsonify(
                {
                    "success": False,
                    "error": "Failed to write secrets.yml to jumpbox",
                    "stderr": (sec_result.stderr or "").strip(),
                }
            ), 500
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Timed out writing files to jumpbox"}), 504

    # Kick off Ansible. The script:
    #   1. Reset any stale exit-code sentinel
    #   2. Run ansible-playbook with the inventory + the vault secrets
    #   3. Persist exit code + PID for the /status route
    launch = (
        f"cd /home/ubuntu && "
        f"rm -f {REMOTE_EXITCODE_PATH} && "
        f"nohup bash -c '"
        f"  cd /home/ubuntu && "
        f"  ansible-playbook "
        f"    -i {REMOTE_INVENTORY_PATH} "
        f"    -e @{REMOTE_SECRETS_PATH} "
        f"    /home/ubuntu/Red_Team_Infra/ansible/playbooks/testlab/main.yml "
        f"    > {REMOTE_LOG_PATH} 2>&1; "
        f"  echo $? > {REMOTE_EXITCODE_PATH}"
        f"' > /dev/null 2>&1 & "
        f"echo $! > {REMOTE_PIDFILE_PATH}; "
        f"cat {REMOTE_PIDFILE_PATH}"
    )

    try:
        run = _ssh_cmd(jumpbox_ip, key_path, launch, timeout=30)
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Timed out launching Ansible on jumpbox"}), 504

    if run.returncode != 0:
        return jsonify(
            {
                "success": False,
                "error": "Failed to launch ansible-playbook",
                "stderr": (run.stderr or "").strip(),
            }
        ), 502

    pid = (run.stdout or "").strip()
    TESTLAB_WORKSPACE.mkdir(parents=True, exist_ok=True)
    marker = TESTLAB_WORKSPACE / f"{project}.json"
    try:
        marker.write_text(
            json.dumps(
                {
                    "project": project,
                    "jumpbox_ip": jumpbox_ip,
                    "remote_pid": pid,
                    "started_at": time.time(),
                    "ssh_key_path": key_path,
                },
                indent=2,
            )
        )
    except OSError:
        # Non-fatal — the marker is a convenience, the source of truth is
        # the jumpbox-side PID file.
        pass

    return jsonify(
        {
            "success": True,
            "pid": pid,
            "log_path": REMOTE_LOG_PATH,
            "jumpbox_ip": jumpbox_ip,
        }
    )


@bp.route("/status/<project>", methods=["GET"])
def status(project: str):
    """Poll provisioning status.

    Returns {status, last_exit_code, log_tail, remote_pid?, jumpbox_ip?}.

    status:
      - idle       — no marker / no remote PID file
      - running    — the process is still alive on the jumpbox
      - success    — exit code present and == 0
      - failed     — exit code present and != 0
    """
    state = _read_state(project)
    if state is None:
        return jsonify({"success": False, "error": f"No deployment state for '{project}'"}), 404
    if not _test_lab_enabled(project):
        return jsonify(
            {
                "success": True,
                "enabled": False,
                "status": "idle",
                "last_exit_code": None,
                "log_tail": "",
            }
        )

    marker = TESTLAB_WORKSPACE / f"{project}.json"
    if not marker.exists():
        return jsonify(
            {
                "success": True,
                "enabled": True,
                "status": "idle",
                "last_exit_code": None,
                "log_tail": "",
            }
        )

    try:
        meta = json.loads(marker.read_text())
    except (json.JSONDecodeError, OSError):
        return jsonify(
            {
                "success": True,
                "enabled": True,
                "status": "idle",
                "last_exit_code": None,
                "log_tail": "",
            }
        )

    jumpbox_ip = meta.get("jumpbox_ip") or _resolve_jumpbox_ip(state)
    key_path = meta.get("ssh_key_path") or _ssh_key_path()
    if not jumpbox_ip:
        return jsonify(
            {
                "success": True,
                "enabled": True,
                "status": "idle",
                "last_exit_code": None,
                "log_tail": "",
            }
        )

    # Compose a single SSH round-trip that returns: state token, exit code
    # (when finalized), and the log tail. Splitting these into separate
    # round-trips makes the status endpoint feel sluggish.
    probe = (
        f"if [ -f {REMOTE_PIDFILE_PATH} ] && kill -0 $(cat {REMOTE_PIDFILE_PATH}) 2>/dev/null; "
        f"then echo STATE:running; "
        f"elif [ -f {REMOTE_EXITCODE_PATH} ]; then echo STATE:done:$(cat {REMOTE_EXITCODE_PATH}); "
        f"else echo STATE:idle; fi; "
        f"echo ---LOG_TAIL---; "
        f"tail -40 {REMOTE_LOG_PATH} 2>/dev/null || true"
    )
    try:
        result = _ssh_cmd(jumpbox_ip, key_path, probe, timeout=20)
    except subprocess.TimeoutExpired:
        return jsonify(
            {
                "success": True,
                "enabled": True,
                "status": "running",
                "last_exit_code": None,
                "log_tail": "",
                "message": "Timed out reaching jumpbox (assume still running)",
            }
        )

    if result.returncode != 0:
        return jsonify(
            {
                "success": True,
                "enabled": True,
                "status": "idle",
                "last_exit_code": None,
                "log_tail": "",
                "message": "Could not reach jumpbox",
            }
        )

    raw = (result.stdout or "").strip()
    if "---LOG_TAIL---" in raw:
        state_line, log_tail = raw.split("---LOG_TAIL---", 1)
        state_line = state_line.strip()
        log_tail = log_tail.strip()
    else:
        state_line = raw
        log_tail = ""

    status_token = "idle"
    last_exit_code: int | None = None
    if state_line.startswith("STATE:running"):
        status_token = "running"
    elif state_line.startswith("STATE:done:"):
        try:
            last_exit_code = int(state_line.split(":", 2)[2].strip())
        except (ValueError, IndexError):
            last_exit_code = None
        status_token = "success" if last_exit_code == 0 else "failed"

    return jsonify(
        {
            "success": True,
            "enabled": True,
            "status": status_token,
            "last_exit_code": last_exit_code,
            "log_tail": log_tail,
            "remote_pid": meta.get("remote_pid"),
            "jumpbox_ip": jumpbox_ip,
            "subnet_cidr": _test_lab_subnet_cidr(project),
        }
    )
