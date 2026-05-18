"""Pydantic v2 schema for bolt-on vulnerability descriptors.

This is the single source of truth for the descriptor shape. Other agents
(Phase 1 B/C/D) import from here — do NOT rename fields without coordinating.

The schema is the formalization of:
    - master plan §4 (Vulnerability data schema)
    - BOLTON_REFINEMENT_patch.md §2 (uninstall / patch / patch_revert blocks)
    - BOLTON_REFINEMENT_ttp_elastic.md §2 (mitre + detection blocks)
    - BOLTON_REFINEMENT_compatibility.md §2 (targets / depends_on / conflicts)

Pydantic v2 conventions used here:
    - `model_config = ConfigDict(...)` for class-level config (not inner Config)
    - `field_validator` for per-field validation
    - `model_validator(mode="after")` for cross-field invariants
    - String enums for any closed-set value (renders cleanly in YAML)
"""

from __future__ import annotations

import re
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)


# ---------------------------------------------------------------------------
# Regexes used in multiple places
# ---------------------------------------------------------------------------

MITRE_TECHNIQUE_RE = re.compile(r"^T\d{4}(\.\d{3})?$")
MITRE_TACTIC_RE = re.compile(r"^TA\d{4}$")
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
CVE_RE = re.compile(r"^CVE-\d{4}-\d{4,7}$")
ID_RE = re.compile(r"^bolton\.[a-z0-9_-]+(\.[a-z0-9_-]+)+$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class OSFamily(str, Enum):
    """Top-level OS family the host belongs to."""

    WINDOWS = "windows"
    LINUX = "linux"
    MACOS = "macos"
    NETWORK = "network"
    CONTAINER = "container"


class HostRole(str, Enum):
    """Logical role of the target host within a lab."""

    DOMAIN_CONTROLLER = "domain_controller"
    MEMBER_SERVER = "member_server"
    WORKSTATION = "workstation"
    CA_HOST = "ca_host"
    LINUX_MEMBER = "linux_member"
    STANDALONE = "standalone"


class CoverageStatus(str, Enum):
    """Computed detection coverage state for a descriptor."""

    COVERED = "covered"
    PARTIAL = "partial"
    NO_RULE = "no-rule"
    RULE_STALE = "rule-stale"


class RuleCoverage(str, Enum):
    """Per-rule coverage strength for one Elastic detection rule."""

    FULL = "full"
    PARTIAL = "partial"
    INDIRECT = "indirect"


class RuleConfidence(str, Enum):
    """Author confidence that the referenced rule will actually fire."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DetectabilityProfile(str, Enum):
    """How loud the install is on a defender's monitoring stack."""

    LOUD = "loud"
    MEDIUM = "medium"
    QUIET = "quiet"


class PatchComplexity(str, Enum):
    """Effort required to apply the vendor patch."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class StepEngineHint(str, Enum):
    """Hint about which automation engine a step targets.

    Each step is either an Ansible role invocation or a script execution; the
    engine hint primarily drives logging/UI labels — the executor inspects the
    payload (`ansible_role` vs `script`) to decide what to run.
    """

    ANSIBLE = "ansible"
    BASH = "bash"
    POWERSHELL = "powershell"
    COMPOSITE = "composite"


class DescriptorStatus(str, Enum):
    """Lifecycle status of the descriptor itself."""

    STABLE = "stable"
    BETA = "beta"
    EXPERIMENTAL = "experimental"
    DEPRECATED = "deprecated"


# ---------------------------------------------------------------------------
# Sub-models — MITRE
# ---------------------------------------------------------------------------


class MitreTactic(BaseModel):
    """ATT&CK tactic reference (TA####)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="ATT&CK tactic ID, e.g. TA0006")
    name: str = Field(..., description="Human-readable tactic name")

    @field_validator("id")
    @classmethod
    def _validate_tactic_id(cls, v: str) -> str:
        if not MITRE_TACTIC_RE.match(v):
            raise ValueError(
                f"MITRE tactic id must match TA#### (got {v!r})"
            )
        return v


class MitreTechnique(BaseModel):
    """ATT&CK technique reference (T#### or T####.### sub)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="ATT&CK technique ID, e.g. T1558 or T1558.003")
    name: str = Field(..., description="Human-readable technique name")

    @field_validator("id")
    @classmethod
    def _validate_technique_id(cls, v: str) -> str:
        if not MITRE_TECHNIQUE_RE.match(v):
            raise ValueError(
                f"MITRE technique id must match T#### or T####.### (got {v!r})"
            )
        return v


class MitreBlock(BaseModel):
    """Primary MITRE mapping for the descriptor.

    Per `BOLTON_REFINEMENT_ttp_elastic.md` §2.2 the descriptor allows the whole
    `mitre:` field to be `null` for vulns that genuinely don't map (custom web
    app CVEs etc). When present, `tactic` and `technique` are required;
    `subtechnique` is optional and must be a deeper sub of the technique.
    """

    model_config = ConfigDict(extra="forbid")

    tactic: MitreTactic
    technique: MitreTechnique
    subtechnique: MitreTechnique | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _subtechnique_must_extend_technique(self) -> "MitreBlock":
        if self.subtechnique is None:
            return self
        # Subtechnique must be the same base technique
        base = self.technique.id  # e.g. T1558
        sub = self.subtechnique.id  # e.g. T1558.003
        if "." not in sub:
            raise ValueError(
                f"subtechnique.id must contain '.' (got {sub!r}); "
                "use the technique slot for base techniques"
            )
        if not sub.startswith(base + "."):
            raise ValueError(
                f"subtechnique {sub!r} does not extend technique {base!r}"
            )
        return self


# ---------------------------------------------------------------------------
# Sub-models — Detection (Elastic)
# ---------------------------------------------------------------------------


class ElasticRuleRef(BaseModel):
    """Reference to one Elastic detection rule by UUID + metadata."""

    model_config = ConfigDict(extra="forbid")

    rule_uuid: str = Field(
        ...,
        description="The `rule_id` field from the rule's TOML (stable UUID).",
    )
    rule_name: str = Field(..., description="Display name (drifts; UUID is canonical).")
    rule_filename: str | None = Field(
        default=None,
        description="Path relative to Research/elastic-detection-rules/rules/",
    )
    coverage: RuleCoverage = RuleCoverage.FULL
    confidence: RuleConfidence = RuleConfidence.MEDIUM
    last_validated: date = Field(
        ...,
        description="When this descriptor's author last confirmed the rule fires.",
    )
    notes: str | None = None

    @field_validator("rule_uuid")
    @classmethod
    def _validate_uuid(cls, v: str) -> str:
        if not UUID_RE.match(v):
            raise ValueError(
                f"rule_uuid must be a UUID (got {v!r})"
            )
        return v.lower()


class DetectionBlock(BaseModel):
    """Detection coverage block."""

    model_config = ConfigDict(extra="forbid")

    elastic_rules: list[ElasticRuleRef] = Field(default_factory=list)
    coverage_status: CoverageStatus
    fallback_rule_template: str | None = Field(
        default=None,
        description=(
            "Path to a starter rule template (e.g. "
            "webapp/bolton/rule_templates/kerberoasting.j2.yml). Required when "
            "coverage_status is `no-rule`."
        ),
    )
    signal_sources: list[str] = Field(
        default_factory=list,
        description="Free-text log sources that emit signal for this vuln.",
    )

    @model_validator(mode="after")
    def _fallback_required_when_no_rule(self) -> "DetectionBlock":
        if (
            self.coverage_status == CoverageStatus.NO_RULE
            and not self.fallback_rule_template
        ):
            raise ValueError(
                "When coverage_status is `no-rule`, fallback_rule_template is required"
            )
        if (
            self.coverage_status == CoverageStatus.NO_RULE
            and self.elastic_rules
        ):
            raise ValueError(
                "coverage_status=`no-rule` is inconsistent with non-empty elastic_rules"
            )
        if (
            self.coverage_status in (CoverageStatus.COVERED, CoverageStatus.PARTIAL)
            and not self.elastic_rules
        ):
            raise ValueError(
                f"coverage_status={self.coverage_status.value} requires "
                "at least one elastic_rules entry"
            )
        return self


# ---------------------------------------------------------------------------
# Sub-models — Targets / dependencies
# ---------------------------------------------------------------------------


class SupportedOS(BaseModel):
    """One supported OS row.

    Per `BOLTON_REFINEMENT_compatibility.md` §8.4, v1 matches on family +
    version (min/max). LTSC/edition narrowing is deferred to a future version.
    """

    model_config = ConfigDict(extra="forbid")

    family: OSFamily
    min_version: str | None = Field(
        default=None,
        description="Lowest supported major version (string for Win '2016', Linux '20.04').",
    )
    max_version: str | None = Field(
        default=None,
        description="Highest supported major version.",
    )
    edition_in: list[str] | None = Field(
        default=None,
        description="Optional edition allow-list (Datacenter, Standard, LTSC).",
    )


class TargetsBlock(BaseModel):
    """Compatibility targets — what the host must look like."""

    model_config = ConfigDict(extra="forbid")

    supported_os: list[SupportedOS] = Field(default_factory=list)
    required_roles: list[HostRole] = Field(default_factory=list)
    required_services: list[str] = Field(
        default_factory=list,
        description="Service names like 'adcs', 'mssql', 'iis', 'smb'.",
    )
    required_domain_function_level: str | None = Field(
        default=None,
        description="Optional minimum forest/domain function level, e.g. '2016'.",
    )

    @field_validator("supported_os")
    @classmethod
    def _at_least_one_os(cls, v: list[SupportedOS]) -> list[SupportedOS]:
        if not v:
            raise ValueError("targets.supported_os must list at least one OS")
        return v


class SideEffects(BaseModel):
    """Coarse side-effect flags used by the compatibility resolver and audit."""

    # `global` is a Python keyword; use an alias so YAML can spell it `global:`.
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    global_: bool = Field(
        default=False,
        alias="global",
        description=(
            "True if install mutates domain-wide state (GPO, schema, "
            "trust). Triggers cross-host fact invalidation per refinement §2.4."
        ),
    )
    network_visible: bool = Field(
        default=False,
        description="True if install changes network-observable surface (open port, listener).",
    )
    reboot_required: bool = Field(
        default=False,
        description="True if any step requires a reboot.",
    )


# ---------------------------------------------------------------------------
# Sub-models — Install / Uninstall / Patch / Patch revert
# ---------------------------------------------------------------------------


class AnsibleStep(BaseModel):
    """Ansible role invocation step."""

    model_config = ConfigDict(extra="forbid")

    ansible_role: str = Field(
        ...,
        description="Fully qualified collection.role, e.g. ansible.windows.win_regedit",
    )
    role_vars: dict[str, Any] = Field(
        default_factory=dict,
        description="Variables passed into the role.",
    )
    description: str | None = None


class ScriptStep(BaseModel):
    """Inline script step."""

    model_config = ConfigDict(extra="forbid")

    script: str = Field(
        ...,
        description="Inline script body or path to a script under bolton/scripts/.",
    )
    args: dict[str, Any] = Field(default_factory=dict)
    engine: StepEngineHint = StepEngineHint.BASH
    description: str | None = None


# A step is either Ansible or script. We use a discriminated union by field
# presence (Pydantic v2 picks based on extra="forbid" + required field shapes).
Step = AnsibleStep | ScriptStep


class VerifyProbe(BaseModel):
    """A verification probe — confirms install/uninstall/patch worked."""

    model_config = ConfigDict(extra="forbid")

    probe: str = Field(
        ...,
        description="Command or Ansible task body. Templated with Jinja at runtime.",
    )
    timeout_seconds: int = Field(default=60, ge=1, le=3600)
    expect_exit_code: int | None = Field(
        default=0,
        description="Expected exit code; null means don't check.",
    )
    expect_stdout_contains: str | None = None
    expect_stdout_empty: bool | None = None


class InstallBlock(BaseModel):
    """Install steps + verification."""

    model_config = ConfigDict(extra="forbid")

    steps: list[Step] = Field(..., min_length=1)
    estimated_time_seconds: int = Field(..., ge=1, le=7200)
    verify: VerifyProbe


class UninstallBlock(BaseModel):
    """Uninstall (artifact rollback). Always reversible by re-installing."""

    model_config = ConfigDict(extra="forbid")

    description: str
    steps: list[Step] = Field(..., min_length=1)
    estimated_time_seconds: int = Field(..., ge=1, le=7200)
    verify: VerifyProbe


class PatchBlock(BaseModel):
    """Vendor remediation. Closes the underlying vuln semantically.

    Per `BOLTON_REFINEMENT_patch.md` §2.1.
    """

    model_config = ConfigDict(extra="forbid")

    description: str
    patch_reference: HttpUrl | list[HttpUrl] = Field(
        ...,
        description="URL(s) to authoritative vendor / MITRE / advisory page(s).",
    )
    complexity: PatchComplexity
    side_effects: list[str] = Field(
        default_factory=list,
        description="What ELSE changes on the host beyond closing the vuln.",
    )
    rollback_supported: bool = Field(
        ...,
        description=(
            "If True, the descriptor MUST also declare a patch_revert block. "
            "If False, patch is one-way (e.g. KB cannot be cleanly removed)."
        ),
    )
    steps: list[Step] = Field(..., min_length=1)
    verify: VerifyProbe
    exploit_probe_after_patch: str | None = Field(
        default=None,
        description=(
            "Path to a synthetic-exploit script under bolton/exploit_probes/ "
            "that should FAIL after patch (proof the patch holds)."
        ),
    )


class PatchRevertBlock(BaseModel):
    """Reverse the patch so the lab is exploitable again (training loop)."""

    model_config = ConfigDict(extra="forbid")

    description: str
    steps: list[Step] = Field(..., min_length=1)
    estimated_time_seconds: int = Field(..., ge=1, le=7200)
    verify: VerifyProbe
    warning: str | None = Field(
        default=None,
        description="Operator-facing warning ('lab is exploitable again', etc.).",
    )


# ---------------------------------------------------------------------------
# Sub-models — Cost
# ---------------------------------------------------------------------------


class CostBlock(BaseModel):
    """Cost / resource impact estimate."""

    model_config = ConfigDict(extra="forbid")

    storage_mb: int = Field(default=0, ge=0)
    cpu_pct: int = Field(default=0, ge=0, le=100)
    detectability: DetectabilityProfile = DetectabilityProfile.MEDIUM


# ---------------------------------------------------------------------------
# Top-level descriptor
# ---------------------------------------------------------------------------


class BoltOnDescriptor(BaseModel):
    """Top-level descriptor for one bolt-on vulnerability."""

    model_config = ConfigDict(
        extra="forbid",
        # Allow JSON-style aliasing of `global` (Python keyword) on SideEffects.
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    # Identity
    id: str = Field(..., description="Globally unique dotted ID, e.g. bolton.adcs.esc1")
    name: str = Field(..., min_length=3)
    slug: str = Field(..., description="Filename-safe slug, e.g. kerberoastable-svc")
    version: str = Field(..., description="Descriptor semver")
    author: str
    last_updated: date

    # Categorization
    category: str
    subcategory: str | None = None
    tags: list[str] = Field(default_factory=list)
    description: str = Field(..., min_length=20)
    cve: list[str] = Field(default_factory=list)
    references: list[HttpUrl] = Field(default_factory=list)

    # MITRE — nullable per refinement §2.3 example 3
    mitre: MitreBlock | None

    # Detection coverage
    detection: DetectionBlock

    # Compatibility
    targets: TargetsBlock
    depends_on: list[str] = Field(
        default_factory=list,
        description="IDs of bolt-ons that MUST be installed first.",
    )
    conflicts_with: list[str] = Field(
        default_factory=list,
        description="IDs of bolt-ons that CANNOT coexist.",
    )

    # Side effects
    side_effects: SideEffects = Field(default_factory=SideEffects)

    # Install / Uninstall / Patch
    install: InstallBlock
    uninstall: UninstallBlock
    patch: PatchBlock
    patch_revert: PatchRevertBlock | None = None

    # Cost
    cost: CostBlock = Field(default_factory=CostBlock)

    # Lifecycle
    status: DescriptorStatus = DescriptorStatus.STABLE

    # -----------------------------------------------------------------
    # Field-level validators
    # -----------------------------------------------------------------

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        if not ID_RE.match(v):
            raise ValueError(
                f"id must match {ID_RE.pattern} (got {v!r})"
            )
        return v

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError(
                f"slug must be lowercase a-z0-9- with no leading/trailing dash (got {v!r})"
            )
        return v

    @field_validator("version")
    @classmethod
    def _validate_version(cls, v: str) -> str:
        if not SEMVER_RE.match(v):
            raise ValueError(
                f"version must be semver MAJOR.MINOR.PATCH[-pre] (got {v!r})"
            )
        return v

    @field_validator("cve", mode="after")
    @classmethod
    def _validate_cves(cls, v: list[str]) -> list[str]:
        for c in v:
            if not CVE_RE.match(c):
                raise ValueError(
                    f"cve entry must match CVE-YYYY-NNNN+ (got {c!r})"
                )
        return v

    @field_validator("depends_on", "conflicts_with", mode="after")
    @classmethod
    def _validate_id_refs(cls, v: list[str]) -> list[str]:
        for ref in v:
            if not ID_RE.match(ref):
                raise ValueError(
                    f"reference id must match {ID_RE.pattern} (got {ref!r})"
                )
        return v

    # -----------------------------------------------------------------
    # Cross-field invariants
    # -----------------------------------------------------------------

    @model_validator(mode="after")
    def _patch_revert_iff_rollback_supported(self) -> "BoltOnDescriptor":
        if self.patch.rollback_supported and self.patch_revert is None:
            raise ValueError(
                "patch.rollback_supported is True but patch_revert is missing — "
                "a rollback-supporting patch MUST declare patch_revert"
            )
        if not self.patch.rollback_supported and self.patch_revert is not None:
            raise ValueError(
                "patch.rollback_supported is False but patch_revert is present — "
                "remove patch_revert or set rollback_supported=true"
            )
        return self

    @model_validator(mode="after")
    def _no_self_reference(self) -> "BoltOnDescriptor":
        if self.id in self.depends_on:
            raise ValueError(f"descriptor {self.id!r} cannot depend on itself")
        if self.id in self.conflicts_with:
            raise ValueError(f"descriptor {self.id!r} cannot conflict with itself")
        return self

    @model_validator(mode="after")
    def _depends_and_conflicts_disjoint(self) -> "BoltOnDescriptor":
        overlap = set(self.depends_on) & set(self.conflicts_with)
        if overlap:
            raise ValueError(
                f"descriptor {self.id!r} has IDs in both depends_on and "
                f"conflicts_with: {sorted(overlap)}"
            )
        return self

    @model_validator(mode="after")
    def _slug_matches_id_tail(self) -> "BoltOnDescriptor":
        # id is bolton.<category>.<slug-ish>, slug is the human filename
        # We don't enforce a strict equality — descriptor authors may want
        # different slugs from id tails — but we DO enforce that the slug is
        # not empty and not the literal 'bolton'.
        if self.slug == "bolton":
            raise ValueError("slug cannot be the literal 'bolton'")
        return self


# ---------------------------------------------------------------------------
# Catalog-level validators (separate functions; not on a single descriptor)
# ---------------------------------------------------------------------------


def validate_unique_ids(descriptors: list[BoltOnDescriptor]) -> None:
    """Raise ValueError if two descriptors share an id."""
    seen: dict[str, BoltOnDescriptor] = {}
    for d in descriptors:
        if d.id in seen:
            raise ValueError(
                f"Duplicate descriptor id {d.id!r} — found in both "
                f"{seen[d.id].slug!r} and {d.slug!r}"
            )
        seen[d.id] = d


def validate_cross_references(descriptors: list[BoltOnDescriptor]) -> None:
    """Raise ValueError if any depends_on or conflicts_with refers to an
    id not present in the descriptor set."""
    known = {d.id for d in descriptors}
    errors: list[str] = []
    for d in descriptors:
        for dep in d.depends_on:
            if dep not in known:
                errors.append(
                    f"{d.id}: depends_on references unknown id {dep!r}"
                )
        for con in d.conflicts_with:
            if con not in known:
                errors.append(
                    f"{d.id}: conflicts_with references unknown id {con!r}"
                )
    if errors:
        raise ValueError("Catalog cross-reference errors:\n  " + "\n  ".join(errors))


# ---------------------------------------------------------------------------
# Convenience: load a single YAML file into a descriptor
# ---------------------------------------------------------------------------


def load_descriptor_yaml(path: Path) -> BoltOnDescriptor:
    """Load and validate a single descriptor YAML file."""
    import yaml  # local import: pyyaml is in requirements.txt

    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(
            f"Descriptor {path} must be a YAML mapping at top level (got {type(raw).__name__})"
        )
    return BoltOnDescriptor.model_validate(raw)


__all__ = [
    # Enums
    "CoverageStatus",
    "DescriptorStatus",
    "DetectabilityProfile",
    "HostRole",
    "OSFamily",
    "PatchComplexity",
    "RuleConfidence",
    "RuleCoverage",
    "StepEngineHint",
    # Models
    "AnsibleStep",
    "BoltOnDescriptor",
    "CostBlock",
    "DetectionBlock",
    "ElasticRuleRef",
    "InstallBlock",
    "MitreBlock",
    "MitreTactic",
    "MitreTechnique",
    "PatchBlock",
    "PatchRevertBlock",
    "ScriptStep",
    "SideEffects",
    "Step",
    "SupportedOS",
    "TargetsBlock",
    "UninstallBlock",
    "VerifyProbe",
    # Functions
    "load_descriptor_yaml",
    "validate_cross_references",
    "validate_unique_ids",
]
