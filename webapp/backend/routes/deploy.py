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

from webapp.backend.services.terraform_service import TerraformService
from webapp.backend.utils.goad_template_processor import get_lab_info, extract_vm_info

bp = Blueprint('deploy', __name__)

# File storage directory (local to user's machine)
UPLOAD_FOLDER = project_root / "uploads"
ALLOWED_EXTENSIONS = {'tar', 'gz', 'zip', 'tar.gz'}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB

# SSH keys directory
SSH_KEYS_FOLDER = project_root / "ssh_keys"

# Ensure directories exist
UPLOAD_FOLDER.mkdir(exist_ok=True)
SSH_KEYS_FOLDER.mkdir(exist_ok=True)

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

def add_history_entry(message, level='info', details=None):
    """Add an entry to deployment history"""
    from datetime import datetime
    history = load_deployment_history()
    history.append({
        'timestamp': datetime.now().isoformat(),
        'level': level,
        'message': message,
        'details': details
    })
    save_deployment_history(history)

# =============================================================================

# Deployment state (in-memory, simple implementation)
deployment_state = {
    "status": "idle",  # idle, running, success, error
    "step": "",
    "output": "",
    "error": None,
    "deployment_type": None,
    "goad_ansible_status": None,  # pending, running, complete, error
    # Enhanced progress tracking
    "started_at": None,
    "completed_at": None,
    "progress_percent": 0,
    "current_phase": "",
    "phases_completed": [],
    "logs": []  # List of {timestamp, message, type}
}

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

def add_log(message, log_type="info"):
    """Add a log entry to deployment state and persistent history"""
    deployment_state["logs"].append({
        "timestamp": time.time(),
        "message": message,
        "type": log_type  # info, success, warning, error
    })
    # Also save to persistent history
    add_history_entry(message, log_type)

def update_phase(phase_name, deployment_type="c2"):
    """Update current phase and calculate progress"""
    phases = DEPLOYMENT_PHASES.get(deployment_type, DEPLOYMENT_PHASES["c2"])
    
    # Find current phase index
    current_idx = -1
    for i, phase in enumerate(phases):
        if phase["name"] == phase_name:
            current_idx = i
            break
    
    if current_idx >= 0:
        # Calculate progress percentage
        deployment_state["progress_percent"] = int((current_idx / len(phases)) * 100)
        deployment_state["current_phase"] = phases[current_idx]["label"]
        deployment_state["step"] = phases[current_idx]["label"]
        
        # Calculate estimated time remaining
        remaining_time = sum(p["est_time"] for p in phases[current_idx:])
        deployment_state["est_remaining_seconds"] = remaining_time
        
        add_log(f"Started: {phases[current_idx]['label']}", "info")

