"""
GOAD (Game Of Active Directory) API Routes
Handles GOAD lab deployment, status, and management
"""

from flask import Blueprint, jsonify, request
import subprocess
import os
import json
from pathlib import Path

bp = Blueprint('goad', __name__, url_prefix='/api/goad')

# GOAD lab configurations
GOAD_LABS = {
    'GOAD-Mini': {
        'name': 'GOAD-Mini',
        'display_name': 'GOAD Mini',
        'vms': 1,
        'domains': 1,
        'forests': 1,
        'description': 'Minimalist lab with single domain controller. Perfect for quick testing and learning basics.',
        'est_cost': 75,
        'attacks': ['Kerberoasting', 'AS-REP Roasting', 'DCSync', 'Pass-the-Hash'],
        'domain_names': ['sevenkingdoms.local']
    },
    'MINILAB': {
        'name': 'MINILAB',
        'display_name': 'Mini Lab',
        'vms': 2,
        'domains': 1,
        'forests': 1,
        'description': 'Basic lab with one DC and one Workstation. Good for practicing basic attack chains.',
        'est_cost': 150,
        'attacks': ['Kerberoasting', 'AS-REP Roasting', 'DCSync', 'Pass-the-Hash', 'Lateral Movement'],
        'domain_names': ['psycho.psycho.local']
    },
    'GOAD-Light': {
        'name': 'GOAD-Light',
        'display_name': 'GOAD Light',
        'vms': 3,
        'domains': 2,
        'forests': 1,
        'description': 'Smaller lab with 2 domains. Covers most common AD attack scenarios.',
        'est_cost': 200,
        'attacks': ['Kerberoasting', 'AS-REP Roasting', 'DCSync', 'Pass-the-Hash', 'Trust Attacks', 'Constrained Delegation'],
        'domain_names': ['sevenkingdoms.local', 'north.sevenkingdoms.local']
    },
    'SCCM': {
        'name': 'SCCM',
        'display_name': 'SCCM Lab',
        'vms': 4,
        'domains': 1,
        'forests': 1,
        'description': 'Lab with Microsoft Configuration Manager (SCCM/ConfigMgr). For SCCM-specific attacks.',
        'est_cost': 300,
        'attacks': ['SCCM Attacks', 'NAA Credentials', 'PXE Boot Attacks', 'Task Sequence Attacks'],
        'domain_names': ['sccm.local']
    },
    'GOAD': {
        'name': 'GOAD',
        'display_name': 'GOAD Full',
        'vms': 5,
        'domains': 3,
        'forests': 2,
        'description': 'Full lab with 3 domains across 2 forests. Complete AD environment for comprehensive testing.',
        'est_cost': 350,
        'attacks': ['Kerberoasting', 'AS-REP Roasting', 'DCSync', 'DCShadow', 'Pass-the-Hash', 'Golden Ticket', 'Silver Ticket', 'Trust Attacks', 'Forest Attacks', 'Constrained/Unconstrained Delegation', 'ACL Abuse', 'GPO Abuse'],
        'domain_names': ['sevenkingdoms.local', 'north.sevenkingdoms.local', 'essos.local']
    },
    'NHA': {
        'name': 'NHA',
        'display_name': 'NHA Challenge',
        'vms': 5,
        'domains': 2,
        'forests': 1,
        'description': 'Challenge lab with no hints provided. CTF-style for advanced practice.',
        'est_cost': 350,
        'attacks': ['Unknown - Challenge Mode'],
        'domain_names': ['Hidden']
    }
}

# Get project root directory
def get_project_root():
    """Get the project root directory"""
    return Path(__file__).parent.parent.parent.parent.parent

def get_goad_dir():
    """Get the GOAD tools directory"""
    return get_project_root() / 'tools' / 'goad'

def get_goad_workspace():
    """Get the GOAD workspace directory for this deployment"""
    return get_project_root() / 'goad_workspace'


@bp.route('/labs', methods=['GET'])
def list_labs():
    """List all available GOAD labs with their configurations"""
    return jsonify({
        'success': True,
        'labs': GOAD_LABS
    })


