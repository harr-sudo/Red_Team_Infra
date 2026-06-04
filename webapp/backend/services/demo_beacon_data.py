"""Demo beacon data surfaces (P2-OB).

Synthetic fixtures for the beacon DATA-SURFACE endpoints:
files, processes, creds, tokens, jobs, downloads, screenshots,
keystrokes, recon, pivoting, config writes, C2 hosts, server info,
payload generation, BOF.

Designed so the operator demoing the dashboard sees populated content
on every Beacons sub-tab without a live Cobalt Strike team server.

Companion module ``demo_beacon_ops`` (owned by agent OA) handles the
console/tasks/sleep/listeners surfaces. Both modules share the
``is_demo_bid()`` predicate defined here.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

# ──────────────────────────────────────────────────────────────────────
# Detection predicate (shared with demo_beacon_ops)
# ──────────────────────────────────────────────────────────────────────


def is_demo_bid(bid: str | None) -> bool:
    """Single source of truth: any bid prefixed with ``demo-`` is synthetic."""
    return bool(bid) and str(bid).startswith("demo-")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: datetime) -> str:
    return ts.replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ──────────────────────────────────────────────────────────────────────
# Per-bid OS family lookup
# ──────────────────────────────────────────────────────────────────────

# Mirror beacon_list() in demo_data_service.py.
_BID_OS = {
    "demo-root-WS01": "windows",
    "demo-pivot-MS01": "windows",
    "demo-pivot-DC01": "windows",
    "demo-pivot-LIN01": "linux",
}

_BID_HOST = {
    "demo-root-WS01": "tlws01",
    "demo-pivot-MS01": "tlms01",
    "demo-pivot-DC01": "tldc01",
    "demo-pivot-LIN01": "tllinux01",
}


def _is_windows(bid: str) -> bool:
    return _BID_OS.get(bid, "windows") == "windows"


def _is_dc(bid: str) -> bool:
    return bid == "demo-pivot-DC01"


def _ok(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    base = {"success": True, "is_demo": True}
    if payload:
        base.update(payload)
    return base


def _task_id(prefix: str = "demo-task") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _dispatch_task(bid: str, command: str) -> str:
    """Best-effort: register a task with OA's demo_beacon_ops if available."""
    try:
        from webapp.backend.services import demo_beacon_ops  # type: ignore
        if hasattr(demo_beacon_ops, "dispatch_demo_command"):
            res = demo_beacon_ops.dispatch_demo_command(bid, command)
            if isinstance(res, dict) and "task_id" in res:
                return res["task_id"]
            if isinstance(res, str):
                return res
    except Exception:
        pass
    return _task_id()


# ──────────────────────────────────────────────────────────────────────
# Files
# ──────────────────────────────────────────────────────────────────────


def list_directory(bid: str, path: str | None) -> dict[str, Any]:
    now = _iso(_now() - timedelta(hours=2))
    if _is_windows(bid):
        rows = [
            {"name": "Documents", "type": "dir", "size": 0, "modified": now,
             "attributes": "D"},
            {"name": "Downloads", "type": "dir", "size": 0, "modified": now,
             "attributes": "D"},
            {"name": "Pictures", "type": "dir", "size": 0, "modified": now,
             "attributes": "D"},
            {"name": "secret.txt", "type": "file", "size": 142,
             "modified": now, "attributes": "A"},
            {"name": "notes.docx", "type": "file", "size": 24576,
             "modified": now, "attributes": "A"},
            {"name": "desktop.ini", "type": "file", "size": 282,
             "modified": now, "attributes": "HSA"},
        ]
        cwd = path or "C:\\Users\\jdoe"
    else:
        rows = [
            {"name": "bin", "type": "dir", "size": 4096, "modified": now,
             "permissions": "drwxr-xr-x"},
            {"name": "etc", "type": "dir", "size": 4096, "modified": now,
             "permissions": "drwxr-xr-x"},
            {"name": "home", "type": "dir", "size": 4096, "modified": now,
             "permissions": "drwxr-xr-x"},
            {"name": "var", "type": "dir", "size": 4096, "modified": now,
             "permissions": "drwxr-xr-x"},
            {"name": "tmp", "type": "dir", "size": 4096, "modified": now,
             "permissions": "drwxrwxrwt"},
            {"name": "root", "type": "dir", "size": 4096, "modified": now,
             "permissions": "drwx------"},
        ]
        cwd = path or "/"
    return _ok({"path": cwd, "entries": rows, "data": rows})


def list_drives(bid: str) -> dict[str, Any]:
    if not _is_windows(bid):
        return _ok({"drives": [], "data": []})
    drives = [
        {"drive": "C:", "type": "Fixed", "filesystem": "NTFS",
         "free_bytes": 60 * 1024**3, "total_bytes": 100 * 1024**3,
         "label": "OS"},
        {"drive": "D:", "type": "Fixed", "filesystem": "NTFS",
         "free_bytes": 200 * 1024**3, "total_bytes": 250 * 1024**3,
         "label": "Data"},
    ]
    return _ok({"drives": drives, "data": drives})


