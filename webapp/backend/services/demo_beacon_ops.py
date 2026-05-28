"""Demo-mode beacon operations: canned responses for the synthetic
``demo`` deployment.

When the active deployment's project_name is ``demo``, the beacon route
handlers short-circuit the live Cobalt Strike REST API and dispatch
through this module instead. Goal: a Cobalt Strike-style operator
experience (console exec → task polling, listener CRUD, sleep config)
that resolves end-to-end against synthetic data, so the operator can
showcase the dashboard without a real CS REST tunnel.

Design contract (mirrors demo_data_service.py):
  - All identifiers obviously synthetic (TESTLAB, tlws01, demo-task-*).
  - State is in-memory only — restart Flask to reset.
  - Output formats are CS-style realistic but not exhaustive: the dashboard
    "looks alive" without faking the entire CS feature set.
  - Detection: caller checks bid.startswith("demo-") OR project == "demo".

Coupled to: demo_data_service.beacon_list() (canonical demo beacons).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from webapp.backend.services import demo_data_service


# ──────────────────────────────────────────────────────────────────────
# In-memory state
# ──────────────────────────────────────────────────────────────────────

# task_id → task dict
_TASKS: dict[str, dict[str, Any]] = {}

# bid → {"sleep": int, "jitter": int} — override layer for set_demo_sleep
# (beacon_list() is regenerated on each call so we can't mutate in place).
_SLEEP_OVERRIDES: dict[str, dict[str, int]] = {}


# ──────────────────────────────────────────────────────────────────────
# Demo listeners (3 entries — shape matches CS REST API ListenerDto)
# ──────────────────────────────────────────────────────────────────────

DEMO_LISTENERS: list[dict[str, Any]] = [
    {
        "id": "demo-https-cdn",
        "name": "demo-https-cdn",
        "payload": "windows/beacon_https/reverse_https",
        "host": "cdn.example-demo.com",
        "hosts": ["cdn.example-demo.com", "edge.example-demo.com"],
        "port": 443,
        "httpPort": 443,
        "profile": "default-cdn-malleable.profile",
        "enabled": True,
        "color": "RED",
        "created_at": "2026-05-20T12:14:00Z",
    },
    {
        "id": "demo-http",
        "name": "demo-http",
        "payload": "windows/beacon_http/reverse_http",
        "host": "203.0.113.50",
        "hosts": ["203.0.113.50"],
        "port": 80,
        "httpPort": 80,
        "profile": "default.profile",
        "enabled": True,
        "color": "DEFAULT",
        "created_at": "2026-05-20T12:15:00Z",
    },
    {
        "id": "smb-pivot",
        "name": "smb-pivot",
        "payload": "windows/beacon_bind_pipe",
        "host": "",
        "hosts": [],
        "port": 0,
        "pipename": "msagent_##",
        "profile": None,
        "enabled": True,
        "color": "BLUE",
        "created_at": "2026-05-20T12:16:00Z",
    },
]


def list_demo_listeners() -> dict[str, Any]:
    return {"success": True, "listeners": DEMO_LISTENERS, "is_demo": True}


def get_demo_listener(lid: str) -> dict[str, Any]:
    for l in DEMO_LISTENERS:
        if l["id"] == lid or l["name"] == lid:
            return {"success": True, "listener": l, "is_demo": True}
    return {"success": False, "error": f"demo listener '{lid}' not found", "is_demo": True}


def create_demo_listener(listener_type: str, config: dict[str, Any]) -> dict[str, Any]:
    """Demo accept (no-op persistence). Returns a fake listener record so
    the frontend's createListener flow lights up green."""
    name = (config or {}).get("name") or f"demo-{listener_type}-{uuid.uuid4().hex[:6]}"
    return {
        "success": True,
        "is_demo": True,
        "listener": {
            "id": name,
            "name": name,
            "payload": f"windows/beacon_{listener_type}/reverse_{listener_type}",
            "host": (config or {}).get("host", ""),
            "port": (config or {}).get("httpPort") or (config or {}).get("port") or 0,
            "enabled": True,
        },
        "message": f"demo: listener '{name}' accepted (not persisted)",
    }


def update_demo_listener(lid: str, config: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "is_demo": True,
        "message": f"demo: listener '{lid}' update accepted (not persisted)",
    }


def delete_demo_listener(lid: str) -> dict[str, Any]:
    return {
        "success": True,
        "is_demo": True,
        "message": f"demo: listener '{lid}' delete accepted (not persisted)",
    }


