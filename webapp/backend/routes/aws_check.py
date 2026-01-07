"""
AWS Check API Routes
Handle AWS credentials and permissions checking
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

bp = Blueprint('aws_check', __name__)

@bp.route('/credentials', methods=['GET'])
def check_credentials():
    """Check current AWS CLI credentials"""
    try:
        # Run AWS CLI command to get caller identity
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
                    "user": identity.get("Arn", ""),
                    "user_id": identity.get("UserId", ""),
                    "message": "AWS credentials are valid"
                })
            except json.JSONDecodeError:
                return jsonify({
                    "success": True,
                    "authenticated": True,
                    "raw_output": result.stdout,
                    "message": "AWS credentials are valid"
                })
        else:
            # Check if AWS CLI is installed
            if "aws: command not found" in result.stderr or "aws: not found" in result.stderr:
                return jsonify({
                    "success": False,
                    "authenticated": False,
                    "error": "AWS CLI is not installed",
                    "message": "Please install AWS CLI to use this feature"
                }), 400
            
            # Credentials are invalid or not configured
            return jsonify({
                "success": False,
                "authenticated": False,
                "error": result.stderr.strip() or "AWS credentials not configured or invalid",
                "message": "AWS credentials are not configured or invalid. Please run 'aws configure' to set up your credentials."
            }), 401
            
    except FileNotFoundError:
        return jsonify({
            "success": False,
            "authenticated": False,
            "error": "AWS CLI not found",
            "message": "AWS CLI is not installed. Please install it first."
        }), 500
    except subprocess.TimeoutExpired:
        return jsonify({
            "success": False,
            "authenticated": False,
            "error": "Command timed out",
            "message": "AWS credentials check timed out"
        }), 500
    except Exception as e:
        return jsonify({
            "success": False,
            "authenticated": False,
            "error": str(e),
            "message": f"Error checking credentials: {str(e)}"
        }), 500

@bp.route('/github-cli', methods=['GET'])
def check_github_cli():
    """Check if user is logged into GitHub CLI and has access to the tools repo"""
    import re
    
    TOOLS_REPO = "harr-sudo/red-team-tools"
    TOOLS_REPO_URL = f"https://github.com/{TOOLS_REPO}"
    
    try:
        # Run gh auth status to check if logged in
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            # Parse the output to extract user info
            output = result.stdout + result.stderr  # gh auth status outputs to stderr
            
            # Try to extract username from output
            username = None
            account_type = None
            
            # Look for "Logged in to github.com account <username>"
            match = re.search(r'Logged in to github\.com account (\S+)', output)
            if match:
                username = match.group(1)
            
            # Check if it's a token or SSH auth
            if 'Token:' in output:
                account_type = 'token'
            elif 'ssh' in output.lower():
                account_type = 'ssh'
            
            # Now check if user has access to the private tools repo
            repo_access_result = subprocess.run(
                ["gh", "repo", "view", TOOLS_REPO, "--json", "name,visibility"],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if repo_access_result.returncode == 0:
                # User has access to the repo
                try:
                    repo_info = json.loads(repo_access_result.stdout)
                    return jsonify({
                        "success": True,
                        "authenticated": True,
                        "has_repo_access": True,
                        "username": username,
                        "account_type": account_type,
                        "repo_name": repo_info.get("name", TOOLS_REPO),
                        "repo_visibility": repo_info.get("visibility", "unknown"),
                        "message": "GitHub CLI authenticated with tools repo access",
                        "tools_repo": TOOLS_REPO_URL
                    })
                except json.JSONDecodeError:
                    return jsonify({
                        "success": True,
                        "authenticated": True,
                        "has_repo_access": True,
                        "username": username,
                        "account_type": account_type,
                        "message": "GitHub CLI authenticated with tools repo access",
                        "tools_repo": TOOLS_REPO_URL
                    })
            else:
                # User is logged in but doesn't have access to the repo
                repo_error = repo_access_result.stderr.strip()
                
                return jsonify({
                    "success": True,
                    "authenticated": True,
                    "has_repo_access": False,
                    "username": username,
                    "account_type": account_type,
                    "message": "GitHub CLI authenticated but no access to tools repository",
                    "repo_error": repo_error,
                    "tools_repo": TOOLS_REPO_URL,
                    "access_request_info": {
                        "contact": "Harris",
                        "repo": TOOLS_REPO,
                        "instruction": f"Please ask Harris to grant you access to {TOOLS_REPO_URL}"
                    }
                })
        else:
            error_output = result.stderr.strip() or result.stdout.strip()
            
            # Check if gh CLI is installed but not logged in
            if "not logged" in error_output.lower() or "authentication" in error_output.lower():
                return jsonify({
                    "success": False,
                    "authenticated": False,
                    "has_repo_access": False,
                    "error": "Not logged in to GitHub CLI",
                    "message": "Please run 'gh auth login' to authenticate with GitHub CLI",
                    "tools_repo": TOOLS_REPO_URL
                }), 401
            
            return jsonify({
                "success": False,
                "authenticated": False,
                "has_repo_access": False,
                "error": error_output or "GitHub CLI authentication failed",
                "message": "GitHub CLI authentication check failed. Please run 'gh auth login'.",
                "tools_repo": TOOLS_REPO_URL
            }), 401
            
    except FileNotFoundError:
        return jsonify({
            "success": False,
            "authenticated": False,
            "has_repo_access": False,
            "error": "GitHub CLI (gh) not found",
            "message": "GitHub CLI is not installed. Please install it from https://cli.github.com/",
            "tools_repo": TOOLS_REPO_URL
        }), 500
    except subprocess.TimeoutExpired:
        return jsonify({
            "success": False,
            "authenticated": False,
            "has_repo_access": False,
            "error": "Command timed out",
            "message": "GitHub CLI check timed out"
        }), 500
    except Exception as e:
        return jsonify({
            "success": False,
            "authenticated": False,
            "has_repo_access": False,
            "error": str(e),
            "message": f"Error checking GitHub CLI: {str(e)}"
        }), 500

@bp.route('/permissions', methods=['GET'])
def check_permissions():
    """Check if AWS credentials have sufficient permissions for deployment"""
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
                "message": "Please configure AWS credentials first using 'aws configure'"
            }), 401
        
        # Try policy simulation first (more accurate)
        simulation_result = AWSPermissionsService.check_using_policy_simulation()
        
        if simulation_result.get("success"):
            # Policy simulation succeeded
            missing = simulation_result.get("missing_permissions", [])
            available = simulation_result.get("available_permissions", [])
            overall = simulation_result.get("overall", "unknown")
            
            # Determine status
            if overall == "complete":
                status = "sufficient"
                status_icon = "✅"
                status_text = "All required permissions are available"
            elif overall == "partial":
                status = "partial"
                status_icon = "⚠️"
                status_text = f"Some permissions are missing ({len(missing)} missing, {len(available)} available)"
            else:
                status = "insufficient"
                status_icon = "❌"
                status_text = "Many required permissions are missing"
            
            return jsonify({
                "success": True,
                "method": "policy_simulation",
                "status": status,
                "status_icon": status_icon,
                "status_text": status_text,
                "overall": overall,
                "missing_permissions": missing,
                "available_permissions": available,
                "total_required": len(missing) + len(available),
                "total_available": len(available),
                "total_missing": len(missing),
                "permissions": simulation_result.get("permissions", {})
            })
        else:
            # Fallback to simple checks
            batch_result = AWSPermissionsService.check_permissions_batch()
            missing = batch_result.get("missing_permissions", [])
            available = batch_result.get("available_permissions", [])
            overall = batch_result.get("overall", "unknown")
            
            # Determine status
            if overall == "complete":
                status = "sufficient"
                status_icon = "✅"
                status_text = "All testable permissions are available"
            elif overall == "partial":
                status = "partial"
                status_icon = "⚠️"
                status_text = f"Some permissions may be missing (best-effort check)"
            else:
                status = "unknown"
                status_icon = "⚠️"
                status_text = "Cannot fully verify permissions (write permissions cannot be safely tested)"
            
            return jsonify({
                "success": True,
                "method": "simple_check",
                "status": status,
                "status_icon": status_icon,
                "status_text": status_text,
                "overall": overall,
                "missing_permissions": missing,
                "available_permissions": available,
                "total_required": len(missing) + len(available),
                "total_available": len(available),
                "total_missing": len(missing),
                "categories": batch_result.get("categories", {}),
                "warning": simulation_result.get("error", "Using simplified permission checks (write permissions cannot be safely tested)")
            })
            
    except FileNotFoundError:
        return jsonify({
            "success": False,
            "error": "AWS CLI not found",
            "message": "AWS CLI is not installed. Please install it first."
        }), 500
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "message": f"Error checking permissions: {str(e)}"
        }), 500

