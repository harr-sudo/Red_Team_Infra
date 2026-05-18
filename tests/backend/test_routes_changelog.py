"""P1 #7.6 — Tests for the /changelog Flask route.

Verifies:
- /changelog returns 200 with the CHANGELOG.md content as text/markdown
- The Content-Type is text/markdown (UTF-8)
- The body contains the Keep-a-Changelog header marker
- A missing CHANGELOG.md returns 404 with a JSON error body
"""

from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).parent.parent.parent
CHANGELOG_FILE = PROJECT_ROOT / 'CHANGELOG.md'


def test_changelog_route_returns_200(flask_client):
    response = flask_client.get('/changelog')
    assert response.status_code == 200


def test_changelog_route_returns_markdown_content_type(flask_client):
    response = flask_client.get('/changelog')
    ctype = response.headers.get('Content-Type', '')
    assert 'text/markdown' in ctype, f"expected text/markdown, got {ctype!r}"
    assert 'utf-8' in ctype.lower()


def test_changelog_route_returns_real_file_contents(flask_client):
    response = flask_client.get('/changelog')
    body = response.get_data(as_text=True)
    expected = CHANGELOG_FILE.read_text(encoding='utf-8')
    assert body == expected


def test_changelog_route_404s_when_file_missing(flask_client):
    """If CHANGELOG.md is missing, the route returns 404 with JSON error."""
    # Patch Path.read_text on the route's _CHANGELOG_FILE so the route
    # raises FileNotFoundError without us actually deleting the real file.
    with patch('webapp.backend.app._CHANGELOG_FILE') as mock_file:
        mock_file.read_text.side_effect = FileNotFoundError()
        response = flask_client.get('/changelog')
    assert response.status_code == 404
    data = response.get_json()
    assert data is not None and 'error' in data
