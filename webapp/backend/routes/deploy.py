"""
Deployment API Routes
Handle infrastructure deployment operations
"""

from flask import Blueprint, request, jsonify
from pathlib import Path
import sys
import threading
import time

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from webapp.backend.services.terraform_service import TerraformService

bp = Blueprint('deploy', __name__)

# Deployment state (in-memory, simple implementation)
deployment_state = {
    "status": "idle",  # idle, running, success, error
    "step": "",
    "output": "",
    "error": None
}

terraform_service = TerraformService(project_root)

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

