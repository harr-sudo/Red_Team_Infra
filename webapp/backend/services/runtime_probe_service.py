"""
Runtime Probe Service (Mission Control)
=======================================
Layer 2 + Layer 3 of the Mission Control monitoring plan.

Where the existing SetupCheckService answers "did bootstrap run?", this service
answers "is the infrastructure actually *healthy right now*?" by running active,
external synthetic probes from the Dashboard Server — the same vantage point the
operator tunnels through. It deliberately probes the sensitive data-plane
(redirectors, C2 team servers) from the OUTSIDE and keeps NO logs on those hosts,
matching red-team OPSEC (nginx access_log is off by design).

Per-host runtime checks:
  - Redirector  : TLS reachable on 443, live cert days-to-expiry, decoy site
                  HTTP 200 (+ optional body marker), HTTP 80 reachable, and the
                  end-to-end PROXY PATH (the C2 callback URI actually forwards
                  through to the team server instead of being served the decoy).
  - C2 server   : TCP reach to the CS management port over VPC peering
                  (only reachable from the Dashboard Server in prod; on a dev
                  laptop with no peering this reports "unreachable", which is
                  expected and labelled as such).
  - Domain      : DNS resolves + HTTPS 200 (if a primary_domain_name is set).
  - VPC peering : the dashboard<->deployment peering connection is "active"
                  (the backbone every SSM check silently depends on).

Layer 3: a single daemon scheduler thread re-runs the probes for every known
project on an interval and writes a heartbeat file each loop. The heartbeat is a
dead-man's switch — a stalled scheduler shows up as a stale heartbeat instead of
silently serving old "green" results.

All AWS calls used here (ec2:DescribeInstances, ec2:DescribeVpcPeeringConnections)
are free; the HTTP/TLS/TCP probes cost nothing.
"""

import concurrent.futures
import json
import os
import socket
import ssl
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

try:
    import requests
except Exception:  # pragma: no cover - requests is a declared dependency
    requests = None

# Optional: richer cert parsing for self-signed / IP-only endpoints. Falls back
# gracefully to the verified-handshake path when cryptography is absent.
try:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    _HAVE_CRYPTO = True
except Exception:
    _HAVE_CRYPTO = False

# Status vocabulary (worst-wins when rolled up).
OK = "ok"
WARN = "warn"
CRIT = "crit"
UNKNOWN = "unknown"
# NA = "not applicable from here" — a check that genuinely can't run from the
# current vantage (e.g. the C2 private mgmt port when probing from a dev laptop
# with no VPC peering) or a role with no runtime probe. NA is muted and is
# EXCLUDED from the rollup (severity 0) so a healthy fleet never reads degraded
# just because we're running off-cluster. In production (on the Dashboard
# Server, which has peering) these checks actually run and report ok/crit.
NA = "na"
_SEVERITY = {OK: 0, NA: 0, UNKNOWN: 1, WARN: 2, CRIT: 3}

# Cert-expiry thresholds (days).
CERT_WARN_DAYS = 14
CERT_CRIT_DAYS = 3

_PROBE_TIMEOUT = 6  # seconds per network probe

# Overall wall-clock budget for one project's probe run. With concurrency the run
# finishes in ~the slowest single target; any target still going past this is
# reported `unknown`/"timed out" rather than hanging the whole run. Generous
# enough to cover an SSM metrics round-trip (send + bounded poll) on a slow host.
_OVERALL_PROBE_DEADLINE = 45
# Bounded worker pool — sized so even the largest deployment (combined-full-full:
# 3 C2 + 2 redirectors + attack box + a full GOAD lab, plus the 2 fabric probes)
# fans out ALL AT ONCE with nothing queued. Probes are IO-bound (sockets / SSM
# waits), so threads are cheap; the cap is just a runaway backstop. Keeping every
# probe running concurrently is what stops a slow host from starving others of
# their turn within the wall-clock deadline.
_PROBE_MAX_WORKERS = 32


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _worst(statuses) -> str:
    """Roll a list of statuses up to the most severe one."""
    worst = OK
    for s in statuses:
        if _SEVERITY.get(s, 1) > _SEVERITY.get(worst, 0):
            worst = s
    return worst


