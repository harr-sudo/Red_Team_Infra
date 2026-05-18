"""Audit log read endpoint.

The activity feed in the frontend reads from /api/audit. Writes are done
inline from each state-changing route via audit_service.write().
"""
from flask import Blueprint, request, jsonify
from webapp.backend.services import audit_service

bp = Blueprint("audit", __name__, url_prefix="/api/audit")


@bp.route("", methods=["GET"])
def recent():
    try:
        limit = min(int(request.args.get("limit", 50)), 500)
    except (TypeError, ValueError):
        limit = 50
    op = request.args.get("op")
    action_prefix = request.args.get("action_prefix")
    project = request.args.get("project")
    entries = audit_service.read_recent(
        limit=limit,
        op_filter=op,
        action_prefix=action_prefix,
        project_filter=project,
    )
    return jsonify({"success": True, "entries": entries, "count": len(entries)})
