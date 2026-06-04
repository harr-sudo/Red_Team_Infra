"""M-Operators Agent A — operator_service tests.

Verifies the JSON-backed operator profile store: list, add (valid +
duplicate + invalid id), remove (with default-protect + last-operator
protect), and cookie resolution.

Uses monkeypatched _STORE_PATH so tests never touch the real
~/.dashboard/ directory.
"""
import json
import pytest
from unittest.mock import MagicMock

from webapp.backend.services import operator_service


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    """Redirect operator_service._STORE_PATH to a tmpdir for each test."""
    target = tmp_path / "operators.json"
    monkeypatch.setattr(operator_service, "_STORE_PATH", target)
    return target


def test_seed_creates_default_operator(tmp_store):
    """First call to load() seeds the store with the current OS user."""
    data = operator_service.load()
    assert "operators" in data
    assert "default" in data
    assert len(data["operators"]) == 1
    assert data["operators"][0]["id"] == data["default"]
    assert "color" in data["operators"][0]
    assert "created" in data["operators"][0]


def test_list_operators_returns_seeded_entry(tmp_store):
    ops = operator_service.list_operators()
    assert isinstance(ops, list)
    assert len(ops) == 1


def test_add_valid_operator(tmp_store):
    entry = operator_service.add("operator1", "Harris K", "#a31621")
    assert entry["id"] == "operator1"
    assert entry["display"] == "Harris K"
    assert entry["color"] == "#a31621"
    # Now the store has 2 entries
    assert len(operator_service.list_operators()) == 2


def test_add_assigns_default_display_and_color_when_omitted(tmp_store):
    entry = operator_service.add("alice", None, None)
    assert entry["id"] == "alice"
    assert entry["display"] == "Alice"
    assert entry["color"].startswith("#")


def test_add_lowercases_and_strips_id(tmp_store):
    entry = operator_service.add("  HaRRis  ", "Harris", None)
    assert entry["id"] == "operator1"


def test_add_duplicate_raises(tmp_store):
    operator_service.add("operator1", "Harris", None)
    with pytest.raises(ValueError, match="already exists"):
        operator_service.add("operator1", "Harris", None)


def test_add_empty_id_raises(tmp_store):
    with pytest.raises(ValueError, match="alphanumeric"):
        operator_service.add("", "Empty", None)


def test_add_invalid_id_raises(tmp_store):
    with pytest.raises(ValueError, match="alphanumeric"):
        operator_service.add("has spaces", "Bad", None)
    with pytest.raises(ValueError, match="alphanumeric"):
        operator_service.add("has/slash", "Bad", None)


def test_add_allows_dashes_and_underscores(tmp_store):
    operator_service.add("op-1", "Op 1", None)
    operator_service.add("op_2", "Op 2", None)
    ids = [o["id"] for o in operator_service.list_operators()]
    assert "op-1" in ids
    assert "op_2" in ids


def test_add_enforces_max_32(tmp_store):
    # Seed creates 1 operator, so add 31 more = 32 total
    for i in range(31):
        operator_service.add(f"op{i}", None, None)
    assert len(operator_service.list_operators()) == 32
    with pytest.raises(ValueError, match="too many"):
        operator_service.add("overflow", None, None)


def test_remove_existing_operator(tmp_store):
    operator_service.add("operator1", "Harris", None)
    operator_service.add("alice", "Alice", None)
    operator_service.remove("alice")
    ids = [o["id"] for o in operator_service.list_operators()]
    assert "alice" not in ids
    assert "operator1" in ids


def test_remove_unknown_operator_raises(tmp_store):
    with pytest.raises(ValueError, match="not found"):
        operator_service.remove("ghost")


def test_remove_last_operator_raises(tmp_store):
    # Store seeds 1 operator
    only_op = operator_service.list_operators()[0]["id"]
    with pytest.raises(ValueError, match="last operator"):
        operator_service.remove(only_op)


def test_remove_default_promotes_another(tmp_store):
    """Removing the default operator promotes another to default."""
    seed_id = operator_service.get_default()
    operator_service.add("operator1", "Harris", None)
    operator_service.remove(seed_id)
    new_default = operator_service.get_default()
    assert new_default == "operator1"
    assert new_default != seed_id


def test_get_returns_entry(tmp_store):
    operator_service.add("operator1", "Harris", None)
    op = operator_service.get("operator1")
    assert op is not None
    assert op["id"] == "operator1"


def test_get_unknown_returns_none(tmp_store):
    assert operator_service.get("ghost") is None


def test_resolve_from_request_with_valid_cookie(tmp_store):
    operator_service.add("operator1", "Harris", None)
    req = MagicMock()
    req.cookies = {"dashboard_operator": "operator1"}
    op = operator_service.resolve_from_request(req)
    assert op["id"] == "operator1"


def test_resolve_from_request_without_cookie_returns_default(tmp_store):
    default_id = operator_service.get_default()
    req = MagicMock()
    req.cookies = {}
    op = operator_service.resolve_from_request(req)
    assert op["id"] == default_id


def test_resolve_from_request_with_unknown_cookie_falls_back_to_default(tmp_store):
    default_id = operator_service.get_default()
    req = MagicMock()
    req.cookies = {"dashboard_operator": "ghost"}
    op = operator_service.resolve_from_request(req)
    assert op["id"] == default_id


def test_resolve_returns_unknown_synthetic_when_no_operators(tmp_store, monkeypatch):
    """If the store load returns an empty operator list, resolve returns
    a synthetic 'unknown' record (never None)."""
    monkeypatch.setattr(
        operator_service,
        "load",
        lambda: {"operators": [], "default": None},
    )
    req = MagicMock()
    req.cookies = {}
    op = operator_service.resolve_from_request(req)
    assert op is not None
    assert op["id"] == "unknown"


