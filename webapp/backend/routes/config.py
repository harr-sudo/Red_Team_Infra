"""
Configuration API Routes
Handle configuration file management
"""

from flask import Blueprint, request, jsonify
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from webapp.backend.utils.config_parser import ConfigParser
from webapp.backend.utils.validators import ConfigValidator

bp = Blueprint('config', __name__)

# Paths
config_dir = project_root / "configs"
tfvars_file = config_dir / "terraform.tfvars"
tfvars_example = config_dir / "terraform.tfvars.example"

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
        
        # Generate terraform.tfvars content
        content = ConfigParser.generate_tfvars(config)
        
        # Ensure configs directory exists
        config_dir.mkdir(parents=True, exist_ok=True)
        
        # Write to file
        with open(tfvars_file, 'w') as f:
            f.write(content)
        
        return jsonify({
            "success": True,
            "message": "Configuration saved successfully"
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

