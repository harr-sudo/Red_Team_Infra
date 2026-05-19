"""Bolt-on schema + catalog tests (Phase 1, Agent A).

Coverage:
    - Catalog YAML round-trip — every shipped descriptor validates
    - Schema field-level validators (id, slug, version, CVE, UUID, MITRE IDs)
    - Cross-field invariants (patch_revert iff rollback_supported, etc.)
    - DetectionBlock invariants (no-rule needs fallback template, covered
      needs >= 1 rule)
    - Catalog-level: unique ids, cross-reference validation
    - Dependency resolver: topological order, cycle detection, dedupe of
      transitive deps
    - Conflict checker: bidirectional, dedupe, canonical pair order
"""

from __future__ import annotations

import copy
import textwrap
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from webapp.bolton.catalog import (
    CyclicDependencyError,
    UnknownDescriptorError,
    check_conflicts,
    load_catalog,
    resolve_install_order,
)
from webapp.bolton.schema import (
    BoltOnDescriptor,
    CoverageStatus,
    load_descriptor_yaml,
    validate_cross_references,
    validate_unique_ids,
)


CATALOG_ROOT = Path(__file__).resolve().parents[2] / "webapp" / "bolton" / "catalog"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def all_descriptor_paths() -> list[Path]:
    return sorted(CATALOG_ROOT.rglob("*.yaml"))


@pytest.fixture
def loaded_catalog() -> dict[str, BoltOnDescriptor]:
    return load_catalog(CATALOG_ROOT)


@pytest.fixture
def kerberoastable_raw() -> dict:
    """A valid descriptor dict that tests can mutate without affecting disk."""
    path = CATALOG_ROOT / "identity-kerberos" / "kerberoastable-svc.yaml"
    with path.open() as f:
        return yaml.safe_load(f)


@pytest.fixture
def minimal_descriptor_dict() -> dict:
    """A minimal but valid descriptor as a Python dict.

    Useful for negative tests where we mutate one field at a time.
    """
    return yaml.safe_load(
        textwrap.dedent(
            """
            id: bolton.test.minimal-descriptor
            slug: minimal-descriptor
            name: "Minimal Test Descriptor"
            version: "1.0.0"
            author: "Test"
            last_updated: 2026-05-18
            category: test
            description: "Minimal descriptor used by tests; does nothing meaningful."
            mitre:
              tactic:   { id: TA0006, name: "Credential Access" }
              technique: { id: T1558, name: "Steal or Forge Kerberos Tickets" }
            detection:
              coverage_status: no-rule
              elastic_rules: []
              fallback_rule_template: "templates/test.j2.yml"
              signal_sources: []
            targets:
              supported_os:
                - { family: windows, min_version: "2019" }
              required_roles: [domain_controller]
              required_services: []
            depends_on: []
            conflicts_with: []
            side_effects:
              global: false
              network_visible: false
              reboot_required: false
            install:
              estimated_time_seconds: 10
              steps:
                - { ansible_role: ansible.windows.win_ping, role_vars: {} }
              verify:
                probe: "exit 0"
                timeout_seconds: 5
                expect_exit_code: 0
            uninstall:
              description: "no-op"
              estimated_time_seconds: 5
              steps:
                - { ansible_role: ansible.windows.win_ping, role_vars: {} }
              verify:
                probe: "exit 0"
                timeout_seconds: 5
                expect_exit_code: 0
            patch:
              description: "no-op patch"
              patch_reference: "https://example.com/advisory"
              complexity: low
              rollback_supported: false
              side_effects: []
              steps:
                - { ansible_role: ansible.windows.win_ping, role_vars: {} }
              verify:
                probe: "exit 0"
                timeout_seconds: 5
                expect_exit_code: 0
            cost:
              storage_mb: 0
              cpu_pct: 0
              detectability: quiet
            status: experimental
            """
        )
    )


# ---------------------------------------------------------------------------
# 1. Every shipped descriptor validates
# ---------------------------------------------------------------------------


