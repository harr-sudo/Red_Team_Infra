"""
Cost Tracking API
=================
Endpoints for AWS Cost Explorer data, running estimates, and budget settings.
"""

import logging
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from webapp.backend.services.cost_service import CostService

bp = Blueprint('costs', __name__)
logger = logging.getLogger(__name__)

_service = CostService(project_root)


@bp.route('/summary', methods=['GET'])
def cost_summary():
    """Get actual + estimated costs for a project."""
    project = request.args.get('project', '')
    force = request.args.get('force', 'false').lower() == 'true'

    if not project:
        return jsonify({"success": False, "error": "Missing 'project' parameter"}), 400

    # 2026-05-28 — demo bypass: never invoke Cost Explorer for the
    # synthetic deployment. CE has hard daily caps + non-zero per-call
    # cost; we already short-circuit demo across the rest of the API
    # surface. Return a canned $0 envelope shaped like the real one so
    # the Settings → Cost Tracker panel renders cleanly.
    try:
        from webapp.backend.services import demo_data_service
        if demo_data_service.is_demo_project(project):
            demo_cost = demo_data_service.cost_summary() if hasattr(
                demo_data_service, "cost_summary") else {}
            return jsonify({
                "success": True,
                "is_demo": True,
                "project": project,
                "actual_costs": {
                    "available": True,
                    "total": demo_cost.get("monthly_total", 0.0),
                    "currency": "USD",
                    "daily_costs": [],
                    "source": "demo",
                },
                "budget": {
                    "monthly_limit": 500.0,
                    "used": demo_cost.get("monthly_total", 0.0),
                    "remaining": 500.0 - demo_cost.get("monthly_total", 0.0),
                    "percent": (demo_cost.get("monthly_total", 0.0) / 500.0 * 100) if 500.0 else 0,
                },
            })
    except Exception:
        # Fall through to real path on any demo helper failure.
        pass

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


@bp.route('/aggregate', methods=['GET'])
def aggregate():
    """Aggregate monthly burn across all active deployments.

    Per Decision #19, D5 Dashboard launchpad's cost trend tile shows
    "all deployments" by default, with drill-down to per-deployment.

    Optional query params:
      ?region=eu-central-1     Filter to a specific AWS region
                                (default: all regions tracked in the
                                project's tfvars)
      ?include_destroyed=true  Include recently-destroyed deployments
                                (default: active only)

    Returns:
      {
        "success": true,
        "monthly_total": 407.53,
        "currency": "USD",
        "deployments": [
            {"project_name": "c2_adhoc_dev_...", "monthly": 207.53, "status": "running"},
            {"project_name": "goad_mini_dev_...", "monthly": 200.00, "status": "running"}
        ],
        "region_filter": null,
        "computed_at": "2026-05-18T15:30:00Z"
      }
    """
    region_filter = request.args.get('region')
    include_destroyed = request.args.get('include_destroyed', 'false').lower() == 'true'

    try:
        agg = _service.get_aggregate_monthly_burn(
            region=region_filter,
            include_destroyed=include_destroyed,
        )
        deployments = list(agg.get('deployments') or [])
        # 2026-05-28 — surface the demo project's synthetic monthly burn
        # as a labeled line item so the operator can drill into it from
        # the picker, but EXCLUDE it from monthly_total so the headline
        # real-spend number isn't inflated by synthetic data. The
        # frontend reads monthly_total_demo separately for an "+ X demo"
        # tag on the Cost Trend tile.
        demo_monthly = 0.0
        try:
            from webapp.backend.services import demo_data_service
            if hasattr(demo_data_service, "cost_summary"):
                demo_cost = demo_data_service.cost_summary()
                if demo_cost and not any(
                    (d.get("project_name") == demo_cost.get("project_name"))
                    for d in deployments
                ):
                    demo_monthly = float(demo_cost.get("monthly_total", 0.0) or 0.0)
                    deployments.append({
                        "project_name": demo_cost.get("project_name"),
                        "monthly": demo_monthly,
                        "status": "running",
                        "is_demo": True,
                    })
        except Exception:
            # Demo fold-in failures must not break the real aggregate.
            pass
        monthly_total = sum(
            float(d.get("monthly", 0) or 0)
            for d in deployments
            if not d.get("is_demo")
        )
        return jsonify({
            'success': True,
            'monthly_total': monthly_total,
            'monthly_total_demo': demo_monthly,
            'currency': agg.get('currency', 'USD'),
            'deployments': deployments,
            'region_filter': agg.get('region_filter'),
            'computed_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        })
    except Exception as e:
        logger.exception("aggregate cost calculation failed")
        return jsonify({'success': False, 'error': str(e)}), 500


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


@bp.route('/ce-usage', methods=['GET'])
def ce_usage():
    """Today's Cost Explorer call usage vs the daily hard limit.

    Surfaced on the cost overlay so the operator can see how many CE
    requests they've burned today + how many remain. Cheap to call — no
    AWS hit, just reads logs/cost_cache/_ce_call_counter.json.
    """
    return jsonify({"success": True, **_service.get_ce_usage()})
