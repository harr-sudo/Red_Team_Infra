"""Tests for the GET /api/costs/aggregate endpoint (D5.0).

Per the D5 dashboard launchpad plan (§17 P2 #29c, Decision #19), the cost
trend tile defaults to summing monthly burn across ALL active deployments,
with optional region filter and an include_destroyed escape hatch.

cost_service helpers are stubbed via mocker.patch so the test does NOT hit
real AWS Cost Explorer.
"""

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _projects_active_only():
    return [
        {"name": "c2_adhoc_dev_01", "status": "active", "deployment_type": "c2-adhoc"},
        {"name": "goad_mini_dev_01", "status": "active", "deployment_type": "goad-mini"},
    ]


def _projects_with_destroyed():
    return _projects_active_only() + [
        {"name": "c2_full_old_01", "status": "destroyed", "deployment_type": "c2-full"},
    ]


def _estimate_for(monthly: float, available: bool = True):
    return {
        "available": available,
        "estimated_monthly": monthly,
        "estimated_total": 0.0,
        "hourly_rate": 0.0,
        "hours_running": 0.0,
        "by_component": [],
        "is_active": True,
        "deployment_type": "c2-adhoc",
        "calculated_at": "2026-05-18T00:00:00",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_aggregate_returns_200_with_expected_shape(flask_client, mocker):
    """Default invocation: sum monthly burn across active deployments."""
    from webapp.backend.routes import costs as costs_route

    mocker.patch.object(
        costs_route._service,
        "get_all_projects_summary",
        return_value=_projects_active_only(),
    )

    def fake_est(name):
        return _estimate_for(207.53 if "c2_adhoc" in name else 200.00)

    mocker.patch.object(
        costs_route._service,
        "calculate_running_estimate",
        side_effect=fake_est,
    )

    response = flask_client.get('/api/costs/aggregate')
    assert response.status_code == 200

    data = response.get_json()
    assert data is not None
    assert data['success'] is True
    assert data['currency'] == 'USD'
    assert data['region_filter'] is None
    assert 'computed_at' in data
    assert isinstance(data['deployments'], list)
    assert len(data['deployments']) == 2
    # 207.53 + 200.00 = 407.53
    assert data['monthly_total'] == pytest.approx(407.53, abs=0.01)
    # Each deployment entry has the documented shape
    for entry in data['deployments']:
        assert 'project_name' in entry
        assert 'monthly' in entry
        assert 'status' in entry


def test_aggregate_region_filter_does_not_crash(flask_client, mocker):
    """?region=eu-central-1 is currently passthrough; just ensure no crash
    and that the region echo is reflected in the response."""
    from webapp.backend.routes import costs as costs_route

    mocker.patch.object(
        costs_route._service,
        "get_all_projects_summary",
        return_value=_projects_active_only(),
    )
    mocker.patch.object(
        costs_route._service,
        "calculate_running_estimate",
        return_value=_estimate_for(100.0),
    )

    response = flask_client.get('/api/costs/aggregate?region=eu-central-1')
    assert response.status_code == 200

    data = response.get_json()
    assert data['success'] is True
    assert data['region_filter'] == 'eu-central-1'


def test_aggregate_include_destroyed_returns_more_or_equal(flask_client, mocker):
    """?include_destroyed=true should return >= entries than the default."""
    from webapp.backend.routes import costs as costs_route

    # First, default call (active only)
    mocker.patch.object(
        costs_route._service,
        "get_all_projects_summary",
        return_value=_projects_with_destroyed(),
    )
    mocker.patch.object(
        costs_route._service,
        "calculate_running_estimate",
        return_value=_estimate_for(50.0),
    )

    active_resp = flask_client.get('/api/costs/aggregate')
    assert active_resp.status_code == 200
    active_count = len(active_resp.get_json()['deployments'])

    full_resp = flask_client.get('/api/costs/aggregate?include_destroyed=true')
    assert full_resp.status_code == 200
    full_count = len(full_resp.get_json()['deployments'])

    assert full_count >= active_count
    # And specifically: the fixture has 1 extra destroyed deployment
    assert full_count == active_count + 1


def test_aggregate_handles_estimate_failure_gracefully(flask_client, mocker):
    """If calculate_running_estimate raises, the deployment is still listed
    with monthly=0 — never crashes the whole aggregate."""
    from webapp.backend.routes import costs as costs_route

    mocker.patch.object(
        costs_route._service,
        "get_all_projects_summary",
        return_value=_projects_active_only(),
    )
    mocker.patch.object(
        costs_route._service,
        "calculate_running_estimate",
        side_effect=RuntimeError("boom"),
    )

    response = flask_client.get('/api/costs/aggregate')
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['monthly_total'] == 0
    assert len(data['deployments']) == 2
    for entry in data['deployments']:
        assert entry['monthly'] == 0


def test_aggregate_empty_project_list(flask_client, mocker):
    """No deployments at all — should still return 200 with empty list."""
    from webapp.backend.routes import costs as costs_route

    mocker.patch.object(
        costs_route._service,
        "get_all_projects_summary",
        return_value=[],
    )

    response = flask_client.get('/api/costs/aggregate')
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['monthly_total'] == 0
    assert data['deployments'] == []
