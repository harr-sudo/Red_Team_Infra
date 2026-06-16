"""
Runtime Probes API (Mission Control)
====================================
Active runtime health probes for the live fleet — Layer 2/3 of the Mission
Control plan. Distinct from /api/setup-check (which reads bootstrap status):
these endpoints answer "is it healthy right now?".

  GET  /api/health/probes/status?project=...     cached probe result (no probe)
  POST /api/health/probes/run     {project, region}   kick off a probe run -> run_id
  GET  /api/health/probes/poll?run_id=...         poll an in-flight run
  GET  /api/health/probes/scheduler               scheduler + heartbeat status
  POST /api/health/probes/scheduler/start  {region, interval}   start/reconfigure
"""

from flask import Blueprint, jsonify, request, g
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from webapp.backend.services.runtime_probe_service import RuntimeProbeService
from webapp.backend.services import demo_data_service

bp = Blueprint('runtime_probes', __name__)

_service = RuntimeProbeService(project_root)


@bp.route('/status', methods=['GET'])
def get_status():
    """Return cached probe results for a project (no live probe).

    For the demo deployment, an optional ?state=healthy|degraded|critical
    switches (and stickily persists) the synthetic scenario so the operator
    can showcase each state through the normal status path."""
    project = request.args.get('project', '')
    if not project:
        return jsonify({"success": False, "error": "Missing 'project' parameter"}), 400
    state = request.args.get('state')
    if state and demo_data_service.is_demo_project(project):
        demo_data_service.set_probe_state(state)
    cached = _service.get_cached(project)
    # A demo scenario switch records a sample so history / incident timeline /
    # alerts reflect it immediately (no separate probe run + poll needed).
    if state and cached and demo_data_service.is_demo_project(project):
        try:
            _service._history.record_run(project, cached)
        except Exception:
            pass
    if cached:
        return jsonify({"success": True, "cached": True, **cached})
    return jsonify({"success": True, "cached": False, "hosts": [], "fabric": [],
                    "summary": None, "status": "unknown"})


@bp.route('/run', methods=['POST'])
def run_probe():
    """Trigger a live probe run for a project. Returns run_id for polling."""
    data = request.get_json(silent=True) or {}
    project = data.get('project', '')
    region = data.get('region', 'eu-central-1')
    demo_state = data.get('demo_state')  # only honored for the demo deployment
    if not project:
        return jsonify({"success": False, "error": "Missing 'project' in request body"}), 400
    run_id = _service.start_run(project, region, demo_state)
    return jsonify({"success": True, "run_id": run_id})


@bp.route('/poll', methods=['GET'])
def poll_probe():
    """Poll an in-flight probe run."""
    run_id = request.args.get('run_id', '')
    if not run_id:
        return jsonify({"success": False, "error": "Missing 'run_id' parameter"}), 400
    result = _service.poll_run(run_id)
    if result is None:
        return jsonify({"success": False, "error": "Unknown run_id"}), 404
    if result["status"] == "running":
        return jsonify({"success": True, "status": "running"})
    if result.get("error"):
        return jsonify({"success": False, "status": "complete", "error": result["error"]})
    return jsonify({"success": True, "status": "complete", **(result.get("result") or {})})


@bp.route('/scheduler', methods=['GET'])
def scheduler_status():
    """Scheduler liveness + dead-man's-switch heartbeat age."""
    return jsonify({"success": True, **_service.scheduler_status()})


@bp.route('/scheduler/start', methods=['POST'])
def scheduler_start():
    """Start or reconfigure the background scheduler."""
    data = request.get_json(silent=True) or {}
    region = data.get('region', 'eu-central-1')
    interval = data.get('interval', 3600)
    result = _service.start_scheduler(region, interval)
    return jsonify({"success": True, **result})


@bp.route('/scheduler/stop', methods=['POST'])
def scheduler_stop():
    """Stop the background scheduler (turn auto-checks off). The daemon thread
    wakes from its interval wait and exits; a later start spins up a fresh one."""
    _service.stop_scheduler()
    return jsonify({"success": True, "running": False})


# ── Phase 4: history / incidents / heartbeat / alerts ────────────────────────

def _seed_if_demo(project):
    if project and _service._is_demo(project):
        try:
            _service._history.seed_demo(project)
        except Exception:
            pass


@bp.route('/history', methods=['GET'])
def history():
    """Status + response-time series and uptime% for one target over a window."""
    project = request.args.get('project', '')
    target = request.args.get('target', '')
    window = int(request.args.get('window', 86400))
    if not project or not target:
        return jsonify({"success": False, "error": "Missing 'project' or 'target'"}), 400
    _seed_if_demo(project)
    h = _service._history
    return jsonify({"success": True, "target": target,
                    "series": h.series(project, target, window),
                    "uptime": h.uptime(project, target, window)})