def test_catalog_root_exists():
    assert CATALOG_ROOT.is_dir(), f"catalog root missing: {CATALOG_ROOT}"


def test_catalog_has_expected_descriptors(all_descriptor_paths):
    """Phase 1 ships 5 worked vuln descriptors; Phase 3b adds 4
    infrastructure-class descriptors (Elastic stack + 3 shippers);
    catalog expansion (task #50) adds 5 more vuln descriptors. The
    catalog grows organically — this test asserts a floor, not a
    ceiling, so adding new descriptors doesn't break the suite."""
    assert len(all_descriptor_paths) >= 14, (
        f"Expected >=14 descriptors; found {len(all_descriptor_paths)}: "
        f"{[p.relative_to(CATALOG_ROOT) for p in all_descriptor_paths]}"
    )


@pytest.mark.parametrize(
    "rel_path",
    [
        "identity-kerberos/kerberoastable-svc.yaml",
        "adcs/esc1-misconfigured-template.yaml",
        "known-cve/printnightmare.yaml",
        "known-cve/zerologon.yaml",
        "protocol-network/llmnr-nbtns-enabled.yaml",
    ],
)
def test_each_descriptor_validates(rel_path):
    descriptor = load_descriptor_yaml(CATALOG_ROOT / rel_path)
    assert isinstance(descriptor, BoltOnDescriptor)
    # Every descriptor we ship has a non-empty install/uninstall/patch block
    assert descriptor.install.steps
    assert descriptor.uninstall.steps
    assert descriptor.patch.steps


def test_catalog_loads_keyed_by_id(loaded_catalog):
    """Asserts the core Phase 1 + Phase 3b descriptors are present.
    Subsequent catalog expansion (task #50) is checked separately
    via len() floors so adding descriptors doesn't break this."""
    required_ids = {
        # Phase 1 vulnerability descriptors
        "bolton.identity-kerberos.kerberoastable-svc",
        "bolton.adcs.esc1-misconfigured-template",
        "bolton.known-cve.printnightmare",
        "bolton.known-cve.zerologon",
        "bolton.protocol-network.llmnr-nbtns-enabled",
        # Phase 3b infrastructure descriptors
        "bolton.infrastructure.elastic-detection-stack",
        "bolton.infrastructure.winlogbeat-shipper",
        "bolton.infrastructure.filebeat-shipper",
        "bolton.infrastructure.sysmon",
    }
    assert required_ids.issubset(set(loaded_catalog.keys())), (
        f"Required IDs missing: {required_ids - set(loaded_catalog.keys())}"
    )


# ---------------------------------------------------------------------------
# 2. Field-level validators — negative tests
# ---------------------------------------------------------------------------


def test_id_must_match_bolton_dotted_pattern(minimal_descriptor_dict):
    minimal_descriptor_dict["id"] = "not.a.bolton.id"
    with pytest.raises(ValidationError) as exc:
        BoltOnDescriptor.model_validate(minimal_descriptor_dict)
    assert "id must match" in str(exc.value)


def test_slug_rejects_uppercase(minimal_descriptor_dict):
    minimal_descriptor_dict["slug"] = "BadSlug"
    with pytest.raises(ValidationError) as exc:
        BoltOnDescriptor.model_validate(minimal_descriptor_dict)
    assert "slug must be lowercase" in str(exc.value)


def test_version_rejects_non_semver(minimal_descriptor_dict):
    minimal_descriptor_dict["version"] = "v1"
    with pytest.raises(ValidationError) as exc:
        BoltOnDescriptor.model_validate(minimal_descriptor_dict)
    assert "semver" in str(exc.value)


def test_cve_format_validation(minimal_descriptor_dict):
    minimal_descriptor_dict["cve"] = ["NOT-A-CVE"]
    with pytest.raises(ValidationError) as exc:
        BoltOnDescriptor.model_validate(minimal_descriptor_dict)
    assert "cve entry" in str(exc.value)


def test_mitre_technique_regex(minimal_descriptor_dict):
    minimal_descriptor_dict["mitre"]["technique"]["id"] = "X9999"
    with pytest.raises(ValidationError) as exc:
        BoltOnDescriptor.model_validate(minimal_descriptor_dict)
    assert "MITRE technique id must match" in str(exc.value)


