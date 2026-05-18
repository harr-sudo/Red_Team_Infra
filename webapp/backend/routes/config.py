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
from webapp.backend.services import audit_service


def _audit_actor():
    op = getattr(g, "operator", None)
    return op.get("id") if op else "unknown"

bp = Blueprint('config', __name__)

# Paths
config_dir = project_root / "configs"
tfvars_file = config_dir / "terraform.tfvars"
tfvars_example = config_dir / "terraform.tfvars.example"

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
    """Get current configuration"""
    try:
        if tfvars_file.exists():
            config = ConfigParser.parse_tfvars(tfvars_file)
        else:
            # Return example config if actual config doesn't exist
            config = ConfigParser.parse_tfvars(tfvars_example)
        
        return jsonify({
            "success": True,
            "config": config,
            "file_exists": tfvars_file.exists()
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@bp.route('/', methods=['DELETE'])
def delete_config():
    """Delete the saved configuration file"""
    try:
        if tfvars_file.exists():
            tfvars_file.unlink()
            return jsonify({
                "success": True,
                "message": "Configuration file deleted successfully"
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
    """Update configuration"""
    try:
        data = request.get_json()
        if not data or 'config' not in data:
            return jsonify({
                "success": False,
                "error": "Configuration data required"
            }), 400
        
        config = data['config']
        
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
        
        # Ensure configs directory exists
        config_dir.mkdir(parents=True, exist_ok=True)
        
        # Write atomically (temp file + rename prevents partial writes on crash)
        import tempfile
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(config_dir), suffix='.tfvars.tmp')
        try:
            with os.fdopen(tmp_fd, 'w') as f:
                f.write(content)
            os.replace(tmp_path, str(tfvars_file))
        except Exception:
            os.unlink(tmp_path)
            raise
        
        project_name = (config or {}).get("project_name") if isinstance(config, dict) else None
        audit_service.write(
            _audit_actor(),
            "deploy.save_config",
            project=project_name,
        )
        return jsonify({
            "success": True,
            "message": "Configuration saved successfully",
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
    """Get configuration templates for different engagement types"""
    templates = {
        "adhoc": {
            "engagement_type": "adhoc",
            "c2_deployment_mode": "",
            "c2_server_count": 1,
            "c2_server_instance_type": "t3.medium"
        },
        "purple-team": {
            "engagement_type": "purple-team",
            "c2_deployment_mode": "",
            "c2_server_count": 2,
            "c2_server_instance_type": "t3.medium"
        },
        "full-red-team": {
            "engagement_type": "full-red-team",
            "c2_deployment_mode": "",
            "c2_server_count": 2,
            "c2_server_instance_type": "t3.medium"
        }
    }
    
    return jsonify({
        "success": True,
        "templates": templates
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
            return jsonify({
                "success": False,
                "error": gen.stderr.strip() or "Script failed",
                "results": results
            }), 500
        results["generate"] = gen.stdout.strip()
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "results": results}), 500

    return jsonify({"success": True, "results": results})

