"""Bolt-on vulnerability framework package.

See `docs/internal/VULNERABLE_LAB_BOLTON_PLAN.md` for the design and
`docs/internal/BOLTON_REFINEMENT_*.md` for the patch/uninstall, TTP/Elastic,
and host-compatibility refinements.

Phase 1 owns:
    - `schema.py`     — Pydantic v2 descriptor model + enums + validators
    - `catalog.py`    — YAML loader, topological sort, conflict checker
    - `catalog/**/*.yaml` — 5 worked descriptors
"""

from webapp.bolton.schema import (  # noqa: F401
    BoltOnDescriptor,
    CoverageStatus,
    DetectabilityProfile,
    HostRole,
    OSFamily,
    PatchComplexity,
    StepEngineHint,
)
