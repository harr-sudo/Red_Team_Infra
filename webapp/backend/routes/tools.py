"""
Tools Upload API Routes
Upload files to the attack box via SCP through the bastion host.
"""

from flask import Blueprint, request, jsonify
from pathlib import Path
import os
import sys
import threading
import time
import subprocess
import json
import uuid
import re
from werkzeug.utils import secure_filename

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from webapp.backend.services.terraform_service import get_terraform_service

bp = Blueprint('tools', __name__)

# Staging directory for uploaded files
TOOLS_UPLOAD_FOLDER = Path(__file__).parent.parent / "uploads_tools"
TOOLS_UPLOAD_FOLDER.mkdir(exist_ok=True)

MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB

# Preset destinations on the attack box
PRESET_DESTINATIONS = {
    'outflank': 'C:\\Outflank\\',
    'tools': 'C:\\Tools\\',
}

# Deployment state directory (shared with deploy.py)
STATE_DIR = project_root / "logs" / "deployment_state"

# Transfer state tracking
transfer_states = {}

# Projects cache — avoids running `terraform workspace list` on every page load
_projects_cache = {"data": None, "fetched_at": 0}
_PROJECTS_CACHE_TTL = 300  # 5 minutes


# =============================================================================
# HELPERS
# =============================================================================

def _get_file_info(filepath):
    """Get file metadata."""
    if not filepath.exists():
        return None
    stat = filepath.stat()
    return {
        "filename": filepath.name,
        "size": stat.st_size,
        "size_mb": round(stat.st_size / (1024 * 1024), 2),
        "modified": stat.st_mtime,
    }


def _resolve_ssh_key_path():
    """Resolve the SSH private key path from the stored public key comment.

    Replicates the pattern from deploy.py:4504-4541.
    """
    ssh_key_path = None
    try:
        pub_key_file = Path(__file__).parent.parent / "data" / "ssh_public_key.txt"
        if pub_key_file.exists():
            pub_key = pub_key_file.read_text().strip()
            parts = pub_key.split(None, 2)
            key_type = parts[0] if len(parts) >= 1 else ''
            comment = parts[2].strip() if len(parts) >= 3 else ''

            if '/.ssh/' in comment:
                ssh_key_path = comment.strip()
            elif '@' in comment and '.' in comment:
                ssh_key_path = '~/.ssh/id_ed25519' if key_type == 'ssh-ed25519' else '~/.ssh/id_rsa'
            elif comment and ' ' not in comment:
                ssh_key_path = f'~/.ssh/{comment}'
            else:
                ssh_key_path = '~/.ssh/id_ed25519' if key_type == 'ssh-ed25519' else '~/.ssh/id_rsa'
    except Exception:
        pass

    if not ssh_key_path:
        ssh_key_path = '~/.ssh/id_ed25519'

    expanded_key = os.path.expanduser(ssh_key_path)
    if not os.path.exists(expanded_key):
        for alt in ['~/.ssh/id_ed25519', '~/.ssh/id_rsa', '~/.ssh/id_ecdsa']:
            if os.path.exists(os.path.expanduser(alt)):
                ssh_key_path = alt
                expanded_key = os.path.expanduser(alt)
                break

    return ssh_key_path, os.path.exists(expanded_key)


def _scan_active_projects():
    """Scan Terraform workspaces for currently active deployments.

    Uses workspace list as the source of truth — destroyed deployments
    have their workspace deleted, so they won't appear here.
    """
    projects = []

    # Get active Terraform workspaces
    try:
        service = get_terraform_service(project_root)
        service.init()
        ws_result = service.workspace_list()
        active_workspaces = set(ws_result.get("workspaces", [])) - {"default"}
    except Exception:
        active_workspaces = set()

    if not active_workspaces:
        return projects

    # Enrich with deployment metadata from in-memory state or persisted files
    deploy_states = {}
    try:
        from webapp.backend.routes.deploy import deployment_states as mem_states
        deploy_states = dict(mem_states)
    except ImportError:
        pass

    for ws_name in sorted(active_workspaces):
        dep_type = "unknown"
        completed_at = None

        # Check in-memory state first
        if ws_name in deploy_states:
            state = deploy_states[ws_name]
            dep_type = state.get("deployment_type", dep_type)
            completed_at = state.get("completed_at")
        else:
            # Fall back to persisted state file
            state_file = STATE_DIR / f"{ws_name}.state.json"
            if state_file.exists():
                try:
                    with open(state_file, 'r') as f:
                        state = json.load(f)
                    dep_type = state.get("deployment_type", dep_type)
                    completed_at = state.get("completed_at")
                except (json.JSONDecodeError, IOError):
                    pass

        projects.append({
            "name": ws_name,
            "deployment_type": dep_type,
            "completed_at": completed_at,
        })

    return projects


