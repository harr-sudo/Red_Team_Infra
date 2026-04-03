"""
Setup Check Service
===================
Queries EC2 instances via SSM to read bootstrap status JSON files.
Returns per-host setup status with step-by-step detail.
"""

import json
import time
import uuid
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError


class SetupCheckService:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.cache_dir = project_root / "logs" / "setup_check_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._checks = {}  # check_id -> {status, results, ...}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_check(self, project: str, region: str) -> str:
        """Discover instances and send SSM commands to read status files.
        Returns a check_id for polling."""
        check_id = str(uuid.uuid4())[:8]

        with self._lock:
            self._checks[check_id] = {
                "status": "running",
                "project": project,
                "region": region,
                "started_at": datetime.utcnow().isoformat() + "Z",
                "results": [],
                "error": None,
            }

        thread = threading.Thread(
            target=self._execute_check,
            args=(check_id, project, region),
            daemon=True,
        )
        thread.start()
        return check_id

    def poll_check(self, check_id: str) -> Optional[dict]:
        """Return current state of an in-flight check."""
        with self._lock:
            return self._checks.get(check_id)

    def get_cached(self, project: str) -> Optional[dict]:
        """Return disk-cached results for a project."""
        cache_file = self.cache_dir / f"{project}.json"
        if cache_file.exists():
            try:
                return json.loads(cache_file.read_text())
            except Exception:
                return None
        return None

    # ------------------------------------------------------------------
    # Background execution
    # ------------------------------------------------------------------

    def _execute_check(self, check_id: str, project: str, region: str):
        """Background thread: discover instances, send SSM, poll results."""
        try:
            instances = self._discover_instances(project, region)
            if not instances:
                with self._lock:
                    self._checks[check_id]["status"] = "complete"
                    self._checks[check_id]["error"] = "No running instances found"
                return

            ssm = boto3.client("ssm", region_name=region)
            results = []

            # Send SSM commands to each instance
            pending = []
            for inst in instances:
                try:
                    cmd = self._send_ssm_command(ssm, inst)
                    if cmd:
                        pending.append({"instance": inst, "command_id": cmd})
                    else:
                        results.append(self._make_error_result(
                            inst, "ssm_send_failed", "Failed to send SSM command"
                        ))
                except Exception as e:
                    results.append(self._make_error_result(
                        inst, "ssm_error", str(e)
                    ))

            # Poll for results (up to 60 seconds)
            deadline = time.time() + 60
            while pending and time.time() < deadline:
                time.sleep(3)
                still_pending = []
                for item in pending:
                    result = self._check_ssm_result(
                        ssm, item["command_id"], item["instance"]
                    )
                    if result is None:
                        still_pending.append(item)  # Still in progress
                    else:
                        results.append(result)
                pending = still_pending

            # Anything still pending is a timeout
            for item in pending:
                results.append(self._make_error_result(
                    item["instance"], "ssm_timeout", "SSM command timed out after 60s"
                ))

            # Build final payload
            payload = {
                "status": "complete",
                "project": project,
                "region": region,
                "checked_at": datetime.utcnow().isoformat() + "Z",
                "hosts": results,
                "summary": self._build_summary(results),
            }

            # Cache to disk
            cache_file = self.cache_dir / f"{project}.json"
            cache_file.write_text(json.dumps(payload, indent=2))

            with self._lock:
                self._checks[check_id]["status"] = "complete"
                self._checks[check_id]["results"] = payload

        except NoCredentialsError:
            with self._lock:
                self._checks[check_id]["status"] = "complete"
                self._checks[check_id]["error"] = "AWS credentials not configured"
        except Exception as e:
            with self._lock:
                self._checks[check_id]["status"] = "complete"
                self._checks[check_id]["error"] = str(e)

    # ------------------------------------------------------------------
    # Instance discovery
    # ------------------------------------------------------------------

    def _discover_instances(self, project: str, region: str) -> list:
        """Find running EC2 instances tagged with this project."""
        ec2 = boto3.client("ec2", region_name=region)
        instances = []
        try:
            resp = ec2.describe_instances(
                Filters=[
                    {"Name": "tag:Project", "Values": [project]},
                    {"Name": "instance-state-name", "Values": ["running"]},
                ]
            )
            for reservation in resp.get("Reservations", []):
                for inst in reservation.get("Instances", []):
                    tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
                    platform = inst.get("Platform", "")  # "windows" or empty
                    # Determine role from tag or instance name
                    role = tags.get("Role", "").lower()
                    if not role or role == "unknown":
                        name_lower = tags.get("Name", "").lower()
                        if "teamserver" in name_lower or "c2-server" in name_lower:
                            role = "TeamServer"
                        elif "redirector" in name_lower:
                            role = "Redirector"
                        elif "bastion" in name_lower:
                            role = "Bastion"
                        elif "attackbox" in name_lower or "attack-box" in name_lower:
                            role = "AttackBox"
                        elif "jumpbox" in name_lower:
                            role = "Jumpbox"
                        elif "dc0" in name_lower:
                            role = "DC"
                        else:
                            role = "unknown"
                    instances.append({
                        "instance_id": inst["InstanceId"],
                        "name": tags.get("Name", "Unknown"),
                        "role": role,
                        "private_ip": inst.get("PrivateIpAddress", ""),
                        "platform": "windows" if platform == "windows" else "linux",
                    })
        except Exception as e:
            print(f"[SetupCheck] Instance discovery failed: {e}")
        return instances

    # ------------------------------------------------------------------
    # SSM command handling
    # ------------------------------------------------------------------

    def _send_ssm_command(self, ssm, instance: dict) -> Optional[str]:
        """Send SSM command to read the setup status file. Returns command_id."""
        if instance["platform"] == "windows":
            doc = "AWS-RunPowerShellScript"
            # Check for status file, then fall back to live service check
            cmd = [
                'if (Test-Path "C:\\ProgramData\\setup-status.json") {'
                '  Get-Content "C:\\ProgramData\\setup-status.json" -Raw'
                '} else {'
                '  $services = @();'
                '  if (Get-Service -Name sshd -ErrorAction SilentlyContinue | Where-Object {$_.Status -eq "Running"}) { $services += "sshd" };'
                '  if (Get-Service -Name TermService -ErrorAction SilentlyContinue | Where-Object {$_.Status -eq "Running"}) { $services += "rdp" };'
                '  if (Get-Service -Name WinRM -ErrorAction SilentlyContinue | Where-Object {$_.Status -eq "Running"}) { $services += "winrm" };'
                '  if (Test-Path "C:\\Tools") { $services += "tools_dir" };'
                '  if (Test-Path "C:\\Tools\\CobaltStrike") { $services += "cs_client" };'
                '  if (Test-Path "C:\\Tools\\PowerSploit") { $services += "powersploit" };'
                '  $json = @{ status = "live_check"; services = $services; uptime = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToString("o") } | ConvertTo-Json -Compress;'
                '  Write-Output $json'
                '}'
            ]
        else:
            doc = "AWS-RunShellScript"
            # Check status files first, then fall back to live service detection
            cmd = [
                'for f in /opt/cobaltstrike/bootstrap-status /opt/jumpbox/bootstrap-status /opt/setup-status.json; do '
                '  if [ -f "$f" ]; then '
                '    content=$(cat "$f"); '
                '    if echo "$content" | grep -q "^{"; then '
                '      echo "$content"; '
                '    else '
                '      echo "{"; '
                '      echo "$content" | while IFS="=" read -r key val; do '
                '        [ -n "$key" ] && echo "  \\"$key\\": \\"$val\\","; '
                '      done; '
                '      echo "  \\"status\\": \\"found\\","; '
                '      echo "  \\"status_file\\": \\"$f\\""; '
                '      echo "}"; '
                '    fi; '
                '    exit 0; '
                '  fi; '
                'done; '
                'svcs=""; '
                'systemctl is-active teamserver.service >/dev/null 2>&1 && svcs="${svcs}teamserver,"; '
                'systemctl is-active csrestapi.service >/dev/null 2>&1 && svcs="${svcs}csrestapi,"; '
                'systemctl is-active nginx.service >/dev/null 2>&1 && svcs="${svcs}nginx,"; '
                'systemctl is-active ssh.service >/dev/null 2>&1 && svcs="${svcs}sshd,"; '
                '[ -d /opt/cobaltstrike ] && svcs="${svcs}cs_installed,"; '
                '[ -d /opt/goad ] && svcs="${svcs}goad_installed,"; '
                'uptime_str=$(uptime -s 2>/dev/null || echo "unknown"); '
                'echo "{\\"status\\":\\"live_check\\",\\"services\\":\\"${svcs}\\",\\"uptime\\":\\"${uptime_str}\\"}"'
            ]

        try:
            resp = ssm.send_command(
                InstanceIds=[instance["instance_id"]],
                DocumentName=doc,
                Parameters={"commands": cmd},
                TimeoutSeconds=30,
            )
            return resp["Command"]["CommandId"]
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "InvalidInstanceId":
                return None  # SSM agent not ready
            raise

    def _check_ssm_result(self, ssm, command_id: str, instance: dict) -> Optional[dict]:
        """Check if SSM command completed. Returns result dict or None if still pending."""
        try:
            resp = ssm.get_command_invocation(
                CommandId=command_id,
                InstanceId=instance["instance_id"],
            )
        except ClientError as e:
            if "InvocationDoesNotExist" in str(e):
                return None  # Not ready yet
            return self._make_error_result(instance, "ssm_error", str(e))

        status = resp.get("Status", "")
        if status in ("Pending", "InProgress", "Delayed"):
            return None  # Still running

        if status == "Success":
            output = resp.get("StandardOutputContent", "").strip()
            return self._parse_status_output(instance, output)
        else:
            error_output = resp.get("StandardErrorContent", "")[:200]
            return self._make_error_result(
                instance, "ssm_failed", f"SSM status: {status}. {error_output}"
            )

    # ------------------------------------------------------------------
    # Result parsing
    # ------------------------------------------------------------------

    def _parse_status_output(self, instance: dict, output: str) -> dict:
        """Parse the JSON status file content from SSM output."""
        base = {
            "instance_id": instance["instance_id"],
            "name": instance["name"],
            "role": instance["role"],
            "private_ip": instance["private_ip"],
            "platform": instance["platform"],
        }
        try:
            data = json.loads(output)
            if data.get("status") == "no_status_file":
                base["check_status"] = "no_status_file"
                base["message"] = "Bootstrap not started yet"
                base["setup_data"] = None
            elif data.get("status") == "live_check":
                # No status file — fall back to live service detection
                services_raw = data.get("services", "")
                if isinstance(services_raw, list):
                    services = services_raw
                else:
                    services = [s for s in services_raw.split(",") if s]
                base["setup_data"] = data
                base["setup_data"]["detected_services"] = services
                if services:
                    base["check_status"] = "ok"
                    base["message"] = f"Services running: {', '.join(services)}"
                else:
                    base["check_status"] = "warning"
                    base["message"] = "Instance reachable but no known services detected"
            else:
                base["check_status"] = "ok"
                base["setup_data"] = data
                base["message"] = ""
        except (json.JSONDecodeError, ValueError):
            base["check_status"] = "parse_error"
            base["message"] = "Could not parse setup status JSON"
            base["setup_data"] = None
        return base

    def _make_error_result(self, instance: dict, error_type: str, message: str) -> dict:
        return {
            "instance_id": instance["instance_id"],
            "name": instance["name"],
            "role": instance["role"],
            "private_ip": instance["private_ip"],
            "platform": instance["platform"],
            "check_status": error_type,
            "message": message,
            "setup_data": None,
        }

    def _build_summary(self, results: list) -> dict:
        """Build summary counts from results."""
        total = len(results)
        healthy = 0
        partial = 0
        failed = 0
        pending = 0

        for r in results:
            cs = r.get("check_status", "")
            sd = r.get("setup_data")
            if cs == "ok":
                healthy += 1
            elif sd and sd.get("status") == "complete":
                healthy += 1
            elif sd and sd.get("status") == "partial":
                partial += 1
            elif sd and sd.get("status") == "running":
                pending += 1
            elif cs == "no_status_file":
                pending += 1
            elif cs == "warning":
                partial += 1
            else:
                failed += 1

        return {
            "total": total,
            "healthy": healthy,
            "partial": partial,
            "failed": failed,
            "pending": pending,
        }
