"""
Terraform Service
Wrapper for Terraform CLI operations with workspace support for multiple concurrent deployments
"""

import subprocess
import json
import os
import shutil
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
TIMEOUT_WORKSPACE = 30      # 30 seconds for workspace operations


class TerraformService:
    """Service for executing Terraform commands with workspace isolation"""
    
    def __init__(self, project_root: Path, workspace_name: Optional[str] = None):
        """
        Initialize TerraformService.
        
        Args:
            project_root: Root path of the project
            workspace_name: Optional workspace name for isolated deployments.
                           If None, uses 'default' workspace (backward compatible)
        """
        self.project_root = project_root
        self.terraform_dir = project_root / "terraform"
        self.config_dir = project_root / "configs"
        self.workspace_name = workspace_name or "default"
        
        # Each workspace has its own tfvars file
        if workspace_name and workspace_name != "default":
            self.tfvars_file = self.config_dir / f"{workspace_name}.tfvars"
        else:
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
    
    # =========================================================================
    # WORKSPACE MANAGEMENT
    # =========================================================================
    
    def workspace_list(self) -> Dict:
        """List all Terraform workspaces"""
        exit_code, stdout, stderr = self._run_command(
            ["terraform", "workspace", "list"],
            timeout=TIMEOUT_WORKSPACE
        )
        
        workspaces = []
        current = "default"
        
        if exit_code == 0:
            for line in stdout.strip().split('\n'):
                line = line.strip()
                if line.startswith('*'):
                    # Current workspace is marked with *
                    ws_name = line[1:].strip()
                    current = ws_name
                    workspaces.append(ws_name)
                elif line:
                    workspaces.append(line)
        
        return {
            "success": exit_code == 0,
            "workspaces": workspaces,
            "current": current,
            "stderr": stderr
        }
    
    def workspace_new(self, name: str) -> Dict:
        """Create a new Terraform workspace"""
        # Validate workspace name
        if not name or not name.replace('_', '').replace('-', '').isalnum():
            return {
                "success": False,
                "error": "Invalid workspace name. Use only alphanumeric characters, underscores, and hyphens."
            }
        
        exit_code, stdout, stderr = self._run_command(
            ["terraform", "workspace", "new", name],
            timeout=TIMEOUT_WORKSPACE
        )
        
        if exit_code == 0:
            self.workspace_name = name
            # Create workspace-specific tfvars file
            self.tfvars_file = self.config_dir / f"{name}.tfvars"
        
        return {
            "success": exit_code == 0,
            "workspace": name,
            "stdout": stdout,
            "stderr": stderr
        }
    
    def workspace_select(self, name: str) -> Dict:
        """Select/switch to a Terraform workspace"""
        exit_code, stdout, stderr = self._run_command(
            ["terraform", "workspace", "select", name],
            timeout=TIMEOUT_WORKSPACE
        )
        
        if exit_code == 0:
            self.workspace_name = name
            if name != "default":
                self.tfvars_file = self.config_dir / f"{name}.tfvars"
            else:
                self.tfvars_file = self.config_dir / "terraform.tfvars"
        
        return {
            "success": exit_code == 0,
            "workspace": name,
            "stdout": stdout,
            "stderr": stderr
        }
    
    def workspace_delete(self, name: str) -> Dict:
        """Delete a Terraform workspace"""
        if name == "default":
            return {
                "success": False,
                "error": "Cannot delete the default workspace"
            }
        
        # First switch to default if we're deleting current workspace
        if self.workspace_name == name:
            self.workspace_select("default")
        
        exit_code, stdout, stderr = self._run_command(
            ["terraform", "workspace", "delete", "-force", name],
            timeout=TIMEOUT_WORKSPACE
        )
        
        # Also delete the workspace-specific tfvars file
        if exit_code == 0:
            tfvars_file = self.config_dir / f"{name}.tfvars"
            if tfvars_file.exists():
                tfvars_file.unlink()
        
        return {
            "success": exit_code == 0,
            "workspace": name,
            "stdout": stdout,
            "stderr": stderr
        }
    
    def workspace_show(self) -> Dict:
        """Show current workspace"""
        exit_code, stdout, stderr = self._run_command(
            ["terraform", "workspace", "show"],
            timeout=TIMEOUT_WORKSPACE
        )
        
        return {
            "success": exit_code == 0,
            "workspace": stdout.strip() if exit_code == 0 else None,
            "stderr": stderr
        }
    
    def ensure_workspace(self) -> Dict:
        """Ensure the configured workspace exists and is selected"""
        if self.workspace_name == "default":
            return {"success": True, "workspace": "default"}
        
        # Check if workspace exists
        list_result = self.workspace_list()
        if not list_result["success"]:
            return list_result
        
        if self.workspace_name in list_result["workspaces"]:
            # Workspace exists, select it
            return self.workspace_select(self.workspace_name)
        else:
            # Create new workspace
            return self.workspace_new(self.workspace_name)
    
    # =========================================================================
    # CORE TERRAFORM OPERATIONS
    # =========================================================================
    
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
                "error": f"terraform.tfvars file not found: {self.tfvars_file}"
            }
        
        # Ensure correct workspace is selected
        if self.workspace_name != "default":
            ws_result = self.ensure_workspace()
            if not ws_result["success"]:
                return ws_result
        
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
            "plan": {},
            "workspace": self.workspace_name
        }
    
    def apply(self) -> Dict:
        """Apply Terraform changes"""
        plan_file = self.terraform_dir / "tfplan"
        
        if not plan_file.exists():
            return {
                "success": False,
                "error": "Terraform plan file not found. Run plan first."
            }
        
        # Ensure correct workspace is selected
        if self.workspace_name != "default":
            ws_result = self.ensure_workspace()
            if not ws_result["success"]:
                return ws_result
        
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
            "stderr": stderr,
            "workspace": self.workspace_name
        }
    
    def destroy(self) -> Dict:
        """Destroy Terraform infrastructure"""
        if not self.tfvars_file.exists():
            return {
                "success": False,
                "error": f"terraform.tfvars file not found: {self.tfvars_file}"
            }
        
        # Ensure correct workspace is selected
        if self.workspace_name != "default":
            ws_result = self.ensure_workspace()
            if not ws_result["success"]:
                return ws_result
        
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
            "stderr": stderr,
            "workspace": self.workspace_name
        }
    
    def destroy_target(self, target: str) -> Dict:
        """Destroy a specific Terraform resource or module"""
        if not self.tfvars_file.exists():
            return {
                "success": False,
                "error": f"terraform.tfvars file not found: {self.tfvars_file}"
            }
        
        # Ensure correct workspace is selected
        if self.workspace_name != "default":
            ws_result = self.ensure_workspace()
            if not ws_result["success"]:
                return ws_result
        
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
            "target": target,
            "workspace": self.workspace_name
        }
    
    def apply_target(self, target: str) -> Dict:
        """Apply a specific Terraform resource or module (targeted apply)"""
        if not self.tfvars_file.exists():
            return {
                "success": False,
                "error": f"terraform.tfvars file not found: {self.tfvars_file}"
            }
        
        # Ensure correct workspace is selected
        if self.workspace_name != "default":
            ws_result = self.ensure_workspace()
            if not ws_result["success"]:
                return ws_result
        
        exit_code, stdout, stderr = self._run_command(
            [
                "terraform", "apply",
                "-var-file", str(self.tfvars_file.absolute()),
                "-target", target,
                "-auto-approve"
            ],
            timeout=TIMEOUT_APPLY
        )
        
        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "target": target,
            "workspace": self.workspace_name
        }
    
    def apply_fresh(self) -> Dict:
        """Apply Terraform changes without using a saved plan file.
        
        This is useful when the state has changed since the plan was created
        (e.g., after a targeted apply). It runs a fresh plan and apply in one step.
        """
        if not self.tfvars_file.exists():
            return {
                "success": False,
                "error": f"terraform.tfvars file not found: {self.tfvars_file}"
            }
        
        # Ensure correct workspace is selected
        if self.workspace_name != "default":
            ws_result = self.ensure_workspace()
            if not ws_result["success"]:
                return ws_result
        
        exit_code, stdout, stderr = self._run_command(
            [
                "terraform", "apply",
                "-var-file", str(self.tfvars_file.absolute()),
                "-auto-approve"
            ],
            timeout=TIMEOUT_APPLY
        )
        
        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "workspace": self.workspace_name
        }
    
    def output(self) -> Dict:
        """Get Terraform outputs"""
        # Ensure correct workspace is selected
        if self.workspace_name != "default":
            ws_result = self.ensure_workspace()
            if not ws_result["success"]:
                return {"success": False, "outputs": {}, "stderr": ws_result.get("stderr", "")}
        
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
            "stderr": stderr,
            "workspace": self.workspace_name
        }
    
    def show(self) -> Dict:
        """Show current Terraform state"""
        # Ensure correct workspace is selected
        if self.workspace_name != "default":
            ws_result = self.ensure_workspace()
            if not ws_result["success"]:
                return {"success": False, "state": {}, "stderr": ws_result.get("stderr", "")}
        
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
            "stderr": stderr,
            "workspace": self.workspace_name
        }
    
    def refresh(self) -> Dict:
        """Refresh Terraform state to match actual infrastructure"""
        if not self.tfvars_file.exists():
            return {
                "success": False,
                "error": f"terraform.tfvars file not found: {self.tfvars_file}"
            }
        
        # Ensure correct workspace is selected
        if self.workspace_name != "default":
            ws_result = self.ensure_workspace()
            if not ws_result["success"]:
                return ws_result
        
        exit_code, stdout, stderr = self._run_command(
            [
                "terraform", "refresh",
                "-var-file", str(self.tfvars_file.absolute())
            ],
            timeout=TIMEOUT_PLAN  # Use plan timeout
        )
        
        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "workspace": self.workspace_name
        }
    
    def force_destroy(self) -> Dict:
        """Force destroy infrastructure without refreshing state first"""
        if not self.tfvars_file.exists():
            return {
                "success": False,
                "error": f"terraform.tfvars file not found: {self.tfvars_file}"
            }
        
        # Ensure correct workspace is selected
        if self.workspace_name != "default":
            ws_result = self.ensure_workspace()
            if not ws_result["success"]:
                return ws_result
        
        exit_code, stdout, stderr = self._run_command(
            [
                "terraform", "destroy",
                "-var-file", str(self.tfvars_file.absolute()),
                "-auto-approve",
                "-refresh=false"  # Skip refresh, use current state
            ],
            timeout=TIMEOUT_DESTROY
        )
        
        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "workspace": self.workspace_name
        }
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def get_state_file_path(self) -> Path:
        """Get the path to the state file for current workspace"""
        if self.workspace_name == "default":
            return self.terraform_dir / "terraform.tfstate"
        else:
            return self.terraform_dir / "terraform.tfstate.d" / self.workspace_name / "terraform.tfstate"
    
    def has_state(self) -> bool:
        """Check if state file exists for current workspace"""
        return self.get_state_file_path().exists()
    
    def get_workspace_config(self) -> Dict:
        """Get configuration for current workspace"""
        if not self.tfvars_file.exists():
            return {}
        
        # Parse tfvars file
        config = {}
        try:
            with open(self.tfvars_file, 'r') as f:
                content = f.read()
                # Simple parsing - for complex cases use HCL parser
                for line in content.split('\n'):
                    line = line.strip()
                    if '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"')
                        config[key] = value
        except Exception:
            pass
        
        return config
    
    def copy_config_to_workspace(self, source_config: Path) -> bool:
        """Copy a configuration file to this workspace's tfvars"""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_config, self.tfvars_file)
            return True
        except Exception:
            return False


# Factory function for creating workspace-specific services
def get_terraform_service(project_root: Path, workspace_name: Optional[str] = None) -> TerraformService:
    """
    Factory function to get a TerraformService instance.
    
    Args:
        project_root: Root path of the project
        workspace_name: Optional workspace name. If None, uses default workspace.
    
    Returns:
        TerraformService instance configured for the workspace
    """
    return TerraformService(project_root, workspace_name)
