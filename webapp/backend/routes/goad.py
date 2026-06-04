"""
GOAD (Game Of Active Directory) API Routes
Handles GOAD lab deployment, status, and management
"""

from flask import Blueprint, jsonify, request
import subprocess
import os
import json
import boto3
from pathlib import Path
from webapp.backend.utils.config_parser import DEPLOYMENT_TYPE_MAP

bp = Blueprint('goad', __name__, url_prefix='/api/goad')

# Timeout constants (in seconds)
TERRAFORM_INIT_TIMEOUT = 300      # 5 minutes
TERRAFORM_DESTROY_TIMEOUT = 3600  # 60 minutes (increased from 30)
TERRAFORM_OUTPUT_TIMEOUT = 60     # 1 minute
AWS_OPERATION_TIMEOUT = 300       # 5 minutes

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
        'domain_names': ['sccm.lab']
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
        'description': 'Network Hacking Academy - CTF-style challenge lab. Ninja-themed corporate network.',
        'est_cost': 350,
        'attacks': ['Challenge Mode - Discover attack paths yourself'],
        'domain_names': ['ninja.hack', 'academy.ninja.lan']
    }
}

# Mapping from lab_type to upstream GOAD Ansible directory name
GOAD_ANSIBLE_LAB_MAP = {
    'GOAD-Mini': 'GOAD-Mini',
    'GOAD-Light': 'GOAD-Light',
    'GOAD': 'GOAD',
    'SCCM': 'SCCM',
    'NHA': 'NHA',
}

# Get project root directory
def get_project_root():
    """Get the project root directory"""
    return Path(__file__).parent.parent.parent.parent

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

    # Check main terraform state for combined deployments (GOAD resources in main state)
    if not deployed_lab:
        main_tf_state = project_root / 'terraform' / 'terraform.tfstate'
        if main_tf_state.exists():
            try:
                with open(main_tf_state, 'r') as f:
                    state = json.load(f)
                    for r in state.get('resources', []):
                        if r.get('module', '').startswith('module.goad'):
                            # Found GOAD resources in main state — combined deployment
                            deployed_lab = 'GOAD-Mini'  # Default; could parse from config
                            deployment_info = {
                                'lab_name': deployed_lab,
                                'lab_info': GOAD_LABS.get(deployed_lab, {}),
                                'tf_state_path': str(main_tf_state),
                                'combined_mode': True,
                            }
                            break
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


