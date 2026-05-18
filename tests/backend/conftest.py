"""Backend-test isolation for the M-Operators stores.

The before_request hook in webapp.backend.app resolves the current
operator from ~/.dashboard/operators.json. To prevent the test suite
from writing to the real user's home dir, redirect both the operator
store and the audit log to a per-session tmpdir for ALL backend tests.

Module-level tests that want their own fresh tmp_store can still
monkeypatch the paths inside the test (see test_operators.py,
test_audit.py, test_operator_middleware.py).
"""
from pathlib import Path
import pytest

from webapp.backend.services import operator_service, audit_service


@pytest.fixture(autouse=True)
def _isolate_dashboard_stores(tmp_path, monkeypatch):
    """Redirect operator + audit storage to a tmpdir for every backend test."""
    monkeypatch.setattr(operator_service, "_STORE_PATH", tmp_path / "operators.json")
    monkeypatch.setattr(audit_service, "_LOG_PATH", tmp_path / "audit.log")
    yield
