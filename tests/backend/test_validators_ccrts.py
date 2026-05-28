"""Unit tests for the CCRTS-Lab additions to ConfigValidator.

Covers the five contract guarantees the deploy/config routes rely on:

  1. Pure ccrts-* deployments DO NOT require a domain.
  2. combined-*-ccrts-* deployments DO require a domain (the C2 half
     still needs DNS for redirector SSL).
  3. enable_ccrts_lab=true is REJECTED on anything other than a pure
     c2-* deployment — mirrors the enable_test_lab gating in main.tf.
  4. crest_kali_ami_override / crest_windows_ami_override must look
     like a real AMI ID when provided (catches typos like 'ami-abc'
     vs 'ami_abc' before terraform spends time on the AMI copy).
  5. is_ccrts_only / is_combined_ccrts / is_ccrts helpers stay in
     sync with the underlying constants (no copy-paste drift).
"""
from __future__ import annotations

import pytest

from webapp.backend.utils.validators import (
    ConfigValidator,
    CCRTS_ONLY_DEPLOYMENT_TYPES,
    COMBINED_CCRTS_DEPLOYMENT_TYPES,
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
        "project_name": "ccrts_full_dev_lab_01",
        "environment": "dev",
        "deployment_type": "ccrts-full",
        "management_cidr_blocks": ["1.2.3.4/32"],
        # Pure ccrts-* doesn't need key_pair_name, but supplying one is
        # harmless — the validator only requires it for non-goad/non-ccrts.
        "enable_ssl": False,
    }
    cfg.update(overrides)
    return cfg


# ============================================================================
# 1. Pure ccrts-* does NOT require a domain
# ============================================================================

def test_ccrts_only_deployment_no_domain_required():
    """ccrts-mini and ccrts-full both pass validation without
    primary_domain_name — the lab is internal-only behind the dashboard
    server jump, so there's no public DNS / SSL surface to configure."""
    for dtype in CCRTS_ONLY_DEPLOYMENT_TYPES:
        cfg = _base_config(deployment_type=dtype,
                           project_name=f"ccrts_{dtype.split('-')[1]}_dev_01")
        is_valid, errors = ConfigValidator.validate_config(cfg)
        assert is_valid is True, (
            f"Expected {dtype} to validate without domain, got errors: {errors}"
        )
        # Defensive: requires_domain() must also report False.
        assert ConfigValidator.requires_domain(dtype) is False
        # validate_domain_config alone must short-circuit to True/[].
        ok, dom_errors = ConfigValidator.validate_domain_config(cfg)
        assert ok is True
        assert dom_errors == []


# ============================================================================
# 2. combined-*-ccrts-* DOES require a domain
# ============================================================================

def test_combined_ccrts_requires_domain():
    """Every combined-*-ccrts-* variant must be present in the
    DOMAIN_REQUIRED list AND must fail validation when no domain is
    provided. The C2 half still needs DNS for redirector SSL."""
    for dtype in COMBINED_CCRTS_DEPLOYMENT_TYPES:
        assert dtype in DOMAIN_REQUIRED_DEPLOYMENT_TYPES, (
            f"{dtype} missing from DOMAIN_REQUIRED_DEPLOYMENT_TYPES"
        )
        assert ConfigValidator.requires_domain(dtype) is True
        cfg = _base_config(
            deployment_type=dtype,
            project_name=f"combined_test_{dtype.replace('-', '_')}",
            key_pair_name="my-kp",  # combined needs key_pair_name
            # NO primary_domain_name — expect failure.
        )
        is_valid, errors = ConfigValidator.validate_config(cfg)
        assert is_valid is False
        # The domain error must surface explicitly.
        assert any("primary_domain_name" in e.lower() or "domain" in e.lower()
                   for e in errors), errors


# ============================================================================
# 3. enable_ccrts_lab only on c2-* deployments
# ============================================================================