def fs_noop(bid: str, action: str, target: str = "") -> dict[str, Any]:
    return _ok({
        "task_id": _dispatch_task(bid, f"{action} {target}".strip()),
        "message": f"{action} accepted (demo no-op)",
    })


# ──────────────────────────────────────────────────────────────────────
# Processes
# ──────────────────────────────────────────────────────────────────────


_WIN_PS = [
    {"pid": 4, "ppid": 0, "name": "System", "user": "SYSTEM", "arch": "x64", "session": 0},
    {"pid": 612, "ppid": 4, "name": "lsass.exe", "user": "SYSTEM", "arch": "x64", "session": 0},
    {"pid": 720, "ppid": 4, "name": "svchost.exe", "user": "SYSTEM", "arch": "x64", "session": 0},
    {"pid": 880, "ppid": 4, "name": "sysmon.exe", "user": "SYSTEM", "arch": "x64", "session": 0},
    {"pid": 1024, "ppid": 720, "name": "winlogon.exe", "user": "SYSTEM", "arch": "x64", "session": 1},
    {"pid": 1840, "ppid": 1024, "name": "explorer.exe", "user": "jdoe", "arch": "x64", "session": 1},
    {"pid": 2104, "ppid": 1840, "name": "chrome.exe", "user": "jdoe", "arch": "x64", "session": 1},
    {"pid": 2228, "ppid": 2104, "name": "chrome.exe", "user": "jdoe", "arch": "x64", "session": 1},
    {"pid": 3140, "ppid": 1840, "name": "OUTLOOK.EXE", "user": "jdoe", "arch": "x64", "session": 1},
    {"pid": 4128, "ppid": 1840, "name": "beacon.exe", "user": "jdoe", "arch": "x64", "session": 1},
    {"pid": 4404, "ppid": 720, "name": "MsMpEng.exe", "user": "SYSTEM", "arch": "x64", "session": 0},
    {"pid": 5012, "ppid": 720, "name": "spoolsv.exe", "user": "SYSTEM", "arch": "x64", "session": 0},
]

_LIN_PS = [
    {"pid": 1, "ppid": 0, "name": "systemd", "user": "root", "arch": "x64"},
    {"pid": 412, "ppid": 1, "name": "systemd-journald", "user": "root", "arch": "x64"},
    {"pid": 588, "ppid": 1, "name": "sshd", "user": "root", "arch": "x64"},
    {"pid": 612, "ppid": 1, "name": "cron", "user": "root", "arch": "x64"},
    {"pid": 740, "ppid": 1, "name": "dbus-daemon", "user": "messagebus", "arch": "x64"},
    {"pid": 920, "ppid": 1, "name": "rsyslogd", "user": "syslog", "arch": "x64"},
    {"pid": 1102, "ppid": 1, "name": "nginx", "user": "www-data", "arch": "x64"},
    {"pid": 1340, "ppid": 588, "name": "sshd: root@pts/0", "user": "root", "arch": "x64"},
    {"pid": 1408, "ppid": 1340, "name": "bash", "user": "root", "arch": "x64"},
    {"pid": 1932, "ppid": 1408, "name": "python3", "user": "root", "arch": "x64"},
    {"pid": 2188, "ppid": 1, "name": "docker-containerd", "user": "root", "arch": "x64"},
    {"pid": 2540, "ppid": 1, "name": "snap-store", "user": "root", "arch": "x64"},
]


def list_processes(bid: str) -> dict[str, Any]:
    rows = _WIN_PS if _is_windows(bid) else _LIN_PS
    return _ok({"processes": rows, "data": rows})


def kill_process(bid: str, pid: int | str) -> dict[str, Any]:
    return _ok({
        "task_id": _dispatch_task(bid, f"kill {pid}"),
        "message": f"PID {pid} kill requested (demo)",
    })


# ──────────────────────────────────────────────────────────────────────
# Tokens
# ──────────────────────────────────────────────────────────────────────


