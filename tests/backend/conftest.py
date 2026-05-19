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

from webapp.backend.services import operator_service, audit_service, presence_service


@pytest.fixture(autouse=True)
def _isolate_dashboard_stores(tmp_path, monkeypatch):
    """Redirect operator + audit + presence storage to a tmpdir for every
    backend test. task #33 added presence_service which writes to
    webapp/state/presence/ — that path must also be redirected so tests
    don't dirty the working tree.

    Also forces the bolton install service to use its simulation path
    regardless of whether ansible-playbook is on PATH. Tests that need
    the real-ansible code paths (test_bolton_real_ansible.py) unset
    this in their own fixtures.
    """
    monkeypatch.setattr(operator_service, "_STORE_PATH", tmp_path / "operators.json")
    monkeypatch.setattr(audit_service, "_LOG_PATH", tmp_path / "audit.log")
    monkeypatch.setattr(presence_service, "STATE_DIR", tmp_path / "presence")
    monkeypatch.setenv("BOLTON_SIMULATE_ANSIBLE", "1")
    yield
