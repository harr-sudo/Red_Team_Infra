"""Canned dummy data for the `demo` deployment_type.

When the active deployment's ``project_name`` is exactly ``demo`` (and
``deployment_type`` is ``demo``), the routes that normally hit live AWS
infrastructure return fixture data from this module instead. The point
is to give an operator a polished, fully-populated dashboard they can
showcase without provisioning anything.

Data shapes match the production endpoints exactly — same keys, same
nesting, same enum values — so the frontend code paths are identical.

Design contract:
  - Demo data is fully in-memory; no AWS calls, no state writes.
  - Per-operator progress (curriculum) still uses the real progress
    service against ``DASHBOARD_STATE_DIR`` — that way "Try the demo"
    actually persists what the operator clicks through.
  - All identifiers, IPs, hostnames are obviously synthetic so an
    operator demoing this can't confuse it for real infra.

Module is import-cheap (no I/O at import time) so the route handlers
can lazily require it on the ``demo`` branch only.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any


DEMO_PROJECT = "demo"
# Unique sentinel used by is_demo_project + route short-circuits.
DEMO_DEPLOYMENT_TYPE = "demo"
DEMO_LAB_NAME = "demo"
# (2026-05-29 — the demo-ccrts showcase row was removed: a CCRTS demo was
# never requested and only cluttered the deployments picker.)
# The real-world architecture the demo models — surfaces in the Manage
# hero + topology badge so the operator knows "this is what you'd get
# from a c2-adhoc deployment with enable_test_lab=true". The CS REST API
# is presumed live so Operations sub-pills (Beacons / Terminal /
# Payloads) auto-light without a real tunnel.
DEMO_MODELS_DEPLOYMENT_TYPE = "c2-adhoc"
DEMO_MODELS_DESCRIPTION = "External C2 (c2-adhoc) + CS REST API + test_lab module"


def _iso(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ──────────────────────────────────────────────────────────────────────
# Deployment state (the record /api/deploy/active returns)
# ──────────────────────────────────────────────────────────────────────

def deployment_state() -> dict[str, Any]:
    """Synthetic deployment-state record. Matches the shape of the JSON
    files under ``logs/deployment_state/{project}.state.json``.

    Demo models a fully-deployed ``c2-adhoc`` deployment with the
    test_lab module enabled and the CS REST API tunnel live, so every
    sub-pill (Manage, Bolt-ons, Beacons, Terminal, Payloads) renders
    populated data without provisioning anything.

    2026-05-23 fixes:
      * completed_at/started_at are unix timestamps (float seconds) to
        match real-deployment shape (frontend does
        `new Date(d.completed_at * 1000)` so ISO strings produced
        "Invalid Date" in the operations dropdown).
      * `output` (singular) is the dict the frontend reads; every value
        is wrapped {"value": ...} terraform-output style. The CS REST
        marker now lives there so APP.BEACON's "REST API enabled?" gate
        accepts demo as connected.
    """
    now = _now()
    now_ts = now.timestamp()
    return {
        "project_name": DEMO_PROJECT,
        "_filename": DEMO_PROJECT,
        # NOTE: deployment_type stays "demo" as the unique sentinel for
        # is_demo_project(); models_deployment_type carries the real-world
        # architecture this demo represents (surfaced in the Manage hero).
        "deployment_type": DEMO_DEPLOYMENT_TYPE,
        "models_deployment_type": DEMO_MODELS_DEPLOYMENT_TYPE,
        "models_description": DEMO_MODELS_DESCRIPTION,
        "status": "success",
        "step": "complete",
        # `output` is the terraform-output dict the frontend consumes;
        # `output_summary` is the human-readable string for log surfaces.
        "output": {
            # 2026-06-02 — No bastion_public_ip: the per-deployment bastion was
            # removed framework-wide; operators jump through the Dashboard
            # Server (its own VPC, not a deployment output).
            "c2_team_server_private_ips": {"value": ["10.0.10.20"], "type": "list"},
            "redirector_public_ip": {"value": "203.0.113.50", "type": "string"},
            "ansible_inventory_path": {"value": "/demo/ansible/inventory.yml", "type": "string"},
            # CS REST API marker — presence of cs_connection_info with
            # rest_api_enabled: true tells Operations sub-pills that the
            # REST tunnel is "up" so they render data instead of the
            # not-enabled empty state.
            "cs_connection_info": {
                "value": {
                    "rest_api_enabled": True,
                    "host": "10.0.10.20",
                    "port": 50050,
                    "is_demo": True,
                },
                "type": "object",
            },
            "deployment_type": {"value": DEMO_MODELS_DEPLOYMENT_TYPE, "type": "string"},
            # test_lab outputs so Manage hero can render the inventory.
            "test_lab_host_inventory": {
                "value": {
                    "tldc01": "10.99.50.10",
                    "tlms01": "10.99.50.20",
                    "tlws01": "10.99.50.30",
                    "tllinux01": "10.99.50.40",
                },
                "type": "object",
            },
            "ssh_key_path": {"value": "~/.ssh/demo_lab_ed25519", "type": "string"},
        },
        "output_summary": "demo deployment — canned data, no real AWS resources",
        "error": None,
        # Unix timestamps (seconds since epoch) so `new Date(ts * 1000)` works
        # in the frontend dropdown date formatter.
        "started_at": now_ts - 2 * 3600,           # 2h ago
        "completed_at": now_ts - (1 * 3600 + 42 * 60),  # 1h42 ago
        "progress_percent": 100,
        "current_phase": "operational",
        "phases_completed": [
            "vpc", "security", "c2_team_server",
            "redirector", "test_lab", "ansible_provisioning",
            "post_deploy_validation",
        ],
        "logs": [],
        "total_resources": 47,
        "resources_completed": 47,
        "aws_region": "eu-central-1",
        "enable_test_lab": True,
        "is_demo": True,
        # Top-level `outputs` (plural) — consumed by the LEGACY full-screen
        # TOPOLOGY overlay (const TOPOLOGY in app.js around line 27586).
        # That code reads /api/deploy/outputs?project=<name> and expects
        # a flat dict with the keys below. Without these, the overlay
        # only renders Operator + Dashboard Server. 2026-05-23 — populated
        # the full c2-adhoc + test_lab field set so the demo paints the
        # complete topology (domain -> redirector -> team server -> attack
        # box + test_lab hosts; no per-deployment bastion).
        "outputs": {
            # Identity
            "project_name": DEMO_PROJECT,
            "deployment_type": DEMO_MODELS_DEPLOYMENT_TYPE,
            "aws_region": "eu-central-1",
            # Domain layer (external)
            "primary_domain_name": "demo-engagement.example.com",
            "c2_subdomain": "api",
            "dns_domain": "demo-engagement.example.com",
            "dns_nameservers": ["ns-1.awsdns-01.com", "ns-2.awsdns-02.net"],
            # Domain fronting disabled in this demo profile
            "enable_domain_fronting": False,
            # Redirector (DMZ public subnet)
            "redirector_public_ip": "203.0.113.50",
            "redirector_private_ip": "10.0.1.20",
            "redirector_instance_id": "i-0demoredir01",
            "redirector_state": "running",
            # Team server (C2 private subnet) — both shapes (singular fallback
            # + plural c2_servers array) so either resolver path works.
            "teamserver_private_ip": "10.0.10.20",
            "teamserver_instance_id": "i-0demots01",
            "teamserver_state": "running",
            "c2_servers": [
                {
                    "private_ip": "10.0.10.20",
                    "instance_id": "i-0demots01",
                    "state": "running",
                },
            ],
            "c2_team_server_private_ips": ["10.0.10.20"],
            "cs_teamserver_password": "demo-pass-do-not-use",
            "malleable_profile": "demo-jquery.profile",
            # 2026-06-02 — No bastion block: the per-deployment SSH-relay
            # bastion was removed framework-wide. The Dashboard Server is the
            # sole jump host (own VPC, EIP) and is not a deployment output.
            # Attack box (Windows operator host, C2 private subnet)
            "attackbox_private_ip": "10.0.10.30",
            "attackbox_instance_id": "i-0demoattack01",
            "attackbox_state": "running",
            "attackbox_password": "demo-attack-do-not-use",
            # Test lab module (linked to the bolt-on host roster — same
            # hostnames the Bolt-ons sub-pill targets).
            "enable_test_lab": True,
            "tldc01_private_ip": "10.99.50.10",
            "tlms01_private_ip": "10.99.50.20",
            "tlws01_private_ip": "10.99.50.30",
            "tllinux01_private_ip": "10.99.50.40",
            # Ansible orchestration paths
            "ansible_inventory_path": "/demo/ansible/inventory.yml",
            # CS REST API marker (also surfaced under `output.cs_connection_info`
            # for the V3 sub-pill gates; mirrored here for the legacy overlay).
            "enable_cs_rest_api": True,
            "c2_server_port": 50050,
            "c2_listener_port": 443,
        },
    }


# ──────────────────────────────────────────────────────────────────────
# Beacons
# ──────────────────────────────────────────────────────────────────────

def beacon_list() -> list[dict[str, Any]]:
    """Synthetic beacon tree mirroring the test_lab hosts (tldc01/tlms01/
    tlws01/tllinux01) with a realistic attack chain: initial drop on the
    workstation → lateral to member → DA on the DC, plus a Linux foothold
    via found credentials.

    Field names match the CS REST API exactly (bid/user/computer/internal/
    pid/os/arch/isAdmin/alive/listener/sleep/jitter/lastCheckinMs/pbid/
    pivotHint) so APP.BEACON.refreshBeacons() can consume them without any
    demo-aware normalization layer.

    Topology (parent → child):
        demo-root-WS01   (tlws01, phishing drop, HTTPS callback)
          └── demo-pivot-MS01     (tlms01, lateral via SMB)
                ├── demo-pivot-DC01    (tldc01, Golden Ticket → DA)
                └── demo-pivot-LIN01   (tllinux01, SSH key from cred dump)
    """
    now_ms = int(now.timestamp() * 1000) if (now := _now()) else 0
    return [
        {
            "bid": "demo-root-WS01",
            "pbid": None,
            "user": "TESTLAB\\jdoe",
            "computer": "tlws01",
            "internal": "10.99.50.30",
            "external": "203.0.113.50",
            "os": "Windows 10 Pro",
            "arch": "x64",
            "pid": 4128,
            "ppid": 1024,
            "process": "explorer.exe",
            "isAdmin": False,
            "alive": True,
            "listener": "demo-https-cdn",
            "linkState": "PARENT",
            "pivotHint": "",
            "session": "beacon",
            "sleep": 60,           # CS REST returns int seconds; refreshBeacons multiplies by 1000
            "jitter": 15,
            "lastCheckinMs": 8000,  # 8s since last check-in
            "is_demo": True,
            "deployment": DEMO_PROJECT,
        },
        {
            "bid": "demo-pivot-MS01",
            "pbid": "demo-root-WS01",
            "user": "TESTLAB\\svc_sql",
            "computer": "tlms01",
            "internal": "10.99.50.20",
            "external": "203.0.113.50",
            "os": "Windows Server 2022 Standard",
            "arch": "x64",
            "pid": 612,
            "ppid": 8,
            "process": "services.exe",
            "isAdmin": True,
            "alive": True,
            "listener": "smb-pivot",
            "linkState": "CHILD",
            "pivotHint": "445, smb",
            "session": "beacon",
            "sleep": 60,
            "jitter": 10,
            "lastCheckinMs": 12000,
            "is_demo": True,
            "deployment": DEMO_PROJECT,
        },
        {
            "bid": "demo-pivot-DC01",
            "pbid": "demo-pivot-MS01",
            "user": "TESTLAB\\Administrator",
            "computer": "tldc01",
            "internal": "10.99.50.10",
            "external": "203.0.113.50",
            "os": "Windows Server 2022 Datacenter",
            "arch": "x64",
            "pid": 932,
            "ppid": 612,
            "process": "lsass.exe",
            "isAdmin": True,
            "alive": True,
            "listener": "smb-pivot",
            "linkState": "CHILD",
            "pivotHint": "445, smb",
            "session": "beacon",
            "sleep": 30,
            "jitter": 5,
            "lastCheckinMs": 4000,
            "is_demo": True,
            "deployment": DEMO_PROJECT,
        },
        {
            "bid": "demo-pivot-LIN01",
            "pbid": "demo-pivot-MS01",
            "user": "root",
            "computer": "tllinux01",
            "internal": "10.99.50.40",
            "external": "203.0.113.50",
            "os": "Linux 22.04 (Ubuntu)",
            "arch": "x64",
            "pid": 1932,
            "ppid": 1,
            "process": "/usr/bin/python3",
            "isAdmin": True,
            "alive": True,
            "listener": "demo-https-cdn",
            "linkState": "CHILD",
            "pivotHint": "",
            "session": "ssh_beacon",
            "sleep": 90,
            "jitter": 20,
            "lastCheckinMs": 45000,  # stale-but-alive
            "is_demo": True,
            "deployment": DEMO_PROJECT,
        },
    ]


def beacon_detail(bid: str) -> dict[str, Any] | None:
    # 2026-05-23 — field rename: beacon_list() now uses CS REST API field
    # names (user/computer instead of username/hostname). Detail keeps the
    # same structure plus a one-task fake history + metadata block.
    for b in beacon_list():
        if b["bid"] == bid:
            # Derive a sensible "role" string for the metadata block from
            # the host's name (tldc01 → domain_controller, etc.).
            computer = (b.get("computer") or "").lower()
            if "dc" in computer:
                role = "domain_controller"
            elif "ms" in computer or "srv" in computer:
                role = "member_server"
            elif "ws" in computer:
                role = "workstation"
            elif "lin" in computer or "linux" in computer:
                role = "linux_member"
            else:
                role = "unknown"
            return {
                **b,
                "tasks": [
                    {
                        "task_id": f"demo-task-{bid}-001",
                        "status": "COMPLETED",
                        "command": "shell whoami",
                        "result": f"{b.get('user', '')}\n",
                        "issued_at": _iso(_now() - timedelta(seconds=120)),
                        "completed_at": _iso(_now() - timedelta(seconds=118)),
                    },
                ],
                "metadata": {
                    "computer_role": role,
                    "smb_pipe": None,
                    "session_id": "1",
                    "parent_bid": b.get("pbid"),
                    "pivot_hint": b.get("pivotHint") or "",
                },
            }
    return None


# ──────────────────────────────────────────────────────────────────────
# Payloads
# ──────────────────────────────────────────────────────────────────────

def payload_artifacts() -> list[dict[str, Any]]:
    now = _now()
    return [
        {
            "filename": "beacon-demo-https-stageless.exe",
            "kind": "stageless_pe",
            "listener": "demo-https-cdn",
            "size_bytes": 287232,
            "sha256": "a1b2c3d4e5f60718293a4b5c6d7e8f90112233445566778899aabbccddeeff00",
            "generated_at": _iso(now - timedelta(hours=1, minutes=30)),
            "operator": "demo",
        },
        {
            "filename": "beacon-demo-http-stager.exe",
            "kind": "stager_pe",
            "listener": "demo-http",
            "size_bytes": 11264,
            "sha256": "deadbeef00112233445566778899aabbccddeeff112233445566778899aabbcc",
            "generated_at": _iso(now - timedelta(hours=1, minutes=10)),
            "operator": "demo",
        },
        {
            "filename": "beacon-demo-https-stageless.dll",
            "kind": "stageless_dll",
            "listener": "demo-https-cdn",
            "size_bytes": 281600,
            "sha256": "feedfacecafebabe00112233445566778899aabbccddeeff1122334455667788",
            "generated_at": _iso(now - timedelta(minutes=42)),
            "operator": "demo",
        },
    ]


# ──────────────────────────────────────────────────────────────────────
# Resources (Manage pane)
# ──────────────────────────────────────────────────────────────────────

def resources() -> list[dict[str, Any]]:
    # 2026-06-02 — Coherent single-deployment fleet for the showcased
    # `c2-adhoc` (+ test_lab) deployment. The per-deployment bastion was
    # removed framework-wide — the AWS-hosted Dashboard Server is the sole
    # SSH/RDP jump host (its own VPC, not part of this deployment's resource
    # set), so there is NO bastion instance or bastion security group here.
    # The GOAD rows were dropped too: c2-adhoc has no AD lab (the test_lab
    # hosts are surfaced separately via lab_hosts()).
    return [
        {"type": "aws_vpc", "name": "demo-vpc", "id": "vpc-0demo01",
         "region": "eu-central-1", "state": "live",
         "details": {"cidr": "10.0.0.0/16"}},
        {"type": "aws_subnet", "name": "demo-private-1", "id": "subnet-0demo10",
         "region": "eu-central-1", "state": "live",
         "details": {"cidr": "10.0.10.0/24", "az": "eu-central-1a"}},
        {"type": "aws_subnet", "name": "demo-public-1", "id": "subnet-0demo11",
         "region": "eu-central-1", "state": "live",
         "details": {"cidr": "10.0.1.0/24", "az": "eu-central-1a"}},
        {"type": "aws_internet_gateway", "name": "demo-igw", "id": "igw-0demo01",
         "region": "eu-central-1", "state": "live", "details": {}},
        {"type": "aws_nat_gateway", "name": "demo-nat", "id": "nat-0demo01",
         "region": "eu-central-1", "state": "live",
         "details": {"public_ip": "203.0.113.60"}},
        {"type": "aws_instance", "name": "demo-c2-team-server", "id": "i-0democ2",
         "region": "eu-central-1", "state": "live",
         "details": {"instance_type": "t3.medium", "private_ip": "10.0.10.20"}},
        {"type": "aws_instance", "name": "demo-redirector", "id": "i-0demoredir",
         "region": "eu-central-1", "state": "live",
         "details": {"instance_type": "t3.micro", "private_ip": "10.0.1.20",
                     "public_ip": "203.0.113.50"}},
        {"type": "aws_instance", "name": "demo-attack-box", "id": "i-0demoattack01",
         "region": "eu-central-1", "state": "live",
         "details": {"instance_type": "t2.large", "private_ip": "10.0.10.30"}},
        {"type": "aws_security_group", "name": "demo-sg-c2",
         "id": "sg-0democ2", "region": "eu-central-1", "state": "live",
         "details": {"ingress_count": 2}},
        {"type": "aws_security_group", "name": "demo-sg-redirector",
         "id": "sg-0demoredir", "region": "eu-central-1", "state": "live",
         "details": {"ingress_count": 3}},
    ]


# ──────────────────────────────────────────────────────────────────────
# Cost summary
# ──────────────────────────────────────────────────────────────────────

def cost_summary() -> dict[str, Any]:
    return {
        "project_name": DEMO_PROJECT,
        "monthly_total": 184.20,
        "currency": "USD",
        "by_service": {
            "EC2-Instances": 124.50,
            "VPC-NAT": 32.40,
            "Data-Transfer": 18.30,
            "EBS-Storage": 9.00,
        },
        "last_updated": _iso(_now() - timedelta(minutes=8)),
        "is_demo": True,
    }


# ──────────────────────────────────────────────────────────────────────
# Test lab / bolt-on host facts
# ──────────────────────────────────────────────────────────────────────

DEMO_HOSTS = ["tldc01", "tlms01", "tlws01", "tllinux01"]


def lab_hosts() -> list[dict[str, Any]]:
    """2026-05-22 — Mirrors the canonical `test_lab` Terraform module output
    EXACTLY (terraform/modules/test_lab/outputs.tf::host_inventory) so the
    demo represents what an operator sees when they enable
    `enable_test_lab=true` on a c2-* deployment. Same hostnames, same
    role values that bolt-on catalog descriptors target.
    """
    return [
        {"name": "tldc01", "role": "domain_controller",
         "os": "Windows Server 2022", "ip": "10.99.50.10",
         "installed_count": 2},
        {"name": "tlms01", "role": "member_server",
         "os": "Windows Server 2022", "ip": "10.99.50.20",
         "installed_count": 0},
        {"name": "tlws01", "role": "workstation",
         "os": "Windows 10", "ip": "10.99.50.30",
         "installed_count": 0},
        {"name": "tllinux01", "role": "linux_member",
         "os": "Ubuntu 22.04", "ip": "10.99.50.40",
         "installed_count": 0},
    ]


def host_facts(host: str) -> dict[str, Any] | None:
    # Same canonical roster as test_lab outputs.tf — see comment on
    # lab_hosts() above. Mismatching this map against catalog descriptors'
    # `targets.required_roles` is what made `ca_host` etc. show up
    # before; now demo == test_lab.
    #
    # 2026-05-23 — added os_edition + domain_function_level so descriptors
    # that gate on those fields (edition_in, required_domain_function_level)
    # paint correctly in demo. tldc01 carries the DFL since it's the DC.
    matrix = {
        "tldc01": ("windows", "2022", "domain_controller", "Datacenter", "2016"),
        "tlms01": ("windows", "2022", "member_server", "Standard", "2016"),
        "tlws01": ("windows", "10", "workstation", "Pro", "2016"),
        "tllinux01": ("linux", "22.04", "linux_member", None, None),
    }
    if host not in matrix:
        return None
    family, version, role, edition, dfl = matrix[host]
    now = _now()
    # Installed list is dynamic — pulled from the in-memory install state
    # so the operator's fake install / uninstall actions are reflected on
    # the next /facts request.
    # 2026-05-23 — populate installed_services so descriptors that gate on
    # `required_services` (smb, iis, adcs, print spooler, etc.) resolve
    # correctly. Windows hosts get SMBv3 + Print Spooler by default;
    # the DC also runs ADCS + IIS for ESC1/ESC2 / coercion paths.
    if family == "windows":
        services = {"smb": "SMBv3", "spooler": "10.0", "rpc": "10.0"}
        if role == "domain_controller":
            services.update({"adcs": "ADCS-Cert-Authority", "iis": "10.0",
                            "netlogon": "10.0", "kdc": "10.0", "dns": "10.0"})
    else:
        # Linux test_lab host — populate the services that the new Linux
        # bolt-ons (sudo / SUID / cron / SSH key / NFS / wildcard / PATH
        # hijack / PwnKit + docker) declare as `required_services`. These
        # are all default-installed on Ubuntu 22.04 server.
        services = {
            "openssh": "8.9", "sshd": "8.9",
            "cron": "3.0", "rsyslog": "8.2",
            "polkit": "0.105", "policykit-1": "0.105",
            "docker": "24.0",
            "nfs-kernel-server": "2.6",
            "sudo": "1.9",
        }
    return {
        "host": host,
        "host_id": host,
        "os_family": family,
        "os_version": version,
        "os_edition": edition,
        "role": role,
        "domain_function_level": dfl,
        "installed_services": services,
        "gathered_at": _iso(now - timedelta(minutes=5)),
        "stale": False,
        "installed_boltons": get_installed_for_host(host),
    }


# ──────────────────────────────────────────────────────────────────────
# Audit (we DON'T mock — operator's real audit log still applies)
# ──────────────────────────────────────────────────────────────────────


def is_demo_project(project_name: str | None) -> bool:
    """Single source of truth for the demo-or-not branch in route handlers.

    Matches any of:
      * The literal ``demo`` showcase project (static fully-populated dashboard).
      * A walkthrough draft whose name matches ``demo-draft-<slug>``
        (Phase 4 — "+ Provision a Demo Deployment" flow). The slug is the
        operator's session-scoped timestamp (base36), so the regex stays
        permissive: alphanumerics + dashes.
      * Any project whose persisted deployment state JSON flags itself as
        ``is_demo`` or ``is_demo_draft``. This is the load-bearing check
        for the Phase 4 synthetic apply — the demo-draft handler writes
        ``is_demo: True`` into the state file once the simulated 30s tick
        finishes, so downstream surfaces (Manage, Bolt-ons, Operations
        sub-pills) resolve it the same way they resolve the static demo.
    """
    if not project_name:
        return False
    name = str(project_name).strip()
    lower = name.lower()
    # Path A — literal "demo".
    if lower == DEMO_PROJECT:
        seed_demo_audit_entries()
        return True
    # Path B — demo-draft-* walkthrough deployments.
    # Pattern is intentionally permissive: lower-cased letters, digits,
    # and dashes after the prefix. The frontend generates
    # ``demo-draft-<base36-timestamp>`` so this matches without imposing
    # tighter shape constraints that would silently break future slug
    # schemes.
    import re as _re
    if _re.match(r"^demo-draft-[a-z0-9-]+$", lower):
        return True
    # Path C — state-file flagged. Best-effort: if the per-project state
    # file carries is_demo / is_demo_draft we honor it. Never raises —
    # is_demo_project is called on hot paths and a missing/corrupt state
    # file must NOT cause demo detection to fail open and trigger real
    # terraform calls.
    try:
        from pathlib import Path as _Path
        # Mirror routes/deploy.py:_state_file_path sanitization.
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        # Project root: services/ → backend/ → webapp/ → repo root.
        _root = _Path(__file__).parent.parent.parent.parent
        _state = _root / "logs" / "deployment_state" / f"{safe}.state.json"
        if _state.exists():
            import json as _json
            with open(_state, "r") as _f:
                _data = _json.load(_f)
            if isinstance(_data, dict) and (
                _data.get("is_demo") is True
                or _data.get("is_demo_draft") is True
            ):
                return True
    except Exception:
        # Silent fallthrough — never let state-file IO break demo
        # detection on the hot path.
        pass
    return False


# ──────────────────────────────────────────────────────────────────────
# Audit seed (one-shot per process — see seed_demo_audit_entries below)
# ──────────────────────────────────────────────────────────────────────

_DEMO_AUDIT_SEEDED = False
_DEMO_AUDIT_SEED_LOCK = threading.RLock()


def seed_demo_audit_entries() -> None:
    """Write a handful of fake audit rows the first time the demo is
    touched in this Flask process. Idempotent + best-effort.

    Rows written:
      * deploy.start          — synthetic operator kicks off the demo
      * deploy.complete       — demo finishes provisioning
      * beacon.exec           — two beacons each get a `shell whoami`
      * bolton.install        — kerberoast bolt-on installed on tldc01

    All entries carry `details.is_demo = True` and use the synthetic
    actor `"demo"` so they're visually distinct from the operator's
    real audit activity in the Recent Activity feed.
    """
    global _DEMO_AUDIT_SEEDED
    if _DEMO_AUDIT_SEEDED:
        return
    with _DEMO_AUDIT_SEED_LOCK:
        if _DEMO_AUDIT_SEEDED:
            return
        # Flip the flag UP FRONT so failed audit writes don't cause us
        # to retry on every request — the seed runs at most once per
        # process regardless of outcome.
        _DEMO_AUDIT_SEEDED = True
        try:
            from webapp.backend.services import audit_service
            actor = "demo"
            entries = [
                ("deploy.start", DEMO_PROJECT,
                 {"is_demo": True, "deployment_type": DEMO_MODELS_DEPLOYMENT_TYPE}),
                ("deploy.complete", DEMO_PROJECT,
                 {"is_demo": True, "duration_seconds": 1080,
                  "phases": ["vpc", "security", "c2_team_server",
                             "redirector", "test_lab"]}),
                ("beacon.exec", DEMO_PROJECT,
                 {"is_demo": True, "bid": "demo-root-WS01",
                  "command": "shell whoami", "target": "tlws01"}),
                ("beacon.exec", DEMO_PROJECT,
                 {"is_demo": True, "bid": "demo-pivot-DC01",
                  "command": "shell whoami", "target": "tldc01"}),
                ("bolton.install", DEMO_PROJECT,
                 {"is_demo": True,
                  "vuln_id": "bolton.identity-kerberos.kerberoastable-svc",
                  "host": "tldc01", "lab": DEMO_LAB_NAME}),
            ]
            for action, project, details in entries:
                target = details.get("target") or details.get("host")
                audit_service.write(
                    actor, action,
                    target=target,
                    project=project,
                    details=details,
                )
        except Exception:
            # Audit is best-effort and must NEVER break a request. The
            # flag stays UP so we don't keep retrying.
            pass


# ──────────────────────────────────────────────────────────────────────
# Fake install / patch / uninstall — in-memory bolt-on state per host
# ──────────────────────────────────────────────────────────────────────
#
# Demo mode pretends to install/patch/uninstall bolt-ons so an operator
# can showcase the full lifecycle (Available → Installed → Patched →
# Uninstalled) without provisioning real Ansible/AWS. State is held in
# module-level dicts; restart Flask to reset.
#
# The fake job manager spawns "jobs" that complete instantly (status =
# SUCCEEDED) and have a canned log tail so the progress overlay
# resolves cleanly.

import threading
import uuid as _uuid

# host_id -> {vuln_id: "installed" | "patched"}
# Seed: two installed on tldc01 so operators land on a populated
# "Installed" section without having to click Install first.
_demo_install_state: dict[str, dict[str, str]] = {
    "tldc01": {
        "bolton.identity-kerberos.kerberoastable-svc": "installed",
        "bolton.access-control.adminsdholder-acl-modified": "installed",
    },
}

# job_id -> dict
_demo_jobs: dict[str, dict[str, Any]] = {}
_demo_lock = threading.RLock()


def get_installed_for_host(host: str) -> list[str]:
    """Return the IDs of bolt-ons currently installed on a demo host."""
    with _demo_lock:
        return [
            vid for vid, state in _demo_install_state.get(host, {}).items()
            # Patched bolt-ons are still "installed" from a catalog-state POV.
            if state in ("installed", "patched")
        ]


def get_install_state(host: str, vuln_id: str) -> str | None:
    """`installed` | `patched` | None."""
    with _demo_lock:
        return _demo_install_state.get(host, {}).get(vuln_id)


def dispatch_fake_op(*, op: str, lab: str, host: str, vuln_id: str,
                     actor: str) -> dict[str, Any]:
    """Mutate the in-memory install state for demo, then return a fake
    job record so the frontend's progress overlay completes cleanly.

    Supported ops: install | uninstall | patch | patch-revert.
    """
    with _demo_lock:
        host_state = _demo_install_state.setdefault(host, {})
        if op == "install":
            host_state[vuln_id] = "installed"
            log_lines = [
                "[demo] dispatching install (fake)",
                f"[demo] target: {host} · vuln: {vuln_id}",
                "[demo] ansible play simulated — 4 tasks, 0 changed",
                "[demo] verify probe: OK",
                "[demo] install COMPLETE",
            ]
        elif op == "uninstall":
            if vuln_id in host_state:
                del host_state[vuln_id]
            log_lines = [
                "[demo] dispatching uninstall (fake)",
                "[demo] revert artefacts removed",
                "[demo] uninstall COMPLETE",
            ]
        elif op == "patch":
            host_state[vuln_id] = "patched"
            log_lines = [
                "[demo] dispatching patch (fake)",
                "[demo] applying remediation (rotating password / clearing RC4 / etc)",
                "[demo] exploit_probe_after_patch: blocked",
                "[demo] patch COMPLETE",
            ]
        elif op == "patch-revert":
            host_state[vuln_id] = "installed"
            log_lines = [
                "[demo] dispatching patch-revert (fake)",
                "[demo] re-arming exploitable state",
                "[demo] patch-revert COMPLETE",
            ]
        else:
            return {"job_id": None, "message": f"unknown op {op}"}

        job_id = f"demo-job-{_uuid.uuid4().hex[:8]}"
        now = _now()
        job = {
            "job_id": job_id,
            "is_demo": True,
            "op": op,
            "lab": lab,
            "host": host,
            "vuln_id": vuln_id,
            "actor": actor,
            "status": "SUCCEEDED",
            "started_at": _iso(now),
            "completed_at": _iso(now),
            "estimated_time_seconds": 0,
            "message": f"demo {op} completed instantly (no real infra touched)",
            "steps": [
                {"name": op, "status": "SUCCEEDED",
                 "started_at": _iso(now), "completed_at": _iso(now)},
            ],
            "log_tail": "\n".join(log_lines),
            "log_lines": log_lines,
        }
        _demo_jobs[job_id] = job
        return job


def get_fake_job(job_id: str) -> dict[str, Any] | None:
    with _demo_lock:
        return _demo_jobs.get(job_id)


def reset_install_state() -> None:
    """Wipe demo install state (operator-facing 'reset demo' button hook)."""
    with _demo_lock:
        _demo_install_state.clear()
        _demo_install_state["tldc01"] = {
            "bolton.identity-kerberos.kerberoastable-svc": "installed",
            "bolton.access-control.adminsdholder-acl-modified": "installed",
        }
        _demo_jobs.clear()