_BID_TOKENS = {
    "demo-pivot-DC01": [
        {"id": 1, "user": "NT AUTHORITY\\SYSTEM", "pid": 612, "process": "lsass.exe", "type": "PRIMARY"},
        {"id": 2, "user": "TESTLAB\\Administrator", "pid": 932, "process": "lsass.exe", "type": "IMPERSONATION"},
        {"id": 3, "user": "TESTLAB\\svc_sql", "pid": 2104, "process": "sqlservr.exe", "type": "IMPERSONATION"},
    ],
    "demo-pivot-MS01": [
        {"id": 1, "user": "NT AUTHORITY\\SYSTEM", "pid": 612, "process": "lsass.exe", "type": "PRIMARY"},
        {"id": 2, "user": "TESTLAB\\svc_sql", "pid": 2104, "process": "sqlservr.exe", "type": "IMPERSONATION"},
    ],
    "demo-root-WS01": [
        {"id": 1, "user": "NT AUTHORITY\\SYSTEM", "pid": 4, "process": "System", "type": "PRIMARY"},
        {"id": 2, "user": "TESTLAB\\jdoe", "pid": 4128, "process": "beacon.exe", "type": "IMPERSONATION"},
    ],
    "demo-pivot-LIN01": [],
}


_BID_CURRENT_USER = {
    "demo-root-WS01": "TESTLAB\\jdoe",
    "demo-pivot-MS01": "NT AUTHORITY\\SYSTEM",
    "demo-pivot-DC01": "TESTLAB\\Administrator",
    "demo-pivot-LIN01": "uid=0(root) gid=0(root) groups=0(root)",
}


def get_uid(bid: str) -> dict[str, Any]:
    user = _BID_CURRENT_USER.get(bid, "DEMO\\user")
    return _ok({"user": user, "data": user, "result": user})


def steal_token(bid: str, pid: int | str) -> dict[str, Any]:
    return _ok({
        "task_id": _dispatch_task(bid, f"steal_token {pid}"),
        "message": f"token from PID {pid} stolen (demo)",
    })


def make_token(bid: str, domain: str, user: str, password: str) -> dict[str, Any]:
    return _ok({
        "task_id": _dispatch_task(bid, f"make_token {domain}\\{user}"),
        "message": f"impersonated {domain}\\{user} (demo)",
    })


def rev2self(bid: str) -> dict[str, Any]:
    return _ok({
        "task_id": _dispatch_task(bid, "rev2self"),
        "message": "reverted to self (demo)",
    })


def token_store_list(bid: str) -> dict[str, Any]:
    tokens = _BID_TOKENS.get(bid, [])
    return _ok({"tokens": tokens, "data": tokens})


def token_store_action(bid: str, action: str, **kwargs) -> dict[str, Any]:
    return _ok({
        "task_id": _dispatch_task(bid, f"tokenstore.{action}"),
        "message": f"tokenstore.{action} accepted (demo)",
        **kwargs,
    })


# ──────────────────────────────────────────────────────────────────────
# Credentials (per-beacon dump)
# ──────────────────────────────────────────────────────────────────────


_HASHDUMP_OUTPUT = (
    "Administrator:500:aad3b435b51404eeaad3b435b51404ee:"
    "31d6cfe0d16ae931b73c59d7e0c089c0:::\n"
    "Guest:501:aad3b435b51404eeaad3b435b51404ee:"
    "31d6cfe0d16ae931b73c59d7e0c089c0:::\n"
    "DefaultAccount:503:aad3b435b51404eeaad3b435b51404ee:"
    "31d6cfe0d16ae931b73c59d7e0c089c0:::\n"
    "krbtgt:502:aad3b435b51404eeaad3b435b51404ee:"
    "fc0f1e5359b2bc7b1d6f7b5a0aaaaaaa:::\n"
    "svc_sql:1108:aad3b435b51404eeaad3b435b51404ee:"
    "b4b9b02e6f09a9bd760f388b67351e2b:::\n"
)


_LOGONPASSWORDS_OUTPUT = (
    "Authentication Id : 0 ; 996 (00000000:000003e4)\n"
    "Session           : Service from 0\n"
    "User Name         : SYSTEM\n"
    "Domain            : NT AUTHORITY\n"
    "Logon Server      : (null)\n"
    "Logon Time        : 2026-05-23 09:00:00\n"
    "SID               : S-1-5-18\n"
    "\tmsv :\n"
    "\t [00000003] Primary\n"
    "\t * Username : svc_sql\n"
    "\t * Domain   : TESTLAB\n"
    "\t * NTLM     : b4b9b02e6f09a9bd760f388b67351e2b\n"
    "\t * SHA1     : 0123456789abcdef0123456789abcdef01234567\n"
    "\ttspkg :\n"
    "\twdigest :\n"
    "\t * Username : svc_sql\n"
    "\t * Domain   : TESTLAB\n"
    "\t * Password : Sup3rS3cr3t!2026\n"
    "\tkerberos :\n"
    "\t * Username : svc_sql\n"
    "\t * Domain   : TESTLAB.LOCAL\n"
    "\t * Password : Sup3rS3cr3t!2026\n"
    "\nAuthentication Id : 0 ; 502341 (00000000:0007a9c5)\n"
    "Session           : Interactive from 1\n"
    "User Name         : Administrator\n"
    "Domain            : TESTLAB\n"
    "\tmsv :\n"
    "\t * Username : Administrator\n"
    "\t * Domain   : TESTLAB\n"
    "\t * NTLM     : 31d6cfe0d16ae931b73c59d7e0c089c0\n"
    "\twdigest :\n"
    "\t * Password : P@ssw0rd-DA-2026\n"
)