@bp.route('/labs/<lab_name>', methods=['GET'])
def get_lab_info(lab_name):
    """Get detailed information about a specific GOAD lab"""
    if lab_name not in GOAD_LABS:
        return jsonify({
            'success': False,
            'error': f'Unknown lab: {lab_name}',
            'available_labs': list(GOAD_LABS.keys())
        }), 404
    
    return jsonify({
        'success': True,
        'lab': GOAD_LABS[lab_name]
    })


@bp.route('/status', methods=['GET'])
def get_goad_status():
    """Get the current GOAD deployment status"""
    goad_workspace = get_goad_workspace()
    goad_dir = get_goad_dir()
    
    # Check if GOAD is available
    if not goad_dir.exists():
        return jsonify({
            'success': True,
            'goad_available': False,
            'has_deployment': False,
            'message': 'GOAD not found. Please ensure tools/goad is cloned.'
        })
    
    # Check for active deployment by looking for terraform state
    deployed_lab = None
    deployment_info = {}
    
    # Check each lab's terraform directory for state
    for lab_name in GOAD_LABS.keys():
        lab_tf_dir = goad_dir / 'ad' / lab_name / 'providers' / 'aws'
        tf_state_file = lab_tf_dir / 'terraform.tfstate'
        
        if tf_state_file.exists():
            try:
                with open(tf_state_file, 'r') as f:
                    state = json.load(f)
                    resources = state.get('resources', [])
                    if len(resources) > 0:
                        deployed_lab = lab_name
                        deployment_info = {
                            'lab_name': lab_name,
                            'lab_info': GOAD_LABS[lab_name],
                            'tf_state_path': str(tf_state_file),
                            'resource_count': len(resources)
                        }
                        break
            except Exception as e:
                pass
    
    # Also check our workspace for deployment marker
    deployment_marker = goad_workspace / 'current_deployment.json'
    if deployment_marker.exists():
        try:
            with open(deployment_marker, 'r') as f:
                marker_data = json.load(f)
                if not deployed_lab:
                    deployed_lab = marker_data.get('lab_name')
                    deployment_info = marker_data
        except Exception:
            pass
    
    return jsonify({
        'success': True,
        'goad_available': True,
        'has_deployment': deployed_lab is not None,
        'deployed_lab': deployed_lab,
        'deployment_info': deployment_info,
        'available_labs': list(GOAD_LABS.keys())
    })


