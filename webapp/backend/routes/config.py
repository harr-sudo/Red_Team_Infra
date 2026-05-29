"""
Configuration API Routes
Handle configuration file management
"""

import subprocess
from flask import Blueprint, request, jsonify, g
from pathlib import Path
import os
import sys

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from webapp.backend.utils.config_parser import ConfigParser
from webapp.backend.utils.validators import ConfigValidator
from webapp.backend.utils.tfvars_path import (
    RESERVED_PROJECT_NAMES as _RESERVED_PROJECT_NAMES,
    resolve_tfvars_path as _shared_resolve_tfvars_path,
)
from webapp.backend.services import audit_service


def _audit_actor():
    op = getattr(g, "operator", None)
    return op.get("id") if op else "unknown"

bp = Blueprint('config', __name__)

# Paths
config_dir = project_root / "configs"
tfvars_file = config_dir / "terraform.tfvars"
tfvars_example = config_dir / "terraform.tfvars.example"


def _rel_to_project(p):
    """Display path relative to project root when possible — falls back to
    the absolute path (e.g. when tests redirect ``config_dir`` to a tmpdir)."""
    try:
        return str(p.relative_to(project_root))
    except (ValueError, AttributeError):
        return str(p)


def _resolve_tfvars_path(project_param):
    """Thin wrapper around the shared sanitizer that injects this route's
    current ``config_dir`` / ``tfvars_file`` so test monkeypatches still apply.
    See ``webapp.backend.utils.tfvars_path.resolve_tfvars_path``.
    """
    return _shared_resolve_tfvars_path(project_param, config_dir, tfvars_file)

# SSH public key file (shared with deploy.py)
SSH_KEY_FILE = Path(__file__).parent / ".." / "data" / "ssh_public_key.txt"

def get_user_public_key_for_tfvars() -> str:
    """
    Get the user's SSH public key for inclusion in terraform.tfvars.
    Returns empty string if not configured (Terraform will handle the fallback).
    """
    try:
        key_file = SSH_KEY_FILE.resolve()
        if key_file.exists():
            key_content = key_file.read_text().strip()
            if key_content:
                return key_content
    except Exception as e:
        print(f"Warning: Could not read SSH public key: {e}")
    return ""