def hashdump(bid: str) -> dict[str, Any]:
    task_id = _dispatch_task(bid, "hashdump")
    return _ok({
        "task_id": task_id,
        "output": _HASHDUMP_OUTPUT,
        "result": _HASHDUMP_OUTPUT,
        "data": _HASHDUMP_OUTPUT,
    })


def logonpasswords(bid: str) -> dict[str, Any]:
    task_id = _dispatch_task(bid, "logonpasswords")
    return _ok({
        "task_id": task_id,
        "output": _LOGONPASSWORDS_OUTPUT,
        "result": _LOGONPASSWORDS_OUTPUT,
        "data": _LOGONPASSWORDS_OUTPUT,
    })


def dcsync(bid: str, domain: str, user: str | None) -> dict[str, Any]:
    if not _is_dc(bid):
        # CS lets dcsync run from any beacon with DA, but for demo realism
        # we still succeed even off-DC.
        pass
    output = _HASHDUMP_OUTPUT
    task_id = _dispatch_task(bid, f"dcsync {domain} {user or ''}".strip())
    return _ok({
        "task_id": task_id,
        "output": output,
        "result": output,
        "data": output,
        "domain": domain,
    })


def cred_subcommand(bid: str, name: str, args: str = "") -> dict[str, Any]:
    return _ok({
        "task_id": _dispatch_task(bid, f"mimikatz {name} {args}".strip()),
        "output": f"[+] demo mimikatz '{name}' completed\n",
    })


# ──────────────────────────────────────────────────────────────────────
# Credential vault (server-wide)
# ──────────────────────────────────────────────────────────────────────


_CRED_VAULT: list[dict[str, Any]] = [
    {
        "id": "1",
        "user": "Administrator",
        "password": None,
        "realm": "TESTLAB",
        "host": "tldc01",
        "source": "dcsync",
        "type": "ntlm",
        "hash": "31d6cfe0d16ae931b73c59d7e0c089c0",
        "note": "Domain Admin (DC dcsync)",
        "added_at": _iso(_now() - timedelta(hours=2)),
    },
    {
        "id": "2",
        "user": "svc_sql",
        "password": None,
        "realm": "TESTLAB",
        "host": "tlms01",
        "source": "logonpasswords",
        "type": "ntlm",
        "hash": "b4b9b02e6f09a9bd760f388b67351e2b",
        "note": "service account",
        "added_at": _iso(_now() - timedelta(hours=1, minutes=45)),
    },
    {
        "id": "3",
        "user": "svc_sql",
        "password": "Sup3rS3cr3t!2026",
        "realm": "TESTLAB",
        "host": "tlms01",
        "source": "wdigest",
        "type": "plaintext",
        "note": "from mimikatz wdigest",
        "added_at": _iso(_now() - timedelta(hours=1, minutes=44)),
    },
    {
        "id": "4",
        "user": "jdoe",
        "password": "Summer2026!",
        "realm": "TESTLAB",
        "host": "tlws01",
        "source": "phishing",
        "type": "plaintext",
        "note": "initial access from phishing capture",
        "added_at": _iso(_now() - timedelta(hours=3)),
    },
    {
        "id": "5",
        "user": "Administrator",
        "password": None,
        "realm": "TESTLAB.LOCAL",
        "host": "tldc01",
        "source": "tgt",
        "type": "kerberos",
        "ticket": "doIE7jCC...DEMO-TICKET-PLACEHOLDER...wA=",
        "note": "Golden Ticket (demo placeholder)",
        "added_at": _iso(_now() - timedelta(minutes=18)),
    },
]


def list_vault_credentials() -> dict[str, Any]:
    return _ok({"credentials": list(_CRED_VAULT), "data": list(_CRED_VAULT)})


def delete_vault_credential(cred_id: str) -> dict[str, Any]:
    return _ok({"id": cred_id, "message": "credential deleted (demo no-op)"})


# ──────────────────────────────────────────────────────────────────────
# Jobs
# ──────────────────────────────────────────────────────────────────────


def list_jobs(bid: str) -> dict[str, Any]:
    if bid == "demo-root-WS01":
        jobs = [
            {
                "jid": 1, "id": 1, "pid": 4128,
                "description": "keylogger",
                "command": "keylogger",
                "started_at": _iso(_now() - timedelta(minutes=45)),
                "running": True,
            },
        ]
    else:
        jobs = []
    return _ok({"jobs": jobs, "data": jobs})