# ──────────────────────────────────────────────────────────────────────
# Command dispatcher — canned realistic-looking outputs
# ──────────────────────────────────────────────────────────────────────

def _beacon_meta(bid: str) -> dict[str, Any]:
    """Resolve the canonical demo beacon record for templating output."""
    detail = demo_data_service.beacon_detail(bid) or {}
    return {
        "user": detail.get("user", "TESTLAB\\jdoe"),
        "computer": detail.get("computer", "tlws01"),
        "os": detail.get("os", "Windows"),
        "internal": detail.get("internal", "10.99.50.30"),
        "pid": detail.get("pid", 4128),
        "is_linux": "linux" in (detail.get("os") or "").lower(),
    }


def _shell_handler(meta: dict[str, Any], args: str) -> str:
    """Mimic ``shell <cmd>`` output for the common cases."""
    parts = args.strip().split()
    if not parts:
        return "[-] shell: no command provided\n"
    cmd = parts[0].lower()
    if cmd in ("whoami",):
        return f"{meta['user']}\n"
    if cmd in ("hostname",):
        return f"{meta['computer']}\n"
    if cmd in ("ipconfig",):
        return (
            "Windows IP Configuration\n\n"
            "Ethernet adapter Ethernet0:\n"
            "   Connection-specific DNS Suffix . : testlab.local\n"
            f"   IPv4 Address. . . . . . . . . . : {meta['internal']}\n"
            "   Subnet Mask . . . . . . . . . . : 255.255.255.0\n"
            "   Default Gateway . . . . . . . . : 10.99.50.1\n"
        )
    if cmd in ("ifconfig", "ip"):
        return (
            "eth0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500\n"
            f"        inet {meta['internal']}  netmask 255.255.255.0  broadcast 10.99.50.255\n"
            "        ether 02:42:0a:63:32:1e  txqueuelen 1000  (Ethernet)\n"
            "        RX packets 18234  bytes 9128732 (8.7 MiB)\n"
            "        TX packets 12041  bytes 3417823 (3.2 MiB)\n"
        )
    if cmd in ("dir",):
        return (
            f" Volume in drive C has no label.\n"
            f" Directory of C:\\Users\\{meta['user'].split(chr(92))[-1]}\n\n"
            "05/20/2026  10:14 AM    <DIR>          .\n"
            "05/20/2026  10:14 AM    <DIR>          ..\n"
            "05/20/2026  10:14 AM    <DIR>          Desktop\n"
            "05/20/2026  10:14 AM    <DIR>          Documents\n"
            "05/20/2026  10:14 AM    <DIR>          Downloads\n"
            "               0 File(s)              0 bytes\n"
        )
    return f"[+] shell> {args}\n[*] (demo) exit code 0\n"


def _ls_output(meta: dict[str, Any], args: str) -> str:
    if meta["is_linux"]:
        return (
            "total 32\n"
            "drwxr-xr-x  6 root root  4096 May 20 10:14 .\n"
            "drwxr-xr-x 22 root root  4096 May 19 14:02 ..\n"
            "-rw-------  1 root root  1241 May 20 08:11 .bash_history\n"
            "drwx------  3 root root  4096 May 20 10:14 .cache\n"
            "drwxr-xr-x  3 root root  4096 May 20 09:55 .config\n"
            "drwx------  2 root root  4096 May 20 10:12 .ssh\n"
            "-rw-r--r--  1 root root   807 May 19 14:02 .profile\n"
            "-rwxr-xr-x  1 root root  8392 May 20 10:14 beacon\n"
        )
    user = meta["user"].split("\\")[-1]
    return (
        f" Volume in drive C has no label.\n"
        f" Directory of C:\\Users\\{user}\n\n"
        "05/20/2026  10:14 AM    <DIR>          .\n"
        "05/20/2026  10:14 AM    <DIR>          ..\n"
        "05/20/2026  10:14 AM    <DIR>          Desktop\n"
        "05/20/2026  10:14 AM    <DIR>          Documents\n"
        "05/20/2026  10:14 AM    <DIR>          Downloads\n"
        "05/20/2026  10:14 AM    <DIR>          AppData\n"
        "05/19/2026  09:01 AM             1,217 NTUSER.DAT\n"
        "               1 File(s)          1,217 bytes\n"
        "               4 Dir(s)  42,108,239,872 bytes free\n"
    )