@pytest.mark.parametrize("dtype", [
    "ccrts-mini", "ccrts-full",
    "combined-adhoc-ccrts-mini", "combined-full-ccrts-full",
    "goad-mini", "goad-full",
    "combined-adhoc-mini", "combined-full-full",
])
def test_enable_ccrts_lab_only_on_c2_deployments(dtype):
    """Setting enable_ccrts_lab=true on anything other than c2-* must
    surface a validation error pointing the operator at the standalone
    ccrts-* / combined-*-ccrts-* variants instead."""
    cfg = _base_config(
        deployment_type=dtype,
        project_name="test_enable_ccrts_lab",
        key_pair_name="my-kp" if not dtype.startswith("goad-") else None,
        primary_domain_name="example.com" if dtype.startswith("combined-") else None,
        enable_ccrts_lab=True,
    )
    # Strip Nones so they don't shadow defaults.
    cfg = {k: v for k, v in cfg.items() if v is not None}
    _, errors = ConfigValidator.validate_ccrts_config(cfg)
    assert any("enable_ccrts_lab" in e for e in errors), (
        f"Expected enable_ccrts_lab error on {dtype}, got: {errors}"
    )


def test_enable_ccrts_lab_allowed_on_c2_adhoc():
    """The flag IS valid on c2-* deployments — symmetric with the
    enable_test_lab pattern."""
    cfg = _base_config(
        deployment_type="c2-adhoc",
        project_name="c2_adhoc_test_lab",
        key_pair_name="my-kp",
        primary_domain_name="example.com",
        enable_ccrts_lab=True,
    )
    ok, errors = ConfigValidator.validate_ccrts_config(cfg)
    assert ok is True, errors


# ============================================================================
# 4. AMI override format validation
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
# 5. Helper consistency — no copy-paste drift
# ============================================================================

def test_ccrts_helpers_consistent():
    """is_ccrts_only / is_combined_ccrts / is_ccrts must stay aligned
    with the underlying constants. Drift here would cause silent UX
    bugs in routes that branch on these helpers."""
    for dtype in CCRTS_ONLY_DEPLOYMENT_TYPES:
        assert ConfigValidator.is_ccrts_only_deployment(dtype) is True
        assert ConfigValidator.is_combined_ccrts_deployment(dtype) is False
        assert ConfigValidator.is_ccrts_deployment(dtype) is True

    for dtype in COMBINED_CCRTS_DEPLOYMENT_TYPES:
        assert ConfigValidator.is_ccrts_only_deployment(dtype) is False
        assert ConfigValidator.is_combined_ccrts_deployment(dtype) is True
        assert ConfigValidator.is_ccrts_deployment(dtype) is True

    # ALL_CCRTS must be exactly the union — no extras, no gaps.
    assert set(ALL_CCRTS_DEPLOYMENT_TYPES) == (
        set(CCRTS_ONLY_DEPLOYMENT_TYPES)
        | set(COMBINED_CCRTS_DEPLOYMENT_TYPES)
    )

    # Defensive consistency: ccrts types must NEVER report as GOAD-only.
    for dtype in ALL_CCRTS_DEPLOYMENT_TYPES:
        assert dtype not in GOAD_ONLY_DEPLOYMENT_TYPES
        assert ConfigValidator.is_goad_only_deployment(dtype) is False


def test_ccrts_project_name_prefix_warning():
    """Pure ccrts-* deployments should warn when project_name doesn't
    match the ccrts_<size>_* convention. Combined variants are exempt
    (they reuse the C2 naming convention)."""
    cfg = _base_config(
        deployment_type="ccrts-full",
        project_name="my_random_lab",  # wrong prefix
    )
    _, errors = ConfigValidator.validate_ccrts_config(cfg)
    assert any("project_name" in e and "ccrts_full_" in e for e in errors), errors

    # Correct prefix passes.
    cfg["project_name"] = "ccrts_full_dev_alice_01"
    ok, errors = ConfigValidator.validate_ccrts_config(cfg)
    assert ok is True, errors

    # Combined ccrts: no prefix enforcement.
    cfg = _base_config(
        deployment_type="combined-adhoc-ccrts-mini",
        project_name="combined_adhoc_alice_01",
    )
    ok, errors = ConfigValidator.validate_ccrts_config(cfg)
    assert ok is True, errors