def stop_job(jid: str | int) -> dict[str, Any]:
    return _ok({"jid": jid, "message": f"job {jid} stopped (demo)"})


# ──────────────────────────────────────────────────────────────────────
# Downloads
# ──────────────────────────────────────────────────────────────────────


_DOWNLOADS: list[dict[str, Any]] = [
    {
        "id": "dl-001", "bid": "demo-root-WS01", "host": "tlws01",
        "path": "C:\\Users\\jdoe\\Documents\\secrets.txt",
        "name": "secrets.txt",
        "size": 142, "downloaded": 142, "progress": 100,
        "status": "completed",
        "started_at": _iso(_now() - timedelta(minutes=30)),
        "completed_at": _iso(_now() - timedelta(minutes=30)),
    },
    {
        "id": "dl-002", "bid": "demo-root-WS01", "host": "tlws01",
        "path": "C:\\Users\\jdoe\\.ssh\\id_rsa",
        "name": "id_rsa",
        "size": 3247, "downloaded": 3247, "progress": 100,
        "status": "completed",
        "started_at": _iso(_now() - timedelta(minutes=22)),
        "completed_at": _iso(_now() - timedelta(minutes=22)),
    },
    {
        "id": "dl-003", "bid": "demo-pivot-MS01", "host": "tlms01",
        "path": "D:\\backups\\backup.tgz",
        "name": "backup.tgz",
        "size": 50 * 1024 * 1024, "downloaded": 12 * 1024 * 1024,
        "progress": 24,
        "status": "in_progress",
        "started_at": _iso(_now() - timedelta(minutes=4)),
        "completed_at": None,
    },
]


def list_beacon_downloads(bid: str) -> dict[str, Any]:
    rows = [d for d in _DOWNLOADS if d["bid"] == bid]
    return _ok({"downloads": rows, "data": rows})


def list_all_downloads() -> dict[str, Any]:
    return _ok({"downloads": list(_DOWNLOADS), "data": list(_DOWNLOADS)})


def list_active_downloads() -> dict[str, Any]:
    rows = [d for d in _DOWNLOADS if d.get("status") == "in_progress"]
    return _ok({"downloads": rows, "data": rows})


def cancel_download(download_id: str) -> dict[str, Any]:
    return _ok({"id": download_id, "message": f"download {download_id} cancelled (demo)"})


# ──────────────────────────────────────────────────────────────────────
# Screenshots / Keystrokes
# ──────────────────────────────────────────────────────────────────────


_SCREENSHOTS: list[dict[str, Any]] = [
    {
        "id": "ss-001",
        "bid": "demo-root-WS01",
        "host": "tlws01",
        "user": "TESTLAB\\jdoe",
        "captured_at": _iso(_now() - timedelta(minutes=12)),
        "size": 187432,
        "width": 1920, "height": 1080,
    },
    {
        "id": "ss-002",
        "bid": "demo-pivot-DC01",
        "host": "tldc01",
        "user": "TESTLAB\\Administrator",
        "captured_at": _iso(_now() - timedelta(minutes=3)),
        "size": 240118,
        "width": 1920, "height": 1080,
    },
]


def take_screenshot(bid: str) -> dict[str, Any]:
    return _ok({
        "task_id": _dispatch_task(bid, "screenshot"),
        "message": "screenshot queued (demo)",
    })


def start_screenwatch(bid: str) -> dict[str, Any]:
    return _ok({
        "task_id": _dispatch_task(bid, "screenwatch"),
        "message": "screenwatch started (demo)",
    })


def list_beacon_screenshots(bid: str) -> dict[str, Any]:
    # Per-bid is intentionally empty — the gallery aggregates server-wide.
    return _ok({"screenshots": [], "data": []})


def list_all_screenshots() -> dict[str, Any]:
    return _ok({"screenshots": list(_SCREENSHOTS), "data": list(_SCREENSHOTS)})


_KEYSTROKES: list[dict[str, Any]] = [
    {
        "id": "ks-001",
        "bid": "demo-root-WS01",
        "host": "tlws01",
        "user": "TESTLAB\\jdoe",
        "captured_at": _iso(_now() - timedelta(minutes=33)),
        "text": (
            "[CMD] (explorer.exe)\n"
            "TESTLAB\\jdoe<TAB>Summer2026!<ENTER>"
        ),
        "size": 64,
    },
]


def list_all_keystrokes() -> dict[str, Any]:
    return _ok({"keystrokes": list(_KEYSTROKES), "data": list(_KEYSTROKES)})


# ──────────────────────────────────────────────────────────────────────
# Recon (net/portscan)
# ──────────────────────────────────────────────────────────────────────