def test_save_persists_to_disk(tmp_store):
    operator_service.add("operator1", "Harris", "#a31621")
    raw = json.loads(tmp_store.read_text())
    ids = [o["id"] for o in raw["operators"]]
    assert "operator1" in ids


# ─── M-OperatorManagement — update() + audit analytics helpers ──────────────

def test_update_rename_and_recolor(tmp_store):
    """Happy path — both display and color change, id stays put."""
    operator_service.add("operator1", "Harris K", "#a31621")
    entry = operator_service.update("operator1", display="Operator One", color="#3b82f6")
    assert entry["id"] == "operator1"
    assert entry["display"] == "Operator One"
    assert entry["color"] == "#3b82f6"
    # Persisted to disk
    raw = json.loads(tmp_store.read_text())
    persisted = next(o for o in raw["operators"] if o["id"] == "operator1")
    assert persisted["display"] == "Operator One"
    assert persisted["color"] == "#3b82f6"


def test_update_unknown_id_raises(tmp_store):
    with pytest.raises(ValueError, match="not found"):
        operator_service.update("ghost", display="Ghost")


def test_update_invalid_color_raises(tmp_store):
    operator_service.add("operator1", "Harris", "#a31621")
    with pytest.raises(ValueError, match="hex"):
        operator_service.update("operator1", color="not-a-color")
    with pytest.raises(ValueError, match="hex"):
        operator_service.update("operator1", color="#abc")  # 3-char short form rejected
    with pytest.raises(ValueError, match="hex"):
        operator_service.update("operator1", color="#zzzzzz")  # bad hex chars


def test_update_partial_display_only(tmp_store):
    operator_service.add("operator1", "Harris", "#a31621")
    entry = operator_service.update("operator1", display="HarrisK")
    assert entry["display"] == "HarrisK"
    assert entry["color"] == "#a31621"  # untouched


def test_update_partial_color_only(tmp_store):
    operator_service.add("operator1", "Harris", "#a31621")
    entry = operator_service.update("operator1", color="#65a30d")
    assert entry["display"] == "Harris"  # untouched
    assert entry["color"] == "#65a30d"


def test_update_never_changes_id(tmp_store):
    """id is the audit-log join key — must be immutable through update()."""
    operator_service.add("operator1", "Harris", "#a31621")
    # Even if a caller (hypothetically) passed id, the function signature
    # has no parameter for it. The DB record keeps its id.
    entry = operator_service.update("operator1", display="renamed")
    assert entry["id"] == "operator1"


def test_update_blank_display_is_noop(tmp_store):
    """Empty/whitespace display does not blank out the existing name."""
    operator_service.add("operator1", "Harris K", "#a31621")
    entry = operator_service.update("operator1", display="   ")
    assert entry["display"] == "Harris K"


def test_get_last_active_returns_none_for_unused(tmp_store, monkeypatch, tmp_path):
    """A fresh operator with no audit entries → last_active is None."""
    from webapp.backend.services import audit_service
    monkeypatch.setattr(audit_service, "_LOG_PATH", tmp_path / "audit.log")
    operator_service.add("operator1", "Harris", "#a31621")
    assert operator_service.get_last_active("operator1") is None


def test_get_last_active_returns_iso_timestamp(tmp_store, monkeypatch, tmp_path):
    from webapp.backend.services import audit_service
    monkeypatch.setattr(audit_service, "_LOG_PATH", tmp_path / "audit.log")
    operator_service.add("operator1", "Harris", "#a31621")
    audit_service.write("operator1", "deploy.plan", project="proj-a")
    ts = operator_service.get_last_active("operator1")
    assert ts is not None
    assert ts.endswith("Z")  # ISO with explicit Zulu suffix


def test_get_last_active_map_shape(tmp_store, monkeypatch, tmp_path):
    """Bulk variant returns one slot per known operator with last_active + count."""
    from webapp.backend.services import audit_service
    monkeypatch.setattr(audit_service, "_LOG_PATH", tmp_path / "audit.log")
    operator_service.add("operator1", "Harris", "#a31621")
    operator_service.add("alice", "Alice", "#3b82f6")
    operator_service.add("bob", "Bob", "#7c3aed")
    # Mixed audit history
    audit_service.write("operator1", "deploy.plan")
    audit_service.write("operator1", "deploy.apply", project="p1")
    audit_service.write("alice", "beacon.exec")
    # bob has no audit entries
    # Also write an entry for an unknown operator — must be ignored.
    audit_service.write("ghost", "deploy.plan")

    m = operator_service.get_last_active_map()
    # Exactly the known operator ids
    seed_id = operator_service.get_default()  # the auto-seeded op
    assert set(m.keys()) == {"operator1", "alice", "bob", seed_id}
    assert m["operator1"]["action_count"] == 2
    assert m["alice"]["action_count"] == 1
    assert m["bob"]["action_count"] == 0
    assert m["bob"]["last_active"] is None
    # last_active must be the MOST RECENT entry for each op
    assert m["operator1"]["last_active"] is not None
    assert m["alice"]["last_active"] is not None


def test_get_last_active_map_excludes_unknown_operators(tmp_store, monkeypatch, tmp_path):
    """Audit entries from operators that no longer exist are filtered out
    (not silently added to the map under their stale id)."""
    from webapp.backend.services import audit_service
    monkeypatch.setattr(audit_service, "_LOG_PATH", tmp_path / "audit.log")
    operator_service.add("operator1", "Harris", "#a31621")
    audit_service.write("ghost", "deploy.plan")
    audit_service.write("operator1", "deploy.apply")
    m = operator_service.get_last_active_map()
    assert "ghost" not in m
    assert m["operator1"]["action_count"] == 1
