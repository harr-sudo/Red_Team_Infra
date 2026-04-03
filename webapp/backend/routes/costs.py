"""
Cost Tracking API
=================
Endpoints for AWS Cost Explorer data, running estimates, and budget settings.
"""

from flask import Blueprint, jsonify, request
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from webapp.backend.services.cost_service import CostService

bp = Blueprint('costs', __name__)

_service = CostService(project_root)


@bp.route('/summary', methods=['GET'])
def cost_summary():
    """Get actual + estimated costs for a project."""
    project = request.args.get('project', '')
    force = request.args.get('force', 'false').lower() == 'true'

    if not project:
        return jsonify({"success": False, "error": "Missing 'project' parameter"}), 400

    try:
        result = _service.get_cost_summary(project, force_refresh=force)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/projects', methods=['GET'])
def cost_projects():
    """List all projects with cost overview."""
    projects = _service.get_all_projects_summary()
    return jsonify({"success": True, "projects": projects})


@bp.route('/budget-alert', methods=['GET'])
def budget_alert():
    """Lightweight budget check for Deployment Manager banner."""
    alert = _service.get_budget_alert()
    return jsonify({"success": True, **alert})


@bp.route('/settings', methods=['GET'])
def get_settings():
    """Get current cost tracking settings."""
    settings = _service.load_settings()
    return jsonify({"success": True, **settings})


@bp.route('/settings', methods=['POST'])
def update_settings():
    """Update cost tracking settings."""
    data = request.get_json(silent=True) or {}
    saved = _service.save_settings(data)
    return jsonify({"success": True, "message": "Cost settings saved", **saved})
