"""
Status API Routes
Handle infrastructure status and information
"""

from flask import Blueprint, jsonify
from pathlib import Path
import sys
import json

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from webapp.backend.services.terraform_service import TerraformService

bp = Blueprint('status', __name__)

terraform_service = TerraformService(project_root)

@bp.route('/', methods=['GET'])
def get_status():
    """Get overall infrastructure status"""
    try:
        # Check if terraform.tfvars exists
        tfvars_file = project_root / "configs" / "terraform.tfvars"
        config_exists = tfvars_file.exists()
        
        # Check if Terraform is initialized
        terraform_dir = project_root / "terraform"
        terraform_init = (terraform_dir / ".terraform").exists()
        
        # Try to get outputs (indicates deployed infrastructure)
        outputs_result = terraform_service.output()
        has_outputs = outputs_result.get("success", False) and outputs_result.get("outputs", {})
        
        # Try to get state
        state_result = terraform_service.show()
        has_state = state_result.get("success", False) and state_result.get("state", {})
        
        status = "not_deployed"
        if has_state:
            status = "deployed"
        elif terraform_init:
            status = "initialized"
        elif config_exists:
            status = "configured"
        
        return jsonify({
            "success": True,
            "status": status,
            "config_exists": config_exists,
            "terraform_initialized": terraform_init,
            "infrastructure_deployed": has_state
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@bp.route('/outputs', methods=['GET'])
def get_outputs():
    """Get Terraform outputs"""
    try:
        result = terraform_service.output()
        return jsonify({
            "success": result["success"],
            "outputs": result.get("outputs", {}),
            "error": result.get("stderr", "")
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@bp.route('/state', methods=['GET'])
def get_state():
    """Get Terraform state"""
    try:
        result = terraform_service.show()
        return jsonify({
            "success": result["success"],
            "state": result.get("state", {}),
            "error": result.get("stderr", "")
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@bp.route('/resources', methods=['GET'])
def get_resources():
    """Get list of deployed resources"""
    try:
        result = terraform_service.show()
        if not result["success"]:
            return jsonify({
                "success": False,
                "resources": [],
                "error": result.get("stderr", "No state available")
            })
        
        state = result.get("state", {})
        resources = []
        
        # Extract resource information from state
        if "values" in state and "root_module" in state["values"]:
            root_module = state["values"]["root_module"]
            if "resources" in root_module:
                for resource in root_module["resources"]:
                    resources.append({
                        "type": resource.get("type", ""),
                        "name": resource.get("name", ""),
                        "address": resource.get("address", "")
                    })
        
        return jsonify({
            "success": True,
            "resources": resources
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

