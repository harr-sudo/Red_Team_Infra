"""
Setup Check API
===============
Endpoints for checking bootstrap script status on deployed EC2 instances via SSM.
"""

from flask import Blueprint, jsonify, request
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from webapp.backend.services.setup_check_service import SetupCheckService

bp = Blueprint('setup_check', __name__)

_service = SetupCheckService(project_root)


@bp.route('/status', methods=['GET'])
def get_status():
    """Return cached setup check results for a project (no SSM call)."""
    project = request.args.get('project', '')
    if not project:
        return jsonify({"success": False, "error": "Missing 'project' parameter"}), 400

    cached = _service.get_cached(project)
    if cached:
        return jsonify({"success": True, "cached": True, **cached})
    return jsonify({"success": True, "cached": False, "hosts": [], "summary": None})


@bp.route('/run', methods=['POST'])
def run_check():
    """Trigger SSM check on all instances for a project. Returns check_id for polling."""
    data = request.get_json(silent=True) or {}
    project = data.get('project', '')
    region = data.get('region', 'eu-central-1')

    if not project:
        return jsonify({"success": False, "error": "Missing 'project' in request body"}), 400

    check_id = _service.start_check(project, region)
    return jsonify({"success": True, "check_id": check_id})


@bp.route('/poll', methods=['GET'])
def poll_check():
    """Poll for in-flight check results."""
    check_id = request.args.get('check_id', '')
    if not check_id:
        return jsonify({"success": False, "error": "Missing 'check_id' parameter"}), 400

    result = _service.poll_check(check_id)
    if result is None:
        return jsonify({"success": False, "error": "Unknown check_id"}), 404

    if result["status"] == "running":
        return jsonify({"success": True, "status": "running"})

    # Complete
    if result.get("error"):
        return jsonify({"success": False, "status": "complete", "error": result["error"]})

    return jsonify({"success": True, "status": "complete", **result.get("results", {})})