_NET_FIXTURES = {
    "domain": {"domain": "TESTLAB.local", "forest": "TESTLAB.local",
               "data": "TESTLAB.local"},
    "computers": {
        "data": [
            {"name": "tldc01", "ip": "10.99.50.10", "os": "Windows Server 2022",
             "role": "domain_controller"},
            {"name": "tlms01", "ip": "10.99.50.20", "os": "Windows Server 2022",
             "role": "member_server"},
            {"name": "tlws01", "ip": "10.99.50.30", "os": "Windows 10",
             "role": "workstation"},
            {"name": "tllinux01", "ip": "10.99.50.40", "os": "Ubuntu 22.04",
             "role": "linux_member"},
        ],
    },
    "dclist": {
        "data": [
            {"name": "tldc01.testlab.local", "ip": "10.99.50.10",
             "site": "Default-First-Site-Name"},
        ],
    },
    "users": {
        "data": [
            {"name": "Administrator", "rid": 500, "description": "Built-in admin"},
            {"name": "Guest", "rid": 501, "disabled": True},
            {"name": "krbtgt", "rid": 502, "description": "Key Distribution Center Service"},
            {"name": "jdoe", "rid": 1104, "description": "Jordan Doyle - Finance"},
            {"name": "asmith", "rid": 1105, "description": "Alice Smith - HR"},
            {"name": "bwood", "rid": 1106, "description": "Ben Wood - IT Helpdesk"},
            {"name": "cnguyen", "rid": 1107, "description": "Chau Nguyen - Sales"},
            {"name": "svc_sql", "rid": 1108, "description": "SQL service"},
            {"name": "svc_iis", "rid": 1109, "description": "IIS service"},
            {"name": "svc_backup", "rid": 1110, "description": "Backup service"},
        ],
    },
    "groups": {
        "data": [
            {"name": "Domain Admins", "member_count": 2},
            {"name": "Domain Users", "member_count": 10},
            {"name": "TESTLAB-IT", "member_count": 4},
        ],
    },
    "shares": {
        "data": [
            {"server": "tldc01", "share": "SYSVOL", "type": "Disk",
             "comment": "Logon server share"},
            {"server": "tldc01", "share": "NETLOGON", "type": "Disk",
             "comment": "Logon server share"},
            {"server": "tlms01", "share": "Backups$", "type": "Disk",
             "comment": "Hidden backup share"},
        ],
    },
    "sessions": {
        "data": [
            {"user": "jdoe", "computer": "tlws01", "logon_time": _iso(_now() - timedelta(hours=4))},
            {"user": "Administrator", "computer": "tldc01", "logon_time": _iso(_now() - timedelta(minutes=12))},
        ],
    },
    "logons": {
        "data": [
            {"user": "jdoe", "logon_type": "Interactive",
             "ts": _iso(_now() - timedelta(hours=4))},
            {"user": "svc_sql", "logon_type": "Service",
             "ts": _iso(_now() - timedelta(hours=8))},
        ],
    },
    "trusts": {"data": []},
}


def net_recon(bid: str, subcmd: str) -> dict[str, Any]:
    fixture = _NET_FIXTURES.get(subcmd, {"data": []})
    payload = dict(fixture)
    payload["subcmd"] = subcmd
    payload["task_id"] = _dispatch_task(bid, f"net {subcmd}")
    return _ok(payload)


def portscan(bid: str, targets: str, ports: str, method: str) -> dict[str, Any]:
    results = [
        {"host": "10.99.50.10", "port": 88,  "service": "kerberos", "state": "open"},
        {"host": "10.99.50.10", "port": 389, "service": "ldap",     "state": "open"},
        {"host": "10.99.50.10", "port": 445, "service": "smb",      "state": "open"},
        {"host": "10.99.50.20", "port": 1433, "service": "ms-sql-s", "state": "open"},
        {"host": "10.99.50.30", "port": 3389, "service": "rdp",     "state": "open"},
    ]
    return _ok({
        "task_id": _dispatch_task(bid, f"portscan {targets} {ports} {method}"),
        "targets": targets,
        "ports": ports,
        "method": method,
        "results": results,
        "data": results,
    })


# ──────────────────────────────────────────────────────────────────────
# Pivoting (SOCKS / rportfwd)
# ──────────────────────────────────────────────────────────────────────


_SOCKS: list[dict[str, Any]] = []
_RPORTFWD: list[dict[str, Any]] = []


def socks_start(bid: str, port: int | str, version: str) -> dict[str, Any]:
    entry = {
        "id": f"socks-{int(time.time())}",
        "bid": bid,
        "host": _BID_HOST.get(bid, "unknown"),
        "port": int(port),
        "version": version,
        "status": "active",
        "started_at": _iso(_now()),
    }
    _SOCKS.append(entry)
    return _ok({"socks": entry, "data": entry})


