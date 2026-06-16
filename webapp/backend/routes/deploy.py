"""
Deployment API Routes
Handle infrastructure deployment operations
"""

from flask import Blueprint, request, jsonify, g
from pathlib import Path
import sys
import threading
import time
import os
import subprocess
import hashlib
import json
import re
from werkzeug.utils import secure_filename

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from webapp.backend.services.terraform_service import TerraformService, get_terraform_service
from webapp.backend.services import audit_service
from webapp.backend.services import dashboard_settings_service
from webapp.backend.utils.goad_template_processor import get_lab_info, extract_vm_info
from webapp.backend.utils.tfvars_path import (
    RESERVED_PROJECT_NAMES as _RESERVED_PROJECT_NAMES,
    resolve_tfvars_path as _resolve_tfvars_path,
    sanitize_project_name as _sanitize_project_name,
)
from webapp.backend.utils.destroy_safety import (
    expected_modules_for as _expected_modules_for,
    parse_top_level_modules as _parse_top_level_modules,
    compute_foreign_modules as _compute_foreign_modules,
)


def _resolve_project_tfvars(project_param, default_tfvars):
    """Resolve a ?project= or body project_name to (tfvars_path, workspace_name).

    Returns ``(default_tfvars, "default")`` when no per-project file applies
    so callers preserve the legacy single-config behavior. When a real
    per-project tfvars exists, returns the resolved path AND the sanitized
    workspace name so the terraform_service can be retargeted in one shot.

    Path-traversal hardening lives in ``utils.tfvars_path`` — never
    re-implement it here.
    """
    config_dir = default_tfvars.parent
    if not project_param or project_param in _RESERVED_PROJECT_NAMES:
        return default_tfvars, "default"
    candidate = _resolve_tfvars_path(project_param, config_dir, default_tfvars)
    if candidate == default_tfvars or not candidate.exists():
        return default_tfvars, "default"
    workspace = _sanitize_project_name(project_param) or "default"
    return candidate, workspace


def _project_tfvars_for(project_param):
    """Pick the right tfvars file for a project (per-project first, then global).

    Helper used by read-only endpoints that just need a config dict (region,
    project_name, domain). Returns the resolved ``Path`` so callers can pass
    it straight to ``ConfigParser.parse_tfvars``. Mirrors the resolution
    precedence in ``_resolve_project_tfvars`` but without forcing the
    workspace name onto the global terraform_service — read-only callers
    shouldn't mutate shared service state.
    """
    global_tfvars = project_root / "configs" / "terraform.tfvars"
    if not project_param or project_param in _RESERVED_PROJECT_NAMES:
        return global_tfvars
    candidate = _resolve_tfvars_path(
        project_param, global_tfvars.parent, global_tfvars
    )
    return candidate if candidate.exists() else global_tfvars


def _read_project_config(project_param):
    """Parse ``configs/<project>.tfvars`` (or global) into a dict.

    Returns ``{}`` if no file exists. Centralizes the "load region +
    project_name + domain" boilerplate that was duplicated across the
    stop/start/outputs/sg-rules/ssl-status/toggle-redirector handlers.
    """
    from webapp.backend.utils.config_parser import ConfigParser
    tfvars = _project_tfvars_for(project_param)
    if not tfvars.exists():
        return {}
    return ConfigParser.parse_tfvars(tfvars) or {}


def _audit_actor():
    """Return the current operator id from flask.g (set by app.before_request)."""
    op = getattr(g, "operator", None)
    return op.get("id") if op else "unknown"


def _read_project_deployment_type(configs_dir, project_stem: str) -> str:
    """Best-effort read of ``deployment_type`` from configs/<project>.tfvars.

    Returns ``""`` if the file is missing or the key is absent. Used by
    the destroy-safety check so we can build the expected-modules set
    without depending on terraform output (which may be unavailable if
    the state was hand-edited or the dashboard was just upgraded).

    Mirrors the lightweight regex approach in ``_project_has_test_lab``
    — full HCL parsing is overkill for a single string assignment.
    """
    tfvars_path = configs_dir / f"{project_stem}.tfvars"
    if not tfvars_path.exists():
        return ""
    try:
        text = tfvars_path.read_text()
    except (OSError, UnicodeDecodeError):
        return ""
    import re as _re
    m = _re.search(
        r'^\s*deployment_type\s*=\s*"([^"]+)"',
        text,
        _re.MULTILINE,
    )
    return m.group(1).strip() if m else ""


def _summarize_state_for_safety(project_name: str):
    """Compute (deployment_type, expected, actual, foreign) for a project.

    Returns a dict shaped::

        {
          "success": bool,
          "error": str | None,                # populated on failure
          "deployment_type": str,
          "enable_test_lab": bool,
          "expected_modules": [str, ...],
          "actual_modules":   [str, ...],
          "foreign_modules":  [str, ...],
          "state_list_stderr": str,            # for debugging
        }

    Used by both the destroy guard (Component 1) and the state-summary
    endpoint (Component 5). The shared helper guarantees the two surfaces
    can never drift — same definition of "foreign" everywhere.

    NOTE: ``terraform state list`` against an empty / uninitialized
    workspace returns an empty list with exit 0 — in that case all four
    lists are empty and ``foreign_modules`` is ``[]`` (no false positive).
    """
    configs_dir = project_root / "configs"
    deployment_type = _read_project_deployment_type(configs_dir, project_name)
    enable_test_lab = _project_has_test_lab(configs_dir, project_name)

    service = get_service_for_project(project_name)
    listing = service.state_list()

    if not listing.get("success"):
        return {
            "success": False,
            "error": "state_list_failed",
            "state_list_stderr": listing.get("stderr", ""),
            "deployment_type": deployment_type,
            "enable_test_lab": enable_test_lab,
            "expected_modules": sorted(_expected_modules_for(
                deployment_type, enable_test_lab=enable_test_lab)),
            "actual_modules": [],
            "foreign_modules": [],
        }

    actual = _parse_top_level_modules(listing.get("stdout", ""))
    expected = _expected_modules_for(deployment_type, enable_test_lab=enable_test_lab)
    foreign = _compute_foreign_modules(
        deployment_type, actual, enable_test_lab=enable_test_lab)

    return {
        "success": True,
        "error": None,
        "state_list_stderr": listing.get("stderr", ""),
        "deployment_type": deployment_type,
        "enable_test_lab": enable_test_lab,
        "expected_modules": sorted(expected),
        "actual_modules": sorted(actual),
        "foreign_modules": foreign,
    }

bp = Blueprint('deploy', __name__)

# File storage directory (local to user's machine)
UPLOAD_FOLDER = project_root / "uploads"
CS_CLIENT_FOLDER = project_root / "uploads_client"  # Separate folder for CS Client
ALLOWED_EXTENSIONS = {'tar', 'gz', 'zip', 'tar.gz', 'exe'}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB

# SSH keys directory
SSH_KEYS_FOLDER = project_root / "ssh_keys"

# Ensure directories exist
UPLOAD_FOLDER.mkdir(exist_ok=True)
CS_CLIENT_FOLDER.mkdir(exist_ok=True)
SSH_KEYS_FOLDER.mkdir(exist_ok=True)

# =============================================================================
# ACTIVE DEPLOYMENT STATE
# =============================================================================

def _project_has_test_lab(configs_dir, project_stem: str) -> bool:
    """Return True iff configs/<project_stem>.tfvars sets enable_test_lab=true.

    Lightweight regex-based reader — we only need this boolean for the
    /api/deploy/active enrichment. Robust to comments / surrounding
    whitespace; ignores commented-out lines.
    """
    tfvars_path = configs_dir / f"{project_stem}.tfvars"
    if not tfvars_path.exists():
        return False
    try:
        text = tfvars_path.read_text()
    except (OSError, UnicodeDecodeError):
        return False
    import re as _re
    # `^\s*` ensures commented-out (# enable_test_lab = …) lines are skipped.
    match = _re.search(r"^\s*enable_test_lab\s*=\s*(true|false)", text, _re.MULTILINE | _re.IGNORECASE)
    return bool(match and match.group(1).lower() == "true")


@bp.route("/active", methods=["GET"])
def get_active_deployments():
    """Get all successful deployments, sorted most recent first.

    2026-05-22 — Always prepends a synthetic ``demo`` deployment record
    so the operator can showcase the dashboard without provisioning
    real AWS infrastructure. The demo deployment is served from
    ``demo_data_service.deployment_state()`` and is filtered out when
    Terraform/operations endpoints would otherwise act on it.
    """
    from webapp.backend.services import demo_data_service

    state_dir = os.path.join(str(project_root), "logs", "deployment_state")

    deployments: list = []
    configs_dir = project_root / "configs"
    if os.path.isdir(state_dir):
        for fname in os.listdir(state_dir):
            if not fname.endswith(".state.json"):
                continue
            fpath = os.path.join(state_dir, fname)
            try:
                with open(fpath) as f:
                    state = json.load(f)
                if state.get("status") == "success":
                    stem = fname.replace(".state.json", "")
                    state["_filename"] = stem
                    # 2026-05-20 — surface ``enable_test_lab`` on each row so
                    # the frontend's APP.computeVisibleSubPills can flip
                    # Bolt-ons on for c2-* deployments that opted into the
                    # test lab. Cheap one-line grep over the matching per-
                    # project tfvars.
                    state["enable_test_lab"] = _project_has_test_lab(configs_dir, stem)
                    deployments.append(state)
            except (json.JSONDecodeError, IOError):
                continue

    deployments.sort(key=lambda d: d.get("completed_at", 0), reverse=True)
    # Synthetic demo deployment — the single c2-adhoc "demo" showcase row,
    # prepended so it's the first entry. (2026-05-29 — the demo-ccrts row was
    # removed: a CCRTS demo was never requested and only cluttered the picker.)
    deployments.insert(0, demo_data_service.deployment_state())

    return jsonify({"success": True, "deployments": deployments})

# =============================================================================
# WINDOWS PASSWORD DECRYPTION (EC2Launch v2)
# =============================================================================