def complete_phase(phase_name, deployment_type="c2"):
    """Mark a phase as completed"""
    phases = DEPLOYMENT_PHASES.get(deployment_type, DEPLOYMENT_PHASES["c2"])
    
    for phase in phases:
        if phase["name"] == phase_name:
            if phase_name not in deployment_state["phases_completed"]:
                deployment_state["phases_completed"].append(phase_name)
                add_log(f"Completed: {phase['label']}", "success")
            break

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
    """Run deployment in background thread with enhanced progress tracking"""
    global deployment_state
    
    try:
        # Reset state
        deployment_state["status"] = "running"
        deployment_state["step"] = "Initializing..."
        deployment_state["output"] = ""
        deployment_state["error"] = None
        deployment_state["started_at"] = time.time()
        deployment_state["completed_at"] = None
        deployment_state["progress_percent"] = 0
        deployment_state["phases_completed"] = []
        deployment_state["logs"] = []
        deployment_state["est_remaining_seconds"] = 0
        
        # Determine deployment type from config
        from webapp.backend.utils.config_parser import ConfigParser
        config_dir = project_root / "configs"
        tfvars_file = config_dir / "terraform.tfvars"
        config = ConfigParser.parse_tfvars(tfvars_file) if tfvars_file.exists() else {}
        
        deploy_type = config.get('deployment_type', 'c2-adhoc')
        if 'combined' in deploy_type:
            phase_type = "combined"
        elif 'goad' in deploy_type:
            phase_type = "goad"
        else:
            phase_type = "c2"
        
        deployment_state["deployment_type"] = deploy_type
        add_log(f"Starting deployment: {deploy_type}", "info")
        
        # Phase 1: Initialize
        update_phase("init", phase_type)
        result = terraform_service.init()
        if not result["success"]:
            deployment_state["status"] = "error"
            deployment_state["error"] = result.get("stderr", "Terraform init failed")
            add_log(f"Error: {deployment_state['error']}", "error")
            return
        complete_phase("init", phase_type)
        
        # Phase 2: Validate
        update_phase("validate", phase_type)
        result = terraform_service.validate()
        if not result["success"]:
            deployment_state["status"] = "error"
            deployment_state["error"] = result.get("stderr", "Validation failed")
            add_log(f"Error: {deployment_state['error']}", "error")
            return
        complete_phase("validate", phase_type)
        
        # Phase 3: Plan
        update_phase("plan", phase_type)
        result = terraform_service.plan()
        if not result["success"] and result["exit_code"] != 2:  # 2 means changes detected
            deployment_state["status"] = "error"
            deployment_state["error"] = result.get("stderr", "Plan failed")
            add_log(f"Error: {deployment_state['error']}", "error")
            return
        complete_phase("plan", phase_type)
        
        # Phase 4+: Apply (this is the long one)
        # Note: Terraform apply handles all resources together, but we simulate progress
        if phase_type == "c2":
            update_phase("apply_vpc", phase_type)
        elif phase_type == "goad":
            update_phase("apply_vpc", phase_type)
        else:
            update_phase("apply_c2_vpc", phase_type)
        
        add_log("Applying Terraform changes (this may take 5-15 minutes)...", "info")
        result = terraform_service.apply()
        
        if not result["success"]:
            deployment_state["status"] = "error"
            deployment_state["error"] = result.get("stderr", "Apply failed")
            add_log(f"Error: {deployment_state['error']}", "error")
            return
        
        # Mark infrastructure phases complete
        if phase_type == "c2":
            for p in ["apply_vpc", "apply_security", "apply_instances", "apply_config"]:
                complete_phase(p, phase_type)
        elif phase_type == "goad":
            for p in ["apply_vpc", "apply_jumpbox", "apply_windows"]:
                complete_phase(p, phase_type)
        else:
            for p in ["apply_c2_vpc", "apply_goad_vpc", "apply_peering", "apply_c2", "apply_goad"]:
                complete_phase(p, phase_type)
        
        # Phase: Get outputs
        update_phase("outputs", phase_type)
        result = terraform_service.output()
        complete_phase("outputs", phase_type)
        
        # Success!
        deployment_state["status"] = "success"
        deployment_state["step"] = "Deployment complete"
        deployment_state["progress_percent"] = 100
        deployment_state["completed_at"] = time.time()
        deployment_state["output"] = result.get("outputs", {})
        deployment_state["est_remaining_seconds"] = 0
        
        elapsed = int(deployment_state["completed_at"] - deployment_state["started_at"])
        add_log(f"Deployment completed successfully in {elapsed // 60}m {elapsed % 60}s", "success")
        
    except Exception as e:
        deployment_state["status"] = "error"
        deployment_state["error"] = str(e)
        deployment_state["completed_at"] = time.time()
        add_log(f"Unexpected error: {str(e)}", "error")

def run_destroy():
    """Run destroy in background thread with phased destruction for combined mode"""
    global deployment_state
    
    try:
        deployment_state["status"] = "running"
        deployment_state["output"] = ""
        deployment_state["error"] = None
        
        # Get current deployment type
        output_result = terraform_service.output()
        outputs = output_result.get("outputs", {})
        deployment_type = outputs.get("deployment_type", {}).get("value", "")
        
        # Check if combined mode (requires phased destruction)
        is_combined = deployment_type.startswith("combined-")
        
        if is_combined:
            # Phase 1: Destroy VPC peering first
            deployment_state["step"] = "Phase 1/3: Destroying VPC peering..."
            result = terraform_service.destroy_target("module.vpc_peering")
            if not result["success"]:
                deployment_state["status"] = "error"
                deployment_state["error"] = result.get("stderr", "Failed to destroy VPC peering")
                return
            
            # Phase 2: Destroy GOAD
            deployment_state["step"] = "Phase 2/3: Destroying GOAD lab..."
            result = terraform_service.destroy_target("module.goad")
            if not result["success"]:
                deployment_state["status"] = "error"
                deployment_state["error"] = result.get("stderr", "Failed to destroy GOAD")
                return
            
            # Phase 3: Destroy remaining C2 infrastructure
            deployment_state["step"] = "Phase 3/3: Destroying C2 infrastructure..."
            result = terraform_service.destroy()
            if not result["success"]:
                deployment_state["status"] = "error"
                deployment_state["error"] = result.get("stderr", "Failed to destroy C2 infrastructure")
                return
        else:
            # Standard destroy for non-combined modes
            deployment_state["step"] = "Destroying infrastructure..."
        result = terraform_service.destroy()
        if not result["success"]:
            deployment_state["status"] = "error"
            deployment_state["error"] = result.get("stderr", "Destroy failed")
            return
        
        deployment_state["status"] = "success"
        deployment_state["step"] = "Infrastructure destroyed"
        deployment_state["deployment_type"] = None
        
    except Exception as e:
        deployment_state["status"] = "error"
        deployment_state["error"] = str(e)

