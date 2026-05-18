"""Operator profile CRUD + cookie-based identity switching.

Identity is asserted by an unsigned `dashboard_operator` cookie. The
trust boundary is upstream (AWS IAM + SSH access to the dashboard) —
see Decision #23 in docs/internal/STATUS_DEEP_DIVE_2026-05-16.md.
"""
from flask import Blueprint, request, jsonify, make_response, g
from webapp.backend.services import operator_service, audit_service

bp = Blueprint("operators", __name__, url_prefix="/api/operators")


@bp.route("", methods=["GET"])
def list_all():
    """Return all operators + the current one (from cookie)."""
    current = operator_service.resolve_from_request(request)
    return jsonify({
        "success": True,
        "operators": operator_service.list_operators(),
        "current": current,
        "default": operator_service.get_default(),
    })


@bp.route("", methods=["POST"])
def add():
    data = request.get_json(silent=True) or {}
    try:
        entry = operator_service.add(data.get("id"), data.get("display"), data.get("color"))
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    actor = getattr(g, "operator", None) or {"id": "unknown"}
    audit_service.write(actor.get("id"), "operator.add", target=entry["id"])
    return jsonify({"success": True, "operator": entry})


@bp.route("/<op_id>", methods=["DELETE"])
def remove(op_id):
    try:
        operator_service.remove(op_id)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    actor = getattr(g, "operator", None) or {"id": "unknown"}
    audit_service.write(actor.get("id"), "operator.remove", target=op_id)
    return jsonify({"success": True})


@bp.route("/switch", methods=["POST"])
def switch():
    """Set the dashboard_operator cookie. Cookie is unsigned by design — trust
    is upstream (IAM/SSH). 1-year persistence."""
    data = request.get_json(silent=True) or {}
    op_id = data.get("id")
    op = operator_service.get(op_id)
    if not op:
        return jsonify({"success": False, "error": f"unknown operator '{op_id}'"}), 400
    actor = getattr(g, "operator", None) or {"id": "unknown"}
    audit_service.write(actor.get("id"), "operator.switch", target=op_id)
    resp = make_response(jsonify({"success": True, "current": op}))
    resp.set_cookie(
        "dashboard_operator",
        op_id,
        max_age=60 * 60 * 24 * 365,
        samesite="Lax",
        path="/",
    )
    return resp