@bp.route('/deploy', methods=['POST'])
def deploy_goad():
    """Deploy a GOAD lab"""
    data = request.get_json() or {}
    lab_name = data.get('lab_name')
    
    if not lab_name:
        return jsonify({
            'success': False,
            'error': 'lab_name is required'
        }), 400
    
    if lab_name not in GOAD_LABS:
        return jsonify({
            'success': False,
            'error': f'Unknown lab: {lab_name}',
            'available_labs': list(GOAD_LABS.keys())
        }), 400
    
    goad_dir = get_goad_dir()
    goad_workspace = get_goad_workspace()
    
    if not goad_dir.exists():
        return jsonify({
            'success': False,
            'error': 'GOAD not found. Please ensure tools/goad is cloned.'
        }), 500
    
    # Create workspace directory
    goad_workspace.mkdir(parents=True, exist_ok=True)
    
    # Get the terraform directory for this lab
    lab_tf_dir = goad_dir / 'ad' / lab_name / 'providers' / 'aws'
    
    if not lab_tf_dir.exists():
        return jsonify({
            'success': False,
            'error': f'Terraform configuration not found for lab: {lab_name}',
            'expected_path': str(lab_tf_dir)
        }), 500
    
    try:
        # Save deployment marker
        deployment_marker = goad_workspace / 'current_deployment.json'
        with open(deployment_marker, 'w') as f:
            json.dump({
                'lab_name': lab_name,
                'lab_info': GOAD_LABS[lab_name],
                'status': 'deploying',
                'tf_dir': str(lab_tf_dir)
            }, f, indent=2)
        
        # Run terraform init
        init_result = subprocess.run(
            ['terraform', 'init'],
            cwd=str(lab_tf_dir),
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if init_result.returncode != 0:
            return jsonify({
                'success': False,
                'error': 'Terraform init failed',
                'stderr': init_result.stderr,
                'stdout': init_result.stdout
            }), 500
        
        # Run terraform apply (non-blocking would be better for production)
        # For now, we'll start it and return immediately
        # In production, this should be a background task
        
        return jsonify({
            'success': True,
            'message': f'GOAD {lab_name} deployment initiated',
            'lab_info': GOAD_LABS[lab_name],
            'next_steps': [
                'Run terraform apply manually in: ' + str(lab_tf_dir),
                'Or use the GOAD CLI: cd tools/goad && ./goad.sh -t aws -l ' + lab_name + ' -p deploy'
            ],
            'note': 'Full automated deployment coming soon. For now, please complete deployment manually.'
        })
        
    except subprocess.TimeoutExpired:
        return jsonify({
            'success': False,
            'error': 'Terraform init timed out'
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/destroy', methods=['POST'])
def destroy_goad():
    """Destroy the current GOAD deployment"""
    data = request.get_json() or {}
    confirm = data.get('confirm')
    
    if confirm != 'DESTROY':
        return jsonify({
            'success': False,
            'error': 'Confirmation required. Send {"confirm": "DESTROY"}'
        }), 400
    
    goad_workspace = get_goad_workspace()
    goad_dir = get_goad_dir()
    
    # Find current deployment
    deployment_marker = goad_workspace / 'current_deployment.json'
    if not deployment_marker.exists():
        return jsonify({
            'success': False,
            'error': 'No GOAD deployment found'
        }), 404
    
    try:
        with open(deployment_marker, 'r') as f:
            deployment = json.load(f)
        
        lab_name = deployment.get('lab_name')
        lab_tf_dir = goad_dir / 'ad' / lab_name / 'providers' / 'aws'
        
        if not lab_tf_dir.exists():
            return jsonify({
                'success': False,
                'error': f'Terraform directory not found: {lab_tf_dir}'
            }), 500
        
        # Run terraform destroy
        result = subprocess.run(
            ['terraform', 'destroy', '-auto-approve'],
            cwd=str(lab_tf_dir),
            capture_output=True,
            text=True,
            timeout=1800  # 30 minutes
        )
        
        # Clean up marker
        deployment_marker.unlink(missing_ok=True)
        
        if result.returncode != 0:
            return jsonify({
                'success': False,
                'error': 'Terraform destroy failed',
                'stderr': result.stderr,
                'stdout': result.stdout
            }), 500
        
        return jsonify({
            'success': True,
            'message': f'GOAD {lab_name} destroyed successfully',
            'stdout': result.stdout
        })
        
    except subprocess.TimeoutExpired:
        return jsonify({
            'success': False,
            'error': 'Terraform destroy timed out'
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/credentials', methods=['GET'])
def get_credentials():
    """Get credentials for the deployed GOAD lab"""
    goad_workspace = get_goad_workspace()
    goad_dir = get_goad_dir()
    
    # Find current deployment
    deployment_marker = goad_workspace / 'current_deployment.json'
    if not deployment_marker.exists():
        return jsonify({
            'success': False,
            'error': 'No GOAD deployment found'
        }), 404
    
    try:
        with open(deployment_marker, 'r') as f:
            deployment = json.load(f)
        
        lab_name = deployment.get('lab_name')
        lab_info = GOAD_LABS.get(lab_name, {})
        
        # Default credentials (these are from GOAD's documentation)
        credentials = {
            'lab_name': lab_name,
            'domains': lab_info.get('domain_names', []),
            'default_users': [
                {'domain': 'SEVENKINGDOMS', 'username': 'Administrator', 'note': 'Check GOAD inventory for password'},
                {'domain': 'NORTH', 'username': 'Administrator', 'note': 'Check GOAD inventory for password'},
            ],
            'inventory_path': str(goad_dir / 'ad' / lab_name / 'data' / 'inventory'),
            'note': 'Actual credentials are in the GOAD inventory files. Check ad/<lab>/data/inventory'
        }
        
        return jsonify({
            'success': True,
            'credentials': credentials
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/jumpbox', methods=['GET'])
def get_jumpbox_info():
    """Get jumpbox connection information for GOAD"""
    goad_workspace = get_goad_workspace()
    goad_dir = get_goad_dir()
    
    # Find current deployment
    deployment_marker = goad_workspace / 'current_deployment.json'
    if not deployment_marker.exists():
        return jsonify({
            'success': False,
            'error': 'No GOAD deployment found'
        }), 404
    
    try:
        with open(deployment_marker, 'r') as f:
            deployment = json.load(f)
        
        lab_name = deployment.get('lab_name')
        lab_tf_dir = goad_dir / 'ad' / lab_name / 'providers' / 'aws'
        
        # Try to get terraform outputs
        result = subprocess.run(
            ['terraform', 'output', '-json'],
            cwd=str(lab_tf_dir),
            capture_output=True,
            text=True,
            timeout=30
        )
        
        jumpbox_info = {
            'lab_name': lab_name,
            'ssh_key_path': str(goad_dir / 'workspace' / lab_name / 'ssh_keys'),
            'commands': {
                'ssh': f'cd {goad_dir} && ./goad.sh -t ssh_jumpbox',
                'socks_proxy': f'cd {goad_dir} && ./goad.sh -t ssh_jumpbox_proxy 1080'
            }
        }
        
        if result.returncode == 0:
            try:
                outputs = json.loads(result.stdout)
                if 'jumpbox_ip' in outputs:
                    jumpbox_info['public_ip'] = outputs['jumpbox_ip'].get('value')
            except json.JSONDecodeError:
                pass
        
        return jsonify({
            'success': True,
            'jumpbox': jumpbox_info
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/start', methods=['POST'])
def start_goad():
    """Start stopped GOAD lab VMs"""
    goad_dir = get_goad_dir()
    goad_workspace = get_goad_workspace()
    
    deployment_marker = goad_workspace / 'current_deployment.json'
    if not deployment_marker.exists():
        return jsonify({
            'success': False,
            'error': 'No GOAD deployment found'
        }), 404
    
    try:
        with open(deployment_marker, 'r') as f:
            deployment = json.load(f)
        
        lab_name = deployment.get('lab_name')
        
        # Use GOAD's start command
        result = subprocess.run(
            ['./goad.sh', '-t', 'aws', '-l', lab_name, '-p', 'start'],
            cwd=str(goad_dir),
            capture_output=True,
            text=True,
            timeout=300
        )
        
        return jsonify({
            'success': result.returncode == 0,
            'message': f'GOAD {lab_name} start command executed',
            'stdout': result.stdout,
            'stderr': result.stderr if result.returncode != 0 else None
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/stop', methods=['POST'])
def stop_goad():
    """Stop GOAD lab VMs to save costs"""
    goad_dir = get_goad_dir()
    goad_workspace = get_goad_workspace()
    
    deployment_marker = goad_workspace / 'current_deployment.json'
    if not deployment_marker.exists():
        return jsonify({
            'success': False,
            'error': 'No GOAD deployment found'
        }), 404
    
    try:
        with open(deployment_marker, 'r') as f:
            deployment = json.load(f)
        
        lab_name = deployment.get('lab_name')
        
        # Use GOAD's stop command
        result = subprocess.run(
            ['./goad.sh', '-t', 'aws', '-l', lab_name, '-p', 'stop'],
            cwd=str(goad_dir),
            capture_output=True,
            text=True,
            timeout=300
        )
        
        return jsonify({
            'success': result.returncode == 0,
            'message': f'GOAD {lab_name} stop command executed',
            'stdout': result.stdout,
            'stderr': result.stderr if result.returncode != 0 else None
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

