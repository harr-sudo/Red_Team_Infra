"""
Deployment API Routes
Handle infrastructure deployment operations
"""

from flask import Blueprint, request, jsonify
from pathlib import Path
import sys
import threading
import time
import os
import hashlib
from werkzeug.utils import secure_filename

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from webapp.backend.services.terraform_service import TerraformService

bp = Blueprint('deploy', __name__)

# File storage directory (local to user's machine)
UPLOAD_FOLDER = project_root / "uploads"
ALLOWED_EXTENSIONS = {'tar', 'gz', 'zip', 'tar.gz'}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB

# Ensure upload directory exists
UPLOAD_FOLDER.mkdir(exist_ok=True)

# Deployment state (in-memory, simple implementation)
deployment_state = {
    "status": "idle",  # idle, running, success, error
    "step": "",
    "output": "",
    "error": None
}

terraform_service = TerraformService(project_root)

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS or \
           filename.endswith('.tar.gz')

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

def run_deployment():
    """Run deployment in background thread"""
    global deployment_state
    
    try:
        deployment_state["status"] = "running"
        deployment_state["step"] = "Initializing Terraform..."
        deployment_state["output"] = ""
        deployment_state["error"] = None
        
        # Initialize
        result = terraform_service.init()
        if not result["success"]:
            deployment_state["status"] = "error"
            deployment_state["error"] = result.get("stderr", "Terraform init failed")
            return
        
        deployment_state["step"] = "Validating configuration..."
        result = terraform_service.validate()
        if not result["success"]:
            deployment_state["status"] = "error"
            deployment_state["error"] = result.get("stderr", "Validation failed")
            return
        
        deployment_state["step"] = "Planning deployment..."
        result = terraform_service.plan()
        if not result["success"] and result["exit_code"] != 2:  # 2 means changes detected
            deployment_state["status"] = "error"
            deployment_state["error"] = result.get("stderr", "Plan failed")
            return
        
        deployment_state["step"] = "Applying changes..."
        result = terraform_service.apply()
        if not result["success"]:
            deployment_state["status"] = "error"
            deployment_state["error"] = result.get("stderr", "Apply failed")
            return
        
        deployment_state["step"] = "Getting outputs..."
        result = terraform_service.output()
        
        deployment_state["status"] = "success"
        deployment_state["step"] = "Deployment complete"
        deployment_state["output"] = result.get("outputs", {})
        
    except Exception as e:
        deployment_state["status"] = "error"
        deployment_state["error"] = str(e)

def run_destroy():
    """Run destroy in background thread"""
    global deployment_state
    
    try:
        deployment_state["status"] = "running"
        deployment_state["step"] = "Destroying infrastructure..."
        deployment_state["output"] = ""
        deployment_state["error"] = None
        
        result = terraform_service.destroy()
        if not result["success"]:
            deployment_state["status"] = "error"
            deployment_state["error"] = result.get("stderr", "Destroy failed")
            return
        
        deployment_state["status"] = "success"
        deployment_state["step"] = "Infrastructure destroyed"
        
    except Exception as e:
        deployment_state["status"] = "error"
        deployment_state["error"] = str(e)

@bp.route('/status', methods=['GET'])
def get_deployment_status():
    """Get current deployment status"""
    return jsonify({
        "success": True,
        "status": deployment_state
    })

@bp.route('/deploy', methods=['POST'])
def deploy():
    """Start deployment"""
    global deployment_state
    
    if deployment_state["status"] == "running":
        return jsonify({
            "success": False,
            "error": "Deployment already in progress"
        }), 400
    
    # Check prerequisite: Cobalt Strike file must be uploaded
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
    
    # Check prerequisite: Domain must be configured
    from webapp.backend.utils.config_parser import ConfigParser
    from webapp.backend.utils.validators import ConfigValidator
    
    config_dir = project_root / "configs"
    tfvars_file = config_dir / "terraform.tfvars"
    
    if not tfvars_file.exists():
        return jsonify({
            "success": False,
            "error": "Configuration file (terraform.tfvars) not found. Please configure infrastructure first."
        }), 400
    
    config = ConfigParser.parse_tfvars(tfvars_file)
    primary_domain = config.get('primary_domain_name', '').strip()
    
    if not primary_domain:
        return jsonify({
            "success": False,
            "error": "Domain configuration is required. Please configure primary_domain_name in terraform.tfvars before deployment."
        }), 400
    
    domain_valid, domain_errors = ConfigValidator.validate_domain_config(config)
    if not domain_valid:
        return jsonify({
            "success": False,
            "error": f"Domain configuration is invalid: {', '.join(domain_errors)}"
        }), 400
    
    # Start deployment in background thread
    thread = threading.Thread(target=run_deployment)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "success": True,
        "message": "Deployment started"
    })

