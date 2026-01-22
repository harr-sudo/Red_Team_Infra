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
import json
from werkzeug.utils import secure_filename

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from webapp.backend.services.terraform_service import TerraformService, get_terraform_service
from webapp.backend.utils.goad_template_processor import get_lab_info, extract_vm_info

bp = Blueprint('deploy', __name__)

# File storage directory (local to user's machine)
UPLOAD_FOLDER = project_root / "uploads"
CS_CLIENT_FOLDER = project_root / "uploads_client"  # Separate folder for CS Client
ALLOWED_EXTENSIONS = {'tar', 'gz', 'zip', 'tar.gz'}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB

# SSH keys directory
SSH_KEYS_FOLDER = project_root / "ssh_keys"

# Ensure directories exist
UPLOAD_FOLDER.mkdir(exist_ok=True)
CS_CLIENT_FOLDER.mkdir(exist_ok=True)
SSH_KEYS_FOLDER.mkdir(exist_ok=True)

# =============================================================================
# MULTI-PROJECT DEPLOYMENT STATE
# =============================================================================

# Track deployments by project name (workspace)
# Structure: {"project_name": {"status": "running", "logs": [], ...}}
deployment_states = {}

# =============================================================================
# DEPLOYMENT HISTORY HELPERS (defined early for use by add_log)
# =============================================================================

HISTORY_FILE = project_root / "logs" / "deployment_history.json"

def load_deployment_history():
    """Load deployment history from file"""
    try:
        if HISTORY_FILE.exists():
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading deployment history: {e}")
    return []

def save_deployment_history(history):
    """Save deployment history to file"""
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history[-500:], f, indent=2)  # Keep last 500 entries
    except Exception as e:
        print(f"Error saving deployment history: {e}")

def add_history_entry(message, level='info', details=None, project_name=None, entry_type=None):
    """Add an entry to deployment history
    
    Args:
        message: Log message
        level: Log level (info, success, error, warning)
        details: Additional details
        project_name: Project/workspace name
        entry_type: Type of entry ('plan', 'deployment', etc.) - used to filter in UI
    """
    from datetime import datetime
    history = load_deployment_history()
    entry = {
        'timestamp': datetime.now().isoformat(),
        'level': level,
        'message': message,
        'details': details
    }
    if project_name:
        entry['project_name'] = project_name
    if entry_type:
        entry['entry_type'] = entry_type
    history.append(entry)
    save_deployment_history(history)

# =============================================================================
# HELPER FUNCTIONS FOR MULTI-PROJECT STATE
# =============================================================================

def get_project_state(project_name: str) -> dict:
    """Get or create deployment state for a project"""
    if project_name not in deployment_states:
        deployment_states[project_name] = create_empty_state()
    return deployment_states[project_name]

def create_empty_state() -> dict:
    """Create a new empty deployment state"""
    return {
    "status": "idle",  # idle, running, success, error
    "step": "",
    "output": "",
    "error": None,
    "deployment_type": None,
        "goad_ansible_status": None,
    "started_at": None,
    "completed_at": None,
    "progress_percent": 0,
    "current_phase": "",
    "phases_completed": [],
        "logs": []
    }

def get_active_deployments() -> list:
    """Get list of currently running deployments"""
    return [
        {"project_name": name, **state}
        for name, state in deployment_states.items()
        if state.get("status") == "running"
    ]

# =============================================================================
# BACKWARD COMPATIBILITY: Single deployment state (for existing code)
# This will be deprecated - use deployment_states[project_name] instead
# =============================================================================

deployment_state = create_empty_state()

# Deployment phases with estimated times (seconds)
DEPLOYMENT_PHASES = {
    "c2": [
        {"name": "init", "label": "Initializing Terraform", "est_time": 15},
        {"name": "validate", "label": "Validating Configuration", "est_time": 5},
        {"name": "plan", "label": "Planning Deployment", "est_time": 30},
        {"name": "apply_vpc", "label": "Creating VPC & Networking", "est_time": 60},
        {"name": "apply_security", "label": "Creating Security Groups", "est_time": 30},
        {"name": "apply_instances", "label": "Launching EC2 Instances", "est_time": 120},
        {"name": "apply_config", "label": "Configuring Instances", "est_time": 180},
        {"name": "outputs", "label": "Retrieving Outputs", "est_time": 10},
    ],
    "goad": [
        {"name": "init", "label": "Initializing Terraform", "est_time": 15},
        {"name": "validate", "label": "Validating Configuration", "est_time": 5},
        {"name": "plan", "label": "Planning Deployment", "est_time": 30},
        {"name": "apply_vpc", "label": "Creating VPC & Networking", "est_time": 60},
        {"name": "apply_jumpbox", "label": "Launching Jumpbox", "est_time": 90},
        {"name": "apply_windows", "label": "Launching Windows VMs", "est_time": 180},
        {"name": "ansible_prep", "label": "Preparing Ansible", "est_time": 30},
        {"name": "ansible_ad", "label": "Configuring Active Directory", "est_time": 600},
        {"name": "outputs", "label": "Retrieving Outputs", "est_time": 10},
    ],
    "combined": [
        {"name": "init", "label": "Initializing Terraform", "est_time": 15},
        {"name": "validate", "label": "Validating Configuration", "est_time": 5},
        {"name": "plan", "label": "Planning Deployment", "est_time": 45},
        {"name": "apply_c2_vpc", "label": "Creating C2 VPC", "est_time": 60},
        {"name": "apply_goad_vpc", "label": "Creating GOAD VPC", "est_time": 60},
        {"name": "apply_peering", "label": "Setting up VPC Peering", "est_time": 30},
        {"name": "apply_c2", "label": "Launching C2 Servers", "est_time": 150},
        {"name": "apply_goad", "label": "Launching GOAD VMs", "est_time": 240},
        {"name": "ansible_ad", "label": "Configuring Active Directory", "est_time": 600},
        {"name": "outputs", "label": "Retrieving Outputs", "est_time": 10},
    ]
}

def add_log(message, log_type="info", project_name=None):
    """Add a log entry to deployment state and persistent history"""
    # Use project-specific state if provided
    if project_name and project_name in deployment_states:
        state = deployment_states[project_name]
    else:
        state = deployment_state
    
    state["logs"].append({
        "timestamp": time.time(),
        "message": message,
        "type": log_type  # info, success, warning, error
    })
    # Also save to persistent history
    add_history_entry(message, log_type, project_name=project_name)

def update_phase(phase_name, deployment_type="c2", project_name=None):
    """Update current phase and calculate progress"""
    # Use project-specific state if provided
    if project_name and project_name in deployment_states:
        state = deployment_states[project_name]
    else:
        state = deployment_state
    
    phases = DEPLOYMENT_PHASES.get(deployment_type, DEPLOYMENT_PHASES["c2"])
    
    # Find current phase index
    current_idx = -1
    for i, phase in enumerate(phases):
        if phase["name"] == phase_name:
            current_idx = i
            break
    
    if current_idx >= 0:
        # Calculate progress percentage
        state["progress_percent"] = int((current_idx / len(phases)) * 100)
        state["current_phase"] = phases[current_idx]["label"]
        state["step"] = phases[current_idx]["label"]
        
        # Calculate estimated time remaining
        remaining_time = sum(p["est_time"] for p in phases[current_idx:])
        state["est_remaining_seconds"] = remaining_time
        
        add_log(f"Started: {phases[current_idx]['label']}", "info", project_name)

def complete_phase(phase_name, deployment_type="c2", project_name=None):
    """Mark a phase as completed"""
    # Use project-specific state if provided
    if project_name and project_name in deployment_states:
        state = deployment_states[project_name]
    else:
        state = deployment_state
    
    phases = DEPLOYMENT_PHASES.get(deployment_type, DEPLOYMENT_PHASES["c2"])
    
    for phase in phases:
        if phase["name"] == phase_name:
            if phase_name not in state["phases_completed"]:
                state["phases_completed"].append(phase_name)
                add_log(f"Completed: {phase['label']}", "success", project_name)
            break

# Default terraform service (for backward compatibility)
terraform_service = TerraformService(project_root)

def get_service_for_project(project_name: str) -> TerraformService:
    """Get a TerraformService instance for a specific project/workspace"""
    return get_terraform_service(project_root, project_name)

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS or \
           filename.endswith('.tar.gz')

def update_tfvars_cs_path(tfvars_file, s3_uri):
    """Update terraform.tfvars with the Cobalt Strike S3 path"""
    try:
        if not tfvars_file.exists():
            return False
        
        content = tfvars_file.read_text()
        
        # Check if cobalt_strike_archive_s3_path already exists
        if 'cobalt_strike_archive_s3_path' in content:
            # Update existing value
            import re
            content = re.sub(
                r'cobalt_strike_archive_s3_path\s*=\s*"[^"]*"',
                f'cobalt_strike_archive_s3_path = "{s3_uri}"',
                content
            )
        else:
            # Add new line
            content += f'\n# Cobalt Strike S3 Path (auto-generated)\ncobalt_strike_archive_s3_path = "{s3_uri}"\n'
        
        tfvars_file.write_text(content)
        return True
    except Exception as e:
        print(f"Error updating tfvars with CS path: {e}")
        return False

def update_tfvars_cs_client_path(tfvars_file, s3_uri):
    """Update terraform.tfvars with the Cobalt Strike Client S3 path (for Attack Box)"""
    try:
        if not tfvars_file.exists():
            return False
        
        content = tfvars_file.read_text()
        
        # Check if cs_client_s3_path already exists
        if 'cs_client_s3_path' in content:
            # Update existing value
            import re
            content = re.sub(
                r'cs_client_s3_path\s*=\s*"[^"]*"',
                f'cs_client_s3_path = "{s3_uri}"',
                content
            )
        else:
            # Add new line
            content += f'\n# Cobalt Strike Client S3 Path for Attack Box (auto-generated)\ncs_client_s3_path = "{s3_uri}"\n'
        
        tfvars_file.write_text(content)
        return True
    except Exception as e:
        print(f"Error updating tfvars with CS Client path: {e}")
        return False

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

def run_deployment(project_name: str = None):
    """Run deployment in background thread with enhanced progress tracking"""
    global deployment_state
    
    # Use project-specific state if provided
    if project_name and project_name in deployment_states:
        state = deployment_states[project_name]
        service = get_service_for_project(project_name)
    else:
        state = deployment_state
        service = terraform_service
        project_name = None  # For logging
    
    try:
        # Reset state
        state["status"] = "running"
        state["step"] = "Initializing..."
        state["output"] = ""
        state["error"] = None
        state["started_at"] = time.time()
        state["completed_at"] = None
        state["progress_percent"] = 0
        state["phases_completed"] = []
        state["logs"] = []
        state["est_remaining_seconds"] = 0
        
        # Determine deployment type from config
        from webapp.backend.utils.config_parser import ConfigParser
        config = ConfigParser.parse_tfvars(service.tfvars_file) if service.tfvars_file.exists() else {}
        
        deploy_type = config.get('deployment_type', 'c2-adhoc')
        if 'combined' in deploy_type:
            phase_type = "combined"
        elif 'goad' in deploy_type:
            phase_type = "goad"
        else:
            phase_type = "c2"
        
        state["deployment_type"] = deploy_type
        add_log(f"Starting deployment: {deploy_type}", "info", project_name)
        
        # Phase 1: Initialize
        update_phase("init", phase_type, project_name)
        result = service.init()
        if not result["success"]:
            state["status"] = "error"
            state["error"] = result.get("stderr", "Terraform init failed")
            add_log(f"Error: {state['error']}", "error", project_name)
            return
        complete_phase("init", phase_type, project_name)
        
        # Ensure workspace exists (for multi-project)
        if project_name:
            ws_result = service.ensure_workspace()
            if not ws_result["success"]:
                state["status"] = "error"
                state["error"] = ws_result.get("stderr", "Failed to setup workspace")
                add_log(f"Error: {state['error']}", "error", project_name)
                return
            add_log(f"Using workspace: {service.workspace_name}", "info", project_name)
        
        # Phase 2: Validate
        update_phase("validate", phase_type, project_name)
        result = service.validate()
        if not result["success"]:
            state["status"] = "error"
            state["error"] = result.get("stderr", "Validation failed")
            add_log(f"Error: {state['error']}", "error", project_name)
            return
        complete_phase("validate", phase_type, project_name)
        
        # Phase 3: Plan
        update_phase("plan", phase_type, project_name)
        result = service.plan()
        if not result["success"] and result["exit_code"] != 2:  # 2 means changes detected
            state["status"] = "error"
            state["error"] = result.get("stderr", "Plan failed")
            add_log(f"Error: {state['error']}", "error", project_name)
            return
        complete_phase("plan", phase_type, project_name)
        
        # Phase 4+: Apply (this is the long one)
        # Note: Terraform apply handles all resources together, but we simulate progress
        if phase_type == "c2":
            update_phase("apply_vpc", phase_type, project_name)
        elif phase_type == "goad":
            update_phase("apply_vpc", phase_type, project_name)
        else:
            update_phase("apply_c2_vpc", phase_type, project_name)
        
        # Check if we need to upload Cobalt Strike to S3
        # For GOAD or C2 deployments that use CS, we need to:
        # 1. First create just the S3 bucket
        # 2. Upload the CS file to S3
        # 3. Then apply the rest (EC2 instances will have the file available)
        needs_cs_upload = (phase_type == "goad" or phase_type == "c2" or phase_type == "combined")
        
        # Check if there's a local CS file to upload (Team Server archive)
        local_cs_file = None
        if needs_cs_upload:
            cs_files = [f for f in UPLOAD_FOLDER.glob("*") if f.is_file() and allowed_file(f.name)]
            if cs_files:
                local_cs_file = max(cs_files, key=lambda f: f.stat().st_mtime)
                add_log(f"Found Cobalt Strike file: {local_cs_file.name}", "info", project_name)
        
        # Check if there's a CS Client file to upload (for Attack Box)
        local_cs_client_file = None
        if needs_cs_upload:
            cs_client_files = [f for f in CS_CLIENT_FOLDER.glob("*") if f.is_file() and allowed_file(f.name)]
            if cs_client_files:
                local_cs_client_file = max(cs_client_files, key=lambda f: f.stat().st_mtime)
                add_log(f"Found CS Client file: {local_cs_client_file.name}", "info", project_name)
        
        if local_cs_file or local_cs_client_file:
            # Phase: Create S3 bucket first (targeted apply)
            add_log("Creating S3 bucket for Cobalt Strike files...", "info", project_name)
            result = service.apply_target("module.cs_storage")
        
        if not result["success"]:
            # If bucket already exists, that's OK - continue
            if "already exists" not in str(result.get("stderr", "")):
                state["status"] = "error"
                state["error"] = result.get("stderr", "Failed to create S3 bucket")
                add_log(f"Error: {state['error']}", "error", project_name)
                return
            
        add_log("S3 bucket created successfully", "success", project_name)
        
        # Phase: Upload CS file to S3 (Team Server archive)
        if local_cs_file:
            add_log("Uploading Cobalt Strike to S3...", "info", project_name)
            try:
                from webapp.backend.utils.s3_upload import upload_cs_file, find_cs_bucket, S3UploadError
                
                # Find the bucket that was just created
                bucket_name = find_cs_bucket(project_name, config.get('aws_region', 'us-east-1'))
                
                if bucket_name:
                    s3_uri, _ = upload_cs_file(
                        str(local_cs_file),
                        project_name,
                        config.get('aws_region', 'us-east-1'),
                        bucket_name=bucket_name
                    )
                    add_log(f"Uploaded Cobalt Strike to {s3_uri}", "success", project_name)
                    
                    # Update tfvars with the S3 path so EC2 user_data can find it
                    update_tfvars_cs_path(service.tfvars_file, s3_uri)
                    add_log("Updated configuration with S3 path", "info", project_name)
                else:
                    add_log("Warning: Could not find S3 bucket for CS upload", "warning", project_name)
                    
            except Exception as e:
                add_log(f"Warning: Failed to upload CS to S3: {str(e)}", "warning", project_name)
                # Continue anyway - CS won't be auto-installed but deployment can proceed
        
        # Phase: Upload CS Client file to S3 (for Attack Box)
        if local_cs_client_file:
            add_log("Uploading CS Client to S3...", "info", project_name)
            try:
                from webapp.backend.utils.s3_upload import upload_cs_file, find_cs_bucket, S3UploadError
                
                # Find the bucket
                bucket_name = find_cs_bucket(project_name, config.get('aws_region', 'us-east-1'))
                
                if bucket_name:
                    # Upload with a different key prefix for the client
                    s3_client_uri, _ = upload_cs_file(
                        str(local_cs_client_file),
                        project_name,
                        config.get('aws_region', 'us-east-1'),
                        bucket_name=bucket_name,
                        s3_key_prefix="cs-client/"
                    )
                    add_log(f"Uploaded CS Client to {s3_client_uri}", "success", project_name)
                    
                    # Update tfvars with the CS Client S3 path
                    update_tfvars_cs_client_path(service.tfvars_file, s3_client_uri)
                    add_log("Updated configuration with CS Client S3 path", "info", project_name)
                else:
                    add_log("Warning: Could not find S3 bucket for CS Client upload", "warning", project_name)
                    
            except Exception as e:
                add_log(f"Warning: Failed to upload CS Client to S3: {str(e)}", "warning", project_name)
                # Continue anyway - CS Client won't be auto-installed but deployment can proceed
        
        # Now apply the rest of the infrastructure
        # Use apply_fresh() instead of apply() because the targeted apply above
        # changed the state, making the saved plan file stale
        add_log("Applying Terraform changes (this may take 5-15 minutes)...", "info", project_name)
        result = service.apply_fresh()
        
        if not result["success"]:
            state["status"] = "error"
            state["error"] = result.get("stderr", "Apply failed")
            add_log(f"Error: {state['error']}", "error", project_name)
            return
        
        # Mark infrastructure phases complete
        if phase_type == "c2":
            for p in ["apply_vpc", "apply_security", "apply_instances", "apply_config"]:
                complete_phase(p, phase_type, project_name)
        elif phase_type == "goad":
            for p in ["apply_vpc", "apply_jumpbox", "apply_windows"]:
                complete_phase(p, phase_type, project_name)
        else:
            for p in ["apply_c2_vpc", "apply_goad_vpc", "apply_peering", "apply_c2", "apply_goad"]:
                complete_phase(p, phase_type, project_name)
        
        # Phase: Get outputs
        update_phase("outputs", phase_type, project_name)
        result = service.output()
        complete_phase("outputs", phase_type, project_name)
        
        # Success!
        state["status"] = "success"
        state["step"] = "Deployment complete"
        state["progress_percent"] = 100
        state["completed_at"] = time.time()
        state["output"] = result.get("outputs", {})
        state["est_remaining_seconds"] = 0
        
        elapsed = int(state["completed_at"] - state["started_at"])
        add_log(f"Deployment completed successfully in {elapsed // 60}m {elapsed % 60}s", "success", project_name)
        
        # Save deployed resources to history for this project
        save_deployment_resources(project_name, service, deploy_type)
        
    except Exception as e:
        state["status"] = "error"
        state["error"] = str(e)
        state["completed_at"] = time.time()
        add_log(f"Unexpected error: {str(e)}", "error", project_name)


