"""M-Operators Agent A — audit_service tests.

Verifies the JSONL audit log: write + read_recent, op_filter + action_prefix
slicing, and the invariant that write() never raises.
"""
import gzip
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


# ─────────────────────────────────────────────────────────────────────────
# Polish B — server-side target= filter
# Previously the beacon "driven by" pill and per-bid command history pulled
# action_prefix=beacon.exec with a high limit and filtered client-side. The
# target= kwarg moves that filter to the server.
# ─────────────────────────────────────────────────────────────────────────

def test_read_recent_target_filter_exact_match(tmp_log):
    audit_service.write("harris", "beacon.exec", target="ABCD1234")
    audit_service.write("alice", "beacon.exec", target="WXYZ9999")
    audit_service.write("harris", "beacon.exec", target="ABCD1234")
    entries = audit_service.read_recent(target_filter="ABCD1234")
    assert len(entries) == 2
    assert all(e["target"] == "ABCD1234" for e in entries)


def test_read_recent_target_filter_excludes_missing_target(tmp_log):
    """Entries without a target field should not match a target filter."""
    audit_service.write("harris", "deploy.apply")  # no target
    audit_service.write("harris", "beacon.exec", target="ABCD1234")
    entries = audit_service.read_recent(target_filter="ABCD1234")
    assert len(entries) == 1
    assert entries[0]["action"] == "beacon.exec"


def test_read_recent_target_filter_combines_with_action_prefix(tmp_log):
    audit_service.write("harris", "beacon.exec", target="ABCD1234")
    audit_service.write("harris", "beacon.sleep", target="ABCD1234")  # diff action
    audit_service.write("harris", "beacon.exec", target="WXYZ9999")   # diff target
    entries = audit_service.read_recent(
        action_prefix="beacon.exec", target_filter="ABCD1234"
    )
    assert len(entries) == 1
    assert entries[0]["action"] == "beacon.exec"
    assert entries[0]["target"] == "ABCD1234"


# ─────────────────────────────────────────────────────────────────────────
# Polish B — size-based rotation
# audit.log → audit.log.1.gz (shift older archives, keep last _MAX_ARCHIVES)
# Threshold is monkeypatched to a tiny value to keep tests fast.
# ─────────────────────────────────────────────────────────────────────────

def _force_low_threshold(monkeypatch, n_bytes=200):
    monkeypatch.setattr(audit_service, "_ROTATION_THRESHOLD_BYTES", n_bytes)


def test_rotation_triggers_when_threshold_exceeded(tmp_log, monkeypatch):
    _force_low_threshold(monkeypatch, n_bytes=200)
    # Each write line is well under 200 bytes; ~10 writes should overflow.
    for i in range(20):
        audit_service.write("harris", f"deploy.step.{i}")
    parent = tmp_log.parent
    assert (parent / "audit.log.1.gz").exists(), "expected first archive after overflow"
    # Live log should still exist (recreated empty or near-empty after rotation).
    assert tmp_log.exists()


def test_rotation_archive_contains_prior_content(tmp_log, monkeypatch):
    _force_low_threshold(monkeypatch, n_bytes=200)
    # Fill up enough to trigger one rotation, capture content before next write.
    for i in range(15):
        audit_service.write("harris", f"deploy.step.{i}")
    archive = tmp_log.parent / "audit.log.1.gz"
    assert archive.exists()
    with gzip.open(archive, "rt") as f:
        archived = f.read()
    # Sanity check the gzip round-trips and contains valid JSONL.
    lines = [l for l in archived.splitlines() if l.strip()]
    assert len(lines) >= 1
    for line in lines:
        entry = json.loads(line)
        assert entry["op"] == "harris"
        assert entry["action"].startswith("deploy.step.")


def test_rotation_keeps_only_last_three_archives(tmp_log, monkeypatch):
    _force_low_threshold(monkeypatch, n_bytes=150)
    parent = tmp_log.parent
    # Generate enough writes to force at least 5 rotations.
    for i in range(120):
        audit_service.write("harris", f"deploy.step.{i:04d}")
    assert (parent / "audit.log.1.gz").exists()
    assert (parent / "audit.log.2.gz").exists()
    assert (parent / "audit.log.3.gz").exists()
    # Anything beyond _MAX_ARCHIVES must have been pruned.
    assert not (parent / "audit.log.4.gz").exists()
    assert not (parent / "audit.log.5.gz").exists()


def test_read_recent_ignores_archives(tmp_log, monkeypatch):
    """read_recent reads only the live audit.log; archived rows must NOT
    appear in the API response."""
    _force_low_threshold(monkeypatch, n_bytes=200)
    # First wave — will be rotated out.
    for i in range(15):
        audit_service.write("harris", f"old.step.{i}")
    # Verify a rotation happened.
    assert (tmp_log.parent / "audit.log.1.gz").exists()
    # Second wave — these stay in the live log.
    audit_service.write("harris", "new.step.0")
    entries = audit_service.read_recent(limit=500)
    assert any(e["action"] == "new.step.0" for e in entries)
    assert not any(e["action"].startswith("old.step.") for e in entries)


def test_rotation_does_not_raise_when_unlink_fails(tmp_log, monkeypatch):
    """Even if archive cleanup fails, write() must not raise."""
    _force_low_threshold(monkeypatch, n_bytes=200)
    # Fill once to create audit.log.1.gz, then patch unlink to error.
    for i in range(15):
        audit_service.write("harris", f"step.{i}")
    with patch("pathlib.Path.unlink", side_effect=OSError("locked")):
        # Should not raise even though the cleanup path errors.
        for i in range(15):
            audit_service.write("harris", f"more.{i}")


def test_no_rotation_when_under_threshold(tmp_log, monkeypatch):
    """A handful of small writes should NOT trigger rotation at the default
    10 MiB threshold."""
    # Don't monkeypatch — use the real 10 MiB threshold.
    for i in range(50):
        audit_service.write("harris", f"deploy.step.{i}")
    assert not (tmp_log.parent / "audit.log.1.gz").exists()