def _get_aws_region(project_param: str = None) -> str:
    """Get AWS region from the project's tfvars (or global) or AWS CLI default.

    Accepts an optional ``project_param`` — when provided, looks up
    ``configs/<project>.tfvars`` first, then falls back to the global
    tfvars, then to the AWS CLI configured region. This is invoked from
    places like the EC2 password-decryption helper that previously hard-
    coded the global tfvars and silently picked up the wrong region for
    per-project deployments.
    """
    try:
        cfg = _read_project_config(project_param)
        region = (cfg.get("aws_region") or "").strip()
        if region:
            return region
    except Exception:
        pass
    # Fall back to AWS CLI default region
    try:
        result = subprocess.run(["aws", "configure", "get", "region"],
                                capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return "eu-central-1"


def get_windows_password(instance_id: str, terraform_service) -> str:
    """Decrypt EC2Launch v2 auto-generated Windows Administrator password.

    Uses the RSA private key from Terraform state to decrypt the password
    that EC2Launch v2 generates during instance boot.
    """
    import tempfile, base64
    try:
        # Get RSA private key from Terraform state
        state_json = subprocess.run(
            ["terraform", "state", "pull"],
            capture_output=True, text=True, timeout=30,
            cwd=str(project_root / "terraform")
        )
        if state_json.returncode != 0:
            return ""

        state = json.loads(state_json.stdout)
        pem_key = ""
        for r in state.get("resources", []):
            if r.get("type") == "tls_private_key" and r.get("name") == "windows":
                for inst in r.get("instances", []):
                    pem_key = inst.get("attributes", {}).get("private_key_pem", "")
                    break
        if not pem_key:
            return ""

        # Write key to temp file for AWS CLI
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as f:
            f.write(pem_key)
            key_path = f.name

        try:
            os.chmod(key_path, 0o600)
            result = subprocess.run(
                ["aws", "ec2", "get-password-data",
                 "--instance-id", instance_id,
                 "--priv-launch-key", key_path,
                 "--query", "PasswordData",
                 "--output", "text",
                 "--region", _get_aws_region()],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        finally:
            os.unlink(key_path)
    except Exception as e:
        print(f"Warning: Could not decrypt Windows password: {e}")
    return ""


# =============================================================================
# MULTI-PROJECT DEPLOYMENT STATE
# =============================================================================

# Track deployments by project name (workspace)
# Structure: {"project_name": {"status": "running", "logs": [], ...}}
deployment_states = {}

# =============================================================================
# STATE PERSISTENCE — survives Flask server restarts
# =============================================================================

STATE_DIR = project_root / "logs" / "deployment_state"
STATE_LOCK = threading.Lock()

def _state_file_path(project_name: str) -> Path:
    """Return the JSON file path for a project's deployment state."""
    safe_name = project_name or "default"
    # Sanitize for filesystem
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in safe_name)
    return STATE_DIR / f"{safe_name}.state.json"

def _persist_state(project_name: str, state: dict):
    """Write deployment state to disk. Called on every mutation."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        path = _state_file_path(project_name)
        with STATE_LOCK:
            with open(path, 'w') as f:
                json.dump(state, f, default=str)
    except Exception as e:
        print(f"Error persisting deployment state: {e}")

def _load_persisted_state(project_name: str) -> dict:
    """Load deployment state from disk if it exists."""
    path = _state_file_path(project_name)
    if path.exists():
        try:
            with open(path, 'r') as f:
                loaded = json.load(f)
            # Handle stale "running" state from a crashed server
            if loaded.get("status") == "running":
                loaded["status"] = "error"
                loaded["error"] = "Server restarted during deployment. State recovered but deployment was interrupted."
                loaded["completed_at"] = time.time()
                _persist_state(project_name, loaded)
            return loaded
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading persisted state for {project_name}: {e}")
    return None

# =============================================================================
# DEPLOYMENT HISTORY HELPERS (defined early for use by add_log)
# =============================================================================

HISTORY_FILE = project_root / "logs" / "deployment_history.json"

# In-memory cache for deployment history — avoids disk reads on every API call.
# Invalidated on write (add_history_entry, save_deployment_history).
_history_cache = None

def load_deployment_history():
    """Load deployment history from file (cached in memory after first read)"""
    global _history_cache
    if _history_cache is not None:
        return list(_history_cache)  # Return a copy so callers can't corrupt cache
    try:
        if HISTORY_FILE.exists():
            with open(HISTORY_FILE, 'r') as f:
                _history_cache = json.load(f)
                return list(_history_cache)
    except Exception as e:
        print(f"Error loading deployment history: {e}")
    _history_cache = []
    return []

def save_deployment_history(history):
    """Save deployment history to file and update in-memory cache"""
    global _history_cache
    trimmed = history[-500:]  # Keep last 500 entries
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(HISTORY_FILE, 'w') as f:
            json.dump(trimmed, f, indent=2)
        _history_cache = trimmed  # Update cache after successful write
    except Exception as e:
        print(f"Error saving deployment history: {e}")
        _history_cache = None  # Invalidate cache on error

def add_history_entry(message, level='info', details=None, project_name=None, entry_type=None):
    """Add an entry to deployment history

    Args:
        message: Log message
        level: Log level (info, success, error, warning)
        details: Additional details
        project_name: Project/workspace name
        entry_type: Type of entry ('plan', 'deployment', etc.) - used to filter in UI
    """
    from datetime import datetime
    history = load_deployment_history()
    entry = {
        'timestamp': datetime.now().isoformat(),
        'level': level,
        'message': message,
        'details': details
    }
    if project_name:
        entry['project_name'] = project_name
    if entry_type:
        entry['entry_type'] = entry_type
    # Attribute the deploy to the VERIFIED operator (the signed, SSH-bound
    # g.operator), NOT the old spoofable ss/proc SSH-trace heuristic — deploy
    # history is a high-value audit record and must be non-repudiable.
    try:
        from flask import g, has_request_context
        op = getattr(g, 'operator', None) if has_request_context() else None
        entry['initiated_by'] = (op or {}).get('id') or 'system'
    except Exception:
        entry['initiated_by'] = 'system'
    history.append(entry)
    save_deployment_history(history)

# =============================================================================
# HELPER FUNCTIONS FOR MULTI-PROJECT STATE
# =============================================================================

def get_project_state(project_name: str) -> dict:
    """Get or create deployment state for a project (loads from disk on first access)"""
    if project_name not in deployment_states:
        loaded = _load_persisted_state(project_name)
        if loaded:
            deployment_states[project_name] = loaded
        else:
            deployment_states[project_name] = create_empty_state()
    return deployment_states[project_name]

def create_empty_state() -> dict:
    """Create a new empty deployment state"""
    return {
        "status": "idle",  # idle, running, success, error
        "step": "",
        "output": "",
        "error": None,
        "deployment_type": None,
        "goad_ansible_status": None,
        "started_at": None,
        "completed_at": None,
        "progress_percent": 0,
        "current_phase": "",
        "current_phase_name": "",
        "phases_completed": [],
        "logs": []
    }

def query_remaining_resources(project_name: str) -> dict:
    """Query AWS for resources still tagged with this project.
    Uses Resource Groups Tagging API for comprehensive coverage.
    Filters out terminated/deleted resources (instances, NAT gateways, volumes)
    that AWS retains temporarily after destruction.
    Returns {count, by_service, resources} or {count: -1, error} on failure."""
    import boto3

    # Per-project region lookup: configs/<project>.tfvars wins over the
    # global tfvars. Falls back to eu-central-1 only if neither exists.
    config = _read_project_config(project_name)
    aws_region = config.get('aws_region', 'eu-central-1')

    try:
        tagging = boto3.client('resourcegroupstaggingapi', region_name=aws_region)
        paginator = tagging.get_paginator('get_resources')
        pages = paginator.paginate(
            TagFilters=[{'Key': 'Project', 'Values': [project_name]}],
            ResourcesPerPage=100
        )

        raw_resources = []
        for page in pages:
            for r in page.get('ResourceTagMappingList', []):
                arn = r['ResourceARN']
                parts = arn.split(':')
                service = parts[2] if len(parts) > 2 else 'unknown'
                # Extract resource type and id from ARN (e.g. "instance/i-xxx", "natgateway/nat-xxx")
                resource_part = parts[-1] if parts else arn
                resource_type = resource_part.split('/')[0] if '/' in resource_part else ''
                resource_id = resource_part.split('/')[-1] if '/' in resource_part else resource_part
                raw_resources.append({
                    'arn': arn,
                    'service': service,
                    'resource_type': resource_type,
                    'resource_id': resource_id
                })

        # Filter out terminated/deleted EC2 resources (AWS keeps tags on dead resources temporarily)
        dead_resource_ids = set()
        ec2_instance_ids = [r['resource_id'] for r in raw_resources if r['resource_type'] == 'instance']
        ec2_nat_ids = [r['resource_id'] for r in raw_resources if r['resource_type'] == 'natgateway']
        ec2_volume_ids = [r['resource_id'] for r in raw_resources if r['resource_type'] == 'volume']
        ec2_vpce_ids = [r['resource_id'] for r in raw_resources if r['resource_type'] == 'vpc-endpoint']

        if ec2_instance_ids or ec2_nat_ids or ec2_volume_ids or ec2_vpce_ids:
            ec2 = boto3.client('ec2', region_name=aws_region)

            if ec2_instance_ids:
                try:
                    resp = ec2.describe_instances(InstanceIds=ec2_instance_ids)
                    for res in resp.get('Reservations', []):
                        for inst in res.get('Instances', []):
                            if inst['State']['Name'] in ('terminated', 'shutting-down'):
                                dead_resource_ids.add(inst['InstanceId'])
                except Exception:
                    pass

            if ec2_nat_ids:
                try:
                    resp = ec2.describe_nat_gateways(NatGatewayIds=ec2_nat_ids)
                    for nat in resp.get('NatGateways', []):
                        if nat['State'] in ('deleted', 'deleting'):
                            dead_resource_ids.add(nat['NatGatewayId'])
                except Exception:
                    pass

            if ec2_volume_ids:
                try:
                    resp = ec2.describe_volumes(VolumeIds=ec2_volume_ids)
                    for vol in resp.get('Volumes', []):
                        if vol['State'] in ('deleted', 'deleting'):
                            dead_resource_ids.add(vol['VolumeId'])
                except Exception:
                    # Volumes that no longer exist throw an error — mark them as dead
                    for vid in ec2_volume_ids:
                        dead_resource_ids.add(vid)

            if ec2_vpce_ids:
                try:
                    resp = ec2.describe_vpc_endpoints(VpcEndpointIds=ec2_vpce_ids)
                    for vpce in resp.get('VpcEndpoints', []):
                        if vpce['State'] in ('deleted', 'deleting'):
                            dead_resource_ids.add(vpce['VpcEndpointId'])
                except Exception:
                    pass

            # Volumes attached to terminated instances are also dead
            if ec2_volume_ids and dead_resource_ids:
                try:
                    resp = ec2.describe_volumes(VolumeIds=[v for v in ec2_volume_ids if v not in dead_resource_ids])
                    for vol in resp.get('Volumes', []):
                        attachments = vol.get('Attachments', [])
                        if all(a.get('InstanceId', '') in dead_resource_ids for a in attachments) and attachments:
                            dead_resource_ids.add(vol['VolumeId'])
                except Exception:
                    pass

        # Build filtered results
        resources = []
        by_service = {}
        filtered_count = 0
        for r in raw_resources:
            if r['resource_id'] in dead_resource_ids:
                filtered_count += 1
                continue
            resources.append(r)
            by_service[r['service']] = by_service.get(r['service'], 0) + 1

        result = {'count': len(resources), 'by_service': by_service, 'resources': resources}
        if filtered_count > 0:
            result['filtered_dead'] = filtered_count
        return result
    except Exception as e:
        return {'count': -1, 'error': str(e), 'by_service': {}, 'resources': []}


def parse_terraform_destroy_output(stdout: str, stderr: str) -> dict:
    """Parse terraform destroy stdout/stderr into structured results.

    Terraform outputs lines like:
      aws_instance.example: Destroying... [id=i-1234567890abcdef0]
      aws_instance.example: Destruction complete after 1m2s
      Error: error deleting Security Group (sg-xxx): DependencyViolation...
    """
    import re

    destroyed = []
    errors = []

    # Match successful destructions
    for match in re.finditer(
        r'^(\S+): Destruction complete after (.+)$', stdout, re.MULTILINE
    ):
        destroyed.append({'address': match.group(1), 'duration': match.group(2)})

    # Match errors from stderr
    for match in re.finditer(r'^.*Error: (.+)$', stderr, re.MULTILINE):
        errors.append(match.group(1).strip())

    # Track resources that started destroying but never completed (timeout/hang)
    destroying = set()
    for match in re.finditer(r'^(\S+): Destroying\.\.\.', stdout, re.MULTILINE):
        destroying.add(match.group(1))

    completed = {d['address'] for d in destroyed}
    still_destroying = list(destroying - completed)

    return {
        'destroyed_count': len(destroyed),
        'destroyed': destroyed,
        'error_count': len(errors),
        'errors': errors,
        'still_destroying': still_destroying
    }


def get_active_deployments() -> list:
    """Get list of currently running deployments"""
    return [
        {"project_name": name, **state}
        for name, state in deployment_states.items()
        if state.get("status") == "running"
    ]

# =============================================================================
# BACKWARD COMPATIBILITY: Single deployment state (for existing code)
# This will be deprecated - use deployment_states[project_name] instead
# =============================================================================

deployment_state = create_empty_state()
# Restore default state from disk if available (survives server restarts)
_loaded_default = _load_persisted_state(None)
if _loaded_default:
    deployment_state.update(_loaded_default)

# Deployment phases — universal for all deployment types
# Progress is driven by real Terraform resource completion events, not estimates
DEPLOYMENT_PHASES = [
    {"name": "init", "label": "Initializing Terraform"},
    {"name": "validate", "label": "Validating Configuration"},
    {"name": "plan", "label": "Planning Deployment"},
    {"name": "apply", "label": "Applying Infrastructure"},
    {"name": "outputs", "label": "Retrieving Outputs"},
]

# Fixed progress anchors for non-apply phases
_PHASE_PROGRESS = {
    "init": 0,
    "validate": 5,
    "plan": 10,
    "apply": 20,  # Resource events drive this from 20% to 95%
    "outputs": 95,
}

def add_log(message, log_type="info", project_name=None):
    """Add a log entry to deployment state and persistent history"""
    # Use project-specific state if provided
    if project_name and project_name in deployment_states:
        state = deployment_states[project_name]
    else:
        state = deployment_state

    state["logs"].append({
        "timestamp": time.time(),
        "message": message,
        "type": log_type  # info, success, warning, error
    })
    # Cap log volume to prevent unbounded growth (especially with streaming)
    if len(state["logs"]) > 200:
        state["logs"] = state["logs"][-150:]
    # Persist to disk
    _persist_state(project_name, state)
    # Also save to persistent history
    add_history_entry(message, log_type, project_name=project_name)

def update_phase(phase_name, project_name=None):
    """Update current phase and set progress based on fixed anchors"""
    # Use project-specific state if provided
    if project_name and project_name in deployment_states:
        state = deployment_states[project_name]
    else:
        state = deployment_state

    for phase in DEPLOYMENT_PHASES:
        if phase["name"] == phase_name:
            state["progress_percent"] = _PHASE_PROGRESS.get(phase_name, 0)
            state["current_phase"] = phase["label"]
            state["current_phase_name"] = phase_name
            state["step"] = phase["label"]
            add_log(f"Started: {phase['label']}", "info", project_name)
            break

def complete_phase(phase_name, project_name=None):
    """Mark a phase as completed"""
    # Use project-specific state if provided
    if project_name and project_name in deployment_states:
        state = deployment_states[project_name]
    else:
        state = deployment_state

    for phase in DEPLOYMENT_PHASES:
        if phase["name"] == phase_name:
            if phase_name not in state["phases_completed"]:
                state["phases_completed"].append(phase_name)
                add_log(f"Completed: {phase['label']}", "success", project_name)
                _persist_state(project_name, state)
            break

# Default terraform service (for backward compatibility)
terraform_service = TerraformService(project_root)

def get_service_for_project(project_name: str) -> TerraformService:
    """Get a TerraformService instance for a specific project/workspace"""
    return get_terraform_service(project_root, project_name)

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS or \
           filename.endswith('.tar.gz')

def update_tfvars_cs_path(tfvars_file, s3_uri):
    """Update terraform.tfvars with the Cobalt Strike S3 path"""
    try:
        if not tfvars_file.exists():
            return False
        
        content = tfvars_file.read_text()
        
        # Check if cobalt_strike_archive_s3_path already exists
        if 'cobalt_strike_archive_s3_path' in content:
            # Update existing value
            import re
            content = re.sub(
                r'cobalt_strike_archive_s3_path\s*=\s*"[^"]*"',
                f'cobalt_strike_archive_s3_path = "{s3_uri}"',
                content
            )
        else:
            # Add new line
            content += f'\n# Cobalt Strike S3 Path (auto-generated)\ncobalt_strike_archive_s3_path = "{s3_uri}"\n'
        
        tfvars_file.write_text(content)
        return True
    except Exception as e:
        print(f"Error updating tfvars with CS path: {e}")
        return False

def update_tfvars_cs_client_path(tfvars_file, s3_uri):
    """Update terraform.tfvars with the Cobalt Strike Client S3 path (for Attack Box)"""
    try:
        if not tfvars_file.exists():
            return False
        
        content = tfvars_file.read_text()
        
        # Check if cs_client_s3_path already exists
        if 'cs_client_s3_path' in content:
            # Update existing value
            import re
            content = re.sub(
                r'cs_client_s3_path\s*=\s*"[^"]*"',
                f'cs_client_s3_path = "{s3_uri}"',
                content
            )
        else:
            # Add new line
            content += f'\n# Cobalt Strike Client S3 Path for Attack Box (auto-generated)\ncs_client_s3_path = "{s3_uri}"\n'
        
        tfvars_file.write_text(content)
        return True
    except Exception as e:
        print(f"Error updating tfvars with CS Client path: {e}")
        return False

def extract_and_inject_github_token(tfvars_file, add_log_fn, project_name):
    """Extract GitHub token from gh CLI and inject into tfvars for private repo cloning"""
    try:
        add_log_fn("Extracting GitHub token from gh CLI for private repo access...", "info", project_name)
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            token = result.stdout.strip()
            add_log_fn("GitHub token extracted successfully", "success", project_name)

            # Inject into tfvars
            if tfvars_file.exists():
                content = tfvars_file.read_text()
                import re
                if 'tools_repo_https_token' in content:
                    content = re.sub(
                        r'tools_repo_https_token\s*=\s*"[^"]*"',
                        f'tools_repo_https_token = "{token}"',
                        content
                    )
                else:
                    content += f'\n# GitHub token for private tools repo (auto-injected from gh CLI)\ntools_repo_https_token = "{token}"\n'
                tfvars_file.write_text(content)
                add_log_fn("GitHub token injected into deployment config", "info", project_name)
                return True
        else:
            add_log_fn("GitHub CLI not authenticated — private repo cloning may fail", "warning", project_name)
            return False
    except FileNotFoundError:
        add_log_fn("gh CLI not installed — private repo cloning may fail", "warning", project_name)
        return False
    except subprocess.TimeoutExpired:
        add_log_fn("gh auth token timed out — skipping token injection", "warning", project_name)
        return False
    except Exception as e:
        add_log_fn(f"Failed to extract GitHub token: {str(e)}", "warning", project_name)
        return False


def get_file_info(filepath):
    """Get file information"""
    if not filepath.exists():
        return None

    stat = filepath.stat()
    return {
        "filename": filepath.name,
        "size": stat.st_size,
        "size_mb": round(stat.st_size / (1024 * 1024), 2),
        "modified": stat.st_mtime,
        "path": str(filepath)
    }

# =============================================================================
# Phase 4 — Demo-draft synthetic deployment tick
# =============================================================================
# Walks the canonical DEPLOYMENT_PHASES list over ~30s, emitting realistic
# per-phase log lines and flipping the persisted state to is_demo=True so
# the generalized is_demo_project() resolves the walkthrough deployment
# everywhere downstream (Manage, Bolt-ons, Operations sub-pills). No
# terraform shell-out, no AWS calls — purely in-memory + on-disk state.
#
# Per-phase log scripts are intentionally verbose so the operator sees a
# convincing "real deployment" tick — operator UX intent: this surface
# MUST feel like the production deploy progress overlay so the muscle
# memory transfers. Total elapsed: ~30s (init 2s + validate 2s + plan 3s
# + apply 20s + outputs 3s).

DEMO_DRAFT_PHASE_LOGS = {
    "init": [
        ("Initializing Terraform backend (s3)...", "info", 0.4),
        ("Reading workspace configuration...", "info", 0.4),
        ("Provider plugins: aws v5.x, null v3.x, random v3.x", "info", 0.4),
        ("Backend ready, workspace pinned: demo-walkthrough", "success", 0.4),
    ],
    "validate": [
        ("Validating terraform configuration...", "info", 0.4),
        ("Module: vpc — valid", "info", 0.3),
        ("Module: security — valid", "info", 0.3),
        ("Module: c2_team_server — valid", "info", 0.3),
        ("Configuration valid — no syntax or reference errors", "success", 0.4),
    ],
    "plan": [
        ("Generating execution plan...", "info", 0.5),
        ("Refreshing state from backend...", "info", 0.5),
        ("Plan: 47 to add, 0 to change, 0 to destroy", "success", 0.5),
        ("Estimated cost delta: $0.12/hr (eu-central-1)", "info", 0.5),
    ],
    "apply": [
        ("[+] aws_vpc.main: Creating... (vpc-0demo01)", "info", 1.0),
        ("[+] aws_internet_gateway.main: Creating... (igw-0demo01)", "info", 0.9),
        ("[+] aws_subnet.public[0]: Creating... (subnet-0pub0demo)", "info", 0.9),
        ("[+] aws_subnet.private[0]: Creating... (subnet-0priv0demo)", "info", 0.9),
        ("[+] aws_nat_gateway.main: Still creating... [10s elapsed]", "info", 1.2),
        ("[+] aws_security_group.attack_box: Creating... (sg-0attackbox0demo)", "info", 0.9),
        ("[+] aws_security_group.c2: Creating... (sg-0c20demo)", "info", 0.9),
        ("[+] aws_iam_role.ec2_ssm: Creating...", "info", 0.8),
        ("[+] aws_instance.attack_box: Creating... (i-0demoattackbox01)", "info", 1.0),
        ("[+] aws_instance.c2_team_server[0]: Creating... (i-0demots01)", "info", 1.0),
        ("[+] aws_instance.redirector: Creating... (i-0demoredir01)", "info", 1.0),
        ("[+] aws_vpc_peering_connection.dashboard: Creating... (pcx-0demo01)", "info", 0.8),
        ("[+] aws_route53_record.c2: Creating...", "info", 0.8),
        ("[+] null_resource.bootstrap_cs: Provisioning... (Cobalt Strike install)", "info", 1.5),
        ("[+] null_resource.bootstrap_redirector: Provisioning... (nginx config)", "info", 1.5),
        ("[+] null_resource.bootstrap_attack_box: Provisioning... (Windows attack box)", "info", 1.5),
        ("Apply complete! Resources: 47 added, 0 changed, 0 destroyed.", "success", 0.8),
    ],
    "outputs": [
        ("Retrieving terraform outputs...", "info", 0.5),
        ("attackbox_private_ip = 10.0.10.50  # reached via the Dashboard Server jump", "info", 0.5),
        ("redirector_public_ip = 203.0.113.50", "info", 0.5),
        ("c2_team_server_private_ips = [\"10.0.10.20\"]", "info", 0.5),
        ("attackbox_public_ip = 203.0.113.30", "info", 0.5),
        ("cs_connection_info = { rest_api_enabled = true, host = 10.0.10.20, port = 50050 }", "success", 0.5),
    ],
}


def run_demo_draft_deployment(project_name: str):
    """Synthetic ~30s tick through DEPLOYMENT_PHASES — Phase 4.

    No terraform, no AWS — pure progress simulation. Writes the demo
    fixture output dict onto the state at completion so Manage +
    Operations sub-pills paint with the canonical demo bundle.
    """
    if project_name not in deployment_states:
        return
    state = deployment_states[project_name]
    try:
        for phase in DEPLOYMENT_PHASES:
            update_phase(phase["name"], project_name)
            scripted = DEMO_DRAFT_PHASE_LOGS.get(phase["name"], [])
            for message, log_type, delay in scripted:
                # Re-check at every step so a cancel can break us out early.
                if state.get("status") != "running":
                    return
                time.sleep(delay)
                add_log(message, log_type, project_name)
            complete_phase(phase["name"], project_name)

        # Inject canonical demo output bundle so Manage hero +
        # Operations sub-pills render populated data even though no
        # AWS resources exist. Pulled from the static `demo` fixture
        # so both walkthrough + static demos render the same topology.
        try:
            from webapp.backend.services import demo_data_service
            _demo_state = demo_data_service.deployment_state()
            state["output"] = _demo_state.get("output", {})
            state["outputs"] = _demo_state.get("outputs", {})
            state["models_deployment_type"] = _demo_state.get("models_deployment_type")
            state["models_description"] = _demo_state.get("models_description")
            state["enable_test_lab"] = _demo_state.get("enable_test_lab", True)
        except Exception as _e:
            add_log(f"[demo] could not load demo fixture bundle: {_e}",
                    "warning", project_name)

        state["status"] = "success"
        state["step"] = "complete"
        state["completed_at"] = time.time()
        state["progress_percent"] = 100
        state["is_demo"] = True
        state["is_demo_draft"] = True
        elapsed = int(state["completed_at"] - (state.get("started_at") or state["completed_at"]))
        add_log(
            f"Demo deployment completed successfully in {elapsed // 60}m {elapsed % 60}s "
            f"(simulated — no AWS resources provisioned)",
            "success",
            project_name,
        )
        _persist_state(project_name, state)
        try:
            audit_service.write(
                "demo",
                "deploy.demo_draft.complete",
                project=project_name,
                details={"is_demo": True, "duration_seconds": elapsed},
            )
        except Exception:
            pass
    except Exception as e:
        state["status"] = "error"
        state["error"] = f"Demo walkthrough failed: {e}"
        state["completed_at"] = time.time()
        add_log(f"Demo walkthrough error: {e}", "error", project_name)
        _persist_state(project_name, state)


def run_deployment(project_name: str = None):
    """Run deployment in background thread with enhanced progress tracking"""
    global deployment_state
    
    # Use project-specific state if provided
    if project_name and project_name in deployment_states:
        state = deployment_states[project_name]
        service = get_service_for_project(project_name)
    else:
        state = deployment_state
        service = terraform_service
        project_name = None  # For logging
    
    try:
        # Reset state
        state["status"] = "running"
        state["step"] = "Initializing..."
        state["output"] = ""
        state["error"] = None
        state["started_at"] = time.time()
        state["completed_at"] = None
        state["progress_percent"] = 0
        state["current_phase_name"] = ""
        state["phases_completed"] = []
        state["logs"] = []
        state["total_resources"] = 0
        state["resources_completed"] = 0
        _persist_state(project_name, state)

        # Determine deployment type from config
        from webapp.backend.utils.config_parser import ConfigParser
        config = ConfigParser.parse_tfvars(service.tfvars_file) if service.tfvars_file.exists() else {}
        
        deploy_type = config.get('deployment_type', 'c2-adhoc')
        if 'combined' in deploy_type:
            phase_type = "combined"
        elif 'goad' in deploy_type:
            phase_type = "goad"
        else:
            phase_type = "c2"
        
        state["deployment_type"] = deploy_type
        add_log(f"Starting deployment: {deploy_type}", "info", project_name)

        # Pre-flight: Extract GitHub token for private tools repo cloning
        extract_and_inject_github_token(service.tfvars_file, add_log, project_name)

        # Phase 1: Initialize
        update_phase("init", project_name)
        result = service.init()
        if not result["success"]:
            state["status"] = "error"
            state["error"] = result.get("stderr", "Terraform init failed")
            add_log(f"Error: {state['error']}", "error", project_name)
            return
        complete_phase("init", project_name)

        # Ensure workspace exists (for multi-project)
        if project_name:
            ws_result = service.ensure_workspace()
            if not ws_result["success"]:
                state["status"] = "error"
                state["error"] = ws_result.get("stderr", "Failed to setup workspace")
                add_log(f"Error: {state['error']}", "error", project_name)
                return
            add_log(f"Using workspace: {service.workspace_name}", "info", project_name)

        # Phase 2: Validate
        update_phase("validate", project_name)
        result = service.validate()
        if not result["success"]:
            state["status"] = "error"
            state["error"] = result.get("stderr", "Validation failed")
            add_log(f"Error: {state['error']}", "error", project_name)
            return
        complete_phase("validate", project_name)

        # Phase 3: Plan (also extracts total resource count for progress tracking)
        update_phase("plan", project_name)
        result = service.plan()
        if not result["success"] and result["exit_code"] != 2:  # 2 means changes detected
            state["status"] = "error"
            state["error"] = result.get("stderr", "Plan failed")
            add_log(f"Error: {state['error']}", "error", project_name)
            return

        # Parse plan output for total resource count and existing resources
        plan_stdout = result.get("stdout", "")
        plan_match = re.search(r'Plan: (\d+) to add, (\d+) to change, (\d+) to destroy', plan_stdout)
        if plan_match:
            total_resources = int(plan_match.group(1)) + int(plan_match.group(2)) + int(plan_match.group(3))
        else:
            total_resources = 0
        state["total_resources"] = total_resources
        state["resources_completed"] = 0

        # Count resources already in Terraform state (shows up as "Refreshing state..." lines)
        refreshing_count = len(re.findall(r'Refreshing state\.\.\.', plan_stdout))

        if total_resources > 0:
            if refreshing_count > 0:
                add_log(f"Resuming: {refreshing_count} resources already provisioned, {total_resources} remaining", "success", project_name)
            else:
                add_log(f"Plan: {total_resources} resources to create/modify", "info", project_name)
        elif 'No changes' in plan_stdout:
            add_log("All resources already provisioned - no changes needed", "success", project_name)

        complete_phase("plan", project_name)

        # Phase 4: Apply — progress driven by real resource completion events
        update_phase("apply", project_name)
        
        # Check if we need to upload Cobalt Strike to S3
        # For GOAD or C2 deployments that use CS, we need to:
        # 1. First create just the S3 bucket
        # 2. Upload the CS file to S3
        # 3. Then apply the rest (EC2 instances will have the file available)
        needs_cs_upload = (phase_type == "goad" or phase_type == "c2" or phase_type == "combined")
        
        # Check if there's a local CS file to upload (Team Server archive)
        local_cs_file = None
        if needs_cs_upload:
            cs_files = [f for f in UPLOAD_FOLDER.glob("*") if f.is_file() and allowed_file(f.name)]
            if cs_files:
                local_cs_file = max(cs_files, key=lambda f: f.stat().st_mtime)
                add_log(f"Found Cobalt Strike file: {local_cs_file.name}", "info", project_name)
        
        # Check if there's a CS Client file to upload (for Attack Box)
        # First check uploads_client/ for an explicit upload, then check uploads/
        # for a CS distribution directory (auto-zip it)
        local_cs_client_file = None
        if needs_cs_upload:
            # 1. Check uploads_client/ for manually uploaded files
            cs_client_files = [f for f in CS_CLIENT_FOLDER.glob("*") if f.is_file() and allowed_file(f.name)]
            if cs_client_files:
                local_cs_client_file = max(cs_client_files, key=lambda f: f.stat().st_mtime)
                add_log(f"Found CS Client file: {local_cs_client_file.name}", "info", project_name)
            else:
                # 2. Auto-detect a CS distribution directory in uploads/
                # Look for directories containing cobaltstrike.jar or update.bat (CS distribution)
                for d in UPLOAD_FOLDER.iterdir():
                    if d.is_dir() and any((d / f).exists() for f in ["cobaltstrike.jar", "update.jar", "update.bat"]):
                        add_log(f"Found CS Client directory: {d.name} — zipping for upload...", "info", project_name)
                        import zipfile
                        zip_path = CS_CLIENT_FOLDER / f"{d.name}.zip"
                        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                            for file_path in d.rglob("*"):
                                if file_path.is_file():
                                    zf.write(file_path, file_path.relative_to(d.parent))
                        local_cs_client_file = zip_path
                        add_log(f"Created CS Client archive: {zip_path.name}", "info", project_name)
                        break
        
        def _on_tf_event(message, event_type):
            """Callback for streaming Terraform events — counts resource completions for progress"""
            add_log(message, event_type, project_name)
            if event_type == "success" and any(message.startswith(p) for p in ["Created:", "Destroyed:", "Modified:"]):
                state["resources_completed"] = state.get("resources_completed", 0) + 1
                total = state.get("total_resources", 0)
                if total > 0:
                    apply_pct = min(state["resources_completed"] / total, 1.0)
                    state["progress_percent"] = int(20 + apply_pct * 75)

        if local_cs_file or local_cs_client_file:
            # Phase: Create S3 bucket first (targeted apply)
            add_log("Creating S3 bucket for Cobalt Strike files...", "info", project_name)
            result = service.apply_target_streaming("module.cs_storage", on_event=_on_tf_event)
        else:
            # No CS files to upload — skip S3 bucket creation
            result = {"success": True}

        if not result["success"]:
            # If bucket already exists, that's OK - continue
            if "already exists" not in str(result.get("stderr", "")):
                state["status"] = "error"
                state["error"] = result.get("stderr", "Failed to create S3 bucket")
                add_log(f"Error: {state['error']}", "error", project_name)
                return
            
        add_log("S3 bucket created successfully", "success", project_name)
        
        # Phase: Upload CS file to S3 (Team Server archive)
        if local_cs_file:
            add_log("Uploading Cobalt Strike to S3...", "info", project_name)
            try:
                from webapp.backend.utils.s3_upload import upload_cs_file, find_cs_bucket, S3UploadError
                
                # Find the bucket that was just created
                bucket_name = find_cs_bucket(project_name, config.get('aws_region', 'eu-central-1'))
                
                if bucket_name:
                    s3_uri, _ = upload_cs_file(
                        str(local_cs_file),
                        project_name,
                        config.get('aws_region', 'eu-central-1'),
                        bucket_name=bucket_name
                    )
                    add_log(f"Uploaded Cobalt Strike to {s3_uri}", "success", project_name)
                    
                    # Update tfvars with the S3 path so EC2 user_data can find it
                    update_tfvars_cs_path(service.tfvars_file, s3_uri)
                    add_log("Updated configuration with S3 path", "info", project_name)
                else:
                    add_log("Warning: Could not find S3 bucket for CS upload", "warning", project_name)
                    
            except Exception as e:
                state["status"] = "error"
                state["error"] = f"Failed to upload Cobalt Strike to S3: {str(e)}"
                add_log(f"Error: {state['error']}", "error", project_name)
                return
        
        # Phase: Upload CS Client file to S3 (for Attack Box)
        if local_cs_client_file:
            add_log("Uploading CS Client to S3...", "info", project_name)
            try:
                from webapp.backend.utils.s3_upload import upload_cs_file, find_cs_bucket, S3UploadError
                
                # Find the bucket
                bucket_name = find_cs_bucket(project_name, config.get('aws_region', 'eu-central-1'))
                
                if bucket_name:
                    # Upload with a different key prefix for the client
                    s3_client_uri, _ = upload_cs_file(
                        str(local_cs_client_file),
                        project_name,
                        config.get('aws_region', 'eu-central-1'),
                        bucket_name=bucket_name,
                        s3_key_prefix="cs-client/"
                    )
                    add_log(f"Uploaded CS Client to {s3_client_uri}", "success", project_name)
                    
                    # Update tfvars with the CS Client S3 path
                    update_tfvars_cs_client_path(service.tfvars_file, s3_client_uri)
                    add_log("Updated configuration with CS Client S3 path", "info", project_name)
                else:
                    add_log("Warning: Could not find S3 bucket for CS Client upload", "warning", project_name)
                    
            except Exception as e:
                add_log(f"Warning: Failed to upload CS Client to S3: {str(e)}", "warning", project_name)
                # Continue anyway - CS Client won't be auto-installed but deployment can proceed
        
        # Clean up old timestamped duplicates from previous deploys
        if local_cs_file or local_cs_client_file:
            try:
                from webapp.backend.utils.s3_upload import cleanup_duplicate_cs_files
                aws_region = config.get('aws_region', 'eu-central-1')
                cleaned = cleanup_duplicate_cs_files(project_name, aws_region)
                if cleaned > 0:
                    add_log(f"Cleaned up {cleaned} duplicate CS archive(s) from S3", "info", project_name)
            except Exception as e:
                add_log(f"Warning: Failed to clean up old S3 files: {e}", "warning", project_name)

        # Now apply the rest of the infrastructure
        # Use streaming apply for real-time resource creation events
        add_log("Applying Terraform changes...", "info", project_name)

        result = service.apply_fresh_streaming(on_event=_on_tf_event)

        if not result["success"]:
            state["status"] = "error"
            state["error"] = result.get("stderr", "Apply failed")
            add_log(f"Error: {state['error']}", "error", project_name)
            return

        complete_phase("apply", project_name)

        # Phase: Get outputs
        update_phase("outputs", project_name)
        result = service.output()
        complete_phase("outputs", project_name)

        # CRITICAL #3 fix (2026-05-28): `service.output()` can fail silently —
        # e.g., when terraform-output returns non-zero because the state has no
        # outputs declared, or the workspace race (CRITICAL #1 + #2) selected
        # the wrong workspace and that one has no state. Previously this code
        # blindly read `result["outputs"]` and persisted an empty dict, which
        # rendered as a green "Deployment complete" with an empty connection
        # block in the Manage hero. Surface the failure both in the log stream
        # and as a structured `output_warning` so the UI can show "outputs
        # unavailable — re-run terraform output manually" instead.
        output_warning = None
        if not result.get("success"):
            stderr_snippet = (result.get("stderr") or "").strip().splitlines()[:3]
            stderr_summary = " | ".join(stderr_snippet) if stderr_snippet else "no stderr"
            output_warning = (
                "Terraform outputs unavailable after apply — connection details "
                "may not render in Manage. Re-run `terraform output -json` "
                f"manually in workspace '{service.workspace_name}'. ({stderr_summary})"
            )
            try:
                print(f"[deploy] WARNING [{project_name}]: {output_warning}")
            except Exception:
                pass
            add_log(output_warning, "warning", project_name)

        # Decrypt Windows attack box password from EC2Launch v2 if applicable
        sensitive_outputs = {}
        all_outputs = result.get("outputs", {}) or {}
        attack_box_id = all_outputs.get("attack_box_instance_id", {}).get("value")
        if attack_box_id:
            win_pwd = get_windows_password(attack_box_id, service)
            if win_pwd:
                sensitive_outputs["attack_box_admin_password"] = {"value": win_pwd, "sensitive": True}

        # Success!
        state["status"] = "success"
        state["step"] = "Deployment complete"
        state["progress_percent"] = 100
        state["completed_at"] = time.time()
        all_outputs.update(sensitive_outputs)
        state["output"] = all_outputs
        if output_warning:
            # Persist so the Manage hero can read it and surface an
            # actionable banner instead of an empty connection block.
            state["output_warning"] = output_warning
        elapsed = int(state["completed_at"] - state["started_at"])
        add_log(f"Deployment completed successfully in {elapsed // 60}m {elapsed % 60}s", "success", project_name)
        _persist_state(project_name, state)

        # Create GOAD deployment marker for GOAD/combined deployments
        # This enables /goad/credentials, /goad/jumpbox, and other GOAD-specific endpoints
        if deploy_type and ('goad' in deploy_type or 'combined' in deploy_type):
            try:
                from webapp.backend.utils.config_parser import get_goad_lab_type
                goad_workspace = project_root / 'goad_workspace'
                goad_workspace.mkdir(parents=True, exist_ok=True)
                deployment_marker = goad_workspace / 'current_deployment.json'
                lab_type = get_goad_lab_type(deploy_type) or deploy_type
                import json as json_mod
                with open(deployment_marker, 'w') as f:
                    json_mod.dump({
                        'lab_name': lab_type,
                        'project_name': project_name,
                        'deployment_type': deploy_type,
                        'status': 'deployed',
                        'deployed_at': time.strftime('%Y-%m-%dT%H:%M:%S')
                    }, f, indent=2)
                add_log("Created GOAD deployment marker", "info", project_name)
            except Exception as e:
                add_log(f"Warning: Could not create GOAD marker: {e}", "warning", project_name)

        # Save deployed resources to history for this project
        save_deployment_resources(project_name, service, deploy_type)

    except Exception as e:
        state["status"] = "error"
        state["error"] = str(e)
        state["completed_at"] = time.time()
        add_log(f"Unexpected error: {str(e)}", "error", project_name)
        _persist_state(project_name, state)


def save_deployment_resources(project_name: str, service: TerraformService, deployment_type: str):
    """
    Save the list of deployed resources for a project after successful deployment.
    This allows tracking resources per deployment even with multiple concurrent deployments.
    """
    import boto3
    from webapp.backend.utils.config_parser import ConfigParser
    from datetime import datetime
    
    try:
        # Get config for region
        config = ConfigParser.parse_tfvars(service.tfvars_file) if service.tfvars_file.exists() else {}
        aws_region = config.get('aws_region', 'eu-central-1')
        
        # Query AWS for all resources with this project tag
        resources = []
        ec2 = boto3.client('ec2', region_name=aws_region)
        
        # EC2 Instances
        try:
            response = ec2.describe_instances(
                Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
            )
            for reservation in response.get('Reservations', []):
                for instance in reservation.get('Instances', []):
                    name = next((t['Value'] for t in instance.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                    role = next((t['Value'] for t in instance.get('Tags', []) if t['Key'] == 'Role'), '')
                    resources.append({
                        'type': 'ec2',
                        'id': instance['InstanceId'],
                        'name': name,
                        'role': role,
                        'state': instance['State']['Name'],
                        'instance_type': instance['InstanceType'],
                        'private_ip': instance.get('PrivateIpAddress'),
                        'public_ip': instance.get('PublicIpAddress')
                    })
        except Exception as e:
            print(f"Error fetching EC2 instances: {e}")
        
        # VPCs
        try:
            response = ec2.describe_vpcs(
                Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
            )
            for vpc in response.get('Vpcs', []):
                name = next((t['Value'] for t in vpc.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                resources.append({
                    'type': 'vpc',
                    'id': vpc['VpcId'],
                    'name': name,
                    'state': vpc['State'],
                    'cidr': vpc['CidrBlock']
                })
        except Exception as e:
            print(f"Error fetching VPCs: {e}")
        
        # Subnets
        try:
            response = ec2.describe_subnets(
                Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
            )
            for subnet in response.get('Subnets', []):
                name = next((t['Value'] for t in subnet.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                resources.append({
                    'type': 'subnet',
                    'id': subnet['SubnetId'],
                    'name': name,
                    'state': subnet['State'],
                    'cidr': subnet['CidrBlock'],
                    'az': subnet['AvailabilityZone']
                })
        except Exception as e:
            print(f"Error fetching subnets: {e}")
        
        # Security Groups
        try:
            response = ec2.describe_security_groups(
                Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
            )
            for sg in response.get('SecurityGroups', []):
                resources.append({
                    'type': 'security_group',
                    'id': sg['GroupId'],
                    'name': sg['GroupName'],
                    'state': 'active',
                    'description': sg.get('Description', '')[:100]
                })
        except Exception as e:
            print(f"Error fetching security groups: {e}")
        
        # NAT Gateways
        try:
            response = ec2.describe_nat_gateways(
                Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
            )
            for nat in response.get('NatGateways', []):
                name = next((t['Value'] for t in nat.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                public_ip = nat.get('NatGatewayAddresses', [{}])[0].get('PublicIp', 'N/A')
                resources.append({
                    'type': 'nat_gateway',
                    'id': nat['NatGatewayId'],
                    'name': name,
                    'state': nat['State'],
                    'public_ip': public_ip
                })
        except Exception as e:
            print(f"Error fetching NAT gateways: {e}")
        
        # Elastic IPs
        try:
            response = ec2.describe_addresses(
                Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
            )
            for eip in response.get('Addresses', []):
                name = next((t['Value'] for t in eip.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                resources.append({
                    'type': 'elastic_ip',
                    'id': eip.get('AllocationId', 'N/A'),
                    'name': name,
                    'state': 'associated' if eip.get('InstanceId') else 'available',
                    'public_ip': eip.get('PublicIp')
                })
        except Exception as e:
            print(f"Error fetching Elastic IPs: {e}")
        
        # S3 Buckets
        try:
            s3 = boto3.client('s3', region_name=aws_region)
            response = s3.list_buckets()
            project_prefix = project_name.lower().replace('_', '-')
            for bucket in response.get('Buckets', []):
                if bucket['Name'].lower().startswith(project_prefix):
                    resources.append({
                        'type': 's3_bucket',
                        'id': bucket['Name'],
                        'name': bucket['Name'],
                        'state': 'available',
                        'created': bucket['CreationDate'].isoformat()
                    })
        except Exception as e:
            print(f"Error fetching S3 buckets: {e}")
        
        # Key Pairs
        try:
            response = ec2.describe_key_pairs(
                Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
            )
            for kp in response.get('KeyPairs', []):
                resources.append({
                    'type': 'key_pair',
                    'id': kp.get('KeyPairId', kp['KeyName']),
                    'name': kp['KeyName'],
                    'state': 'available',
                    'key_type': kp.get('KeyType', 'rsa')
                })
        except Exception as e:
            print(f"Error fetching key pairs: {e}")
        
        # Internet Gateways
        try:
            response = ec2.describe_internet_gateways(
                Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
            )
            for igw in response.get('InternetGateways', []):
                name = next((t['Value'] for t in igw.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                attached = 'attached' if igw.get('Attachments') else 'detached'
                resources.append({
                    'type': 'internet_gateway',
                    'id': igw['InternetGatewayId'],
                    'name': name,
                    'state': attached
                })
        except Exception as e:
            print(f"Error fetching Internet Gateways: {e}")
        
        # Route Tables
        try:
            response = ec2.describe_route_tables(
                Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
            )
            for rt in response.get('RouteTables', []):
                name = next((t['Value'] for t in rt.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                route_count = len(rt.get('Routes', []))
                resources.append({
                    'type': 'route_table',
                    'id': rt['RouteTableId'],
                    'name': name,
                    'state': 'active',
                    'route_count': route_count
                })
        except Exception as e:
            print(f"Error fetching route tables: {e}")
        
        # Network Interfaces (ENIs)
        try:
            response = ec2.describe_network_interfaces(
                Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
            )
            for eni in response.get('NetworkInterfaces', []):
                name = next((t['Value'] for t in eni.get('TagSet', []) if t['Key'] == 'Name'), 'Unnamed')
                private_ip = eni.get('PrivateIpAddress', 'N/A')
                resources.append({
                    'type': 'network_interface',
                    'id': eni['NetworkInterfaceId'],
                    'name': name,
                    'state': eni.get('Status', 'unknown'),
                    'private_ip': private_ip
                })
        except Exception as e:
            print(f"Error fetching network interfaces: {e}")
        
        # IAM Roles
        try:
            iam = boto3.client('iam', region_name=aws_region)
            project_prefix = project_name.lower().replace('_', '-')
            paginator = iam.get_paginator('list_roles')
            for page in paginator.paginate():
                for role in page.get('Roles', []):
                    if role['RoleName'].lower().startswith(project_prefix):
                        resources.append({
                            'type': 'iam_role',
                            'id': role['RoleId'],
                            'name': role['RoleName'],
                            'state': 'active',
                            'created': role['CreateDate'].isoformat()
                        })
        except Exception as e:
            print(f"Error fetching IAM roles: {e}")
        
        # IAM Instance Profiles
        try:
            iam = boto3.client('iam', region_name=aws_region)
            project_prefix = project_name.lower().replace('_', '-')
            paginator = iam.get_paginator('list_instance_profiles')
            for page in paginator.paginate():
                for profile in page.get('InstanceProfiles', []):
                    if profile['InstanceProfileName'].lower().startswith(project_prefix):
                        resources.append({
                            'type': 'iam_instance_profile',
                            'id': profile['InstanceProfileId'],
                            'name': profile['InstanceProfileName'],
                            'state': 'active',
                            'role_count': len(profile.get('Roles', []))
                        })
        except Exception as e:
            print(f"Error fetching IAM instance profiles: {e}")
        
        # Save to deployment resources file
        resources_file = project_root / "logs" / "deployment_resources.json"
        resources_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing resources
        all_deployments = {}
        if resources_file.exists():
            try:
                with open(resources_file, 'r') as f:
                    all_deployments = json.load(f)
            except:
                pass
        
        # Save this deployment's resources
        all_deployments[project_name] = {
            'project_name': project_name,
            'deployment_type': deployment_type,
            'deployed_at': datetime.now().isoformat(),
            'region': aws_region,
            'resource_count': len(resources),
            'resources': resources
        }
        
        with open(resources_file, 'w') as f:
            json.dump(all_deployments, f, indent=2)
        
        add_log(f"Saved {len(resources)} resources for project '{project_name}'", "info", project_name)
        
    except Exception as e:
        print(f"Error saving deployment resources: {e}")
        add_log(f"Warning: Could not save resource list: {e}", "warning", project_name)

def run_destroy(project_name: str = None):
    """Run destroy in background thread with phased destruction for combined mode.
    Tracks before/after resource counts and parses terraform output for detailed reporting."""
    global deployment_state

    # Use project-specific state if provided
    if project_name and project_name in deployment_states:
        state = deployment_states[project_name]
        service = get_service_for_project(project_name)
    else:
        state = deployment_state
        service = terraform_service

    all_destroyed = []
    all_errors = []

    try:
        state["status"] = "running"
        state["output"] = ""
        state["error"] = None

        add_log("Starting infrastructure destruction...", "warning", project_name)
        state["progress_percent"] = 5

        # Count resources before destroy
        resources_before = {'count': 0, 'by_service': {}, 'resources': []}
        if project_name:
            state["step"] = "Counting existing resources..."
            add_log("Querying AWS for tagged resources before destroy...", "info", project_name)
            resources_before = query_remaining_resources(project_name)
            if resources_before['count'] > 0:
                breakdown = ", ".join(f"{c} {s}" for s, c in sorted(
                    resources_before['by_service'].items(), key=lambda x: -x[1]))
                add_log(f"Found {resources_before['count']} tagged resources: {breakdown}", "info", project_name)

        # Get current deployment type
        output_result = service.output()
        outputs = output_result.get("outputs", {})
        deployment_type = outputs.get("deployment_type", {}).get("value", "")

        # Check if combined mode (requires phased destruction)
        is_combined = deployment_type.startswith("combined-")
        destroy_failed = False

        state["progress_percent"] = 10

        def _on_tf_destroy_event(message, event_type):
            add_log(message, event_type, project_name)

        if is_combined:
            # Phase 1: Destroy VPC peering first
            state["step"] = "Phase 1/3: Destroying VPC peering..."
            state["progress_percent"] = 15
            add_log("Phase 1/3: Destroying VPC peering...", "info", project_name)
            result = service.destroy_target("module.vpc_peering")
            parsed = parse_terraform_destroy_output(result.get("stdout", ""), result.get("stderr", ""))
            all_destroyed.extend(parsed['destroyed'])
            all_errors.extend(parsed['errors'])
            if not result["success"]:
                state["status"] = "error"
                state["error"] = result.get("stderr", "Failed to destroy VPC peering")
                add_log(f"Failed to destroy VPC peering: {state['error'][:500]}", "error", project_name)
                destroy_failed = True

            if not destroy_failed:
                # Phase 2: Destroy GOAD
                state["step"] = "Phase 2/3: Destroying GOAD lab..."
                state["progress_percent"] = 35
                add_log("Phase 2/3: Destroying GOAD lab...", "info", project_name)
                result = service.destroy_target("module.goad")
                parsed = parse_terraform_destroy_output(result.get("stdout", ""), result.get("stderr", ""))
                all_destroyed.extend(parsed['destroyed'])
                all_errors.extend(parsed['errors'])
                if not result["success"]:
                    state["status"] = "error"
                    state["error"] = result.get("stderr", "Failed to destroy GOAD")
                    add_log(f"Failed to destroy GOAD: {state['error'][:500]}", "error", project_name)
                    destroy_failed = True

            if not destroy_failed:
                # Phase 3: Destroy remaining C2 infrastructure
                state["step"] = "Phase 3/3: Destroying C2 infrastructure..."
                state["progress_percent"] = 55
                add_log("Phase 3/3: Destroying C2 infrastructure...", "info", project_name)
                result = service.destroy_streaming(on_event=_on_tf_destroy_event)
                parsed = parse_terraform_destroy_output(result.get("stdout", ""), result.get("stderr", ""))
                all_destroyed.extend(parsed['destroyed'])
                all_errors.extend(parsed['errors'])
                if not result["success"]:
                    state["status"] = "error"
                    state["error"] = result.get("stderr", "Failed to destroy C2 infrastructure")
                    add_log(f"Failed to destroy C2 infrastructure: {state['error'][:500]}", "error", project_name)
                    destroy_failed = True
        else:
            # Standard destroy for non-combined modes
            state["step"] = "Destroying infrastructure..."
            state["progress_percent"] = 15
            add_log("Running terraform destroy...", "info", project_name)
            result = service.destroy_streaming(on_event=_on_tf_destroy_event)
            parsed = parse_terraform_destroy_output(result.get("stdout", ""), result.get("stderr", ""))
            all_destroyed.extend(parsed['destroyed'])
            all_errors.extend(parsed['errors'])
            if not result["success"]:
                state["status"] = "error"
                state["error"] = result.get("stderr", "Destroy failed")
                add_log(f"Destroy failed: {state['error'][:500]}", "error", project_name)
                destroy_failed = True

        if not destroy_failed:
            state["progress_percent"] = 85
            for d in all_destroyed:
                add_log(f"Destroyed: {d['address']} ({d['duration']})", "success", project_name)
            state["step"] = "Terraform destroy complete, verifying cleanup..."
            state["deployment_type"] = None
            add_log(f"Terraform destroy complete: {len(all_destroyed)} resources removed. Verifying...", "success", project_name)

        # Query remaining resources after destroy (success or failure)
        state["progress_percent"] = 90
        resources_after = {'count': 0, 'by_service': {}, 'resources': []}
        if project_name:
            state["step"] = "Verifying cleanup..."
            add_log("Querying AWS for remaining resources...", "info", project_name)
            resources_after = query_remaining_resources(project_name)
            filtered = resources_after.get('filtered_dead', 0)
            if filtered > 0:
                add_log(f"Filtered {filtered} terminated/deleted resources (AWS retains tags temporarily)", "info", project_name)
            if resources_after['count'] > 0:
                breakdown = ", ".join(f"{c} {s}" for s, c in sorted(
                    resources_after['by_service'].items(), key=lambda x: -x[1]))
                add_log(f"WARNING: {resources_after['count']} live resources still remain: {breakdown}", "warning", project_name)
            elif resources_after['count'] == 0:
                add_log("Verification complete: no live resources remain in AWS", "success", project_name)

        # Store structured result
        state["progress_percent"] = 95
        state["purge_result"] = {
            "resources_before": resources_before.get('count', 0),
            "resources_after": resources_after.get('count', 0),
            "resources_after_by_service": resources_after.get('by_service', {}),
            "resources_after_list": resources_after.get('resources', []),
            "terraform_destroyed": all_destroyed,
            "terraform_destroyed_count": len(all_destroyed),
            "terraform_errors": all_errors,
            "terraform_error_count": len(all_errors),
            "filtered_dead": filtered if project_name else 0,
        }

        if not destroy_failed:
            state["status"] = "success"
            state["step"] = "Infrastructure destroyed"

        # Clean up Terraform workspace after successful destroy
        if state["status"] == "success" and service.workspace_name != "default":
            try:
                ws_result = service.workspace_delete(service.workspace_name)
                if ws_result.get("success"):
                    add_log(f"Workspace '{service.workspace_name}' cleaned up", "info", project_name)
                    # Also remove workspace-specific tfvars
                    if service.tfvars_file.exists():
                        service.tfvars_file.unlink()
            except Exception as ws_err:
                add_log(f"Workspace cleanup warning: {ws_err}", "warning", project_name)

        state["progress_percent"] = 100
        state["completed_at"] = time.time()

        # 2026-05-28 — Real-pipeline audit fix (CRITICAL #5): persist
        # destroyed deployments with status="destroyed" (NOT "success")
        # so /api/deploy/active's `status == "success"` filter (line ~249)
        # naturally excludes them. Previously a destroyed deployment kept
        # its file with status="success" forever — the top-bar dropdown
        # showed ghost entries indefinitely with stale outputs.
        # In-memory deployment_states[project] retains status="success"
        # for the current polling cycle so the frontend's destroy UI sees
        # the final success state correctly — only the on-disk record
        # gets the destroyed flag.
        persisted_state = dict(state)
        if state["status"] == "success":
            persisted_state["status"] = "destroyed"
            persisted_state["destroyed_at"] = state["completed_at"]
        _persist_state(project_name, persisted_state)

    except Exception as e:
        state["status"] = "error"
        state["error"] = str(e)
        state["completed_at"] = time.time()
        add_log(f"Destroy error: {str(e)}", "error", project_name)
        _persist_state(project_name, state)

@bp.route('/status', methods=['GET'])
def get_deployment_status():
    """Get current deployment status with enhanced progress info"""
    # Check if requesting specific project status
    project_name = request.args.get('project')

    # 2026-05-28 — demo bypass. Dashboard's Architecture widget reads
    # `deployment_type` from this endpoint; without the bypass it gets
    # an empty fallback state with deployment_type=None and the widget
    # never resolves a diagram. Return a deployment_state shape with
    # `models_deployment_type` surfaced under the legacy `deployment_type`
    # key (the widget reads either) so the c2-adhoc architecture image
    # resolves.
    #
    # Phase 4 — demo-draft EXCEPTION: walkthrough deployments need their
    # real in-memory tick state surfaced (status=running, progress,
    # current_phase, live log buffer) so the operator sees the synthetic
    # Apply animate. Only the literal "demo" showcase project should
    # short-circuit to the static fixture. Demo-draft entries fall
    # through to the normal deployment_states[project_name] lookup below
    # — they're still flagged is_demo in their state file so downstream
    # bypasses (outputs, beacon, terminal) keep working.
    try:
        from webapp.backend.services import demo_data_service
        _is_demo = demo_data_service.is_demo_project(project_name)
    except Exception:
        _is_demo = False
    _is_demo_draft_status = (
        isinstance(project_name, str)
        and project_name.startswith("demo-draft-")
    )
    if _is_demo and not _is_demo_draft_status:
        demo_state = demo_data_service.deployment_state()
        return jsonify({
            "success": True,
            "is_demo": True,
            "status": {
                "status": demo_state.get("status", "success"),
                "step": demo_state.get("step", "complete"),
                "output": demo_state.get("output", {}),
                "error": None,
                "deployment_type": demo_state.get("models_deployment_type")
                                   or demo_state.get("deployment_type"),
                "deployed": True,
                "progress_percent": demo_state.get("progress_percent", 100),
                "current_phase": demo_state.get("current_phase", "operational"),
                "current_phase_name": demo_state.get("current_phase", "operational"),
                "phases": DEPLOYMENT_PHASES,
                "phases_completed": demo_state.get("phases_completed", []),
                "total_resources": demo_state.get("total_resources", 0),
                "resources_completed": demo_state.get("resources_completed", 0),
                "elapsed_seconds": 0,
                "elapsed_formatted": "0m 0s",
                "logs": [],
                "purge_result": None,
                "project_name": project_name,
            },
        })

    if project_name and project_name in deployment_states:
        state = deployment_states[project_name]
    elif project_name:
        # Try loading from disk (e.g., after server restart)
        state = get_project_state(project_name)
    else:
        state = deployment_state

    # Calculate elapsed time if running
    elapsed_seconds = 0
    if state["started_at"]:
        if state["completed_at"]:
            elapsed_seconds = int(state["completed_at"] - state["started_at"])
        else:
            elapsed_seconds = int(time.time() - state["started_at"])

    # Guard against negative elapsed (stale completed_at from a previous operation)
    elapsed_seconds = max(0, elapsed_seconds)

    # Format elapsed time
    elapsed_formatted = f"{elapsed_seconds // 60}m {elapsed_seconds % 60}s"
    
    return jsonify({
        "success": True,
        "status": {
            "status": state["status"],
            "step": state["step"],
            "output": state["output"],
            "error": state["error"],
            "deployment_type": state.get("deployment_type"),
            # Progress info — driven by real resource completion events
            "progress_percent": state.get("progress_percent", 0),
            "current_phase": state.get("current_phase", ""),
            "current_phase_name": state.get("current_phase_name", ""),
            "phases": DEPLOYMENT_PHASES,
            "phases_completed": state.get("phases_completed", []),
            "total_resources": state.get("total_resources", 0),
            "resources_completed": state.get("resources_completed", 0),
            "elapsed_seconds": elapsed_seconds,
            "elapsed_formatted": elapsed_formatted,
            "logs": state.get("logs", []),
            "purge_result": state.get("purge_result"),
            "project_name": project_name
        }
    })


# /status/all removed 2026-05-21 — no frontend or script caller; the
# Manage fleet view uses /api/deploy/active (which surfaces all
# successful per-project state files). The "default" legacy single-
# deployment view is no longer presented in the V3 UI.


# /workspaces removed 2026-05-21 — debugging endpoint with no frontend or
# script callers. The Configure / Manage UIs read per-project deployment
# state from logs/deployment_state/*.state.json (via /api/deploy/active),
# not from terraform workspace listings. Use that endpoint for the same
# information.


@bp.route('/check-project-name', methods=['GET'])
def check_project_name():
    """
    Check if a project name is available (not already in use).
    Checks both local Terraform workspaces AND AWS resources directly.
    Returns whether the name is available and any existing resources.
    """
    import boto3
    import re
    from webapp.backend.utils.config_parser import ConfigParser
    
    project_name = request.args.get('name', '').strip()
    
    if not project_name:
        return jsonify({
            "success": False,
            "error": "Project name is required"
        }), 400
    
    # Validate project name format
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', project_name):
        return jsonify({
            "success": True,
            "available": False,
            "error": "Invalid project name. Must start with a letter and contain only letters, numbers, underscores, and hyphens.",
            "valid_format": False
        })
    
    # Check if currently deploying locally
    if project_name in deployment_states and deployment_states[project_name].get("status") == "running":
        return jsonify({
            "success": True,
            "available": False,
            "reason": "currently_deploying",
            "message": f"Project '{project_name}' is currently being deployed"
        })
    
    # Check deployment history for previously used names
    history = load_deployment_history()
    project_history = [h for h in history if h.get('project_name') == project_name]
    if project_history:
        # Check if there were any errors or if it was purged
        has_errors = any(h.get('level') == 'error' for h in project_history)
        was_purged = any('purge' in h.get('message', '').lower() for h in project_history)
        last_entry = project_history[-1] if project_history else None
        last_time = last_entry.get('timestamp', 'unknown') if last_entry else 'unknown'
        
        # This is a warning, not a block - user can still proceed
        # We'll return available=True but with a warning
        history_warning = {
            "previously_used": True,
            "entry_count": len(project_history),
            "had_errors": has_errors,
            "was_purged": was_purged,
            "last_activity": last_time
        }
    else:
        history_warning = None
    
    # Get AWS region from config — prefer the candidate project's per-project
    # tfvars (if any) so check-project-name surfaces the right region when the
    # operator is naming a candidate that already has a stub config on disk.
    aws_region = 'eu-central-1'  # Default
    config = _read_project_config(project_name)
    if config:
        aws_region = config.get('aws_region', 'eu-central-1')

    # Check AWS using Resource Groups Tagging API — finds ALL resources with Project tag
    # This is comprehensive: covers EC2, VPC, S3, IAM, Secrets Manager, Security Groups, etc.
    aws_check = {"checked": False, "found": 0, "by_service": {}, "error": None}
    try:
        tagging = boto3.client('resourcegroupstaggingapi', region_name=aws_region)
        paginator = tagging.get_paginator('get_resources')
        pages = paginator.paginate(
            TagFilters=[{'Key': 'Project', 'Values': [project_name]}],
            ResourcesPerPage=100
        )

        aws_resources = []
        by_service = {}
        for page in pages:
            for r in page.get('ResourceTagMappingList', []):
                arn = r['ResourceARN']
                # Extract service from ARN (arn:aws:SERVICE:region:account:...)
                parts = arn.split(':')
                service = parts[2] if len(parts) > 2 else 'unknown'
                resource_id = parts[-1].split('/')[-1] if parts else arn
                aws_resources.append({'arn': arn, 'service': service, 'resource_id': resource_id})
                by_service[service] = by_service.get(service, 0) + 1

        aws_check["checked"] = True
        aws_check["found"] = len(aws_resources)
        aws_check["by_service"] = by_service

        if aws_resources:
            # Build human-readable service breakdown
            breakdown = ", ".join(f"{count} {svc}" for svc, count in sorted(by_service.items(), key=lambda x: -x[1]))
            return jsonify({
                "success": True,
                "available": False,
                "reason": "aws_resources_exist",
                "resource_count": len(aws_resources),
                "breakdown": breakdown,
                "by_service": by_service,
                "message": f"Project '{project_name}' has {len(aws_resources)} AWS resources ({breakdown})",
                "source": "aws",
                "checks": {
                    "aws_tagging": aws_check,
                    "deployment_history": {"checked": True, "previously_used": bool(history_warning)} if history_warning else {"checked": True, "previously_used": False}
                }
            })
    except Exception as e:
        aws_check["checked"] = True
        aws_check["error"] = str(e)
        print(f"AWS Resource Groups Tagging API check failed: {e}")
    
    # Check local Terraform workspaces
    local_check = {"checked": False, "found": False, "resources": 0, "error": None}
    try:
        init_result = terraform_service.init()
        if init_result["success"]:
            ws_list = terraform_service.workspace_list()
            local_check["checked"] = True
            if ws_list["success"] and project_name in ws_list.get("workspaces", []):
                terraform_service.workspace_select(project_name)
                state_result = terraform_service.show()
                # Restore default workspace so other endpoints aren't affected
                terraform_service.workspace_select("default")

                if state_result["success"]:
                    state = state_result.get("state", {})
                    resources = state.get("values", {}).get("root_module", {}).get("resources", [])

                    if resources and len(resources) > 0:
                        local_check["found"] = True
                        local_check["resources"] = len(resources)
                        return jsonify({
                            "success": True,
                            "available": False,
                            "reason": "has_local_resources",
                            "resource_count": len(resources),
                            "message": f"Project '{project_name}' exists locally with {len(resources)} Terraform resources",
                            "source": "local",
                            "checks": {
                                "aws_tagging": aws_check,
                                "local_workspace": local_check,
                                "deployment_history": {"checked": True, "previously_used": bool(history_warning)} if history_warning else {"checked": True, "previously_used": False}
                            }
                        })

                # Workspace exists but is empty - allow reuse with warning
                local_check["found"] = True
                local_check["resources"] = 0
                response = {
                    "success": True,
                    "available": True,
                    "workspace_exists": True,
                    "message": f"Project '{project_name}' workspace exists but has no resources",
                    "checks": {
                        "aws_tagging": aws_check,
                        "local_workspace": local_check,
                        "deployment_history": {"checked": True, "previously_used": bool(history_warning)} if history_warning else {"checked": True, "previously_used": False}
                    }
                }
                if history_warning:
                    response["history"] = history_warning
                    response["message"] += " (previously used)"
                return jsonify(response)
    except Exception as e:
        local_check["checked"] = True
        local_check["error"] = str(e)
        print(f"Local workspace check failed: {e}")

    # Build final checks summary
    checks = {
        "aws_tagging": aws_check,
        "local_workspace": local_check,
        "deployment_history": {"checked": True, "previously_used": bool(history_warning)} if history_warning else {"checked": True, "previously_used": False}
    }

    # If AWS check failed entirely, warn the user rather than silently passing
    if aws_check.get("error"):
        response = {
            "success": True,
            "available": True,
            "aws_warning": f"Could not verify AWS resources: {aws_check['error']}",
            "message": f"Project name '{project_name}' appears available (AWS check failed — verify manually)",
            "checks": checks
        }
        if history_warning:
            response["history"] = history_warning
        return jsonify(response)

    # Project name is available
    response = {
        "success": True,
        "available": True,
        "message": f"Project name '{project_name}' is available",
        "checks": checks
    }
    if history_warning:
        response["history"] = history_warning
        response["warning"] = f"This name was previously used ({history_warning['entry_count']} history entries)"
    return jsonify(response)


# /generate-project-name removed 2026-05-21 — no frontend or script
# caller. The frontend now composes project names client-side from
# /api/deploy/machine-info (returns sanitized hostname) + the operator-
# selected deployment_type / environment in Configure V2.


@bp.route('/machine-info', methods=['GET'])
def get_machine_info():
    """
    Get information about the current machine for project naming.
    """
    import socket
    import re
    import platform
    
    hostname = socket.gethostname()
    # Sanitize hostname for use in project names
    sanitized_hostname = re.sub(r'[^a-zA-Z0-9]', '_', hostname.lower())
    sanitized_hostname = re.sub(r'_+', '_', sanitized_hostname).strip('_')
    if len(sanitized_hostname) > 20:
        sanitized_hostname = sanitized_hostname[:20].rstrip('_')
    
    return jsonify({
        "success": True,
        "hostname": hostname,
        "machine_suffix": sanitized_hostname,
        "platform": platform.system(),
        "message": f"Your machine suffix is '{sanitized_hostname}' (from hostname '{hostname}')"
    })


@bp.route('/deploy', methods=['POST'])
def deploy():
    """Start deployment for a specific project"""
    global deployment_state

    # Get request data
    data = request.get_json() or {}

    # ── Phase 4: synthetic walkthrough deploy ───────────────────────────
    # When the operator launches "+ Provision a Demo Deployment" from the
    # Dashboard, the body carries is_demo_draft=true OR project_name
    # starts with "demo-draft-". Skip ALL prereq checks (no CS file, no
    # domain, no AWS CLI, no IAM) and spawn a background thread that
    # walks DEPLOYMENT_PHASES over ~30s with realistic per-phase logs.
    # No terraform shell-out, no tfvars read, no AWS calls.
    _body_demo_flag = bool(data.get("is_demo_draft")) if isinstance(data, dict) else False
    _body_project = (data.get("project_name") or "").strip() if isinstance(data, dict) else ""
    _query_project = (request.args.get("project") or "").strip()
    _candidate_name = _body_project or _query_project
    _is_demo_draft = _body_demo_flag or _candidate_name.startswith("demo-draft-")
    if _is_demo_draft:
        if not _candidate_name:
            return jsonify({
                "success": False,
                "error": "demo-draft deploy requires project_name"
            }), 400
        project_name = _candidate_name
        # Idempotent — if the synthetic tick is already running for this
        # draft, return the same envelope so the frontend Apply button
        # doesn't double-spawn.
        if project_name in deployment_states and deployment_states[project_name].get("status") == "running":
            return jsonify({
                "success": True,
                "is_demo": True,
                "message": f"Demo deployment '{project_name}' is already in progress",
                "project_name": project_name,
                "deployment_type": "demo",
            })
        # Fresh state — mirrors create_empty_state() but flagged is_demo
        # so the persisted JSON triggers is_demo_project() downstream.
        deployment_states[project_name] = create_empty_state()
        state = deployment_states[project_name]
        state["status"] = "running"
        state["step"] = "Initializing demo walkthrough..."
        state["started_at"] = time.time()
        state["progress_percent"] = 0
        state["error"] = None
        state["logs"] = []
        state["is_demo"] = True
        state["is_demo_draft"] = True
        state["deployment_type"] = "demo"
        _persist_state(project_name, state)
        try:
            audit_service.write(
                _audit_actor(),
                "deploy.demo_draft.start",
                project=project_name,
                details={"is_demo": True, "is_demo_draft": True},
            )
        except Exception:
            pass
        thread = threading.Thread(target=run_demo_draft_deployment, args=(project_name,))
        thread.daemon = True
        thread.start()
        return jsonify({
            "success": True,
            "is_demo": True,
            "message": "Demo deployment started",
            "project_name": project_name,
            "deployment_type": "demo",
        })

    # Load configuration to get project name
    from webapp.backend.utils.config_parser import ConfigParser
    from webapp.backend.utils.validators import ConfigValidator

    config_dir = project_root / "configs"
    global_tfvars = config_dir / "terraform.tfvars"

    # Per-project tfvars resolution (?project= wins over body.project_name).
    # Configure V2 saves to configs/<project>.tfvars — Deploy must read from
    # the same per-project file, not the stale global tfvars. Sentinel
    # values (__draft__ / __all__) fall back to global so unsaved drafts
    # still surface a clear "configure first" error below.
    project_param = request.args.get("project") or (data.get("project_name") if isinstance(data, dict) else None)
    tfvars_file, _resolved_workspace = _resolve_project_tfvars(project_param, global_tfvars)

    if not tfvars_file.exists():
        return jsonify({
            "success": False,
            "error": "Configuration file (terraform.tfvars) not found. Please configure infrastructure first."
        }), 400

    config = ConfigParser.parse_tfvars(tfvars_file)
    project_name = config.get('project_name', '').strip()
    deployment_type = config.get('deployment_type', '').strip()
    
    if not project_name:
        return jsonify({
            "success": False,
            "error": "Project name not configured. Please set project_name in configuration."
        }), 400
    
    # Check if THIS project is already deploying
    if project_name in deployment_states and deployment_states[project_name].get("status") == "running":
        return jsonify({
            "success": False,
            "error": f"Project '{project_name}' is already deploying"
        }), 400
    
    # Also check legacy single deployment state
    if deployment_state["status"] == "running":
        return jsonify({
            "success": False,
            "error": "Another deployment is already in progress"
        }), 400
    
    # Note: We skip the workspace existence check here to avoid blocking.
    # The deployment thread will handle workspace creation/selection.
    # If resources already exist, Terraform will detect conflicts during apply.
    
    # Define which deployment types require what prerequisites
    GOAD_ONLY_TYPES = ['goad-mini', 'goad-light', 'goad-sccm', 'goad-full', 'goad-nha']
    C2_ONLY_TYPES = ['c2-adhoc', 'c2-purple', 'c2-full']
    COMBINED_TYPES = ['combined-adhoc-mini', 'combined-adhoc-light', 'combined-full-full']
    # CCRTS-Lab: the single self-contained `ccrts` type ships its own
    # CS-on-Kali (no upload) and is internal-only (no public domain).
    CCRTS_ONLY_TYPES = ['ccrts']

    is_ccrts_only = deployment_type in CCRTS_ONLY_TYPES

    # All deployments with CS need the CS file uploaded — EXCEPT the
    # `ccrts` lab which boots CS from the CREST Community Kali AMI.
    requires_cobalt_strike = not is_ccrts_only

    # Only C2 / Combined need a public domain. The `ccrts` lab is
    # internal-only behind the dashboard server jump.
    requires_domain = (
        deployment_type in C2_ONLY_TYPES
        or deployment_type in COMBINED_TYPES
    )
    
    # Check prerequisite: Cobalt Strike file
    if requires_cobalt_strike:
        cobalt_strike_files = list(UPLOAD_FOLDER.glob("*"))
        has_file = any(
            f.is_file() and allowed_file(f.name)
            for f in cobalt_strike_files
        )
        
        if not has_file:
            return jsonify({
                "success": False,
                "error": "Cobalt Strike file must be uploaded before deployment. Please upload the file first."
            }), 400
    
    # Check prerequisite: Domain configuration
    if requires_domain:
        primary_domain = config.get("primary_domain_name", "").strip()
        
        if not primary_domain:
            return jsonify({
                "success": False,
                "error": "Domain configuration is required for C2 deployments. Please configure primary_domain_name."
            }), 400
        
        domain_valid, domain_errors = ConfigValidator.validate_domain_config(config)
        if not domain_valid:
            return jsonify({
                "success": False,
                "error": f"Domain configuration is invalid: {', '.join(domain_errors)}"
            }), 400
    
    # Initialize project-specific state
    deployment_states[project_name] = create_empty_state()
    state = deployment_states[project_name]
    
    # Set initial state BEFORE starting the thread
    state["status"] = "running"
    state["step"] = "Initializing..."
    state["started_at"] = time.time()
    state["progress_percent"] = 0
    state["error"] = None
    state["logs"] = []
    
    # Copy config to project-specific tfvars
    service = get_service_for_project(project_name)
    service.copy_config_to_workspace(tfvars_file)
    
    # Log what we're deploying
    add_history_entry(f"Starting deployment: {deployment_type} (project: {project_name})", "info", project_name=project_name)
    
    # Start deployment in background thread
    thread = threading.Thread(target=run_deployment, args=(project_name,))
    thread.daemon = False
    thread.start()

    audit_service.write(
        _audit_actor(),
        "deploy.apply",
        project=project_name,
        details={"deployment_type": deployment_type},
    )

    return jsonify({
        "success": True,
        "message": f"Deployment started for project '{project_name}' ({deployment_type})",
        "project_name": project_name,
        "deployment_type": deployment_type
    })

@bp.route('/cancel', methods=['POST'])
def cancel_deployment():
    """Cancel an in-progress deployment by killing the Terraform subprocess.

    Per-project: must specify ``project_name`` in the JSON body OR
    ``?project=`` query param. Refuses without one — there's no single
    "active deployment" to cancel on a multi-project dashboard.
    """
    data = request.get_json() or {}
    project_name = (data.get("project_name") or request.args.get("project") or "").strip()

    if not project_name:
        return jsonify({"success": False, "error": "project_name required"}), 400

    state = get_project_state(project_name)
    if state["status"] != "running":
        return jsonify({"success": False, "error": "No active deployment to cancel"}), 400

    # Kill the Terraform subprocess
    service = get_service_for_project(project_name)
    killed = service.cancel()

    state["status"] = "error"
    state["error"] = "Deployment cancelled by user"
    state["completed_at"] = time.time()
    add_log("Deployment cancelled by user", "warning", project_name)
    _persist_state(project_name, state)

    return jsonify({
        "success": True,
        "message": f"Deployment cancelled for '{project_name}'",
        "killed_process": killed
    })

@bp.route('/destroy', methods=['POST'])
def destroy():
    """Destroy infrastructure for a specific project.

    Pre-destroy safety guard:
        Before kicking off the terraform destroy thread we list the
        workspace's state and check whether any "foreign" modules are
        present — modules that should NOT exist for the deployment_type
        declared in configs/<project>.tfvars. The classic example is
        ``module.dashboard_server`` accidentally pinned to a goad-mini
        workspace at provisioning time. Destroying that workspace would
        wipe the dashboard server out from under the operator.

        When foreign modules are present we refuse with HTTP 409 and a
        structured payload telling the UI to offer the "Detach" recovery
        action (preferred) or the explicit ``?force_foreign=1`` override.
        The override is audited so we can trace which operator pulled the
        ripcord and when.

        The check is intentionally cheap (one ``terraform state list``)
        and only blocks when state actually contains foreign modules —
        on an empty / clean workspace it's a no-op.
    """
    global deployment_state

    # Get request data
    data = request.get_json() or {}
    project_name = data.get("project_name")
    # URL flag override: only this exact form bypasses the safety check.
    # We do NOT honor a body field here — forcing the operator to type
    # `?force_foreign=1` into a URL is a deliberate friction step.
    force_foreign = request.args.get("force_foreign", "").strip() == "1"

    # ── 2026-05-28 SAFETY: hard-block real terraform-destroy on demo ────
    # Demo deployments are pure in-memory + synthetic — they MUST NOT
    # trigger a real `terraform destroy`. Without this guard the legacy
    # destroy path would (a) attempt to find a real workspace under
    # `terraform/` keyed off the project name, then (b) shell out to
    # `terraform destroy`. For project_name="demo" that targets nothing
    # real but for an operator-flagged demo deployment (`demo-<ts>`,
    # see Phase 4) it would attempt to destroy the dashboard's own
    # workspace by accident. Short-circuit by detecting the demo
    # marker BEFORE we touch terraform; emit an audit row + return
    # an immediate success envelope mirroring the real shape.
    try:
        from webapp.backend.services import demo_data_service
        _is_demo = demo_data_service.is_demo_project(project_name)
    except Exception:
        _is_demo = False
    if _is_demo:
        # Clear any in-memory state for the synthetic deployment.
        try:
            if project_name in deployment_states:
                deployment_states.pop(project_name, None)
        except Exception:
            pass
        # Clear the per-project on-disk state file if one was synthesised.
        try:
            state_path = STATE_DIR / f"{project_name}.state.json"
            if state_path.exists():
                state_path.unlink()
        except Exception:
            pass
        audit_service.write(_audit_actor(), "deploy.destroy_demo",
                            project=project_name, details={"is_demo": True})
        return jsonify({
            "success": True,
            "is_demo": True,
            "message": (f"Demo deployment '{project_name}' cleared from "
                        "memory. No AWS resources were touched."),
            "project_name": project_name,
            "status": "destroyed",
        })

    # Check if specific project is running
    if project_name and project_name in deployment_states:
        if deployment_states[project_name].get("status") == "running":
            return jsonify({
                "success": False,
                "error": f"Operation already in progress for project '{project_name}'"
            }), 400
    elif deployment_state["status"] == "running":
        return jsonify({
            "success": False,
            "error": "Operation already in progress"
        }), 400

    # Require confirmation
    if data.get("confirm") != "DESTROY":
        return jsonify({
            "success": False,
            "error": "Confirmation required. Send confirm: 'DESTROY'"
        }), 400

    # =====================================================================
    # SAFETY GUARD — refuse if foreign modules are in the workspace state
    # =====================================================================
    # 2026-05-22 — CRITICAL FIX after live-fire incident: previous logic
    # was fail-open. When `_summarize_state_for_safety` failed for any
    # reason (lock contention, terraform init in progress, transient AWS
    # API blip), `success=False` was returned and the guard SKIPPED
    # entirely, letting destroy proceed against state we couldn't read.
    # That's exactly what triggered the goad_mini dashboard_server tear-
    # down on 2026-05-22.
    #
    # New behaviour: fail-CLOSED. If the state probe didn't succeed AND
    # we can't prove the workspace is empty/never-deployed, refuse and
    # ask the operator to re-confirm via `?force_foreign=1`. Only the
    # explicit "draft workspace never applied" case (empty actual_modules
    # AND empty foreign list AND no error other than a workspace-not-found
    # signal) is allowed through.
    if project_name and not force_foreign:
        safe = _sanitize_project_name(project_name)
        if safe:
            summary = _summarize_state_for_safety(safe)
            foreign = summary.get("foreign_modules") or []
            success = bool(summary.get("success"))
            err = (summary.get("error") or "").strip().lower()
            actual = summary.get("actual_modules") or []
            # Empty-workspace fast-path: we successfully read state AND
            # state had zero modules → legitimate "destroy a draft that
            # never applied" path.
            empty_workspace_ok = success and not foreign and not actual
            # Indeterminate-state guard: we couldn't read state at all
            # (lock contention, init failure, etc). Refuse — operator
            # must force_foreign=1 to override after manual triage.
            if not success and not empty_workspace_ok:
                return jsonify({
                    "success": False,
                    "error": "state_indeterminate",
                    "message": (
                        f"Could not read terraform state for {safe!r} "
                        f"({err or 'unknown reason'}). Destroy refused — "
                        "the workspace may be locked or mid-init. Resolve "
                        "the lock and retry, or pass ?force_foreign=1 to "
                        "override after manual triage."
                    ),
                    "state_summary": summary,
                    "actions": [
                        {
                            "id": "force-anyway",
                            "label": "Override and destroy anyway (manual triage done)",
                            "endpoint": "/api/deploy/destroy?force_foreign=1",
                            "method": "POST",
                            "description": (
                                "Bypasses the state-summary guard. Only do this "
                                "after confirming the workspace lock is stale "
                                "AND that you've verified what's actually in state."
                            ),
                        },
                    ],
                }), 409
            if success and foreign:
                dtype = summary.get("deployment_type") or "unknown"
                foreign_list = ", ".join(foreign)
                return jsonify({
                    "success": False,
                    "error": "foreign_modules_in_state",
                    "message": (
                        f"This workspace contains modules that aren't part of the "
                        f"{dtype} deployment: {foreign_list}. Destroying would damage "
                        f"shared infrastructure."
                    ),
                    "deployment_type": dtype,
                    "foreign_modules": foreign,
                    "expected_modules": summary.get("expected_modules") or [],
                    "actual_modules": summary.get("actual_modules") or [],
                    "actions": [
                        {
                            "id": "detach-foreign",
                            "label": "Detach foreign modules from this workspace's state",
                            "endpoint": f"/api/deploy/detach-foreign/{safe}",
                            "method": "POST",
                            "description": (
                                "Removes the foreign modules from terraform's state "
                                "tracking for THIS workspace only. Does NOT touch AWS "
                                "— the dashboard server keeps running. After this, "
                                "Destroy is safe."
                            ),
                        },
                        {
                            "id": "force-anyway",
                            "label": "I understand — destroy everything in state including foreign modules",
                            "endpoint": "/api/deploy/destroy?force_foreign=1",
                            "method": "POST",
                            "description": (
                                "Last-resort escape hatch. Will destroy the foreign "
                                "modules too. Operator must explicitly opt in via "
                                "the URL flag."
                            ),
                        },
                    ],
                }), 409

    # Initialize state for this project
    if project_name:
        if project_name not in deployment_states:
            deployment_states[project_name] = create_empty_state()
        deployment_states[project_name]["status"] = "running"
        deployment_states[project_name]["step"] = "Destroying infrastructure..."
        deployment_states[project_name]["started_at"] = time.time()
        deployment_states[project_name]["completed_at"] = None
        deployment_states[project_name]["progress_percent"] = 0
        deployment_states[project_name]["logs"] = []  # Clear previous logs
        deployment_states[project_name]["purge_result"] = None

    # Log the start of destroy to history
    add_history_entry(f"Starting destroy for project: {project_name or 'default'}", "warning", project_name=project_name)

    # Start destroy in background thread
    thread = threading.Thread(target=run_destroy, args=(project_name,))
    thread.daemon = False
    thread.start()

    audit_service.write(_audit_actor(), "deploy.destroy", project=project_name)

    # If the operator force-bypassed the safety check, record that
    # separately so the override is independently auditable. We use a
    # distinct action name (``deploy.destroy.force_foreign``) so the
    # filter on the Activity page can surface these as a discrete event.
    if force_foreign and project_name:
        try:
            safe = _sanitize_project_name(project_name)
            details = {"force_foreign": True}
            if safe:
                # Best-effort: enrich the audit record with the foreign
                # list at decision time. Never raise from audit.
                summary = _summarize_state_for_safety(safe)
                if summary.get("success"):
                    details["foreign_modules"] = summary.get("foreign_modules") or []
            audit_service.write(
                _audit_actor(),
                "deploy.destroy.force_foreign",
                project=project_name,
                details=details,
            )
        except Exception:
            pass

    return jsonify({
        "success": True,
        "message": f"Destruction started" + (f" for project '{project_name}'" if project_name else ""),
        "project_name": project_name,
        "force_foreign": force_foreign,
    })


@bp.route('/state-summary/<project>', methods=['GET'])
def state_summary(project):
    """Return the expected vs actual top-level modules for a project.

    Cheap GET — runs a single ``terraform state list`` against the
    project's workspace and computes the foreign-module delta using the
    same helper the destroy guard uses. Surfaced by the Manage UI
    pre-destroy warning banner (Component 3).

    Response::

        {
          "success": true,
          "project": "<sanitized>",
          "deployment_type": "<type or ''>",
          "expected_modules": [str, ...],
          "actual_modules":   [str, ...],
          "foreign_modules":  [str, ...],
          "enable_test_lab":  bool
        }

    Sanitization mirrors every other per-project endpoint — a malformed
    name returns ``success: false`` rather than scanning a fallback
    workspace (which would be misleading for the UI).
    """
    safe = _sanitize_project_name(project)
    if not safe:
        return jsonify({
            "success": False,
            "error": "invalid_project_name",
            "project": project,
        }), 400

    summary = _summarize_state_for_safety(safe)

    return jsonify({
        "success": bool(summary.get("success")),
        "project": safe,
        "deployment_type": summary.get("deployment_type") or "",
        "enable_test_lab": bool(summary.get("enable_test_lab")),
        "expected_modules": summary.get("expected_modules") or [],
        "actual_modules": summary.get("actual_modules") or [],
        "foreign_modules": summary.get("foreign_modules") or [],
        "error": summary.get("error"),
    })


@bp.route('/detach-foreign/<project>', methods=['POST'])
def detach_foreign(project):
    """Remove foreign modules from a project's terraform state.

    Computes the same foreign-modules set as the destroy guard, then runs
    ``terraform state rm module.<name>`` for each one. ``state rm`` does
    NOT touch the underlying AWS resource — it only stops the workspace
    from tracking it. This is the safe recovery path for the
    "dashboard_server pinned to goad-mini" class of bug.

    Audits each successful detachment + the operator who triggered it.
    Returns the list of modules actually detached so the UI can confirm.
    """
    safe = _sanitize_project_name(project)
    if not safe:
        return jsonify({
            "success": False,
            "error": "invalid_project_name",
            "project": project,
        }), 400

    summary = _summarize_state_for_safety(safe)
    if not summary.get("success"):
        return jsonify({
            "success": False,
            "error": summary.get("error") or "state_list_failed",
            "stderr": summary.get("state_list_stderr", ""),
            "project": safe,
        }), 500

    foreign = summary.get("foreign_modules") or []
    if not foreign:
        return jsonify({
            "success": True,
            "project": safe,
            "detached": [],
            "message": "No foreign modules to detach — state is already clean.",
        })

    service = get_service_for_project(safe)
    detached = []
    errors = []
    for name in foreign:
        addr = f"module.{name}"
        result = service.state_rm(addr)
        if result.get("success"):
            detached.append(name)
            audit_service.write(
                _audit_actor(),
                "deploy.detach_foreign",
                project=safe,
                details={"address": addr},
            )
        else:
            errors.append({
                "module": name,
                "stderr": result.get("stderr", ""),
            })

    success = len(errors) == 0
    msg = (
        f"Detached {len(detached)} foreign module(s) from workspace '{safe}'."
        if success
        else f"Detached {len(detached)} of {len(foreign)} foreign module(s); "
             f"{len(errors)} failed — see errors."
    )

    return jsonify({
        "success": success,
        "project": safe,
        "detached": detached,
        "errors": errors,
        "message": msg,
    }), (200 if success else 207)

@bp.route('/purge', methods=['POST'])
def purge_resources():
    """
    Force purge all resources from a failed deployment.
    This runs terraform destroy with -refresh=false to clean up orphaned resources.
    """
    global deployment_state

    # Get request data
    data = request.get_json() or {}
    project_name = data.get("project_name")
    force_foreign = request.args.get("force_foreign", "").strip() == "1"

    # ── 2026-05-28 SAFETY: demo deployments must NEVER hit terraform. ────
    # Mirrors the destroy guard. Purge does the same dangerous shellout
    # so it gets the same short-circuit.
    try:
        from webapp.backend.services import demo_data_service
        _is_demo = demo_data_service.is_demo_project(project_name)
    except Exception:
        _is_demo = False
    if _is_demo:
        try:
            if project_name in deployment_states:
                deployment_states.pop(project_name, None)
            state_path = STATE_DIR / f"{project_name}.state.json"
            if state_path.exists():
                state_path.unlink()
        except Exception:
            pass
        audit_service.write(_audit_actor(), "deploy.purge_demo",
                            project=project_name, details={"is_demo": True})
        return jsonify({
            "success": True,
            "is_demo": True,
            "message": (f"Demo deployment '{project_name}' cleared. "
                        "No AWS resources were touched."),
            "project_name": project_name,
        })

    # Check if specific project is running
    if project_name and project_name in deployment_states:
        if deployment_states[project_name].get("status") == "running":
            return jsonify({
                "success": False,
                "error": f"Operation already in progress for project '{project_name}'"
            }), 400
    elif deployment_state["status"] == "running":
        return jsonify({
            "success": False,
            "error": "Operation already in progress"
        }), 400

    # Require confirmation
    if data.get("confirm") != "PURGE":
        return jsonify({
            "success": False,
            "error": "Confirmation required. Send confirm: 'PURGE'"
        }), 400

    # ── 2026-05-28 CRITICAL #4: foreign-modules safety guard. ───────────
    # /api/deploy/destroy has this guard (line ~2275). /api/deploy/purge
    # didn't — same teardown risk via a different button. Mirror the
    # exact fail-closed check here so an operator clicking "Force Purge"
    # on a workspace contaminated with foreign modules (e.g. an
    # accidentally-pinned dashboard_server module) gets the same refusal
    # + Detach action they'd get on Destroy.
    if project_name and not force_foreign:
        safe = _sanitize_project_name(project_name)
        if safe:
            summary = _summarize_state_for_safety(safe)
            foreign = summary.get("foreign_modules") or []
            success_probe = bool(summary.get("success"))
            err = (summary.get("error") or "").strip().lower()
            actual = summary.get("actual_modules") or []
            empty_workspace_ok = success_probe and not foreign and not actual
            if not success_probe and not empty_workspace_ok:
                return jsonify({
                    "success": False,
                    "error": "state_indeterminate",
                    "message": (
                        f"Could not read terraform state for {safe!r} "
                        f"({err or 'unknown reason'}). Purge refused — the "
                        "workspace may be locked or mid-init. Resolve the "
                        "lock and retry, or pass ?force_foreign=1 to "
                        "override after manual triage."
                    ),
                    "state_summary": summary,
                    "actions": [{
                        "id": "force-anyway",
                        "label": "Override and purge anyway (manual triage done)",
                        "endpoint": "/api/deploy/purge?force_foreign=1",
                        "method": "POST",
                        "description": (
                            "Bypasses the state-summary guard. Only do "
                            "this after verifying the lock is stale AND "
                            "you've reviewed what's in state."
                        ),
                    }],
                }), 409
            if success_probe and foreign:
                dtype = summary.get("deployment_type") or "unknown"
                foreign_list = ", ".join(foreign)
                return jsonify({
                    "success": False,
                    "error": "foreign_modules_in_state",
                    "message": (
                        f"This workspace contains modules that aren't "
                        f"part of the {dtype} deployment: {foreign_list}. "
                        "Purging would damage shared infrastructure."
                    ),
                    "deployment_type": dtype,
                    "foreign_modules": foreign,
                    "expected_modules": summary.get("expected_modules") or [],
                    "actual_modules": summary.get("actual_modules") or [],
                    "actions": [
                        {
                            "id": "detach-foreign",
                            "label": "Detach foreign modules from this workspace's state",
                            "endpoint": f"/api/deploy/detach-foreign/{safe}",
                            "method": "POST",
                            "description": (
                                "Removes the foreign modules from terraform's "
                                "state tracking for THIS workspace only. "
                                "Does NOT touch AWS. After this, Purge is safe."
                            ),
                        },
                        {
                            "id": "force-anyway",
                            "label": "I understand — purge everything including foreign modules",
                            "endpoint": "/api/deploy/purge?force_foreign=1",
                            "method": "POST",
                            "description": (
                                "Last-resort escape hatch. Will purge the "
                                "foreign modules too. Explicit opt-in via URL flag."
                            ),
                        },
                    ],
                }), 409
    
    # Initialize state for this project
    if project_name:
        if project_name not in deployment_states:
            deployment_states[project_name] = create_empty_state()
        state = deployment_states[project_name]
    else:
        state = deployment_state
    
    # Set initial state before starting thread
    state["status"] = "running"
    state["step"] = "Purging resources..."
    state["started_at"] = time.time()
    state["completed_at"] = None
    state["progress_percent"] = 0
    state["error"] = None
    state["logs"] = []
    state["purge_result"] = None

    # Log the start of purge to history (like deployment does)
    add_history_entry(f"Starting purge/destroy for project: {project_name or 'default'}", "warning", project_name=project_name)
    
    # Start purge in background thread
    thread = threading.Thread(target=run_purge, args=(project_name,))
    thread.daemon = False
    thread.start()
    
    return jsonify({
        "success": True,
        "message": "Purge started - cleaning up all resources" + (f" for project '{project_name}'" if project_name else ""),
        "project_name": project_name
    })

def run_purge(project_name: str = None):
    """Run purge in background thread - force destroy all resources.
    Tracks before/after resource counts and parses terraform output for detailed reporting."""
    global deployment_state

    # Use project-specific state if provided
    if project_name and project_name in deployment_states:
        state = deployment_states[project_name]
        service = get_service_for_project(project_name)
    else:
        state = deployment_state
        service = terraform_service

    try:
        add_log("Starting resource purge...", "warning", project_name)

        # Count resources before purge
        resources_before = {'count': 0, 'by_service': {}, 'resources': []}
        if project_name:
            state["step"] = "Counting existing resources..."
            add_log("Querying AWS for tagged resources before purge...", "info", project_name)
            resources_before = query_remaining_resources(project_name)
            if resources_before['count'] > 0:
                breakdown = ", ".join(f"{c} {s}" for s, c in sorted(
                    resources_before['by_service'].items(), key=lambda x: -x[1]))
                add_log(f"Found {resources_before['count']} tagged resources: {breakdown}", "info", project_name)
            elif resources_before['count'] == 0:
                add_log("No tagged AWS resources found (Terraform state may still have resources)", "info", project_name)

        # Refresh state
        state["step"] = "Refreshing Terraform state..."
        add_log("Refreshing Terraform state to detect existing resources...", "info", project_name)
        refresh_result = service.refresh()
        if refresh_result.get("success"):
            add_log("State refreshed successfully", "success", project_name)
        else:
            add_log("State refresh had issues, continuing with destroy...", "warning", project_name)

        # Run destroy
        state["step"] = "Destroying all resources..."
        state["progress_percent"] = 30
        add_log("Running terraform destroy to remove all resources...", "info", project_name)

        result = service.destroy()
        destroy_parsed = parse_terraform_destroy_output(
            result.get("stdout", ""), result.get("stderr", ""))

        if result["success"]:
            for d in destroy_parsed['destroyed']:
                add_log(f"Destroyed: {d['address']} ({d['duration']})", "success", project_name)

            state["status"] = "success"
            state["step"] = "Terraform destroy complete, verifying cleanup..."
            state["progress_percent"] = 85
            add_log(f"Terraform destroy completed: {destroy_parsed['destroyed_count']} resources destroyed. Verifying...", "success", project_name)

            if project_name and service.workspace_name != "default":
                add_log(f"Cleaning up workspace '{service.workspace_name}'...", "info", project_name)
        else:
            first_error = result.get("stderr", "Unknown error")
            add_log(f"Standard destroy failed: {first_error[:500]}", "error", project_name)

            # Force destroy fallback
            add_log("Trying force destroy with -refresh=false...", "warning", project_name)
            state["step"] = "Force destroying resources..."
            state["progress_percent"] = 60

            result = service.force_destroy()
            force_parsed = parse_terraform_destroy_output(
                result.get("stdout", ""), result.get("stderr", ""))

            # Merge parsed results
            destroy_parsed['destroyed'].extend(force_parsed['destroyed'])
            destroy_parsed['destroyed_count'] += force_parsed['destroyed_count']
            destroy_parsed['errors'].extend(force_parsed['errors'])
            destroy_parsed['error_count'] += force_parsed['error_count']

            if result["success"]:
                for d in force_parsed['destroyed']:
                    add_log(f"Force-destroyed: {d['address']} ({d['duration']})", "success", project_name)
                state["status"] = "success"
                state["step"] = "Force destroy complete, verifying cleanup..."
                state["progress_percent"] = 85
                add_log(f"Force destroy completed: {force_parsed['destroyed_count']} additional resources destroyed. Verifying...", "success", project_name)
            else:
                state["status"] = "error"
                error_msg = result.get("stderr", "Purge failed")
                state["error"] = error_msg
                add_log(f"Purge failed: {error_msg[:1000]}", "error", project_name)

        # Query remaining resources after purge
        state["progress_percent"] = 90
        resources_after = {'count': 0, 'by_service': {}, 'resources': []}
        purge_filtered = 0
        if project_name:
            state["step"] = "Verifying cleanup..."
            add_log("Querying AWS for remaining resources...", "info", project_name)
            resources_after = query_remaining_resources(project_name)
            purge_filtered = resources_after.get('filtered_dead', 0)
            if purge_filtered > 0:
                add_log(f"Filtered {purge_filtered} terminated/deleted resources (AWS retains tags temporarily)", "info", project_name)
            if resources_after['count'] > 0:
                breakdown = ", ".join(f"{c} {s}" for s, c in sorted(
                    resources_after['by_service'].items(), key=lambda x: -x[1]))
                add_log(f"WARNING: {resources_after['count']} live resources still remain: {breakdown}", "warning", project_name)
            elif resources_after['count'] == 0:
                add_log("Verification complete: no live resources remain in AWS", "success", project_name)

        # Store structured purge result
        state["purge_result"] = {
            "resources_before": resources_before.get('count', 0),
            "resources_after": resources_after.get('count', 0),
            "resources_after_by_service": resources_after.get('by_service', {}),
            "resources_after_list": resources_after.get('resources', []),
            "terraform_destroyed": destroy_parsed['destroyed'],
            "terraform_destroyed_count": destroy_parsed['destroyed_count'],
            "terraform_errors": destroy_parsed['errors'],
            "terraform_error_count": destroy_parsed['error_count'],
            "still_destroying": destroy_parsed.get('still_destroying', []),
            "filtered_dead": purge_filtered,
        }

        state["progress_percent"] = 95
        state["step"] = "Resources purged"

        # Workspace cleanup
        if state["status"] == "success" and service.workspace_name != "default":
            try:
                ws_result = service.workspace_delete(service.workspace_name)
                if ws_result.get("success"):
                    add_log(f"Workspace '{service.workspace_name}' cleaned up", "info", project_name)
                    if service.tfvars_file.exists():
                        service.tfvars_file.unlink()
            except Exception as ws_err:
                add_log(f"Workspace cleanup warning: {ws_err}", "warning", project_name)

        state["progress_percent"] = 100
        state["completed_at"] = time.time()

    except Exception as e:
        state["status"] = "error"
        state["error"] = str(e)
        state["completed_at"] = time.time()
        add_log(f"Purge error: {str(e)}", "error", project_name)

@bp.route('/plan', methods=['GET'])
def plan():
    """Run Terraform plan with improved error handling"""
    try:
        # Check if terraform is installed
        import shutil
        if not shutil.which('terraform'):
            return jsonify({
                "success": False,
                "error": "Terraform CLI not found. Please install Terraform first.",
                "error_type": "terraform_not_installed",
                "help": "Please install Terraform CLI. Run: brew install terraform (macOS) or visit https://terraform.io/downloads",
                "stdout": "",
                "stderr": "Terraform CLI is not installed on this system.\n\nTo install:\n  macOS: brew install terraform\n  Linux: See https://terraform.io/downloads\n  Windows: choco install terraform"
            })
        
        # Check if tfvars file exists (use canonical path — the global
        # terraform_service.tfvars_file may have been mutated by workspace_select)
        global_tfvars = project_root / "configs" / "terraform.tfvars"

        # Per-project tfvars resolution. The Deploy sub-pill's Plan button
        # passes ?project=<name>; we point terraform_service at that
        # project's tfvars (and workspace) instead of the stale global one.
        # Sentinels (__draft__/__all__) fall through to global so a missing
        # file produces the right "configure first" error below.
        project_param = request.args.get("project")
        tfvars_file, resolved_workspace = _resolve_project_tfvars(project_param, global_tfvars)

        if not tfvars_file.exists():
            return jsonify({
                "success": False,
                "error": "Configuration file not found",
                "error_type": "config_missing",
                "help": "Please save your configuration in the Configuration tab before running plan.",
                "stdout": "",
                "stderr": f"Configuration file not found at:\n{tfvars_file}\n\nPlease go to the Configuration tab and save your settings first."
            })

        # Retarget the global service at the resolved project's workspace
        # and tfvars file. Without this, plan would either pick up the
        # legacy global tfvars (wrong config) or fail with "tfvars file
        # not found" against the previous workspace's path.
        terraform_service.workspace_name = resolved_workspace
        terraform_service.tfvars_file = tfvars_file

        # Check if terraform is initialized
        terraform_dir = terraform_service.terraform_dir
        if not (terraform_dir / ".terraform").exists():
            # Auto-initialize terraform
            add_history_entry("Auto-initializing Terraform...", "info", entry_type='plan')
            init_result = terraform_service.init()
            if not init_result.get("success"):
                init_error = init_result.get("stderr", "") or init_result.get("stdout", "") or "Unknown initialization error"
                return jsonify({
                    "success": False,
                    "error": "Terraform initialization failed",
                    "error_type": "init_failed",
                    "help": "Terraform failed to initialize. This usually means network issues or missing AWS credentials.",
                    "stdout": init_result.get("stdout", ""),
                    "stderr": f"Terraform Init Failed:\n\n{init_error}"
                })

        # Ensure we're on the resolved workspace for plan preview. When
        # ?project= is set this is the per-project workspace; otherwise
        # it falls through to "default" so legacy behavior is preserved.
        terraform_service.workspace_select(resolved_workspace)
        # workspace_select mutates tfvars_file based on the workspace name —
        # re-pin it to the resolved tfvars so the in-place per-project file
        # (written by Configure V2) wins over any workspace-derived path.
        terraform_service.tfvars_file = tfvars_file

        # Run the plan
        add_history_entry("Running Terraform plan...", "info", entry_type='plan')
        result = terraform_service.plan()
        
        # Get combined output
        full_output = result.get("full_output", "") or result.get("stdout", "") or result.get("stderr", "")
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        
        if result["success"]:
            add_history_entry("Terraform plan completed successfully", "success", entry_type='plan')
            audit_service.write(_audit_actor(), "deploy.plan")
            return jsonify({
                "success": True,
                "exit_code": result.get("exit_code"),
                "stdout": full_output or "Plan completed. No output captured.",
                "stderr": stderr,
                "plan": result.get("plan", {}),
                "message": "Plan completed successfully"
            })
        else:
            # Combine all output for error analysis
            all_output = f"{stdout}\n{stderr}".strip()
            
            # Parse common error patterns from combined output
            error_type = "unknown"
            help_text = "Check the error output below for details."
            
            # Check both stdout and stderr for error patterns
            if "No valid credential sources found" in all_output or "NoCredentialProviders" in all_output:
                error_type = "aws_credentials"
                help_text = "AWS credentials not configured. Run 'aws configure' in your terminal to set up credentials."
            elif "could not find credentials" in all_output.lower() or "no credentials" in all_output.lower():
                error_type = "aws_credentials"
                help_text = "AWS credentials not found. Run 'aws configure' to set up your AWS access keys."
            elif "ExpiredToken" in all_output or "ExpiredTokenException" in all_output or "token has expired" in all_output.lower() or "credentials have expired" in all_output.lower() or "security token expired" in all_output.lower():
                error_type = "aws_credentials"
                help_text = "Your AWS credentials have expired. Please refresh your credentials."
            elif "AccessDenied" in all_output or "UnauthorizedAccess" in all_output or "not authorized" in all_output.lower():
                error_type = "aws_permissions"
                help_text = "Your AWS credentials don't have sufficient permissions. Check your IAM policies."
            elif "Invalid provider configuration" in all_output:
                error_type = "provider_config"
                help_text = "Invalid Terraform provider configuration. Check your AWS region setting."
            elif "Error acquiring the state lock" in all_output:
                error_type = "state_lock"
                help_text = "Terraform state is locked. Another operation may be in progress. Wait and try again."
            elif "timeout" in all_output.lower():
                error_type = "timeout"
                help_text = "The operation timed out. Check your network connection."
            elif "Error:" in all_output:
                # Generic error - try to extract the error message
                error_type = "terraform_error"
                help_text = "Terraform encountered an error. See the details below."
            
            # Create a helpful error message
            error_display = all_output if all_output else "No error details available. Exit code: " + str(result.get("exit_code", "unknown"))
            
            add_history_entry(f"Terraform plan failed: {error_type}", "error", entry_type='plan')
            
            return jsonify({
                "success": False,
                "exit_code": result.get("exit_code"),
                "error": help_text,
                "error_type": error_type,
                "stdout": stdout,
                "stderr": error_display,
                "help": help_text
            })
            
    except Exception as e:
        error_msg = str(e)
        error_type = "unknown"
        help_text = "An unexpected error occurred."
        detailed_error = error_msg
        
        if "No such file or directory: 'terraform'" in error_msg:
            error_type = "terraform_not_installed"
            help_text = "Terraform CLI is not installed. Please install it first."
            detailed_error = "Terraform CLI is not installed on this system.\n\nTo install:\n  macOS: brew install terraform\n  Linux: See https://terraform.io/downloads"
        
        add_history_entry(f"Plan error: {error_msg}", "error", entry_type='plan')
        
        return jsonify({
            "success": False,
            "error": help_text,
            "error_type": error_type,
            "help": help_text,
            "stdout": "",
            "stderr": detailed_error
        }), 500

# /init removed 2026-05-21 — no frontend or script caller; terraform init
# is run inline by the deployment pipeline (run_deployment) and the
# /plan handler. A standalone init endpoint was a duplicate code path.

@bp.route('/upload-cobalt-strike', methods=['POST'])
def upload_cobalt_strike():
    """Upload Cobalt Strike archive file"""
    try:
        if 'file' not in request.files:
            return jsonify({"success": False, "error": "No file provided"}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({"success": False, "error": "No file selected"}), 400
        
        if not allowed_file(file.filename):
            return jsonify({
                "success": False,
                "error": f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            }), 400
        
        # Check file size
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > MAX_FILE_SIZE:
            return jsonify({
                "success": False,
                "error": f"File too large. Maximum size: {MAX_FILE_SIZE / (1024*1024)}MB"
            }), 400
        
        # Secure filename
        filename = secure_filename(file.filename)
        filepath = UPLOAD_FOLDER / filename
        
        # Save file
        file.save(str(filepath))
        
        # Get file info
        file_info = get_file_info(filepath)
        
        return jsonify({
            "success": True,
            "message": "File uploaded successfully",
            "file": file_info
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/cobalt-strike-file', methods=['GET'])
def get_cobalt_strike_file():
    """Get information about uploaded Cobalt Strike file"""
    try:
        # Look for Cobalt Strike files in upload directory
        files = list(UPLOAD_FOLDER.glob("*"))
        cobalt_strike_files = [
            get_file_info(f) for f in files 
            if f.is_file() and allowed_file(f.name)
        ]
        
        # Sort: files with "cobaltstrike" or "cobalt" in the name first,
        # then by modified time (newest first) within each group
        def _cs_sort_key(f):
            name_lower = (f.get('filename') or '').lower().replace('-', '').replace('_', '')
            is_cs = 'cobaltstrike' in name_lower or 'cobalt' in name_lower
            return (not is_cs, -(f.get('modified') or 0))

        cobalt_strike_files.sort(key=_cs_sort_key)

        return jsonify({
            "success": True,
            "files": cobalt_strike_files,
            "has_file": len(cobalt_strike_files) > 0,
            "latest_file": cobalt_strike_files[0] if cobalt_strike_files else None
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/cobalt-strike-file', methods=['DELETE'])
def delete_cobalt_strike_file():
    """Delete uploaded Cobalt Strike file"""
    try:
        data = request.get_json() or {}
        filename = data.get('filename')
        
        if filename and filename != 'latest':
            # Delete specific file
            filepath = UPLOAD_FOLDER / secure_filename(filename)
        else:
            # Delete latest file (most recent)
            files = list(UPLOAD_FOLDER.glob("*"))
            cobalt_strike_files = [
                f for f in files 
                if f.is_file() and allowed_file(f.name)
            ]
            
            if not cobalt_strike_files:
                return jsonify({"success": False, "error": "No files found"}), 404
            
            # Get most recent file
            filepath = max(cobalt_strike_files, key=lambda f: f.stat().st_mtime)
        
        if not filepath.exists():
            return jsonify({"success": False, "error": "File not found"}), 404
        
        if not filepath.is_file():
            return jsonify({"success": False, "error": "Not a file"}), 400
        
        filepath.unlink()
        
        return jsonify({
            "success": True,
            "message": "File deleted successfully"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# =============================================================================
# COBALT STRIKE CLIENT UPLOAD (for Attack Box)
# =============================================================================
# These endpoints manage the CS Client archive that gets deployed to the
# Windows Attack Box. This is separate from the Team Server archive.
# =============================================================================

@bp.route('/upload-cs-client', methods=['POST'])
def upload_cs_client():
    """Upload Cobalt Strike Client archive file for Attack Box"""
    try:
        if 'file' not in request.files:
            return jsonify({"success": False, "error": "No file provided"}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({"success": False, "error": "No file selected"}), 400
        
        if not allowed_file(file.filename):
            return jsonify({
                "success": False,
                "error": f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            }), 400
        
        # Check file size
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > MAX_FILE_SIZE:
            return jsonify({
                "success": False,
                "error": f"File too large. Maximum size: {MAX_FILE_SIZE / (1024*1024)}MB"
            }), 400
        
        # Secure filename
        filename = secure_filename(file.filename)
        filepath = CS_CLIENT_FOLDER / filename
        
        # Save file
        file.save(str(filepath))
        
        # Get file info
        file_info = get_file_info(filepath)
        
        return jsonify({
            "success": True,
            "message": "CS Client file uploaded successfully",
            "file": file_info
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/cs-client-file', methods=['GET'])
def get_cs_client_file():
    """Get information about uploaded CS Client file"""
    try:
        # Look for CS Client files in uploads_client/
        files = list(CS_CLIENT_FOLDER.glob("*"))
        cs_client_files = [
            get_file_info(f) for f in files
            if f.is_file() and allowed_file(f.name)
        ]

        # Also check for a CS distribution directory in uploads/
        # (will be auto-zipped at deploy time)
        auto_detected_dir = None
        if not cs_client_files:
            for d in UPLOAD_FOLDER.iterdir():
                if d.is_dir() and any((d / f).exists() for f in ["cobaltstrike.jar", "update.jar", "update.bat"]):
                    auto_detected_dir = d.name
                    cs_client_files.append({
                        "name": f"{d.name}/ (auto-detected)",
                        "size": sum(f.stat().st_size for f in d.rglob("*") if f.is_file()),
                        "modified": d.stat().st_mtime,
                        "source": "auto-detected directory"
                    })
                    break

        # Sort by modified time (newest first)
        cs_client_files.sort(key=lambda x: x['modified'] if x else 0, reverse=True)

        return jsonify({
            "success": True,
            "files": cs_client_files,
            "has_file": len(cs_client_files) > 0,
            "latest_file": cs_client_files[0] if cs_client_files else None,
            "auto_detected_dir": auto_detected_dir
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/cs-client-file', methods=['DELETE'])
def delete_cs_client_file():
    """Delete uploaded CS Client file"""
    try:
        data = request.get_json() or {}
        filename = data.get('filename')
        
        if filename and filename != 'latest':
            # Delete specific file
            filepath = CS_CLIENT_FOLDER / secure_filename(filename)
        else:
            # Delete latest file (most recent)
            files = list(CS_CLIENT_FOLDER.glob("*"))
            cs_client_files = [
                f for f in files 
                if f.is_file() and allowed_file(f.name)
            ]
            
            if not cs_client_files:
                return jsonify({"success": False, "error": "No files found"}), 404
            
            # Get most recent file
            filepath = max(cs_client_files, key=lambda f: f.stat().st_mtime)
        
        if not filepath.exists():
            return jsonify({"success": False, "error": "File not found"}), 404
        
        if not filepath.is_file():
            return jsonify({"success": False, "error": "Not a file"}), 400
        
        filepath.unlink()
        
        return jsonify({
            "success": True,
            "message": "CS Client file deleted successfully"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# =============================================================================
# SSH PUBLIC KEY MANAGEMENT
# =============================================================================
# These endpoints manage the user's SSH public key for secure lab access.
# The public key is stored locally and passed to Terraform during deployment.
# Private keys are NEVER handled by this application - they stay on the user's machine.
# =============================================================================

# SSH key storage file
SSH_KEY_FILE = Path(__file__).parent.parent / "data" / "ssh_public_key.txt"

def validate_ssh_public_key(key: str) -> dict:
    """
    Validate an SSH public key format.
    Returns dict with 'valid', 'key_type', 'fingerprint', and 'comment' fields.
    """
    import re
    import hashlib
    import base64
    
    key = key.strip()
    
    # Supported key types
    valid_types = [
        'ssh-ed25519',
        'ssh-rsa', 
        'ecdsa-sha2-nistp256',
        'ecdsa-sha2-nistp384',
        'ecdsa-sha2-nistp521'
    ]
    
    # Basic format check: type base64-data [comment]
    pattern = r'^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp\d+)\s+([A-Za-z0-9+/=]+)(\s+.*)?$'
    match = re.match(pattern, key)
    
    if not match:
        return {
            'valid': False,
            'error': 'Invalid SSH public key format. Expected: ssh-ed25519 AAAA... or ssh-rsa AAAA...'
        }
    
    key_type = match.group(1)
    key_data = match.group(2)
    comment = match.group(3).strip() if match.group(3) else ''
    
    # Validate base64 encoding
    try:
        decoded = base64.b64decode(key_data)
        # Calculate fingerprint (SHA256)
        fingerprint = hashlib.sha256(decoded).digest()
        fingerprint_b64 = base64.b64encode(fingerprint).decode('utf-8').rstrip('=')
        fingerprint_str = f"SHA256:{fingerprint_b64}"
    except Exception:
        return {
            'valid': False,
            'error': 'Invalid base64 encoding in key data'
        }
    
    # Check minimum key length
    if key_type == 'ssh-rsa' and len(decoded) < 256:
        return {
            'valid': False,
            'error': 'RSA key is too short. Use at least 2048 bits (preferably 4096)'
        }
    
    return {
        'valid': True,
        'key_type': key_type,
        'fingerprint': fingerprint_str,
        'comment': comment,
        'key_preview': f"{key_type} {key_data[:20]}...{key_data[-10:]}" if len(key_data) > 30 else key
    }


@bp.route('/ssh-public-key', methods=['GET'])
def get_ssh_public_key():
    """Get the stored SSH public key"""
    try:
        # Ensure data directory exists
        SSH_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        if not SSH_KEY_FILE.exists():
            return jsonify({
                "success": True,
                "has_key": False,
                "message": "No SSH public key configured"
            })
        
        key_content = SSH_KEY_FILE.read_text().strip()
        
        if not key_content:
            return jsonify({
                "success": True,
                "has_key": False,
                "message": "SSH public key file is empty"
            })
        
        # Validate and get key info
        validation = validate_ssh_public_key(key_content)
        
        if not validation['valid']:
            return jsonify({
                "success": True,
                "has_key": True,
                "valid": False,
                "error": validation['error'],
                "key_preview": key_content[:50] + "..." if len(key_content) > 50 else key_content
            })
        
        return jsonify({
            "success": True,
            "has_key": True,
            "valid": True,
            "key_type": validation['key_type'],
            "fingerprint": validation['fingerprint'],
            "comment": validation['comment'],
            "key_preview": validation['key_preview']
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/ssh-public-key', methods=['POST'])
def save_ssh_public_key():
    """Save the user's SSH public key"""
    try:
        data = request.get_json() or {}
        public_key = data.get('public_key', '').strip()
        
        if not public_key:
            return jsonify({
                "success": False,
                "error": "No public key provided"
            }), 400
        
        # Validate the key
        validation = validate_ssh_public_key(public_key)
        
        if not validation['valid']:
            return jsonify({
                "success": False,
                "error": validation['error']
            }), 400
        
        # Warn if using RSA (recommend Ed25519)
        warning = None
        if validation['key_type'] == 'ssh-rsa':
            warning = "Consider using Ed25519 keys for better security and performance: ssh-keygen -t ed25519"
        
        # Ensure data directory exists
        SSH_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # Save the key
        SSH_KEY_FILE.write_text(public_key + '\n')
        
        return jsonify({
            "success": True,
            "message": "SSH public key saved successfully",
            "key_type": validation['key_type'],
            "fingerprint": validation['fingerprint'],
            "comment": validation['comment'],
            "key_preview": validation['key_preview'],
            "warning": warning
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/ssh-public-key', methods=['DELETE'])
def delete_ssh_public_key():
    """Delete the stored SSH public key"""
    try:
        if SSH_KEY_FILE.exists():
            SSH_KEY_FILE.unlink()
        
        return jsonify({
            "success": True,
            "message": "SSH public key deleted successfully"
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def get_user_public_key() -> str:
    """
    Get the user's SSH public key for Terraform.
    Returns the key content or raises an exception if not configured.
    """
    if not SSH_KEY_FILE.exists():
        raise ValueError("SSH public key not configured. Please add your public key in the Deploy tab.")
    
    key_content = SSH_KEY_FILE.read_text().strip()
    
    if not key_content:
        raise ValueError("SSH public key file is empty. Please add your public key in the Deploy tab.")
    
    validation = validate_ssh_public_key(key_content)
    
    if not validation['valid']:
        raise ValueError(f"Invalid SSH public key: {validation['error']}")
    
    return key_content


# =============================================================================
# REMOVED 2026-05-21 — /connection-info, /connection-info/quick, /ssh-fingerprints
# =============================================================================
# These Phase-4 endpoints had no frontend or script callers. The Manage
# sub-pill renders connection info from /api/deploy/infrastructure +
# /api/deploy/outputs (which are project-aware). The fingerprint info was
# never surfaced — SSH-host-key trust uses TOFU on first connect from
# the operator's terminal, not a UI display. Keeping them around added
# 350+ lines of unmaintained code reading global terraform_service state.
# =============================================================================
# (legacy handler bodies deleted in full — see banner above)


# =============================================================================
# DEPRECATED: SSH PRIVATE KEY ENDPOINTS
# =============================================================================
# These endpoints are DEPRECATED and will be removed in a future version.
# Private keys are now generated on hosts and never transmitted.
# Users should use their own SSH key that they uploaded before deployment.
# =============================================================================

@bp.route('/infrastructure', methods=['GET'])
def get_infrastructure():
    """Get current infrastructure state and outputs from Terraform.

    Query params:
        project: project name (optional). If not provided, auto-detects
                 the active project from deployment states or workspaces.
    """
    try:
        project_name = request.args.get('project')

        # 2026-05-22 — demo deployment bypasses the terraform shell-out path
        # which costs ~4.6 seconds per call. Returns the same shape with
        # synthetic outputs so the Manage pane populates instantly.
        from webapp.backend.services import demo_data_service
        if demo_data_service.is_demo_project(project_name):
            state = demo_data_service.deployment_state()
            o = state.get("outputs", {})
            return jsonify({
                "success": True,
                "has_deployment": True,
                "is_demo": True,
                "deployment_mode": "single",
                "project_name": project_name,
                "account_id": "0123456789ab",
                "ansible_inventory": {},
                "attack_box": {"enabled": False},
                "jump_host": "203.0.113.10",
                "c2_servers": {"private_ips": o.get("c2_team_server_private_ips", [])},
                "redirectors": {"public_ips": [o.get("redirector_public_ip")] if o.get("redirector_public_ip") else []},
                "network": {"vpc_id": "vpc-0demo01"},
                "security_groups": {"c2": "sg-0democ2"},
                "summary": {
                    "c2_server_count": 1,
                    "redirector_count": 1,
                    "has_jump_host": True,
                    "has_attack_box": False,
                },
            })

        # Auto-detect active project if not specified
        if not project_name:
            # Active deployment statuses (not destroyed/error)
            active_statuses = ("success", "running", "idle", "complete")

            # 1. Check in-memory deployment_states for an active deployment
            for name, state in deployment_states.items():
                if state.get("status") in active_statuses:
                    project_name = name
                    break

            # 2. If nothing in memory, scan persisted state files on disk
            #    (handles server restart where deployment_states is empty)
            if not project_name and STATE_DIR.exists():
                for state_file in sorted(STATE_DIR.glob("*.state.json"), key=lambda p: p.stat().st_mtime, reverse=True):
                    try:
                        with open(state_file, 'r') as f:
                            persisted = json.load(f)
                        if persisted.get("status") in active_statuses:
                            # Extract project name from filename (name.state.json)
                            fname = state_file.stem.replace('.state', '')
                            if fname != "default":
                                project_name = fname
                                # Load into memory for future use
                                deployment_states[fname] = persisted
                                break
                    except (json.JSONDecodeError, IOError):
                        continue

        # Use project-specific service if we found/received a project name
        if project_name:
            service = get_service_for_project(project_name)
            service.init()
            service.ensure_workspace()
        else:
            service = terraform_service

        # Check if Terraform state exists
        state_file = service.terraform_dir / "terraform.tfstate"

        if not state_file.exists():
            return jsonify({
                "success": True,
                "has_deployment": False,
                "message": "No infrastructure deployed yet"
            })

        # Get Terraform outputs
        output_result = service.output()

        if not output_result.get("success"):
            # State exists but outputs failed - might be empty state
            return jsonify({
                "success": True,
                "has_deployment": False,
                "message": "No active infrastructure found"
            })

        outputs = output_result.get("outputs", {})

        # Decrypt Windows attack box password from EC2Launch v2
        # (EC2Launch generates a random password encrypted with the instance's RSA key pair)
        attack_box_instance_id = outputs.get("attack_box_instance_id", {}).get("value")
        if attack_box_instance_id:
            win_password = get_windows_password(attack_box_instance_id, service)
            if win_password:
                outputs["attack_box_admin_password"] = {"value": win_password, "sensitive": True}
        
        # Check if there's actually deployed infrastructure
        # by checking for key outputs
        vpc_id = outputs.get("vpc_id", {}).get("value")
        
        if not vpc_id:
            return jsonify({
                "success": True,
                "has_deployment": False,
                "message": "No active infrastructure found"
            })
        
        # Parse outputs into structured format
        infrastructure = {
            "has_deployment": True,
            "deployment_mode": outputs.get("c2_deployment_mode", {}).get("value", "unknown"),
            
            # Network
            "network": {
                "vpc_id": vpc_id,
                "vpc_cidr": outputs.get("vpc_cidr_block", {}).get("value"),
                "public_subnets": outputs.get("public_subnet_ids", {}).get("value", []),
                "private_subnets": outputs.get("private_subnet_ids", {}).get("value", []),
            },
            
            # Security Groups
            "security_groups": {
                "c2_server_sg": outputs.get("c2_team_server_security_group_id", {}).get("value"),
                "redirector_sg": outputs.get("proxy_redirector_security_group_id", {}).get("value"),
            },
            
            # Dashboard Server jump (sole SSH/RDP jump — the per-deployment
            # bastion is gone). EIP resolved from override + detected sources.
            "jump_host": dashboard_settings_service.resolve_eip()["effective"],

            # C2 Servers
            "c2_servers": {
                "instance_ids": outputs.get("c2_team_server_instance_ids", {}).get("value", []),
                "private_ips": outputs.get("c2_team_server_private_ips", {}).get("value", []),
                "servers": outputs.get("c2_servers", {}).get("value", {}),
                "phase_instance_ids": outputs.get("c2_phase_server_instance_ids", {}).get("value", {}),
                "phase_private_ips": outputs.get("c2_phase_server_private_ips", {}).get("value", {}),
            },
            
            # Proxy Redirectors
            "redirectors": {
                "instance_ids": outputs.get("proxy_redirector_instance_ids", {}).get("value", []),
                "public_ips": outputs.get("proxy_redirector_public_ips", {}).get("value", []),
                "private_ips": outputs.get("proxy_redirector_private_ips", {}).get("value", []),
            },

            # Attack Box (Windows workstation)
            "attack_box": {
                "enabled": outputs.get("attack_box_private_ip", {}).get("value") is not None,
                "private_ip": outputs.get("attack_box_private_ip", {}).get("value"),
                "admin_password": outputs.get("attack_box_admin_password", {}).get("value"),
                "rdp_tunnel": outputs.get("attack_box_rdp_tunnel", {}).get("value"),
            },

            # Ansible Inventory Info
            "ansible_inventory": outputs.get("ansible_inventory", {}).get("value", {}),
        }

        # Count resources
        infrastructure["summary"] = {
            "c2_server_count": len(infrastructure["c2_servers"]["instance_ids"]) or len(infrastructure["c2_servers"]["servers"]),
            "redirector_count": len(infrastructure["redirectors"]["instance_ids"]),
            "has_jump_host": bool(infrastructure["jump_host"]),
            "has_attack_box": infrastructure["attack_box"]["enabled"],
            "subnet_count": len(infrastructure["network"]["public_subnets"]) + len(infrastructure["network"]["private_subnets"]),
        }
        
        return jsonify({
            "success": True,
            "project_name": project_name or "default",
            **infrastructure
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "message": f"Error getting infrastructure state: {str(e)}"
        }), 500


# /infrastructure/refresh removed 2026-05-21 — no frontend or script
# caller. The endpoint shelled out to `terraform refresh` against the
# global terraform_service workspace, which is wrong for any per-project
# deployment (would refresh the default workspace). The Manage sub-pill
# uses ?refresh=true on /api/deploy/resources/project/<name> for live
# AWS state instead.


# =============================================================================
# DEPLOYMENT DETAILS ENDPOINT
# =============================================================================

@bp.route('/deployment-details', methods=['GET'])
def get_deployment_details():
    """
    Get comprehensive deployment details including IPs, credentials, and access instructions.
    This is the primary endpoint for the Deployment Manager UI.

    HIGH #8 fix (2026-05-28): now project-aware. The previous implementation
    used the module-level `terraform_service` (default workspace), so any
    Manage-page lookup against a per-project deployment either returned
    empty or — worse — cross-contaminated by reading whichever workspace
    happened to be selected at the time (CRITICAL #1 + #2 race). Reading
    `?project=<name>` and routing through `get_service_for_project()`
    pins the lookup to the correct workspace + tfvars file.
    """
    try:
        project_name = request.args.get("project") or None

        # Per-project services have their own workspace + tfvars file.
        # `get_service_for_project()` returns a TerraformService scoped to
        # `configs/<project>.tfvars` and workspace=<project>, falling back
        # to the legacy default workspace when no project is given.
        if project_name:
            service = get_service_for_project(project_name)
        else:
            service = terraform_service

        # Check if Terraform state exists
        # Per-project workspaces store state under terraform.tfstate.d/<ws>/
        # — use the helper so we honor that layout.
        try:
            state_file = service.get_state_file_path()
        except Exception:
            state_file = service.terraform_dir / "terraform.tfstate"

        if not state_file.exists():
            return jsonify({
                "success": False,
                "error": "No deployment found",
                "has_deployment": False
            })

        # Get Terraform outputs (project-scoped — see comment above)
        output_result = service.output()
        
        if not output_result.get("success"):
            return jsonify({
                "success": False,
                "error": "Failed to get deployment outputs",
                "has_deployment": False
            })
        
        outputs = output_result.get("outputs", {})
        
        # Get deployment type
        deployment_type = outputs.get("deployment_type", {}).get("value", "")
        deployment_mode = outputs.get("deployment_mode", {}).get("value", {})
        
        if not deployment_type:
            return jsonify({
                "success": False,
                "error": "No active deployment",
                "has_deployment": False
            })
        
        # Determine deployment architecture
        is_c2_only = deployment_mode.get("is_c2_only", False)
        is_goad_only = deployment_mode.get("is_goad_only", False)
        is_combined = deployment_mode.get("is_combined", False)
        
        # Build response
        response = {
            "success": True,
            "has_deployment": True,
            "deployment_type": deployment_type,
            "architecture": "goad-only" if is_goad_only else ("combined" if is_combined else "c2-only"),
            
            # Cobalt Strike Connection Info
            "cobalt_strike": {
                "host": None,
                "port": outputs.get("cs_connection_info", {}).get("value", {}).get("port", 50050),
                "method": outputs.get("cs_connection_info", {}).get("value", {}).get("method", "ssh_tunnel"),
                "password": None  # User must know this - not stored in state
            },
            
            # C2 Infrastructure (if deployed)
            "infrastructure": {
                "c2_server": {
                    "private_ip": outputs.get("c2_server_primary_ip", {}).get("value"),
                    "public_ip": None  # C2 servers are in private subnets
                },
                "redirectors": outputs.get("proxy_redirector_public_ips", {}).get("value", []),
                # Dashboard Server jump EIP (sole SSH jump; bastion removed).
                "jump_host": dashboard_settings_service.resolve_eip()["effective"],
            },
            
            # GOAD Lab (if deployed)
            "goad": {
                "deployed": is_goad_only or is_combined,
                "lab_type": outputs.get("goad_lab_type", {}).get("value"),
                "jumpbox": {
                    "public_ip": outputs.get("goad_jumpbox_public_ip", {}).get("value"),
                    "private_ip": outputs.get("goad_jumpbox_private_ip", {}).get("value"),
                    "ssh_command": outputs.get("goad_jumpbox_ssh_command", {}).get("value")
                },
                "vms": outputs.get("goad_lab_vms", {}).get("value", []),
                "domain_info": outputs.get("goad_domain_info", {}).get("value"),
                "credentials": outputs.get("goad_credentials", {}).get("value")
            },
            
            # VPC Peering (combined mode)
            "vpc_peering": {
                "enabled": is_combined,
                "connection_id": outputs.get("vpc_peering_connection_id", {}).get("value")
            },
            
            # Access Instructions
            "access_instructions": outputs.get("access_instructions", {}).get("value", {})
        }
        
        # Set CS host based on architecture
        if is_goad_only:
            response["cobalt_strike"]["host"] = outputs.get("goad_jumpbox_public_ip", {}).get("value")
            response["cobalt_strike"]["method"] = "direct"
        else:
            response["cobalt_strike"]["host"] = outputs.get("c2_server_primary_ip", {}).get("value")
            response["cobalt_strike"]["method"] = "ssh_tunnel"
        
        # Add GOAD lab info if applicable
        if response["goad"]["deployed"] and response["goad"]["lab_type"]:
            lab_info = get_lab_info(response["goad"]["lab_type"])
            if lab_info:
                response["goad"]["lab_info"] = {
                    "vm_count": lab_info.get("vm_count"),
                    "domains": lab_info.get("domains"),
                    "forests": lab_info.get("forests"),
                    "description": lab_info.get("description")
                }
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# /goad-status removed 2026-05-21 — no frontend or script caller.
# It also read terraform_service.output() against the default workspace,
# which is wrong for per-project GOAD deployments. The Manage sub-pill
# uses /api/goad/status (which IS project-aware via the goad workspace
# marker) for the same information.


# =============================================================================
# DEPRECATED: SSH KEY DOWNLOAD ENDPOINT
# =============================================================================
# ⚠️  DEPRECATED: This endpoint is deprecated and will be removed.
# 
# SECURITY CHANGE: Private keys are no longer generated by Terraform or
# transmitted via this API. Instead:
#   1. Users generate their own SSH key locally (ssh-keygen -t ed25519)
#   2. Users upload their PUBLIC key via the web UI before deployment
#   3. Internal keys are generated ON the hosts during bootstrap
#   4. Private keys NEVER leave the machine that generates them
#
# Use the new /connection-info endpoint for secure connection instructions.
# =============================================================================

@bp.route('/ssh-key/<key_type>', methods=['GET'])
def download_ssh_key(key_type: str):
    """
    ⚠️  DEPRECATED: This endpoint is deprecated.
    
    Private keys are no longer provided by this API for security reasons.
    
    NEW APPROACH:
    1. Generate your own SSH key: ssh-keygen -t ed25519 -f ~/.ssh/goad_key
    2. Upload your PUBLIC key via the web UI before deployment
    3. Use your private key to connect: ssh -i ~/.ssh/goad_key ubuntu@<jumpbox-ip>
    
    Use GET /connection-info for secure connection instructions.
    """
    # Return deprecation notice instead of keys
    return jsonify({
        "success": False,
        "deprecated": True,
        "error": "This endpoint is deprecated for security reasons.",
        "message": "Private keys are no longer provided by this API.",
        "migration_guide": {
            "step1": "Generate your own SSH key: ssh-keygen -t ed25519 -f ~/.ssh/goad_key",
            "step2": "Upload your PUBLIC key via the Deploy tab before deployment",
            "step3": "Use your private key to connect: ssh -i ~/.ssh/goad_key ubuntu@<jumpbox-ip>",
            "step4": "Use GET /deploy/connection-info for connection instructions"
        },
        "security_reason": "Private keys should never be transmitted over networks. "
                          "Keys are now generated on hosts and never leave them."
    }), 410  # 410 Gone - resource no longer available


@bp.route('/ssh-key/download', methods=['POST'])
def save_ssh_key_to_disk():
    """
    ⚠️  DEPRECATED: This endpoint is deprecated.
    
    Private keys are no longer provided by this API for security reasons.
    
    NEW APPROACH:
    1. Generate your own SSH key: ssh-keygen -t ed25519 -f ~/.ssh/goad_key
    2. Upload your PUBLIC key via the web UI before deployment
    3. Use your private key to connect: ssh -i ~/.ssh/goad_key ubuntu@<jumpbox-ip>
    
    Use GET /connection-info for secure connection instructions.
    """
    # Return deprecation notice instead of saving keys
    return jsonify({
        "success": False,
        "deprecated": True,
        "error": "This endpoint is deprecated for security reasons.",
        "message": "Private keys are no longer provided by this API.",
        "migration_guide": {
            "step1": "Generate your own SSH key: ssh-keygen -t ed25519 -f ~/.ssh/goad_key",
            "step2": "Upload your PUBLIC key via the Deploy tab before deployment",
            "step3": "Use your private key to connect: ssh -i ~/.ssh/goad_key ubuntu@<jumpbox-ip>",
            "step4": "Use GET /deploy/connection-info for connection instructions"
        },
        "security_reason": "Private keys should never be transmitted over networks. "
                          "Keys are now generated on hosts and never leave them."
    }), 410  # 410 Gone - resource no longer available


# Keep the old implementation commented for reference during migration
# TODO: Remove after migration is complete
"""
# OLD IMPLEMENTATION - DEPRECATED
@bp.route('/ssh-key/download', methods=['POST'])
def save_ssh_key_to_disk_OLD():
    # Save SSH key to user's ~/.ssh directory.
    # This endpoint is called from the UI to download and save the key.
    # ... (old implementation removed for security)
"""


# /upload-to-s3 removed 2026-05-21 — no frontend or script caller.
# The deploy pipeline (run_deployment) uploads the CS archive to S3
# itself via webapp.backend.utils.s3_upload during the apply phase, and
# the per-project tfvars is rewritten with the resulting S3 URI in-place
# (see update_tfvars_cs_path above). A standalone "upload to S3" UI
# button was never wired up.


# =============================================================================
# STOP/START INFRASTRUCTURE ENDPOINTS
# =============================================================================

@bp.route('/stop', methods=['POST'])
def stop_infrastructure():
    """
    Stop all EC2 instances (keep resources, stop compute charges).
    This is a cost-saving measure that preserves all data and configuration.

    Project resolution: body ``project_name`` wins, else ``?project=`` query
    param, else falls back to the global tfvars' ``project_name`` field (legacy
    single-deployment hosts). Per-project tfvars dictate the region.
    """
    try:
        import boto3

        # Get project name from request body, then query, then global tfvars
        data = request.get_json() or {}
        project_name = (data.get('project_name') or request.args.get('project') or '').strip()

        # Pull region (and project_name fallback) from the per-project tfvars
        # when we already know the name, otherwise from the global tfvars.
        config = _read_project_config(project_name) if project_name else _read_project_config(None)
        aws_region = config.get('aws_region', 'eu-central-1')

        if not project_name:
            project_name = config.get('project_name', '')
        
        if not project_name:
            return jsonify({
                "success": False,
                "error": "Project name not specified"
            }), 400
        
        # Connect to EC2
        ec2 = boto3.client('ec2', region_name=aws_region)
        
        # Find instances by project tag
        response = ec2.describe_instances(
            Filters=[
                {'Name': 'tag:Project', 'Values': [project_name]},
                {'Name': 'instance-state-name', 'Values': ['running']}
            ]
        )
        
        instances = []
        instance_ids = []
        for reservation in response.get('Reservations', []):
            for inst in reservation.get('Instances', []):
                inst_id = inst['InstanceId']
                instance_ids.append(inst_id)
                # Get instance name from tags
                name = inst_id
                for tag in inst.get('Tags', []):
                    if tag['Key'] == 'Name':
                        name = tag['Value']
                        break
                instances.append({
                    'id': inst_id,
                    'name': name,
                    'type': inst.get('InstanceType', ''),
                    'private_ip': inst.get('PrivateIpAddress'),
                    'public_ip': inst.get('PublicIpAddress')
                })

        if not instance_ids:
            return jsonify({
                "success": True,
                "message": "No running instances found",
                "stopped_count": 0,
                "instances": []
            })

        # Stop instances
        ec2.stop_instances(InstanceIds=instance_ids)

        return jsonify({
            "success": True,
            "message": f"Stopped {len(instance_ids)} instances",
            "stopped_count": len(instance_ids),
            "instance_ids": instance_ids,
            "instances": instances
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@bp.route('/start', methods=['POST'])
def start_infrastructure():
    """
    Start all stopped EC2 instances.
    Resumes compute charges.

    Same project-resolution model as /stop.
    """
    try:
        import boto3

        # Get project name from request body, then query, then global tfvars
        data = request.get_json() or {}
        project_name = (data.get('project_name') or request.args.get('project') or '').strip()

        config = _read_project_config(project_name) if project_name else _read_project_config(None)
        aws_region = config.get('aws_region', 'eu-central-1')

        if not project_name:
            project_name = config.get('project_name', '')
        
        if not project_name:
            return jsonify({
                "success": False,
                "error": "Project name not specified"
            }), 400
        
        # Connect to EC2
        ec2 = boto3.client('ec2', region_name=aws_region)
        
        # Find stopped instances by project tag
        response = ec2.describe_instances(
            Filters=[
                {'Name': 'tag:Project', 'Values': [project_name]},
                {'Name': 'instance-state-name', 'Values': ['stopped']}
            ]
        )
        
        instances = []
        instance_ids = []
        for reservation in response.get('Reservations', []):
            for inst in reservation.get('Instances', []):
                inst_id = inst['InstanceId']
                instance_ids.append(inst_id)
                # Get instance name from tags
                name = inst_id
                for tag in inst.get('Tags', []):
                    if tag['Key'] == 'Name':
                        name = tag['Value']
                        break
                instances.append({
                    'id': inst_id,
                    'name': name,
                    'type': inst.get('InstanceType', ''),
                    'private_ip': inst.get('PrivateIpAddress'),
                    'public_ip': inst.get('PublicIpAddress')
                })

        if not instance_ids:
            return jsonify({
                "success": True,
                "message": "No stopped instances found",
                "started_count": 0,
                "instances": []
            })

        # Start instances
        ec2.start_instances(InstanceIds=instance_ids)

        return jsonify({
            "success": True,
            "message": f"Started {len(instance_ids)} instances",
            "started_count": len(instance_ids),
            "instance_ids": instance_ids,
            "instances": instances
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@bp.route('/instance-status', methods=['GET'])
def get_instance_status():
    """
    Get the current status of all EC2 instances for this project.
    Accepts optional ?project=name query parameter — when provided the
    region is read from configs/<project>.tfvars; otherwise the global.
    """
    try:
        import boto3

        # Get project name from query param
        project_name = request.args.get('project', '').strip()

        # 2026-05-23 — demo project has no real EC2; short-circuit so the
        # Manage / dashboard surfaces don't pay a wasted boto3 call (and
        # don't 400 when no project query param is sent).
        from webapp.backend.services import demo_data_service
        if demo_data_service.is_demo_project(project_name):
            return jsonify({
                "success": True,
                "is_demo": True,
                "instances": [],
                "status_counts": {"running": 0, "stopped": 0, "pending": 0,
                                  "stopping": 0, "terminated": 0},
            })

        config = _read_project_config(project_name) if project_name else _read_project_config(None)
        aws_region = config.get('aws_region', 'eu-central-1')

        if not project_name:
            project_name = config.get('project_name', '')

        if not project_name:
            return jsonify({
                "success": False,
                "error": "Project name not configured"
            }), 400
        
        # Connect to EC2
        ec2 = boto3.client('ec2', region_name=aws_region)
        
        # Find all instances by project tag
        response = ec2.describe_instances(
            Filters=[
                {'Name': 'tag:Project', 'Values': [project_name]}
            ]
        )
        
        instances = []
        status_counts = {'running': 0, 'stopped': 0, 'pending': 0, 'stopping': 0, 'terminated': 0}
        
        for reservation in response.get('Reservations', []):
            for instance in reservation.get('Instances', []):
                state = instance['State']['Name']
                status_counts[state] = status_counts.get(state, 0) + 1
                
                # Get instance name from tags
                name = 'Unknown'
                for tag in instance.get('Tags', []):
                    if tag['Key'] == 'Name':
                        name = tag['Value']
                        break
                
                instances.append({
                    'id': instance['InstanceId'],
                    'name': name,
                    'state': state,
                    'type': instance['InstanceType'],
                    'private_ip': instance.get('PrivateIpAddress'),
                    'public_ip': instance.get('PublicIpAddress')
                })
        
        return jsonify({
            "success": True,
            "project_name": project_name,
            "region": aws_region,
            "instances": instances,
            "status_counts": status_counts,
            "total_instances": len(instances)
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# =============================================================================
# RESOURCE LIST ENDPOINT
# =============================================================================

@bp.route('/resources/project/<project_name>', methods=['GET'])
def get_project_resources(project_name: str):
    """
    Get resources for a specific project/deployment.
    When refresh=true, does a full AWS query for all resource types.
    Otherwise returns saved resources from deployment history.
    """
    # 2026-05-22 — demo deployment short-circuits the AWS query path and
    # serves canned resources from demo_data_service. No boto3 calls.
    from webapp.backend.services import demo_data_service
    if demo_data_service.is_demo_project(project_name):
        return jsonify({
            "success": True,
            "project": project_name,
            "deployment_type": demo_data_service.DEMO_DEPLOYMENT_TYPE,
            "resources": demo_data_service.resources(),
            "total": len(demo_data_service.resources()),
            "is_demo": True,
        })
    try:
        import boto3
        from webapp.backend.utils.config_parser import ConfigParser
        from datetime import datetime

        # Load saved deployment resources for metadata
        resources_file = project_root / "logs" / "deployment_resources.json"
        deployment_data = {}

        if resources_file.exists():
            with open(resources_file, 'r') as f:
                all_deployments = json.load(f)
            deployment_data = all_deployments.get(project_name, {})
        
        aws_region = deployment_data.get('region', 'eu-central-1')
        
        # Check if we should do a full AWS refresh
        refresh = request.args.get('refresh', 'false').lower() == 'true'
        
        if refresh:
            # Do a FULL AWS query for all resource types (same as save_deployment_resources)
            resources = []
            ec2 = boto3.client('ec2', region_name=aws_region)
            project_prefix = project_name.lower().replace('_', '-')
            
            # EC2 Instances (by tag)
            try:
                response = ec2.describe_instances(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for reservation in response.get('Reservations', []):
                    for instance in reservation.get('Instances', []):
                        # Skip terminated instances
                        if instance['State']['Name'] == 'terminated':
                            continue
                        name = next((t['Value'] for t in instance.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                        role = next((t['Value'] for t in instance.get('Tags', []) if t['Key'] == 'Role'), '')
                        resources.append({
                            'type': 'ec2',
                            'id': instance['InstanceId'],
                            'name': name,
                            'role': role,
                            'state': instance['State']['Name'],
                            'instance_type': instance['InstanceType'],
                            'private_ip': instance.get('PrivateIpAddress'),
                            'public_ip': instance.get('PublicIpAddress')
                        })
            except Exception as e:
                print(f"Error fetching EC2 instances: {e}")
            
            # VPCs (by tag)
            try:
                response = ec2.describe_vpcs(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for vpc in response.get('Vpcs', []):
                    name = next((t['Value'] for t in vpc.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                    resources.append({
                        'type': 'vpc',
                        'id': vpc['VpcId'],
                        'name': name,
                        'state': vpc['State'],
                        'cidr': vpc['CidrBlock']
                    })
            except Exception as e:
                print(f"Error fetching VPCs: {e}")
            
            # Subnets (by tag)
            try:
                response = ec2.describe_subnets(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for subnet in response.get('Subnets', []):
                    name = next((t['Value'] for t in subnet.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                    resources.append({
                        'type': 'subnet',
                        'id': subnet['SubnetId'],
                        'name': name,
                        'state': subnet['State'],
                        'cidr': subnet['CidrBlock'],
                        'az': subnet['AvailabilityZone']
                    })
            except Exception as e:
                print(f"Error fetching subnets: {e}")
            
            # Security Groups (by tag)
            try:
                response = ec2.describe_security_groups(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for sg in response.get('SecurityGroups', []):
                    resources.append({
                        'type': 'security_group',
                        'id': sg['GroupId'],
                        'name': sg['GroupName'],
                        'state': 'active',
                        'description': sg.get('Description', '')[:100]
                    })
            except Exception as e:
                print(f"Error fetching security groups: {e}")
            
            # NAT Gateways (by tag)
            try:
                response = ec2.describe_nat_gateways(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for nat in response.get('NatGateways', []):
                    if nat['State'] == 'deleted':
                        continue
                    name = next((t['Value'] for t in nat.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                    public_ip = nat.get('NatGatewayAddresses', [{}])[0].get('PublicIp', 'N/A')
                    resources.append({
                        'type': 'nat_gateway',
                        'id': nat['NatGatewayId'],
                        'name': name,
                        'state': nat['State'],
                        'public_ip': public_ip
                    })
            except Exception as e:
                print(f"Error fetching NAT gateways: {e}")
            
            # Elastic IPs (by tag)
            try:
                response = ec2.describe_addresses(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for eip in response.get('Addresses', []):
                    name = next((t['Value'] for t in eip.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                    resources.append({
                        'type': 'elastic_ip',
                        'id': eip.get('AllocationId', 'N/A'),
                        'name': name,
                        'state': 'associated' if eip.get('InstanceId') else 'available',
                        'public_ip': eip.get('PublicIp')
                    })
            except Exception as e:
                print(f"Error fetching Elastic IPs: {e}")
            
            # Internet Gateways (by tag)
            try:
                response = ec2.describe_internet_gateways(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for igw in response.get('InternetGateways', []):
                    name = next((t['Value'] for t in igw.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                    attached = 'attached' if igw.get('Attachments') else 'detached'
                    resources.append({
                        'type': 'internet_gateway',
                        'id': igw['InternetGatewayId'],
                        'name': name,
                        'state': attached
                    })
            except Exception as e:
                print(f"Error fetching Internet Gateways: {e}")
            
            # Key Pairs (by tag)
            try:
                response = ec2.describe_key_pairs(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for kp in response.get('KeyPairs', []):
                    resources.append({
                        'type': 'key_pair',
                        'id': kp.get('KeyPairId', kp['KeyName']),
                        'name': kp['KeyName'],
                        'state': 'available',
                        'key_type': kp.get('KeyType', 'rsa')
                    })
            except Exception as e:
                print(f"Error fetching key pairs: {e}")
            
            # Route Tables (by tag)
            try:
                response = ec2.describe_route_tables(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for rt in response.get('RouteTables', []):
                    name = next((t['Value'] for t in rt.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                    route_count = len(rt.get('Routes', []))
                    resources.append({
                        'type': 'route_table',
                        'id': rt['RouteTableId'],
                        'name': name,
                        'state': 'active',
                        'route_count': route_count
                    })
            except Exception as e:
                print(f"Error fetching route tables: {e}")
            
            # Network Interfaces (by tag)
            try:
                response = ec2.describe_network_interfaces(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for eni in response.get('NetworkInterfaces', []):
                    name = next((t['Value'] for t in eni.get('TagSet', []) if t['Key'] == 'Name'), 'Unnamed')
                    private_ip = eni.get('PrivateIpAddress', 'N/A')
                    resources.append({
                        'type': 'network_interface',
                        'id': eni['NetworkInterfaceId'],
                        'name': name,
                        'state': eni.get('Status', 'unknown'),
                        'private_ip': private_ip
                    })
            except Exception as e:
                print(f"Error fetching network interfaces: {e}")
            
            # S3 Buckets (by name prefix - no tags) + list objects
            try:
                s3 = boto3.client('s3', region_name=aws_region)
                response = s3.list_buckets()
                for bucket in response.get('Buckets', []):
                    if bucket['Name'].lower().startswith(project_prefix):
                        bucket_info = {
                            'type': 's3_bucket',
                            'id': bucket['Name'],
                            'name': bucket['Name'],
                            'state': 'available',
                            'created': bucket['CreationDate'].isoformat(),
                            'objects': []
                        }
                        # List objects in the bucket (max 50)
                        try:
                            obj_response = s3.list_objects_v2(
                                Bucket=bucket['Name'],
                                MaxKeys=50
                            )
                            for obj in obj_response.get('Contents', []):
                                size_bytes = obj['Size']
                                if size_bytes >= 1024 * 1024:
                                    size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
                                elif size_bytes >= 1024:
                                    size_str = f"{size_bytes / 1024:.1f} KB"
                                else:
                                    size_str = f"{size_bytes} B"
                                bucket_info['objects'].append({
                                    'key': obj['Key'],
                                    'size': size_str,
                                    'size_bytes': size_bytes,
                                    'last_modified': obj['LastModified'].isoformat()
                                })
                            bucket_info['object_count'] = obj_response.get('KeyCount', 0)
                            bucket_info['is_truncated'] = obj_response.get('IsTruncated', False)
                        except Exception as obj_err:
                            print(f"Error listing objects in {bucket['Name']}: {obj_err}")
                        resources.append(bucket_info)
            except Exception as e:
                print(f"Error fetching S3 buckets: {e}")
            
            # IAM Roles (by name prefix - no tags)
            try:
                iam = boto3.client('iam', region_name=aws_region)
                paginator = iam.get_paginator('list_roles')
                for page in paginator.paginate():
                    for role in page.get('Roles', []):
                        if role['RoleName'].lower().startswith(project_prefix):
                            resources.append({
                                'type': 'iam_role',
                                'id': role['RoleId'],
                                'name': role['RoleName'],
                                'state': 'active',
                                'created': role['CreateDate'].isoformat()
                            })
            except Exception as e:
                print(f"Error fetching IAM roles: {e}")
            
            # IAM Instance Profiles (by name prefix - no tags)
            try:
                iam = boto3.client('iam', region_name=aws_region)
                paginator = iam.get_paginator('list_instance_profiles')
                for page in paginator.paginate():
                    for profile in page.get('InstanceProfiles', []):
                        if profile['InstanceProfileName'].lower().startswith(project_prefix):
                            resources.append({
                                'type': 'iam_instance_profile',
                                'id': profile['InstanceProfileId'],
                                'name': profile['InstanceProfileName'],
                                'state': 'active',
                                'role_count': len(profile.get('Roles', []))
                            })
            except Exception as e:
                print(f"Error fetching IAM instance profiles: {e}")
            
            # Update the saved resources file with the refreshed data
            if resources:
                try:
                    all_deployments = {}
                    if resources_file.exists():
                        with open(resources_file, 'r') as f:
                            all_deployments = json.load(f)
                    
                    if project_name not in all_deployments:
                        all_deployments[project_name] = {}
                    
                    all_deployments[project_name].update({
                        'project_name': project_name,
                        'deployed_at': all_deployments.get(project_name, {}).get('deployed_at', datetime.now().isoformat()),
                        'region': aws_region,
                        'resource_count': len(resources),
                        'resources': resources,
                        'last_refreshed': datetime.now().isoformat()
                    })
                    
                    with open(resources_file, 'w') as f:
                        json.dump(all_deployments, f, indent=2)
                except Exception as e:
                    print(f"Error saving refreshed resources: {e}")
        else:
            # Return saved resources
            resources = deployment_data.get('resources', [])
        
        # Group resources by type
        grouped = {}
        for r in resources:
            rtype = r['type']
            if rtype not in grouped:
                grouped[rtype] = []
            grouped[rtype].append(r)
        
        return jsonify({
            "success": True,
            "project_name": project_name,
            "deployment_type": deployment_data.get('deployment_type'),
            "deployed_at": deployment_data.get('deployed_at'),
            "region": aws_region,
            "resource_count": len(resources),
            "resources": resources,
            "resources_grouped": grouped
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


def _query_us_east_1_resources():
    """Query us-east-1 for cross-region resources (CloudFront ACM certs).

    CloudFront requires its ACM certificates to live in us-east-1 regardless
    of where the rest of the infra is deployed. The primary `/resources/...`
    endpoints currently build their boto3 clients against `eu-central-1`,
    so these certs would otherwise be invisible. Returns a dict of resource
    lists tagged with their source region — never raises (logs and returns
    an empty list on any error so the primary handler stays healthy).
    """
    import boto3
    out = {'acm_us_east_1': []}
    try:
        acm_us = boto3.client('acm', region_name='us-east-1')
        certs = acm_us.list_certificates(MaxItems=100).get('CertificateSummaryList', [])
        for c in certs:
            out['acm_us_east_1'].append({
                'arn': c.get('CertificateArn'),
                'domain': c.get('DomainName'),
                'status': c.get('Status'),
                'in_use': c.get('InUse'),
                'region': 'us-east-1',
            })
    except Exception as e:
        # Don't fail the whole handler if cross-region ACM is unreachable
        print(f"[deploy] us-east-1 ACM query failed: {e}")
    return out


def _query_orphan_candidates(region):
    """Query AWS for resource types the Cleanup sub-pill flags as orphans.

    Used by /resources/all-projects so the frontend's `_detectOrphans()` has
    something to detect against. The endpoint previously only returned the
    per-project summary list, which is why the Cleanup sub-pill rendered
    empty even when orphan EIPs, untagged S3 buckets, and !in_use ACM certs
    existed in the account.

    Returns a dict with keys: eips, acm_certs, s3_buckets, snapshots. Each
    value is a list of plain dicts shaped for the frontend (snake_case
    field names matching _detectOrphans + _renderGroup expectations).
    Never raises — per-resource queries swallow boto exceptions and log to
    stderr so a single unhealthy service can't blank the whole pane.
    """
    import boto3
    out = {
        'eips': [],
        'acm_certs': [],
        's3_buckets': [],
        'snapshots': [],
    }

    # ── Elastic IPs (region-scoped) ────────────────────────────────────────
    # _detectOrphans() flags any EIP with no `instance_id`. We return ALL
    # EIPs (attached + unattached) and let the frontend filter so the
    # detection rules stay client-side, matching the existing contract.
    try:
        ec2 = boto3.client('ec2', region_name=region)
        for eip in ec2.describe_addresses().get('Addresses', []):
            tags = {t['Key']: t['Value'] for t in eip.get('Tags', []) or []}
            out['eips'].append({
                'allocation_id': eip.get('AllocationId'),
                'public_ip': eip.get('PublicIp'),
                'instance_id': eip.get('InstanceId'),  # None == orphan
                'network_interface_id': eip.get('NetworkInterfaceId'),
                'region': region,
                'project_tag': tags.get('Project'),
                'name_tag': tags.get('Name'),
            })
    except Exception as e:
        print(f"[deploy] EIP query failed (region={region}): {e}")

    # ── ACM certs (region-scoped — us-east-1 added separately) ─────────────
    try:
        acm = boto3.client('acm', region_name=region)
        for c in acm.list_certificates(MaxItems=100).get('CertificateSummaryList', []):
            out['acm_certs'].append({
                'arn': c.get('CertificateArn'),
                'domain': c.get('DomainName'),
                'status': c.get('Status'),
                'in_use': c.get('InUse'),
                'region': region,
            })
    except Exception as e:
        print(f"[deploy] ACM query failed (region={region}): {e}")

    # ── S3 buckets (global namespace, region-agnostic listing) ─────────────
    # list_buckets returns every bucket in the account — the frontend's
    # _detectOrphans() applies the project-prefix regex. We do NOT pre-filter
    # so the detection rule remains in one place (and is auditable in JS).
    try:
        s3 = boto3.client('s3', region_name=region)
        resp = s3.list_buckets()
        for b in resp.get('Buckets', []):
            entry = {
                'name': b['Name'],
                'creation_date': b['CreationDate'].isoformat() if b.get('CreationDate') else None,
            }
            # Best-effort region lookup — get_bucket_location returns None for
            # us-east-1. Wrap each call so a 403 on one bucket doesn't break
            # the whole list.
            try:
                loc = s3.get_bucket_location(Bucket=b['Name'])
                entry['region'] = loc.get('LocationConstraint') or 'us-east-1'
            except Exception:
                entry['region'] = None
            out['s3_buckets'].append(entry)
    except Exception as e:
        print(f"[deploy] S3 bucket query failed: {e}")

    # ── EBS snapshots (region-scoped, owner=self only) ─────────────────────
    # We surface owner=self snapshots so policy-managed DailySnapshot entries
    # show up — the frontend can group/filter as needed. Description is
    # included so DLM-policy snapshots are recognizable.
    try:
        ec2 = boto3.client('ec2', region_name=region)
        # OwnerIds=['self'] is critical — without it the API returns every
        # public AMI snapshot and breaks the timeout budget.
        snaps = ec2.describe_snapshots(OwnerIds=['self']).get('Snapshots', [])
        for s in snaps:
            tags = {t['Key']: t['Value'] for t in s.get('Tags', []) or []}
            out['snapshots'].append({
                'snapshot_id': s.get('SnapshotId'),
                'volume_id': s.get('VolumeId'),
                'state': s.get('State'),
                'start_time': s['StartTime'].isoformat() if s.get('StartTime') else None,
                'description': s.get('Description'),
                'volume_size': s.get('VolumeSize'),
                'region': region,
                'project_tag': tags.get('Project'),
            })
    except Exception as e:
        print(f"[deploy] Snapshot query failed (region={region}): {e}")

    return out


@bp.route('/resources/all-projects', methods=['GET'])
def get_all_project_resources():
    """
    Resource catalog used by the Deployments → Cleanup sub-pill.

    Returns:
      - `projects`: per-deployment summary read from
        logs/deployment_resources.json (cached, written at apply time).
      - `eips`, `acm_certs`, `s3_buckets`, `snapshots`: live AWS resource
        listings for the configured region. The frontend `_detectOrphans()`
        applies orphan detection rules (no instance_id, !in_use, regex
        against project prefixes, etc.).
      - `acm_us_east_1`: us-east-1 ACM certs (CloudFront-bound) so domain
        fronting cert orphans surface alongside region-local ones.

    Before this rebuild the endpoint only returned `projects` + the
    cross-region ACM list, leaving the Cleanup sub-pill blank in any
    account that actually had orphan EIPs/buckets/certs (visible in the
    AWS console but never delivered to the frontend).
    """
    try:
        from webapp.backend.utils.config_parser import ConfigParser

        resources_file = project_root / "logs" / "deployment_resources.json"

        # This endpoint is intentionally cross-project (the Cleanup sub-pill's
        # orphan scan walks ALL deployments), so the region is read from the
        # global tfvars on purpose — there's no single "active project" here.
        # If the operator wants a different region they can pass ?region= (TBD)
        # or rely on the eu-central-1 default that matches the project lock.
        aws_region = 'eu-central-1'
        try:
            global_tfvars = project_root / "configs" / "terraform.tfvars"
            if global_tfvars.exists():
                cfg = ConfigParser.parse_tfvars(global_tfvars)
                aws_region = cfg.get('aws_region', aws_region) or aws_region
        except Exception as e:
            print(f"[deploy] Could not read aws_region from tfvars: {e}")

        # Always include cross-region ACM (CloudFront ACM lives in us-east-1)
        cross_region = _query_us_east_1_resources()
        # Live AWS scan of orphan-candidate resource types.
        orphan_candidates = _query_orphan_candidates(aws_region)

        # Per-project summary (read from cached deployment_resources.json).
        projects = []
        if resources_file.exists():
            try:
                with open(resources_file, 'r') as f:
                    all_deployments = json.load(f)
                for project_name, data in all_deployments.items():
                    projects.append({
                        "project_name": project_name,
                        "deployment_type": data.get('deployment_type'),
                        "deployed_at": data.get('deployed_at'),
                        "region": data.get('region'),
                        "resource_count": data.get('resource_count', len(data.get('resources', []))),
                    })
                projects.sort(key=lambda x: x.get('deployed_at', ''), reverse=True)
            except Exception as e:
                print(f"[deploy] Failed to read deployment_resources.json: {e}")

        return jsonify({
            "success": True,
            "region": aws_region,
            "scanned_at": __import__('datetime').datetime.utcnow().isoformat() + 'Z',
            "projects": projects,
            "total_projects": len(projects),
            "eips": orphan_candidates.get('eips', []),
            "acm_certs": orphan_candidates.get('acm_certs', []),
            "s3_buckets": orphan_candidates.get('s3_buckets', []),
            "snapshots": orphan_candidates.get('snapshots', []),
            "acm_us_east_1": cross_region.get('acm_us_east_1', []),
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@bp.route('/outputs', methods=['GET'])
def get_terraform_outputs():
    """
    Get Terraform outputs for a specific project.
    Returns connection info like IPs, key names, etc.

    Reads region + domain + secret-names from the per-project tfvars
    (``configs/<project>.tfvars``) when ?project= is set; only falls back
    to the global tfvars when no project is specified.
    """
    try:
        import boto3

        # Get project name from query params
        project_name = request.args.get('project')

        # 2026-05-23 — demo project: short-circuit so Manage doesn't pay a
        # ~5-second boto3 round-trip describing instances that don't exist.
        from webapp.backend.services import demo_data_service
        if demo_data_service.is_demo_project(project_name):
            state = demo_data_service.deployment_state()
            return jsonify({
                "success": True,
                "is_demo": True,
                "outputs": state.get("outputs", {"project_name": project_name}),
            })

        # Per-project tfvars first; global only when no project specified.
        config = _read_project_config(project_name)
        aws_region = config.get('aws_region', 'eu-central-1')

        if not project_name:
            project_name = config.get('project_name', '')

        if not project_name:
            return jsonify({
                "success": False,
                "error": "Project name not specified"
            }), 400
        
        # Query AWS for instance details
        ec2 = boto3.client('ec2', region_name=aws_region)
        
        response = ec2.describe_instances(
            Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
        )
        
        outputs = {
            'project_name': project_name,
            'region': aws_region
        }
        
        # Extract instance info
        for reservation in response.get('Reservations', []):
            for instance in reservation.get('Instances', []):
                tags = {t['Key']: t['Value'] for t in instance.get('Tags', [])}
                role = tags.get('Role', '').lower()
                name = tags.get('Name', '')
                
                # Identify instance type by role or name
                if 'jumpbox' in role.lower() or 'jumpbox' in name.lower():
                    outputs['jumpbox_public_ip'] = instance.get('PublicIpAddress')
                    outputs['jumpbox_private_ip'] = instance.get('PrivateIpAddress')
                    outputs['jumpbox_instance_id'] = instance['InstanceId']
                    outputs['jumpbox_key_name'] = instance.get('KeyName')
                    outputs['jumpbox_state'] = instance['State']['Name']
                    
                elif 'dc01' in name.lower() or 'dc' in role.lower():
                    outputs['dc01_private_ip'] = instance.get('PrivateIpAddress')
                    outputs['dc01_instance_id'] = instance['InstanceId']
                    outputs['dc01_state'] = instance['State']['Name']
                    
                elif 'dc02' in name.lower():
                    outputs['dc02_private_ip'] = instance.get('PrivateIpAddress')
                    outputs['dc02_instance_id'] = instance['InstanceId']
                    outputs['dc02_state'] = instance['State']['Name']
                    
                elif 'team' in role.lower() or 'teamserver' in name.lower():
                    outputs['teamserver_private_ip'] = instance.get('PrivateIpAddress')
                    outputs['teamserver_instance_id'] = instance['InstanceId']
                    outputs['teamserver_state'] = instance['State']['Name']
                    
                elif 'attack' in role.lower() or 'attackbox' in name.lower():
                    outputs['attackbox_private_ip'] = instance.get('PrivateIpAddress')
                    outputs['attackbox_instance_id'] = instance['InstanceId']
                    outputs['attackbox_state'] = instance['State']['Name']

                elif 'c2' in role.lower() or 'c2-team-server' in name.lower() or 'c2-server' in name.lower():
                    # Multiple C2 servers — collect into a list
                    if 'c2_servers' not in outputs:
                        outputs['c2_servers'] = []
                    outputs['c2_servers'].append({
                        'name': name,
                        'instance_id': instance['InstanceId'],
                        'private_ip': instance.get('PrivateIpAddress'),
                        'state': instance['State']['Name'],
                        'phase': tags.get('Phase', ''),
                    })

                elif 'redirector' in role.lower() or 'redirector' in name.lower():
                    # Multiple redirectors — collect into a list
                    if 'redirectors' not in outputs:
                        outputs['redirectors'] = []
                    outputs['redirectors'].append({
                        'name': name,
                        'instance_id': instance['InstanceId'],
                        'public_ip': instance.get('PublicIpAddress'),
                        'private_ip': instance.get('PrivateIpAddress'),
                        'state': instance['State']['Name'],
                    })
                    # Keep single-redirector compat for GOAD mode
                    if 'redirector_public_ip' not in outputs:
                        outputs['redirector_public_ip'] = instance.get('PublicIpAddress')
                        outputs['redirector_private_ip'] = instance.get('PrivateIpAddress')
                        outputs['redirector_instance_id'] = instance['InstanceId']
                        outputs['redirector_state'] = instance['State']['Name']
        
        # Include config data useful for connection info
        # Try per-project state first (correct when multiple deployments exist),
        # fall back to global terraform.tfvars config
        project_config = dict(config)  # Start with global config as base
        try:
            state_file = project_root / "logs" / "deployment_state" / f"{project_name}.state.json"
            if state_file.exists():
                import json as json_mod
                state_data = json_mod.loads(state_file.read_text())
                # Override deployment_type from per-project state
                if state_data.get('deployment_type'):
                    project_config['deployment_type'] = state_data['deployment_type']
                # Override config fields from stored terraform outputs if available
                stored_outputs = state_data.get('output', {})
                for key in ('cs_teamserver_password', 'primary_domain_name'):
                    val = stored_outputs.get(key, {}).get('value')
                    if val:
                        project_config[key] = val
        except Exception:
            pass

        outputs['redirector_domain'] = project_config.get('primary_domain_name', '')
        outputs['c2_subdomain'] = project_config.get('c2_subdomain', 'api')
        outputs['key_pair_name'] = project_config.get('key_pair_name', '')
        outputs['cs_teamserver_password'] = project_config.get('cs_teamserver_password', '')
        outputs['cobalt_strike_license_secret_name'] = project_config.get('cobalt_strike_license_secret_name', '')
        outputs['deployment_type'] = project_config.get('deployment_type', '')
        outputs['primary_domain_name'] = config.get('primary_domain_name', '')
        outputs['malleable_profile'] = config.get('malleable_profile', '')
        outputs['enable_domain_fronting'] = config.get('enable_domain_fronting', False)
        outputs['enable_file_portal'] = config.get('enable_file_portal', False)
        if config.get('enable_file_portal'):
            outputs['portal_username'] = config.get('portal_username', 'operator')
            outputs['portal_password'] = config.get('portal_password', '')
            domain = config.get('primary_domain_name', '')
            outputs['portal_url'] = f"https://www.{domain}/login" if domain else None
        outputs['ssl_provider'] = config.get('ssl_provider', 'letsencrypt')
        outputs['enable_nat_gateway'] = config.get('enable_nat_gateway', True)

        # S3 bucket from deployment state
        try:
            state_file2 = project_root / "logs" / "deployment_state" / f"{project_name}.state.json"
            if state_file2.exists():
                import json as json_mod2
                sd = json_mod2.loads(state_file2.read_text())
                so = sd.get("output", {})
                outputs['cs_storage_bucket'] = so.get("cs_storage_bucket", {}).get("value", "")
                outputs['cs_upload_command'] = so.get("cs_storage_upload_command", {}).get("value", "")
        except Exception:
            pass

        # --- Run DNS lookup and password retrieval in parallel ---
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _fetch_dns():
            """Get DNS nameservers from Route 53."""
            domain_name = config.get('primary_domain_name', '')
            if not domain_name:
                return {}
            try:
                route53 = boto3.client('route53', region_name=aws_region)
                zones = route53.list_hosted_zones_by_name(DNSName=domain_name, MaxItems='1')
                for zone in zones.get('HostedZones', []):
                    zone_name = zone['Name'].rstrip('.')
                    if zone_name == domain_name:
                        zone_id = zone['Id'].split('/')[-1]
                        zone_detail = route53.get_hosted_zone(Id=zone_id)
                        ns_records = zone_detail.get('DelegationSet', {}).get('NameServers', [])
                        if ns_records:
                            return {'dns_nameservers': ns_records, 'dns_domain': domain_name}
            except Exception:
                pass
            return {}

        def _fetch_password():
            """Get attack box password — try cached state first, fall back to terraform."""
            # Fast path: check deployment state cache first
            try:
                state_file = project_root / "logs" / "deployment_state" / f"{project_name}.state.json"
                if state_file.exists():
                    import json as json_mod
                    state_data = json_mod.loads(state_file.read_text())
                    stored_outputs = state_data.get("output", {})
                    ab_pw = stored_outputs.get("attack_box_admin_password", {}).get("value")
                    if ab_pw:
                        return {'attackbox_password': ab_pw}
                    goad_pw = stored_outputs.get("goad_attackbox_password", {}).get("value")
                    if goad_pw:
                        return {'attackbox_password': goad_pw}
            except Exception:
                pass

            # Slow path: terraform output + EC2 password decryption (only if no cached password)
            try:
                service = get_service_for_project(project_name)
                service.init()
                service.ensure_workspace()
                tf_outputs = service.output()
                if tf_outputs.get("success"):
                    tf_out = tf_outputs.get("outputs", {})
                    ab_instance_id = tf_out.get("attack_box_instance_id", {}).get("value")
                    if ab_instance_id:
                        win_pwd = get_windows_password(ab_instance_id, service)
                        if win_pwd:
                            return {'attackbox_password': win_pwd}
                    goad_pwd = tf_out.get("goad_attackbox_password", {}).get("value")
                    if goad_pwd:
                        return {'attackbox_password': goad_pwd}
            except Exception:
                pass
            return {}

        # HIGH #9 fix (2026-05-28): also fetch the full `terraform output`
        # payload in parallel and fold it into the response under
        # `terraform_outputs`. The boto3 EC2 scan above only knows about
        # instances — it misses CloudFront distributions, ACM cert ARNs,
        # the Route53 zone id, GOAD lab creds, the deployment S3 bucket
        # name, and Secrets Manager ARNs. Downstream consumers can now
        # read either the legacy flat keys (jumpbox_public_ip, etc.) or
        # the structured terraform output map.
        def _fetch_terraform_outputs():
            try:
                tf_service = get_service_for_project(project_name)
                tf_service.ensure_workspace()
                tf_res = tf_service.output()
                if tf_res.get("success"):
                    return tf_res.get("outputs", {}) or {}
            except Exception as _e:
                try:
                    print(f"[deploy] /outputs terraform-fold-in failed: {_e}")
                except Exception:
                    pass
            return {}

        # Run DNS, password fetch, and terraform-output fold-in in parallel
        terraform_outputs = {}
        with ThreadPoolExecutor(max_workers=3) as executor:
            dns_future = executor.submit(_fetch_dns)
            pwd_future = executor.submit(_fetch_password)
            tf_future = executor.submit(_fetch_terraform_outputs)

            for future in as_completed([dns_future, pwd_future, tf_future], timeout=30):
                try:
                    res = future.result()
                    if future is tf_future:
                        terraform_outputs = res or {}
                    else:
                        outputs.update(res)
                except Exception:
                    pass

        return jsonify({
            "success": True,
            "outputs": outputs,
            "terraform_outputs": terraform_outputs,
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@bp.route('/sg-rules', methods=['GET'])
def get_sg_rules():
    """
    Get actual security group rules for a deployment.
    Returns a connection map: source_instance → destination_instance → [ports].
    Used by the topology graph for accurate edge labels.
    """
    try:
        import boto3

        project_name = request.args.get('project')
        if not project_name:
            return jsonify({"success": False, "error": "Project name required"}), 400

        config = _read_project_config(project_name)
        aws_region = config.get('aws_region', 'eu-central-1')

        ec2 = boto3.client('ec2', region_name=aws_region)

        # Get all instances for this project with their SGs
        response = ec2.describe_instances(
            Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
        )

        # Build instance → SG mapping and SG → role mapping
        sg_to_role = {}   # sg_id → role name (redirector, teamserver, etc.)
        sg_to_ip = {}     # sg_id → private IP
        all_sg_ids = set()

        for res in response.get('Reservations', []):
            for inst in res.get('Instances', []):
                tags = {t['Key']: t['Value'] for t in inst.get('Tags', [])}
                name = tags.get('Name', '').lower()
                role = tags.get('Role', '').lower()
                ip = inst.get('PrivateIpAddress', '')

                # Determine role from name/tags
                inst_role = 'unknown'
                if 'redirector' in name or 'proxy' in name:
                    inst_role = 'redirector'
                elif 'teamserver' in name or 'c2-team' in name or 'c2_team' in name:
                    inst_role = 'teamserver'
                elif 'attackbox' in name or 'attack' in name:
                    inst_role = 'attackbox'
                elif 'jumpbox' in name:
                    inst_role = 'jumpbox'
                elif 'dc0' in name:
                    inst_role = 'goad_vm'

                for sg in inst.get('SecurityGroups', []):
                    sg_id = sg['GroupId']
                    sg_to_role[sg_id] = inst_role
                    sg_to_ip[sg_id] = ip
                    all_sg_ids.add(sg_id)

        # Also include the dashboard SG if peering exists
        try:
            dashboard_sg_resp = ec2.describe_security_groups(
                Filters=[{'Name': 'tag:Name', 'Values': ['redteam-dashboard-sg']}]
            )
            for sg in dashboard_sg_resp.get('SecurityGroups', []):
                sg_to_role[sg['GroupId']] = 'dashboard'
                all_sg_ids.add(sg['GroupId'])
        except Exception:
            pass

        if not all_sg_ids:
            return jsonify({"success": True, "connections": []})

        # Get all inbound rules for all SGs
        rules_resp = ec2.describe_security_group_rules(
            Filters=[{'Name': 'group-id', 'Values': list(all_sg_ids)}]
        )

        # Build connection map
        connections = []
        for rule in rules_resp.get('SecurityGroupRules', []):
            if rule.get('IsEgress'):
                continue

            dest_sg = rule.get('GroupId')
            dest_role = sg_to_role.get(dest_sg, 'unknown')
            from_port = rule.get('FromPort')
            to_port = rule.get('ToPort')
            protocol = rule.get('IpProtocol', 'tcp')

            # Source is either a SG reference or a CIDR
            ref = rule.get('ReferencedGroupInfo', {})
            source_sg = ref.get('GroupId')
            source_cidr = rule.get('CidrIpv4')
            description = rule.get('Description', '')

            source_role = sg_to_role.get(source_sg, '') if source_sg else ''
            if source_cidr == '0.0.0.0/0':
                source_role = 'internet'

            port_str = str(from_port) if from_port == to_port else f"{from_port}-{to_port}"

            connections.append({
                'source_role': source_role,
                'source_sg': source_sg or source_cidr or '',
                'dest_role': dest_role,
                'dest_sg': dest_sg,
                'port': port_str,
                'protocol': protocol,
                'description': description,
            })

        return jsonify({"success": True, "connections": connections})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/ssl-status', methods=['GET'])
def get_ssl_status():
    """
    SSH into redirector(s) to fetch real-time SSL certificate status.
    Reads /opt/ssl-status.json and the last 10 lines of /var/log/ssl-auto-request.log
    from each redirector.
    """
    try:
        import subprocess
        import json as _json

        project_name = request.args.get('project')
        if not project_name:
            # Fall back to the global tfvars' project_name (legacy hosts)
            fallback_cfg = _read_project_config(None)
            project_name = fallback_cfg.get('project_name', '')

        if not project_name:
            return jsonify({"success": False, "error": "No project name"}), 400

        # Determine SSH private key path from stored public key comment
        ssh_key_path = None
        try:
            pub_key_file = Path(__file__).parent.parent / "data" / "ssh_public_key.txt"
            if pub_key_file.exists():
                pub_key = pub_key_file.read_text().strip()
                parts = pub_key.split(None, 2)
                key_type = parts[0] if len(parts) >= 1 else ''
                comment = parts[2].strip() if len(parts) >= 3 else ''

                if '/.ssh/' in comment:
                    # Comment contains a path like ~/.ssh/id_ed25519
                    ssh_key_path = comment.strip()
                elif '@' in comment and '.' in comment:
                    # Email-style comment — use default key names
                    if key_type == 'ssh-ed25519':
                        ssh_key_path = '~/.ssh/id_ed25519'
                    else:
                        ssh_key_path = '~/.ssh/id_rsa'
                elif comment and ' ' not in comment:
                    # Simple name like "mykey"
                    ssh_key_path = f'~/.ssh/{comment}'
                else:
                    ssh_key_path = '~/.ssh/id_ed25519' if key_type == 'ssh-ed25519' else '~/.ssh/id_rsa'
        except Exception:
            pass

        if not ssh_key_path:
            ssh_key_path = '~/.ssh/id_ed25519'

        expanded_key = os.path.expanduser(ssh_key_path)
        if not os.path.exists(expanded_key):
            # Try common alternatives
            for alt in ['~/.ssh/id_ed25519', '~/.ssh/id_rsa', '~/.ssh/id_ecdsa']:
                if os.path.exists(os.path.expanduser(alt)):
                    ssh_key_path = alt
                    expanded_key = os.path.expanduser(alt)
                    break

        # Get redirector public IPs from EC2 — per-project region lookup
        import boto3
        config = _read_project_config(project_name)
        aws_region = config.get('aws_region', 'eu-central-1')

        ec2 = boto3.client('ec2', region_name=aws_region)
        response = ec2.describe_instances(
            Filters=[
                {'Name': 'tag:Project', 'Values': [project_name]},
                {'Name': 'instance-state-name', 'Values': ['running']}
            ]
        )

        redirectors = []
        for reservation in response.get('Reservations', []):
            for instance in reservation.get('Instances', []):
                tags = {t['Key']: t['Value'] for t in instance.get('Tags', [])}
                role = tags.get('Role', '').lower()
                name = tags.get('Name', '').lower()
                if 'redirector' in role or 'redirector' in name:
                    public_ip = instance.get('PublicIpAddress')
                    if public_ip:
                        redirectors.append({
                            'ip': public_ip,
                            'name': tags.get('Name', 'Redirector'),
                            'instance_id': instance['InstanceId']
                        })

        if not redirectors:
            return jsonify({
                "success": True,
                "redirectors": [],
                "message": "No running redirectors found"
            })

        # SSH into each redirector and read status
        results = []
        for redir in redirectors:
            redir_result = {
                'ip': redir['ip'],
                'name': redir['name'],
                'ssh_status': 'unknown',
                'ssl_status': None,
                'log_tail': None,
                'error': None
            }

            # Remote command: read ssl-status.json + last 10 log lines
            remote_cmd = (
                "cat /opt/ssl-status.json 2>/dev/null || echo '{\"status\":\"no_status_file\"}'; "
                "echo '---SSL_LOG_TAIL---'; "
                "tail -10 /var/log/ssl-auto-request.log 2>/dev/null || echo 'No log file'"
            )

            ssh_cmd = [
                'ssh', '-o', 'StrictHostKeyChecking=no',
                '-o', 'BatchMode=yes',
                '-o', 'ConnectTimeout=10',
                '-i', expanded_key,
                f'ubuntu@{redir["ip"]}',
                remote_cmd
            ]

            try:
                result = subprocess.run(
                    ssh_cmd,
                    capture_output=True,
                    text=True,
                    timeout=20
                )

                if result.returncode == 0:
                    redir_result['ssh_status'] = 'connected'
                    raw = result.stdout.strip()

                    if '---SSL_LOG_TAIL---' in raw:
                        status_part, log_part = raw.split('---SSL_LOG_TAIL---', 1)
                        status_part = status_part.strip()
                        log_part = log_part.strip()
                    else:
                        status_part = raw
                        log_part = ''

                    # Parse JSON status
                    try:
                        redir_result['ssl_status'] = _json.loads(status_part)
                    except _json.JSONDecodeError:
                        redir_result['ssl_status'] = {'status': 'parse_error', 'raw': status_part[:500]}

                    redir_result['log_tail'] = log_part
                else:
                    redir_result['ssh_status'] = 'failed'
                    redir_result['error'] = result.stderr.strip()[:500] if result.stderr else 'SSH connection failed'

            except subprocess.TimeoutExpired:
                redir_result['ssh_status'] = 'timeout'
                redir_result['error'] = 'SSH connection timed out after 20 seconds'
            except Exception as e:
                redir_result['ssh_status'] = 'error'
                redir_result['error'] = str(e)[:500]

            results.append(redir_result)

        return jsonify({
            "success": True,
            "redirectors": results,
            "ssh_key_used": ssh_key_path
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@bp.route('/toggle-redirector', methods=['POST'])
def toggle_redirector():
    """
    Enable/disable a redirector by adding/removing its IP from the Route53 A record.
    When the blue team blocks a redirector IP, the operator can disable it here
    so DNS stops resolving to the burned IP — beacons use the remaining redirector(s).

    Body: { "ip": "35.x.x.x", "enabled": true/false, "project": "project-name" }
    """
    try:
        import boto3

        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No JSON body provided"}), 400

        target_ip = data.get('ip', '').strip()
        enabled = data.get('enabled', True)
        project_name = data.get('project', '').strip()

        if not target_ip or not project_name:
            return jsonify({"success": False, "error": "Missing 'ip' or 'project'"}), 400

        # Load the PROJECT's tfvars to get domain and region — without
        # this lookup the redirector toggle would target the global
        # terraform.tfvars' domain even though the operator is acting on
        # a per-project deployment.
        config = _read_project_config(project_name)
        aws_region = config.get('aws_region', 'eu-central-1')
        domain_name = config.get('primary_domain_name', '')
        c2_subdomain = config.get('c2_subdomain', 'api')

        if not domain_name:
            return jsonify({"success": False, "error": "No primary_domain_name configured"}), 400

        c2_fqdn = f"{c2_subdomain}.{domain_name}"

        # Find the hosted zone
        route53 = boto3.client('route53', region_name=aws_region)
        zones = route53.list_hosted_zones_by_name(DNSName=domain_name, MaxItems='1')
        zone_id = None
        for zone in zones.get('HostedZones', []):
            zone_name = zone['Name'].rstrip('.')
            if zone_name == domain_name:
                zone_id = zone['Id'].split('/')[-1]
                break

        if not zone_id:
            return jsonify({"success": False, "error": f"Hosted zone not found for {domain_name}"}), 404

        # Get current A records for the C2 FQDN
        records_resp = route53.list_resource_record_sets(
            HostedZoneId=zone_id,
            StartRecordName=c2_fqdn,
            StartRecordType='A',
            MaxItems='1'
        )

        current_ips = []
        current_ttl = 300
        for rr in records_resp.get('ResourceRecordSets', []):
            if rr['Name'].rstrip('.') == c2_fqdn and rr['Type'] == 'A':
                current_ips = [r['Value'] for r in rr.get('ResourceRecords', [])]
                current_ttl = rr.get('TTL', 300)
                break

        if not current_ips:
            return jsonify({"success": False, "error": f"No A records found for {c2_fqdn}"}), 404

        # Build new IP list
        if enabled:
            # Re-enable: add the IP back if not already present
            if target_ip not in current_ips:
                new_ips = current_ips + [target_ip]
            else:
                return jsonify({"success": True, "message": f"{target_ip} is already active", "active_ips": current_ips})
        else:
            # Disable: remove the IP
            if target_ip not in current_ips:
                return jsonify({"success": True, "message": f"{target_ip} is already removed from DNS", "active_ips": current_ips})
            new_ips = [ip for ip in current_ips if ip != target_ip]
            if not new_ips:
                return jsonify({"success": False, "error": "Cannot disable the last redirector — at least one must remain active"}), 400

        # Update the Route53 record
        route53.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch={
                'Comment': f'{"Enable" if enabled else "Disable"} redirector {target_ip} — operator toggle',
                'Changes': [{
                    'Action': 'UPSERT',
                    'ResourceRecordSet': {
                        'Name': c2_fqdn,
                        'Type': 'A',
                        'TTL': current_ttl,
                        'ResourceRecords': [{'Value': ip} for ip in new_ips]
                    }
                }]
            }
        )

        action = "enabled" if enabled else "disabled"
        return jsonify({
            "success": True,
            "message": f"Redirector {target_ip} {action} — DNS updated for {c2_fqdn}",
            "active_ips": new_ips,
            "disabled_ip": target_ip if not enabled else None,
            "domain": c2_fqdn,
            "ttl": current_ttl,
            "note": f"DNS change will propagate within {current_ttl} seconds (TTL)"
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/redirector-dns-status', methods=['GET'])
def get_redirector_dns_status():
    """
    Get current Route53 A record for the C2 domain — shows which redirector IPs are active in DNS.
    """
    try:
        import boto3

        project_name = request.args.get('project', '')
        if not project_name:
            return jsonify({"success": False, "error": "Missing 'project' parameter"}), 400

        # Per-project tfvars dictate the domain/region for the DNS lookup.
        config = _read_project_config(project_name)
        aws_region = config.get('aws_region', 'eu-central-1')
        domain_name = config.get('primary_domain_name', '')
        c2_subdomain = config.get('c2_subdomain', 'api')

        if not domain_name:
            return jsonify({"success": False, "error": "No domain configured"}), 400

        c2_fqdn = f"{c2_subdomain}.{domain_name}"

        route53 = boto3.client('route53', region_name=aws_region)
        zones = route53.list_hosted_zones_by_name(DNSName=domain_name, MaxItems='1')
        zone_id = None
        for zone in zones.get('HostedZones', []):
            if zone['Name'].rstrip('.') == domain_name:
                zone_id = zone['Id'].split('/')[-1]
                break

        if not zone_id:
            return jsonify({"success": False, "error": f"No hosted zone for {domain_name}"}), 404

        records_resp = route53.list_resource_record_sets(
            HostedZoneId=zone_id,
            StartRecordName=c2_fqdn,
            StartRecordType='A',
            MaxItems='1'
        )

        active_ips = []
        ttl = 300
        for rr in records_resp.get('ResourceRecordSets', []):
            if rr['Name'].rstrip('.') == c2_fqdn and rr['Type'] == 'A':
                active_ips = [r['Value'] for r in rr.get('ResourceRecords', [])]
                ttl = rr.get('TTL', 300)
                break

        return jsonify({
            "success": True,
            "domain": c2_fqdn,
            "active_ips": active_ips,
            "ttl": ttl
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/resources', methods=['GET'])
def get_all_resources():
    """
    Get a comprehensive list of ALL AWS resources across all regions.
    Queries every enabled region in the account without tag filtering.
    """
    try:
        import boto3
        from concurrent.futures import ThreadPoolExecutor, as_completed

        resources = []
        regions_with_resources = set()

        # Get account ID via STS
        sts = boto3.client('sts')
        try:
            caller_identity = sts.get_caller_identity()
            aws_account_id = caller_identity.get('Account', 'unknown')
            aws_user_arn = caller_identity.get('Arn', '')
        except Exception:
            aws_account_id = 'unknown'
            aws_user_arn = ''

        # Restricted to eu-central-1 only
        all_regions = ['eu-central-1']

        def _get_tag(tags, key, default=''):
            """Extract a tag value from a list of AWS tags."""
            return next((t['Value'] for t in (tags or []) if t['Key'] == key), default)

        def query_regional_resources(region):
            """Query all resources in a region — no tag filtering."""
            regional = []
            ec2 = boto3.client('ec2', region_name=region)

            # 1. EC2 Instances (exclude terminated)
            try:
                response = ec2.describe_instances(
                    Filters=[{'Name': 'instance-state-name', 'Values': ['running', 'stopped', 'pending', 'stopping']}]
                )
                for reservation in response.get('Reservations', []):
                    for inst in reservation.get('Instances', []):
                        tags = inst.get('Tags', [])
                        name = _get_tag(tags, 'Name', 'Unnamed')
                        role = _get_tag(tags, 'Role')
                        project = _get_tag(tags, 'Project')
                        regional.append({
                            'type': 'ec2',
                            'name': name,
                            'id': inst['InstanceId'],
                            'state': inst['State']['Name'],
                            'details': f"{inst['InstanceType']} | {role}" if role else inst['InstanceType'],
                            'project': project or '-',
                            'region': region
                        })
            except Exception as e:
                print(f"Error fetching EC2 in {region}: {e}")

            # 2. VPCs (exclude default VPC)
            try:
                response = ec2.describe_vpcs()
                for vpc in response.get('Vpcs', []):
                    if vpc.get('IsDefault'):
                        continue
                    tags = vpc.get('Tags', [])
                    regional.append({
                        'type': 'vpc',
                        'name': _get_tag(tags, 'Name', 'Unnamed VPC'),
                        'id': vpc['VpcId'],
                        'state': vpc['State'],
                        'details': vpc['CidrBlock'],
                        'project': _get_tag(tags, 'Project') or '-',
                        'region': region
                    })
            except Exception as e:
                print(f"Error fetching VPCs in {region}: {e}")

            # 3. Elastic IPs
            try:
                response = ec2.describe_addresses()
                for eip in response.get('Addresses', []):
                    tags = eip.get('Tags', [])
                    regional.append({
                        'type': 'eip',
                        'name': _get_tag(tags, 'Name', 'Unnamed EIP'),
                        'id': eip.get('AllocationId', 'N/A'),
                        'state': 'associated' if eip.get('InstanceId') else 'available',
                        'details': eip.get('PublicIp', 'N/A'),
                        'project': _get_tag(tags, 'Project') or '-',
                        'region': region
                    })
            except Exception as e:
                print(f"Error fetching EIPs in {region}: {e}")

            # 4. NAT Gateways (exclude deleted)
            try:
                response = ec2.describe_nat_gateways(
                    Filters=[{'Name': 'state', 'Values': ['available', 'pending', 'failed']}]
                )
                for nat in response.get('NatGateways', []):
                    tags = nat.get('Tags', [])
                    public_ip = nat.get('NatGatewayAddresses', [{}])[0].get('PublicIp', 'N/A')
                    regional.append({
                        'type': 'nat',
                        'name': _get_tag(tags, 'Name', 'Unnamed NAT'),
                        'id': nat['NatGatewayId'],
                        'state': nat['State'],
                        'details': f"Public IP: {public_ip}",
                        'project': _get_tag(tags, 'Project') or '-',
                        'region': region
                    })
            except Exception as e:
                print(f"Error fetching NAT Gateways in {region}: {e}")

            # 5. Key Pairs
            try:
                response = ec2.describe_key_pairs()
                for kp in response.get('KeyPairs', []):
                    tags = kp.get('Tags', [])
                    regional.append({
                        'type': 'keypair',
                        'name': kp['KeyName'],
                        'id': kp.get('KeyPairId', kp['KeyName']),
                        'state': 'available',
                        'details': f"Type: {kp.get('KeyType', 'rsa')}",
                        'project': _get_tag(tags, 'Project') or '-',
                        'region': region
                    })
            except Exception as e:
                print(f"Error fetching key pairs in {region}: {e}")

            return regional

        def query_global_resources():
            """Query global resources (S3, Route 53) — no tag filtering."""
            global_res = []

            # S3 Buckets
            try:
                s3 = boto3.client('s3')
                response = s3.list_buckets()
                for bucket in response.get('Buckets', []):
                    try:
                        loc = s3.get_bucket_location(Bucket=bucket['Name'])
                        bucket_region = loc.get('LocationConstraint') or 'eu-central-1'
                    except Exception:
                        bucket_region = 'unknown'
                    global_res.append({
                        'type': 's3',
                        'name': bucket['Name'],
                        'id': bucket['Name'],
                        'state': 'available',
                        'details': f"Created: {bucket['CreationDate'].strftime('%Y-%m-%d')}",
                        'project': '-',
                        'region': bucket_region
                    })
            except Exception as e:
                print(f"Error fetching S3 buckets: {e}")

            # Route 53 Hosted Zones
            try:
                route53 = boto3.client('route53')
                response = route53.list_hosted_zones()
                for zone in response.get('HostedZones', []):
                    zone_name = zone['Name'].rstrip('.')
                    global_res.append({
                        'type': 'route53-zone',
                        'name': zone_name,
                        'id': zone['Id'].split('/')[-1],
                        'state': 'active',
                        'details': f"Records: {zone.get('ResourceRecordSetCount', 0)}",
                        'project': '-',
                        'region': 'global'
                    })
            except Exception as e:
                print(f"Error fetching Route 53 zones: {e}")

            return global_res

        # Query all regions in parallel
        with ThreadPoolExecutor(max_workers=min(len(all_regions) + 1, 20)) as executor:
            futures = {executor.submit(query_regional_resources, r): r for r in all_regions}
            futures[executor.submit(query_global_resources)] = 'global'

            for future in as_completed(futures):
                try:
                    result = future.result()
                    resources.extend(result)
                    for r in result:
                        rgn = r.get('region', '')
                        if rgn and rgn != 'global':
                            regions_with_resources.add(rgn)
                except Exception as e:
                    print(f"Error in resource query thread: {e}")

        return jsonify({
            "success": True,
            "resources": resources,
            "total_count": len(resources),
            "regions_queried": sorted(all_regions),
            "regions_with_resources": sorted(regions_with_resources),
            "account_id": aws_account_id,
            "user_arn": aws_user_arn
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "resources": []
        }), 500


# =============================================================================
# DEPLOYMENT HISTORY ENDPOINT
# =============================================================================

@bp.route('/history', methods=['GET'])
def get_deployment_history():
    """Get deployment history"""
    try:
        history = load_deployment_history()
        return jsonify({
            "success": True,
            "history": history,
            "total_entries": len(history)
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "history": []
        }), 500


@bp.route('/history', methods=['DELETE'])
def clear_deployment_history():
    """Clear deployment history"""
    global _history_cache
    try:
        if HISTORY_FILE.exists():
            HISTORY_FILE.unlink()
        _history_cache = []  # Reset in-memory cache
        return jsonify({
            "success": True,
            "message": "Deployment history cleared"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# /history/add removed 2026-05-21 — no frontend or script caller.
# History entries are appended internally by add_history_entry() from
# run_deployment/run_destroy/run_purge — exposing a POST that lets any
# loopback caller manufacture arbitrary log lines was never used and
# made the audit trail easier to forge.
