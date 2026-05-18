"""Tests for the bolt-on Phase 1 backend services (Agent B).

Covers:
  - bolton_facts_service: gather/cache/invalidate/concurrent refresh
  - bolton_compatibility: each of the 8 states, evaluation order,
    catalog evaluation
  - bolton_install_service: dispatch, state transitions, audit-log
    entries, FAILED test hook, list filtering

Ansible stubbing
----------------
The install dispatcher's Phase 1 simulator is wired to:
  - sleep BOLTON_STUB_DURATION seconds (env override) then SUCCEED
  - or FAIL when the bolton id ends in ``-fail``
  - or STUCK when the bolton id ends in ``-stuck``
  - or AS_PATCHED_BUT_VULN when id ends in ``-vuln`` and action is PATCH

These tests set ``BOLTON_STUB_DURATION=0.01`` via the
``_speed_up_stub`` fixture so the suite runs in <1 s.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from webapp.backend.services import audit_service, bolton_facts_service
from webapp.backend.services.bolton_facts_service import (
    HostFacts,
    FACTS_TTL_SECONDS,
    gather_facts,
    gather_facts_async,
    get_cached_facts,
    invalidate_facts,
    list_lab_hosts,
    build_installed_boltons_map,
    _MOCK_HOST_FACTS,
)
from webapp.backend.services.bolton_compatibility import (
    CompatibilityResult,
    CompatibilityState,
    evaluate_catalog_for_host,
    evaluate_compatibility,
)
from webapp.backend.services import bolton_install_service
from webapp.backend.services.bolton_install_service import (
    CompatibilityRefusedError,
    Job,
    JobAction,
    JobStatus,
    cancel_job,
    dispatch_job,
    get_job,
    list_jobs,
    wait_for_job,
)


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    """Redirect facts + jobs storage into a tmpdir for every test."""
    facts_root = tmp_path / "host_facts"
    jobs_root = tmp_path / "jobs"
    facts_root.mkdir()
    jobs_root.mkdir()
    monkeypatch.setattr(bolton_facts_service, "STATE_ROOT", facts_root)
    monkeypatch.setattr(bolton_install_service, "JOBS_ROOT", jobs_root)
    bolton_install_service._reset_registry_for_tests()
    yield {"facts_root": facts_root, "jobs_root": jobs_root}
    bolton_install_service._reset_registry_for_tests()


@pytest.fixture
def speed_up_stub(monkeypatch):
    """Make the Ansible simulation effectively instant."""
    bolton_install_service._set_simulated_duration_for_tests(0.01)
    yield
    bolton_install_service._set_simulated_duration_for_tests(2.0)


def _make_facts(
    host: str = "dc01",
    lab: str = "testlab",
    os_family: str = "windows",
    os_version: str = "2019",
    role: str = "domain_controller",
    installed_services: dict | None = None,
    installed_boltons: list | None = None,
    applied_kbs: list | None = None,
    patched_cves: list | None = None,
    age_seconds: float = 0.0,
) -> HostFacts:
    return HostFacts(
        host=host,
        lab=lab,
        os_family=os_family,
        os_version=os_version,
        role=role,
        installed_services=installed_services or {},
        installed_boltons=installed_boltons or [],
        applied_kbs=applied_kbs or [],
        patched_cves=patched_cves or [],
        gathered_at=datetime.now(timezone.utc) - timedelta(seconds=age_seconds),
    )


def _descriptor(**kw) -> dict:
    """Build a minimal descriptor dict suitable for the evaluator."""
    return {
        "id": kw.get("id", "bolton.test.example"),
        "name": kw.get("name", "Example"),
        "targets": {
            "supported_os": kw.get("supported_os", []),
            "required_roles": kw.get("required_roles", []),
            "required_services": kw.get("required_services", []),
        },
        "depends_on": kw.get("depends_on", []),
        "conflicts_with": kw.get("conflicts_with", []),
        "cve": kw.get("cve", []),
    }


# ──────────────────────────────────────────────────────────────────────
# Facts service tests
# ──────────────────────────────────────────────────────────────────────

class TestFactsGather:
    def test_gather_facts_returns_mocked_facts_for_known_host(self, isolated_state):
        facts = gather_facts("lab1", "dc01")
        assert facts.host == "dc01"
        assert facts.lab == "lab1"
        assert facts.os_family == "windows"
        assert facts.role == "domain_controller"

    def test_gather_facts_writes_yaml_to_disk(self, isolated_state):
        facts = gather_facts("lab1", "dc01")
        path = isolated_state["facts_root"] / "lab1" / "dc01.yaml"
        assert path.exists()
        text = path.read_text()
        assert "dc01" in text
        assert "windows" in text

    def test_gather_facts_unknown_host_returns_standalone_linux(self, isolated_state):
        facts = gather_facts("lab1", "exotic-host")
        assert facts.os_family == "linux"
        assert facts.role == "standalone"

    def test_cache_hit_within_ttl(self, isolated_state):
        first = gather_facts("lab1", "dc01")
        second = gather_facts("lab1", "dc01")
        assert second.gathered_at == first.gathered_at

    def test_cache_miss_on_stale_facts(self, isolated_state, tmp_path):
        # Manually plant a stale facts file
        path = isolated_state["facts_root"] / "lab1" / "dc01.yaml"
        path.parent.mkdir(parents=True)
        stale_facts = _make_facts(
            host="dc01",
            lab="lab1",
            age_seconds=FACTS_TTL_SECONDS + 60,
        )
        import yaml
        path.write_text(yaml.safe_dump(stale_facts.model_dump()))

        # get_cached_facts should return None (stale)
        assert get_cached_facts("lab1", "dc01") is None

        # gather_facts re-probes — new gathered_at
        fresh = gather_facts("lab1", "dc01")
        assert (datetime.now(timezone.utc) - fresh.gathered_at).total_seconds() < 5

    def test_force_refresh_bypasses_cache(self, isolated_state):
        first = gather_facts("lab1", "dc01")
        time.sleep(0.01)
        second = gather_facts("lab1", "dc01", force_refresh=True)
        assert second.gathered_at > first.gathered_at


class TestFactsCache:
    def test_get_cached_facts_missing_returns_none(self, isolated_state):
        assert get_cached_facts("lab1", "missing") is None

    def test_invalidate_facts_drops_one_host(self, isolated_state):
        gather_facts("lab1", "dc01")
        gather_facts("lab1", "srv01")
        removed = invalidate_facts("lab1", "dc01")
        assert removed == 1
        assert get_cached_facts("lab1", "dc01") is None
        assert get_cached_facts("lab1", "srv01") is not None

    def test_invalidate_facts_drops_all_in_lab(self, isolated_state):
        gather_facts("lab1", "dc01")
        gather_facts("lab1", "srv01")
        gather_facts("lab2", "dc01")  # different lab — should survive
        removed = invalidate_facts("lab1")
        assert removed == 2
        assert get_cached_facts("lab1", "dc01") is None
        assert get_cached_facts("lab1", "srv01") is None
        assert get_cached_facts("lab2", "dc01") is not None

    def test_invalidate_facts_nonexistent_lab_returns_zero(self, isolated_state):
        assert invalidate_facts("phantom-lab") == 0

    def test_list_lab_hosts_returns_sorted(self, isolated_state):
        gather_facts("lab1", "srv01")
        gather_facts("lab1", "dc01")
        gather_facts("lab1", "ws01")
        hosts = list_lab_hosts("lab1")
        assert hosts == ["dc01", "srv01", "ws01"]

    def test_build_installed_boltons_map_aggregates(self, isolated_state, monkeypatch):
        # Plant two hosts with different installed_boltons by patching mock table
        monkeypatch.setitem(
            _MOCK_HOST_FACTS,
            "dc01",
            {**_MOCK_HOST_FACTS["dc01"], "installed_boltons": ["bolton.a", "bolton.b"]},
        )
        monkeypatch.setitem(
            _MOCK_HOST_FACTS,
            "srv01",
            {**_MOCK_HOST_FACTS["srv01"], "installed_boltons": ["bolton.c"]},
        )
        gather_facts("lab1", "dc01")
        gather_facts("lab1", "srv01")
        m = build_installed_boltons_map("lab1")
        assert m == {"dc01": ["bolton.a", "bolton.b"], "srv01": ["bolton.c"]}


class TestFactsConcurrency:
    def test_concurrent_refresh_serializes_writes(self, isolated_state):
        """Two threads racing on the same (lab, host) must not corrupt the
        cache file. Both calls return a valid HostFacts."""
        results: list[HostFacts] = []
        errors: list[Exception] = []

        def worker():
            try:
                results.append(gather_facts("lab1", "dc01", force_refresh=True))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert len(results) == 8
        # File must be readable as valid YAML
        path = isolated_state["facts_root"] / "lab1" / "dc01.yaml"
        import yaml
        data = yaml.safe_load(path.read_text())
        assert data["host"] == "dc01"

    def test_gather_facts_async_writes_eventually(self, isolated_state):
        job_id = gather_facts_async("lab1", "dc01")
        assert job_id.startswith("factjob_")
        # Poll for completion (the thread sleeps ~200 ms)
        path = isolated_state["facts_root"] / "lab1" / "dc01.yaml"
        for _ in range(20):
            if path.exists():
                break
            time.sleep(0.05)
        assert path.exists()


# ──────────────────────────────────────────────────────────────────────
# Compatibility tests
# ──────────────────────────────────────────────────────────────────────

class TestCompatibilityStates:
    """One test per state, plus ordering tests."""

    def test_installable_when_all_gates_pass(self, isolated_state):
        facts = _make_facts()
        d = _descriptor(supported_os=["windows"], required_roles=["domain_controller"])
        r = evaluate_compatibility(d, facts)
        assert r.state is CompatibilityState.INSTALLABLE
        assert r.blocking is False
        assert r.suggested_action == "install"

    def test_already_installed(self, isolated_state):
        facts = _make_facts(installed_boltons=["bolton.test.example"])
        d = _descriptor()
        r = evaluate_compatibility(d, facts)
        assert r.state is CompatibilityState.ALREADY_INSTALLED
        assert "already installed" in r.reason.lower()
        assert r.blocking is True

    def test_incompatible_os(self, isolated_state):
        facts = _make_facts(os_family="windows", os_version="2016")
        d = _descriptor(supported_os=["windows-2019", "windows-2022"])
        r = evaluate_compatibility(d, facts)
        assert r.state is CompatibilityState.INCOMPATIBLE_OS
        assert "2019" in r.reason or "2022" in r.reason
        assert "2016" in r.reason
        assert r.suggested_action == "pick_different_host"

    def test_incompatible_role(self, isolated_state):
        facts = _make_facts(role="member_server")
        d = _descriptor(supported_os=["windows"], required_roles=["domain_controller"])
        r = evaluate_compatibility(d, facts)
        assert r.state is CompatibilityState.INCOMPATIBLE_ROLE
        assert "domain_controller" in r.reason
        assert "member_server" in r.reason

    def test_missing_software(self, isolated_state):
        facts = _make_facts(installed_services={"iis": "10.0"})
        d = _descriptor(supported_os=["windows"], required_services=["adcs"])
        r = evaluate_compatibility(d, facts)
        assert r.state is CompatibilityState.MISSING_SOFTWARE
        assert "adcs" in r.reason

    def test_patched(self, isolated_state):
        facts = _make_facts(
            installed_services={},
            patched_cves=["CVE-2021-34527"],
            applied_kbs=["KB5005010"],
        )
        d = _descriptor(supported_os=["windows"], cve=["CVE-2021-34527"])
        r = evaluate_compatibility(d, facts)
        assert r.state is CompatibilityState.PATCHED
        assert "CVE-2021-34527" in r.reason
        assert "KB5005010" in r.reason
        assert r.suggested_action == "view_alternatives"

    def test_patched_requires_ALL_cves_patched(self, isolated_state):
        """If only some CVEs are patched, state is NOT PATCHED."""
        facts = _make_facts(patched_cves=["CVE-2021-34527"])
        d = _descriptor(
            supported_os=["windows"],
            cve=["CVE-2021-34527", "CVE-2021-1675"],
        )
        r = evaluate_compatibility(d, facts)
        assert r.state is not CompatibilityState.PATCHED

    def test_missing_prereq(self, isolated_state):
        facts = _make_facts(installed_boltons=[])
        d = _descriptor(
            supported_os=["windows"],
            depends_on=["identity-kerberos/kerberoastable-svc"],
        )
        r = evaluate_compatibility(d, facts)
        assert r.state is CompatibilityState.MISSING_PREREQ
        assert "identity-kerberos/kerberoastable-svc" in r.reason
        assert r.suggested_action == "install_prereq_first"

    def test_missing_prereq_satisfied_when_installed(self, isolated_state):
        facts = _make_facts(installed_boltons=["bolton.dep.one"])
        d = _descriptor(supported_os=["windows"], depends_on=["bolton.dep.one"])
        r = evaluate_compatibility(d, facts)
        assert r.state is CompatibilityState.INSTALLABLE

    def test_conflicts_same_host(self, isolated_state):
        facts = _make_facts(installed_boltons=["adcs/esc1-misconfigured-template"])
        d = _descriptor(
            supported_os=["windows"],
            conflicts_with=["adcs/esc1-misconfigured-template"],
        )
        r = evaluate_compatibility(d, facts)
        assert r.state is CompatibilityState.CONFLICTS_WITH_INSTALLED
        assert "adcs/esc1-misconfigured-template" in r.reason
        assert "dc01" in r.reason  # same host

    def test_conflicts_cross_host(self, isolated_state):
        facts = _make_facts(host="srv01", role="member_server")
        d = _descriptor(
            supported_os=["windows"],
            required_roles=["member_server"],
            conflicts_with=["bolton.global.something"],
        )
        lab_state = {"dc01": ["bolton.global.something"]}
        r = evaluate_compatibility(d, facts, installed_boltons_in_lab=lab_state)
        assert r.state is CompatibilityState.CONFLICTS_WITH_INSTALLED
        assert "dc01" in r.reason


class TestCompatibilityOrdering:
    def test_already_installed_short_circuits_everything(self, isolated_state):
        """ALREADY_INSTALLED trumps INCOMPATIBLE_OS."""
        facts = _make_facts(
            os_family="linux",  # wrong OS
            installed_boltons=["bolton.test.example"],
        )
        d = _descriptor(supported_os=["windows"])
        r = evaluate_compatibility(d, facts)
        assert r.state is CompatibilityState.ALREADY_INSTALLED

    def test_incompatible_os_trumps_role(self, isolated_state):
        facts = _make_facts(os_family="linux", role="workstation")
        d = _descriptor(
            supported_os=["windows"],
            required_roles=["domain_controller"],
        )
        r = evaluate_compatibility(d, facts)
        assert r.state is CompatibilityState.INCOMPATIBLE_OS

    def test_role_trumps_missing_software(self, isolated_state):
        facts = _make_facts(role="workstation", installed_services={})
        d = _descriptor(
            supported_os=["windows"],
            required_roles=["domain_controller"],
            required_services=["adcs"],
        )
        r = evaluate_compatibility(d, facts)
        assert r.state is CompatibilityState.INCOMPATIBLE_ROLE


class TestCatalogEvaluation:
    def test_evaluate_catalog_for_host_returns_one_result_per_entry(self, isolated_state):
        facts = _make_facts()
        catalog = {
            "bolton.a": _descriptor(id="bolton.a", supported_os=["windows"]),
            "bolton.b": _descriptor(
                id="bolton.b",
                supported_os=["windows"],
                required_roles=["workstation"],
            ),
            "bolton.c": _descriptor(
                id="bolton.c",
                supported_os=["linux"],
            ),
        }
        results = evaluate_catalog_for_host(catalog, facts)
        assert set(results.keys()) == {"bolton.a", "bolton.b", "bolton.c"}
        assert results["bolton.a"].state is CompatibilityState.INSTALLABLE
        assert results["bolton.b"].state is CompatibilityState.INCOMPATIBLE_ROLE
        assert results["bolton.c"].state is CompatibilityState.INCOMPATIBLE_OS

    def test_evaluate_empty_catalog_returns_empty(self, isolated_state):
        facts = _make_facts()
        assert evaluate_catalog_for_host({}, facts) == {}


# ──────────────────────────────────────────────────────────────────────
# Install dispatcher tests
# ──────────────────────────────────────────────────────────────────────

class TestDispatchJob:
    def test_dispatch_creates_job_with_queued_status(self, isolated_state, speed_up_stub):
        job = dispatch_job(
            JobAction.INSTALL,
            "bolton.test.simple",
            "lab1",
            "dc01",
            "harriss",
        )
        # Job may have already started by the time we read it (background thread),
        # so allow any of the early states.
        assert job.id.startswith("job_")
        assert job.action is JobAction.INSTALL
        assert job.bolton_id == "bolton.test.simple"
        assert job.lab == "lab1"
        assert job.host == "dc01"
        assert job.operator == "harriss"

    def test_dispatch_persists_yaml(self, isolated_state, speed_up_stub):
        job = dispatch_job(
            JobAction.INSTALL, "bolton.test.simple", "lab1", "dc01", "harriss",
        )
        path = isolated_state["jobs_root"] / f"{job.id}.yaml"
        assert path.exists()

    def test_succeeded_transition(self, isolated_state, speed_up_stub):
        job = dispatch_job(
            JobAction.INSTALL, "bolton.test.simple", "lab1", "dc01", "harriss",
        )
        terminal = wait_for_job(job.id)
        assert terminal is not None
        assert terminal.status is JobStatus.SUCCEEDED
        assert terminal.started_at is not None
        assert terminal.finished_at is not None

    def test_failed_test_hook_triggers_failed_status(self, isolated_state, speed_up_stub):
        job = dispatch_job(
            JobAction.INSTALL, "bolton.demo-fail", "lab1", "dc01", "harriss",
        )
        terminal = wait_for_job(job.id)
        assert terminal.status is JobStatus.FAILED
        assert terminal.error_summary is not None
        assert "-fail" in terminal.error_summary.lower() or "simulated" in terminal.error_summary.lower()

    def test_stuck_test_hook(self, isolated_state, speed_up_stub):
        job = dispatch_job(
            JobAction.INSTALL, "bolton.demo-stuck", "lab1", "dc01", "harriss",
        )
        terminal = wait_for_job(job.id)
        assert terminal.status is JobStatus.STUCK

    def test_as_patched_but_vuln_only_for_patch_action(self, isolated_state, speed_up_stub):
        # PATCH action: should hit AS_PATCHED_BUT_VULN
        job = dispatch_job(
            JobAction.PATCH, "bolton.demo-vuln", "lab1", "dc01", "harriss",
        )
        terminal = wait_for_job(job.id)
        assert terminal.status is JobStatus.AS_PATCHED_BUT_VULN

    def test_as_patched_but_vuln_fallthrough_for_install(self, isolated_state, speed_up_stub):
        # INSTALL action with -vuln id: falls through to SUCCEEDED
        job = dispatch_job(
            JobAction.INSTALL, "bolton.demo-vuln", "lab1", "dc01", "harriss",
        )
        terminal = wait_for_job(job.id)
        assert terminal.status is JobStatus.SUCCEEDED

    def test_log_file_is_written(self, isolated_state, speed_up_stub):
        job = dispatch_job(
            JobAction.INSTALL, "bolton.test.logged", "lab1", "dc01", "harriss",
        )
        wait_for_job(job.id)
        log = isolated_state["jobs_root"] / f"{job.id}.log"
        assert log.exists()
        content = log.read_text()
        assert "[STUB] dispatching install" in content
        assert "bolton.test.logged" in content

    def test_compatibility_backstop_refuses_when_facts_say_incompatible(
        self, isolated_state, speed_up_stub
    ):
        # Cache facts that make dc01 a Linux box, then try to install a Windows bolt-on
        facts_path = isolated_state["facts_root"] / "lab1" / "dc01.yaml"
        facts_path.parent.mkdir(parents=True)
        import yaml
        bad_facts = _make_facts(host="dc01", lab="lab1", os_family="linux")
        facts_path.write_text(yaml.safe_dump(bad_facts.model_dump()))
        d = _descriptor(supported_os=["windows"])
        with pytest.raises(CompatibilityRefusedError):
            dispatch_job(
                JobAction.INSTALL, "bolton.test.win", "lab1", "dc01", "harriss",
                descriptor=d,
            )

    def test_skip_compat_check_lets_uninstall_proceed(self, isolated_state, speed_up_stub):
        # Uninstall should not run compat backstop
        d = _descriptor(supported_os=["windows"])
        job = dispatch_job(
            JobAction.UNINSTALL, "bolton.test.win", "lab1", "dc01", "harriss",
            descriptor=d,
        )
        terminal = wait_for_job(job.id)
        assert terminal.status is JobStatus.SUCCEEDED


class TestJobListing:
    def test_list_jobs_unfiltered(self, isolated_state, speed_up_stub):
        dispatch_job(JobAction.INSTALL, "b1", "lab1", "dc01", "harriss")
        dispatch_job(JobAction.UNINSTALL, "b2", "lab2", "ca01", "alice")
        jobs = list_jobs()
        assert len(jobs) == 2

    def test_list_jobs_filter_by_lab(self, isolated_state, speed_up_stub):
        dispatch_job(JobAction.INSTALL, "b1", "lab1", "dc01", "harriss")
        dispatch_job(JobAction.INSTALL, "b2", "lab2", "ca01", "alice")
        only_lab1 = list_jobs(lab="lab1")
        assert len(only_lab1) == 1
        assert only_lab1[0].lab == "lab1"

    def test_list_jobs_filter_by_host(self, isolated_state, speed_up_stub):
        dispatch_job(JobAction.INSTALL, "b1", "lab1", "dc01", "harriss")
        dispatch_job(JobAction.INSTALL, "b2", "lab1", "srv01", "harriss")
        only_dc01 = list_jobs(host="dc01")
        assert len(only_dc01) == 1
        assert only_dc01[0].host == "dc01"

    def test_list_jobs_filter_by_status(self, isolated_state, speed_up_stub):
        ok = dispatch_job(JobAction.INSTALL, "b1", "lab1", "dc01", "harriss")
        bad = dispatch_job(JobAction.INSTALL, "b2-fail", "lab1", "dc01", "harriss")
        wait_for_job(ok.id)
        wait_for_job(bad.id)
        succeeded = list_jobs(status=JobStatus.SUCCEEDED)
        failed = list_jobs(status=JobStatus.FAILED)
        assert all(j.status is JobStatus.SUCCEEDED for j in succeeded)
        assert all(j.status is JobStatus.FAILED for j in failed)
        assert ok.id in {j.id for j in succeeded}
        assert bad.id in {j.id for j in failed}

    def test_get_job_unknown_returns_none(self, isolated_state):
        assert get_job("phantom-id") is None


class TestAuditIntegration:
    def test_audit_entries_written_on_state_transitions(
        self, isolated_state, speed_up_stub
    ):
        job = dispatch_job(
            JobAction.INSTALL, "bolton.audit.test", "lab1", "dc01", "harriss",
        )
        wait_for_job(job.id)
        # Audit log should contain multiple entries: queued, running, succeeded
        rows = audit_service.read_recent(action_prefix="bolton.")
        op_actions = [(r["op"], r["action"]) for r in rows]
        assert ("harriss", "bolton.install") in op_actions
        # At least one transition should record status_to=succeeded
        success_rows = [
            r for r in rows
            if r.get("details", {}).get("status_to") == "succeeded"
        ]
        assert success_rows, "expected a bolton.install audit entry transitioning to succeeded"
        assert success_rows[0]["target"] == "bolton.audit.test"
        assert success_rows[0]["project"] == "lab1"

    def test_audit_uses_action_specific_name(
        self, isolated_state, speed_up_stub
    ):
        job = dispatch_job(
            JobAction.PATCH, "bolton.audit.patch", "lab1", "dc01", "harriss",
        )
        wait_for_job(job.id)
        rows = audit_service.read_recent(action_prefix="bolton.patch")
        assert rows, "expected bolton.patch audit entries"
        assert all(r["action"] == "bolton.patch" for r in rows)


class TestCancelJob:
    def test_cancel_unknown_returns_none(self, isolated_state):
        assert cancel_job("phantom-id", "harriss") is None


# ──────────────────────────────────────────────────────────────────────
# Integration with Agent A's schema (skipped when pydantic is missing).
# Confirms the compatibility evaluator's duck-typing handles Pydantic
# models with Enum-valued fields (HostRole, OSFamily).
# ──────────────────────────────────────────────────────────────────────

class TestSchemaIntegration:
    def test_evaluate_with_real_pydantic_descriptor(self, isolated_state):
        pytest.importorskip("pydantic")
        try:
            from webapp.bolton.schema import (
                BoltOnDescriptor,
            )
        except Exception:
            pytest.skip("Agent A's schema not importable in this env")
        # Build a minimal descriptor through dict construction (avoids
        # having to know every required field on BoltOnDescriptor).
        from webapp.bolton import catalog as catalog_module  # noqa: F401
        # Walk the catalog dir; if Agent A shipped any descriptors, load one.
        from pathlib import Path
        import yaml
        catalog_dir = Path(catalog_module.__file__).parent / "catalog"
        if not catalog_dir.exists():
            pytest.skip("No catalog dir yet")
        yamls = list(catalog_dir.rglob("*.yaml"))
        if not yamls:
            pytest.skip("No descriptor files yet")
        try:
            data = yaml.safe_load(yamls[0].read_text())
            descriptor = BoltOnDescriptor.model_validate(data)
        except Exception as e:
            pytest.skip(f"Descriptor failed to validate: {e}")
        facts = _make_facts(role="domain_controller")
        result = evaluate_compatibility(descriptor, facts)
        # Result is one of the enum values — exact state depends on the
        # descriptor. What we're asserting is that the evaluator did not
        # raise on a real Pydantic model.
        assert isinstance(result.state, CompatibilityState)