@bp.route('/destroy', methods=['POST'])
def destroy():
    """Destroy infrastructure"""
    global deployment_state
    
    if deployment_state["status"] == "running":
        return jsonify({
            "success": False,
            "error": "Operation already in progress"
        }), 400
    
    # Require confirmation
    data = request.get_json() or {}
    if data.get("confirm") != "DESTROY":
        return jsonify({
            "success": False,
            "error": "Confirmation required. Send confirm: 'DESTROY'"
        }), 400
    
    # Start destroy in background thread
    thread = threading.Thread(target=run_destroy)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "success": True,
        "message": "Destruction started"
    })

@bp.route('/plan', methods=['GET'])
def plan():
    """Run Terraform plan"""
    try:
        result = terraform_service.plan()
        return jsonify({
            "success": result["success"],
            "exit_code": result.get("exit_code"),
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "plan": result.get("plan", {})
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@bp.route('/init', methods=['POST'])
def init():
    """Initialize Terraform"""
    try:
        result = terraform_service.init()
        return jsonify({
            "success": result["success"],
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", "")
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

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
        
        # Sort by modified time (newest first)
        cobalt_strike_files.sort(key=lambda x: x['modified'] if x else 0, reverse=True)
        
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


@bp.route('/infrastructure', methods=['GET'])
def get_infrastructure():
    """Get current infrastructure state and outputs from Terraform"""
    try:
        # Check if Terraform state exists
        state_file = terraform_service.terraform_dir / "terraform.tfstate"
        
        if not state_file.exists():
            return jsonify({
                "success": True,
                "has_deployment": False,
                "message": "No infrastructure deployed yet"
            })
        
        # Get Terraform outputs
        output_result = terraform_service.output()
        
        if not output_result.get("success"):
            # State exists but outputs failed - might be empty state
            return jsonify({
                "success": True,
                "has_deployment": False,
                "message": "No active infrastructure found"
            })
        
        outputs = output_result.get("outputs", {})
        
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
            
            # Bastion Host
            "bastion": {
                "enabled": outputs.get("bastion_public_ip", {}).get("value") is not None,
                "public_ip": outputs.get("bastion_public_ip", {}).get("value"),
                "private_ip": outputs.get("bastion_private_ip", {}).get("value"),
                "rdp_connection": outputs.get("bastion_rdp_connection", {}).get("value"),
                "wsl2_info": outputs.get("bastion_wsl2_info", {}).get("value"),
            },
            
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
            
            # Ansible Inventory Info
            "ansible_inventory": outputs.get("ansible_inventory", {}).get("value", {}),
        }
        
        # Count resources
        infrastructure["summary"] = {
            "c2_server_count": len(infrastructure["c2_servers"]["instance_ids"]) or len(infrastructure["c2_servers"]["servers"]),
            "redirector_count": len(infrastructure["redirectors"]["instance_ids"]),
            "has_bastion": infrastructure["bastion"]["enabled"],
            "subnet_count": len(infrastructure["network"]["public_subnets"]) + len(infrastructure["network"]["private_subnets"]),
        }
        
        return jsonify({
            "success": True,
            **infrastructure
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "message": f"Error getting infrastructure state: {str(e)}"
        }), 500


@bp.route('/infrastructure/refresh', methods=['POST'])
def refresh_infrastructure():
    """Refresh Terraform state (terraform refresh)"""
    try:
        # Run terraform refresh to sync state with actual infrastructure
        exit_code, stdout, stderr = terraform_service._run_command([
            "terraform", "refresh",
            "-var-file", str(terraform_service.tfvars_file.relative_to(terraform_service.terraform_dir))
        ])
        
        if exit_code != 0:
            return jsonify({
                "success": False,
                "error": stderr or "Terraform refresh failed"
            }), 500
        
        # Now get the updated infrastructure
        return get_infrastructure()
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

