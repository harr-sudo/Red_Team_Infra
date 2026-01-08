
from flask import Blueprint, jsonify
from pathlib import Path
import sys
import subprocess
import shutil

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


@bp.route('/terraform', methods=['GET'])
def check_terraform():
    """Check if Terraform CLI is installed"""
    try:
        # Check if terraform is in PATH
        terraform_path = shutil.which('terraform')
        
        if not terraform_path:
            return jsonify({
                "success": True,
                "installed": False,
                "error": "Terraform CLI not found in PATH. Please install Terraform."
            })
        
        # Get version
        result = subprocess.run(
            ['terraform', 'version', '-json'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        version = "Unknown"
        if result.returncode == 0:
            try:
                import json
                version_data = json.loads(result.stdout)
                version = version_data.get('terraform_version', 'Unknown')
            except:
                # Fallback to parsing text output
                result_text = subprocess.run(
                    ['terraform', 'version'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result_text.returncode == 0:
                    first_line = result_text.stdout.strip().split('\n')[0]
                    version = first_line.replace('Terraform v', '').strip()
        
        return jsonify({
            "success": True,
            "installed": True,
            "version": version,
            "path": terraform_path
        })
        
    except subprocess.TimeoutExpired:
        return jsonify({
            "success": True,
            "installed": False,
            "error": "Terraform command timed out"
        })
    except FileNotFoundError:
        return jsonify({
            "success": True,
            "installed": False,
            "error": "Terraform CLI not found. Please install Terraform."
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "installed": False,
            "error": str(e)
        }), 500


@bp.route('/aws-cli', methods=['GET'])
def check_aws_cli():
    """Check if AWS CLI is installed"""
    try:
        # Check if aws is in PATH
        aws_path = shutil.which('aws')
        
        if not aws_path:
            return jsonify({
                "success": True,
                "installed": False,
                "error": "AWS CLI not found in PATH. Please install AWS CLI."
            })
        
        # Get version
        result = subprocess.run(
            ['aws', '--version'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        version = "Unknown"
        if result.returncode == 0:
            # Output format: aws-cli/2.x.x Python/3.x.x ...
            version_line = result.stdout.strip() or result.stderr.strip()
            if version_line:
                parts = version_line.split()
                if parts:
                    version = parts[0].replace('aws-cli/', '')
        
        return jsonify({
            "success": True,
            "installed": True,
            "version": version,
            "path": aws_path
        })
        
    except subprocess.TimeoutExpired:
        return jsonify({
            "success": True,
            "installed": False,
            "error": "AWS CLI command timed out"
        })
    except FileNotFoundError:
        return jsonify({
            "success": True,
            "installed": False,
            "error": "AWS CLI not found. Please install AWS CLI."
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "installed": False,
            "error": str(e)
        }), 500

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

