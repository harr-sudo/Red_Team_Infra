"""Shared pytest fixtures for the Red Team Infrastructure test suite.

Layered architecture per docs/internal/STATUS_DEEP_DIVE_2026-05-16.md §21:
- Layer 1 (this file + tests/backend/): pytest + moto + mocked subprocess
- Layer 1.5 (tests/cs_contract/): jsonschema + Prism mock CS server
- Layer 2 (tests/js/): Vitest + jsdom
- Layer 3 (tests/browser/): Playwright + Chromium
"""

import os
import sys
from pathlib import Path
import pytest

# Make the project root importable regardless of pytest's cwd
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def flask_client():
    """A Flask test_client.

    test_client requests appear as remote_addr=127.0.0.1, so the
    enforce_loopback() guard at webapp/backend/app.py:35-39 passes
    naturally. No bypass needed.
    """
    from webapp.backend.app import app
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_aws():
    """Wraps a test in moto's mock_aws decorator (single fixture for all
    AWS services this project uses: ec2, s3, iam, secretsmanager, route53,
    acm, dynamodb, cloudfront, sts)."""
    from moto import mock_aws as _mock_aws
    with _mock_aws():
        yield


@pytest.fixture
def mock_terraform_subprocess(mocker):
    """Patches subprocess.run/Popen so that no terraform binary is ever
    actually invoked. Returns a MagicMock that tests can configure with
    canned stdout/stderr/returncode.

    Usage in a test:
        def test_x(mock_terraform_subprocess):
            mock_terraform_subprocess.return_value.returncode = 0
            mock_terraform_subprocess.return_value.stdout = "No changes."
            ...
    """
    mock = mocker.patch('subprocess.run')
    mock.return_value.returncode = 0
    mock.return_value.stdout = ""
    mock.return_value.stderr = ""
    return mock