def _validate_destination(path):
    """Validate a Windows destination path. Returns (valid, error_msg)."""
    if not path:
        return False, "Destination path is required"
    # Must start with drive letter
    if not re.match(r'^[A-Za-z]:\\', path):
        return False, "Path must start with a drive letter (e.g. C:\\)"
    # No path traversal
    if '..' in path:
        return False, "Path must not contain '..'"
    # No shell metacharacters
    dangerous = set(';|&`$')
    if any(c in path for c in dangerous):
        return False, "Path contains invalid characters"
    # Must end with backslash (directory)
    if not path.endswith('\\'):
        path += '\\'
    return True, path


# =============================================================================
# ENDPOINTS
# =============================================================================

# /api/tools/projects removed 2026-05-21 — no live frontend caller
# (only referenced from app.js.bak). The Operations → Payloads UI gets
# project options from /api/deploy/active instead, which is the
# canonical source of "deployments that exist on this host".


@bp.route('/upload', methods=['POST'])
def upload_file():
    """Upload a file to the staging directory."""
    try:
        if 'file' not in request.files:
            return jsonify({"success": False, "error": "No file provided"}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({"success": False, "error": "No file selected"}), 400

        # Check file size
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)

        if file_size > MAX_FILE_SIZE:
            return jsonify({
                "success": False,
                "error": f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
            }), 400

        filename = secure_filename(file.filename)
        filepath = TOOLS_UPLOAD_FOLDER / filename
        file.save(str(filepath))

        return jsonify({
            "success": True,
            "message": "File uploaded successfully",
            "file": _get_file_info(filepath)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/staged', methods=['GET'])
def list_staged():
    """List files in the staging directory."""
    try:
        files = []
        for f in sorted(TOOLS_UPLOAD_FOLDER.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if f.is_file() and f.name != '.gitkeep':
                files.append(_get_file_info(f))

        total_size = sum(f["size"] for f in files)
        return jsonify({
            "success": True,
            "files": files,
            "count": len(files),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/staged', methods=['DELETE'])
def delete_staged():
    """Delete a staged file or all staged files."""
    try:
        data = request.get_json() or {}
        filename = data.get('filename')

        if not filename:
            return jsonify({"success": False, "error": "filename is required"}), 400

        if filename == 'all':
            count = 0
            for f in TOOLS_UPLOAD_FOLDER.iterdir():
                if f.is_file() and f.name != '.gitkeep':
                    f.unlink()
                    count += 1
            return jsonify({"success": True, "message": f"Deleted {count} file(s)"})

        filepath = TOOLS_UPLOAD_FOLDER / secure_filename(filename)
        if not filepath.exists():
            return jsonify({"success": False, "error": "File not found"}), 404

        filepath.unlink()
        return jsonify({"success": True, "message": "File deleted"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/connection-info', methods=['GET'])
def connection_info():
    """Get connection details (bastion IP, attack box IP, SSH key) for a project."""
    try:
        project_name = request.args.get('project')
        if not project_name:
            return jsonify({"success": False, "error": "project parameter is required"}), 400

        # Demo bypass — no AWS / no terraform output. Return synthetic
        # connection metadata so the Payloads sub-pill paints with the
        # same shape it would for a real c2-adhoc deployment. See
        # demo_data_service.deployment_state() for the canonical IPs.
        try:
            from webapp.backend.services import demo_data_service
            if demo_data_service.is_demo_project(project_name):
                demo_data_service.seed_demo_audit_entries()
                return jsonify({
                    "success": True,
                    "is_demo": True,
                    "has_attack_box": True,
                    "has_hop_host": True,
                    "bastion_ip": "203.0.113.10",
                    "bastion_type": "bastion",
                    "attack_box_ip": "10.0.10.30",
                    "attack_box_private_ip": "10.0.10.30",
                    "attack_box_instance_id": "i-0demoattack01",
                    "attack_box_password": "demo-attack-do-not-use",
                    "s3_bucket": "demo-payloads-bucket",
                    "transfer_method": "s3",
                    "ready": True,
                })
        except Exception:
            # Demo branch is best-effort — never break the real path.
            pass

        # Get terraform outputs for this project
        service = get_terraform_service(project_root, project_name)
        service.init()
        service.ensure_workspace()

        output_result = service.output()
        if not output_result.get("success"):
            return jsonify({
                "success": True,
                "has_attack_box": False,
                "message": "No active infrastructure found for this project"
            })

        outputs = output_result.get("outputs", {})
        bastion_ip = outputs.get("bastion_public_ip", {}).get("value")
        attack_box_ip = outputs.get("attack_box_private_ip", {}).get("value")

        # Also check GOAD jumpbox as alternative hop host
        jumpbox_ip = outputs.get("goad_jumpbox_public_ip", {}).get("value")

        # Determine hop host: prefer bastion, fall back to jumpbox
        hop_ip = bastion_ip or jumpbox_ip
        hop_type = "bastion" if bastion_ip else ("jumpbox" if jumpbox_ip else None)

        if not attack_box_ip:
            return jsonify({
                "success": True,
                "has_attack_box": False,
                "message": "This deployment does not have an attack box"
            })

        # S3 bucket and instance ID for S3-based transfer
        s3_bucket = outputs.get("cs_storage_bucket", {}).get("value")
        attack_box_instance_id = outputs.get("attack_box_instance_id", {}).get("value")

        return jsonify({
            "success": True,
            "has_attack_box": True,
            "has_hop_host": True,  # kept for backward compat
            "bastion_ip": hop_ip,
            "bastion_type": hop_type,
            "attack_box_ip": attack_box_ip,
            "attack_box_instance_id": attack_box_instance_id,
            "s3_bucket": s3_bucket,
            "transfer_method": "s3",
            "ready": bool(s3_bucket and attack_box_instance_id),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/transfer', methods=['POST'])
def start_transfer():
    """Start an SCP transfer of staged files to the attack box."""
    try:
        data = request.get_json() or {}
        files = data.get('files', [])
        destination = data.get('destination', '')
        project = data.get('project', '')

        if not files:
            return jsonify({"success": False, "error": "No files specified"}), 400
        if not project:
            return jsonify({"success": False, "error": "No project specified"}), 400

        # Demo bypass — synthetic transfer that never touches S3 / SSM.
        # Returns a single-shot success payload so the UI's progress
        # overlay resolves cleanly. We do NOT register a transfer_state
        # entry because there's nothing to poll for the demo.
        try:
            from webapp.backend.services import demo_data_service
            if demo_data_service.is_demo_project(project):
                demo_data_service.seed_demo_audit_entries()
                from datetime import datetime as _dt, timezone as _tz
                names = ", ".join(files) if isinstance(files, list) else str(files)
                # Mimic the validated destination path (Windows-style).
                dest = destination if destination else "C:\\demo-payloads\\"
                if not dest.endswith("\\"):
                    dest += "\\"
                first = files[0] if isinstance(files, list) and files else "payload"
                return jsonify({
                    "success": True,
                    "is_demo": True,
                    "message": f"Transferred {names} to demo attack box (synthetic)",
                    "target_path": f"C:/demo-payloads/{first}",
                    "destination": dest,
                    "uploaded_at": _dt.now(_tz.utc).isoformat().replace("+00:00", "Z"),
                })
        except Exception:
            pass

        # Validate destination
        valid, result = _validate_destination(destination)
        if not valid:
            return jsonify({"success": False, "error": result}), 400
        destination = result  # cleaned path

        # Check no transfer already running for this project
        for tid, state in transfer_states.items():
            if state.get("project") == project and state.get("status") == "running":
                return jsonify({
                    "success": False,
                    "error": "A transfer is already running for this project"
                }), 409

        # Verify all files exist
        missing = [f for f in files if not (TOOLS_UPLOAD_FOLDER / secure_filename(f)).exists()]
        if missing:
            return jsonify({"success": False, "error": f"Files not found: {', '.join(missing)}"}), 404

        # Get connection details
        service = get_terraform_service(project_root, project)
        service.init()
        service.ensure_workspace()
        output_result = service.output()
        outputs = output_result.get("outputs", {})

        s3_bucket = outputs.get("cs_storage_bucket", {}).get("value")
        attack_box_id = outputs.get("attack_box_instance_id", {}).get("value")
        attack_box_ip = outputs.get("attack_box_private_ip", {}).get("value")

        if not s3_bucket:
            return jsonify({"success": False, "error": "Cannot resolve S3 bucket from deployment outputs"}), 400

        # Per-project tfvars: the transfer is scoped to the project we're
        # talking to, so read region from configs/<project>.tfvars first.
        from webapp.backend.utils.config_parser import ConfigParser
        from webapp.backend.utils.tfvars_path import resolve_tfvars_path
        config_dir = project_root / "configs"
        default_tfvars = config_dir / "terraform.tfvars"
        tfvars_file = resolve_tfvars_path(project, config_dir, default_tfvars)
        if not tfvars_file.exists():
            tfvars_file = default_tfvars
        config = ConfigParser.parse_tfvars(tfvars_file) if tfvars_file.exists() else {}
        aws_region = config.get('aws_region', 'eu-central-1')

        # Resolve attack box instance ID for SSM (if not in outputs, find by IP)
        if not attack_box_id and attack_box_ip:
            try:
                ec2_result = subprocess.run(
                    ['aws', 'ec2', 'describe-instances', '--region', aws_region,
                     '--filters', f'Name=private-ip-address,Values={attack_box_ip}',
                     'Name=instance-state-name,Values=running',
                     '--query', 'Reservations[0].Instances[0].InstanceId', '--output', 'text'],
                    capture_output=True, text=True, timeout=15
                )
                if ec2_result.returncode == 0 and ec2_result.stdout.strip() != 'None':
                    attack_box_id = ec2_result.stdout.strip()
            except Exception:
                pass

        if not attack_box_id:
            return jsonify({"success": False, "error": "Cannot resolve attack box instance ID for SSM"}), 400

        # Create transfer state
        transfer_id = str(uuid.uuid4())[:8]
        transfer_states[transfer_id] = {
            "id": transfer_id,
            "project": project,
            "status": "starting",
            "files": files,
            "destination": destination,
            "progress": {"total": len(files), "completed": 0, "current": None},
            "logs": [],
            "errors": [],
            "started_at": time.time(),
            "completed_at": None,
        }

        # Launch background thread — S3 transfer (upload to S3, pull on attack box via SSM)
        thread = threading.Thread(
            target=_run_transfer,
            args=(transfer_id, files, destination, s3_bucket, attack_box_id, aws_region),
            daemon=True,
        )
        thread.start()

        return jsonify({
            "success": True,
            "transfer_id": transfer_id,
            "message": f"Transfer started: {len(files)} file(s) → {destination}"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# =============================================================================
# AGGREGATE PAYLOAD HISTORY — used by Operations → Payloads "All deployments"
# (2026-05-19). Walks every active deployment + every recorded transfer to
# render a read-only history listing for the fleet. Generating new payloads
# is gated to single-deployment mode in the UI.
# =============================================================================

@bp.route('/payloads/all', methods=['GET'])
def list_all_payloads():
    """Aggregate payload history across every active deployment.

    Source of truth for the listing is the in-memory `transfer_states` dict
    (transfers initiated since the dashboard last started) PLUS the local
    staging directory contents (operator-uploaded artifacts that have not
    yet been transferred). The listing is read-only — the UI hides the
    generator form when the top-bar selector is on `__all__`.

    Response shape:
    ```
    {
      "success": true,
      "payloads": [
        {
          "name": "loader.exe",
          "type": "exe",
          "deployment": "c2_adhoc_dev",
          "generated_by": "alice",
          "generated_at": 1716100000.0,
          "status": "success",
          "size_mb": 1.4,
          "download": null
        }, ...
      ],
      "errors": [
        { "deployment": "<staging>", "error": "could not read staging" }
      ]
    }
    ```

    Errors are non-fatal — partial results are returned even if some
    deployments cannot be queried.
    """
    payloads = []
    errors = []

    # 1) In-flight + completed transfer history (per-deployment).
    try:
        for tid, state in list(transfer_states.items()):
            project = state.get("project") or "—"
            files = state.get("files") or []
            started_at = state.get("started_at")
            completed_at = state.get("completed_at") or started_at
            status = state.get("status") or "unknown"
            generated_by = state.get("operator") or state.get("generated_by") or "—"
            for fname in files:
                # Infer payload type from the extension. The Tools Upload
                # flow accepts any file (exe / dll / raw / zip / py / etc.) —
                # we surface the bare extension so operators can scan the
                # column without having to read each filename.
                ptype = "raw"
                if isinstance(fname, str) and "." in fname:
                    ptype = fname.rsplit(".", 1)[-1].lower()
                size_mb = None
                try:
                    staged = TOOLS_UPLOAD_FOLDER / secure_filename(fname)
                    if staged.exists():
                        size_mb = round(staged.stat().st_size / (1024 * 1024), 2)
                except Exception:
                    pass
                payloads.append({
                    "name": fname,
                    "type": ptype,
                    "deployment": project,
                    "generated_by": generated_by,
                    "generated_at": completed_at,
                    "status": status,
                    "size_mb": size_mb,
                    "download": None,
                    "transfer_id": tid,
                })
    except Exception as e:
        errors.append({"deployment": "<transfers>", "error": str(e)})

    # 2) Staged files that have not yet been transferred — they belong to
    #    no specific deployment yet, so we mark them as "(staged)".
    try:
        seen_names = {p["name"] for p in payloads}
        for f in TOOLS_UPLOAD_FOLDER.iterdir():
            if not f.is_file() or f.name == ".gitkeep":
                continue
            if f.name in seen_names:
                continue
            ptype = "raw"
            if "." in f.name:
                ptype = f.name.rsplit(".", 1)[-1].lower()
            payloads.append({
                "name": f.name,
                "type": ptype,
                "deployment": "(staged)",
                "generated_by": "—",
                "generated_at": f.stat().st_mtime,
                "status": "staged",
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "download": None,
                "transfer_id": None,
            })
    except Exception as e:
        errors.append({"deployment": "<staging>", "error": str(e)})

    # Newest first.
    payloads.sort(key=lambda p: p.get("generated_at") or 0, reverse=True)

    return jsonify({
        "success": True,
        "payloads": payloads,
        "errors": errors,
    })


@bp.route('/transfer/<transfer_id>', methods=['GET'])
def get_transfer_status(transfer_id):
    """Get the status of an ongoing or completed transfer."""
    state = transfer_states.get(transfer_id)
    if not state:
        return jsonify({"success": False, "error": "Transfer not found"}), 404

    elapsed = None
    if state.get("started_at"):
        end = state.get("completed_at") or time.time()
        elapsed = round(end - state["started_at"], 1)

    return jsonify({
        "success": True,
        "transfer": {
            "id": state["id"],
            "status": state["status"],
            "progress": state["progress"],
            "logs": state["logs"],
            "errors": state["errors"],
            "elapsed_seconds": elapsed,
        }
    })


# =============================================================================
# SCP TRANSFER LOGIC (runs in background thread)
# =============================================================================

def _run_transfer(transfer_id, files, destination, s3_bucket, attack_box_id, aws_region):
    """Transfer files via S3: upload from local to S3, then pull on attack box via SSM.

    Flow: Local staging → S3 bucket (tools-transfer/ prefix) → SSM aws s3 sync on attack box
    No SSH needed on the Windows attack box.
    """
    state = transfer_states[transfer_id]
    state["status"] = "running"

    s3_prefix = "tools-transfer"
    total = len(files)
    completed = 0

    # Step 1: Upload files to S3
    state["logs"].append(f"Starting transfer of {total} file(s) via S3...")
    state["logs"].append(f"S3 bucket: {s3_bucket}")

    for filename in files:
        safe_name = secure_filename(filename)
        filepath = TOOLS_UPLOAD_FOLDER / safe_name
        if not filepath.exists():
            state["logs"].append(f"SKIP {filename} — not found in staging")
            continue

        state["progress"]["current"] = filename
        state["logs"].append(f"[{completed + 1}/{total}] Uploading {filename} to S3...")

        try:
            result = subprocess.run(
                ['aws', 's3', 'cp', str(filepath),
                 f's3://{s3_bucket}/{s3_prefix}/{safe_name}',
                 '--region', aws_region],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode == 0:
                completed += 1
                state["logs"].append(f"OK {filename} → S3")
            else:
                err = result.stderr.strip()
                state["logs"].append(f"FAIL {filename}: {err}")
                state["errors"].append({"file": filename, "error": err})
        except subprocess.TimeoutExpired:
            state["logs"].append(f"TIMEOUT {filename}")
            state["errors"].append({"file": filename, "error": "S3 upload timed out"})
        except Exception as e:
            state["logs"].append(f"ERROR {filename}: {str(e)}")
            state["errors"].append({"file": filename, "error": str(e)})

        state["progress"]["completed"] = completed

    if completed == 0:
        state["status"] = "error"
        state["logs"].append("All S3 uploads failed. Aborting.")
        state["completed_at"] = time.time()
        return

    # Step 2: Pull files from S3 to attack box via SSM
    state["logs"].append(f"Downloading {completed} file(s) from S3 to attack box ({destination})...")
    win_dest = destination.rstrip("\\")

    ssm_cmd = (
        f'mkdir "{win_dest}" -Force | Out-Null; '
        f'aws s3 sync s3://{s3_bucket}/{s3_prefix}/ "{win_dest}\\\\" --region {aws_region}; '
        f'$count = (Get-ChildItem "{win_dest}" -File).Count; '
        f'Write-Output "Downloaded $count file(s) to {win_dest}"'
    )

    try:
        result = subprocess.run(
            ['aws', 'ssm', 'send-command',
             '--region', aws_region,
             '--instance-ids', attack_box_id,
             '--document-name', 'AWS-RunPowerShellScript',
             '--parameters', json.dumps({"commands": [ssm_cmd]}),
             '--query', 'Command.CommandId',
             '--output', 'text'],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            state["logs"].append(f"FAIL SSM command: {result.stderr.strip()}")
            state["errors"].append({"file": "SSM", "error": result.stderr.strip()})
        else:
            ssm_cmd_id = result.stdout.strip()
            state["logs"].append(f"SSM command sent: {ssm_cmd_id}")

            # Poll for SSM completion
            import time as _time
            for attempt in range(20):
                _time.sleep(5)
                poll = subprocess.run(
                    ['aws', 'ssm', 'get-command-invocation',
                     '--region', aws_region,
                     '--command-id', ssm_cmd_id,
                     '--instance-id', attack_box_id,
                     '--query', '[Status,StandardOutputContent,StandardErrorContent]',
                     '--output', 'text'],
                    capture_output=True, text=True, timeout=15
                )
                if poll.returncode != 0:
                    continue

                parts = poll.stdout.strip().split('\t')
                ssm_status = parts[0] if parts else ''
                ssm_output = parts[1] if len(parts) > 1 else ''
                ssm_error = parts[2] if len(parts) > 2 else ''

                if ssm_status == 'Success':
                    state["logs"].append(f"OK {ssm_output.strip()}")
                    break
                elif ssm_status in ('Failed', 'TimedOut', 'Cancelled'):
                    state["logs"].append(f"FAIL SSM: {ssm_status} — {ssm_error.strip()}")
                    state["errors"].append({"file": "SSM", "error": ssm_error.strip()})
                    break
                # InProgress — keep polling
            else:
                state["logs"].append("Warning: SSM command still running after 100s — files may still be downloading")

    except Exception as e:
        state["logs"].append(f"ERROR SSM: {str(e)}")
        state["errors"].append({"file": "SSM", "error": str(e)})

    # Step 3: Clean up S3 transfer prefix
    try:
        subprocess.run(
            ['aws', 's3', 'rm', f's3://{s3_bucket}/{s3_prefix}/',
             '--recursive', '--region', aws_region],
            capture_output=True, text=True, timeout=30
        )
        state["logs"].append("Cleaned up S3 transfer staging area.")
    except Exception:
        pass

    # Done
    state["progress"]["current"] = None
    state["completed_at"] = time.time()

    if not state["errors"]:
        state["status"] = "success"
        state["logs"].append(f"All {completed}/{total} file(s) transferred successfully.")
    elif completed > 0:
        state["status"] = "completed_with_errors"
        state["logs"].append(f"Completed with errors: {completed}/{total} uploaded to S3.")
    else:
        state["status"] = "error"
        state["logs"].append(f"All transfers failed.")