def test_mitre_can_be_null(minimal_descriptor_dict):
    minimal_descriptor_dict["mitre"] = None
    d = BoltOnDescriptor.model_validate(minimal_descriptor_dict)
    assert d.mitre is None


def test_mitre_subtechnique_must_extend_technique(minimal_descriptor_dict):
    minimal_descriptor_dict["mitre"]["subtechnique"] = {
        "id": "T1059.001",
        "name": "PowerShell",
    }
    # Technique is T1558; subtechnique T1059.001 does not extend it
    with pytest.raises(ValidationError) as exc:
        BoltOnDescriptor.model_validate(minimal_descriptor_dict)
    assert "does not extend technique" in str(exc.value)


def test_elastic_rule_uuid_must_be_uuid(minimal_descriptor_dict):
    minimal_descriptor_dict["detection"]["coverage_status"] = "covered"
    minimal_descriptor_dict["detection"]["fallback_rule_template"] = None
    minimal_descriptor_dict["detection"]["elastic_rules"] = [
        {
            "rule_uuid": "not-a-uuid",
            "rule_name": "X",
            "coverage": "full",
            "confidence": "high",
            "last_validated": "2026-04-15",
        }
    ]
    with pytest.raises(ValidationError) as exc:
        BoltOnDescriptor.model_validate(minimal_descriptor_dict)
    assert "rule_uuid must be a UUID" in str(exc.value)


def test_no_rule_requires_fallback_template(minimal_descriptor_dict):
    minimal_descriptor_dict["detection"]["coverage_status"] = "no-rule"
    minimal_descriptor_dict["detection"]["fallback_rule_template"] = None
    with pytest.raises(ValidationError) as exc:
        BoltOnDescriptor.model_validate(minimal_descriptor_dict)
    assert "fallback_rule_template is required" in str(exc.value)


def test_covered_requires_at_least_one_rule(minimal_descriptor_dict):
    minimal_descriptor_dict["detection"]["coverage_status"] = "covered"
    minimal_descriptor_dict["detection"]["elastic_rules"] = []
    with pytest.raises(ValidationError) as exc:
        BoltOnDescriptor.model_validate(minimal_descriptor_dict)
    assert "requires at least one elastic_rules entry" in str(exc.value)


def test_invalid_enum_rejected(minimal_descriptor_dict):
    minimal_descriptor_dict["cost"]["detectability"] = "earsplitting"
    with pytest.raises(ValidationError):
        BoltOnDescriptor.model_validate(minimal_descriptor_dict)


def test_unknown_field_rejected(minimal_descriptor_dict):
    minimal_descriptor_dict["some_new_field"] = "oops"
    with pytest.raises(ValidationError) as exc:
        BoltOnDescriptor.model_validate(minimal_descriptor_dict)
    assert "Extra inputs are not permitted" in str(exc.value) or "extra" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# 3. Cross-field invariants
# ---------------------------------------------------------------------------


def test_patch_revert_required_when_rollback_supported(minimal_descriptor_dict):
    minimal_descriptor_dict["patch"]["rollback_supported"] = True
    # No patch_revert in minimal descriptor
    with pytest.raises(ValidationError) as exc:
        BoltOnDescriptor.model_validate(minimal_descriptor_dict)
    assert "patch_revert is missing" in str(exc.value)


def test_patch_revert_forbidden_when_rollback_unsupported(minimal_descriptor_dict):
    # rollback_supported is False; adding patch_revert is illegal
    minimal_descriptor_dict["patch_revert"] = {
        "description": "should not be allowed",
        "estimated_time_seconds": 5,
        "steps": [{"ansible_role": "ansible.windows.win_ping", "role_vars": {}}],
        "verify": {"probe": "exit 0", "timeout_seconds": 5, "expect_exit_code": 0},
    }
    with pytest.raises(ValidationError) as exc:
        BoltOnDescriptor.model_validate(minimal_descriptor_dict)
    assert "rollback_supported is False" in str(exc.value)


