"""Presence routes — soft "who else is here" surface.

Per Decision #23 these endpoints are explicitly NOT audited. A heartbeat
fires every 30s per active project per operator; piping that through the
audit log would dwarf every other action category and tell us nothing
operationally interesting. The presence state files are the only
persistent record.

Endpoints
---------
POST /api/presence/heartbeat
    body: {project: str, page: str}
    response: {success: true, entry: {...}, others: [{...}, ...]}

GET /api/presence/<project>
    response: {success: true, project, entries: [{...}, ...]}
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from webapp.backend.services import presence_service

bp = Blueprint("presence", __name__, url_prefix="/api/presence")


def _current_operator_id() -> str:
    op = getattr(g, "operator", None) or {}
    return op.get("id") or "unknown"


@bp.route("/heartbeat", methods=["POST"])
def heartbeat():
    """Record a heartbeat for the current operator on a given project.

    Returns ``others`` — the list of OTHER operators (not the caller)
    currently active on the same project — so the frontend can render
    the banner without a second round trip.
    """
    data = request.get_json(silent=True) or {}
    project = (data.get("project") or "").strip()
    page = (data.get("page") or "").strip() or "unknown"
    if not project:
        return jsonify({"success": False, "error": "project is required"}), 400

    op_id = _current_operator_id()
    presence_service.heartbeat(op_id, project, page)

    fresh = presence_service.list_active(project)
    caller = next((e for e in fresh if e.operator_id == op_id), None)
    others = [presence_service.entry_to_dict(e) for e in fresh if e.operator_id != op_id]
    return jsonify({
        "success": True,
        "entry": presence_service.entry_to_dict(caller) if caller else None,
        "others": others,
    })


@bp.route("/<project>", methods=["GET"])
def list_for_project(project):
    """Return the current presence list for ``project`` (everyone, including
    the caller). Used by tests and admin tooling; the frontend banner reads
    `others` from the heartbeat response instead.
    """
    entries = presence_service.list_active(project)
    return jsonify({
        "success": True,
        "project": project,
        "entries": presence_service.entries_to_list(entries),
        "count": len(entries),
    })
