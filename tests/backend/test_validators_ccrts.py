"""Unit tests for the CCRTS-Lab additions to ConfigValidator.

CCRTS is a SINGLE, fully self-contained deployment type (`ccrts`) that
mirrors the upstream spark42/ccrts-lab: one isolated lab, no size tiers,
no C2 integration, no combined modes, no bolt-on flag. These tests cover
the contracts the deploy/config routes rely on:

  1. The `ccrts` deployment DOES NOT require a domain (internal-only,
     reached via the dashboard server jump — no public DNS / SSL).
  2. `ccrts` does NOT require key_pair_name (lab-scoped keys; the operator
     never SSHes directly).
  3. crest_kali_ami_override / crest_windows_ami_override must look like a
     real AMI ID when provided (catches typos before terraform spends 20
     min on the cross-region AMI copy).
  4. project_name should use the `ccrts_` prefix (soft warning only).
  5. is_ccrts_only / is_ccrts helpers stay in sync with the constants.
  6. Regression guard: the removed variants/combined modes/bolt-on flag
     stay removed (no ccrts-mini/ccrts-full/combined-*-ccrts, no
     COMBINED_CCRTS_DEPLOYMENT_TYPES, no is_combined_ccrts_deployment).
"""
from __future__ import annotations

import pytest

import webapp.backend.utils.validators as validators_module
from webapp.backend.utils.validators import (
    ConfigValidator,
    CCRTS_ONLY_DEPLOYMENT_TYPES,
    ALL_CCRTS_DEPLOYMENT_TYPES,
    DOMAIN_REQUIRED_DEPLOYMENT_TYPES,
    GOAD_ONLY_DEPLOYMENT_TYPES,
)


# ----------------------------------------------------------------------------
# Minimal-valid-config helper — keeps each test focused on the CCRTS bits.
# ----------------------------------------------------------------------------

def _base_config(**overrides):
    """Return a minimum-viable config that passes validate_config (for the
    non-CCRTS-specific checks). Tests override the keys they care about."""
    cfg = {
        "project_name": "ccrts_dev_lab_01",
        "environment": "dev",
        "deployment_type": "ccrts",
        "management_cidr_blocks": ["1.2.3.4/32"],
        # Pure ccrts doesn't need key_pair_name; supplying one is harmless.
        "enable_ssl": False,
    }
    cfg.update(overrides)
    return cfg


# ============================================================================
# 1. The single `ccrts` type does NOT require a domain
# ============================================================================

def test_ccrts_deployment_no_domain_required():
    """`ccrts` passes validation without primary_domain_name — the lab is
    internal-only behind the dashboard server jump, so there's no public
    DNS / SSL surface to configure."""
    for dtype in CCRTS_ONLY_DEPLOYMENT_TYPES:
        cfg = _base_config(deployment_type=dtype)
        is_valid, errors = ConfigValidator.validate_config(cfg)
        assert is_valid is True, (
            f"Expected {dtype} to validate without domain, got errors: {errors}"
        )
        # Defensive: requires_domain() must also report False.
        assert ConfigValidator.requires_domain(dtype) is False
        # ccrts must NOT be in the domain-required list.
        assert dtype not in DOMAIN_REQUIRED_DEPLOYMENT_TYPES
        # validate_domain_config alone must short-circuit to True/[].
        ok, dom_errors = ConfigValidator.validate_domain_config(cfg)
        assert ok is True
        assert dom_errors == []


# ============================================================================
# 2. The single `ccrts` type does NOT require key_pair_name
# ============================================================================

def test_ccrts_deployment_no_key_pair_required():
    """ccrts builds a lab-scoped key pair; the operator never SSHes
    directly (dashboard server is the jump), so key_pair_name is optional."""
    cfg = _base_config()  # no key_pair_name
    cfg.pop("key_pair_name", None)
    is_valid, errors = ConfigValidator.validate_config(cfg)
    assert is_valid is True, errors
    assert not any("key_pair_name" in e for e in errors), errors


# ============================================================================
# 3. AMI override format validation
# ============================================================================