def test_self_dependency_rejected(minimal_descriptor_dict):
    minimal_descriptor_dict["depends_on"] = [minimal_descriptor_dict["id"]]
    with pytest.raises(ValidationError) as exc:
        BoltOnDescriptor.model_validate(minimal_descriptor_dict)
    assert "cannot depend on itself" in str(exc.value)


def test_depends_and_conflicts_overlap_rejected(minimal_descriptor_dict):
    minimal_descriptor_dict["depends_on"] = ["bolton.test.other"]
    minimal_descriptor_dict["conflicts_with"] = ["bolton.test.other"]
    with pytest.raises(ValidationError) as exc:
        BoltOnDescriptor.model_validate(minimal_descriptor_dict)
    assert "depends_on and" in str(exc.value)


# ---------------------------------------------------------------------------
# 4. Catalog-level validation
# ---------------------------------------------------------------------------


def test_duplicate_id_detected(minimal_descriptor_dict):
    a = BoltOnDescriptor.model_validate(minimal_descriptor_dict)
    b = BoltOnDescriptor.model_validate(copy.deepcopy(minimal_descriptor_dict))
    with pytest.raises(ValueError) as exc:
        validate_unique_ids([a, b])
    assert "Duplicate descriptor id" in str(exc.value)


def test_cross_reference_dangling_dep_detected(minimal_descriptor_dict):
    d = copy.deepcopy(minimal_descriptor_dict)
    d["depends_on"] = ["bolton.does-not-exist.nothing"]
    desc = BoltOnDescriptor.model_validate(d)
    with pytest.raises(ValueError) as exc:
        validate_cross_references([desc])
    assert "references unknown id" in str(exc.value)


def test_cross_reference_dangling_conflict_detected(minimal_descriptor_dict):
    d = copy.deepcopy(minimal_descriptor_dict)
    d["conflicts_with"] = ["bolton.does-not-exist.nothing"]
    desc = BoltOnDescriptor.model_validate(d)
    with pytest.raises(ValueError) as exc:
        validate_cross_references([desc])
    assert "references unknown id" in str(exc.value)


def test_loaded_catalog_passes_cross_reference(loaded_catalog):
    """The 5 shipped descriptors are independent — no deps, no conflicts."""
    validate_cross_references(list(loaded_catalog.values()))


# ---------------------------------------------------------------------------
# 5. Dependency resolver
# ---------------------------------------------------------------------------


def _make_catalog(*pairs: tuple[str, list[str]]) -> dict[str, BoltOnDescriptor]:
    """Build a tiny in-memory catalog. Each pair is (id, depends_on)."""
    base = yaml.safe_load(
        textwrap.dedent(
            """
            slug: xx
            name: "Test Descriptor"
            version: "1.0.0"
            author: "Tester"
            last_updated: 2026-05-18
            category: test
            description: "Synthetic descriptor for resolver tests, padded length."
            mitre:
              tactic:    { id: TA0006, name: "Credential Access" }
              technique: { id: T1558,  name: "Steal or Forge Kerberos Tickets" }
            detection:
              coverage_status: no-rule
              elastic_rules: []
              fallback_rule_template: "templates/test.j2.yml"
              signal_sources: []
            targets:
              supported_os: [{ family: windows, min_version: "2019" }]
              required_roles: [domain_controller]
              required_services: []
            side_effects: { global: false, network_visible: false, reboot_required: false }
            install:
              estimated_time_seconds: 10
              steps: [{ ansible_role: ansible.windows.win_ping, role_vars: {} }]
              verify: { probe: "x", timeout_seconds: 5, expect_exit_code: 0 }
            uninstall:
              description: "x"
              estimated_time_seconds: 5
              steps: [{ ansible_role: ansible.windows.win_ping, role_vars: {} }]
              verify: { probe: "x", timeout_seconds: 5, expect_exit_code: 0 }
            patch:
              description: "x"
              patch_reference: "https://example.com/advisory"
              complexity: low
              rollback_supported: false
              side_effects: []
              steps: [{ ansible_role: ansible.windows.win_ping, role_vars: {} }]
              verify: { probe: "x", timeout_seconds: 5, expect_exit_code: 0 }
            cost: { storage_mb: 0, cpu_pct: 0, detectability: quiet }
            status: experimental
            """
        )
    )
    out: dict[str, BoltOnDescriptor] = {}
    for vid, deps in pairs:
        body = copy.deepcopy(base)
        body["id"] = vid
        tail = vid.split(".")[-1]
        # Slug regex requires >=2 chars (^[a-z0-9][a-z0-9-]*[a-z0-9]$);
        # pad single-char tails to "tail-x" for test fixtures.
        body["slug"] = tail if len(tail) >= 2 else f"{tail}-x"
        body["depends_on"] = list(deps)
        body["conflicts_with"] = []
        out[vid] = BoltOnDescriptor.model_validate(body)
    return out


