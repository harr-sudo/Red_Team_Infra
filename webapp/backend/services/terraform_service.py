"""
Terraform Service
Wrapper for Terraform CLI operations
"""

import subprocess
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
            return -1, "", "Command timed out"
        except Exception as e:
            return -1, "", str(e)
    
    def init(self) -> Dict:
        """Initialize Terraform"""
        exit_code, stdout, stderr = self._run_command(["terraform", "init"])
        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr
        }
    
    def validate(self) -> Dict:
        """Validate Terraform configuration"""
        if not self.tfvars_file.exists():
            return {
                "success": False,
                "error": "terraform.tfvars file not found"
            }
        
        exit_code, stdout, stderr = self._run_command([
            "terraform", "validate",
            "-var-file", str(self.tfvars_file.relative_to(self.terraform_dir))
        ])
        
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
        
        exit_code, stdout, stderr = self._run_command([
            "terraform", "plan",
            "-var-file", str(self.tfvars_file.relative_to(self.terraform_dir)),
            "-out", "tfplan",
            "-json"
        ])
        
        # Try to parse JSON output
        plan_data = {}
        if exit_code == 0 or exit_code == 2:  # 2 means changes detected
            try:
                plan_data = json.loads(stdout)
            except:
                pass
        
        return {
            "success": exit_code in [0, 2],
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "plan": plan_data
        }
    
    def apply(self) -> Dict:
        """Apply Terraform changes"""
        plan_file = self.terraform_dir / "tfplan"
        
        if not plan_file.exists():
            return {
                "success": False,
                "error": "Terraform plan file not found. Run plan first."
            }
        
        exit_code, stdout, stderr = self._run_command([
            "terraform", "apply",
            "-auto-approve",
            "tfplan"
        ])
        
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
        
        exit_code, stdout, stderr = self._run_command([
            "terraform", "destroy",
            "-var-file", str(self.tfvars_file.relative_to(self.terraform_dir)),
            "-auto-approve"
        ])
        
        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr
        }
    
    def output(self) -> Dict:
        """Get Terraform outputs"""
        exit_code, stdout, stderr = self._run_command([
            "terraform", "output",
            "-json"
        ])
        
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
        exit_code, stdout, stderr = self._run_command([
            "terraform", "show",
            "-json"
        ])
        
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

