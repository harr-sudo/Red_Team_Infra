"""Command palette index + selection tracking.

The palette indexes EVERYTHING useful in the dashboard for fuzzy search:
routes, actions, deployments, beacons, sessions, operators, audit
entries, bolt-on vulnerabilities, and Settings sections.

Endpoints
=========
GET  /api/palette/index   Full indexable surface as a flat list + the
                          current operator's recently-used MRU.
POST /api/palette/select  Records a selection in the per-operator MRU
                          (last 20, dedupe). Audits as ``palette.select``.

Design notes
============
- The index is rebuilt on every GET. It's cheap (~hundreds of items)
  and operators expect it to be live (new deployments / new operators
  should appear without a server restart). If this ever shows up in a
  flame graph we can memoize with a TTL.
- Recently-used is per-operator: ``~/.dashboard/palette_recent_<op>.json``.
  Stored separately from operators.json so palette churn doesn't
  rewrite the operator store on every selection.
- Item kinds and shapes are documented in the response example in
  v3.0.0 plan §1. Keep field names stable — the JS dispatcher
  switches on ``target.action`` / ``target.page`` keys directly.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Blueprint, g, jsonify, request

from webapp.backend.services import audit_service, operator_service

_log = logging.getLogger(__name__)

bp = Blueprint("palette", __name__, url_prefix="/api/palette")


# ─── Constants ──────────────────────────────────────────────────────────────

_MAX_ITEMS = 1000            # safety cap for v1
_MAX_RECENT = 20             # MRU size per operator
_RECENT_DIR = Path.home() / ".dashboard"
_RECENT_LOCK = threading.RLock()


# ─── Static route + action definitions ──────────────────────────────────────
# These are stable across operators / sessions. Listed in display order;
# the JS layer further reorders by recency + fuzzy-match score.
#
# Field shape:
#   id       — globally unique stable string ("route:dashboard", etc.)
#   kind     — bucketing class (route, action, deployment, …)
#   label    — what the operator sees as the primary line
#   subtitle — secondary line (context, location, last-touched)
#   keywords — additional fuzzy-match alternates (synonyms, abbrevs)
#   target   — dispatch directive consumed by APP.palette._dispatchTarget

_ROUTES: list[dict[str, Any]] = [
    # Primary pages
    {"id": "route:dashboard", "kind": "route", "label": "Dashboard",
     "subtitle": "Landing page · live deployments + activity",
     "keywords": ["home", "overview", "launchpad"],
     "target": {"page": "dashboard"}},

    # Deployments sub-pills
    {"id": "route:dep.configure", "kind": "route", "label": "Configure",
     "subtitle": "Deployments · Configure",
     "keywords": ["edit", "form", "tfvars", "configuration"],
     "target": {"page": "deployments-tab", "subpill": "configure"}},
    {"id": "route:dep.deploy", "kind": "route", "label": "Deploy",
     "subtitle": "Deployments · Deploy",
     "keywords": ["apply", "provision", "terraform"],
     "target": {"page": "deployments-tab", "subpill": "deploy"}},
    {"id": "route:dep.manage", "kind": "route", "label": "Manage",
     "subtitle": "Deployments · Manage",
     "keywords": ["hosts", "outputs", "ssh", "rdp", "connection"],
     "target": {"page": "deployments-tab", "subpill": "manage"}},
    {"id": "route:dep.cleanup", "kind": "route", "label": "Cleanup",
     "subtitle": "Deployments · Cleanup",
     "keywords": ["destroy", "purge", "orphan", "leftover", "tear down"],
     "target": {"page": "deployments-tab", "subpill": "cleanup"}},

    # Operations sub-pills
    {"id": "route:ops.beacons", "kind": "route", "label": "Beacons",
     "subtitle": "Operations · Beacons",
     "keywords": ["cs", "cobalt", "implant", "agent", "sessions"],
     "target": {"page": "operations-tab", "subpill": "beacons"}},
    {"id": "route:ops.terminal", "kind": "route", "label": "Terminal",
     "subtitle": "Operations · Terminal",
     "keywords": ["shell", "ssh", "console", "tmux"],
     "target": {"page": "operations-tab", "subpill": "terminal"}},
    {"id": "route:ops.payloads", "kind": "route", "label": "Payloads",
     "subtitle": "Operations · Payloads",
     "keywords": ["malleable", "stager", "shellcode", "exe", "dll", "build"],
     "target": {"page": "operations-tab", "subpill": "payloads"}},

    # Settings (parent + every section as its own anchor route)
    {"id": "route:settings", "kind": "route", "label": "Settings",
     "subtitle": "All preferences and configuration",
     "keywords": ["prefs", "options", "config"],
     "target": {"page": "settings"}},
    {"id": "route:settings.general", "kind": "route", "label": "General",
     "subtitle": "Settings · General",
     "keywords": ["app info", "version", "build"],
     "target": {"page": "settings", "anchor": "settings-general"}},
    {"id": "route:settings.prereqs", "kind": "route",
     "label": "AWS & SSH Prerequisites",
     "subtitle": "Settings · Prerequisites",
     "keywords": ["aws check", "iam", "permissions", "credentials", "keys"],
     "target": {"page": "settings", "anchor": "settings-prereqs"}},
    {"id": "route:settings.domains", "kind": "route", "label": "Domains & DNS",
     "subtitle": "Settings · Domains",
     "keywords": ["route53", "dns", "domain fronting", "categorization"],
     "target": {"page": "settings", "anchor": "settings-domains"}},
    {"id": "route:settings.secrets", "kind": "route", "label": "Secrets Manager",
     "subtitle": "Settings · Secrets",
     "keywords": ["passwords", "tokens", "github", "credentials"],
     "target": {"page": "settings", "anchor": "settings-secrets"}},
    {"id": "route:settings.services", "kind": "route",
     "label": "Infrastructure Services",
     "subtitle": "Settings · Services",
     "keywords": ["s3", "vpc", "ec2", "infra"],
     "target": {"page": "settings", "anchor": "settings-services"}},
    {"id": "route:settings.cost", "kind": "route", "label": "Cost Tracker",
     "subtitle": "Settings · Cost",
     "keywords": ["billing", "burn", "monthly", "budget"],
     "target": {"page": "settings", "anchor": "settings-cost"}},
    {"id": "route:settings.prefs", "kind": "route",
     "label": "Deployment Preferences",
     "subtitle": "Settings · Preferences",
     "keywords": ["defaults", "region", "ssh", "preferences"],
     "target": {"page": "settings", "anchor": "settings-prefs"}},
    {"id": "route:settings.roadmap", "kind": "route", "label": "Roadmap",
     "subtitle": "Settings · Roadmap",
     "keywords": ["upcoming", "planned", "todo"],
     "target": {"page": "settings", "anchor": "settings-roadmap"}},
]


_ACTIONS: list[dict[str, Any]] = [
    # Primary deployment lifecycle
    {"id": "action:new-deployment", "kind": "action",
     "label": "+ New deployment",
     "subtitle": "Open the deployment journey",
     "keywords": ["create", "wizard", "start", "spin up", "deploy"],
     "target": {"action": "journey.open"}},
    {"id": "action:apply", "kind": "action", "label": "Apply current deployment",
     "subtitle": "terraform apply on the active project",
     "keywords": ["deploy", "run", "provision"],
     "target": {"action": "deploy.apply"}},
    {"id": "action:plan", "kind": "action", "label": "Plan current deployment",
     "subtitle": "terraform plan — diff without apply",
     "keywords": ["diff", "dry-run", "preview"],
     "target": {"action": "deploy.plan"}},
    {"id": "action:destroy", "kind": "action", "label": "Destroy current deployment",
     "subtitle": "terraform destroy on the active project",
     "keywords": ["teardown", "remove", "delete"],
     "target": {"action": "deploy.destroy"}},
    {"id": "action:purge", "kind": "action", "label": "Purge leftover resources",
     "subtitle": "Cleanup orphaned AWS resources",
     "keywords": ["orphan", "leftover", "cleanup", "force-delete"],
     "target": {"action": "deploy.purge"}},
    {"id": "action:cancel-deployment", "kind": "action", "label": "Cancel running deployment",
     "subtitle": "Stop the in-flight Terraform run",
     "keywords": ["stop", "abort", "kill"],
     "target": {"action": "deploy.cancel"}},
    {"id": "action:save-config", "kind": "action", "label": "Save configuration",
     "subtitle": "Persist tfvars edits",
     "keywords": ["write", "store", "tfvars"],
     "target": {"action": "config.save"}},
    {"id": "action:refresh-all", "kind": "action", "label": "Refresh all data",
     "subtitle": "Re-fetch deployments + costs + audit feed",
     "keywords": ["reload", "sync", "update"],
     "target": {"action": "app.refresh"}},

    # Operators
    {"id": "action:add-operator", "kind": "action", "label": "Add operator…",
     "subtitle": "Create a new operator profile",
     "keywords": ["new", "create", "user"],
     "target": {"action": "operator.add"}},
    {"id": "action:manage-operators", "kind": "action", "label": "Manage operators…",
     "subtitle": "Open the operator management modal",
     "keywords": ["edit", "rename", "color", "delete"],
     "target": {"action": "operator.manage"}},

    # Theme / chrome
    {"id": "action:switch-theme", "kind": "action", "label": "Toggle theme",
     "subtitle": "Switch dark / light",
     "keywords": ["dark", "light", "mode", "appearance"],
     "target": {"action": "theme.toggle"}},

    # Diagnostics + operations utilities
    {"id": "action:run-health-check", "kind": "action", "label": "Run health check",
     "subtitle": "Validate the active deployment's infrastructure",
     "keywords": ["status", "verify", "diagnose"],
     "target": {"action": "health.run"}},
    {"id": "action:check-aws-prereqs", "kind": "action",
     "label": "Check AWS & SSH prerequisites",
     "subtitle": "Verify workstation tooling + credentials",
     "keywords": ["aws", "ssh", "iam", "preflight"],
     "target": {"action": "aws.check"}},
    {"id": "action:generate-payload", "kind": "action", "label": "Generate payload",
     "subtitle": "Open the Payloads sub-pill",
     "keywords": ["build", "stager", "shellcode", "exe", "dll"],
     "target": {"page": "operations-tab", "subpill": "payloads"}},
    {"id": "action:open-terminal", "kind": "action", "label": "Open terminal",
     "subtitle": "Web SSH console",
     "keywords": ["shell", "console", "bash"],
     "target": {"page": "operations-tab", "subpill": "terminal"}},
    {"id": "action:view-beacons", "kind": "action", "label": "View beacons",
     "subtitle": "Open the Beacons sub-pill",
     "keywords": ["sessions", "implants", "cs"],
     "target": {"page": "operations-tab", "subpill": "beacons"}},

    # Misc / informational
    {"id": "action:view-architecture", "kind": "action", "label": "View architecture diagram",
     "subtitle": "Open the architecture modal for the active deployment",
     "keywords": ["topology", "graph", "diagram"],
     "target": {"action": "architecture.open"}},
    {"id": "action:view-changelog", "kind": "action", "label": "View changelog",
     "subtitle": "Open the release notes",
     "keywords": ["releases", "history", "what's new"],
     "target": {"action": "changelog.open"}},
    {"id": "action:open-version-info", "kind": "action", "label": "Show version info",
     "subtitle": "Build version + git SHA",
     "keywords": ["build", "git", "sha"],
     "target": {"action": "version.open"}},
    {"id": "action:update-elastic-rules", "kind": "action",
     "label": "Update Elastic detection rules",
     "subtitle": "Pull latest SIEM rules from GitHub",
     "keywords": ["siem", "detections", "rules", "elastic"],
     "target": {"action": "elastic.update"}},
    {"id": "action:mark-known-external", "kind": "action",
     "label": "Mark resources as known-external",
     "subtitle": "Cleanup helper — suppress noise on adopted infra",
     "keywords": ["adopt", "ignore", "external", "cleanup"],
     "target": {"page": "deployments-tab", "subpill": "cleanup"}},
]


# ─── Recently-used MRU store ────────────────────────────────────────────────

def _recent_path(op_id: str) -> Path:
    """Per-operator MRU JSON path. Path-traversal hardened.

    The operator id is constrained to alphanumerics + dash/underscore at
    creation time (see ``operator_service.add``) so we additionally
    enforce that constraint here in case a forged cookie reaches us.
    """
    safe = "".join(c for c in (op_id or "unknown")
                   if c.isalnum() or c in ("-", "_"))[:64] or "unknown"
    return _RECENT_DIR / f"palette_recent_{safe}.json"


def _read_recent(op_id: str) -> list[str]:
    """Return the operator's MRU list (most-recent first).

    Missing file / malformed JSON / I/O errors all return ``[]`` — the
    palette must always render even with a fresh store.
    """
    path = _recent_path(op_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    return [str(x) for x in items if isinstance(x, str)][:_MAX_RECENT]


def _write_recent(op_id: str, item_id: str) -> None:
    """Push item_id to the front of the MRU; dedupe; cap at _MAX_RECENT.

    Best-effort: any failure is logged but never raises (palette
    selection must not break the user flow).
    """
    try:
        with _RECENT_LOCK:
            _RECENT_DIR.mkdir(parents=True, exist_ok=True)
            existing = _read_recent(op_id)
            existing = [x for x in existing if x != item_id]
            existing.insert(0, item_id)
            existing = existing[:_MAX_RECENT]
            _recent_path(op_id).write_text(
                json.dumps({"items": existing,
                            "updated_at": datetime.now(timezone.utc).isoformat()})
            )
    except OSError as e:
        _log.warning("palette MRU write failed for op=%s: %s", op_id, e)


# ─── Dynamic item builders ──────────────────────────────────────────────────

def _build_deployment_items() -> list[dict[str, Any]]:
    """Return one or two items per active deployment.

    Reads the same on-disk state directory the /api/deploy/active route
    walks. Defensive: missing dir → empty list, malformed file → skip.
    Each deployment yields up to two items (switch + manage) but only the
    'manage' item is emitted in v1 to keep the index lean; the switch
    behavior is implicit (selecting Manage on a project also makes it the
    active deployment context).
    """
    items: list[dict[str, Any]] = []
    try:
        from webapp.backend.routes.deploy import _state_file_path  # noqa: F401
    except Exception:
        pass

    # Walk the on-disk deployment-state directory (same as /api/deploy/active).
    from pathlib import Path as _P
    project_root = _P(__file__).resolve().parents[3]
    state_dir = project_root / "logs" / "deployment_state"
    if not state_dir.is_dir():
        return items

    rows: list[dict[str, Any]] = []
    for entry in state_dir.iterdir():
        if not entry.name.endswith(".state.json"):
            continue
        try:
            with entry.open() as f:
                state = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if state.get("status") != "success":
            continue
        rows.append({
            "name": entry.name.replace(".state.json", ""),
            "deployment_type": state.get("deployment_type") or "—",
            "region": state.get("aws_region") or state.get("region") or "—",
            "completed_at": state.get("completed_at") or 0,
        })

    # Most-recent first.
    rows.sort(key=lambda r: r["completed_at"], reverse=True)

    for row in rows:
        items.append({
            "id": f"deployment:{row['name']}",
            "kind": "deployment",
            "label": row["name"],
            "subtitle": f"{row['deployment_type']} · {row['region']}",
            "keywords": ["lab", "project", row["deployment_type"]],
            "target": {"page": "deployments-tab", "subpill": "manage",
                       "project": row["name"]},
        })
    return items


def _build_operator_items() -> list[dict[str, Any]]:
    """One 'Switch to X' item per operator profile."""
    items: list[dict[str, Any]] = []
    try:
        stats = operator_service.get_last_active_map()
        for op in operator_service.list_operators():
            s = stats.get(op["id"], {"last_active": None, "action_count": 0})
            last = s.get("last_active") or "never"
            items.append({
                "id": f"operator:{op['id']}",
                "kind": "operator",
                "label": f"Switch to {op.get('display') or op['id']}",
                "subtitle": f"Operator profile · last active {last}",
                "color": op.get("color"),
                "keywords": [op["id"], "operator", "switch", "profile"],
                "target": {"action": "operator.switch", "id": op["id"]},
            })
    except Exception as e:
        _log.warning("palette: operator items unavailable: %s", e)
    return items


def _build_audit_items() -> list[dict[str, Any]]:
    """Last 50 audit entries as 'View entry' surfaces.

    Each item navigates to the Dashboard activity feed; we don't yet
    deep-link to a per-entry detail view (M-Operators surface only).
    """
    items: list[dict[str, Any]] = []
    try:
        entries = audit_service.read_recent(limit=50)
    except Exception as e:
        _log.warning("palette: audit items unavailable: %s", e)
        return items

    for i, entry in enumerate(entries):
        action = entry.get("action", "?")
        op = entry.get("op", "?")
        ts = entry.get("ts", "")
        target = entry.get("target") or entry.get("project") or "—"
        items.append({
            "id": f"audit-entry:{ts}:{i}",
            "kind": "audit-entry",
            "label": f"{action} — {target}",
            "subtitle": f"{op} · {ts}",
            "keywords": [action, op, "audit", "history"],
            "target": {"page": "dashboard", "anchor": "dashboard-activity-widget"},
        })
    return items


def _build_bolton_items() -> list[dict[str, Any]]:
    """Every bolt-on vulnerability descriptor as 'Browse vuln X' items.

    Pydantic + the descriptor YAMLs may not be loadable in every
    environment (Pydantic isn't a hard dependency); on any failure we
    return an empty list with a debug log rather than break the
    palette.
    """
    items: list[dict[str, Any]] = []
    try:
        from webapp.bolton.catalog import load_catalog
        catalog = load_catalog()
    except Exception as e:
        _log.debug("palette: bolton catalog unavailable (%s) — skipping", e)
        return items

    for vuln_id, desc in catalog.items():
        name = getattr(desc, "name", None) or vuln_id
        category = getattr(desc, "category", None) or "—"
        subcategory = getattr(desc, "subcategory", None) or ""
        sub = f"{category}{(' · ' + subcategory) if subcategory else ''}"
        items.append({
            "id": f"vuln:{vuln_id}",
            "kind": "vuln",
            "label": name,
            "subtitle": f"Bolt-on · {sub}",
            "keywords": [vuln_id, category, subcategory, "vuln", "bolton"],
            "target": {"page": "deployments-tab", "subpill": "manage",
                       "vuln_id": vuln_id},
        })
    return items


def _build_beacon_items() -> list[dict[str, Any]]:
    """Active beacons (placeholder — beacon service auth requires live CS).

    TODO: when the dashboard maintains a passive beacon cache, surface
    real beacons here. For v1 the palette returns an empty list rather
    than fire authenticated CS REST calls on every index fetch.
    """
    return []


def _build_session_items() -> list[dict[str, Any]]:
    """Terminal sessions (placeholder — see _build_beacon_items)."""
    return []


# ─── Routes ─────────────────────────────────────────────────────────────────

@bp.route("/index", methods=["GET"])
def get_index():
    """Return the full palette index + this operator's MRU list."""
    op = getattr(g, "operator", None) or {"id": "unknown"}
    op_id = op.get("id", "unknown")

    items: list[dict[str, Any]] = []
    items.extend(_ROUTES)
    items.extend(_ACTIONS)
    items.extend(_build_deployment_items())
    items.extend(_build_beacon_items())
    items.extend(_build_session_items())
    items.extend(_build_operator_items())
    items.extend(_build_audit_items())
    items.extend(_build_bolton_items())

    # Safety cap — operators reaching 1000 items is years away, but a
    # runaway audit/catalog should never blow up the JSON response.
    if len(items) > _MAX_ITEMS:
        items = items[:_MAX_ITEMS]

    return jsonify({
        "success": True,
        "items": items,
        "recently_used": _read_recent(op_id),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })


@bp.route("/select", methods=["POST"])
def post_select():
    """Record an operator's palette selection.

    Body: ``{"id": "<item id>"}``. The id is pushed to the front of the
    operator's MRU list (deduped, capped at _MAX_RECENT). Also writes
    one ``palette.select`` audit entry so the activity feed reflects
    palette usage alongside other operator actions.
    """
    data = request.get_json(silent=True) or {}
    item_id = data.get("id")
    if not isinstance(item_id, str) or not item_id.strip():
        return jsonify({"success": False, "error": "id is required"}), 400

    item_id = item_id.strip()[:200]  # hard cap to bound MRU file size

    op = getattr(g, "operator", None) or {"id": "unknown"}
    op_id = op.get("id", "unknown")

    _write_recent(op_id, item_id)
    audit_service.write(op_id, "palette.select", target=item_id)

    return jsonify({"success": True})