def test_resolver_empty_targets():
    catalog = _make_catalog(("bolton.t.a", []))
    assert resolve_install_order(catalog, []) == []


def test_resolver_single_node():
    catalog = _make_catalog(("bolton.t.a", []))
    assert resolve_install_order(catalog, ["bolton.t.a"]) == ["bolton.t.a"]


def test_resolver_linear_chain():
    """A <- B <- C: install order should be [A, B, C]."""
    catalog = _make_catalog(
        ("bolton.t.a", []),
        ("bolton.t.b", ["bolton.t.a"]),
        ("bolton.t.c", ["bolton.t.b"]),
    )
    order = resolve_install_order(catalog, ["bolton.t.c"])
    assert order == ["bolton.t.a", "bolton.t.b", "bolton.t.c"]


def test_resolver_diamond():
    """A <- B, A <- C, B <- D, C <- D. A must come first; D last."""
    catalog = _make_catalog(
        ("bolton.t.a", []),
        ("bolton.t.b", ["bolton.t.a"]),
        ("bolton.t.c", ["bolton.t.a"]),
        ("bolton.t.d", ["bolton.t.b", "bolton.t.c"]),
    )
    order = resolve_install_order(catalog, ["bolton.t.d"])
    assert order[0] == "bolton.t.a"
    assert order[-1] == "bolton.t.d"
    assert order.index("bolton.t.b") < order.index("bolton.t.d")
    assert order.index("bolton.t.c") < order.index("bolton.t.d")


def test_resolver_dedupes_transitive():
    """Requesting both B and C (both depending on A) returns A once."""
    catalog = _make_catalog(
        ("bolton.t.a", []),
        ("bolton.t.b", ["bolton.t.a"]),
        ("bolton.t.c", ["bolton.t.a"]),
    )
    order = resolve_install_order(catalog, ["bolton.t.b", "bolton.t.c"])
    assert order.count("bolton.t.a") == 1
    assert len(order) == 3


def test_resolver_cycle_detected():
    catalog = _make_catalog(
        ("bolton.t.a", ["bolton.t.b"]),
        ("bolton.t.b", ["bolton.t.a"]),
    )
    with pytest.raises(CyclicDependencyError) as exc:
        resolve_install_order(catalog, ["bolton.t.a"])
    assert "bolton.t.a" in str(exc.value)
    assert "bolton.t.b" in str(exc.value)


def test_resolver_unknown_id():
    catalog = _make_catalog(("bolton.t.a", []))
    with pytest.raises(UnknownDescriptorError):
        resolve_install_order(catalog, ["bolton.t.missing"])


# ---------------------------------------------------------------------------
# 6. Conflict checker
# ---------------------------------------------------------------------------


