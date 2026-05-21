"""
Terraform Service
Wrapper for Terraform CLI operations with workspace support for multiple concurrent deployments
"""

import subprocess
import json
import os
import re
import shutil
import time as _time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# Timeout constants (in seconds)
TIMEOUT_INIT = 300          # 5 minutes for init
TIMEOUT_VALIDATE = 60       # 1 minute for validate
TIMEOUT_PLAN = 600          # 10 minutes for plan
TIMEOUT_APPLY = 3600        # 60 minutes for apply (combined deployments can be slow)
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
        self._active_process = None  # Track active subprocess for cancellation
        
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

    # Terraform output patterns for streaming parser
    _TF_CREATING = re.compile(r'^(\S+): Creating\.\.\.$')
    _TF_CREATED = re.compile(r'^(\S+): Creation complete after (\S+)')
    _TF_DESTROYING = re.compile(r'^(\S+): Destroying\.\.\.')
    _TF_DESTROYED = re.compile(r'^(\S+): Destruction complete after (\S+)')
    _TF_STILL = re.compile(r'^(\S+): Still (creating|destroying)\.\.\.')
    _TF_MODIFYING = re.compile(r'^(\S+): Modifying\.\.\.')
    _TF_MODIFIED = re.compile(r'^(\S+): Modifications complete after (\S+)')
    _TF_COMPLETE = re.compile(r'^Apply complete! Resources: (.+)$')
    _TF_DESTROY_COMPLETE = re.compile(r'^Destroy complete! Resources: (\d+) destroyed\.$')
    _TF_ERROR = re.compile(r'^\s*Error: (.+)$')

    def _run_command_streaming(
        self,
        command: List[str],
        on_event: Callable = None,
        cwd: Optional[Path] = None,
        timeout: int = 1800
    ) -> Tuple[int, str, str]:
        """
        Run a command with real-time stdout line parsing.

        Args:
            command: Command and arguments
            on_event: Callback(message, event_type) for each parsed terraform line.
                      event_type: "info", "success", "warning", "error"
            cwd: Working directory
            timeout: Timeout in seconds

        Returns:
            (exit_code, full_stdout, full_stderr)
        """
        if cwd is None:
            cwd = self.terraform_dir

        stdout_lines = []

        try:
            proc = subprocess.Popen(
                command,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line-buffered
                start_new_session=True  # Own process group for clean cancellation
            )
            self._active_process = proc

            start = _time.time()

            # Read stdout line-by-line in real time
            for line in proc.stdout:
                line = line.rstrip('\n')
                stdout_lines.append(line)

                if on_event and line.strip():
                    self._parse_terraform_line(line.strip(), on_event)

                if _time.time() - start > timeout:
                    proc.kill()
                    return -1, '\n'.join(stdout_lines), "Command timed out"

            # Wait for process to finish and collect stderr
            proc.wait()
            self._active_process = None
            stderr_text = proc.stderr.read() if proc.stderr else ""

            # Parse errors from stderr
            if on_event and stderr_text:
                for err_line in stderr_text.splitlines():
                    m = self._TF_ERROR.match(err_line.strip())
                    if m:
                        on_event(f"Error: {m.group(1)}", "error")

            return proc.returncode, '\n'.join(stdout_lines), stderr_text

        except Exception as e:
            return -1, '\n'.join(stdout_lines), str(e)

    def _parse_terraform_line(self, line: str, on_event: Callable):
        """Parse a single Terraform output line and fire callback if relevant."""
        # Skip noisy "Still creating/destroying..." lines
        if self._TF_STILL.match(line):
            return

        m = self._TF_CREATING.match(line)
        if m:
            on_event(f"Creating: {m.group(1)}", "info")
            return

        m = self._TF_CREATED.match(line)
        if m:
            on_event(f"Created: {m.group(1)} ({m.group(2)})", "success")
            return

        m = self._TF_DESTROYING.match(line)
        if m:
            on_event(f"Destroying: {m.group(1)}", "warning")
            return

        m = self._TF_DESTROYED.match(line)
        if m:
            on_event(f"Destroyed: {m.group(1)} ({m.group(2)})", "success")
            return

        m = self._TF_MODIFYING.match(line)
        if m:
            on_event(f"Modifying: {m.group(1)}", "info")
            return

        m = self._TF_MODIFIED.match(line)
        if m:
            on_event(f"Modified: {m.group(1)} ({m.group(2)})", "success")
            return

        m = self._TF_COMPLETE.match(line)
        if m:
            on_event(f"Apply complete! {m.group(1)}", "success")
            return

        m = self._TF_DESTROY_COMPLETE.match(line)
        if m:
            on_event(f"Destroy complete! {m.group(1)} destroyed", "success")
            return


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
    
    # =========================================================================
    # STREAMING VARIANTS (real-time resource-level events)
    # =========================================================================

    def apply_fresh_streaming(self, on_event: Callable = None) -> Dict:
        """Apply Terraform changes with real-time event streaming."""
        if not self.tfvars_file.exists():
            return {"success": False, "error": f"terraform.tfvars file not found: {self.tfvars_file}"}

        if self.workspace_name != "default":
            ws_result = self.ensure_workspace()
            if not ws_result["success"]:
                return ws_result

        exit_code, stdout, stderr = self._run_command_streaming(
            [
                "terraform", "apply",
                "-var-file", str(self.tfvars_file.absolute()),
                "-auto-approve",
                "-no-color"
            ],
            on_event=on_event,
            timeout=TIMEOUT_APPLY
        )

        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "workspace": self.workspace_name
        }

    def apply_target_streaming(self, target: str, on_event: Callable = None) -> Dict:
        """Targeted apply with real-time event streaming."""
        if not self.tfvars_file.exists():
            return {"success": False, "error": f"terraform.tfvars file not found: {self.tfvars_file}"}

        if self.workspace_name != "default":
            ws_result = self.ensure_workspace()
            if not ws_result["success"]:
                return ws_result

        exit_code, stdout, stderr = self._run_command_streaming(
            [
                "terraform", "apply",
                "-var-file", str(self.tfvars_file.absolute()),
                "-target", target,
                "-auto-approve",
                "-no-color"
            ],
            on_event=on_event,
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

    def destroy_streaming(self, on_event: Callable = None) -> Dict:
        """Destroy Terraform infrastructure with real-time event streaming."""
        if not self.tfvars_file.exists():
            return {"success": False, "error": f"terraform.tfvars file not found: {self.tfvars_file}"}

        if self.workspace_name != "default":
            ws_result = self.ensure_workspace()
            if not ws_result["success"]:
                return ws_result

        exit_code, stdout, stderr = self._run_command_streaming(
            [
                "terraform", "destroy",
                "-var-file", str(self.tfvars_file.absolute()),
                "-auto-approve",
                "-no-color"
            ],
            on_event=on_event,
            timeout=TIMEOUT_DESTROY
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
            except (json.JSONDecodeError, ValueError):
                pass
        
        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "outputs": outputs,
            "stderr": stderr,
            "workspace": self.workspace_name
        }
    
    def cancel(self) -> bool:
        """Kill the active Terraform subprocess and all its children (provider plugins)"""
        import signal
        proc = self._active_process
        if proc and proc.poll() is None:
            try:
                # Kill entire process group (Terraform + provider plugins)
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            # Fallback: kill the process directly
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass
            self._active_process = None
            return True
        return False

    def output_raw(self, name: str) -> str:
        """Get a single Terraform output value (including sensitive ones)"""
        if self.workspace_name != "default":
            self.ensure_workspace()
        exit_code, stdout, stderr = self._run_command(
            ["terraform", "output", "-raw", name],
            timeout=TIMEOUT_OUTPUT
        )
        return stdout.strip() if exit_code == 0 else ""

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
            except (json.JSONDecodeError, ValueError):
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
    # STATE-LEVEL OPERATIONS (read-only listing + targeted detachment)
    # =========================================================================
    #
    # These thin wrappers exist so the destroy-safety check + the detach-
    # foreign endpoint can pose terraform questions about a workspace
    # WITHOUT shelling out from route code directly. Centralizing the
    # subprocess args here keeps ``terraform state list/rm`` correctly
    # workspace-scoped (every other helper above does ``ensure_workspace``
    # first; these must too).

    def state_list(self) -> Dict:
        """List every resource address in the current workspace's state.

        Returns a dict shaped like the other helpers:
            { success, exit_code, stdout, stderr, addresses, workspace }
        ``addresses`` is a parsed list of non-empty lines from stdout for
        callers that don't want to re-parse. On failure ``addresses`` is
        an empty list; consult ``stderr`` for the underlying error.
        """
        if self.workspace_name != "default":
            ws_result = self.ensure_workspace()
            if not ws_result["success"]:
                return {
                    "success": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": ws_result.get("stderr", "Workspace selection failed"),
                    "addresses": [],
                    "workspace": self.workspace_name,
                }

        exit_code, stdout, stderr = self._run_command(
            ["terraform", "state", "list"],
            timeout=TIMEOUT_SHOW
        )

        addresses = []
        if exit_code == 0:
            addresses = [l.strip() for l in stdout.splitlines() if l.strip()]

        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "addresses": addresses,
            "workspace": self.workspace_name,
        }

    def state_rm(self, addr: str) -> Dict:
        """Detach a resource/module from THIS workspace's state.

        ``terraform state rm <addr>`` removes the address from state tracking
        but does NOT touch the underlying AWS resource. This is the safe
        recovery path when a foreign module was accidentally applied to a
        deployment workspace — the dashboard server (or shared lock table)
        keeps running, we just stop pretending this workspace owns it.

        Returns success/failure shape consistent with the other helpers.
        """
        if not addr or not isinstance(addr, str):
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "state_rm: address required",
                "workspace": self.workspace_name,
            }

        if self.workspace_name != "default":
            ws_result = self.ensure_workspace()
            if not ws_result["success"]:
                return {
                    "success": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": ws_result.get("stderr", "Workspace selection failed"),
                    "workspace": self.workspace_name,
                }

        exit_code, stdout, stderr = self._run_command(
            ["terraform", "state", "rm", addr],
            timeout=TIMEOUT_SHOW
        )

        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "address": addr,
            "workspace": self.workspace_name,
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