def _ps_output(meta: dict[str, Any]) -> str:
    if meta["is_linux"]:
        return (
            "  PID  PPID USER     COMMAND\n"
            "    1     0 root     /sbin/init\n"
            "  102     1 root     /lib/systemd/systemd-journald\n"
            "  118     1 root     /lib/systemd/systemd-udevd\n"
            "  411     1 systemd  /lib/systemd/systemd --user\n"
            "  502     1 root     /usr/sbin/sshd -D\n"
            "  611     1 root     /usr/sbin/cron -f\n"
            "  742   502 root     sshd: root@pts/0\n"
            "  802   742 root     -bash\n"
            f" 1932     1 root     {meta.get('os','/usr/bin/python3')}\n"
            " 2017  1932 root     ps -ef\n"
        )
    return (
        " PID   PPID  Name              Arch  Session  User\n"
        " ---   ----  ----              ----  -------  ----\n"
        "   4     0   System            x64   0        NT AUTHORITY\\SYSTEM\n"
        " 348     4   smss.exe          x64   0        NT AUTHORITY\\SYSTEM\n"
        " 444   436   csrss.exe         x64   0        NT AUTHORITY\\SYSTEM\n"
        " 488   436   wininit.exe       x64   0        NT AUTHORITY\\SYSTEM\n"
        " 612   488   services.exe      x64   0        NT AUTHORITY\\SYSTEM\n"
        " 620   488   lsass.exe         x64   0        NT AUTHORITY\\SYSTEM\n"
        " 720   612   svchost.exe       x64   0        NT AUTHORITY\\SYSTEM\n"
        " 920   612   svchost.exe       x64   0        NT AUTHORITY\\NETWORK SERVICE\n"
        "1024   612   svchost.exe       x64   0        NT AUTHORITY\\LOCAL SERVICE\n"
        "1208   612   spoolsv.exe       x64   0        NT AUTHORITY\\SYSTEM\n"
        "2104   612   MsMpEng.exe       x64   0        NT AUTHORITY\\SYSTEM\n"
        "2812  1024   sihost.exe        x64   1        " + meta["user"] + "\n"
        "3120  2812   explorer.exe      x64   1        " + meta["user"] + "\n"
        f"{meta['pid']:5d}  1024   beacon.exe        x64   1        " + meta["user"] + "\n"
        "4288  3120   chrome.exe        x64   1        " + meta["user"] + "\n"
        "4400  4288   chrome.exe        x64   1        " + meta["user"] + "\n"
        "5012  3120   OUTLOOK.EXE       x64   1        " + meta["user"] + "\n"
    )


def _hashdump_output() -> str:
    return (
        "Administrator:500:aad3b435b51404eeaad3b435b51404ee:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:::\n"
        "Guest:501:aad3b435b51404eeaad3b435b51404ee:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb:::\n"
        "krbtgt:502:aad3b435b51404eeaad3b435b51404ee:cccccccccccccccccccccccccccccccc:::\n"
        "jdoe:1104:aad3b435b51404eeaad3b435b51404ee:dddddddddddddddddddddddddddddddd:::\n"
        "svc_sql:1108:aad3b435b51404eeaad3b435b51404ee:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee:::\n"
        "svc_web:1112:aad3b435b51404eeaad3b435b51404ee:ffffffffffffffffffffffffffffffff:::\n"
        "asmith:1116:aad3b435b51404eeaad3b435b51404ee:11111111111111111111111111111111:::\n"
    )


def _mimikatz_output() -> str:
    return (
        "  .#####.   mimikatz 2.2.0 (x64) #19041 (demo build)\n"
        " .## ^ ##.  \"A La Vie, A L'Amour\" - (oe.eo)\n"
        " ## / \\ ##  /*** Benjamin DELPY `gentilkiwi` ***/\n"
        " ## \\ / ##\n"
        " '## v ##'\n"
        "  '#####'\n\n"
        "Authentication Id : 0 ; 145821 (00000000:000239dd)\n"
        "Session           : Interactive from 1\n"
        "User Name         : jdoe\n"
        "Domain            : TESTLAB\n"
        "Logon Server      : TLDC01\n"
        "Logon Time        : 5/20/2026 10:14:02 AM\n"
        "SID               : S-1-5-21-1111111111-2222222222-3333333333-1104\n"
        "        msv :\n"
        "         [00000003] Primary\n"
        "          * Username : jdoe\n"
        "          * Domain   : TESTLAB\n"
        "          * NTLM     : dddddddddddddddddddddddddddddddd\n"
        "          * SHA1     : 1111111111111111111111111111111111111111\n"
        "        tspkg :\n"
        "        wdigest :\n"
        "          * Username : jdoe\n"
        "          * Domain   : TESTLAB\n"
        "          * Password : (null)\n"
        "        kerberos :\n"
        "          * Username : jdoe\n"
        "          * Domain   : TESTLAB.LOCAL\n"
        "          * Password : DemoPassword123!\n"
    )