@bp.route('/events', methods=['GET'])
def events():
    """Incident timeline — status transitions (one project, or all if omitted)."""
    project = request.args.get('project') or None
    window = int(request.args.get('window', 604800))
    _seed_if_demo(project)
    return jsonify({"success": True, "events": _service._history.events(project, window)})


@bp.route('/heartbeat', methods=['POST'])
def heartbeat():
    """Per-host dead-man's-switch ping. A host (or its agent) calls this; absence
    over the window surfaces it as a 'silent' alert."""
    data = request.get_json(silent=True) or {}
    target = data.get('target_id') or data.get('host')
    project = data.get('project', '')
    if not target or not project:
        return jsonify({"success": False, "error": "Missing 'target_id' or 'project'"}), 400
    last = _service._history.heartbeat(target, project, data.get('source', 'push'))
    return jsonify({"success": True, "last_seen": last})


@bp.route('/alerts', methods=['GET'])
def alerts():
    """Current in-app alerts: targets whose latest status is warn/crit, plus any
    silent (stale-heartbeat) hosts. Filterable by severity + role. No external
    notifications are fired — this is the Mission Control Alerts view's data."""
    project = request.args.get('project', '')
    sev = request.args.get('severity')      # 'warn' | 'crit'
    role = request.args.get('role')
    if not project:
        return jsonify({"success": False, "error": "Missing 'project'"}), 400
    _seed_if_demo(project)
    h = _service._history
    # Build a {target_id -> [failing check details]} map from the latest probe
    # payload so each alert names the SPECIFIC failure, not a generic "x is crit".
    fail_detail = {}
    cached = _service.get_cached(project) or {}
    for item in (cached.get("hosts") or []) + (cached.get("fabric") or []):
        tid = item.get("instance_id") or item.get("id") or item.get("name")
        bad = [c.get("detail") for c in (item.get("checks") or [])
               if c.get("status") in ("warn", "crit") and c.get("detail")]
        if tid and bad:
            fail_detail[tid] = bad

    out = []
    for s in h.latest_per_target(project):
        if s.get("status") in ("warn", "crit"):
            if h.is_suppressed(project, s["target_id"], s["status"]):
                continue  # cleared/archived and not recurred
            details = fail_detail.get(s["target_id"])
            reason = "; ".join(details[:2]) if details else f"{s['role'] or s['kind']} is {s['status']}"
            out.append({"target_id": s["target_id"], "name": s["name"], "role": s["role"],
                        "kind": s["kind"], "severity": s["status"], "ts": s["ts"],
                        "since": h._entered_ts(project, s["target_id"], s["status"]) or s["ts"],
                        "reason": reason})
    for hb in h.stale_heartbeats():
        if hb.get("project") == project and not h.is_suppressed(project, hb["target_id"], "crit"):
            out.append({"target_id": hb["target_id"], "name": hb["target_id"], "role": "host",
                        "kind": "heartbeat", "severity": "crit", "ts": hb["last_seen"],
                        "since": hb["last_seen"],
                        "reason": "silent — no heartbeat within window (dead-man's switch)"})
    if sev:
        out = [a for a in out if a["severity"] == sev]
    if role:
        out = [a for a in out if a["role"] == role]
    out.sort(key=lambda a: ({"crit": 0, "warn": 1}.get(a["severity"], 2), -a["ts"]))
    return jsonify({"success": True, "alerts": out,
                    "counts": {"crit": sum(1 for a in out if a["severity"] == "crit"),
                               "warn": sum(1 for a in out if a["severity"] == "warn")}})


@bp.route('/alerts/clear', methods=['POST'])
def alerts_clear():
    """Clear (acknowledge) an alert → moves it to the archive. Suppressed while
    the target stays in this status; re-raises on a fresh transition back into it."""
    data = request.get_json(silent=True) or {}
    project = data.get('project', '')
    target = data.get('target_id', '')
    status = data.get('status', '')
    if not project or not target or not status:
        return jsonify({"success": False, "error": "Missing project/target_id/status"}), 400
    by = (getattr(g, 'operator', None) or {}).get('id', 'unknown')
    ts = _service._history.clear_alert(project, target, status,
                                       name=data.get('name'), role=data.get('role'),
                                       reason=data.get('reason'), cleared_by=by)
    return jsonify({"success": True, "cleared_at": ts, "cleared_by": by})


@bp.route('/alerts/archive', methods=['GET'])
def alerts_archive():
    """The archive of cleared alerts (most recent first)."""
    project = request.args.get('project') or None
    _seed_if_demo(project)
    return jsonify({"success": True, "archived": _service._history.archived(project)})
