"""Dashboard settings routes — Dashboard Server EIP get/override.

Exposes the Dashboard Server EIP (the public IP of the sole SSH/RDP jump
host) so the frontend can build connect commands and let the operator
view/override it in Settings.

The app-wide loopback guard (app.py enforce_loopback) already protects
/api/* — only requests arriving over the SSH tunnel from 127.0.0.1 reach
here. There is no CSRF layer; the EIP is validated server-side regardless.

Endpoints
---------
GET /api/settings
    response: {
        success: true,
        dashboard_server_eip:          <effective>,
        dashboard_server_eip_override: <override>,
        dashboard_server_eip_detected: <detected>,
        dashboard_server_eip_source:   "override"|"env"|"terraform"|"unset"
    }

POST /api/settings
    body: {dashboard_server_eip: "<ipv4 or empty>"}
    response: same shape as GET (200), or {success:false, error:str} (400)
              when the value is not empty and not a dotted IPv4.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from webapp.backend.services import dashboard_settings_service

bp = Blueprint("settings", __name__, url_prefix="/api/settings")


def _settings_payload() -> dict:
    """Build the GET/POST success payload from the resolver."""
    resolved = dashboard_settings_service.resolve_eip()
    return {
        "success": True,
        "dashboard_server_eip": resolved["effective"],
        "dashboard_server_eip_override": resolved["override"],
        "dashboard_server_eip_detected": resolved["detected"],
        "dashboard_server_eip_source": resolved["source"],
    }


@bp.route("", methods=["GET"])
def get_settings():
    """Return the resolved Dashboard Server EIP (effective/override/detected)."""
    return jsonify(_settings_payload())


@bp.route("", methods=["POST"])
def update_settings():
    """Persist a Dashboard Server EIP override (empty string clears it)."""
    data = request.get_json(silent=True) or {}
    eip = data.get("dashboard_server_eip", "")
    try:
        dashboard_settings_service.save(eip)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify(_settings_payload())