@pytest.mark.parametrize("bad_value", [
    "ami_0123456789abcdef",     # underscore instead of dash
    "ami-XYZ",                  # non-hex
    "i-0123456789abcdef",       # instance id, not AMI
    "0123456789abcdef",         # missing prefix
    "ami-",                     # empty hex
])
def test_exam_mirror_requires_valid_ami_ids(bad_value):
    """Bad AMI ID format must be rejected for BOTH override knobs."""
    for field in ("crest_kali_ami_override", "crest_windows_ami_override"):
        cfg = _base_config(**{field: bad_value})
        _, errors = ConfigValidator.validate_ccrts_config(cfg)
        assert any(field in e for e in errors), (
            f"Expected {field} validation error for {bad_value!r}, got: {errors}"
        )


@pytest.mark.parametrize("good_value", [
    "ami-0123456789abcdef0",     # 17-char hex (current AMI format)
    "ami-abc12345",              # 8-char legacy
    "ami-0",                     # minimal hex
])
def test_valid_ami_ids_accepted(good_value):
    cfg = _base_config(crest_kali_ami_override=good_value,
                       crest_windows_ami_override=good_value)
    ok, errors = ConfigValidator.validate_ccrts_config(cfg)
    assert ok is True, errors


def test_empty_ami_overrides_pass():
    """Empty / unset overrides are the common case (terraform falls back
    to the cross-region AMI copy) — must not flag."""
    cfg = _base_config(
        crest_kali_ami_override="",
        crest_windows_ami_override="",
    )
    ok, errors = ConfigValidator.validate_ccrts_config(cfg)
    assert ok is True, errors


# ============================================================================
# 4. project_name prefix soft-warning
# ============================================================================

def test_ccrts_project_name_prefix_warning():
    """`ccrts` deployments should warn when project_name doesn't match the
    `ccrts_` convention (mirrors c2_adhoc_* / goad_mini_*). Soft only."""
    cfg = _base_config(project_name="my_random_lab")  # wrong prefix
    _, errors = ConfigValidator.validate_ccrts_config(cfg)
    assert any("project_name" in e and "ccrts_" in e for e in errors), errors

    # Correct prefix passes.
    cfg["project_name"] = "ccrts_dev_alice_01"
    ok, errors = ConfigValidator.validate_ccrts_config(cfg)
    assert ok is True, errors


# ============================================================================
# 5. Helper consistency — no copy-paste drift
# ============================================================================

def test_ccrts_helpers_consistent():
    """is_ccrts_only / is_ccrts must stay aligned with the constants.
    Drift here would cause silent UX bugs in routes that branch on them."""
    for dtype in CCRTS_ONLY_DEPLOYMENT_TYPES:
        assert ConfigValidator.is_ccrts_only_deployment(dtype) is True
        assert ConfigValidator.is_ccrts_deployment(dtype) is True
        # ccrts is never GOAD-only.
        assert dtype not in GOAD_ONLY_DEPLOYMENT_TYPES
        assert ConfigValidator.is_goad_only_deployment(dtype) is False

    # The lab is always standalone — ALL == ONLY (no combined union).
    assert set(ALL_CCRTS_DEPLOYMENT_TYPES) == set(CCRTS_ONLY_DEPLOYMENT_TYPES)
    # And there is exactly one ccrts type.
    assert CCRTS_ONLY_DEPLOYMENT_TYPES == ['ccrts']


# ============================================================================
# 6. Regression guard — the old multi-type model stays removed
# ============================================================================

def test_legacy_ccrts_model_is_gone():
    """The size variants, combined modes, and bolt-on flag were removed when
    CCRTS was collapsed to one self-contained type. Guard against any of
    them creeping back."""
    legacy_types = [
        "ccrts-mini", "ccrts-full",
        "combined-adhoc-ccrts-mini", "combined-adhoc-ccrts-full",
        "combined-full-ccrts-full",
    ]
    for legacy in legacy_types:
        assert ConfigValidator.is_ccrts_deployment(legacy) is False, legacy
        assert ConfigValidator.is_ccrts_only_deployment(legacy) is False, legacy
        assert legacy not in CCRTS_ONLY_DEPLOYMENT_TYPES
        assert legacy not in ALL_CCRTS_DEPLOYMENT_TYPES
        assert legacy not in DOMAIN_REQUIRED_DEPLOYMENT_TYPES

    # The removed constant + helper must not reappear.
    assert not hasattr(validators_module, "COMBINED_CCRTS_DEPLOYMENT_TYPES")
    assert not hasattr(ConfigValidator, "is_combined_ccrts_deployment")
