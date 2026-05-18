"""P1 #7.6 — Tests for /api/version and version helper integration.

Verifies:
- /api/version returns 200 with the expected JSON shape
- version matches the VERSION file at repo root
- git_sha is 7-char hex OR the sentinel 'unknown'
- built_at parses as ISO 8601 UTC
- /api/ shares the same version source (helper is reused)
"""

import re
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
VERSION_FILE = PROJECT_ROOT / 'VERSION'

_HEX7_RE = re.compile(r'^[0-9a-f]{7}$')


def _expected_version():
    return VERSION_FILE.read_text(encoding='utf-8').strip()


def test_version_endpoint_returns_200(flask_client):
    response = flask_client.get('/api/version')
    assert response.status_code == 200


def test_version_endpoint_shape(flask_client):
    response = flask_client.get('/api/version')
    data = response.get_json()
    assert data is not None, "Expected JSON body"
    for key in ('version', 'git_sha', 'built_at'):
        assert key in data, f"missing key {key!r} in /api/version response"


def test_version_matches_version_file(flask_client):
    response = flask_client.get('/api/version')
    data = response.get_json()
    assert data['version'] == _expected_version(), (
        f"/api/version reported {data['version']!r} but VERSION file contains "
        f"{_expected_version()!r}"
    )


def test_git_sha_is_short_hex_or_unknown(flask_client):
    response = flask_client.get('/api/version')
    sha = response.get_json()['git_sha']
    assert sha == 'unknown' or _HEX7_RE.match(sha), (
        f"git_sha must be 7-char lowercase hex or 'unknown', got {sha!r}"
    )


def test_built_at_parses_as_iso8601(flask_client):
    response = flask_client.get('/api/version')
    built_at = response.get_json()['built_at']
    # Accept the trailing 'Z' (UTC) format we emit.
    parsed = datetime.fromisoformat(built_at.replace('Z', '+00:00'))
    assert parsed.tzinfo is not None, "built_at must be timezone-aware"


def test_api_root_version_matches_version_endpoint(flask_client):
    """Sanity check: /api/ and /api/version share the get_version_info() helper."""
    api_root = flask_client.get('/api/').get_json()
    api_version = flask_client.get('/api/version').get_json()
    assert api_root['version'] == api_version['version'] == _expected_version()
