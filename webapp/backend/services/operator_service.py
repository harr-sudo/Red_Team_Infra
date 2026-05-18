"""Operator profile store + lookup.

Profile data lives at ~/.dashboard/operators.json — a simple list of
{id, display, color, created}. No password / session — identity is
asserted by the unsigned cookie `dashboard_operator=<id>` set by the
operator from the header chip. Trust boundary is AWS IAM + SSH access
upstream of the dashboard.
"""
import json
import os
import pwd
import threading
from datetime import datetime
from pathlib import Path

_STORE_PATH = Path.home() / ".dashboard" / "operators.json"
_LOCK = threading.RLock()

DEFAULT_COLORS = ["#a31621", "#3b82f6", "#0d9488", "#7c3aed", "#ea580c", "#65a30d"]


def _ensure_store():
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _STORE_PATH.exists():
        # Seed with the SSH user as the default operator
        try:
            user = pwd.getpwuid(os.getuid()).pw_name
        except Exception:
            user = "operator"
        seed = {
            "operators": [{
                "id": user,
                "display": user.capitalize(),
                "color": DEFAULT_COLORS[0],
                "created": datetime.utcnow().isoformat() + "Z",
            }],
            "default": user,
        }
        _STORE_PATH.write_text(json.dumps(seed, indent=2))


def load():
    with _LOCK:
        _ensure_store()
        return json.loads(_STORE_PATH.read_text())


def save(data):
    with _LOCK:
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STORE_PATH.write_text(json.dumps(data, indent=2))


def list_operators():
    return load()["operators"]


def get(op_id):
    return next((o for o in list_operators() if o["id"] == op_id), None)


def add(op_id, display, color):
    """Add a new operator. Returns the created entry."""
    op_id = (op_id or "").strip().lower()
    if not op_id or not op_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("operator id must be alphanumeric with optional -/_ separators")
    with _LOCK:
        data = load()
        if any(o["id"] == op_id for o in data["operators"]):
            raise ValueError(f"operator '{op_id}' already exists")
        if len(data["operators"]) >= 32:
            raise ValueError("too many operators (max 32)")
        entry = {
            "id": op_id,
            "display": display or op_id.capitalize(),
            "color": color or DEFAULT_COLORS[len(data["operators"]) % len(DEFAULT_COLORS)],
            "created": datetime.utcnow().isoformat() + "Z",
        }
        data["operators"].append(entry)
        save(data)
        return entry


def remove(op_id):
    with _LOCK:
        data = load()
        before = len(data["operators"])
        data["operators"] = [o for o in data["operators"] if o["id"] != op_id]
        if len(data["operators"]) == before:
            raise ValueError(f"operator '{op_id}' not found")
        if len(data["operators"]) == 0:
            raise ValueError("cannot remove the last operator")
        if data.get("default") == op_id:
            data["default"] = data["operators"][0]["id"]
        save(data)


def get_default():
    data = load()
    default_id = data.get("default")
    if default_id:
        return default_id
    ops = data.get("operators") or []
    return ops[0]["id"] if ops else None


def resolve_from_request(request):
    """Read the dashboard_operator cookie, fall back to default. Returns the
    full operator dict or a synthesized 'unknown' record (never None)."""
    cookie_id = request.cookies.get("dashboard_operator")
    if cookie_id:
        op = get(cookie_id)
        if op:
            return op
    default_id = get_default()
    if default_id:
        op = get(default_id)
        if op:
            return op
    return {"id": "unknown", "display": "Unknown", "color": "#666666", "created": None}