def save_deployment_resources(project_name: str, service: TerraformService, deployment_type: str):
    """
    Save the list of deployed resources for a project after successful deployment.
    This allows tracking resources per deployment even with multiple concurrent deployments.
    """
    import boto3
    from webapp.backend.utils.config_parser import ConfigParser
    from datetime import datetime
    
    try:
        # Get config for region
        config = ConfigParser.parse_tfvars(service.tfvars_file) if service.tfvars_file.exists() else {}
        aws_region = config.get('aws_region', 'us-east-1')
        
        # Query AWS for all resources with this project tag
        resources = []
        ec2 = boto3.client('ec2', region_name=aws_region)
        
        # EC2 Instances
        try:
            response = ec2.describe_instances(
                Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
            )
            for reservation in response.get('Reservations', []):
                for instance in reservation.get('Instances', []):
                    name = next((t['Value'] for t in instance.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                    role = next((t['Value'] for t in instance.get('Tags', []) if t['Key'] == 'Role'), '')
                    resources.append({
                        'type': 'ec2',
                        'id': instance['InstanceId'],
                        'name': name,
                        'role': role,
                        'state': instance['State']['Name'],
                        'instance_type': instance['InstanceType'],
                        'private_ip': instance.get('PrivateIpAddress'),
                        'public_ip': instance.get('PublicIpAddress')
                    })
        except Exception as e:
            print(f"Error fetching EC2 instances: {e}")
        
        # VPCs
        try:
            response = ec2.describe_vpcs(
                Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
            )
            for vpc in response.get('Vpcs', []):
                name = next((t['Value'] for t in vpc.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                resources.append({
                    'type': 'vpc',
                    'id': vpc['VpcId'],
                    'name': name,
                    'state': vpc['State'],
                    'cidr': vpc['CidrBlock']
                })
        except Exception as e:
            print(f"Error fetching VPCs: {e}")
        
        # Subnets
        try:
            response = ec2.describe_subnets(
                Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
            )
            for subnet in response.get('Subnets', []):
                name = next((t['Value'] for t in subnet.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                resources.append({
                    'type': 'subnet',
                    'id': subnet['SubnetId'],
                    'name': name,
                    'state': subnet['State'],
                    'cidr': subnet['CidrBlock'],
                    'az': subnet['AvailabilityZone']
                })
        except Exception as e:
            print(f"Error fetching subnets: {e}")
        
        # Security Groups
        try:
            response = ec2.describe_security_groups(
                Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
            )
            for sg in response.get('SecurityGroups', []):
                resources.append({
                    'type': 'security_group',
                    'id': sg['GroupId'],
                    'name': sg['GroupName'],
                    'state': 'active',
                    'description': sg.get('Description', '')[:100]
                })
        except Exception as e:
            print(f"Error fetching security groups: {e}")
        
        # NAT Gateways
        try:
            response = ec2.describe_nat_gateways(
                Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
            )
            for nat in response.get('NatGateways', []):
                name = next((t['Value'] for t in nat.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                public_ip = nat.get('NatGatewayAddresses', [{}])[0].get('PublicIp', 'N/A')
                resources.append({
                    'type': 'nat_gateway',
                    'id': nat['NatGatewayId'],
                    'name': name,
                    'state': nat['State'],
                    'public_ip': public_ip
                })
        except Exception as e:
            print(f"Error fetching NAT gateways: {e}")
        
        # Elastic IPs
        try:
            response = ec2.describe_addresses(
                Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
            )
            for eip in response.get('Addresses', []):
                name = next((t['Value'] for t in eip.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                resources.append({
                    'type': 'elastic_ip',
                    'id': eip.get('AllocationId', 'N/A'),
                    'name': name,
                    'state': 'associated' if eip.get('InstanceId') else 'available',
                    'public_ip': eip.get('PublicIp')
                })
        except Exception as e:
            print(f"Error fetching Elastic IPs: {e}")
        
        # S3 Buckets
        try:
            s3 = boto3.client('s3', region_name=aws_region)
            response = s3.list_buckets()
            project_prefix = project_name.lower().replace('_', '-')
            for bucket in response.get('Buckets', []):
                if bucket['Name'].lower().startswith(project_prefix):
                    resources.append({
                        'type': 's3_bucket',
                        'id': bucket['Name'],
                        'name': bucket['Name'],
                        'state': 'available',
                        'created': bucket['CreationDate'].isoformat()
                    })
        except Exception as e:
            print(f"Error fetching S3 buckets: {e}")
        
        # Key Pairs
        try:
            response = ec2.describe_key_pairs(
                Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
            )
            for kp in response.get('KeyPairs', []):
                resources.append({
                    'type': 'key_pair',
                    'id': kp.get('KeyPairId', kp['KeyName']),
                    'name': kp['KeyName'],
                    'state': 'available',
                    'key_type': kp.get('KeyType', 'rsa')
                })
        except Exception as e:
            print(f"Error fetching key pairs: {e}")
        
        # Internet Gateways
        try:
            response = ec2.describe_internet_gateways(
                Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
            )
            for igw in response.get('InternetGateways', []):
                name = next((t['Value'] for t in igw.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                attached = 'attached' if igw.get('Attachments') else 'detached'
                resources.append({
                    'type': 'internet_gateway',
                    'id': igw['InternetGatewayId'],
                    'name': name,
                    'state': attached
                })
        except Exception as e:
            print(f"Error fetching Internet Gateways: {e}")
        
        # Route Tables
        try:
            response = ec2.describe_route_tables(
                Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
            )
            for rt in response.get('RouteTables', []):
                name = next((t['Value'] for t in rt.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                route_count = len(rt.get('Routes', []))
                resources.append({
                    'type': 'route_table',
                    'id': rt['RouteTableId'],
                    'name': name,
                    'state': 'active',
                    'route_count': route_count
                })
        except Exception as e:
            print(f"Error fetching route tables: {e}")
        
        # Network Interfaces (ENIs)
        try:
            response = ec2.describe_network_interfaces(
                Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
            )
            for eni in response.get('NetworkInterfaces', []):
                name = next((t['Value'] for t in eni.get('TagSet', []) if t['Key'] == 'Name'), 'Unnamed')
                private_ip = eni.get('PrivateIpAddress', 'N/A')
                resources.append({
                    'type': 'network_interface',
                    'id': eni['NetworkInterfaceId'],
                    'name': name,
                    'state': eni.get('Status', 'unknown'),
                    'private_ip': private_ip
                })
        except Exception as e:
            print(f"Error fetching network interfaces: {e}")
        
        # IAM Roles
        try:
            iam = boto3.client('iam', region_name=aws_region)
            project_prefix = project_name.lower().replace('_', '-')
            paginator = iam.get_paginator('list_roles')
            for page in paginator.paginate():
                for role in page.get('Roles', []):
                    if role['RoleName'].lower().startswith(project_prefix):
                        resources.append({
                            'type': 'iam_role',
                            'id': role['RoleId'],
                            'name': role['RoleName'],
                            'state': 'active',
                            'created': role['CreateDate'].isoformat()
                        })
        except Exception as e:
            print(f"Error fetching IAM roles: {e}")
        
        # IAM Instance Profiles
        try:
            iam = boto3.client('iam', region_name=aws_region)
            project_prefix = project_name.lower().replace('_', '-')
            paginator = iam.get_paginator('list_instance_profiles')
            for page in paginator.paginate():
                for profile in page.get('InstanceProfiles', []):
                    if profile['InstanceProfileName'].lower().startswith(project_prefix):
                        resources.append({
                            'type': 'iam_instance_profile',
                            'id': profile['InstanceProfileId'],
                            'name': profile['InstanceProfileName'],
                            'state': 'active',
                            'role_count': len(profile.get('Roles', []))
                        })
        except Exception as e:
            print(f"Error fetching IAM instance profiles: {e}")
        
        # Save to deployment resources file
        resources_file = project_root / "logs" / "deployment_resources.json"
        resources_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing resources
        all_deployments = {}
        if resources_file.exists():
            try:
                with open(resources_file, 'r') as f:
                    all_deployments = json.load(f)
            except:
                pass
        
        # Save this deployment's resources
        all_deployments[project_name] = {
            'project_name': project_name,
            'deployment_type': deployment_type,
            'deployed_at': datetime.now().isoformat(),
            'region': aws_region,
            'resource_count': len(resources),
            'resources': resources
        }
        
        with open(resources_file, 'w') as f:
            json.dump(all_deployments, f, indent=2)
        
        add_log(f"Saved {len(resources)} resources for project '{project_name}'", "info", project_name)
        
    except Exception as e:
        print(f"Error saving deployment resources: {e}")
        add_log(f"Warning: Could not save resource list: {e}", "warning", project_name)

def run_destroy(project_name: str = None):
    """Run destroy in background thread with phased destruction for combined mode"""
    global deployment_state
    
    # Use project-specific state if provided
    if project_name and project_name in deployment_states:
        state = deployment_states[project_name]
        service = get_service_for_project(project_name)
    else:
        state = deployment_state
        service = terraform_service
    
    try:
        state["status"] = "running"
        state["output"] = ""
        state["error"] = None
        
        add_log("Starting infrastructure destruction...", "warning", project_name)
        
        # Get current deployment type
        output_result = service.output()
        outputs = output_result.get("outputs", {})
        deployment_type = outputs.get("deployment_type", {}).get("value", "")
        
        # Check if combined mode (requires phased destruction)
        is_combined = deployment_type.startswith("combined-")
        
        if is_combined:
            # Phase 1: Destroy VPC peering first
            state["step"] = "Phase 1/3: Destroying VPC peering..."
            add_log("Phase 1/3: Destroying VPC peering...", "info", project_name)
            result = service.destroy_target("module.vpc_peering")
            if not result["success"]:
                state["status"] = "error"
                state["error"] = result.get("stderr", "Failed to destroy VPC peering")
                add_log(f"Failed to destroy VPC peering: {state['error'][:500]}", "error", project_name)
                return
            
            # Phase 2: Destroy GOAD
            state["step"] = "Phase 2/3: Destroying GOAD lab..."
            add_log("Phase 2/3: Destroying GOAD lab...", "info", project_name)
            result = service.destroy_target("module.goad")
            if not result["success"]:
                state["status"] = "error"
                state["error"] = result.get("stderr", "Failed to destroy GOAD")
                add_log(f"Failed to destroy GOAD: {state['error'][:500]}", "error", project_name)
                return
            
            # Phase 3: Destroy remaining C2 infrastructure
            state["step"] = "Phase 3/3: Destroying C2 infrastructure..."
            add_log("Phase 3/3: Destroying C2 infrastructure...", "info", project_name)
            result = service.destroy()
            if not result["success"]:
                state["status"] = "error"
                state["error"] = result.get("stderr", "Failed to destroy C2 infrastructure")
                add_log(f"Failed to destroy C2 infrastructure: {state['error'][:500]}", "error", project_name)
                return
        else:
            # Standard destroy for non-combined modes
            state["step"] = "Destroying infrastructure..."
            add_log("Running terraform destroy...", "info", project_name)
            result = service.destroy()
            if not result["success"]:
                state["status"] = "error"
                state["error"] = result.get("stderr", "Destroy failed")
                add_log(f"Destroy failed: {state['error'][:500]}", "error", project_name)
                return
        
        state["status"] = "success"
        state["step"] = "Infrastructure destroyed"
        state["deployment_type"] = None
        state["completed_at"] = time.time()
        add_log("Infrastructure destroyed successfully!", "success", project_name)
        
    except Exception as e:
        state["status"] = "error"
        state["error"] = str(e)
        state["completed_at"] = time.time()
        add_log(f"Destroy error: {str(e)}", "error", project_name)

@bp.route('/status', methods=['GET'])
def get_deployment_status():
    """Get current deployment status with enhanced progress info"""
    # Check if requesting specific project status
    project_name = request.args.get('project')
    
    if project_name and project_name in deployment_states:
        state = deployment_states[project_name]
    else:
        state = deployment_state
    
    # Calculate elapsed time if running
    elapsed_seconds = 0
    if state["started_at"]:
        if state["completed_at"]:
            elapsed_seconds = int(state["completed_at"] - state["started_at"])
        else:
            elapsed_seconds = int(time.time() - state["started_at"])
    
    # Format elapsed time
    elapsed_formatted = f"{elapsed_seconds // 60}m {elapsed_seconds % 60}s"
    
    # Format estimated remaining
    est_remaining = state.get("est_remaining_seconds", 0)
    est_remaining_formatted = f"{est_remaining // 60}m {est_remaining % 60}s" if est_remaining > 0 else "Calculating..."
    
    return jsonify({
        "success": True,
        "status": {
            "status": state["status"],
            "step": state["step"],
            "output": state["output"],
            "error": state["error"],
            "deployment_type": state.get("deployment_type"),
            # Enhanced progress info
            "progress_percent": state.get("progress_percent", 0),
            "current_phase": state.get("current_phase", ""),
            "phases_completed": state.get("phases_completed", []),
            "elapsed_seconds": elapsed_seconds,
            "elapsed_formatted": elapsed_formatted,
            "est_remaining_seconds": est_remaining,
            "est_remaining_formatted": est_remaining_formatted,
            "logs": state.get("logs", [])[-20:],  # Last 20 log entries
            "project_name": project_name
        }
    })


@bp.route('/status/all', methods=['GET'])
def get_all_deployment_status():
    """Get status of all active deployments"""
    active = get_active_deployments()
    
    # Also include default deployment state if it's active
    if deployment_state["status"] == "running":
        active.append({"project_name": "default", **deployment_state})
    
    return jsonify({
        "success": True,
        "active_deployments": active,
        "total_active": len(active)
    })


@bp.route('/workspaces', methods=['GET'])
def list_workspaces():
    """List all Terraform workspaces"""
    result = terraform_service.workspace_list()
    
    # Enhance with deployment states
    workspaces = []
    for ws in result.get("workspaces", []):
        ws_info = {
            "name": ws,
            "is_current": ws == result.get("current"),
            "status": "idle"
        }
        if ws in deployment_states:
            ws_info["status"] = deployment_states[ws].get("status", "idle")
        workspaces.append(ws_info)
    
    return jsonify({
        "success": result["success"],
        "workspaces": workspaces,
        "current": result.get("current"),
        "stderr": result.get("stderr", "")
    })


@bp.route('/check-project-name', methods=['GET'])
def check_project_name():
    """
    Check if a project name is available (not already in use).
    Checks both local Terraform workspaces AND AWS resources directly.
    Returns whether the name is available and any existing resources.
    """
    import boto3
    import re
    from webapp.backend.utils.config_parser import ConfigParser
    
    project_name = request.args.get('name', '').strip()
    
    if not project_name:
        return jsonify({
            "success": False,
            "error": "Project name is required"
        }), 400
    
    # Validate project name format
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', project_name):
        return jsonify({
            "success": True,
            "available": False,
            "error": "Invalid project name. Must start with a letter and contain only letters, numbers, underscores, and hyphens.",
            "valid_format": False
        })
    
    # Check if currently deploying locally
    if project_name in deployment_states and deployment_states[project_name].get("status") == "running":
        return jsonify({
            "success": True,
            "available": False,
            "reason": "currently_deploying",
            "message": f"Project '{project_name}' is currently being deployed"
        })
    
    # Check deployment history for previously used names
    history = load_deployment_history()
    project_history = [h for h in history if h.get('project_name') == project_name]
    if project_history:
        # Check if there were any errors or if it was purged
        has_errors = any(h.get('level') == 'error' for h in project_history)
        was_purged = any('purge' in h.get('message', '').lower() for h in project_history)
        last_entry = project_history[-1] if project_history else None
        last_time = last_entry.get('timestamp', 'unknown') if last_entry else 'unknown'
        
        # This is a warning, not a block - user can still proceed
        # We'll return available=True but with a warning
        history_warning = {
            "previously_used": True,
            "entry_count": len(project_history),
            "had_errors": has_errors,
            "was_purged": was_purged,
            "last_activity": last_time
        }
    else:
        history_warning = None
    
    # Get AWS region from config
    config_dir = project_root / "configs"
    tfvars_file = config_dir / "terraform.tfvars"
    aws_region = 'us-east-1'  # Default
    if tfvars_file.exists():
        config = ConfigParser.parse_tfvars(tfvars_file)
        aws_region = config.get('aws_region', 'us-east-1')
    
    # OPTION 2: Check AWS directly for existing resources with this project tag
    try:
        ec2 = boto3.client('ec2', region_name=aws_region)
        
        # Check for VPCs with this project tag
        vpc_response = ec2.describe_vpcs(
            Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
        )
        
        if vpc_response.get('Vpcs'):
            vpc_count = len(vpc_response['Vpcs'])
            return jsonify({
                "success": True,
                "available": False,
                "reason": "aws_resources_exist",
                "resource_count": vpc_count,
                "resource_type": "VPC",
                "message": f"Project '{project_name}' already has {vpc_count} VPC(s) in AWS ({aws_region})",
                "source": "aws"
            })
        
        # Also check for EC2 instances
        instance_response = ec2.describe_instances(
            Filters=[
                {'Name': 'tag:Project', 'Values': [project_name]},
                {'Name': 'instance-state-name', 'Values': ['pending', 'running', 'stopping', 'stopped']}
            ]
        )
        
        instance_count = sum(len(r['Instances']) for r in instance_response.get('Reservations', []))
        if instance_count > 0:
            return jsonify({
                "success": True,
                "available": False,
                "reason": "aws_resources_exist",
                "resource_count": instance_count,
                "resource_type": "EC2",
                "message": f"Project '{project_name}' already has {instance_count} EC2 instance(s) in AWS ({aws_region})",
                "source": "aws"
            })
        
        # Check S3 buckets (they're globally unique)
        s3 = boto3.client('s3', region_name=aws_region)
        project_prefix = project_name.lower().replace('_', '-')
        try:
            bucket_response = s3.list_buckets()
            matching_buckets = [
                b['Name'] for b in bucket_response.get('Buckets', [])
                if project_prefix in b['Name'].lower()
            ]
            if matching_buckets:
                return jsonify({
                    "success": True,
                    "available": False,
                    "reason": "aws_resources_exist",
                    "resource_count": len(matching_buckets),
                    "resource_type": "S3",
                    "buckets": matching_buckets,
                    "message": f"Project '{project_name}' already has S3 bucket(s): {', '.join(matching_buckets)}",
                    "source": "aws"
                })
        except Exception:
            pass  # S3 check is optional
            
    except Exception as e:
        # AWS check failed - continue with local check
        print(f"AWS check failed: {e}")
    
    # Check local Terraform workspaces
    try:
        init_result = terraform_service.init()
        if init_result["success"]:
            ws_list = terraform_service.workspace_list()
            if ws_list["success"] and project_name in ws_list.get("workspaces", []):
                terraform_service.workspace_select(project_name)
                state_result = terraform_service.show()
                
                if state_result["success"]:
                    state = state_result.get("state", {})
                    resources = state.get("values", {}).get("root_module", {}).get("resources", [])
                    
                    if resources and len(resources) > 0:
                        return jsonify({
                            "success": True,
                            "available": False,
                            "reason": "has_local_resources",
                            "resource_count": len(resources),
                            "message": f"Project '{project_name}' exists locally with {len(resources)} resources",
                            "source": "local"
                        })
                
                # Workspace exists but is empty - allow reuse with warning
                response = {
                    "success": True,
                    "available": True,
                    "workspace_exists": True,
                    "message": f"Project '{project_name}' workspace exists but has no resources"
                }
                if history_warning:
                    response["history"] = history_warning
                    response["message"] += " (previously used)"
                return jsonify(response)
    except Exception as e:
        print(f"Local workspace check failed: {e}")
    
    # Project name is available
    response = {
        "success": True,
        "available": True,
        "message": f"Project name '{project_name}' is available"
    }
    if history_warning:
        response["history"] = history_warning
        response["warning"] = f"This name was previously used ({history_warning['entry_count']} history entries)"
    return jsonify(response)


@bp.route('/generate-project-name', methods=['GET'])
def generate_project_name():
    """
    Generate a unique project name with machine-specific suffix.
    OPTION 3: Ensures uniqueness across different users/machines.
    
    Format: {prefix}_{env}_{hostname}
    Example: goad_mini_dev_harris_macbook
    """
    import socket
    import re
    
    prefix = request.args.get('prefix', 'project')
    environment = request.args.get('env', 'dev')
    
    # Get hostname and sanitize it for use in project name
    hostname = socket.gethostname()
    # Sanitize: lowercase, replace dots/spaces with underscores, keep only valid chars
    sanitized_hostname = re.sub(r'[^a-zA-Z0-9]', '_', hostname.lower())
    # Remove consecutive underscores and trim
    sanitized_hostname = re.sub(r'_+', '_', sanitized_hostname).strip('_')
    # Limit length to keep project names reasonable
    if len(sanitized_hostname) > 20:
        sanitized_hostname = sanitized_hostname[:20].rstrip('_')
    
    # Build the project name
    project_name = f"{prefix}_{environment}_{sanitized_hostname}"
    
    return jsonify({
        "success": True,
        "project_name": project_name,
        "components": {
            "prefix": prefix,
            "environment": environment,
            "machine_suffix": sanitized_hostname,
            "hostname": hostname
        },
        "message": f"Generated unique project name based on hostname '{hostname}'"
    })


@bp.route('/machine-info', methods=['GET'])
def get_machine_info():
    """
    Get information about the current machine for project naming.
    """
    import socket
    import re
    import platform
    
    hostname = socket.gethostname()
    # Sanitize hostname for use in project names
    sanitized_hostname = re.sub(r'[^a-zA-Z0-9]', '_', hostname.lower())
    sanitized_hostname = re.sub(r'_+', '_', sanitized_hostname).strip('_')
    if len(sanitized_hostname) > 20:
        sanitized_hostname = sanitized_hostname[:20].rstrip('_')
    
    return jsonify({
        "success": True,
        "hostname": hostname,
        "machine_suffix": sanitized_hostname,
        "platform": platform.system(),
        "message": f"Your machine suffix is '{sanitized_hostname}' (from hostname '{hostname}')"
    })


@bp.route('/deploy', methods=['POST'])
def deploy():
    """Start deployment for a specific project"""
    global deployment_state
    
    # Get request data
    data = request.get_json() or {}
    
    # Load configuration to get project name
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
    project_name = config.get('project_name', '').strip()
    deployment_type = config.get('deployment_type', '').strip()
    
    if not project_name:
        return jsonify({
            "success": False,
            "error": "Project name not configured. Please set project_name in configuration."
        }), 400
    
    # Check if THIS project is already deploying
    if project_name in deployment_states and deployment_states[project_name].get("status") == "running":
        return jsonify({
            "success": False,
            "error": f"Project '{project_name}' is already deploying"
        }), 400
    
    # Also check legacy single deployment state
    if deployment_state["status"] == "running":
        return jsonify({
            "success": False,
            "error": "Another deployment is already in progress"
        }), 400
    
    # Note: We skip the workspace existence check here to avoid blocking.
    # The deployment thread will handle workspace creation/selection.
    # If resources already exist, Terraform will detect conflicts during apply.
    
    # Define which deployment types require what prerequisites
    GOAD_ONLY_TYPES = ['goad-mini', 'goad-minilab', 'goad-light', 'goad-sccm', 'goad-full', 'goad-nha']
    C2_ONLY_TYPES = ['c2-adhoc', 'c2-purple', 'c2-full']
    COMBINED_TYPES = ['combined-adhoc-mini', 'combined-adhoc-light', 'combined-full-full']
    
    # All deployments with CS need the CS file uploaded
    requires_cobalt_strike = True
    
    # Only C2 and Combined need domain
    requires_domain = deployment_type in C2_ONLY_TYPES or deployment_type in COMBINED_TYPES
    
    # Check prerequisite: Cobalt Strike file
    if requires_cobalt_strike:
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
    
    # Check prerequisite: Domain configuration
    if requires_domain:
        primary_domain = config.get("primary_domain_name", "").strip()
        
        if not primary_domain:
            return jsonify({
                "success": False,
                "error": "Domain configuration is required for C2 deployments. Please configure primary_domain_name."
            }), 400
        
        domain_valid, domain_errors = ConfigValidator.validate_domain_config(config)
        if not domain_valid:
            return jsonify({
                "success": False,
                "error": f"Domain configuration is invalid: {', '.join(domain_errors)}"
            }), 400
    
    # Initialize project-specific state
    deployment_states[project_name] = create_empty_state()
    state = deployment_states[project_name]
    
    # Set initial state BEFORE starting the thread
    state["status"] = "running"
    state["step"] = "Initializing..."
    state["started_at"] = time.time()
    state["progress_percent"] = 0
    state["error"] = None
    state["logs"] = []
    
    # Copy config to project-specific tfvars
    service = get_service_for_project(project_name)
    service.copy_config_to_workspace(tfvars_file)
    
    # Log what we're deploying
    add_history_entry(f"Starting deployment: {deployment_type} (project: {project_name})", "info", project_name=project_name)
    
    # Start deployment in background thread
    thread = threading.Thread(target=run_deployment, args=(project_name,))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "success": True,
        "message": f"Deployment started for project '{project_name}' ({deployment_type})",
        "project_name": project_name,
        "deployment_type": deployment_type
    })

@bp.route('/destroy', methods=['POST'])
def destroy():
    """Destroy infrastructure for a specific project"""
    global deployment_state
    
    # Get request data
    data = request.get_json() or {}
    project_name = data.get("project_name")
    
    # Check if specific project is running
    if project_name and project_name in deployment_states:
        if deployment_states[project_name].get("status") == "running":
            return jsonify({
                "success": False,
                "error": f"Operation already in progress for project '{project_name}'"
            }), 400
    elif deployment_state["status"] == "running":
        return jsonify({
            "success": False,
            "error": "Operation already in progress"
        }), 400
    
    # Require confirmation
    if data.get("confirm") != "DESTROY":
        return jsonify({
            "success": False,
            "error": "Confirmation required. Send confirm: 'DESTROY'"
        }), 400
    
    # Initialize state for this project
    if project_name:
        if project_name not in deployment_states:
            deployment_states[project_name] = create_empty_state()
        deployment_states[project_name]["status"] = "running"
        deployment_states[project_name]["step"] = "Destroying infrastructure..."
        deployment_states[project_name]["started_at"] = time.time()
        deployment_states[project_name]["logs"] = []  # Clear previous logs
    
    # Log the start of destroy to history
    add_history_entry(f"Starting destroy for project: {project_name or 'default'}", "warning", project_name=project_name)
    
    # Start destroy in background thread
    thread = threading.Thread(target=run_destroy, args=(project_name,))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "success": True,
        "message": f"Destruction started" + (f" for project '{project_name}'" if project_name else ""),
        "project_name": project_name
    })

@bp.route('/purge', methods=['POST'])
def purge_resources():
    """
    Force purge all resources from a failed deployment.
    This runs terraform destroy with -refresh=false to clean up orphaned resources.
    """
    global deployment_state
    
    # Get request data
    data = request.get_json() or {}
    project_name = data.get("project_name")
    
    # Check if specific project is running
    if project_name and project_name in deployment_states:
        if deployment_states[project_name].get("status") == "running":
            return jsonify({
                "success": False,
                "error": f"Operation already in progress for project '{project_name}'"
            }), 400
    elif deployment_state["status"] == "running":
        return jsonify({
            "success": False,
            "error": "Operation already in progress"
        }), 400
    
    # Require confirmation
    if data.get("confirm") != "PURGE":
        return jsonify({
            "success": False,
            "error": "Confirmation required. Send confirm: 'PURGE'"
        }), 400
    
    # Initialize state for this project
    if project_name:
        if project_name not in deployment_states:
            deployment_states[project_name] = create_empty_state()
        state = deployment_states[project_name]
    else:
        state = deployment_state
    
    # Set initial state before starting thread
    state["status"] = "running"
    state["step"] = "Purging resources..."
    state["started_at"] = time.time()
    state["progress_percent"] = 0
    state["logs"] = []  # Clear previous logs
    
    # Log the start of purge to history (like deployment does)
    add_history_entry(f"Starting purge/destroy for project: {project_name or 'default'}", "warning", project_name=project_name)
    state["error"] = None
    state["logs"] = []
    
    # Start purge in background thread
    thread = threading.Thread(target=run_purge, args=(project_name,))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "success": True,
        "message": "Purge started - cleaning up all resources" + (f" for project '{project_name}'" if project_name else ""),
        "project_name": project_name
    })

def run_purge(project_name: str = None):
    """Run purge in background thread - force destroy all resources"""
    global deployment_state
    
    # Use project-specific state if provided
    if project_name and project_name in deployment_states:
        state = deployment_states[project_name]
        service = get_service_for_project(project_name)
    else:
        state = deployment_state
        service = terraform_service
    
    try:
        add_log("Starting resource purge...", "warning", project_name)
        
        # First, try to refresh state to see what exists
        state["step"] = "Refreshing Terraform state..."
        add_log("Refreshing Terraform state to detect existing resources...", "info", project_name)
        
        # Run terraform refresh to update state with actual AWS resources
        refresh_result = service.refresh()
        if refresh_result.get("success"):
            add_log("State refreshed successfully", "success", project_name)
        else:
            add_log("State refresh had issues, continuing with destroy...", "warning", project_name)
        
        # Now run destroy
        state["step"] = "Destroying all resources..."
        state["progress_percent"] = 30
        add_log("Running terraform destroy to remove all resources...", "info", project_name)
        
        result = service.destroy()
        
        if result["success"]:
            state["status"] = "success"
            state["step"] = "Resources purged"
            state["progress_percent"] = 100
            add_log("All resources have been purged successfully!", "success", project_name)
            
            # Also clear the terraform state to start fresh
            add_log("Clearing Terraform state for clean slate...", "info", project_name)
            
            # If using workspace, optionally delete it
            if project_name and service.workspace_name != "default":
                add_log(f"Cleaning up workspace '{service.workspace_name}'...", "info", project_name)
            
        else:
            # Log the first destroy error
            first_error = result.get("stderr", "Unknown error")
            add_log(f"Standard destroy failed: {first_error[:500]}", "error", project_name)
            
            # If normal destroy fails, try with -refresh=false
            add_log("Trying force destroy with -refresh=false...", "warning", project_name)
            state["step"] = "Force destroying resources..."
            state["progress_percent"] = 60
            
            result = service.force_destroy()
            
            if result["success"]:
                state["status"] = "success"
                state["step"] = "Resources force-purged"
                state["progress_percent"] = 100
                add_log("Resources force-purged successfully!", "success", project_name)
            else:
                state["status"] = "error"
                error_msg = result.get("stderr", "Purge failed")
                state["error"] = error_msg
                # Log the full error (truncated for readability)
                add_log(f"Purge failed: {error_msg[:1000]}", "error", project_name)
        
        state["completed_at"] = time.time()
        
    except Exception as e:
        state["status"] = "error"
        state["error"] = str(e)
        state["completed_at"] = time.time()
        add_log(f"Purge error: {str(e)}", "error", project_name)

@bp.route('/plan', methods=['GET'])
def plan():
    """Run Terraform plan with improved error handling"""
    try:
        # Check if terraform is installed
        import shutil
        if not shutil.which('terraform'):
            return jsonify({
                "success": False,
                "error": "Terraform CLI not found. Please install Terraform first.",
                "error_type": "terraform_not_installed",
                "help": "Please install Terraform CLI. Run: brew install terraform (macOS) or visit https://terraform.io/downloads",
                "stdout": "",
                "stderr": "Terraform CLI is not installed on this system.\n\nTo install:\n  macOS: brew install terraform\n  Linux: See https://terraform.io/downloads\n  Windows: choco install terraform"
            })
        
        # Check if tfvars file exists
        if not terraform_service.tfvars_file.exists():
            return jsonify({
                "success": False,
                "error": "Configuration file not found",
                "error_type": "config_missing",
                "help": "Please save your configuration in the Configuration tab before running plan.",
                "stdout": "",
                "stderr": f"Configuration file not found at:\n{terraform_service.tfvars_file}\n\nPlease go to the Configuration tab and save your settings first."
            })
        
        # Check if terraform is initialized
        terraform_dir = terraform_service.terraform_dir
        if not (terraform_dir / ".terraform").exists():
            # Auto-initialize terraform
            add_history_entry("Auto-initializing Terraform...", "info", entry_type='plan')
            init_result = terraform_service.init()
            if not init_result.get("success"):
                init_error = init_result.get("stderr", "") or init_result.get("stdout", "") or "Unknown initialization error"
                return jsonify({
                    "success": False,
                    "error": "Terraform initialization failed",
                    "error_type": "init_failed",
                    "help": "Terraform failed to initialize. This usually means network issues or missing AWS credentials.",
                    "stdout": init_result.get("stdout", ""),
                    "stderr": f"Terraform Init Failed:\n\n{init_error}"
                })
        
        # Run the plan
        add_history_entry("Running Terraform plan...", "info", entry_type='plan')
        result = terraform_service.plan()
        
        # Get combined output
        full_output = result.get("full_output", "") or result.get("stdout", "") or result.get("stderr", "")
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        
        if result["success"]:
            add_history_entry("Terraform plan completed successfully", "success", entry_type='plan')
            return jsonify({
                "success": True,
                "exit_code": result.get("exit_code"),
                "stdout": full_output or "Plan completed. No output captured.",
                "stderr": stderr,
                "plan": result.get("plan", {}),
                "message": "Plan completed successfully"
            })
        else:
            # Combine all output for error analysis
            all_output = f"{stdout}\n{stderr}".strip()
            
            # Parse common error patterns from combined output
            error_type = "unknown"
            help_text = "Check the error output below for details."
            
            # Check both stdout and stderr for error patterns
            if "No valid credential sources found" in all_output or "NoCredentialProviders" in all_output:
                error_type = "aws_credentials"
                help_text = "AWS credentials not configured. Run 'aws configure' in your terminal to set up credentials."
            elif "could not find credentials" in all_output.lower() or "no credentials" in all_output.lower():
                error_type = "aws_credentials"
                help_text = "AWS credentials not found. Run 'aws configure' to set up your AWS access keys."
            elif "ExpiredToken" in all_output or "expired" in all_output.lower():
                error_type = "aws_credentials"
                help_text = "Your AWS credentials have expired. Please refresh your credentials."
            elif "AccessDenied" in all_output or "UnauthorizedAccess" in all_output or "not authorized" in all_output.lower():
                error_type = "aws_permissions"
                help_text = "Your AWS credentials don't have sufficient permissions. Check your IAM policies."
            elif "Invalid provider configuration" in all_output:
                error_type = "provider_config"
                help_text = "Invalid Terraform provider configuration. Check your AWS region setting."
            elif "Error acquiring the state lock" in all_output:
                error_type = "state_lock"
                help_text = "Terraform state is locked. Another operation may be in progress. Wait and try again."
            elif "timeout" in all_output.lower():
                error_type = "timeout"
                help_text = "The operation timed out. Check your network connection."
            elif "Error:" in all_output:
                # Generic error - try to extract the error message
                error_type = "terraform_error"
                help_text = "Terraform encountered an error. See the details below."
            
            # Create a helpful error message
            error_display = all_output if all_output else "No error details available. Exit code: " + str(result.get("exit_code", "unknown"))
            
            add_history_entry(f"Terraform plan failed: {error_type}", "error", entry_type='plan')
            
            return jsonify({
                "success": False,
                "exit_code": result.get("exit_code"),
                "error": help_text,
                "error_type": error_type,
                "stdout": stdout,
                "stderr": error_display,
                "help": help_text
            })
            
    except Exception as e:
        error_msg = str(e)
        error_type = "unknown"
        help_text = "An unexpected error occurred."
        detailed_error = error_msg
        
        if "No such file or directory: 'terraform'" in error_msg:
            error_type = "terraform_not_installed"
            help_text = "Terraform CLI is not installed. Please install it first."
            detailed_error = "Terraform CLI is not installed on this system.\n\nTo install:\n  macOS: brew install terraform\n  Linux: See https://terraform.io/downloads"
        
        add_history_entry(f"Plan error: {error_msg}", "error", entry_type='plan')
        
        return jsonify({
            "success": False,
            "error": help_text,
            "error_type": error_type,
            "help": help_text,
            "stdout": "",
            "stderr": detailed_error
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


# =============================================================================
# COBALT STRIKE CLIENT UPLOAD (for Attack Box)
# =============================================================================
# These endpoints manage the CS Client archive that gets deployed to the
# Windows Attack Box. This is separate from the Team Server archive.
# =============================================================================

@bp.route('/upload-cs-client', methods=['POST'])
def upload_cs_client():
    """Upload Cobalt Strike Client archive file for Attack Box"""
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
        filepath = CS_CLIENT_FOLDER / filename
        
        # Save file
        file.save(str(filepath))
        
        # Get file info
        file_info = get_file_info(filepath)
        
        return jsonify({
            "success": True,
            "message": "CS Client file uploaded successfully",
            "file": file_info
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/cs-client-file', methods=['GET'])
def get_cs_client_file():
    """Get information about uploaded CS Client file"""
    try:
        # Look for CS Client files in upload directory
        files = list(CS_CLIENT_FOLDER.glob("*"))
        cs_client_files = [
            get_file_info(f) for f in files 
            if f.is_file() and allowed_file(f.name)
        ]
        
        # Sort by modified time (newest first)
        cs_client_files.sort(key=lambda x: x['modified'] if x else 0, reverse=True)
        
        return jsonify({
            "success": True,
            "files": cs_client_files,
            "has_file": len(cs_client_files) > 0,
            "latest_file": cs_client_files[0] if cs_client_files else None
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/cs-client-file', methods=['DELETE'])
def delete_cs_client_file():
    """Delete uploaded CS Client file"""
    try:
        data = request.get_json() or {}
        filename = data.get('filename')
        
        if filename and filename != 'latest':
            # Delete specific file
            filepath = CS_CLIENT_FOLDER / secure_filename(filename)
        else:
            # Delete latest file (most recent)
            files = list(CS_CLIENT_FOLDER.glob("*"))
            cs_client_files = [
                f for f in files 
                if f.is_file() and allowed_file(f.name)
            ]
            
            if not cs_client_files:
                return jsonify({"success": False, "error": "No files found"}), 404
            
            # Get most recent file
            filepath = max(cs_client_files, key=lambda f: f.stat().st_mtime)
        
        if not filepath.exists():
            return jsonify({"success": False, "error": "File not found"}), 404
        
        if not filepath.is_file():
            return jsonify({"success": False, "error": "Not a file"}), 400
        
        filepath.unlink()
        
        return jsonify({
            "success": True,
            "message": "CS Client file deleted successfully"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# =============================================================================
# SSH PUBLIC KEY MANAGEMENT
# =============================================================================
# These endpoints manage the user's SSH public key for secure lab access.
# The public key is stored locally and passed to Terraform during deployment.
# Private keys are NEVER handled by this application - they stay on the user's machine.
# =============================================================================

# SSH key storage file
SSH_KEY_FILE = Path(__file__).parent.parent / "data" / "ssh_public_key.txt"

def validate_ssh_public_key(key: str) -> dict:
    """
    Validate an SSH public key format.
    Returns dict with 'valid', 'key_type', 'fingerprint', and 'comment' fields.
    """
    import re
    import hashlib
    import base64
    
    key = key.strip()
    
    # Supported key types
    valid_types = [
        'ssh-ed25519',
        'ssh-rsa', 
        'ecdsa-sha2-nistp256',
        'ecdsa-sha2-nistp384',
        'ecdsa-sha2-nistp521'
    ]
    
    # Basic format check: type base64-data [comment]
    pattern = r'^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp\d+)\s+([A-Za-z0-9+/=]+)(\s+.*)?$'
    match = re.match(pattern, key)
    
    if not match:
        return {
            'valid': False,
            'error': 'Invalid SSH public key format. Expected: ssh-ed25519 AAAA... or ssh-rsa AAAA...'
        }
    
    key_type = match.group(1)
    key_data = match.group(2)
    comment = match.group(3).strip() if match.group(3) else ''
    
    # Validate base64 encoding
    try:
        decoded = base64.b64decode(key_data)
        # Calculate fingerprint (SHA256)
        fingerprint = hashlib.sha256(decoded).digest()
        fingerprint_b64 = base64.b64encode(fingerprint).decode('utf-8').rstrip('=')
        fingerprint_str = f"SHA256:{fingerprint_b64}"
    except Exception:
        return {
            'valid': False,
            'error': 'Invalid base64 encoding in key data'
        }
    
    # Check minimum key length
    if key_type == 'ssh-rsa' and len(decoded) < 256:
        return {
            'valid': False,
            'error': 'RSA key is too short. Use at least 2048 bits (preferably 4096)'
        }
    
    return {
        'valid': True,
        'key_type': key_type,
        'fingerprint': fingerprint_str,
        'comment': comment,
        'key_preview': f"{key_type} {key_data[:20]}...{key_data[-10:]}" if len(key_data) > 30 else key
    }


@bp.route('/ssh-public-key', methods=['GET'])
def get_ssh_public_key():
    """Get the stored SSH public key"""
    try:
        # Ensure data directory exists
        SSH_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        if not SSH_KEY_FILE.exists():
            return jsonify({
                "success": True,
                "has_key": False,
                "message": "No SSH public key configured"
            })
        
        key_content = SSH_KEY_FILE.read_text().strip()
        
        if not key_content:
            return jsonify({
                "success": True,
                "has_key": False,
                "message": "SSH public key file is empty"
            })
        
        # Validate and get key info
        validation = validate_ssh_public_key(key_content)
        
        if not validation['valid']:
            return jsonify({
                "success": True,
                "has_key": True,
                "valid": False,
                "error": validation['error'],
                "key_preview": key_content[:50] + "..." if len(key_content) > 50 else key_content
            })
        
        return jsonify({
            "success": True,
            "has_key": True,
            "valid": True,
            "key_type": validation['key_type'],
            "fingerprint": validation['fingerprint'],
            "comment": validation['comment'],
            "key_preview": validation['key_preview']
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/ssh-public-key', methods=['POST'])
def save_ssh_public_key():
    """Save the user's SSH public key"""
    try:
        data = request.get_json() or {}
        public_key = data.get('public_key', '').strip()
        
        if not public_key:
            return jsonify({
                "success": False,
                "error": "No public key provided"
            }), 400
        
        # Validate the key
        validation = validate_ssh_public_key(public_key)
        
        if not validation['valid']:
            return jsonify({
                "success": False,
                "error": validation['error']
            }), 400
        
        # Warn if using RSA (recommend Ed25519)
        warning = None
        if validation['key_type'] == 'ssh-rsa':
            warning = "Consider using Ed25519 keys for better security and performance: ssh-keygen -t ed25519"
        
        # Ensure data directory exists
        SSH_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # Save the key
        SSH_KEY_FILE.write_text(public_key + '\n')
        
        return jsonify({
            "success": True,
            "message": "SSH public key saved successfully",
            "key_type": validation['key_type'],
            "fingerprint": validation['fingerprint'],
            "comment": validation['comment'],
            "key_preview": validation['key_preview'],
            "warning": warning
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/ssh-public-key', methods=['DELETE'])
def delete_ssh_public_key():
    """Delete the stored SSH public key"""
    try:
        if SSH_KEY_FILE.exists():
            SSH_KEY_FILE.unlink()
        
        return jsonify({
            "success": True,
            "message": "SSH public key deleted successfully"
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def get_user_public_key() -> str:
    """
    Get the user's SSH public key for Terraform.
    Returns the key content or raises an exception if not configured.
    """
    if not SSH_KEY_FILE.exists():
        raise ValueError("SSH public key not configured. Please add your public key in the Deploy tab.")
    
    key_content = SSH_KEY_FILE.read_text().strip()
    
    if not key_content:
        raise ValueError("SSH public key file is empty. Please add your public key in the Deploy tab.")
    
    validation = validate_ssh_public_key(key_content)
    
    if not validation['valid']:
        raise ValueError(f"Invalid SSH public key: {validation['error']}")
    
    return key_content


# =============================================================================
# SECURE CONNECTION INFO ENDPOINTS (Phase 4)
# =============================================================================
# These endpoints provide connection information WITHOUT exposing private keys.
# Private keys are generated on the hosts themselves and never transmitted.
# Users connect using their own SSH key that they uploaded before deployment.
# =============================================================================

@bp.route('/connection-info', methods=['GET'])
def get_connection_info():
    """
    Get secure connection information for deployed infrastructure.
    
    SECURITY: This endpoint NEVER returns private keys.
    - User's private key stays on their machine
    - Internal keys are generated on hosts and never transmitted
    - Only public information (IPs, ports, commands) is returned
    
    Query params:
        project: project name (optional, uses default workspace if not provided)
    """
    try:
        project_name = request.args.get('project')
        
        # Use project-specific service if provided
        if project_name:
            service = get_service_for_project(project_name)
            service.init()
            service.ensure_workspace()
        else:
            service = terraform_service
        
        # Get Terraform outputs
        output_result = service.output()
        
        if not output_result.get("success"):
            return jsonify({
                "success": False,
                "error": "Failed to get deployment outputs. Infrastructure may not be deployed.",
                "has_deployment": False
            })
        
        outputs = output_result.get("outputs", {})
        
        # Check if there's an active deployment
        deployment_type = outputs.get("deployment_type", {}).get("value", "")
        if not deployment_type:
            return jsonify({
                "success": False,
                "error": "No active deployment found",
                "has_deployment": False
            })
        
        # Get deployment mode
        deployment_mode = outputs.get("deployment_mode", {}).get("value", {})
        is_goad = deployment_mode.get("is_goad_only", False) or deployment_mode.get("is_combined", False)
        
        # Build secure connection info (NO PRIVATE KEYS!)
        connection_info = {
            "success": True,
            "has_deployment": True,
            "deployment_type": deployment_type,
            "project_name": project_name or "default",
            
            # Security notice
            "security_notice": {
                "message": "Private keys are NOT provided by this API.",
                "user_key": "Use the SSH key you generated locally (~/.ssh/goad_key)",
                "internal_keys": "Internal keys are generated on hosts and never transmitted"
            },
            
            # SSH connection commands (using user's own key)
            "ssh_commands": {},
            
            # Host information
            "hosts": {},
            
            # Network information
            "network": {}
        }
        
        # GOAD Lab connection info
        if is_goad:
            jumpbox_ip = outputs.get("goad_jumpbox_public_ip", {}).get("value")
            jumpbox_private_ip = outputs.get("goad_jumpbox_private_ip", {}).get("value")
            
            if jumpbox_ip:
                connection_info["hosts"]["jumpbox"] = {
                    "public_ip": jumpbox_ip,
                    "private_ip": jumpbox_private_ip,
                    "user": "ubuntu",
                    "role": "SSH Gateway / Bastion Host"
                }
                
                # SSH command using user's own key
                connection_info["ssh_commands"]["jumpbox"] = {
                    "command": f"ssh -i ~/.ssh/goad_key ubuntu@{jumpbox_ip}",
                    "description": "Connect to jumpbox using YOUR SSH key"
                }
                
                # Team Server (via jumpbox)
                teamserver_ip = outputs.get("goad_teamserver_private_ip", {}).get("value")
                if teamserver_ip:
                    connection_info["hosts"]["teamserver"] = {
                        "private_ip": teamserver_ip,
                        "user": "ubuntu",
                        "role": "Cobalt Strike Team Server",
                        "access": "Via jumpbox only"
                    }
                    
                    connection_info["ssh_commands"]["teamserver"] = {
                        "command": f"ssh teamserver  # From jumpbox",
                        "description": "Connect to Team Server FROM the jumpbox (internal key is on jumpbox)",
                        "tunnel_command": f"ssh -i ~/.ssh/goad_key -L 50050:{teamserver_ip}:50050 ubuntu@{jumpbox_ip}",
                        "tunnel_description": "Create tunnel for Cobalt Strike client"
                    }
                
                # Attack Box
                attackbox_ip = outputs.get("goad_attackbox_private_ip", {}).get("value")
                if attackbox_ip:
                    connection_info["hosts"]["attackbox"] = {
                        "private_ip": attackbox_ip,
                        "role": "Windows Attack Workstation",
                        "access": "Via jumpbox tunnel (RDP)"
                    }
                    
                    connection_info["ssh_commands"]["attackbox_rdp"] = {
                        "command": f"ssh -i ~/.ssh/goad_key -L 3389:{attackbox_ip}:3389 ubuntu@{jumpbox_ip}",
                        "description": "Create RDP tunnel to Attack Box, then RDP to localhost:3389"
                    }
                
                # Windows AD VMs
                goad_vms = outputs.get("goad_lab_vms", {}).get("value", [])
                if goad_vms:
                    connection_info["hosts"]["windows_vms"] = {
                        "vms": goad_vms,
                        "access": "Via jumpbox tunnel (RDP/WinRM)"
                    }
                    
                    # Example RDP tunnel for first VM
                    if goad_vms and len(goad_vms) > 0:
                        first_vm = goad_vms[0] if isinstance(goad_vms[0], dict) else {"ip": goad_vms[0]}
                        vm_ip = first_vm.get("ip", first_vm.get("private_ip", "192.168.56.10"))
                        connection_info["ssh_commands"]["windows_rdp_example"] = {
                            "command": f"ssh -i ~/.ssh/goad_key -L 3389:{vm_ip}:3389 ubuntu@{jumpbox_ip}",
                            "description": f"Create RDP tunnel to Windows VM ({vm_ip})"
                        }
        
        # C2-only or combined mode - bastion info
        bastion_ip = outputs.get("bastion_public_ip", {}).get("value")
        if bastion_ip:
            connection_info["hosts"]["bastion"] = {
                "public_ip": bastion_ip,
                "user": "ubuntu",
                "role": "C2 Bastion Host"
            }
            
            connection_info["ssh_commands"]["bastion"] = {
                "command": f"ssh -i ~/.ssh/goad_key ubuntu@{bastion_ip}",
                "description": "Connect to C2 bastion using YOUR SSH key"
            }
        
        # C2 server info
        c2_ip = outputs.get("c2_server_primary_ip", {}).get("value")
        if c2_ip:
            connection_info["hosts"]["c2_server"] = {
                "private_ip": c2_ip,
                "role": "C2 Team Server",
                "access": "Via bastion only"
            }
        
        # Redirectors
        redirectors = outputs.get("proxy_redirector_public_ips", {}).get("value", [])
        if redirectors:
            connection_info["hosts"]["redirectors"] = {
                "public_ips": redirectors,
                "role": "Traffic Redirectors"
            }
        
        # Network info
        connection_info["network"] = {
            "vpc_cidr": outputs.get("vpc_cidr", {}).get("value"),
            "private_subnet": outputs.get("private_subnet_cidr", {}).get("value"),
            "public_subnet": outputs.get("public_subnet_cidr", {}).get("value")
        }
        
        return jsonify(connection_info)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@bp.route('/ssh-fingerprints', methods=['GET'])
def get_ssh_fingerprints():
    """
    Get SSH host key fingerprints for deployed hosts.
    
    This endpoint retrieves fingerprints that users can verify when connecting
    to ensure they're connecting to the correct hosts (TOFU verification).
    
    Query params:
        project: project name (optional)
        host: specific host to get fingerprint for (optional)
    
    Note: Fingerprints are retrieved from S3 where hosts upload them during bootstrap,
    or from Terraform outputs if available.
    """
    try:
        project_name = request.args.get('project')
        specific_host = request.args.get('host')
        
        # Use project-specific service if provided
        if project_name:
            service = get_service_for_project(project_name)
            service.init()
            service.ensure_workspace()
        else:
            service = terraform_service
        
        # Get Terraform outputs
        output_result = service.output()
        
        if not output_result.get("success"):
            return jsonify({
                "success": False,
                "error": "Failed to get deployment outputs"
            })
        
        outputs = output_result.get("outputs", {})
        
        # Check for deployment
        deployment_type = outputs.get("deployment_type", {}).get("value", "")
        if not deployment_type:
            return jsonify({
                "success": False,
                "error": "No active deployment found"
            })
        
        fingerprints = {
            "success": True,
            "project_name": project_name or "default",
            "hosts": {},
            "verification_instructions": {
                "description": "Compare these fingerprints with what SSH shows on first connection",
                "example": "The authenticity of host 'x.x.x.x' can't be established. ED25519 key fingerprint is SHA256:xxxxx. Are you sure you want to continue connecting (yes/no)?",
                "action": "Verify the fingerprint matches before typing 'yes'"
            }
        }
        
        # Get jumpbox connection info (includes fingerprint if available)
        jumpbox_info = outputs.get("goad_jumpbox_connection_info", {}).get("value", {})
        if jumpbox_info:
            jumpbox_ip = jumpbox_info.get("public_ip") or outputs.get("goad_jumpbox_public_ip", {}).get("value")
            
            fingerprints["hosts"]["jumpbox"] = {
                "ip": jumpbox_ip,
                "user": "ubuntu",
                "key_type": jumpbox_info.get("key_type", "ed25519"),
                "fingerprint": jumpbox_info.get("host_key_fingerprint", "Available after first boot - check /etc/ssh/ssh_host_ed25519_key.pub on host"),
                "how_to_verify": f"ssh-keyscan -t ed25519 {jumpbox_ip} 2>/dev/null | ssh-keygen -l -f -" if jumpbox_ip else "Deploy first to get IP"
            }
        
        # Internal key info (for verifying jumpbox can connect to internal hosts)
        internal_key_info = outputs.get("goad_internal_key_info", {}).get("value", {})
        if internal_key_info:
            fingerprints["internal_key"] = {
                "description": "Jumpbox's internal key for connecting to Team Server/Attack Box",
                "public_key_location": internal_key_info.get("public_key_location", "S3 bucket"),
                "note": "This key is generated ON the jumpbox - private key never leaves the host"
            }
        
        # Get bastion fingerprint if available
        bastion_ip = outputs.get("bastion_public_ip", {}).get("value")
        if bastion_ip:
            fingerprints["hosts"]["bastion"] = {
                "ip": bastion_ip,
                "user": "ubuntu",
                "key_type": "ed25519",
                "fingerprint": "Available after first boot",
                "how_to_verify": f"ssh-keyscan -t ed25519 {bastion_ip} 2>/dev/null | ssh-keygen -l -f -"
            }
        
        # Filter by specific host if requested
        if specific_host and specific_host in fingerprints["hosts"]:
            fingerprints["hosts"] = {specific_host: fingerprints["hosts"][specific_host]}
        
        return jsonify(fingerprints)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@bp.route('/connection-info/quick', methods=['GET'])
def get_quick_connection_info():
    """
    Get minimal connection info for quick access.
    Returns just the essential SSH commands needed to connect.
    
    Query params:
        project: project name (optional)
    """
    try:
        project_name = request.args.get('project')
        
        # Use project-specific service if provided
        if project_name:
            service = get_service_for_project(project_name)
            service.init()
            service.ensure_workspace()
        else:
            service = terraform_service
        
        # Get Terraform outputs
        output_result = service.output()
        outputs = output_result.get("outputs", {})
        
        # Get key IPs
        jumpbox_ip = outputs.get("goad_jumpbox_public_ip", {}).get("value")
        bastion_ip = outputs.get("bastion_public_ip", {}).get("value")
        teamserver_ip = outputs.get("goad_teamserver_private_ip", {}).get("value")
        
        quick_info = {
            "success": True,
            "project_name": project_name or "default"
        }
        
        if jumpbox_ip:
            quick_info["jumpbox"] = {
                "ip": jumpbox_ip,
                "ssh": f"ssh -i ~/.ssh/goad_key ubuntu@{jumpbox_ip}"
            }
            
            if teamserver_ip:
                quick_info["teamserver_tunnel"] = {
                    "ip": teamserver_ip,
                    "tunnel": f"ssh -i ~/.ssh/goad_key -L 50050:{teamserver_ip}:50050 ubuntu@{jumpbox_ip}",
                    "then": "Connect CS client to localhost:50050"
                }
        
        if bastion_ip:
            quick_info["bastion"] = {
                "ip": bastion_ip,
                "ssh": f"ssh -i ~/.ssh/goad_key ubuntu@{bastion_ip}"
            }
        
        if not jumpbox_ip and not bastion_ip:
            quick_info["message"] = "No deployment found or no public IPs available"
        
        return jsonify(quick_info)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# =============================================================================
# DEPRECATED: SSH PRIVATE KEY ENDPOINTS
# =============================================================================
# These endpoints are DEPRECATED and will be removed in a future version.
# Private keys are now generated on hosts and never transmitted.
# Users should use their own SSH key that they uploaded before deployment.
# =============================================================================

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
            "-var-file", str(terraform_service.tfvars_file.absolute())
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


# =============================================================================
# DEPLOYMENT DETAILS ENDPOINT
# =============================================================================

@bp.route('/deployment-details', methods=['GET'])
def get_deployment_details():
    """
    Get comprehensive deployment details including IPs, credentials, and access instructions.
    This is the primary endpoint for the Deployment Manager UI.
    """
    try:
        # Check if Terraform state exists
        state_file = terraform_service.terraform_dir / "terraform.tfstate"
        
        if not state_file.exists():
            return jsonify({
                "success": False,
                "error": "No deployment found",
                "has_deployment": False
            })
        
        # Get Terraform outputs
        output_result = terraform_service.output()
        
        if not output_result.get("success"):
            return jsonify({
                "success": False,
                "error": "Failed to get deployment outputs",
                "has_deployment": False
            })
        
        outputs = output_result.get("outputs", {})
        
        # Get deployment type
        deployment_type = outputs.get("deployment_type", {}).get("value", "")
        deployment_mode = outputs.get("deployment_mode", {}).get("value", {})
        
        if not deployment_type:
            return jsonify({
                "success": False,
                "error": "No active deployment",
                "has_deployment": False
            })
        
        # Determine deployment architecture
        is_c2_only = deployment_mode.get("is_c2_only", False)
        is_goad_only = deployment_mode.get("is_goad_only", False)
        is_combined = deployment_mode.get("is_combined", False)
        
        # Build response
        response = {
            "success": True,
            "has_deployment": True,
            "deployment_type": deployment_type,
            "architecture": "goad-only" if is_goad_only else ("combined" if is_combined else "c2-only"),
            
            # Cobalt Strike Connection Info
            "cobalt_strike": {
                "host": None,
                "port": outputs.get("cs_connection_info", {}).get("value", {}).get("port", 50050),
                "method": outputs.get("cs_connection_info", {}).get("value", {}).get("method", "ssh_tunnel"),
                "password": None  # User must know this - not stored in state
            },
            
            # C2 Infrastructure (if deployed)
            "infrastructure": {
                "c2_server": {
                    "private_ip": outputs.get("c2_server_primary_ip", {}).get("value"),
                    "public_ip": None  # C2 servers are in private subnets
                },
                "redirectors": outputs.get("proxy_redirector_public_ips", {}).get("value", []),
                "bastion": {
                    "ip": outputs.get("bastion_public_ip", {}).get("value"),
                    "password": None  # Retrieved separately
                }
            },
            
            # GOAD Lab (if deployed)
            "goad": {
                "deployed": is_goad_only or is_combined,
                "lab_type": outputs.get("goad_lab_type", {}).get("value"),
                "jumpbox": {
                    "public_ip": outputs.get("goad_jumpbox_public_ip", {}).get("value"),
                    "private_ip": outputs.get("goad_jumpbox_private_ip", {}).get("value"),
                    "ssh_command": outputs.get("goad_jumpbox_ssh_command", {}).get("value")
                },
                "vms": outputs.get("goad_lab_vms", {}).get("value", []),
                "domain_info": outputs.get("goad_domain_info", {}).get("value"),
                "credentials": outputs.get("goad_credentials", {}).get("value")
            },
            
            # VPC Peering (combined mode)
            "vpc_peering": {
                "enabled": is_combined,
                "connection_id": outputs.get("vpc_peering_connection_id", {}).get("value")
            },
            
            # Access Instructions
            "access_instructions": outputs.get("access_instructions", {}).get("value", {})
        }
        
        # Set CS host based on architecture
        if is_goad_only:
            response["cobalt_strike"]["host"] = outputs.get("goad_jumpbox_public_ip", {}).get("value")
            response["cobalt_strike"]["method"] = "direct"
        else:
            response["cobalt_strike"]["host"] = outputs.get("c2_server_primary_ip", {}).get("value")
            response["cobalt_strike"]["method"] = "ssh_tunnel"
        
        # Add GOAD lab info if applicable
        if response["goad"]["deployed"] and response["goad"]["lab_type"]:
            lab_info = get_lab_info(response["goad"]["lab_type"])
            if lab_info:
                response["goad"]["lab_info"] = {
                    "vm_count": lab_info.get("vm_count"),
                    "domains": lab_info.get("domains"),
                    "forests": lab_info.get("forests"),
                    "description": lab_info.get("description")
                }
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# =============================================================================
# GOAD STATUS ENDPOINT
# =============================================================================

@bp.route('/goad-status', methods=['GET'])
def get_goad_status():
    """
    Get GOAD Ansible provisioning status.
    Returns the status of AD configuration on GOAD VMs.
    """
    global deployment_state
    
    try:
        # Check if GOAD is deployed
        output_result = terraform_service.output()
        outputs = output_result.get("outputs", {})
        
        goad_deployed = outputs.get("goad_deployed", {}).get("value", False)
        
        if not goad_deployed:
            return jsonify({
                "success": True,
                "goad_deployed": False,
                "status": "not_deployed",
                "message": "GOAD lab is not deployed"
            })
        
        # Get current Ansible status from state
        ansible_status = deployment_state.get("goad_ansible_status", "unknown")
        
        # In a real implementation, we'd check the jumpbox for status
        # For now, return the tracked status
        return jsonify({
            "success": True,
            "goad_deployed": True,
            "status": ansible_status or "pending",
            "message": _get_ansible_status_message(ansible_status),
            "jumpbox_ip": outputs.get("goad_jumpbox_public_ip", {}).get("value"),
            "lab_type": outputs.get("goad_lab_type", {}).get("value")
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


def _get_ansible_status_message(status: str) -> str:
    """Get human-readable message for Ansible status."""
    messages = {
        "pending": "Ansible provisioning has not started yet. SSH to jumpbox and run: cd /opt/goad && ansible-playbook main.yml",
        "running": "Ansible provisioning is in progress. This may take 30-60 minutes.",
        "complete": "GOAD Active Directory configuration is complete!",
        "error": "Ansible provisioning encountered an error. Check logs on jumpbox.",
        "unknown": "Unable to determine Ansible status. SSH to jumpbox to check."
    }
    return messages.get(status, messages["unknown"])


# =============================================================================
# DEPRECATED: SSH KEY DOWNLOAD ENDPOINT
# =============================================================================
# ⚠️  DEPRECATED: This endpoint is deprecated and will be removed.
# 
# SECURITY CHANGE: Private keys are no longer generated by Terraform or
# transmitted via this API. Instead:
#   1. Users generate their own SSH key locally (ssh-keygen -t ed25519)
#   2. Users upload their PUBLIC key via the web UI before deployment
#   3. Internal keys are generated ON the hosts during bootstrap
#   4. Private keys NEVER leave the machine that generates them
#
# Use the new /connection-info endpoint for secure connection instructions.
# =============================================================================

@bp.route('/ssh-key/<key_type>', methods=['GET'])
def download_ssh_key(key_type: str):
    """
    ⚠️  DEPRECATED: This endpoint is deprecated.
    
    Private keys are no longer provided by this API for security reasons.
    
    NEW APPROACH:
    1. Generate your own SSH key: ssh-keygen -t ed25519 -f ~/.ssh/goad_key
    2. Upload your PUBLIC key via the web UI before deployment
    3. Use your private key to connect: ssh -i ~/.ssh/goad_key ubuntu@<jumpbox-ip>
    
    Use GET /connection-info for secure connection instructions.
    """
    # Return deprecation notice instead of keys
    return jsonify({
        "success": False,
        "deprecated": True,
        "error": "This endpoint is deprecated for security reasons.",
        "message": "Private keys are no longer provided by this API.",
        "migration_guide": {
            "step1": "Generate your own SSH key: ssh-keygen -t ed25519 -f ~/.ssh/goad_key",
            "step2": "Upload your PUBLIC key via the Deploy tab before deployment",
            "step3": "Use your private key to connect: ssh -i ~/.ssh/goad_key ubuntu@<jumpbox-ip>",
            "step4": "Use GET /deploy/connection-info for connection instructions"
        },
        "security_reason": "Private keys should never be transmitted over networks. "
                          "Keys are now generated on hosts and never leave them."
    }), 410  # 410 Gone - resource no longer available


@bp.route('/ssh-key/download', methods=['POST'])
def save_ssh_key_to_disk():
    """
    ⚠️  DEPRECATED: This endpoint is deprecated.
    
    Private keys are no longer provided by this API for security reasons.
    
    NEW APPROACH:
    1. Generate your own SSH key: ssh-keygen -t ed25519 -f ~/.ssh/goad_key
    2. Upload your PUBLIC key via the web UI before deployment
    3. Use your private key to connect: ssh -i ~/.ssh/goad_key ubuntu@<jumpbox-ip>
    
    Use GET /connection-info for secure connection instructions.
    """
    # Return deprecation notice instead of saving keys
    return jsonify({
        "success": False,
        "deprecated": True,
        "error": "This endpoint is deprecated for security reasons.",
        "message": "Private keys are no longer provided by this API.",
        "migration_guide": {
            "step1": "Generate your own SSH key: ssh-keygen -t ed25519 -f ~/.ssh/goad_key",
            "step2": "Upload your PUBLIC key via the Deploy tab before deployment",
            "step3": "Use your private key to connect: ssh -i ~/.ssh/goad_key ubuntu@<jumpbox-ip>",
            "step4": "Use GET /deploy/connection-info for connection instructions"
        },
        "security_reason": "Private keys should never be transmitted over networks. "
                          "Keys are now generated on hosts and never leave them."
    }), 410  # 410 Gone - resource no longer available


# Keep the old implementation commented for reference during migration
# TODO: Remove after migration is complete
"""
# OLD IMPLEMENTATION - DEPRECATED
@bp.route('/ssh-key/download', methods=['POST'])
def save_ssh_key_to_disk_OLD():
    # Save SSH key to user's ~/.ssh directory.
    # This endpoint is called from the UI to download and save the key.
    # ... (old implementation removed for security)
"""


# =============================================================================
# S3 UPLOAD ENDPOINT
# =============================================================================

@bp.route('/upload-to-s3', methods=['POST'])
def upload_to_s3():
    """
    Upload Cobalt Strike file to S3 bucket.
    The bucket must be created by Terraform first.
    """
    try:
        from webapp.backend.utils.s3_upload import upload_cs_file, S3UploadError
        from webapp.backend.utils.config_parser import ConfigParser
        
        # Get config for project name
        config_dir = project_root / "configs"
        tfvars_file = config_dir / "terraform.tfvars"
        
        if not tfvars_file.exists():
            return jsonify({
                "success": False,
                "error": "Configuration not found. Please configure deployment first."
            }), 400
        
        config = ConfigParser.parse_tfvars(tfvars_file)
        project_name = config.get('project_name', '')
        aws_region = config.get('aws_region', 'us-east-1')
        
        if not project_name:
            return jsonify({
                "success": False,
                "error": "Project name not configured"
            }), 400
        
        # Find local CS file
        cobalt_strike_files = [
            f for f in UPLOAD_FOLDER.glob("*")
            if f.is_file() and allowed_file(f.name)
        ]
        
        if not cobalt_strike_files:
            return jsonify({
                "success": False,
                "error": "No Cobalt Strike file found. Upload a file first."
            }), 400
        
        # Use most recent file
        cs_file = max(cobalt_strike_files, key=lambda f: f.stat().st_mtime)
        
        # Upload to S3
        s3_uri, bucket_name = upload_cs_file(
            str(cs_file),
            project_name,
            aws_region
        )
        
        return jsonify({
            "success": True,
            "message": "File uploaded to S3 successfully",
            "s3_uri": s3_uri,
            "bucket": bucket_name,
            "local_file": str(cs_file)
        })
        
    except S3UploadError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# =============================================================================
# STOP/START INFRASTRUCTURE ENDPOINTS
# =============================================================================

@bp.route('/stop', methods=['POST'])
def stop_infrastructure():
    """
    Stop all EC2 instances (keep resources, stop compute charges).
    This is a cost-saving measure that preserves all data and configuration.
    """
    try:
        import boto3
        from webapp.backend.utils.config_parser import ConfigParser
        
        # Get project name from request body or config
        data = request.get_json() or {}
        project_name = data.get('project_name')
        
        # Get config for region (and fallback project name)
        config_dir = project_root / "configs"
        tfvars_file = config_dir / "terraform.tfvars"
        
        config = ConfigParser.parse_tfvars(tfvars_file) if tfvars_file.exists() else {}
        aws_region = config.get('aws_region', 'us-east-1')
        
        # Use config project name as fallback
        if not project_name:
            project_name = config.get('project_name', '')
        
        if not project_name:
            return jsonify({
                "success": False,
                "error": "Project name not specified"
            }), 400
        
        # Connect to EC2
        ec2 = boto3.client('ec2', region_name=aws_region)
        
        # Find instances by project tag
        response = ec2.describe_instances(
            Filters=[
                {'Name': 'tag:Project', 'Values': [project_name]},
                {'Name': 'instance-state-name', 'Values': ['running']}
            ]
        )
        
        instance_ids = []
        for reservation in response.get('Reservations', []):
            for instance in reservation.get('Instances', []):
                instance_ids.append(instance['InstanceId'])
        
        if not instance_ids:
            return jsonify({
                "success": True,
                "message": "No running instances found",
                "stopped_count": 0
            })
        
        # Stop instances
        ec2.stop_instances(InstanceIds=instance_ids)
        
        return jsonify({
            "success": True,
            "message": f"Stopped {len(instance_ids)} instances",
            "stopped_count": len(instance_ids),
            "instance_ids": instance_ids
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@bp.route('/start', methods=['POST'])
def start_infrastructure():
    """
    Start all stopped EC2 instances.
    Resumes compute charges.
    """
    try:
        import boto3
        from webapp.backend.utils.config_parser import ConfigParser
        
        # Get project name from request body or config
        data = request.get_json() or {}
        project_name = data.get('project_name')
        
        # Get config for region (and fallback project name)
        config_dir = project_root / "configs"
        tfvars_file = config_dir / "terraform.tfvars"
        
        config = ConfigParser.parse_tfvars(tfvars_file) if tfvars_file.exists() else {}
        aws_region = config.get('aws_region', 'us-east-1')
        
        # Use config project name as fallback
        if not project_name:
            project_name = config.get('project_name', '')
        
        if not project_name:
            return jsonify({
                "success": False,
                "error": "Project name not specified"
            }), 400
        
        # Connect to EC2
        ec2 = boto3.client('ec2', region_name=aws_region)
        
        # Find stopped instances by project tag
        response = ec2.describe_instances(
            Filters=[
                {'Name': 'tag:Project', 'Values': [project_name]},
                {'Name': 'instance-state-name', 'Values': ['stopped']}
            ]
        )
        
        instance_ids = []
        for reservation in response.get('Reservations', []):
            for instance in reservation.get('Instances', []):
                instance_ids.append(instance['InstanceId'])
        
        if not instance_ids:
            return jsonify({
                "success": True,
                "message": "No stopped instances found",
                "started_count": 0
            })
        
        # Start instances
        ec2.start_instances(InstanceIds=instance_ids)
        
        return jsonify({
            "success": True,
            "message": f"Started {len(instance_ids)} instances",
            "started_count": len(instance_ids),
            "instance_ids": instance_ids
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@bp.route('/instance-status', methods=['GET'])
def get_instance_status():
    """
    Get the current status of all EC2 instances for this project.
    """
    try:
        import boto3
        from webapp.backend.utils.config_parser import ConfigParser
        
        # Get config
        config_dir = project_root / "configs"
        tfvars_file = config_dir / "terraform.tfvars"
        
        if not tfvars_file.exists():
            return jsonify({
                "success": False,
                "error": "Configuration not found"
            }), 400
        
        config = ConfigParser.parse_tfvars(tfvars_file)
        project_name = config.get('project_name', '')
        aws_region = config.get('aws_region', 'us-east-1')
        
        if not project_name:
            return jsonify({
                "success": False,
                "error": "Project name not configured"
            }), 400
        
        # Connect to EC2
        ec2 = boto3.client('ec2', region_name=aws_region)
        
        # Find all instances by project tag
        response = ec2.describe_instances(
            Filters=[
                {'Name': 'tag:Project', 'Values': [project_name]}
            ]
        )
        
        instances = []
        status_counts = {'running': 0, 'stopped': 0, 'pending': 0, 'stopping': 0, 'terminated': 0}
        
        for reservation in response.get('Reservations', []):
            for instance in reservation.get('Instances', []):
                state = instance['State']['Name']
                status_counts[state] = status_counts.get(state, 0) + 1
                
                # Get instance name from tags
                name = 'Unknown'
                for tag in instance.get('Tags', []):
                    if tag['Key'] == 'Name':
                        name = tag['Value']
                        break
                
                instances.append({
                    'id': instance['InstanceId'],
                    'name': name,
                    'state': state,
                    'type': instance['InstanceType'],
                    'private_ip': instance.get('PrivateIpAddress'),
                    'public_ip': instance.get('PublicIpAddress')
                })
        
        return jsonify({
            "success": True,
            "project_name": project_name,
            "region": aws_region,
            "instances": instances,
            "status_counts": status_counts,
            "total_instances": len(instances)
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# =============================================================================
# RESOURCE LIST ENDPOINT
# =============================================================================

@bp.route('/resources/project/<project_name>', methods=['GET'])
def get_project_resources(project_name: str):
    """
    Get resources for a specific project/deployment.
    When refresh=true, does a full AWS query for all resource types.
    Otherwise returns saved resources from deployment history.
    """
    try:
        import boto3
        from webapp.backend.utils.config_parser import ConfigParser
        from datetime import datetime
        
        # Load saved deployment resources for metadata
        resources_file = project_root / "logs" / "deployment_resources.json"
        deployment_data = {}
        
        if resources_file.exists():
            with open(resources_file, 'r') as f:
                all_deployments = json.load(f)
            deployment_data = all_deployments.get(project_name, {})
        
        aws_region = deployment_data.get('region', 'us-east-1')
        
        # Check if we should do a full AWS refresh
        refresh = request.args.get('refresh', 'false').lower() == 'true'
        
        if refresh:
            # Do a FULL AWS query for all resource types (same as save_deployment_resources)
            resources = []
            ec2 = boto3.client('ec2', region_name=aws_region)
            project_prefix = project_name.lower().replace('_', '-')
            
            # EC2 Instances (by tag)
            try:
                response = ec2.describe_instances(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for reservation in response.get('Reservations', []):
                    for instance in reservation.get('Instances', []):
                        # Skip terminated instances
                        if instance['State']['Name'] == 'terminated':
                            continue
                        name = next((t['Value'] for t in instance.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                        role = next((t['Value'] for t in instance.get('Tags', []) if t['Key'] == 'Role'), '')
                        resources.append({
                            'type': 'ec2',
                            'id': instance['InstanceId'],
                            'name': name,
                            'role': role,
                            'state': instance['State']['Name'],
                            'instance_type': instance['InstanceType'],
                            'private_ip': instance.get('PrivateIpAddress'),
                            'public_ip': instance.get('PublicIpAddress')
                        })
            except Exception as e:
                print(f"Error fetching EC2 instances: {e}")
            
            # VPCs (by tag)
            try:
                response = ec2.describe_vpcs(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for vpc in response.get('Vpcs', []):
                    name = next((t['Value'] for t in vpc.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                    resources.append({
                        'type': 'vpc',
                        'id': vpc['VpcId'],
                        'name': name,
                        'state': vpc['State'],
                        'cidr': vpc['CidrBlock']
                    })
            except Exception as e:
                print(f"Error fetching VPCs: {e}")
            
            # Subnets (by tag)
            try:
                response = ec2.describe_subnets(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for subnet in response.get('Subnets', []):
                    name = next((t['Value'] for t in subnet.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                    resources.append({
                        'type': 'subnet',
                        'id': subnet['SubnetId'],
                        'name': name,
                        'state': subnet['State'],
                        'cidr': subnet['CidrBlock'],
                        'az': subnet['AvailabilityZone']
                    })
            except Exception as e:
                print(f"Error fetching subnets: {e}")
            
            # Security Groups (by tag)
            try:
                response = ec2.describe_security_groups(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for sg in response.get('SecurityGroups', []):
                    resources.append({
                        'type': 'security_group',
                        'id': sg['GroupId'],
                        'name': sg['GroupName'],
                        'state': 'active',
                        'description': sg.get('Description', '')[:100]
                    })
            except Exception as e:
                print(f"Error fetching security groups: {e}")
            
            # NAT Gateways (by tag)
            try:
                response = ec2.describe_nat_gateways(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for nat in response.get('NatGateways', []):
                    if nat['State'] == 'deleted':
                        continue
                    name = next((t['Value'] for t in nat.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                    public_ip = nat.get('NatGatewayAddresses', [{}])[0].get('PublicIp', 'N/A')
                    resources.append({
                        'type': 'nat_gateway',
                        'id': nat['NatGatewayId'],
                        'name': name,
                        'state': nat['State'],
                        'public_ip': public_ip
                    })
            except Exception as e:
                print(f"Error fetching NAT gateways: {e}")
            
            # Elastic IPs (by tag)
            try:
                response = ec2.describe_addresses(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for eip in response.get('Addresses', []):
                    name = next((t['Value'] for t in eip.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                    resources.append({
                        'type': 'elastic_ip',
                        'id': eip.get('AllocationId', 'N/A'),
                        'name': name,
                        'state': 'associated' if eip.get('InstanceId') else 'available',
                        'public_ip': eip.get('PublicIp')
                    })
            except Exception as e:
                print(f"Error fetching Elastic IPs: {e}")
            
            # Internet Gateways (by tag)
            try:
                response = ec2.describe_internet_gateways(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for igw in response.get('InternetGateways', []):
                    name = next((t['Value'] for t in igw.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                    attached = 'attached' if igw.get('Attachments') else 'detached'
                    resources.append({
                        'type': 'internet_gateway',
                        'id': igw['InternetGatewayId'],
                        'name': name,
                        'state': attached
                    })
            except Exception as e:
                print(f"Error fetching Internet Gateways: {e}")
            
            # Key Pairs (by tag)
            try:
                response = ec2.describe_key_pairs(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for kp in response.get('KeyPairs', []):
                    resources.append({
                        'type': 'key_pair',
                        'id': kp.get('KeyPairId', kp['KeyName']),
                        'name': kp['KeyName'],
                        'state': 'available',
                        'key_type': kp.get('KeyType', 'rsa')
                    })
            except Exception as e:
                print(f"Error fetching key pairs: {e}")
            
            # Route Tables (by tag)
            try:
                response = ec2.describe_route_tables(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for rt in response.get('RouteTables', []):
                    name = next((t['Value'] for t in rt.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                    route_count = len(rt.get('Routes', []))
                    resources.append({
                        'type': 'route_table',
                        'id': rt['RouteTableId'],
                        'name': name,
                        'state': 'active',
                        'route_count': route_count
                    })
            except Exception as e:
                print(f"Error fetching route tables: {e}")
            
            # Network Interfaces (by tag)
            try:
                response = ec2.describe_network_interfaces(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for eni in response.get('NetworkInterfaces', []):
                    name = next((t['Value'] for t in eni.get('TagSet', []) if t['Key'] == 'Name'), 'Unnamed')
                    private_ip = eni.get('PrivateIpAddress', 'N/A')
                    resources.append({
                        'type': 'network_interface',
                        'id': eni['NetworkInterfaceId'],
                        'name': name,
                        'state': eni.get('Status', 'unknown'),
                        'private_ip': private_ip
                    })
            except Exception as e:
                print(f"Error fetching network interfaces: {e}")
            
            # S3 Buckets (by name prefix - no tags)
            try:
                s3 = boto3.client('s3', region_name=aws_region)
                response = s3.list_buckets()
                for bucket in response.get('Buckets', []):
                    if bucket['Name'].lower().startswith(project_prefix):
                        resources.append({
                            'type': 's3_bucket',
                            'id': bucket['Name'],
                            'name': bucket['Name'],
                            'state': 'available',
                            'created': bucket['CreationDate'].isoformat()
                        })
            except Exception as e:
                print(f"Error fetching S3 buckets: {e}")
            
            # IAM Roles (by name prefix - no tags)
            try:
                iam = boto3.client('iam', region_name=aws_region)
                paginator = iam.get_paginator('list_roles')
                for page in paginator.paginate():
                    for role in page.get('Roles', []):
                        if role['RoleName'].lower().startswith(project_prefix):
                            resources.append({
                                'type': 'iam_role',
                                'id': role['RoleId'],
                                'name': role['RoleName'],
                                'state': 'active',
                                'created': role['CreateDate'].isoformat()
                            })
            except Exception as e:
                print(f"Error fetching IAM roles: {e}")
            
            # IAM Instance Profiles (by name prefix - no tags)
            try:
                iam = boto3.client('iam', region_name=aws_region)
                paginator = iam.get_paginator('list_instance_profiles')
                for page in paginator.paginate():
                    for profile in page.get('InstanceProfiles', []):
                        if profile['InstanceProfileName'].lower().startswith(project_prefix):
                            resources.append({
                                'type': 'iam_instance_profile',
                                'id': profile['InstanceProfileId'],
                                'name': profile['InstanceProfileName'],
                                'state': 'active',
                                'role_count': len(profile.get('Roles', []))
                            })
            except Exception as e:
                print(f"Error fetching IAM instance profiles: {e}")
            
            # Update the saved resources file with the refreshed data
            if resources:
                try:
                    all_deployments = {}
                    if resources_file.exists():
                        with open(resources_file, 'r') as f:
                            all_deployments = json.load(f)
                    
                    if project_name not in all_deployments:
                        all_deployments[project_name] = {}
                    
                    all_deployments[project_name].update({
                        'project_name': project_name,
                        'deployed_at': all_deployments.get(project_name, {}).get('deployed_at', datetime.now().isoformat()),
                        'region': aws_region,
                        'resource_count': len(resources),
                        'resources': resources,
                        'last_refreshed': datetime.now().isoformat()
                    })
                    
                    with open(resources_file, 'w') as f:
                        json.dump(all_deployments, f, indent=2)
                except Exception as e:
                    print(f"Error saving refreshed resources: {e}")
        else:
            # Return saved resources
            resources = deployment_data.get('resources', [])
        
        # Group resources by type
        grouped = {}
        for r in resources:
            rtype = r['type']
            if rtype not in grouped:
                grouped[rtype] = []
            grouped[rtype].append(r)
        
        return jsonify({
            "success": True,
            "project_name": project_name,
            "deployment_type": deployment_data.get('deployment_type'),
            "deployed_at": deployment_data.get('deployed_at'),
            "region": aws_region,
            "resource_count": len(resources),
            "resources": resources,
            "resources_grouped": grouped
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@bp.route('/resources/all-projects', methods=['GET'])
def get_all_project_resources():
    """
    Get a summary of resources for all deployed projects.
    """
    try:
        resources_file = project_root / "logs" / "deployment_resources.json"
        
        if not resources_file.exists():
            return jsonify({
                "success": True,
                "projects": [],
                "message": "No deployments found"
            })
        
        with open(resources_file, 'r') as f:
            all_deployments = json.load(f)
        
        projects = []
        for project_name, data in all_deployments.items():
            projects.append({
                "project_name": project_name,
                "deployment_type": data.get('deployment_type'),
                "deployed_at": data.get('deployed_at'),
                "region": data.get('region'),
                "resource_count": data.get('resource_count', len(data.get('resources', [])))
            })
        
        # Sort by deployment time (newest first)
        projects.sort(key=lambda x: x.get('deployed_at', ''), reverse=True)
        
        return jsonify({
            "success": True,
            "projects": projects,
            "total_projects": len(projects)
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@bp.route('/outputs', methods=['GET'])
def get_terraform_outputs():
    """
    Get Terraform outputs for a specific project.
    Returns connection info like IPs, key names, etc.
    """
    try:
        import boto3
        from webapp.backend.utils.config_parser import ConfigParser
        
        # Get project name from query params
        project_name = request.args.get('project')
        
        # Get config for region and fallback project name
        config_dir = project_root / "configs"
        tfvars_file = config_dir / "terraform.tfvars"
        
        config = ConfigParser.parse_tfvars(tfvars_file) if tfvars_file.exists() else {}
        aws_region = config.get('aws_region', 'us-east-1')
        
        if not project_name:
            project_name = config.get('project_name', '')
        
        if not project_name:
            return jsonify({
                "success": False,
                "error": "Project name not specified"
            }), 400
        
        # Query AWS for instance details
        ec2 = boto3.client('ec2', region_name=aws_region)
        
        response = ec2.describe_instances(
            Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
        )
        
        outputs = {
            'project_name': project_name,
            'region': aws_region
        }
        
        # Extract instance info
        for reservation in response.get('Reservations', []):
            for instance in reservation.get('Instances', []):
                tags = {t['Key']: t['Value'] for t in instance.get('Tags', [])}
                role = tags.get('Role', '').lower()
                name = tags.get('Name', '')
                
                # Identify instance type by role or name
                if 'jumpbox' in role.lower() or 'jumpbox' in name.lower():
                    outputs['jumpbox_public_ip'] = instance.get('PublicIpAddress')
                    outputs['jumpbox_private_ip'] = instance.get('PrivateIpAddress')
                    outputs['jumpbox_instance_id'] = instance['InstanceId']
                    outputs['jumpbox_key_name'] = instance.get('KeyName')
                    outputs['jumpbox_state'] = instance['State']['Name']
                    
                elif 'dc01' in name.lower() or 'dc' in role.lower():
                    outputs['dc01_private_ip'] = instance.get('PrivateIpAddress')
                    outputs['dc01_instance_id'] = instance['InstanceId']
                    outputs['dc01_state'] = instance['State']['Name']
                    
                elif 'dc02' in name.lower():
                    outputs['dc02_private_ip'] = instance.get('PrivateIpAddress')
                    outputs['dc02_instance_id'] = instance['InstanceId']
                    outputs['dc02_state'] = instance['State']['Name']
                    
                elif 'team' in role.lower() or 'teamserver' in name.lower():
                    outputs['teamserver_private_ip'] = instance.get('PrivateIpAddress')
                    outputs['teamserver_instance_id'] = instance['InstanceId']
                    outputs['teamserver_state'] = instance['State']['Name']
                    
                elif 'attack' in role.lower() or 'attackbox' in name.lower():
                    outputs['attackbox_private_ip'] = instance.get('PrivateIpAddress')
                    outputs['attackbox_instance_id'] = instance['InstanceId']
                    outputs['attackbox_state'] = instance['State']['Name']
                    
                elif 'redirector' in role.lower() or 'redirector' in name.lower():
                    outputs['redirector_public_ip'] = instance.get('PublicIpAddress')
                    outputs['redirector_private_ip'] = instance.get('PrivateIpAddress')
                    outputs['redirector_instance_id'] = instance['InstanceId']
                    outputs['redirector_state'] = instance['State']['Name']
        
        # Get domain from config if available
        outputs['redirector_domain'] = config.get('primary_domain_name', '')
        
        # Get attackbox password from Terraform state if available
        try:
            service = get_service_for_project(project_name)
            service.init()
            service.ensure_workspace()
            tf_outputs = service.output()
            if tf_outputs.get("success"):
                tf_out = tf_outputs.get("outputs", {})
                # Get attackbox password from Terraform
                attackbox_pwd = tf_out.get("goad_attackbox_password", {}).get("value")
                if attackbox_pwd:
                    outputs['attackbox_password'] = attackbox_pwd
        except Exception as e:
            # If we can't get Terraform outputs, continue without password
            pass
        
        return jsonify({
            "success": True,
            "outputs": outputs
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@bp.route('/resources', methods=['GET'])
def get_all_resources():
    """
    Get a comprehensive list of ALL deployed AWS resources.
    Uses boto3 to query AWS directly for accurate resource information.
    
    Query params:
    - project: specific project name to filter by (optional)
    - all_projects: if 'true', fetch resources from all known projects
    """
    try:
        import boto3
        from webapp.backend.utils.config_parser import ConfigParser
        
        # Check query params
        specific_project = request.args.get('project')
        all_projects_flag = request.args.get('all_projects', 'false').lower() == 'true'
        
        # Get config for region
        config_dir = project_root / "configs"
        tfvars_file = config_dir / "terraform.tfvars"
        
        config = ConfigParser.parse_tfvars(tfvars_file) if tfvars_file.exists() else {}
        aws_region = config.get('aws_region', 'us-east-1')
        
        # Determine which project names to query
        project_names = []
        
        if specific_project:
            # Query specific project
            project_names = [specific_project]
        elif all_projects_flag:
            # Get all known project names from deployment history
            history = load_deployment_history()
            project_names = list(set(
                h.get('project_name') for h in history 
                if h.get('project_name')
            ))
            # Also include current config project
            current_project = config.get('project_name', '')
            if current_project and current_project not in project_names:
                project_names.append(current_project)
        else:
            # Default: use current config project
            project_name = config.get('project_name', '')
            if project_name:
                project_names = [project_name]
        
        if not project_names:
            return jsonify({
                "success": True,
                "resources": [],
                "message": "No project name configured"
            })
        
        resources = []
        
        # EC2 Client
        ec2 = boto3.client('ec2', region_name=aws_region)
        
        # Query resources for each project
        for project_name in project_names:
            # 1. EC2 Instances
            try:
                response = ec2.describe_instances(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for reservation in response.get('Reservations', []):
                    for instance in reservation.get('Instances', []):
                        name = next((t['Value'] for t in instance.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed')
                        role = next((t['Value'] for t in instance.get('Tags', []) if t['Key'] == 'Role'), '')
                        resources.append({
                            'type': 'ec2',
                            'name': name,
                            'id': instance['InstanceId'],
                            'state': instance['State']['Name'],
                            'details': f"{instance['InstanceType']} | {role}" if role else instance['InstanceType'],
                            'project': project_name
                        })
            except Exception as e:
                print(f"Error fetching EC2 instances for {project_name}: {e}")
            
            # 2. VPCs
            try:
                response = ec2.describe_vpcs(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for vpc in response.get('Vpcs', []):
                    name = next((t['Value'] for t in vpc.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed VPC')
                    resources.append({
                        'type': 'vpc',
                        'name': name,
                        'id': vpc['VpcId'],
                        'state': vpc['State'],
                        'details': vpc['CidrBlock'],
                        'project': project_name
                    })
            except Exception as e:
                print(f"Error fetching VPCs for {project_name}: {e}")
            
            # 3. Subnets
            try:
                response = ec2.describe_subnets(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for subnet in response.get('Subnets', []):
                    name = next((t['Value'] for t in subnet.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed Subnet')
                    resources.append({
                        'type': 'subnet',
                        'name': name,
                        'id': subnet['SubnetId'],
                        'state': subnet['State'],
                        'details': f"{subnet['CidrBlock']} | AZ: {subnet['AvailabilityZone']}",
                        'project': project_name
                    })
            except Exception as e:
                print(f"Error fetching subnets for {project_name}: {e}")
            
            # 4. Security Groups
            try:
                response = ec2.describe_security_groups(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for sg in response.get('SecurityGroups', []):
                    resources.append({
                        'type': 'sg',
                        'name': sg['GroupName'],
                        'id': sg['GroupId'],
                        'state': 'active',
                        'details': sg.get('Description', '')[:50],
                        'project': project_name
                    })
            except Exception as e:
                print(f"Error fetching security groups for {project_name}: {e}")
            
            # 5. Elastic IPs
            try:
                response = ec2.describe_addresses(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for eip in response.get('Addresses', []):
                    name = next((t['Value'] for t in eip.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed EIP')
                    resources.append({
                        'type': 'eip',
                        'name': name,
                        'id': eip.get('AllocationId', 'N/A'),
                        'state': 'associated' if eip.get('InstanceId') else 'available',
                        'details': eip.get('PublicIp', 'N/A'),
                        'project': project_name
                    })
            except Exception as e:
                print(f"Error fetching Elastic IPs for {project_name}: {e}")
            
            # 6. NAT Gateways
            try:
                response = ec2.describe_nat_gateways(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for nat in response.get('NatGateways', []):
                    name = next((t['Value'] for t in nat.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed NAT')
                    public_ip = nat.get('NatGatewayAddresses', [{}])[0].get('PublicIp', 'N/A')
                    resources.append({
                        'type': 'nat',
                        'name': name,
                        'id': nat['NatGatewayId'],
                        'state': nat['State'],
                        'details': f"Public IP: {public_ip}",
                        'project': project_name
                    })
            except Exception as e:
                print(f"Error fetching NAT Gateways for {project_name}: {e}")
            
            # 7. Internet Gateways
            try:
                response = ec2.describe_internet_gateways(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for igw in response.get('InternetGateways', []):
                    name = next((t['Value'] for t in igw.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed IGW')
                    attached = 'attached' if igw.get('Attachments') else 'detached'
                    resources.append({
                        'type': 'igw',
                        'name': name,
                        'id': igw['InternetGatewayId'],
                        'state': attached,
                        'details': '',
                        'project': project_name
                    })
            except Exception as e:
                print(f"Error fetching Internet Gateways for {project_name}: {e}")
            
            # 8. S3 Buckets (check for project-named buckets)
            try:
                s3 = boto3.client('s3', region_name=aws_region)
                response = s3.list_buckets()
                project_prefix = project_name.lower().replace('_', '-')
                for bucket in response.get('Buckets', []):
                    bucket_name_lower = bucket['Name'].lower()
                    # Must start with the project prefix to avoid matching longer project names
                    if bucket_name_lower.startswith(project_prefix):
                        resources.append({
                            'type': 's3',
                            'name': bucket['Name'],
                            'id': bucket['Name'],
                            'state': 'available',
                            'details': f"Created: {bucket['CreationDate'].strftime('%Y-%m-%d')}",
                            'project': project_name
                        })
            except Exception as e:
                print(f"Error fetching S3 buckets for {project_name}: {e}")
            
            # 9. Key Pairs
            try:
                response = ec2.describe_key_pairs(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for kp in response.get('KeyPairs', []):
                    resources.append({
                        'type': 'keypair',
                        'name': kp['KeyName'],
                        'id': kp.get('KeyPairId', kp['KeyName']),
                        'state': 'available',
                        'details': f"Type: {kp.get('KeyType', 'rsa')}",
                        'project': project_name
                    })
            except Exception as e:
                print(f"Error fetching key pairs for {project_name}: {e}")
            
            # 10. Route Tables
            try:
                response = ec2.describe_route_tables(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for rt in response.get('RouteTables', []):
                    name = next((t['Value'] for t in rt.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed Route Table')
                    route_count = len(rt.get('Routes', []))
                    resources.append({
                        'type': 'rtb',
                        'name': name,
                        'id': rt['RouteTableId'],
                        'state': 'active',
                        'details': f"{route_count} routes",
                        'project': project_name
                    })
            except Exception as e:
                print(f"Error fetching route tables for {project_name}: {e}")
            
            # 11. VPC Peering Connections
            try:
                response = ec2.describe_vpc_peering_connections(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for pcx in response.get('VpcPeeringConnections', []):
                    name = next((t['Value'] for t in pcx.get('Tags', []) if t['Key'] == 'Name'), 'Unnamed Peering')
                    requester = pcx.get('RequesterVpcInfo', {}).get('VpcId', 'N/A')
                    accepter = pcx.get('AccepterVpcInfo', {}).get('VpcId', 'N/A')
                    resources.append({
                        'type': 'pcx',
                        'name': name,
                        'id': pcx['VpcPeeringConnectionId'],
                        'state': pcx.get('Status', {}).get('Code', 'unknown'),
                        'details': f"{requester} ↔ {accepter}",
                        'project': project_name
                    })
            except Exception as e:
                print(f"Error fetching VPC peering connections for {project_name}: {e}")
            
            # 12. Network Interfaces (ENIs)
            try:
                response = ec2.describe_network_interfaces(
                    Filters=[{'Name': 'tag:Project', 'Values': [project_name]}]
                )
                for eni in response.get('NetworkInterfaces', []):
                    name = next((t['Value'] for t in eni.get('TagSet', []) if t['Key'] == 'Name'), 'Unnamed ENI')
                    private_ip = eni.get('PrivateIpAddress', 'N/A')
                    resources.append({
                        'type': 'eni',
                        'name': name,
                        'id': eni['NetworkInterfaceId'],
                        'state': eni.get('Status', 'unknown'),
                        'details': f"Private IP: {private_ip}",
                        'project': project_name
                    })
            except Exception as e:
                print(f"Error fetching network interfaces for {project_name}: {e}")
            
            # 13. IAM Roles (for CS download)
            try:
                iam = boto3.client('iam', region_name=aws_region)
                project_prefix = project_name.lower().replace('_', '-')
                # List roles and filter by project name prefix - must START with prefix to avoid substring matches
                paginator = iam.get_paginator('list_roles')
                for page in paginator.paginate():
                    for role in page.get('Roles', []):
                        role_name_lower = role['RoleName'].lower()
                        # Must start with the project prefix to avoid matching longer project names
                        if role_name_lower.startswith(project_prefix):
                            resources.append({
                                'type': 'iam-role',
                                'name': role['RoleName'],
                                'id': role['RoleId'],
                                'state': 'active',
                                'details': f"Created: {role['CreateDate'].strftime('%Y-%m-%d')}",
                                'project': project_name
                            })
            except Exception as e:
                print(f"Error fetching IAM roles for {project_name}: {e}")
            
            # 14. IAM Instance Profiles
            try:
                iam = boto3.client('iam', region_name=aws_region)
                project_prefix = project_name.lower().replace('_', '-')
                paginator = iam.get_paginator('list_instance_profiles')
                for page in paginator.paginate():
                    for profile in page.get('InstanceProfiles', []):
                        profile_name_lower = profile['InstanceProfileName'].lower()
                        # Must start with the project prefix to avoid matching longer project names
                        if profile_name_lower.startswith(project_prefix):
                            resources.append({
                                'type': 'iam-profile',
                                'name': profile['InstanceProfileName'],
                                'id': profile['InstanceProfileId'],
                                'state': 'active',
                                'details': f"Roles: {len(profile.get('Roles', []))}",
                                'project': project_name
                            })
            except Exception as e:
                print(f"Error fetching IAM instance profiles for {project_name}: {e}")
            
            # 15. Route 53 Hosted Zones
            try:
                route53 = boto3.client('route53', region_name=aws_region)
                project_prefix = project_name.lower().replace('_', '-')
                response = route53.list_hosted_zones()
                for zone in response.get('HostedZones', []):
                    # Check if zone name matches any configured domain
                    zone_name = zone['Name'].rstrip('.')
                    zone_name_lower = zone_name.lower()
                    comment = zone.get('Config', {}).get('Comment', '')
                    # Must start with project prefix or have exact project name in comment
                    if zone_name_lower.startswith(project_prefix) or comment == project_name:
                        resources.append({
                            'type': 'route53-zone',
                            'name': zone_name,
                            'id': zone['Id'].split('/')[-1],
                            'state': 'active',
                            'details': f"Records: {zone.get('ResourceRecordSetCount', 0)}",
                            'project': project_name
                        })
            except Exception as e:
                print(f"Error fetching Route 53 hosted zones for {project_name}: {e}")
            
            # 16. ACM Certificates
            try:
                acm = boto3.client('acm', region_name=aws_region)
                project_prefix = project_name.lower().replace('_', '-')
                response = acm.list_certificates()
                for cert in response.get('CertificateSummaryList', []):
                    domain = cert.get('DomainName', '')
                    domain_lower = domain.lower()
                    # Check if certificate is for a project domain - must start with prefix
                    if domain_lower.startswith(project_prefix):
                        resources.append({
                            'type': 'acm-cert',
                            'name': domain,
                            'id': cert['CertificateArn'].split('/')[-1],
                            'state': cert.get('Status', 'unknown').lower(),
                            'details': f"Type: {cert.get('Type', 'N/A')}",
                            'project': project_name
                        })
            except Exception as e:
                print(f"Error fetching ACM certificates for {project_name}: {e}")
        
        return jsonify({
            "success": True,
            "resources": resources,
            "total_count": len(resources),
            "project_name": project_name,
            "region": aws_region
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "resources": []
        }), 500


# =============================================================================
# DEPLOYMENT HISTORY ENDPOINT
# =============================================================================

@bp.route('/history', methods=['GET'])
def get_deployment_history():
    """Get deployment history"""
    try:
        history = load_deployment_history()
        return jsonify({
            "success": True,
            "history": history,
            "total_entries": len(history)
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "history": []
        }), 500


@bp.route('/history', methods=['DELETE'])
def clear_deployment_history():
    """Clear deployment history"""
    try:
        if HISTORY_FILE.exists():
            HISTORY_FILE.unlink()
        return jsonify({
            "success": True,
            "message": "Deployment history cleared"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@bp.route('/history/add', methods=['POST'])
def add_deployment_history():
    """Add a log entry to deployment history"""
    try:
        data = request.get_json() or {}
        message = data.get('message', '')
        level = data.get('level', 'info')
        details = data.get('details')
        
        if not message:
            return jsonify({
                "success": False,
                "error": "Message is required"
            }), 400
        
        add_history_entry(message, level, details)
        
        return jsonify({
            "success": True,
            "message": "Log entry added"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
