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
    """Return all operators + the current one (from cookie).

    Each operator dict is augmented with ``last_active`` (ISO timestamp or
    null) and ``action_count`` (int) so the Manage operators modal can
    render those stats without a per-row audit fetch. Computed via a single
    audit-log scan — see ``operator_service.get_last_active_map``.
    """
    current = operator_service.resolve_from_request(request)
    stats = operator_service.get_last_active_map()
    operators = []
    for op in operator_service.list_operators():
        s = stats.get(op["id"], {"last_active": None, "action_count": 0})
        operators.append({
            **op,
            "last_active": s["last_active"],
            "action_count": s["action_count"],
        })
    return jsonify({
        "success": True,
        "operators": operators,
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


@bp.route("/<op_id>", methods=["PATCH"])
def update(op_id):
    """Rename and/or recolor an operator. Body: ``{display?, color?}``.

    Only emits an audit row when at least one field actually changed —
    skipped no-op PATCHes do not pollute the timeline. The audit entry's
    ``details`` payload mirrors the request so the activity feed can
    replay what was changed.
    """
    data = request.get_json(silent=True) or {}
    display = data.get("display")
    color = data.get("color")
    try:
        entry = operator_service.update(op_id, display=display, color=color)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    changed = {k: v for k, v in {"display": display, "color": color}.items() if v is not None}
    if changed:
        actor = getattr(g, "operator", None) or {"id": "unknown"}
        audit_service.write(
            actor.get("id"),
            "operator.update",
            target=op_id,
            details=changed,
        )
    return jsonify({"success": True, "operator": entry})


@bp.route("/<op_id>", methods=["DELETE"])
def remove(op_id):
    actor = getattr(g, "operator", None) or {"id": "unknown"}
    current_id = actor.get("id")
    try:
        # 2026-05-22 — pass the current operator id so the service refuses
        # deletes that would orphan the request's cookie (closes the
        # UI/backend protection gap surfaced by Agent B).
        operator_service.remove(op_id, current_id=current_id)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    audit_service.write(current_id, "operator.remove", target=op_id)
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
