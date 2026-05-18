"""Layer 1 smoke test: verify /api/ health endpoint returns expected JSON.

This is the canary that proves the test framework works end-to-end:
- Flask app imports cleanly
- test_client fixture is correctly wired
- enforce_loopback() does not block test_client requests
- The /api/ contract (name + version + endpoints) is honored
"""


def test_api_root_returns_200(flask_client):
    response = flask_client.get('/api/')
    assert response.status_code == 200


def test_api_root_returns_expected_shape(flask_client):
    response = flask_client.get('/api/')
    data = response.get_json()
    assert data is not None, "Expected JSON body"
    assert 'name' in data
    assert 'version' in data
    assert 'endpoints' in data
    assert isinstance(data['endpoints'], dict)


def test_api_root_endpoints_listed(flask_client):
    """Sanity check: the documented sub-endpoints are present."""
    response = flask_client.get('/api/')
    data = response.get_json()
    endpoints = data['endpoints']
    # These are the top-level blueprint groups per app.py
    for expected in ('config', 'deploy', 'aws', 'goad', 'costs'):
        assert expected in endpoints, f"/api/{expected} missing from health response"


def test_loopback_guard_does_not_block_test_client(flask_client):
    """test_client requests appear as 127.0.0.1, so enforce_loopback passes.
    If this test ever fails, the test framework is broken — every other test
    will fail with 403."""
    response = flask_client.get('/api/')
    assert response.status_code != 403, (
        "enforce_loopback() blocked test_client request — check app.py:35-39 "
        "and ensure remote_addr defaults to 127.0.0.1 in tests"
    )