def socks_stop(bid: str) -> dict[str, Any]:
    global _SOCKS
    removed = [s for s in _SOCKS if s["bid"] == bid]
    _SOCKS = [s for s in _SOCKS if s["bid"] != bid]
    return _ok({"removed": removed, "message": f"socks stopped for {bid} (demo)"})


def list_socks() -> dict[str, Any]:
    return _ok({"socks": list(_SOCKS), "data": list(_SOCKS)})


def rportfwd_start(bid: str, bind_port, fwd_host, fwd_port) -> dict[str, Any]:
    entry = {
        "id": f"rpf-{int(time.time())}",
        "bid": bid,
        "host": _BID_HOST.get(bid, "unknown"),
        "bind_port": int(bind_port),
        "forward_host": fwd_host,
        "forward_port": int(fwd_port),
        "status": "active",
        "started_at": _iso(_now()),
    }
    _RPORTFWD.append(entry)
    return _ok({"rportfwd": entry, "data": entry})


def rportfwd_stop(bid: str, bind_port) -> dict[str, Any]:
    global _RPORTFWD
    removed = [r for r in _RPORTFWD
               if r["bid"] == bid and r["bind_port"] == int(bind_port)]
    _RPORTFWD = [r for r in _RPORTFWD
                 if not (r["bid"] == bid and r["bind_port"] == int(bind_port))]
    return _ok({"removed": removed, "message": "rportfwd stopped (demo)"})


def list_rportfwds() -> dict[str, Any]:
    return _ok({"rportfwds": list(_RPORTFWD), "data": list(_RPORTFWD)})


# ──────────────────────────────────────────────────────────────────────
# Config writes
# ──────────────────────────────────────────────────────────────────────


def config_write(bid: str, knob: str, value: Any = None) -> dict[str, Any]:
    return _ok({
        "task_id": _dispatch_task(bid, f"config.{knob}={value}"),
        "knob": knob,
        "value": value,
        "message": f"config.{knob} accepted (demo)",
    })


# ──────────────────────────────────────────────────────────────────────
# Beacon management
# ──────────────────────────────────────────────────────────────────────


def beacon_management(bid: str, action: str, **kwargs) -> dict[str, Any]:
    return _ok({
        "task_id": _dispatch_task(bid, action),
        "action": action,
        "message": f"{action} accepted (demo no-op)",
        **kwargs,
    })


def beacon_info(bid: str) -> dict[str, Any]:
    host = _BID_HOST.get(bid, "demo-host")
    info = {
        "bid": bid,
        "computer": host,
        "user": _BID_CURRENT_USER.get(bid, "demo\\user"),
        "process": "beacon.exe" if _is_windows(bid) else "/usr/bin/python3",
        "pid": 4128,
        "ppid": 1024,
        "arch": "x64",
        "os": "Windows 10 Pro" if _is_windows(bid) else "Linux 22.04 (Ubuntu)",
        "sleep": 60,
        "jitter": 15,
        "last_checkin": _iso(_now() - timedelta(seconds=8)),
        "first_seen": _iso(_now() - timedelta(hours=3)),
        "internal_ip": {
            "demo-root-WS01": "10.99.50.30",
            "demo-pivot-MS01": "10.99.50.20",
            "demo-pivot-DC01": "10.99.50.10",
            "demo-pivot-LIN01": "10.99.50.40",
        }.get(bid, "10.99.50.99"),
        "memory": {
            "allocated_bytes": 4 * 1024 * 1024,
            "stage_size": 287232,
            "module_count": 47,
        },
    }
    return _ok({"info": info, "data": info, "beacon": info})


# ──────────────────────────────────────────────────────────────────────
# C2 hosts
# ──────────────────────────────────────────────────────────────────────


_C2_HOSTS: dict[str, list[dict[str, Any]]] = {}


def _default_c2_hosts() -> list[dict[str, Any]]:
    return [
        {
            "hostname": "https-cdn.demo-engagement.example.com",
            "url": "https://https-cdn.demo-engagement.example.com/api/v1/",
            "status": "active",
            "primary": True,
            "added_at": _iso(_now() - timedelta(hours=4)),
        },
        {
            "hostname": "https-backup.demo-engagement.example.com",
            "url": "https://https-backup.demo-engagement.example.com/api/v1/",
            "status": "standby",
            "primary": False,
            "added_at": _iso(_now() - timedelta(hours=4)),
        },
    ]


def c2_hosts_for(bid: str) -> list[dict[str, Any]]:
    return _C2_HOSTS.setdefault(bid, _default_c2_hosts())


def list_c2_hosts(bid: str) -> dict[str, Any]:
    rows = c2_hosts_for(bid)
    return _ok({"hosts": list(rows), "data": list(rows)})