def _whoami_priv_output() -> str:
    return (
        "PRIVILEGES INFORMATION\n"
        "----------------------\n\n"
        "Privilege Name                Description                          State\n"
        "============================= ==================================== =======\n"
        "SeShutdownPrivilege           Shut down the system                 Disabled\n"
        "SeChangeNotifyPrivilege       Bypass traverse checking             Enabled\n"
        "SeUndockPrivilege             Remove computer from docking station Disabled\n"
        "SeIncreaseWorkingSetPrivilege Increase a process working set       Disabled\n"
        "SeTimeZonePrivilege           Change the time zone                 Disabled\n"
    )


def _net_user_output() -> str:
    return (
        "User accounts for \\\\TLDC01\n\n"
        "-------------------------------------------------------------------------------\n"
        "Administrator            asmith                   bwhite\n"
        "DefaultAccount           Guest                    jdoe\n"
        "krbtgt                   svc_sql                  svc_web\n"
        "svc_backup\n"
        "The command completed successfully.\n"
    )


def _help_output() -> str:
    return (
        "Beacon Commands\n"
        "===============\n"
        "  shell <cmd>           run command via cmd.exe\n"
        "  run <cmd>             run command without cmd.exe\n"
        "  pwd / cd / ls         filesystem nav\n"
        "  ps                    list processes\n"
        "  getuid / whoami /priv current token / privileges\n"
        "  sleep <s> <jitter>    change check-in time\n"
        "  download / upload     file ops\n"
        "  screenshot            capture screen\n"
        "  keylogger             start keylogger\n"
        "  inject <pid> <lst>    inject into PID via listener\n"
        "  spawn <listener>      spawn new beacon\n"
        "  jump <proto> <tgt>    lateral movement\n"
        "  make_token user pass  craft user token\n"
        "  rev2self              drop impersonation\n"
        "  net domain / net user enumerate AD\n"
        "  mimikatz / hashdump   credential dumping\n"
        "  help                  this message\n"
    )


def _dispatch_output(bid: str, command: str) -> str:
    """Map a command string to canned realistic output."""
    meta = _beacon_meta(bid)
    cmd = command.strip()
    if not cmd:
        return "[-] empty command\n"
    parts = cmd.split(maxsplit=1)
    head = parts[0].lower()
    tail = parts[1] if len(parts) > 1 else ""

    if head in ("shell", "run"):
        return _shell_handler(meta, tail)
    if head == "ls":
        return _ls_output(meta, tail)
    if head == "ps":
        return _ps_output(meta)
    if head == "getuid":
        return f"Current Token: {meta['user']} (Domain User)\n"
    if head == "sleep":
        bits = tail.split()
        sec = bits[0] if bits else "60"
        jit = bits[1] if len(bits) > 1 else "0"
        return f"Tasked beacon to sleep for {sec}s ± {jit}%\n"
    if head == "pwd":
        return ("/root\n" if meta["is_linux"] else f"C:\\Users\\{meta['user'].split(chr(92))[-1]}\n")
    if head == "cd":
        return f"Changed directory to {tail or '.'}\n"
    if head == "whoami":
        if "/priv" in tail or tail.strip() == "/priv":
            return _whoami_priv_output()
        return f"{meta['user']}\n"
    if head == "net":
        sub = tail.strip().lower()
        if sub.startswith("domain"):
            return "TESTLAB.local\n"
        if sub.startswith("user"):
            return _net_user_output()
        return f"[+] net> {tail}\n"
    if head == "hashdump":
        return _hashdump_output()
    if head in ("mimikatz", "logonpasswords") or "logonpasswords" in cmd.lower():
        return _mimikatz_output()
    if head == "download":
        return f"Started download of {tail or '<path>'} ({bid})\n"
    if head == "upload":
        return f"Uploaded {tail or '<path>'}\n"
    if head == "screenshot":
        return "Tasked beacon to take screenshot\n[*] received screenshot (104,832 bytes)\n"
    if head == "keylogger":
        return "Tasked beacon to start keylogger\n"
    if head == "inject":
        bits = tail.split()
        pid = bits[0] if bits else "<pid>"
        lst = bits[1] if len(bits) > 1 else "<listener>"
        return f"Tasked beacon to inject into {pid} via {lst}\n"
    if head == "spawn":
        return f"Tasked beacon to spawn beacon via {tail or '<listener>'}\n"
    if head == "jump":
        bits = tail.split()
        proto = bits[0] if bits else "<proto>"
        tgt = bits[1] if len(bits) > 1 else "<target>"
        return f"Tasked beacon to jump to {tgt} via {proto}\n"
    if head == "make_token":
        bits = tail.split()
        user = bits[0] if bits else "<user>"
        return f"Tasked beacon to create token for {user}\n"
    if head == "rev2self":
        return "Tasked beacon to revert to self\n"
    if head == "help":
        return _help_output()
    # Generic fallback — every command yields *something* so the
    # dashboard never shows a blank task result in demo mode.
    return f"[+] Tasked beacon to run: {cmd}\n[*] beacon> (demo) acknowledged\n"