class RuntimeProbeService:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.cache_dir = project_root / "logs" / "health_probe_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.heartbeat_file = self.cache_dir / "_scheduler_heartbeat.json"
        self._runs = {}            # run_id -> {status, result, error}
        self._lock = threading.Lock()
        self._scheduler_thread = None
        self._scheduler_stop = threading.Event()
        self._scheduler_interval = 3600  # seconds; configurable via start_scheduler
        # Phase 4 — shared time-series/events store (history, uptime, incidents,
        # heartbeats). Routes read it via _service._history.
        from webapp.backend.services.health_history_service import HealthHistoryService
        self._history = HealthHistoryService(project_root)

    # ------------------------------------------------------------------
    # Public API — on-demand run + cache read
    # ------------------------------------------------------------------

    def start_run(self, project: str, region: str, demo_state: Optional[str] = None) -> str:
        """Kick off a probe run for one project in a background thread."""
        run_id = str(uuid.uuid4())[:8]
        with self._lock:
            self._runs[run_id] = {"status": "running", "result": None, "error": None}
        threading.Thread(
            target=self._run_and_store,
            args=(run_id, project, region, demo_state),
            daemon=True,
        ).start()
        return run_id

    def poll_run(self, run_id: str) -> Optional[dict]:
        with self._lock:
            return self._runs.get(run_id)

    def get_cached(self, project: str) -> Optional[dict]:
        # Demo deployment: serve synthetic payload for the sticky demo state
        # (no AWS, no cache file) — same shape a real probe produces.
        if self._is_demo(project):
            from webapp.backend.services import demo_data_service
            return demo_data_service.probe_payload()
        cache_file = self.cache_dir / f"{project}.json"
        if cache_file.exists():
            try:
                return json.loads(cache_file.read_text())
            except Exception:
                return None
        return None

    def _is_demo(self, project: str) -> bool:
        try:
            from webapp.backend.services import demo_data_service
            return demo_data_service.is_demo_project(project)
        except Exception:
            return False

    def _run_and_store(self, run_id: str, project: str, region: str,
                       demo_state: Optional[str] = None):
        try:
            payload = self.probe_project(project, region, demo_state)
            with self._lock:
                self._runs[run_id] = {"status": "complete", "result": payload, "error": None}
        except NoCredentialsError:
            with self._lock:
                self._runs[run_id] = {"status": "complete", "result": None,
                                      "error": "AWS credentials not configured"}
        except Exception as e:
            with self._lock:
                self._runs[run_id] = {"status": "complete", "result": None, "error": str(e)}

    # ------------------------------------------------------------------
    # Core: probe a single project end-to-end
    # ------------------------------------------------------------------

    def probe_project(self, project: str, region: str,
                      demo_state: Optional[str] = None) -> dict:
        """Discover targets and run every runtime probe. Caches + returns the payload."""
        # Demo deployment short-circuit: no AWS, return the (optionally
        # state-switched) synthetic payload through the same return shape.
        if self._is_demo(project):
            from webapp.backend.services import demo_data_service
            if demo_state:
                demo_data_service.set_probe_state(demo_state)
            payload = demo_data_service.probe_payload()
            try:
                self._history.record_run(project, payload)
            except Exception:
                pass
            return payload
        # Resolve domain/theme/port from THIS deployment's own config + state
        # outputs (NOT the global tfvars) so each card reflects its real domain.
        cfg = self._deployment_config(project)
        domain = (cfg.get("primary_domain_name") or "").strip()
        decoy_theme = (cfg.get("decoy_theme") or "").strip()
        c2_port = int(cfg.get("c2_server_port") or 50050)
        c2_listener = int(cfg.get("c2_listener_port") or 443)
        # The malleable-profile GET URI a beacon calls home on. Without it we
        # can't verify the end-to-end proxy path, so that check reports N/A.
        c2_uri = (cfg.get("c2_callback_uri") or cfg.get("c2_get_uri") or "").strip()

        instances = self._discover_instances(project, region)
        # Redirector public IPs are known from discovery (not the probe result),
        # so the domain A-record check can run concurrently with everything else.
        redirector_ips = [i.get("public_ip") for i in instances
                          if i["role"].lower() == "redirector" and i.get("public_ip")]

        def _probe_one_host(inst):
            role = inst["role"].lower()
            if role == "redirector":
                rec = self._probe_redirector(inst, domain, decoy_theme, c2_uri)
            elif role == "teamserver":
                rec = self._probe_teamserver(inst, c2_port, c2_listener)
            else:
                # Attack box / jumpbox / lab hosts have no role-specific data-plane
                # probe — but we still collect host resource metrics (disk/mem/CPU)
                # so they aren't a pure N/A blind spot. Off-vantage those metrics
                # are N/A and the host rolls up N/A.
                rec = self._host_record(inst, NA, "")
            rec["checks"].extend(self._metrics_check(inst, region))
            rec["status"] = self._rollup_checks(rec["checks"], rec["status"])
            return rec

        # Run every host probe + the fabric probes CONCURRENTLY with an overall
        # wall-clock deadline. Sequential probing made an unreachable fleet stack
        # 6s timeouts per check and look "stuck"; parallel collapses the run to
        # roughly the slowest single target. A target that blows the deadline is
        # reported as `unknown` ("probe timed out") — never a fake "down".
        hosts, fabric = self._run_probes_parallel(
            instances, _probe_one_host, project, region, domain, redirector_ips)

        # Roll up over checks that ACTUALLY RAN (exclude na). If nothing real
        # was verified (e.g. a lab with no public surface, probed off-vantage),
        # the deployment is UNKNOWN — not falsely "healthy".
        ran = [s for s in ([h["status"] for h in hosts] + [f["status"] for f in fabric])
               if s != NA]
        rollup = _worst(ran) if ran else UNKNOWN

        payload = {
            "project": project,
            "region": region,
            "checked_at": _now_iso(),
            "domain": domain,
            "vpc_cidr": cfg.get("vpc_cidr") or self._derive_vpc_cidr(hosts),
            "status": rollup,
            "hosts": hosts,
            "fabric": fabric,
            "summary": self._summarize(hosts, fabric),
        }
        try:
            (self.cache_dir / f"{project}.json").write_text(json.dumps(payload, indent=2))
        except Exception:
            pass
        try:
            self._history.record_run(project, payload)
        except Exception:
            pass
        return payload

    def _run_probes_parallel(self, instances, probe_one_host, project, region,
                             domain, redirector_ips):
        """Fan every independent probe (each host + peering + domain) out across a
        bounded thread pool under one overall deadline, then collect results in a
        stable order (hosts as discovered, fabric: peering then domain). A probe
        that exceeds the deadline or raises becomes a target-shaped `unknown`
        record ("probe timed out" / the error) — the run never hangs and a slow
        vantage never masquerades as a healthy or down fleet."""
        # label -> (kind, callable). kind drives how a timeout/failure is shaped.
        tasks = []
        for inst in instances:
            tasks.append(("host", inst, lambda i=inst: probe_one_host(i)))
        tasks.append(("peering", None, lambda: self._probe_peering(project, region)))
        if domain:
            tasks.append(("domain", None, lambda: self._probe_domain(domain, redirector_ips)))

        results = {}
        pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=min(_PROBE_MAX_WORKERS, max(1, len(tasks))))
        try:
            futures = {pool.submit(fn): (idx, kind, ref)
                       for idx, (kind, ref, fn) in enumerate(tasks)}
            # ONE wall-clock budget for the whole batch, collected order-INDEPENDENTLY:
            # whoever finishes within the deadline gets their real result; only the
            # genuinely-unfinished become `unknown`. (Waiting on futures in submission
            # order would let a slow early host burn the budget and wrongly time out
            # fast hosts queued behind it — the large-fleet mislabel bug.)
            done, not_done = concurrent.futures.wait(
                futures, timeout=_OVERALL_PROBE_DEADLINE)
            for fut in done:
                idx, kind, ref = futures[fut]
                try:
                    results[idx] = fut.result()
                except Exception as e:
                    results[idx] = self._error_record(kind, ref, str(e))
            for fut in not_done:
                idx, kind, ref = futures[fut]
                results[idx] = self._timeout_record(kind, ref)
        finally:
            # Don't block shutdown on a straggler that blew the deadline.
            pool.shutdown(wait=False, cancel_futures=True)

        hosts, fabric = [], []
        for idx, (kind, ref, _fn) in enumerate(tasks):
            rec = results.get(idx)
            if rec is None:
                continue
            (hosts if kind == "host" else fabric).append(rec)
        return hosts, fabric

    def _timeout_record(self, kind, ref):
        """Shape a deadline-exceeded probe as `unknown` (not down)."""
        detail = f"probe timed out (> {_OVERALL_PROBE_DEADLINE}s)"
        if kind == "host":
            rec = self._host_record(ref, UNKNOWN, detail)
            rec["checks"] = [{"id": "probe", "status": UNKNOWN, "detail": detail}]
            return rec
        label = "VPC peering" if kind == "peering" else "domain"
        return {"id": kind, "label": label, "kind": "fabric", "status": UNKNOWN,
                "checks": [{"id": f"{kind}_probe", "status": UNKNOWN, "detail": detail}]}

    def _error_record(self, kind, ref, msg):
        """Shape a probe that raised as `unknown` with the error detail."""
        detail = f"probe error: {msg}"
        if kind == "host":
            rec = self._host_record(ref, UNKNOWN, detail)
            rec["checks"] = [{"id": "probe", "status": UNKNOWN, "detail": detail}]
            return rec
        label = "VPC peering" if kind == "peering" else "domain"
        return {"id": kind, "label": label, "kind": "fabric", "status": UNKNOWN,
                "checks": [{"id": f"{kind}_probe", "status": UNKNOWN, "detail": detail}]}

    # ------------------------------------------------------------------
    # Per-role probes
    # ------------------------------------------------------------------

    def _probe_redirector(self, inst: dict, domain: str, decoy_theme: str,
                          c2_uri: str = "") -> dict:
        ip = inst.get("public_ip") or inst.get("private_ip")
        checks = []

        # The decoy + cert are best probed via the domain when we have one (so
        # TLS verification + SNI behave), else fall back to the raw EIP.
        https_host = domain or ip
        tcp443 = self._tcp_reachable(ip, 443) if ip else False
        checks.append(self._check("tls_reachable", tcp443,
                      "443 reachable" if tcp443 else "443 not reachable"))

        # Live cert expiry.
        checks.append(self._cert_check(https_host, ip))

        # Decoy site responds 200 (and looks like the configured theme). Time it
        # for the response-time trend.
        _t0 = time.time()
        checks.append(self._decoy_check(https_host, ip, decoy_theme))
        response_ms = int((time.time() - _t0) * 1000)

        # End-to-end PROXY PATH: the C2 callback URI must forward through to the
        # team server, not be swallowed by the decoy. This is the check that
        # catches a broken proxy_pass rule (cert/TLS/decoy all green while every
        # beacon silently dies).
        checks.append(self._proxy_path_check(https_host, ip, c2_uri, decoy_theme))

        # Plain HTTP listener up (redirector typically 301s 80->443).
        http80 = self._tcp_reachable(ip, 80) if ip else False
        checks.append(self._check("http_reachable", http80,
                      "80 reachable" if http80 else "80 not reachable", soft=True))

        status = _worst([c["status"] for c in checks])
        rec = self._host_record(inst, status, "")
        rec["checks"] = checks
        rec["endpoint"] = https_host
        rec["response_ms"] = response_ms
        return rec

    def _proxy_path_check(self, host: str, ip: str, c2_uri: str,
                          decoy_theme: str) -> dict:
        """Verify the redirector actually FORWARDS the C2 callback URI to the
        team server (end-to-end), instead of serving the decoy for every path.
        A redirector whose proxy_pass rule is broken still passes TLS + cert +
        decoy while black-holing every beacon — this is the check that catches
        it. N/A until a c2_callback_uri is configured (we can't guess the
        malleable profile's URI)."""
        if not c2_uri:
            return {"id": "proxy_path", "status": NA,
                    "detail": "set c2_callback_uri to verify end-to-end C2 forwarding"}
        if requests is None:
            return {"id": "proxy_path", "status": UNKNOWN, "detail": "requests unavailable"}
        if not host:
            return {"id": "proxy_path", "status": NA, "detail": "no endpoint to probe"}
        path = c2_uri if c2_uri.startswith("/") else "/" + c2_uri
        url = f"https://{host}{path}"
        try:
            r = requests.get(url, timeout=_PROBE_TIMEOUT, allow_redirects=False,
                             verify=False, headers={"User-Agent": "Mozilla/5.0"})
        except Exception as e:
            return {"id": "proxy_path", "status": CRIT, "detail": f"C2 path unreachable: {e}"}
        # 5xx on the C2 path = redirector up but the upstream team server is
        # down/unreachable through the proxy.
        if r.status_code in (502, 503, 504):
            return {"id": "proxy_path", "status": CRIT,
                    "detail": f"HTTP {r.status_code} on C2 path — upstream team server unreachable"}
        body = (r.text or "")[:20000].lower()
        # Same content as the decoy/default page on the C2 path → the proxy rule
        # is NOT forwarding; beacon callbacks are being served the decoy.
        if "welcome to nginx" in body or (decoy_theme and decoy_theme.lower() in body):
            return {"id": "proxy_path", "status": CRIT,
                    "detail": "C2 path served the decoy page — proxy rule not forwarding to team server"}
        return {"id": "proxy_path", "status": OK,
                "detail": f"C2 callback path forwarded to team server (HTTP {r.status_code})"}

    def _rollup_checks(self, checks: list, fallback: str) -> str:
        """Worst status over checks that actually RAN (NA excluded). If every
        check is NA, keep the caller's fallback rather than collapsing to OK."""
        ran = [c["status"] for c in checks if c.get("status") != NA]
        return _worst(ran) if ran else fallback

    def _probe_teamserver(self, inst: dict, c2_port: int, listener_port: int = 443) -> dict:
        # The team server lives in a private subnet, reachable only over VPC
        # peering. In PRODUCTION the dashboard runs in AWS with that peering, so
        # these checks actually run. In DEV (laptop, no peering) they are
        # genuinely not-applicable — N/A, muted, excluded from the rollup.
        # We track BOTH ports: the CS management port (operator/client) AND the
        # beacon LISTENER port (what beacons actually call into — a listener
        # being down means beacons silently die even if mgmt is up).
        ip = inst.get("private_ip")
        if not self._is_dashboard_vantage():
            checks = [
                {"id": "c2_mgmt_port", "status": NA,
                 "detail": f"n/a from here — {c2_port} checked on the Dashboard Server (over peering)"},
                {"id": "c2_listener_port", "status": NA,
                 "detail": f"n/a from here — beacon listener {listener_port} checked on the Dashboard Server"},
            ]
            rec = self._host_record(inst, NA, "")
            rec["checks"] = checks
            return rec
        checks = []
        # Management port.
        if self._tcp_reachable(ip, c2_port) if ip else False:
            checks.append(self._check("c2_mgmt_port", True, f"{c2_port} reachable over peering"))
        else:
            checks.append({"id": "c2_mgmt_port", "status": CRIT,
                           "detail": f"{c2_port} unreachable — operators can't connect"})
        # Beacon listener port — the one beacons call home on.
        if self._tcp_reachable(ip, listener_port) if ip else False:
            checks.append(self._check("c2_listener_port", True, f"listener {listener_port} up"))
        else:
            checks.append({"id": "c2_listener_port", "status": CRIT,
                           "detail": f"listener {listener_port} down — beacons cannot check in"})
        status = _worst([c["status"] for c in checks])
        rec = self._host_record(inst, status, "")
        rec["checks"] = checks
        return rec

    # Vantage detection — are we running on the AWS Dashboard Server (prod,
    # has peering) or a dev laptop? Cached once. Explicit env override wins;
    # otherwise best-effort EC2 IMDS probe (fast timeout).
    _vantage_cache = None

    def _is_dashboard_vantage(self) -> bool:
        if self._vantage_cache is not None:
            return self._vantage_cache
        env = os.environ.get("MISSION_CONTROL_VANTAGE", "").strip().lower()
        if env in ("dashboard", "prod", "aws", "server"):
            self._vantage_cache = True
            return True
        if env in ("dev", "laptop", "local"):
            self._vantage_cache = False
            return False
        val = False
        if requests is not None:
            try:
                r = requests.put(
                    "http://169.254.169.254/latest/api/token",
                    headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
                    timeout=0.4)
                val = r.status_code == 200
            except Exception:
                val = False
        self._vantage_cache = val
        return val

    # ------------------------------------------------------------------
    # Host resource metrics (disk / memory / CPU) via SSM — Linux AND Windows.
    # A long-running C2/redirector/attack box that fills its disk or pegs CPU
    # fails silently otherwise. Off-vantage (dev laptop, no SSM reach) these are
    # genuinely N/A and excluded from the rollup. Windows uses PowerShell + CIM
    # (multicore-correct, locale-safe); Linux uses df/free/loadavg.
    # ------------------------------------------------------------------

    # Thresholds (percent; load-per-vCPU for the Linux load average).
    _DISK_WARN, _DISK_CRIT = 80, 92
    _MEM_WARN, _MEM_CRIT = 85, 95
    _LOAD_WARN, _LOAD_CRIT = 1.5, 3.0
    _CPU_WARN, _CPU_CRIT = 90, 98  # instantaneous CPU% (Windows)

    def _metrics_check(self, inst: dict, region: str) -> list:
        """Disk/mem/CPU for any host (Linux or Windows). Vantage-gated: off the
        Dashboard Server we can't reach hosts over SSM, so it's N/A — including
        for Windows, which is now an explicit N/A rather than a silent blind
        spot (the old behaviour returned no checks at all for Windows)."""
        if not self._is_dashboard_vantage():
            return [{"id": "host_metrics", "status": NA,
                     "detail": "host metrics gathered on the Dashboard Server (over SSM)"}]
        instance_id = inst.get("instance_id", "")
        if inst.get("platform") == "windows":
            return self._ssm_metrics_windows(instance_id, region)
        return self._ssm_metrics_linux(instance_id, region)

    def _run_ssm(self, instance_id: str, region: str, document: str,
                 commands: list, deadline_s: int = 12, poll_s: float = 1.0):
        """Send one SSM command and bounded-poll for its result. Returns
        (outcome, stdout) where outcome is 'ok' (Success), 'fail' (terminal
        non-success), or 'timeout' (deadline hit while still running). Never
        raises — metrics are supplementary, so any trouble degrades to N/A.
        send_command's TimeoutSeconds is DELIVERY-only; our own poll deadline is
        what actually bounds the wait."""
        if not instance_id:
            return ("fail", "")
        try:
            ssm = boto3.client("ssm", region_name=region)
            cmd_id = ssm.send_command(
                InstanceIds=[instance_id], DocumentName=document,
                Parameters={"commands": commands}, TimeoutSeconds=60,
            )["Command"]["CommandId"]
        except Exception:
            return ("fail", "")
        end = time.time() + deadline_s
        while time.time() < end:
            time.sleep(poll_s)
            try:
                inv = ssm.get_command_invocation(CommandId=cmd_id, InstanceId=instance_id)
            except Exception:
                continue  # invocation may not be registered yet
            st = inv.get("Status")
            if st == "Success":
                return ("ok", inv.get("StandardOutputContent", "") or "")
            if st in ("Cancelled", "TimedOut", "Failed"):
                return ("fail", inv.get("StandardOutputContent", "") or "")
        return ("timeout", "")

    def _ssm_metrics_linux(self, instance_id: str, region: str) -> list:
        """root-fs %, memory %, and load average via shell. Failure → N/A."""
        commands = [
            "df -P / | awk 'NR==2{print \"DISK=\"$5}' | tr -d %",
            "free | awk '/Mem:/{printf \"MEM=%d\\n\", $3/$2*100}'",
            "echo LOAD=$(cut -d' ' -f1 /proc/loadavg)",
            "echo CORES=$(nproc)",
        ]
        outcome, out = self._run_ssm(instance_id, region, "AWS-RunShellScript", commands)
        if outcome != "ok" or not out:
            return [{"id": "host_metrics", "status": NA, "detail": "metrics unavailable (SSM)"}]
        vals = {}
        for line in out.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip()
        checks = []
        try:
            if vals.get("DISK", "").isdigit():
                checks.append(self._pct_check("disk", int(vals["DISK"]),
                              self._DISK_WARN, self._DISK_CRIT, "root fs {v}% used"))
            if vals.get("MEM", "").isdigit():
                checks.append(self._pct_check("memory", int(vals["MEM"]),
                              self._MEM_WARN, self._MEM_CRIT, "memory {v}% used"))
            if "LOAD" in vals and vals.get("CORES", "").isdigit():
                load = float(vals["LOAD"]); cores = max(1, int(vals["CORES"]))
                ratio = load / cores
                st = CRIT if ratio >= self._LOAD_CRIT else WARN if ratio >= self._LOAD_WARN else OK
                checks.append({"id": "cpu_load", "status": st,
                               "detail": f"load {load:.2f} over {cores} vCPU"})
        except Exception:
            pass
        return checks or [{"id": "host_metrics", "status": NA, "detail": "metrics unreadable"}]

    def _ssm_metrics_windows(self, instance_id: str, region: str) -> list:
        """disk %, memory %, CPU % via PowerShell + CIM. Emits one compact JSON
        object so a stray warning/progress line can't corrupt parsing. CPU uses
        Win32_PerfFormattedData_PerfOS_Processor (_Total) — multicore-correct and
        locale-independent, unlike Win32_Processor.LoadPercentage (single-core
        bug) or Get-Counter (localized counter paths)."""
        commands = [
            "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'",
            "$d = Get-CimInstance Win32_LogicalDisk -Filter \"DeviceID='C:'\"",
            "$os = Get-CimInstance Win32_OperatingSystem",
            "$cpu = Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter \"Name='_Total'\"",
            "[pscustomobject]@{"
            "disk_pct=[int][math]::Round((($d.Size-$d.FreeSpace)/$d.Size)*100);"
            "mem_pct=[int][math]::Round((($os.TotalVisibleMemorySize-$os.FreePhysicalMemory)/$os.TotalVisibleMemorySize)*100);"
            "cpu_pct=[int][math]::Round($cpu.PercentProcessorTime)"
            "} | ConvertTo-Json -Compress",
        ]
        outcome, out = self._run_ssm(instance_id, region, "AWS-RunPowerShellScript", commands)
        if outcome != "ok" or not out:
            return [{"id": "host_metrics", "status": NA, "detail": "metrics unavailable (SSM)"}]
        import re as _re
        m = _re.search(r"\{.*\}", out, _re.S)  # bounded extract — ignore any banner noise
        if not m:
            return [{"id": "host_metrics", "status": NA, "detail": "metrics unreadable"}]
        try:
            data = json.loads(m.group(0))
        except Exception:
            return [{"id": "host_metrics", "status": NA, "detail": "metrics unreadable"}]
        checks = []
        try:
            if isinstance(data.get("disk_pct"), int):
                checks.append(self._pct_check("disk", data["disk_pct"],
                              self._DISK_WARN, self._DISK_CRIT, "C: {v}% used"))
            if isinstance(data.get("mem_pct"), int):
                checks.append(self._pct_check("memory", data["mem_pct"],
                              self._MEM_WARN, self._MEM_CRIT, "memory {v}% used"))
            if isinstance(data.get("cpu_pct"), int):
                checks.append(self._pct_check("cpu", data["cpu_pct"],
                              self._CPU_WARN, self._CPU_CRIT, "CPU {v}% busy"))
        except Exception:
            pass
        return checks or [{"id": "host_metrics", "status": NA, "detail": "metrics unreadable"}]

    def _pct_check(self, cid: str, value: int, warn: int, crit: int, fmt: str) -> dict:
        st = CRIT if value >= crit else WARN if value >= warn else OK
        return {"id": cid, "status": st, "detail": fmt.format(v=value)}

    def _probe_domain(self, domain: str, expected_ips: Optional[list] = None) -> dict:
        checks = []
        resolved = None
        try:
            resolved = socket.gethostbyname(domain)
            # Record-correctness: the A record should point at one of THIS
            # deployment's redirectors. Drift (stale record, hijack, wrong
            # rotation) is a warn even though DNS technically "resolves".
            if expected_ips and resolved not in expected_ips:
                checks.append({"id": "dns_record", "status": WARN,
                               "detail": f"resolves to {resolved}, expected redirector "
                                         f"{', '.join(expected_ips)}"})
            else:
                checks.append(self._check("dns_resolves", True, f"resolves to {resolved}"))
        except Exception as e:
            checks.append(self._check("dns_resolves", False, f"DNS failed: {e}"))

        if resolved and requests is not None:
            try:
                r = requests.get(f"https://{domain}/", timeout=_PROBE_TIMEOUT,
                                 allow_redirects=True, verify=False)
                ok = r.status_code < 500
                checks.append(self._check("https_responds", ok,
                              f"HTTP {r.status_code}"))
            except Exception as e:
                checks.append(self._check("https_responds", False, f"no response: {e}"))

        return {
            "id": "domain",
            "label": domain,
            "kind": "dns",
            "status": _worst([c["status"] for c in checks]) if checks else UNKNOWN,
            "checks": checks,
        }

    def _probe_peering(self, project: str, region: str) -> Optional[dict]:
        try:
            ec2 = boto3.client("ec2", region_name=region)
            resp = ec2.describe_vpc_peering_connections()
        except Exception as e:
            return {"id": "vpc_peering", "label": "VPC peering", "kind": "fabric",
                    "status": UNKNOWN, "checks": [
                        {"id": "peering_active", "status": UNKNOWN,
                         "detail": f"could not query peering: {e}"}]}

        conns = resp.get("VpcPeeringConnections", [])
        # Match peerings tagged with this project, or fall back to all active.
        relevant = []
        for c in conns:
            tags = {t["Key"]: t["Value"] for t in c.get("Tags", [])}
            status_code = c.get("Status", {}).get("Code", "")
            if status_code in ("deleted", "deleting", "rejected", "failed"):
                continue
            if project in tags.values() or tags.get("Project") == project or not project:
                relevant.append((c, status_code))
        if not relevant:
            relevant = [(c, c.get("Status", {}).get("Code", "")) for c in conns
                        if c.get("Status", {}).get("Code") == "active"]

        if not relevant:
            return {"id": "vpc_peering", "label": "VPC peering", "kind": "fabric",
                    "status": UNKNOWN, "checks": [
                        {"id": "peering_active", "status": UNKNOWN,
                         "detail": "no peering connection found"}]}

        checks = []
        for c, code in relevant:
            active = code == "active"
            checks.append(self._check(
                f"peering_{c.get('VpcPeeringConnectionId', '?')}", active,
                f"{c.get('VpcPeeringConnectionId', '?')}: {code}"))
        return {"id": "vpc_peering", "label": "VPC peering", "kind": "fabric",
                "status": _worst([c["status"] for c in checks]), "checks": checks}

    # ------------------------------------------------------------------
    # Probe primitives
    # ------------------------------------------------------------------

    def _tcp_reachable(self, host: str, port: int) -> bool:
        if not host:
            return False
        try:
            with socket.create_connection((host, port), timeout=_PROBE_TIMEOUT):
                return True
        except Exception:
            return False

    def _cert_check(self, host: str, ip: str) -> dict:
        """Read the live TLS cert and assert days-to-expiry."""
        not_after = self._get_cert_not_after(host)
        if not_after is None and ip and ip != host:
            not_after = self._get_cert_not_after(ip)

        if not_after is None:
            return {"id": "cert_expiry", "status": UNKNOWN,
                    "detail": "TLS up, expiry unreadable (self-signed/IP)"}

        days = (not_after - datetime.now(timezone.utc)).days
        if days < 0:
            return {"id": "cert_expiry", "status": CRIT, "detail": f"EXPIRED {-days}d ago"}
        if days <= CERT_CRIT_DAYS:
            return {"id": "cert_expiry", "status": CRIT, "detail": f"expires in {days}d"}
        if days <= CERT_WARN_DAYS:
            return {"id": "cert_expiry", "status": WARN, "detail": f"expires in {days}d"}
        return {"id": "cert_expiry", "status": OK, "detail": f"{days}d remaining"}

    def _get_cert_not_after(self, host: str) -> Optional[datetime]:
        if not host:
            return None
        # First try a verified handshake (clean notAfter from the cert dict).
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((host, 443), timeout=_PROBE_TIMEOUT) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                    cert = ssock.getpeercert()
            if cert and cert.get("notAfter"):
                return datetime.strptime(
                    cert["notAfter"], "%b %d %H:%M:%S %Y %Z"
                ).replace(tzinfo=timezone.utc)
        except Exception:
            pass
        # Self-signed / hostname-mismatch (IP) path: grab the DER unverified and
        # parse it if cryptography is available.
        if _HAVE_CRYPTO:
            try:
                ctx = ssl._create_unverified_context()
                with socket.create_connection((host, 443), timeout=_PROBE_TIMEOUT) as sock:
                    with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                        der = ssock.getpeercert(binary_form=True)
                if der:
                    crt = x509.load_der_x509_certificate(der, default_backend())
                    na = crt.not_valid_after_utc if hasattr(crt, "not_valid_after_utc") \
                        else crt.not_valid_after.replace(tzinfo=timezone.utc)
                    return na
            except Exception:
                pass
        return None

    def _decoy_check(self, host: str, ip: str, decoy_theme: str) -> dict:
        """Assert the decoy site answers 200 and (if we know the theme) looks right."""
        if requests is None:
            return {"id": "decoy_site", "status": UNKNOWN, "detail": "requests unavailable"}
        url = f"https://{host}/"
        try:
            r = requests.get(url, timeout=_PROBE_TIMEOUT, allow_redirects=True, verify=False)
        except Exception as e:
            return {"id": "decoy_site", "status": CRIT, "detail": f"no response: {e}"}

        if r.status_code >= 500:
            return {"id": "decoy_site", "status": CRIT, "detail": f"HTTP {r.status_code}"}
        if r.status_code >= 400:
            return {"id": "decoy_site", "status": WARN, "detail": f"HTTP {r.status_code}"}

        body = (r.text or "")[:20000].lower()
        # A default nginx splash means the decoy never deployed — that burns the
        # redirector. Flag it explicitly.
        if "welcome to nginx" in body:
            return {"id": "decoy_site", "status": CRIT,
                    "detail": "default nginx page — decoy not deployed"}
        if decoy_theme and decoy_theme.lower() in body:
            return {"id": "decoy_site", "status": OK,
                    "detail": f"HTTP {r.status_code}, '{decoy_theme}' theme present"}
        return {"id": "decoy_site", "status": OK, "detail": f"HTTP {r.status_code}"}

    def _check(self, cid: str, ok: bool, detail: str, soft: bool = False) -> dict:
        """ok->OK, fail->CRIT (or WARN when soft)."""
        if ok:
            return {"id": cid, "status": OK, "detail": detail}
        return {"id": cid, "status": WARN if soft else CRIT, "detail": detail}

    # ------------------------------------------------------------------
    # Discovery + helpers
    # ------------------------------------------------------------------

    def _discover_instances(self, project: str, region: str) -> list:
        ec2 = boto3.client("ec2", region_name=region)
        out = []
        resp = ec2.describe_instances(Filters=[
            {"Name": "tag:Project", "Values": [project]},
            {"Name": "instance-state-name", "Values": ["running"]},
        ])
        for reservation in resp.get("Reservations", []):
            for inst in reservation.get("Instances", []):
                tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
                name_l = tags.get("Name", "").lower()
                # The per-deployment bastion was removed from the architecture
                # (2026-05-29); skip any lingering bastion-tagged instance so it
                # doesn't show as an "unknown" host in Mission Control.
                if "bastion" in name_l:
                    continue
                role = tags.get("Role", "").lower()
                if not role or role == "unknown":
                    name = tags.get("Name", "").lower()
                    if "teamserver" in name or "c2-server" in name or "c2server" in name:
                        role = "teamserver"
                    elif "redirector" in name:
                        role = "redirector"
                    elif "attack" in name:
                        role = "attackbox"
                    elif "jumpbox" in name:
                        role = "jumpbox"
                    else:
                        role = "unknown"
                private_ip = inst.get("PrivateIpAddress", "")
                out.append({
                    "instance_id": inst["InstanceId"],
                    "name": tags.get("Name", "Unknown"),
                    "role": role,
                    "private_ip": private_ip,
                    "public_ip": inst.get("PublicIpAddress", ""),
                    "platform": "windows" if inst.get("Platform") == "windows" else "linux",
                    # Which attached extension (if any) this host belongs to, so
                    # Mission Control's fleet map can render it in its own sub-box.
                    "ext": self._ext_group(tags.get("Name", ""), private_ip, role),
                })
        return out

    def _ext_group(self, name: str, private_ip: str, role: str) -> str:
        """Classify a discovered host as belonging to an attached EXTENSION of a
        C2 deployment (rendered as its own sub-box in Mission Control's fleet
        map), or "" for the core C2 fabric. Subnet first (most reliable), then
        name:
          - test_lab : in-VPC vuln lab on 10.0.20.0/24 (tl* hosts)
          - goad     : peered GOAD AD lab on 192.168.56.0/24
          - ccrts    : peered CREST lab on 192.168.57.0/24
        Core C2 roles (redirector/teamserver/attackbox) are never extensions."""
        if role in ("redirector", "teamserver", "attackbox"):
            return ""
        ip = private_ip or ""
        nl = (name or "").lower()
        if ip.startswith("10.0.20.") or nl.startswith(("tldc", "tlms", "tlws", "tllinux", "tlhost")):
            return "test_lab"
        if ip.startswith("192.168.56.") or "goad" in nl:
            return "goad"
        if ip.startswith("192.168.57.") or nl.startswith("ccrts"):
            return "ccrts"
        return ""

    def _derive_vpc_cidr(self, hosts: list) -> str:
        """Best-effort VPC CIDR from host private IPs when the state output is
        absent — collapse to the /16 prefix (good enough for a display label)."""
        for h in hosts:
            ip = (h.get("private_ip") or "").split(".")
            if len(ip) == 4:
                return f"{ip[0]}.{ip[1]}.0.0/16"
        return ""

    def _host_record(self, inst: dict, status: str, message: str) -> dict:
        return {
            "instance_id": inst["instance_id"],
            "name": inst["name"],
            "role": inst["role"],
            "private_ip": inst.get("private_ip", ""),
            "public_ip": inst.get("public_ip", ""),
            "platform": inst.get("platform", "linux"),
            "ext": inst.get("ext", ""),
            "status": status,
            "message": message,
            "checks": [],
        }

    def _deployment_config(self, project: str) -> dict:
        """Resolve {primary_domain_name, decoy_theme, c2_server_port} for ONE
        deployment, in priority order:
          1. configs/<project>.tfvars  (the deployment's own config)
          2. its deployment-state outputs (dns_domain / primary_domain_name)
          3. configs/terraform.tfvars   (global fallback)
        This is why each card shows its real domain (e.g. its own configured
        decoy domain) instead of a single shared value."""
        from webapp.backend.utils.config_parser import ConfigParser
        cfg = {}

        # 1 — per-project tfvars
        try:
            p = self.project_root / "configs" / f"{project}.tfvars"
            if p.exists():
                cfg.update({k: v for k, v in ConfigParser.parse_tfvars(p).items() if v not in (None, "")})
        except Exception:
            pass

        # 2 — deployment-state terraform outputs (output.dns_domain etc.)
        if not cfg.get("primary_domain_name"):
            try:
                sf = self.project_root / "logs" / "deployment_state" / f"{project}.state.json"
                if sf.exists():
                    state = json.loads(sf.read_text())
                    out = state.get("output") or {}
                    def _ov(key):
                        v = out.get(key)
                        return v.get("value") if isinstance(v, dict) else v
                    dom = _ov("dns_domain") or _ov("primary_domain_name")
                    if dom:
                        cfg["primary_domain_name"] = dom
                    vpc_cidr = _ov("vpc_cidr_block") or _ov("vpc_cidr")
                    if vpc_cidr and not cfg.get("vpc_cidr"):
                        cfg["vpc_cidr"] = vpc_cidr
                    # CS management port (50050) — resolve from the matching
                    # state output, not the listener port.
                    if not cfg.get("c2_server_port") and _ov("c2_server_port"):
                        cfg["c2_server_port"] = _ov("c2_server_port")
            except Exception:
                pass

        # 3 — global tfvars fallback for anything still unset
        try:
            gp = self.project_root / "configs" / "terraform.tfvars"
            if gp.exists():
                for k, v in ConfigParser.parse_tfvars(gp).items():
                    cfg.setdefault(k, v)
        except Exception:
            pass

        return cfg

    def _summarize(self, hosts: list, fabric: list) -> dict:
        counts = {OK: 0, WARN: 0, CRIT: 0, UNKNOWN: 0, NA: 0}
        for item in hosts + fabric:
            st = item.get("status", UNKNOWN)
            counts[st] = counts.get(st, 0) + 1
        return {
            "total": len(hosts) + len(fabric),
            "hosts": len(hosts),
            "ok": counts[OK],
            "warn": counts[WARN],
            "crit": counts[CRIT],
            "unknown": counts[UNKNOWN],
            "na": counts[NA],
        }

    # ------------------------------------------------------------------
    # Layer 3 — scheduler + dead-man's-switch heartbeat
    # ------------------------------------------------------------------

    def start_scheduler(self, projects_region: str = "eu-central-1",
                        interval: int = 3600) -> dict:
        """Start (or reconfigure) the background scheduler. Idempotent."""
        self._scheduler_interval = max(60, int(interval))
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            # A live thread exists. If a stop was requested but the thread hasn't
            # exited yet (it's mid-cycle), clear the event so it keeps running —
            # re-enabling cancels a pending stop instead of racing into a second
            # thread or a dead-thread/"running" mismatch.
            self._scheduler_stop.clear()
            return {"running": True, "interval": self._scheduler_interval, "restarted": False}
        self._scheduler_stop.clear()
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop, args=(projects_region,), daemon=True)
        self._scheduler_thread.start()
        return {"running": True, "interval": self._scheduler_interval, "restarted": True}

    def stop_scheduler(self):
        self._scheduler_stop.set()

    def _scheduler_loop(self, region: str):
        while not self._scheduler_stop.is_set():
            ran = []
            error = None
            try:
                for project in self._known_projects(region):
                    try:
                        self.probe_project(project, region)
                        ran.append(project)
                    except Exception as e:
                        error = f"{project}: {e}"
            except Exception as e:
                error = str(e)
            self._write_heartbeat(ran, error)
            # Wake early if asked to stop.
            self._scheduler_stop.wait(self._scheduler_interval)

    def _known_projects(self, region: str) -> list:
        """Distinct Project tags across running instances — the live fleet."""
        try:
            ec2 = boto3.client("ec2", region_name=region)
            resp = ec2.describe_instances(Filters=[
                {"Name": "instance-state-name", "Values": ["running"]}])
            projects = set()
            for r in resp.get("Reservations", []):
                for inst in r.get("Instances", []):
                    for t in inst.get("Tags", []):
                        if t["Key"] == "Project" and t["Value"]:
                            projects.add(t["Value"])
            return sorted(projects)
        except Exception:
            return []

    def _write_heartbeat(self, ran: list, error: Optional[str]):
        try:
            self.heartbeat_file.write_text(json.dumps({
                "last_run": _now_iso(),
                "interval": self._scheduler_interval,
                "projects": ran,
                "error": error,
            }, indent=2))
        except Exception:
            pass

    def scheduler_status(self) -> dict:
        alive = bool(self._scheduler_thread and self._scheduler_thread.is_alive())
        hb = None
        stale = None
        if self.heartbeat_file.exists():
            try:
                hb = json.loads(self.heartbeat_file.read_text())
                last = datetime.strptime(hb["last_run"], "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - last).total_seconds()
                # Dead-man's switch: stale if older than 2x the interval.
                stale = age > (self._scheduler_interval * 2)
                hb["age_seconds"] = int(age)
            except Exception:
                pass
        return {
            "running": alive,
            "interval": self._scheduler_interval,
            "heartbeat": hb,
            "stale": stale,
        }