def add_c2_host(bid: str, infos: list[dict[str, Any]]) -> dict[str, Any]:
    rows = c2_hosts_for(bid)
    added = []
    for info in infos or []:
        entry = {
            "hostname": info.get("hostname") or info.get("host") or "demo-host",
            "url": info.get("url", "https://demo-host/api/v1/"),
            "status": "active",
            "primary": False,
            "added_at": _iso(_now()),
        }
        rows.append(entry)
        added.append(entry)
    return _ok({"added": added, "hosts": list(rows)})


def remove_c2_host(bid: str, hostnames: list[str]) -> dict[str, Any]:
    rows = c2_hosts_for(bid)
    targets = set(hostnames or [])
    keep = [h for h in rows if h["hostname"] not in targets]
    _C2_HOSTS[bid] = keep
    return _ok({"removed": list(targets), "hosts": list(keep)})


def c2_host_action(bid: str, action: str, **kwargs) -> dict[str, Any]:
    return _ok({
        "task_id": _dispatch_task(bid, f"c2.{action}"),
        "action": action,
        "message": f"c2.{action} accepted (demo)",
        **kwargs,
    })


# ──────────────────────────────────────────────────────────────────────
# Server metadata
# ──────────────────────────────────────────────────────────────────────


def server_info() -> dict[str, Any]:
    info = {
        "version": "4.10.1-demo",
        "license": "demo",
        "listener_port": 50050,
        "host": "demo-teamserver",
        "started_at": _iso(_now() - timedelta(days=2)),
        "uptime_seconds": 2 * 86400,
        "watermark": "DEMO-WATERMARK-0000-0000-0000-0000",
    }
    return _ok({"info": info, "data": info})


def server_killdate() -> dict[str, Any]:
    killdate = _now() + timedelta(days=30)
    return _ok({
        "killdate": killdate.strftime("%Y-%m-%d"),
        "epoch": int(killdate.timestamp()),
        "data": killdate.strftime("%Y-%m-%d"),
    })


def server_profile() -> dict[str, Any]:
    profile = (
        "# DEMO MALLEABLE PROFILE — synthetic excerpt\n"
        "set sample_name \"demo-jquery\";\n"
        "set sleeptime \"60000\";\n"
        "set jitter    \"15\";\n"
        "set useragent \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Demo/1.0\";\n"
        "\n"
        "http-get {\n"
        "    set uri \"/js/jquery-3.6.0.min.js\";\n"
        "    client { header \"Host\" \"demo-engagement.example.com\"; }\n"
        "}\n"
    )
    return _ok({"profile": profile, "data": profile, "result": profile})


# ──────────────────────────────────────────────────────────────────────
# Payloads (quick generation)
# ──────────────────────────────────────────────────────────────────────


_GENERATED_PAYLOADS: dict[str, bytes] = {}

_DEMO_PAYLOAD_BYTES = b"DEMO PAYLOAD - NOT EXECUTABLE\n"  # 30 bytes; pad to 32
_DEMO_PAYLOAD_BYTES = _DEMO_PAYLOAD_BYTES + b"\x00\x00"  # 32 bytes


def generate_payload(kind: str, config: dict[str, Any]) -> dict[str, Any]:
    fid = uuid.uuid4().hex[:8]
    ext = "bin" if config.get("output") not in ("exe", "dll") else config["output"]
    filename = f"demo-payload-{kind}-{fid}.{ext}"
    _GENERATED_PAYLOADS[filename] = _DEMO_PAYLOAD_BYTES
    return _ok({
        "filename": filename,
        "size": 248320,
        "size_bytes": 248320,
        "kind": kind,
        # Default to a real demo listener (see demo_beacon_ops.DEMO_LISTENERS).
        "listener": config.get("listenerName", "demo-https-cdn"),
        "message": "payload generated (demo)",
    })


def get_payload_bytes(filename: str) -> bytes | None:
    if filename in _GENERATED_PAYLOADS:
        return _GENERATED_PAYLOADS[filename]
    if filename.startswith("demo-"):
        return _DEMO_PAYLOAD_BYTES
    return None


# ──────────────────────────────────────────────────────────────────────
# BOF / spawn / inject
# ──────────────────────────────────────────────────────────────────────


def bof_execute(bid: str, bof: str, entrypoint: str, method: str) -> dict[str, Any]:
    return _ok({
        "task_id": _dispatch_task(bid, f"bof {bof}!{entrypoint} ({method})"),
        "bof": bof,
        "entrypoint": entrypoint,
        "method": method,
        "message": "BOF queued (demo)",
    })


def spawn_or_inject(bid: str, variant: str, pid: int | str | None = None,
                    arch: str = "x64") -> dict[str, Any]:
    cmd = f"{variant} pid={pid} arch={arch}" if pid else f"{variant} arch={arch}"
    return _ok({
        "task_id": _dispatch_task(bid, cmd),
        "variant": variant,
        "pid": pid,
        "arch": arch,
        "message": f"{variant} queued (demo)",
    })