@bp.route('/status', methods=['GET'])
def get_deployment_status():
    """Get current deployment status with enhanced progress info"""
    # Calculate elapsed time if running
    elapsed_seconds = 0
    if deployment_state["started_at"]:
        if deployment_state["completed_at"]:
            elapsed_seconds = int(deployment_state["completed_at"] - deployment_state["started_at"])
        else:
            elapsed_seconds = int(time.time() - deployment_state["started_at"])
    
    # Format elapsed time
    elapsed_formatted = f"{elapsed_seconds // 60}m {elapsed_seconds % 60}s"
    
    # Format estimated remaining
    est_remaining = deployment_state.get("est_remaining_seconds", 0)
    est_remaining_formatted = f"{est_remaining // 60}m {est_remaining % 60}s" if est_remaining > 0 else "Calculating..."
    
    return jsonify({
        "success": True,
        "status": {
            "status": deployment_state["status"],
            "step": deployment_state["step"],
            "output": deployment_state["output"],
            "error": deployment_state["error"],
            "deployment_type": deployment_state.get("deployment_type"),
            # Enhanced progress info
            "progress_percent": deployment_state.get("progress_percent", 0),
            "current_phase": deployment_state.get("current_phase", ""),
            "phases_completed": deployment_state.get("phases_completed", []),
            "elapsed_seconds": elapsed_seconds,
            "elapsed_formatted": elapsed_formatted,
            "est_remaining_seconds": est_remaining,
            "est_remaining_formatted": est_remaining_formatted,
            "logs": deployment_state.get("logs", [])[-20:]  # Last 20 log entries
        }
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
    
    # Load configuration to check deployment type
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
    deployment_type = config.get('deployment_type', '').strip()
    
    # Define which deployment types require what prerequisites
    # GOAD deployments: CS on jumpbox (no redirectors), so NO domain needed but CS IS needed
    # C2 deployments: Full C2 infra with redirectors, needs domain for SSL/routing
    # Combined: Both GOAD + C2 infra, needs everything
    GOAD_ONLY_TYPES = ['goad-mini', 'goad-minilab', 'goad-light', 'goad-sccm', 'goad-full', 'goad-nha']
    C2_ONLY_TYPES = ['c2-adhoc', 'c2-purple', 'c2-full']
    COMBINED_TYPES = ['combined-adhoc-mini', 'combined-adhoc-light', 'combined-full-full']
    
    # All deployments with CS need the CS file uploaded
    # GOAD has CS on jumpbox, C2 has CS on team servers, Combined has both
    requires_cobalt_strike = True  # All our deployment types include CS
    
    # Only C2 and Combined need domain (for redirector SSL certs and routing)
    # GOAD connects directly to jumpbox, no domain needed
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
    
    # Check prerequisite: Domain configuration (only for C2 and combined deployments)
    if requires_domain:
        primary_domain = config.get('primary_domain_name', '').strip()
        
        if not primary_domain:
            return jsonify({
                "success": False,
                "error": "Domain configuration is required for C2 deployments. Please configure primary_domain_name in terraform.tfvars."
            }), 400
        
        domain_valid, domain_errors = ConfigValidator.validate_domain_config(config)
        if not domain_valid:
            return jsonify({
                "success": False,
                "error": f"Domain configuration is invalid: {', '.join(domain_errors)}"
            }), 400
    
    # Log what we're deploying
    add_history_entry(f"Starting deployment: {deployment_type}", "info")
    
    # Start deployment in background thread
    thread = threading.Thread(target=run_deployment)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "success": True,
        "message": f"Deployment started for {deployment_type}"
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
            add_history_entry("Auto-initializing Terraform...", "info")
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
        add_history_entry("Running Terraform plan...", "info")
        result = terraform_service.plan()
        
        # Get combined output
        full_output = result.get("full_output", "") or result.get("stdout", "") or result.get("stderr", "")
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        
        if result["success"]:
            add_history_entry("Terraform plan completed successfully", "success")
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
            
            add_history_entry(f"Terraform plan failed: {error_type}", "error")
            
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
        
        add_history_entry(f"Plan error: {error_msg}", "error")
        
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
# SSH KEY DOWNLOAD ENDPOINT
# =============================================================================

@bp.route('/ssh-key/<key_type>', methods=['GET'])
def download_ssh_key(key_type: str):
    """
    Get SSH private key for jumpbox or Windows VMs.
    Keys are retrieved from Terraform outputs and saved locally.
    
    Args:
        key_type: 'jumpbox' or 'windows'
    """
    try:
        if key_type not in ['jumpbox', 'windows']:
            return jsonify({
                "success": False,
                "error": "Invalid key type. Use 'jumpbox' or 'windows'"
            }), 400
        
        # Get key from Terraform outputs
        output_result = terraform_service.output()
        outputs = output_result.get("outputs", {})
        
        if key_type == 'jumpbox':
            key_content = outputs.get("goad_jumpbox_ssh_private_key", {}).get("value")
            filename = "goad-jumpbox.pem"
        else:
            key_content = outputs.get("goad_windows_ssh_private_key", {}).get("value")
            filename = "goad-windows.pem"
        
        if not key_content:
            return jsonify({
                "success": False,
                "error": f"SSH key not found. GOAD may not be deployed."
            }), 404
        
        # Save key to file
        key_path = SSH_KEYS_FOLDER / filename
        with open(key_path, 'w') as f:
            f.write(key_content)
        os.chmod(key_path, 0o600)
        
        return jsonify({
            "success": True,
            "message": f"SSH key saved to {key_path}",
            "path": str(key_path),
            "filename": filename,
            "chmod_command": f"chmod 600 {key_path}"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


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
        
        # Get config for project name and region
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
        
        # Get config for project name and region
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

@bp.route('/resources', methods=['GET'])
def get_all_resources():
    """
    Get a comprehensive list of ALL deployed AWS resources for this project.
    Uses boto3 to query AWS directly for accurate resource information.
    """
    try:
        import boto3
        from webapp.backend.utils.config_parser import ConfigParser
        
        # Get config
        config_dir = project_root / "configs"
        tfvars_file = config_dir / "terraform.tfvars"
        
        if not tfvars_file.exists():
            return jsonify({
                "success": True,
                "resources": [],
                "message": "No configuration found"
            })
        
        config = ConfigParser.parse_tfvars(tfvars_file)
        project_name = config.get('project_name', '')
        aws_region = config.get('aws_region', 'us-east-1')
        
        if not project_name:
            return jsonify({
                "success": True,
                "resources": [],
                "message": "No project name configured"
            })
        
        resources = []
        
        # EC2 Client
        ec2 = boto3.client('ec2', region_name=aws_region)
        
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
                        'details': f"{instance['InstanceType']} | {role}" if role else instance['InstanceType']
                    })
        except Exception as e:
            print(f"Error fetching EC2 instances: {e}")
        
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
                    'details': vpc['CidrBlock']
                })
        except Exception as e:
            print(f"Error fetching VPCs: {e}")
        
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
                    'details': f"{subnet['CidrBlock']} | AZ: {subnet['AvailabilityZone']}"
                })
        except Exception as e:
            print(f"Error fetching subnets: {e}")
        
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
                    'details': sg.get('Description', '')[:50]
                })
        except Exception as e:
            print(f"Error fetching security groups: {e}")
        
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
                    'details': eip.get('PublicIp', 'N/A')
                })
        except Exception as e:
            print(f"Error fetching Elastic IPs: {e}")
        
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
                    'details': f"Public IP: {public_ip}"
                })
        except Exception as e:
            print(f"Error fetching NAT Gateways: {e}")
        
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
                    'details': ''
                })
        except Exception as e:
            print(f"Error fetching Internet Gateways: {e}")
        
        # 8. S3 Buckets (check for project-named buckets)
        try:
            s3 = boto3.client('s3', region_name=aws_region)
            response = s3.list_buckets()
            project_prefix = project_name.lower().replace('_', '-')
            for bucket in response.get('Buckets', []):
                if project_prefix in bucket['Name'].lower():
                    resources.append({
                        'type': 's3',
                        'name': bucket['Name'],
                        'id': bucket['Name'],
                        'state': 'available',
                        'details': f"Created: {bucket['CreationDate'].strftime('%Y-%m-%d')}"
                    })
        except Exception as e:
            print(f"Error fetching S3 buckets: {e}")
        
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
                    'details': f"Type: {kp.get('KeyType', 'rsa')}"
                })
        except Exception as e:
            print(f"Error fetching key pairs: {e}")
        
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
                    'details': f"{route_count} routes"
                })
        except Exception as e:
            print(f"Error fetching route tables: {e}")
        
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
                    'details': f"{requester} ↔ {accepter}"
                })
        except Exception as e:
            print(f"Error fetching VPC peering connections: {e}")
        
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
                    'details': f"Private IP: {private_ip}"
                })
        except Exception as e:
            print(f"Error fetching network interfaces: {e}")
        
        # 13. IAM Roles (for CS download)
        try:
            iam = boto3.client('iam', region_name=aws_region)
            # List roles and filter by project name prefix
            paginator = iam.get_paginator('list_roles')
            for page in paginator.paginate():
                for role in page.get('Roles', []):
                    if project_prefix in role['RoleName'].lower() or 'cs-download' in role['RoleName'].lower():
                        resources.append({
                            'type': 'iam-role',
                            'name': role['RoleName'],
                            'id': role['RoleId'],
                            'state': 'active',
                            'details': f"Created: {role['CreateDate'].strftime('%Y-%m-%d')}"
                        })
        except Exception as e:
            print(f"Error fetching IAM roles: {e}")
        
        # 14. IAM Instance Profiles
        try:
            iam = boto3.client('iam', region_name=aws_region)
            paginator = iam.get_paginator('list_instance_profiles')
            for page in paginator.paginate():
                for profile in page.get('InstanceProfiles', []):
                    if project_prefix in profile['InstanceProfileName'].lower() or 'cs-download' in profile['InstanceProfileName'].lower():
                        resources.append({
                            'type': 'iam-profile',
                            'name': profile['InstanceProfileName'],
                            'id': profile['InstanceProfileId'],
                            'state': 'active',
                            'details': f"Roles: {len(profile.get('Roles', []))}"
                        })
        except Exception as e:
            print(f"Error fetching IAM instance profiles: {e}")
        
        # 15. Route 53 Hosted Zones
        try:
            route53 = boto3.client('route53', region_name=aws_region)
            response = route53.list_hosted_zones()
            for zone in response.get('HostedZones', []):
                # Check if zone name matches any configured domain
                zone_name = zone['Name'].rstrip('.')
                if project_prefix in zone_name.lower() or zone.get('Config', {}).get('Comment', '').find(project_name) != -1:
                    resources.append({
                        'type': 'route53-zone',
                        'name': zone_name,
                        'id': zone['Id'].split('/')[-1],
                        'state': 'active',
                        'details': f"Records: {zone.get('ResourceRecordSetCount', 0)}"
                    })
        except Exception as e:
            print(f"Error fetching Route 53 hosted zones: {e}")
        
        # 16. ACM Certificates
        try:
            acm = boto3.client('acm', region_name=aws_region)
            response = acm.list_certificates()
            for cert in response.get('CertificateSummaryList', []):
                domain = cert.get('DomainName', '')
                # Check if certificate is for a project domain
                if project_prefix in domain.lower():
                    resources.append({
                        'type': 'acm-cert',
                        'name': domain,
                        'id': cert['CertificateArn'].split('/')[-1],
                        'state': cert.get('Status', 'unknown').lower(),
                        'details': f"Type: {cert.get('Type', 'N/A')}"
                    })
        except Exception as e:
            print(f"Error fetching ACM certificates: {e}")
        
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