def _make_catalog_with_conflicts(
    *pairs: tuple[str, list[str]],
) -> dict[str, BoltOnDescriptor]:
    base = yaml.safe_load(
        textwrap.dedent(
            """
            slug: xx
            name: "Test Descriptor"
            version: "1.0.0"
            author: "Tester"
            last_updated: 2026-05-18
            category: test
            description: "Synthetic descriptor for conflict tests, padded length."
            mitre: null
            detection:
              coverage_status: no-rule
              elastic_rules: []
              fallback_rule_template: "templates/test.j2.yml"
              signal_sources: []
            targets:
              supported_os: [{ family: windows, min_version: "2019" }]
              required_roles: [domain_controller]
              required_services: []
            side_effects: { global: false, network_visible: false, reboot_required: false }
            install:
              estimated_time_seconds: 10
              steps: [{ ansible_role: ansible.windows.win_ping, role_vars: {} }]
              verify: { probe: "x", timeout_seconds: 5, expect_exit_code: 0 }
            uninstall:
              description: "x"
              estimated_time_seconds: 5
              steps: [{ ansible_role: ansible.windows.win_ping, role_vars: {} }]
              verify: { probe: "x", timeout_seconds: 5, expect_exit_code: 0 }
            patch:
              description: "x"
              patch_reference: "https://example.com/advisory"
              complexity: low
              rollback_supported: false
              side_effects: []
              steps: [{ ansible_role: ansible.windows.win_ping, role_vars: {} }]
              verify: { probe: "x", timeout_seconds: 5, expect_exit_code: 0 }
            cost: { storage_mb: 0, cpu_pct: 0, detectability: quiet }
            status: experimental
            """
        )
    )
    out: dict[str, BoltOnDescriptor] = {}
    for vid, conflicts in pairs:
        body = copy.deepcopy(base)
        body["id"] = vid
        _tail = vid.split(".")[-1]
        body["slug"] = _tail if len(_tail) >= 2 else f"{_tail}-x"
        body["depends_on"] = []
        body["conflicts_with"] = list(conflicts)
        out[vid] = BoltOnDescriptor.model_validate(body)
    return out


def test_conflicts_empty_set():
    catalog = _make_catalog_with_conflicts(("bolton.t.a", []))
    assert check_conflicts(catalog, ["bolton.t.a"]) == []


def test_conflicts_unidirectional_still_detected():
    """A.conflicts_with includes B; B has no opinion. Still a conflict."""
    catalog = _make_catalog_with_conflicts(
        ("bolton.t.a", ["bolton.t.b"]),
        ("bolton.t.b", []),
    )
    pairs = check_conflicts(catalog, ["bolton.t.a", "bolton.t.b"])
    assert pairs == [("bolton.t.a", "bolton.t.b")]


def test_conflicts_bidirectional_dedupes():
    """A.conflicts_with B AND B.conflicts_with A: still one pair only."""
    catalog = _make_catalog_with_conflicts(
        ("bolton.t.a", ["bolton.t.b"]),
        ("bolton.t.b", ["bolton.t.a"]),
    )
    pairs = check_conflicts(catalog, ["bolton.t.a", "bolton.t.b"])
    assert pairs == [("bolton.t.a", "bolton.t.b")]


def test_conflicts_pair_is_canonicalized():
    """Pair is reported with lexicographically smaller id first."""
    catalog = _make_catalog_with_conflicts(
        ("bolton.t.zeta", []),
        ("bolton.t.alpha", ["bolton.t.zeta"]),
    )
    pairs = check_conflicts(catalog, ["bolton.t.zeta", "bolton.t.alpha"])
    assert pairs == [("bolton.t.alpha", "bolton.t.zeta")]


def test_conflicts_unrelated_set_returns_empty():
    catalog = _make_catalog_with_conflicts(
        ("bolton.t.a", ["bolton.t.x"]),
        ("bolton.t.b", []),
        ("bolton.t.x", []),
    )
    # Only a + b in the install set; x isn't there
    assert check_conflicts(catalog, ["bolton.t.a", "bolton.t.b"]) == []


def test_conflicts_unknown_id_raises():
    catalog = _make_catalog_with_conflicts(("bolton.t.a", []))
    with pytest.raises(UnknownDescriptorError):
        check_conflicts(catalog, ["bolton.t.a", "bolton.t.missing"])