def _iso_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dispatch_demo_command(bid: str, command: str) -> dict[str, Any]:
    """Create + complete a fake task for the given command. Returns the
    standard CS AsyncCommandResponse envelope so the frontend's
    task-polling flow (POST → taskId → GET /task/<id>) lights up."""
    task_id = f"demo-task-{uuid.uuid4().hex[:8]}"
    now_iso = _iso_utc()
    output = _dispatch_output(bid, command)
    ack = f"[*] Tasked beacon to {command.strip()}"
    task = {
        "task_id": task_id,
        "taskId": task_id,
        "bid": bid,
        "command": command,
        "status": "COMPLETED",
        "acknowledgements": [ack],
        "taskAcknowledgements": [ack],
        "result": output,
        "output": output,
        "issued_at": now_iso,
        "completed_at": now_iso,
        "is_demo": True,
    }
    _TASKS[task_id] = task
    return {"success": True, "taskId": task_id, "is_demo": True}


def get_demo_task(task_id: str) -> Optional[dict[str, Any]]:
    """Retrieve a previously dispatched demo task. Returns an envelope
    matching beacon_service.get_task_detail() shape."""
    task = _TASKS.get(task_id)
    if task is None:
        return None
    return {
        "success": True,
        "is_demo": True,
        "task": task,
        # Mirror common fields at the top level for any callers that
        # don't unwrap `task` (matches the real beacon_service envelope).
        "taskId": task["task_id"],
        "status": task["status"],
        "result": task["result"],
        "output": task["output"],
        "acknowledgements": task["acknowledgements"],
        "command": task["command"],
        "issued_at": task["issued_at"],
        "completed_at": task["completed_at"],
    }


def get_demo_tasks_for_beacon(bid: str) -> dict[str, Any]:
    """Return up to 50 tasks for the given bid, newest first."""
    matched = [t for t in _TASKS.values() if t.get("bid") == bid]
    matched.sort(key=lambda t: t.get("issued_at", ""), reverse=True)
    matched = matched[:50]
    return {
        "success": True,
        "is_demo": True,
        "bid": bid,
        "tasks": matched,
        "count": len(matched),
    }


# ──────────────────────────────────────────────────────────────────────
# Sleep override
# ──────────────────────────────────────────────────────────────────────

def set_demo_sleep(bid: str, sleep_seconds: int, jitter_pct: int) -> dict[str, Any]:
    """Override the sleep/jitter for a demo beacon. beacon_list() is
    regenerated on every call, so we keep an in-memory override map
    that the beacon_list patch (if added) can consult. For now this
    just records the change and emits a confirmation task."""
    _SLEEP_OVERRIDES[bid] = {"sleep": int(sleep_seconds), "jitter": int(jitter_pct)}
    # Also drop a task so the activity feed reflects the change.
    dispatch_demo_command(bid, f"sleep {sleep_seconds} {jitter_pct}")
    return {
        "success": True,
        "is_demo": True,
        "bid": bid,
        "sleep": int(sleep_seconds),
        "jitter": int(jitter_pct),
        "message": f"demo: sleep set to {sleep_seconds}s ± {jitter_pct}%",
    }


def get_sleep_override(bid: str) -> Optional[dict[str, int]]:
    return _SLEEP_OVERRIDES.get(bid)