@bp.route('/provision', methods=['POST'])
def provision_goad():
    """
    Trigger Ansible AD provisioning on the jumpbox.
    This SSHs to the jumpbox and runs the upstream GOAD Ansible playbooks
    to configure Active Directory domains, users, trusts, and vulnerabilities.

    Key steps:
      1. Get jumpbox IP from terraform output
      2. SSH to jumpbox and resolve {{ip_range}} placeholders in inventory files
      3. Run ansible-playbook under nohup (survives SSH disconnects)
      4. Track remote PID for status checks
    """
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

    # Map to upstream GOAD Ansible directory
    ansible_lab = GOAD_ANSIBLE_LAB_MAP.get(lab_name)
    if not ansible_lab:
        return jsonify({
            'success': False,
            'error': f'No Ansible provisioning available for lab: {lab_name}'
        }), 400

    # Get jumpbox IP from terraform output
    try:
        from webapp.backend.utils.config_parser import ConfigParser
        from webapp.backend.utils.tfvars_path import resolve_tfvars_path
        project_root = get_project_root()
        config_dir = project_root / "configs"
        default_tfvars = config_dir / "terraform.tfvars"

        # ?project= or body.project_name → configs/<project>.tfvars (path-
        # traversal sanitized). Falls back to global tfvars when the per-
        # project file is missing — legacy single-deployment hosts.
        project_param = request.args.get("project") or (data.get("project_name") if isinstance(data, dict) else None)
        tfvars_file = resolve_tfvars_path(project_param, config_dir, default_tfvars)
        if not tfvars_file.exists():
            tfvars_file = default_tfvars

        config = ConfigParser.parse_tfvars(tfvars_file) if tfvars_file.exists() else {}

        # Get ip_range from config (default 192.168.56)
        ip_range = config.get('goad_ip_range', config.get('ip_range', '192.168.56'))

        # Try getting jumpbox IP from terraform output
        terraform_dir = project_root / "terraform"
        result = subprocess.run(
            ['terraform', 'output', '-json'],
            cwd=str(terraform_dir),
            capture_output=True,
            text=True,
            timeout=TERRAFORM_OUTPUT_TIMEOUT
        )

        jumpbox_ip = None
        if result.returncode == 0:
            try:
                outputs = json.loads(result.stdout)
                # Look for jumpbox IP in various output formats
                for key in ['goad_jumpbox_public_ip', 'goad_jumpbox_ip', 'jumpbox_ip', 'jumpbox_public_ip']:
                    if key in outputs:
                        val = outputs[key]
                        jumpbox_ip = val.get('value') if isinstance(val, dict) else val
                        break
            except json.JSONDecodeError:
                pass

        if not jumpbox_ip:
            return jsonify({
                'success': False,
                'error': 'Could not determine jumpbox IP. Is the infrastructure deployed?',
                'hint': 'Run terraform apply first, then provision AD.'
            }), 400

        # Build the provisioning script to run on the jumpbox.
        # The script:
        #   1. Resolves {{ip_range}} placeholders in inventory files (GOAD uses Jinja2
        #      templates that are normally rendered by goad.py — we must do it ourselves)
        #   2. Runs ansible-playbook under nohup so it survives SSH disconnects
        #   3. Writes exit code to a status file for remote status checks
        provision_script = (
            f"set -e; "
            # Resolve {{ip_range}} in the AWS inventory file (CRITICAL — without this,
            # Ansible tries to connect to the literal string '{{ip_range}}.10')
            f"INV_FILE=/home/ubuntu/GOAD/ad/{ansible_lab}/providers/aws/inventory; "
            f"if grep -q '{{{{ip_range}}}}' \"$INV_FILE\" 2>/dev/null; then "
            f"  sed -i 's/{{{{ip_range}}}}/{ip_range}/g' \"$INV_FILE\"; "
            f"fi; "
            # Run Ansible under nohup so it survives SSH drops.
            # Log all output to file. Write exit code to status file when done.
            f"nohup bash -c '"
            f"  cd /home/ubuntu/GOAD && "
            f"  ansible-playbook "
            f"    -i ad/{ansible_lab}/data/inventory "
            f"    -i ad/{ansible_lab}/providers/aws/inventory "
            f"    ansible/main.yml "
            f"    > /home/ubuntu/goad-provision.log 2>&1; "
            f"  echo $? > /home/ubuntu/goad-provision-exitcode"
            f"' > /dev/null 2>&1 & "
            # Print the background PID so we can track it remotely
            f"echo $!"
        )

        # SSH command to run on jumpbox (using the user's SSH key)
        ssh_key_path = config.get('ssh_private_key_path', '~/.ssh/id_ed25519')
        ssh_cmd = [
            'ssh', '-o', 'StrictHostKeyChecking=no',
            '-o', 'BatchMode=yes',
            '-i', os.path.expanduser(ssh_key_path),
            f'ubuntu@{jumpbox_ip}',
            provision_script
        ]

        # Run SSH command — this returns quickly because nohup backgrounds the work.
        # The stdout contains the remote Ansible PID.
        ssh_result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=60
        )

        if ssh_result.returncode != 0:
            return jsonify({
                'success': False,
                'error': 'Failed to start provisioning on jumpbox',
                'stderr': ssh_result.stderr,
                'hint': 'Check SSH key and jumpbox connectivity.'
            }), 500

        remote_pid = ssh_result.stdout.strip()

        # Save provisioning state
        goad_workspace = get_goad_workspace()
        goad_workspace.mkdir(parents=True, exist_ok=True)
        provision_marker = goad_workspace / 'provisioning.json'
        with open(provision_marker, 'w') as f:
            json.dump({
                'lab_name': lab_name,
                'ansible_lab': ansible_lab,
                'jumpbox_ip': jumpbox_ip,
                'remote_pid': remote_pid,
                'status': 'running',
                'ip_range': ip_range,
                'ssh_key_path': ssh_key_path,
                'started_at': str(subprocess.run(['date', '-u', '+%Y-%m-%dT%H:%M:%SZ'],
                                                  capture_output=True, text=True).stdout.strip())
            }, f, indent=2)

        return jsonify({
            'success': True,
            'message': f'AD provisioning started for {lab_name}',
            'jumpbox_ip': jumpbox_ip,
            'remote_pid': remote_pid,
            'estimated_time': '30-60 minutes depending on lab type',
            'log_file': '/home/ubuntu/goad-provision.log',
            'monitor_cmd': f'ssh ubuntu@{jumpbox_ip} tail -f /home/ubuntu/goad-provision.log',
            'check_status': 'GET /api/goad/provision-status'
        })

    except subprocess.TimeoutExpired:
        return jsonify({
            'success': False,
            'error': 'Timed out connecting to jumpbox'
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/provision-status', methods=['GET'])
def provision_status():
    """
    Check the status of an ongoing AD provisioning.
    SSHs to the jumpbox to check if the remote Ansible process is still running
    and reads the exit code file to detect success/failure.
    """
    goad_workspace = get_goad_workspace()
    provision_marker = goad_workspace / 'provisioning.json'

    if not provision_marker.exists():
        return jsonify({
            'success': True,
            'provisioning': False,
            'message': 'No provisioning in progress'
        })

    try:
        with open(provision_marker, 'r') as f:
            prov_data = json.load(f)

        # If already completed/failed, just return stored status
        if prov_data.get('status') in ('completed', 'failed'):
            return jsonify({
                'success': True,
                'provisioning': False,
                'data': prov_data
            })

        jumpbox_ip = prov_data.get('jumpbox_ip')
        remote_pid = prov_data.get('remote_pid')
        ssh_key_path = prov_data.get('ssh_key_path', '~/.ssh/id_ed25519')

        if not jumpbox_ip or not remote_pid:
            return jsonify({
                'success': True,
                'provisioning': False,
                'data': prov_data,
                'message': 'Missing jumpbox_ip or remote_pid'
            })

        # SSH to jumpbox to check if the remote process is still running,
        # read exit code if finished, and fetch the last 20 lines of the log
        check_cmd = (
            f"if kill -0 {remote_pid} 2>/dev/null; then "
            f"  echo 'RUNNING'; "
            f"elif [ -f /home/ubuntu/goad-provision-exitcode ]; then "
            f"  echo \"DONE:$(cat /home/ubuntu/goad-provision-exitcode)\"; "
            f"else "
            f"  echo 'UNKNOWN'; "
            f"fi; "
            f"echo '---LOG_TAIL---'; "
            f"tail -20 /home/ubuntu/goad-provision.log 2>/dev/null || echo 'No log file yet'"
        )

        ssh_cmd = [
            'ssh', '-o', 'StrictHostKeyChecking=no',
            '-o', 'BatchMode=yes',
            '-o', 'ConnectTimeout=10',
            '-i', os.path.expanduser(ssh_key_path),
            f'ubuntu@{jumpbox_ip}',
            check_cmd
        ]

        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            # Can't reach jumpbox — don't change status, just report
            return jsonify({
                'success': True,
                'provisioning': True,
                'data': prov_data,
                'message': 'Cannot reach jumpbox to check status (may still be running)'
            })

        # Parse response: split on ---LOG_TAIL--- to get status and log tail
        raw_output = result.stdout.strip()
        if '---LOG_TAIL---' in raw_output:
            status_line, log_tail = raw_output.split('---LOG_TAIL---', 1)
            status_line = status_line.strip()
            log_tail = log_tail.strip()
        else:
            status_line = raw_output
            log_tail = ''

        if status_line == 'RUNNING':
            return jsonify({
                'success': True,
                'provisioning': True,
                'data': prov_data,
                'log_tail': log_tail
            })
        elif status_line.startswith('DONE:'):
            exit_code = status_line.split(':', 1)[1].strip()
            if exit_code == '0':
                prov_data['status'] = 'completed'
            else:
                prov_data['status'] = 'failed'
                prov_data['exit_code'] = exit_code
            prov_data['log_tail'] = log_tail
            with open(provision_marker, 'w') as f:
                json.dump(prov_data, f, indent=2)
            return jsonify({
                'success': True,
                'provisioning': False,
                'data': prov_data,
                'log_tail': log_tail
            })
        else:
            # UNKNOWN — process gone but no exit code file
            prov_data['status'] = 'failed'
            prov_data['error'] = 'Process terminated without writing exit code'
            prov_data['log_tail'] = log_tail
            with open(provision_marker, 'w') as f:
                json.dump(prov_data, f, indent=2)
            return jsonify({
                'success': True,
                'provisioning': False,
                'data': prov_data,
                'log_tail': log_tail
            })

    except subprocess.TimeoutExpired:
        return jsonify({
            'success': True,
            'provisioning': True,
            'data': prov_data,
            'message': 'Timed out checking jumpbox (provisioning may still be running)'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/verify', methods=['POST'])
def verify_goad():
    """
    Verify AD health by SSHing to jumpbox and testing WinRM connectivity
    to each Windows VM using Ansible's win_ping module.

    Flow: Local machine → SSH → Jumpbox → WinRM ping → each AD VM
    """
    goad_workspace = get_goad_workspace()

    # Load provisioning or deployment info to get jumpbox IP and lab name
    provision_marker = goad_workspace / 'provisioning.json'
    deployment_marker = goad_workspace / 'current_deployment.json'

    jumpbox_ip = None
    lab_name = None
    ssh_key_path = '~/.ssh/goad_key'
    ip_range = '192.168.56'

    # Try provisioning.json first, then current_deployment.json
    for marker in [provision_marker, deployment_marker]:
        if marker.exists():
            with open(marker, 'r') as f:
                data = json.load(f)
            jumpbox_ip = jumpbox_ip or data.get('jumpbox_ip')
            lab_name = lab_name or data.get('lab_name')
            ssh_key_path = data.get('ssh_key_path', ssh_key_path)
            ip_range = data.get('ip_range', ip_range)

    if not jumpbox_ip or not lab_name:
        return jsonify({
            'success': False,
            'error': 'No deployment found — need jumpbox_ip and lab_name'
        }), 404

    # Determine which VMs to check based on lab type
    vm_checks = {
        'GOAD-Mini': {'dc01': f'{ip_range}.10'},
        'GOAD-Light': {'dc01': f'{ip_range}.10', 'dc02': f'{ip_range}.11', 'srv02': f'{ip_range}.22'},
        'SCCM': {'dc01': f'{ip_range}.10', 'srv01': f'{ip_range}.11', 'srv02': f'{ip_range}.12', 'ws01': f'{ip_range}.13'},
        'GOAD': {'dc01': f'{ip_range}.10', 'dc02': f'{ip_range}.11', 'dc03': f'{ip_range}.12', 'srv02': f'{ip_range}.22', 'srv03': f'{ip_range}.23'},
        'NHA': {'dc01': f'{ip_range}.10', 'dc02': f'{ip_range}.20', 'srv01': f'{ip_range}.21', 'srv02': f'{ip_range}.22', 'srv03': f'{ip_range}.23'},
    }

    vms = vm_checks.get(lab_name, {})
    if not vms:
        return jsonify({
            'success': False,
            'error': f'Unknown lab type for verification: {lab_name}'
        }), 400

    ansible_lab = GOAD_ANSIBLE_LAB_MAP.get(lab_name, lab_name)

    try:
        # Build a verify command that runs ansible win_ping on the jumpbox
        # This tests WinRM connectivity + authentication in one shot
        verify_cmd = (
            f"cd /home/ubuntu/GOAD && "
            f"ansible -i ad/{ansible_lab}/data/inventory "
            f"-i ad/{ansible_lab}/providers/aws/inventory "
            f"-m win_ping all 2>&1 || true"
        )

        ssh_cmd = [
            'ssh', '-o', 'StrictHostKeyChecking=no',
            '-o', 'BatchMode=yes',
            '-o', 'ConnectTimeout=10',
            '-i', os.path.expanduser(ssh_key_path),
            f'ubuntu@{jumpbox_ip}',
            verify_cmd
        ]

        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0 and not result.stdout:
            return jsonify({
                'success': False,
                'error': 'Cannot reach jumpbox via SSH',
                'details': result.stderr.strip()
            }), 502

        # Parse ansible output to determine per-VM pass/fail
        # Ansible win_ping output looks like:
        #   dc01 | SUCCESS => { "changed": false, "ping": "pong" }
        #   dc02 | UNREACHABLE! => { ... }
        output = result.stdout.strip()
        vm_results = {}
        for vm_name, vm_ip in vms.items():
            # Check if this VM shows SUCCESS in the output
            if f'{vm_name} | SUCCESS' in output or f'{vm_ip} | SUCCESS' in output:
                vm_results[vm_name] = {'ip': vm_ip, 'status': 'healthy', 'winrm': True}
            elif f'{vm_name} | UNREACHABLE' in output or f'{vm_ip} | UNREACHABLE' in output:
                vm_results[vm_name] = {'ip': vm_ip, 'status': 'unreachable', 'winrm': False}
            elif f'{vm_name} | FAILED' in output or f'{vm_ip} | FAILED' in output:
                vm_results[vm_name] = {'ip': vm_ip, 'status': 'failed', 'winrm': False}
            else:
                vm_results[vm_name] = {'ip': vm_ip, 'status': 'unknown', 'winrm': False}

        healthy_count = sum(1 for v in vm_results.values() if v['status'] == 'healthy')
        total_count = len(vm_results)

        return jsonify({
            'success': True,
            'lab_name': lab_name,
            'healthy': healthy_count,
            'total': total_count,
            'all_healthy': healthy_count == total_count,
            'vms': vm_results,
            'raw_output': output
        })

    except subprocess.TimeoutExpired:
        return jsonify({
            'success': False,
            'error': 'Verification timed out (60s) — Ansible win_ping may be slow'
        }), 504
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
        
        # Run terraform destroy with increased timeout
        result = subprocess.run(
            ['terraform', 'destroy', '-auto-approve'],
            cwd=str(lab_tf_dir),
            capture_output=True,
            text=True,
            timeout=TERRAFORM_DESTROY_TIMEOUT  # 60 minutes for complex deployments
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
    goad_dir = get_goad_dir()
    project_name = request.args.get('project')
    lab_name = None

    if project_name:
        # Derive lab type from deployment state file
        project_root_path = get_project_root()
        state_file = project_root_path / "logs" / "deployment_state" / f"{project_name}.state.json"
        if state_file.exists():
            try:
                state_data = json.loads(state_file.read_text())
                deploy_type = state_data.get("deployment_type", "")
                if deploy_type:
                    from webapp.backend.utils.config_parser import get_goad_lab_type
                    lab_name = get_goad_lab_type(deploy_type)
            except Exception:
                pass
        # Fallback: parse from project name pattern
        if not lab_name:
            for dt, info in DEPLOYMENT_TYPE_MAP.items():
                if dt.replace('-', '_') in project_name and info.get('goad_lab'):
                    lab_name = info['goad_lab']
                    break

    # Existing marker-based fallback when no project specified or project lookup failed
    if not lab_name:
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
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    try:
        lab_info = GOAD_LABS.get(lab_name, {})
        
        # Lab-specific credential configurations
        # These are from official GOAD documentation - intentionally vulnerable
        LAB_CREDENTIALS = {
            'GOAD-Mini': {
                'domains': [
                    {'name': 'SEVENKINGDOMS', 'fqdn': 'sevenkingdoms.local', 'dc': 'DC01'}
                ],
                'key_users': [
                    {'username': 'Administrator', 'password': 'vagrant', 'domain': 'SEVENKINGDOMS', 'role': 'Domain Admin'},
                    {'username': 'cersei.lannister', 'password': 'vagrant', 'domain': 'SEVENKINGDOMS', 'role': 'Domain User'},
                    {'username': 'jaime.lannister', 'password': 'vagrant', 'domain': 'SEVENKINGDOMS', 'role': 'Domain User'},
                ]
            },
            'GOAD-Light': {
                'domains': [
                    {'name': 'SEVENKINGDOMS', 'fqdn': 'sevenkingdoms.local', 'dc': 'DC01'},
                    {'name': 'NORTH', 'fqdn': 'north.sevenkingdoms.local', 'dc': 'DC02'}
                ],
                'key_users': [
                    {'username': 'Administrator', 'password': 'vagrant', 'domain': 'SEVENKINGDOMS', 'role': 'Domain Admin'},
                    {'username': 'Administrator', 'password': 'vagrant', 'domain': 'NORTH', 'role': 'Domain Admin'},
                    {'username': 'cersei.lannister', 'password': 'vagrant', 'domain': 'SEVENKINGDOMS', 'role': 'Domain User'},
                    {'username': 'eddard.stark', 'password': 'vagrant', 'domain': 'NORTH', 'role': 'Domain User'},
                ]
            },
            'SCCM': {
                'domains': [
                    {'name': 'SCCM', 'fqdn': 'sccm.lab', 'dc': 'DC01'}
                ],
                'key_users': [
                    {'username': 'Administrator', 'password': 'vagrant', 'domain': 'SCCM', 'role': 'Domain Admin'},
                    {'username': 'sccm_admin', 'password': 'vagrant', 'domain': 'SCCM', 'role': 'SCCM Admin'},
                ],
                'local_admin_passwords': {
                    'dc01': 'AZERTY*qsdfg',
                    'srv01': 'NgtI75cKV+Pu',
                    'srv02': 'NgtazecKV+Pu',
                    'ws01': 'EP+xh7Rk6j90',
                },
                'special_accounts': [
                    {'name': 'NAA (Network Access Account)', 'note': 'Check SCCM for credentials - often misconfigured'},
                    {'name': 'Task Sequence Account', 'note': 'Used for OSD - may have elevated privileges'},
                ]
            },
            'GOAD': {
                'domains': [
                    {'name': 'SEVENKINGDOMS', 'fqdn': 'sevenkingdoms.local', 'dc': 'DC01'},
                    {'name': 'NORTH', 'fqdn': 'north.sevenkingdoms.local', 'dc': 'DC02'},
                    {'name': 'ESSOS', 'fqdn': 'essos.local', 'dc': 'DC03'}
                ],
                'key_users': [
                    {'username': 'Administrator', 'password': 'vagrant', 'domain': 'SEVENKINGDOMS', 'role': 'Domain Admin'},
                    {'username': 'Administrator', 'password': 'vagrant', 'domain': 'NORTH', 'role': 'Domain Admin'},
                    {'username': 'Administrator', 'password': 'vagrant', 'domain': 'ESSOS', 'role': 'Domain Admin'},
                    {'username': 'cersei.lannister', 'password': 'vagrant', 'domain': 'SEVENKINGDOMS', 'role': 'Domain User'},
                    {'username': 'eddard.stark', 'password': 'vagrant', 'domain': 'NORTH', 'role': 'Domain User'},
                    {'username': 'daenerys.targaryen', 'password': 'vagrant', 'domain': 'ESSOS', 'role': 'Domain User'},
                ],
                'trusts': [
                    {'from': 'NORTH', 'to': 'SEVENKINGDOMS', 'type': 'Parent-Child'},
                    {'from': 'ESSOS', 'to': 'SEVENKINGDOMS', 'type': 'External (Bidirectional)'},
                ]
            },
            'NHA': {
                'domains': [
                    {'name': 'NINJA', 'fqdn': 'ninja.hack', 'dc': 'DC01'},
                    {'name': 'ACADEMY', 'fqdn': 'academy.ninja.lan', 'dc': 'DC02'}
                ],
                'key_users': [
                    {'username': 'Administrator', 'password': 'vagrant', 'domain': 'NINJA', 'role': 'Domain Admin'},
                    {'username': 'Administrator', 'password': 'vagrant', 'domain': 'ACADEMY', 'role': 'Domain Admin'},
                ],
                'note': 'NHA is a challenge lab - discover the attack paths yourself! Default password is "vagrant".'
            }
        }
        
        # Get lab-specific creds or use defaults
        lab_creds = LAB_CREDENTIALS.get(lab_name, {})
        
        # Build credentials response
        credentials = {
            'lab_name': lab_name,
            'lab_display_name': lab_info.get('display_name', lab_name),
            'domains': lab_creds.get('domains', []),
            'default_password': 'vagrant',  # Standard GOAD domain password (post AD provisioning)
            'local_admin_passwords': lab_creds.get('local_admin_passwords', {}),
            'default_users': [
                {'username': 'Administrator', 'password': 'vagrant', 'domain': 'Local Admin', 'note': 'Local admin on all VMs'},
                {'username': 'vagrant', 'password': 'vagrant', 'domain': 'Local User', 'note': 'Default vagrant user'},
            ],
            'domain_admins': [],
            'key_users': lab_creds.get('key_users', []),
            'trusts': lab_creds.get('trusts', []),
            'special_accounts': lab_creds.get('special_accounts', []),
            'inventory_path': str(goad_dir / 'ad' / lab_name / 'data' / 'inventory'),
            'note': lab_creds.get('note', 'Default GOAD password is "vagrant" for all users. Check inventory for specific accounts.')
        }
        
        # Add domain admins from domains list
        for domain in lab_creds.get('domains', []):
            if domain.get('name') != 'Hidden':
                credentials['domain_admins'].append({
                    'username': 'Administrator',
                    'password': 'vagrant',
                    'domain': domain.get('name'),
                    'fqdn': domain.get('fqdn'),
                    'dc': domain.get('dc')
                })
        
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
    """Start stopped GOAD lab VMs using AWS EC2 API directly.

    Accepts optional ``?project=`` query param (or ``project_name`` in the
    JSON body) to scope region/tag lookup to a specific per-project tfvars.
    """
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

        # Per-project tfvars wins over the global tfvars when ?project= is set.
        from webapp.backend.utils.config_parser import ConfigParser
        from webapp.backend.utils.tfvars_path import resolve_tfvars_path
        body = request.get_json(silent=True) or {}
        project_param = request.args.get('project') or body.get('project_name')
        project_root = get_project_root()
        config_dir = project_root / "configs"
        default_tfvars = config_dir / "terraform.tfvars"
        tfvars_file = resolve_tfvars_path(project_param, config_dir, default_tfvars)
        if not tfvars_file.exists():
            tfvars_file = default_tfvars

        config = ConfigParser.parse_tfvars(tfvars_file) if tfvars_file.exists() else {}
        aws_region = config.get('aws_region', 'eu-central-1')
        project_name = (project_param or config.get('project_name', '')).strip()
        
        # Use AWS EC2 API to start instances
        ec2 = boto3.client('ec2', region_name=aws_region)
        
        # Find GOAD instances by tags
        filters = [
            {'Name': 'instance-state-name', 'Values': ['stopped']},
            {'Name': 'tag:Lab', 'Values': [lab_name.lower().replace('-', '')]}
        ]
        
        # Also try with Project tag if available
        if project_name:
            filters.append({'Name': 'tag:Project', 'Values': [project_name]})
        
        response = ec2.describe_instances(Filters=filters)
        
        instance_ids = []
        for reservation in response.get('Reservations', []):
            for instance in reservation.get('Instances', []):
                instance_ids.append(instance['InstanceId'])
        
        if not instance_ids:
            return jsonify({
                'success': True,
                'message': f'No stopped instances found for GOAD {lab_name}',
                'started_count': 0
            })
        
        # Start instances
        ec2.start_instances(InstanceIds=instance_ids)
        
        return jsonify({
            'success': True,
            'message': f'Started {len(instance_ids)} GOAD {lab_name} instances',
            'started_count': len(instance_ids),
            'instance_ids': instance_ids
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/stop', methods=['POST'])
def stop_goad():
    """Stop GOAD lab VMs to save costs using AWS EC2 API directly.

    Accepts optional ``?project=`` (or body ``project_name``) to target a
    specific per-project tfvars for region/tag lookup.
    """
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

        # Per-project tfvars wins over the global tfvars when ?project= is set.
        from webapp.backend.utils.config_parser import ConfigParser
        from webapp.backend.utils.tfvars_path import resolve_tfvars_path
        body = request.get_json(silent=True) or {}
        project_param = request.args.get('project') or body.get('project_name')
        project_root = get_project_root()
        config_dir = project_root / "configs"
        default_tfvars = config_dir / "terraform.tfvars"
        tfvars_file = resolve_tfvars_path(project_param, config_dir, default_tfvars)
        if not tfvars_file.exists():
            tfvars_file = default_tfvars

        config = ConfigParser.parse_tfvars(tfvars_file) if tfvars_file.exists() else {}
        aws_region = config.get('aws_region', 'eu-central-1')
        project_name = (project_param or config.get('project_name', '')).strip()
        
        # Use AWS EC2 API to stop instances
        ec2 = boto3.client('ec2', region_name=aws_region)
        
        # Find GOAD instances by tags
        filters = [
            {'Name': 'instance-state-name', 'Values': ['running']},
            {'Name': 'tag:Lab', 'Values': [lab_name.lower().replace('-', '')]}
        ]
        
        # Also try with Project tag if available
        if project_name:
            filters.append({'Name': 'tag:Project', 'Values': [project_name]})
        
        response = ec2.describe_instances(Filters=filters)
        
        instance_ids = []
        for reservation in response.get('Reservations', []):
            for instance in reservation.get('Instances', []):
                instance_ids.append(instance['InstanceId'])
        
        if not instance_ids:
            return jsonify({
                'success': True,
                'message': f'No running instances found for GOAD {lab_name}',
                'stopped_count': 0
            })
        
        # Stop instances
        ec2.stop_instances(InstanceIds=instance_ids)
        
        return jsonify({
            'success': True,
            'message': f'Stopped {len(instance_ids)} GOAD {lab_name} instances',
            'stopped_count': len(instance_ids),
            'instance_ids': instance_ids
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/instance-status', methods=['GET'])
def get_goad_instance_status():
    """Get the current status of all GOAD EC2 instances.

    Accepts optional ``?project=`` to scope region/tag lookup to a
    specific per-project tfvars instead of the legacy global tfvars.
    """
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

        # Per-project tfvars wins over the global tfvars when ?project= is set.
        from webapp.backend.utils.config_parser import ConfigParser
        from webapp.backend.utils.tfvars_path import resolve_tfvars_path
        project_param = request.args.get('project')
        project_root = get_project_root()
        config_dir = project_root / "configs"
        default_tfvars = config_dir / "terraform.tfvars"
        tfvars_file = resolve_tfvars_path(project_param, config_dir, default_tfvars)
        if not tfvars_file.exists():
            tfvars_file = default_tfvars

        config = ConfigParser.parse_tfvars(tfvars_file) if tfvars_file.exists() else {}
        aws_region = config.get('aws_region', 'eu-central-1')
        project_name = (project_param or config.get('project_name', '')).strip()
        
        # Use AWS EC2 API to get instance status
        ec2 = boto3.client('ec2', region_name=aws_region)
        
        # Find GOAD instances by tags
        filters = [
            {'Name': 'tag:Lab', 'Values': [lab_name.lower().replace('-', '')]}
        ]
        
        if project_name:
            filters.append({'Name': 'tag:Project', 'Values': [project_name]})
        
        response = ec2.describe_instances(Filters=filters)
        
        instances = []
        status_counts = {'running': 0, 'stopped': 0, 'pending': 0, 'stopping': 0, 'terminated': 0}
        
        for reservation in response.get('Reservations', []):
            for instance in reservation.get('Instances', []):
                state = instance['State']['Name']
                status_counts[state] = status_counts.get(state, 0) + 1
                
                # Get instance name from tags
                name = 'Unknown'
                role = 'Unknown'
                for tag in instance.get('Tags', []):
                    if tag['Key'] == 'Name':
                        name = tag['Value']
                    if tag['Key'] == 'Role':
                        role = tag['Value']
                
                instances.append({
                    'id': instance['InstanceId'],
                    'name': name,
                    'role': role,
                    'state': state,
                    'type': instance['InstanceType'],
                    'private_ip': instance.get('PrivateIpAddress'),
                    'public_ip': instance.get('PublicIpAddress')
                })
        
        return jsonify({
            'success': True,
            'lab_name': lab_name,
            'region': aws_region,
            'instances': instances,
            'status_counts': status_counts,
            'total_instances': len(instances)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