def test_conflicts_dedupes_repeated_ids_in_install_set():
    catalog = _make_catalog_with_conflicts(
        ("bolton.t.a", ["bolton.t.b"]),
        ("bolton.t.b", []),
    )
    pairs = check_conflicts(catalog, ["bolton.t.a", "bolton.t.b", "bolton.t.a"])
    assert pairs == [("bolton.t.a", "bolton.t.b")]


# ---------------------------------------------------------------------------
# 7. Real-world: malformed YAML inputs
# ---------------------------------------------------------------------------


def test_malformed_yaml_raises(tmp_path):
    bad = tmp_path / "broken.yaml"
    bad.write_text("this: is:\n  - not: valid: yaml\n")
    with pytest.raises(yaml.YAMLError):
        load_descriptor_yaml(bad)


def test_yaml_top_level_must_be_mapping(tmp_path):
    bad = tmp_path / "list.yaml"
    bad.write_text("- this\n- is\n- a\n- list\n")
    with pytest.raises(ValueError) as exc:
        load_descriptor_yaml(bad)
    assert "must be a YAML mapping" in str(exc.value)


def test_missing_required_field_rejected(minimal_descriptor_dict):
    del minimal_descriptor_dict["install"]
    with pytest.raises(ValidationError) as exc:
        BoltOnDescriptor.model_validate(minimal_descriptor_dict)
    assert "install" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# 8. Shipped-descriptor semantic spot checks (the descriptors are anchors)
# ---------------------------------------------------------------------------


def test_kerberoastable_descriptor_has_real_elastic_uuid(loaded_catalog):
    d = loaded_catalog["bolton.identity-kerberos.kerberoastable-svc"]
    uuids = {r.rule_uuid for r in d.detection.elastic_rules}
    assert "897dc6b5-b39f-432a-8d75-d3730d50c782" in uuids


def test_printnightmare_descriptor_has_two_cves(loaded_catalog):
    d = loaded_catalog["bolton.known-cve.printnightmare"]
    assert sorted(d.cve) == ["CVE-2021-1675", "CVE-2021-34527"]


def test_zerologon_has_no_patch_revert(loaded_catalog):
    """ZeroLogon's KB cannot be cleanly removed — patch_revert must be null."""
    d = loaded_catalog["bolton.known-cve.zerologon"]
    assert d.patch.rollback_supported is False
    assert d.patch_revert is None


def test_esc1_has_no_rule_coverage(loaded_catalog):
    """ADCS ESC1 has no direct Elastic rule today — must point at fallback."""
    d = loaded_catalog["bolton.adcs.esc1-misconfigured-template"]
    assert d.detection.coverage_status == CoverageStatus.NO_RULE
    assert d.detection.fallback_rule_template is not None


def test_llmnr_has_t1557_subtechnique(loaded_catalog):
    d = loaded_catalog["bolton.protocol-network.llmnr-nbtns-enabled"]
    assert d.mitre is not None
    assert d.mitre.subtechnique is not None
    assert d.mitre.subtechnique.id == "T1557.001"


# ---------------------------------------------------------------------------
# 9. Pydantic v2 sanity
# ---------------------------------------------------------------------------


def test_descriptor_model_dump_round_trip(loaded_catalog):
    """model_dump() should produce a dict that re-validates to an equal model."""
    d = loaded_catalog["bolton.identity-kerberos.kerberoastable-svc"]
    dumped = d.model_dump(mode="json")
    d2 = BoltOnDescriptor.model_validate(dumped)
    assert d2.id == d.id
    assert d2.detection.coverage_status == d.detection.coverage_status
    assert d2.patch.rollback_supported == d.patch.rollback_supported


def test_global_alias_round_trip(minimal_descriptor_dict):
    """SideEffects' `global` (Python keyword) round-trips via the alias."""
    descriptor = BoltOnDescriptor.model_validate(minimal_descriptor_dict)
    dumped = descriptor.model_dump(by_alias=True, mode="json")
    assert dumped["side_effects"]["global"] is False
    # Re-validate to confirm the alias works as input too
    BoltOnDescriptor.model_validate(dumped)
