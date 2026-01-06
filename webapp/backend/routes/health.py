"""
Health Check API Routes
Handle health checks and validation
"""

from flask import Blueprint, jsonify
from pathlib import Path
import sys
import subprocess
import json

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from webapp.backend.services.aws_permissions_service import AWSPermissionsService

bp = Blueprint('health', __name__)

@bp.route('/check', methods=['POST'])
def run_health_check():
    """Run infrastructure health check"""
    try:
        health_check_script = project_root / "scripts" / "utilities" / "health-check.sh"
        
        if not health_check_script.exists():
            return jsonify({
                "success": False,
                "error": "Health check script not found"
            }), 404
        
        # Run health check script
        result = subprocess.run(
            ["bash", str(health_check_script)],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=60
        )
        
        return jsonify({
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode
        })
    except subprocess.TimeoutExpired:
        return jsonify({
            "success": False,
            "error": "Health check timed out"
        }), 500
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@bp.route('/prerequisites', methods=['GET'])
def check_prerequisites():
    """Check if all prerequisites are installed"""
    prerequisites = {
        "aws": {"installed": False, "version": ""},
        "terraform": {"installed": False, "version": ""},
        "ansible": {"installed": False, "version": ""},
        "python3": {"installed": False, "version": ""},
        "jq": {"installed": False, "version": ""}
    }
    
    all_installed = True
    
    for tool, info in prerequisites.items():
        try:
            if tool == "python3":
                result = subprocess.run(
                    ["python3", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
            else:
                result = subprocess.run(
                    [tool, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
            
            if result.returncode == 0:
                info["installed"] = True
                info["version"] = result.stdout.strip()
            else:
                all_installed = False
        except (FileNotFoundError, subprocess.TimeoutExpired):
            all_installed = False
    
    return jsonify({
        "success": True,
        "all_installed": all_installed,
        "prerequisites": prerequisites
    })

@bp.route('/aws', methods=['GET'])
def check_aws():
    """Check AWS credentials and connectivity"""
    try:
        result = subprocess.run(
            ["aws", "sts", "get-caller-identity"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            try:
                identity = json.loads(result.stdout)
                return jsonify({
                    "success": True,
                    "authenticated": True,
                    "account": identity.get("Account", ""),
                    "user": identity.get("Arn", "")
                })
            except:
                return jsonify({
                    "success": True,
                    "authenticated": True,
                    "raw_output": result.stdout
                })
        else:
            return jsonify({
                "success": False,
                "authenticated": False,
                "error": result.stderr
            })
    except FileNotFoundError:
        return jsonify({
            "success": False,
            "authenticated": False,
            "error": "AWS CLI not found"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "authenticated": False,
            "error": str(e)
        })

@bp.route('/permissions', methods=['GET'])
def check_permissions():
    """Check if AWS account has required permissions for deployment"""
    try:
        # First verify AWS connectivity
        result = subprocess.run(
            ["aws", "sts", "get-caller-identity"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return jsonify({
                "success": False,
                "error": "AWS credentials not configured or invalid",
                "stderr": result.stderr
            }), 401
        
        # Try policy simulation first (more accurate)
        simulation_result = AWSPermissionsService.check_using_policy_simulation()
        
        if simulation_result.get("success"):
            return jsonify({
                "success": True,
                "method": "policy_simulation",
                "overall_status": simulation_result.get("overall", "unknown"),
                "missing_permissions": simulation_result.get("missing_permissions", []),
                "available_permissions": simulation_result.get("available_permissions", []),
                "permissions": simulation_result.get("permissions", {}),
                "categories": {
                    "EC2": {
                        "status": "checking",
                        "required": len([p for p in AWSPermissionsService.REQUIRED_PERMISSIONS.get("EC2", []) if p in simulation_result.get("missing_permissions", [])]) == 0
                    },
                    "IAM": {
                        "status": "checking",
                        "required": len([p for p in AWSPermissionsService.REQUIRED_PERMISSIONS.get("IAM", []) if p in simulation_result.get("missing_permissions", [])]) == 0
                    },
                    "S3": {
                        "status": "checking",
                        "required": len([p for p in AWSPermissionsService.REQUIRED_PERMISSIONS.get("S3", []) if p in simulation_result.get("missing_permissions", [])]) == 0
                    },
                    "CloudWatch": {
                        "status": "checking",
                        "required": len([p for p in AWSPermissionsService.REQUIRED_PERMISSIONS.get("CloudWatch", []) if p in simulation_result.get("missing_permissions", [])]) == 0
                    }
                }
            })
        else:
            # Fallback to simple checks
            batch_result = AWSPermissionsService.check_permissions_batch()
            return jsonify({
                "success": True,
                "method": "simple_check",
                "overall_status": batch_result.get("overall", "unknown"),
                "missing_permissions": batch_result.get("missing_permissions", []),
                "available_permissions": batch_result.get("available_permissions", []),
                "categories": batch_result.get("categories", {}),
                "warning": simulation_result.get("error", "Using simplified permission checks")
            })
            
    except FileNotFoundError:
        return jsonify({
            "success": False,
            "error": "AWS CLI not found"
        }), 500
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