@bp.route('/', methods=['GET'])
def get_config():
    """Get current configuration.

    Honors ``?project=<name>`` — if a per-project tfvars file exists at
    ``configs/<name>.tfvars`` it's loaded; otherwise the global tfvars is
    used (or the example file if even that's missing).
    """
    try:
        project_param = request.args.get("project")
        target = _resolve_tfvars_path(project_param)
        if target.exists():
            config = ConfigParser.parse_tfvars(target)
        elif tfvars_file.exists():
            config = ConfigParser.parse_tfvars(tfvars_file)
        else:
            config = ConfigParser.parse_tfvars(tfvars_example)

        return jsonify({
            "success": True,
            "config": config,
            "project": project_param or None,
            "tfvars_path": _rel_to_project(target) if target.exists() else None,
            "file_exists": target.exists()
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@bp.route('/', methods=['DELETE'])
def delete_config():
    """Delete the saved configuration file (per-project when ?project= is set)."""
    try:
        project_param = request.args.get("project")
        target = _resolve_tfvars_path(project_param)
        if target.exists():
            target.unlink()
            audit_service.write(
                _audit_actor(),
                "deploy.delete_config",
                project=project_param,
            )
            return jsonify({
                "success": True,
                "message": f"Configuration file deleted: {target.name}"
            })
        else:
            return jsonify({
                "success": True,
                "message": "No configuration file to delete"
            })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@bp.route('/', methods=['POST'])
def update_config():
    """Update configuration.

    Resolution precedence for the target tfvars path:
      1. ``?project=<name>`` query param (sanitized to ``configs/<name>.tfvars``)
      2. ``config.project_name`` from the request body
      3. Global ``configs/terraform.tfvars``
    """
    try:
        data = request.get_json()
        if not data or 'config' not in data:
            return jsonify({
                "success": False,
                "error": "Configuration data required"
            }), 400

        config = data['config']

        # ── Phase 4: demo-draft save (no persistence) ───────────────────
        # When the walkthrough flow is active the operator should still
        # get a real validation experience (so they see the same error
        # surfaces a real Configure would produce), but we MUST NOT write
        # configs/<project>.tfvars — that file would pollute the operator's
        # config directory and could be picked up by a subsequent real
        # deploy. Detected via either:
        #   * body.is_demo_draft=True (frontend flag)
        #   * ?project=demo-draft-* OR config.project_name=demo-draft-*
        _body_demo_flag = bool(data.get("is_demo_draft"))
        _query_project = (request.args.get("project") or "").strip()
        _body_project = ""
        if isinstance(config, dict):
            _body_project = (config.get("project_name") or "").strip()
        _is_demo_draft = (
            _body_demo_flag
            or _query_project.startswith("demo-draft-")
            or _body_project.startswith("demo-draft-")
        )
        if _is_demo_draft:
            # Run validation so the operator sees real errors if the form
            # is malformed — but never persist.
            is_valid, errors = ConfigValidator.validate_config(config)
            if not is_valid:
                return jsonify({
                    "success": False,
                    "error": "Validation failed",
                    "errors": errors,
                    "is_demo": True,
                }), 400
            return jsonify({
                "success": True,
                "is_demo": True,
                "message": "Demo configuration accepted (not persisted)",
                "tfvars_path": None,
                "ssh_key_included": False,
            })

        # 2026-05-23 — operator directive: all new infra is pinned to
        # eu-central-1. Force the region on save so the wizard, legacy form,
        # or any future caller can't accidentally write a different region
        # into configs/<project>.tfvars. CloudFront ACM lives in us-east-1
        # but it's provisioned by the domain_fronting module, not from
        # operator-supplied aws_region.
        if isinstance(config, dict):
            existing = (config.get("aws_region") or "").strip()
            if existing and existing != "eu-central-1":
                # Don't fail — silently coerce + flag in the response so the
                # UI can surface a notice. Failing would block tests + legacy
                # callers that still ship the field.
                config["_aws_region_coerced_from"] = existing
            config["aws_region"] = "eu-central-1"

        # Validate configuration
        is_valid, errors = ConfigValidator.validate_config(config)
        if not is_valid:
            return jsonify({
                "success": False,
                "error": "Validation failed",
                "errors": errors
            }), 400

        # Add user's SSH public key if available (for GOAD deployments)
        # This enables the new secure SSH key architecture
        user_public_key = get_user_public_key_for_tfvars()
        if user_public_key:
            config['user_public_key'] = user_public_key

        # Generate terraform.tfvars content
        content = ConfigParser.generate_tfvars(config)

        # Pick the on-disk target. URL param wins UNLESS it's a UI sentinel
        # (e.g. ``__draft__`` means "draft state, no committed name yet"),
        # in which case fall through to the body's project_name. Then the
        # global tfvars.
        project_param = request.args.get("project")
        body_project = (config or {}).get("project_name") if isinstance(config, dict) else None
        if project_param and project_param not in _RESERVED_PROJECT_NAMES:
            target = _resolve_tfvars_path(project_param)
        elif body_project:
            target = _resolve_tfvars_path(body_project)
        else:
            target = _resolve_tfvars_path(None)

        # Ensure configs directory exists
        config_dir.mkdir(parents=True, exist_ok=True)

        # Write atomically (temp file + rename prevents partial writes on crash)
        import tempfile
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(config_dir), suffix='.tfvars.tmp')
        try:
            with os.fdopen(tmp_fd, 'w') as f:
                f.write(content)
            os.replace(tmp_path, str(target))
        except Exception:
            os.unlink(tmp_path)
            raise

        audit_service.write(
            _audit_actor(),
            "deploy.save_config",
            project=project_param or body_project,
        )
        return jsonify({
            "success": True,
            "message": "Configuration saved successfully",
            "tfvars_path": _rel_to_project(target),
            "ssh_key_included": bool(user_public_key)
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@bp.route('/validate', methods=['POST'])
def validate_config():
    """Validate configuration without saving"""
    try:
        data = request.get_json()
        if not data or 'config' not in data:
            return jsonify({
                "success": False,
                "error": "Configuration data required"
            }), 400
        
        config = data['config']
        is_valid, errors = ConfigValidator.validate_config(config)
        
        return jsonify({
            "success": is_valid,
            "errors": errors if not is_valid else []
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@bp.route('/templates', methods=['GET'])
def get_templates():
    """Get configuration templates for different deployment types.

    2026-05-28 — Real-pipeline audit fix (HIGH #15): templates used to
    carry the legacy ``engagement_type`` field which the validator
    rejected — every template load produced an immediately-invalid
    config. Switched to ``deployment_type`` (the current canonical name)
    matching DEPLOYMENT_CONFIGS keys in the frontend.
    """
    templates = {
        "c2-adhoc": {
            "deployment_type": "c2-adhoc",
            "c2_server_count": 1,
            "c2_server_instance_type": "t3.medium",
        },
        "c2-purple": {
            "deployment_type": "c2-purple",
            "c2_server_count": 2,
            "c2_server_instance_type": "t3.medium",
        },
        "c2-full": {
            "deployment_type": "c2-full",
            "c2_server_count": 3,
            "c2_server_instance_type": "t3.medium",
        },
        # CCRTS-Lab template — a single, fully self-contained lab. No C2
        # integration, no combined mode, no size variants.
        "ccrts": {
            "deployment_type": "ccrts",
            "ccrts_vpc_cidr": "192.168.57.0/24",
            "project_name": "ccrts_dev_lab_01",
        },
    }

    return jsonify({
        "success": True,
        "templates": templates,
    })

@bp.route('/example', methods=['GET'])
def get_example():
    """Get example configuration"""
    try:
        if tfvars_example.exists():
            config = ConfigParser.parse_tfvars(tfvars_example)
            return jsonify({
                "success": True,
                "config": config
            })
        else:
            return jsonify({
                "success": False,
                "error": "Example configuration file not found"
            }), 404
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@bp.route('/public-ip', methods=['GET'])
def get_public_ip():
    """Get the operator's real public IP via server-side curl.

    This bypasses iCloud Private Relay / VPN split-tunnelling that would
    cause browser-based IP lookups to return a relay address instead of
    the real IP that AWS will see for SSH/RDP connections.
    """
    services = [
        ['curl', '-4', '-s', '--max-time', '5', 'https://api.ipify.org'],
        ['curl', '-4', '-s', '--max-time', '5', 'https://ifconfig.me'],
        ['curl', '-4', '-s', '--max-time', '5', 'https://checkip.amazonaws.com'],
    ]

    for cmd in services:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=6)
            ip = result.stdout.strip()
            if ip and len(ip) <= 45 and all(c in '0123456789.' for c in ip):
                return jsonify({"success": True, "ip": ip})
        except Exception:
            continue

    return jsonify({
        "success": False,
        "error": "Could not determine public IP from any service"
    }), 500


@bp.route('/update-elastic-rules', methods=['POST'])
def update_elastic_rules():
    """Pull latest Elastic detection rules and regenerate elastic-rules.js."""
    repo_dir = project_root / "Research" / "elastic-detection-rules"
    script = project_root / "scripts" / "utilities" / "update-elastic-rules.py"

    if not repo_dir.is_dir():
        return jsonify({
            "success": False,
            "error": "Elastic detection-rules repo not found. Run: git clone --depth 1 https://github.com/elastic/detection-rules.git Research/elastic-detection-rules"
        }), 404

    if not script.is_file():
        return jsonify({"success": False, "error": "update-elastic-rules.py not found"}), 404

    results = {"git_pull": None, "generate": None}

    # Step 1: git pull
    try:
        pull = subprocess.run(
            ["git", "-C", str(repo_dir), "pull", "--depth", "1"],
            capture_output=True, text=True, timeout=60
        )
        results["git_pull"] = pull.stdout.strip() or pull.stderr.strip()
    except Exception as e:
        results["git_pull"] = f"git pull failed: {e}"

    # Step 2: regenerate JS
    try:
        gen = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True, text=True, timeout=120,
            cwd=str(project_root)
        )
        if gen.returncode != 0:
            audit_service.write(
                _audit_actor(),
                "config.update_elastic_rules",
                details={"status": "failed", "error": (gen.stderr or "").strip()[:500]},
            )
            return jsonify({
                "success": False,
                "error": gen.stderr.strip() or "Script failed",
                "results": results
            }), 500
        results["generate"] = gen.stdout.strip()
    except Exception as e:
        audit_service.write(
            _audit_actor(),
            "config.update_elastic_rules",
            details={"status": "error", "error": str(e)[:500]},
        )
        return jsonify({"success": False, "error": str(e), "results": results}), 500

    audit_service.write(
        _audit_actor(),
        "config.update_elastic_rules",
        details={"status": "ok"},
    )
    return jsonify({"success": True, "results": results})

