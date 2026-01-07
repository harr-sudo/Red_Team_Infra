
from flask import Blueprint, jsonify
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from webapp.backend.utils.config_parser import ConfigParser
from webapp.backend.utils.validators import ConfigValidator

bp = Blueprint('health', __name__)

# Paths
config_dir = project_root / "configs"
tfvars_file = config_dir / "terraform.tfvars"
UPLOAD_FOLDER = project_root / "uploads"
ALLOWED_EXTENSIONS = {'tar', 'gz', 'zip', 'tar.gz'}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS or \
           filename.endswith('.tar.gz')

@bp.route('/domain-config', methods=['GET'])
def check_domain_config():
    """Check if domain is configured"""
    try:
        if not tfvars_file.exists():
            return jsonify({
                "success": True,
                "configured": False,
                "error": "Configuration file not found"
            })
            
        config = ConfigParser.parse_tfvars(tfvars_file)
        primary_domain = config.get('primary_domain_name', '').strip()
        
        if not primary_domain:
            return jsonify({
                "success": True,
                "configured": False,
                "error": "Primary domain not configured"
            })
            
        # Validate domain config
        is_valid, errors = ConfigValidator.validate_domain_config(config)
        
        return jsonify({
            "success": True,
            "configured": is_valid,
            "domain_info": {
                "primary_domain": primary_domain,
                "c2_subdomain": config.get('c2_subdomain', 'c2'),
                "www_subdomain": config.get('www_subdomain', 'www'),
                "cdn_subdomain": config.get('cdn_subdomain', 'cdn'),
                "backup_domains": config.get('backup_domains', [])
            },
            "errors": errors
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@bp.route('/cobalt-strike-file', methods=['GET'])
def check_cobalt_strike_file():
    """Check if Cobalt Strike file is uploaded"""
    try:
        if not UPLOAD_FOLDER.exists():
            return jsonify({
                "success": True,
                "has_file": False
            })
            
        files = list(UPLOAD_FOLDER.glob("*"))
        cobalt_strike_files = [
            f for f in files 
            if f.is_file() and allowed_file(f.name)
        ]
        
        return jsonify({
            "success": True,
            "has_file": len(cobalt_strike_files) > 0
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

