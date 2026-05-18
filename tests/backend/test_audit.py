"""M-Operators Agent A — audit_service tests.

Verifies the JSONL audit log: write + read_recent, op_filter + action_prefix
slicing, and the invariant that write() never raises.
"""
import json
import pytest
from unittest.mock import patch

from webapp.backend.services import audit_service


@pytest.fixture
def tmp_log(tmp_path, monkeypatch):
    target = tmp_path / "audit.log"
    monkeypatch.setattr(audit_service, "_LOG_PATH", target)
    return target


def test_write_appends_jsonl_entry(tmp_log):
    audit_service.write("harris", "deploy.apply", project="c2-adhoc-01")
    lines = tmp_log.read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["op"] == "harris"
    assert entry["action"] == "deploy.apply"
    assert entry["project"] == "c2-adhoc-01"
    assert "ts" in entry


def test_write_includes_optional_fields_when_provided(tmp_log):
    audit_service.write(
        "harris",
        "beacon.exec",
        target="ABCD1234",
        details={"cmd": "whoami"},
    )
    entry = json.loads(tmp_log.read_text().splitlines()[0])
    assert entry["target"] == "ABCD1234"
    assert entry["details"] == {"cmd": "whoami"}


def test_write_omits_empty_optional_fields(tmp_log):
    audit_service.write("harris", "deploy.plan")
    entry = json.loads(tmp_log.read_text().splitlines()[0])
    assert "target" not in entry
    assert "project" not in entry
    assert "details" not in entry


def test_write_handles_none_op_as_unknown(tmp_log):
    audit_service.write(None, "deploy.plan")
    entry = json.loads(tmp_log.read_text().splitlines()[0])
    assert entry["op"] == "unknown"


def test_read_recent_returns_most_recent_first(tmp_log):
    audit_service.write("harris", "deploy.apply")
    audit_service.write("alice", "deploy.plan")
    audit_service.write("harris", "deploy.destroy")
    entries = audit_service.read_recent()
    assert len(entries) == 3
    # Most-recent first
    assert entries[0]["action"] == "deploy.destroy"
    assert entries[1]["action"] == "deploy.plan"
    assert entries[2]["action"] == "deploy.apply"


def test_read_recent_respects_limit(tmp_log):
    for i in range(20):
        audit_service.write("harris", f"deploy.step.{i}")
    entries = audit_service.read_recent(limit=5)
    assert len(entries) == 5


def test_read_recent_op_filter(tmp_log):
    audit_service.write("harris", "deploy.apply")
    audit_service.write("alice", "deploy.plan")
    audit_service.write("harris", "deploy.destroy")
    entries = audit_service.read_recent(op_filter="harris")
    assert len(entries) == 2
    assert all(e["op"] == "harris" for e in entries)


def test_read_recent_action_prefix_filter(tmp_log):
    audit_service.write("harris", "deploy.apply")
    audit_service.write("harris", "beacon.exec")
    audit_service.write("harris", "deploy.destroy")
    audit_service.write("harris", "operator.add")
    entries = audit_service.read_recent(action_prefix="deploy.")
    assert len(entries) == 2
    assert all(e["action"].startswith("deploy.") for e in entries)


def test_read_recent_empty_log_returns_empty_list(tmp_log):
    assert audit_service.read_recent() == []


def test_read_recent_skips_malformed_lines(tmp_log):
    audit_service.write("harris", "deploy.apply")
    with tmp_log.open("a") as f:
        f.write("this is not json\n")
        f.write("{broken json\n")
    audit_service.write("harris", "deploy.plan")
    entries = audit_service.read_recent()
    # Two valid entries, malformed lines silently skipped
    assert len(entries) == 2


def test_write_never_raises_on_io_error(tmp_log):
    """Even when the filesystem layer fails, write() must not raise."""
    with patch("pathlib.Path.open", side_effect=OSError("read-only fs")):
        audit_service.write("harris", "deploy.apply")  # must not raise


def test_write_never_raises_on_json_error(tmp_log):
    """A non-serializable details payload must not raise."""

    class Unserializable:
        pass

    # json.dumps will raise TypeError on this — write should swallow it
    audit_service.write("harris", "weird", details=Unserializable())


def test_read_recent_combines_filters(tmp_log):
    audit_service.write("harris", "deploy.apply")
    audit_service.write("alice", "deploy.apply")
    audit_service.write("harris", "beacon.exec")
    entries = audit_service.read_recent(op_filter="harris", action_prefix="deploy.")
    assert len(entries) == 1
    assert entries[0]["op"] == "harris"
    assert entries[0]["action"] == "deploy.apply"
