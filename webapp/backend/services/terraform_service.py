"""
Terraform Service
Wrapper for Terraform CLI operations
"""

import subprocess
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Timeout constants (in seconds)
TIMEOUT_INIT = 300          # 5 minutes for init
TIMEOUT_VALIDATE = 60       # 1 minute for validate
TIMEOUT_PLAN = 600          # 10 minutes for plan
TIMEOUT_APPLY = 1800        # 30 minutes for apply
TIMEOUT_DESTROY = 3600      # 60 minutes for destroy (increased for combined deployments)
TIMEOUT_OUTPUT = 60         # 1 minute for output
TIMEOUT_SHOW = 120          # 2 minutes for show


class TerraformService:
    """Service for executing Terraform commands"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.terraform_dir = project_root / "terraform"
        self.config_dir = project_root / "configs"
        self.tfvars_file = self.config_dir / "terraform.tfvars"
    
    def _run_command(self, command: List[str], cwd: Optional[Path] = None, timeout: int = 600) -> Tuple[int, str, str]:
        """
        Run a command and return exit code, stdout, stderr
        """
        if cwd is None:
            cwd = self.terraform_dir
        
        try:
            result = subprocess.run(
                command,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            return -1, "", str(e)
    
    def init(self) -> Dict:
        """Initialize Terraform"""
        exit_code, stdout, stderr = self._run_command(
            ["terraform", "init"],
            timeout=TIMEOUT_INIT
        )
        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr
        }
    
    def validate(self) -> Dict:
        """Validate Terraform configuration syntax"""
        # Note: terraform validate doesn't accept -var-file, it only checks syntax
        exit_code, stdout, stderr = self._run_command(
            ["terraform", "validate", "-no-color"],
            timeout=TIMEOUT_VALIDATE
        )
        
        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr
        }
    
    def plan(self) -> Dict:
        """Run Terraform plan"""
        if not self.tfvars_file.exists():
            return {
                "success": False,
                "error": "terraform.tfvars file not found"
            }
        
        # Run plan without -json for human-readable output
        exit_code, stdout, stderr = self._run_command(
            [
            "terraform", "plan",
                "-var-file", str(self.tfvars_file.absolute()),
            "-out", "tfplan",
                "-no-color"  # Remove color codes for cleaner output
            ],
            timeout=TIMEOUT_PLAN
        )
        
        # Combine stdout and stderr for complete output
        full_output = ""
        if stdout:
            full_output += stdout
        if stderr:
            if full_output:
                full_output += "\n\n--- STDERR ---\n"
            full_output += stderr
        
        return {
            "success": exit_code in [0, 2],  # 2 means changes detected
            "exit_code": exit_code,
            "stdout": stdout or "",
            "stderr": stderr or "",
            "full_output": full_output,
            "plan": {}
        }
    
    def apply(self) -> Dict:
        """Apply Terraform changes"""
        plan_file = self.terraform_dir / "tfplan"
        
        if not plan_file.exists():
            return {
                "success": False,
                "error": "Terraform plan file not found. Run plan first."
            }
        
        exit_code, stdout, stderr = self._run_command(
            [
            "terraform", "apply",
            "-auto-approve",
            "tfplan"
            ],
            timeout=TIMEOUT_APPLY
        )
        
        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr
        }
    
    def destroy(self) -> Dict:
        """Destroy Terraform infrastructure"""
        if not self.tfvars_file.exists():
            return {
                "success": False,
                "error": "terraform.tfvars file not found"
            }
        
        exit_code, stdout, stderr = self._run_command(
            [
            "terraform", "destroy",
                "-var-file", str(self.tfvars_file.absolute()),
            "-auto-approve"
            ],
            timeout=TIMEOUT_DESTROY  # 60 minutes for complex deployments
        )
        
        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr
        }
    
    def destroy_target(self, target: str) -> Dict:
        """Destroy a specific Terraform resource or module"""
        if not self.tfvars_file.exists():
            return {
                "success": False,
                "error": "terraform.tfvars file not found"
            }
        
        exit_code, stdout, stderr = self._run_command(
            [
            "terraform", "destroy",
                "-var-file", str(self.tfvars_file.absolute()),
            "-target", target,
            "-auto-approve"
            ],
            timeout=TIMEOUT_DESTROY  # 60 minutes for complex modules
        )
        
        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "target": target
        }
    
    def output(self) -> Dict:
        """Get Terraform outputs"""
        exit_code, stdout, stderr = self._run_command(
            [
            "terraform", "output",
            "-json"
            ],
            timeout=TIMEOUT_OUTPUT
        )
        
        outputs = {}
        if exit_code == 0:
            try:
                outputs = json.loads(stdout)
            except:
                pass
        
        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "outputs": outputs,
            "stderr": stderr
        }
    
    def show(self) -> Dict:
        """Show current Terraform state"""
        exit_code, stdout, stderr = self._run_command(
            [
            "terraform", "show",
            "-json"
            ],
            timeout=TIMEOUT_SHOW
        )
        
        state = {}
        if exit_code == 0:
            try:
                state = json.loads(stdout)
            except:
                pass
        
        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "state": state,
            "stderr": stderr
        }

