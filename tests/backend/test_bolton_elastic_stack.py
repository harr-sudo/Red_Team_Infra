"""Tests for Phase 3b — Elastic detection stack bolt-on component.

Coverage:
  - The Elastic stack descriptor validates against the (widened) schema
    and demonstrates the new `category: infrastructure, patch: null`
    path.
  - All three shipper descriptors validate AND declare a depends_on
    edge pointing at the stack.
  - The dependency resolver auto-includes the stack when any shipper is
    requested.
  - Probe service runs in `full` mode (queries a mocked Kibana) when
    the stack is "installed" in the lab's facts cache.
  - Probe service falls back to `degraded` mode when the stack is not
    installed OR when the Kibana HTTP query fails.

Mocking strategy
----------------
- ``requests.post`` is monkey-patched on the ``bolton_probe_service``
  module so no real network traffic occurs. A small dataclass-style
  fake response covers the happy path; a side-effect that raises
  ConnectionError covers the failure path.
- The facts service is driven via its existing ``_MOCK_HOST_FACTS``
  table plus a small ``HostFacts`` dataclass with extra ``installed_services``
  fields, written through ``gather_facts``. The Phase 3b probe service
  reads ``kibana_endpoint`` / ``es_password`` off the cached HostFacts;
  for the test fixture we plant them via ``installed_services``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from webapp.bolton.catalog import (
    load_catalog,
    resolve_install_order,
)
from webapp.bolton.schema import (
    BoltOnDescriptor,
    load_descriptor_yaml,
)


CATALOG_ROOT = Path(__file__).resolve().parents[2] / "webapp" / "bolton" / "catalog"
INFRA_ROOT = CATALOG_ROOT / "infrastructure"

STACK_ID = "bolton.infrastructure.elastic-detection-stack"
WINLOGBEAT_ID = "bolton.infrastructure.winlogbeat-shipper"
FILEBEAT_ID = "bolton.infrastructure.filebeat-shipper"
SYSMON_ID = "bolton.infrastructure.sysmon"

SHIPPER_IDS = (WINLOGBEAT_ID, FILEBEAT_ID, SYSMON_ID)


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def loaded_catalog() -> dict[str, BoltOnDescriptor]:
    return load_catalog(CATALOG_ROOT)


@pytest.fixture
def stack_descriptor() -> BoltOnDescriptor:
    return load_descriptor_yaml(INFRA_ROOT / "elastic-detection-stack.yaml")


@pytest.fixture
def isolated_probe_state(tmp_path, monkeypatch):
    """Redirect probe storage + facts storage into tmpdir for the test."""
    from webapp.backend.services import bolton_facts_service, bolton_probe_service

    probes_root = tmp_path / "probes"
    probes_root.mkdir()
    facts_root = tmp_path / "host_facts"
    facts_root.mkdir()
    monkeypatch.setattr(bolton_probe_service, "PROBES_ROOT", probes_root)
    monkeypatch.setattr(bolton_facts_service, "STATE_ROOT", facts_root)
    yield {"probes_root": probes_root, "facts_root": facts_root}


# ─────────────────────────────────────────────────────────────────────
# 1. Descriptor validation
# ─────────────────────────────────────────────────────────────────────

class TestStackDescriptor:
    def test_stack_descriptor_validates(self, stack_descriptor):
        assert isinstance(stack_descriptor, BoltOnDescriptor)
        assert stack_descriptor.id == STACK_ID
        assert stack_descriptor.category == "infrastructure"

    def test_stack_descriptor_has_null_patch(self, stack_descriptor):
        """Phase 3b widened schema: infrastructure descriptors omit
        patch / patch_revert entirely (no vuln to remediate)."""
        assert stack_descriptor.patch is None
        assert stack_descriptor.patch_revert is None

    def test_stack_descriptor_has_null_mitre(self, stack_descriptor):
        """The stack is detection infra, not an attacker technique."""
        assert stack_descriptor.mitre is None

    def test_stack_descriptor_install_and_uninstall_present(self, stack_descriptor):
        assert stack_descriptor.install.steps
        assert stack_descriptor.uninstall.steps

    def test_infrastructure_descriptor_with_patch_is_rejected(self, stack_descriptor):
        """The widened schema also enforces the inverse — an
        infrastructure descriptor MAY NOT declare a patch block."""
        raw = stack_descriptor.model_dump(mode="json")
        raw["patch"] = {
            "description": "should-not-be-allowed",
            "patch_reference": "https://example.com",
            "complexity": "low",
            "rollback_supported": False,
            "side_effects": [],
            "steps": [{"ansible_role": "x", "role_vars": {}}],
            "verify": {"probe": "exit 0", "timeout_seconds": 5},
        }
        with pytest.raises(Exception) as exc:
            BoltOnDescriptor.model_validate(raw)
        assert "infrastructure" in str(exc.value)


# ─────────────────────────────────────────────────────────────────────
# 2. Shipper descriptors
# ─────────────────────────────────────────────────────────────────────

class TestShipperDescriptors:
    @pytest.mark.parametrize("slug,expected_id", [
        ("winlogbeat-shipper", WINLOGBEAT_ID),
        ("filebeat-shipper", FILEBEAT_ID),
        ("sysmon", SYSMON_ID),
    ])
    def test_each_shipper_validates(self, slug, expected_id):
        d = load_descriptor_yaml(INFRA_ROOT / f"{slug}.yaml")
        assert d.id == expected_id
        assert d.category == "infrastructure"
        assert d.patch is None

    @pytest.mark.parametrize("slug,expected_id", [
        ("winlogbeat-shipper", WINLOGBEAT_ID),
        ("filebeat-shipper", FILEBEAT_ID),
        ("sysmon", SYSMON_ID),
    ])
    def test_each_shipper_depends_on_stack(self, slug, expected_id):
        d = load_descriptor_yaml(INFRA_ROOT / f"{slug}.yaml")
        assert STACK_ID in d.depends_on, (
            f"{expected_id} should depend on the Elastic stack so the "
            f"resolver auto-installs it first"
        )

    def test_catalog_contains_all_four_infrastructure_descriptors(self, loaded_catalog):
        for needed in (STACK_ID, *SHIPPER_IDS):
            assert needed in loaded_catalog, f"{needed} missing from catalog"


# ─────────────────────────────────────────────────────────────────────
# 3. Dependency resolver auto-includes the stack
# ─────────────────────────────────────────────────────────────────────

class TestResolverAutoIncludesStack:
    def test_installing_winlogbeat_alone_pulls_in_stack_first(self, loaded_catalog):
        order = resolve_install_order(loaded_catalog, [WINLOGBEAT_ID])
        assert STACK_ID in order
        assert order.index(STACK_ID) < order.index(WINLOGBEAT_ID)

    def test_installing_all_shippers_pulls_in_stack_first(self, loaded_catalog):
        order = resolve_install_order(loaded_catalog, list(SHIPPER_IDS))
        # Stack must appear exactly once and before every shipper.
        assert order.count(STACK_ID) == 1
        stack_idx = order.index(STACK_ID)
        for shipper in SHIPPER_IDS:
            assert order.index(shipper) > stack_idx, (
                f"{shipper} resolved before the stack — order: {order}"
            )

    def test_installing_stack_alone_works(self, loaded_catalog):
        order = resolve_install_order(loaded_catalog, [STACK_ID])
        assert order == [STACK_ID]


# ─────────────────────────────────────────────────────────────────────
# 4. Probe service — full vs degraded mode
# ─────────────────────────────────────────────────────────────────────

class _FakeKibanaResponse:
    """Tiny stand-in for requests.Response that the probe service uses."""

    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def _plant_stack_facts(facts_root: Path, lab: str, host: str = "elastic01") -> None:
    """Write a HostFacts YAML that looks like the Elastic stack is
    installed and reachable. The Phase 3b probe service reads
    ``installed_boltons`` to discover the stack and
    ``installed_services`` (legacy field) for the endpoint/password."""
    from webapp.backend.services.bolton_facts_service import HostFacts
    facts = HostFacts(
        host=host,
        lab=lab,
        os_family="linux",
        os_version="22.04",
        role="standalone",
        gathered_at=datetime.now(timezone.utc),
        installed_services={
            "kibana_endpoint": "10.0.0.5:5601",
            "es_password": "test-elastic-pw",
            "es_user": "elastic",
        },
        installed_boltons=[STACK_ID],
    )
    lab_dir = facts_root / lab
    lab_dir.mkdir(parents=True, exist_ok=True)
    (lab_dir / f"{host}.yaml").write_text(yaml.safe_dump(facts.model_dump()))


def _kerberoast_vuln_id() -> str:
    """We re-use the existing kerberoastable-svc descriptor as the vuln
    target since it carries an ``exploit_probe_after_patch`` field, which
    the probe service treats as evidence of a probe block."""
    return "bolton.identity-kerberos.kerberoastable-svc"


class TestProbeServiceFullMode:
    def test_full_mode_returns_fired_alert_shape(
        self, isolated_probe_state, monkeypatch
    ):
        """When the stack is installed in the lab AND Kibana returns a
        hit, the probe record carries fired=true + alert_id + fire_time."""
        from webapp.backend.services import bolton_probe_service

        _plant_stack_facts(isolated_probe_state["facts_root"], lab="lab-purple")

        fake_payload = {
            "hits": {
                "hits": [
                    {
                        "_id": "alert-abc-123",
                        "_source": {
                            "@timestamp": "2026-05-19T10:15:00.000Z",
                            "signal": {
                                "rule": {
                                    "rule_id": "897dc6b5-b39f-432a-8d75-d3730d50c782",
                                },
                                "original_event": {
                                    "host": {"name": "dc01"},
                                },
                            },
                        },
                    }
                ]
            }
        }

        def _fake_post(url, **kwargs):
            assert "/api/detection_engine/signals/search" in url
            assert kwargs["auth"] == ("elastic", "test-elastic-pw")
            return _FakeKibanaResponse(200, fake_payload)

        monkeypatch.setattr(bolton_probe_service, "requests", SimpleNamespace(post=_fake_post))

        result = bolton_probe_service.run_probe(
            vuln_id=_kerberoast_vuln_id(),
            lab="lab-purple",
            host="dc01",
            actor="tester",
        )
        record = bolton_probe_service.get_probe(result["probe_job_id"])
        assert record is not None
        assert record["mode"] == "full"
        assert record["fired"] is True
        assert record["alert_id"] == "alert-abc-123"
        assert record["fire_time"] == "2026-05-19T10:15:00.000Z"
        assert record["degraded"] is False

    def test_full_mode_returns_no_alert_when_kibana_empty(
        self, isolated_probe_state, monkeypatch
    ):
        from webapp.backend.services import bolton_probe_service

        _plant_stack_facts(isolated_probe_state["facts_root"], lab="lab-empty")

        def _fake_post(url, **kwargs):
            return _FakeKibanaResponse(200, {"hits": {"hits": []}})

        monkeypatch.setattr(bolton_probe_service, "requests", SimpleNamespace(post=_fake_post))

        result = bolton_probe_service.run_probe(
            vuln_id=_kerberoast_vuln_id(),
            lab="lab-empty",
            host="dc01",
        )
        record = bolton_probe_service.get_probe(result["probe_job_id"])
        assert record["mode"] == "full"
        assert record["fired"] is False
        assert record["alert_id"] is None
        assert record["degraded"] is False
        assert record["result"] == "no-alert"


class TestProbeServiceDegradedFallback:
    def test_degraded_when_stack_not_installed(
        self, isolated_probe_state, monkeypatch
    ):
        """No stack facts planted → degraded mode immediately."""
        from webapp.backend.services import bolton_probe_service

        # No facts planted; requests should NOT even be called.
        def _explode(*a, **kw):
            raise AssertionError("requests.post should not be called in degraded mode")
        monkeypatch.setattr(bolton_probe_service, "requests", SimpleNamespace(post=_explode))

        result = bolton_probe_service.run_probe(
            vuln_id=_kerberoast_vuln_id(),
            lab="lab-no-elastic",
            host="dc01",
        )
        record = bolton_probe_service.get_probe(result["probe_job_id"])
        assert record["mode"] == "degraded"
        assert record["degraded"] is True
        assert record["fired"] is False
        assert record["result"] == "probe-only"

    def test_degraded_when_kibana_connect_fails(
        self, isolated_probe_state, monkeypatch
    ):
        """Stack is installed but the Kibana HTTP call raises."""
        from webapp.backend.services import bolton_probe_service

        _plant_stack_facts(isolated_probe_state["facts_root"], lab="lab-broken")

        def _connect_error(*a, **kw):
            raise ConnectionError("kibana unreachable")
        monkeypatch.setattr(bolton_probe_service, "requests", SimpleNamespace(post=_connect_error))

        result = bolton_probe_service.run_probe(
            vuln_id=_kerberoast_vuln_id(),
            lab="lab-broken",
            host="dc01",
        )
        record = bolton_probe_service.get_probe(result["probe_job_id"])
        assert record["fired"] is False
        assert record["degraded"] is True
        assert record["mode"] == "degraded"
        assert "connect:" in (record.get("error") or "")

    def test_degraded_when_kibana_returns_http_error(
        self, isolated_probe_state, monkeypatch
    ):
        from webapp.backend.services import bolton_probe_service

        _plant_stack_facts(isolated_probe_state["facts_root"], lab="lab-401")

        def _fake_post(url, **kwargs):
            return _FakeKibanaResponse(401, {"error": "unauthorized"})

        monkeypatch.setattr(bolton_probe_service, "requests", SimpleNamespace(post=_fake_post))

        result = bolton_probe_service.run_probe(
            vuln_id=_kerberoast_vuln_id(),
            lab="lab-401",
            host="dc01",
        )
        record = bolton_probe_service.get_probe(result["probe_job_id"])
        assert record["fired"] is False
        assert record["degraded"] is True
        assert record["error"] == "http-401"
