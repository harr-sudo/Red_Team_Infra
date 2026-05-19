"""Shared per-project tfvars path resolution.

Both ``/api/config`` and ``/api/deploy`` need to translate a ``?project=<name>``
query-string parameter (or body field) into an on-disk path under
``configs/<name>.tfvars`` — with strict sanitization so a hostile request
can't escape the configs directory via path-traversal tricks.

Factored out from ``webapp.backend.routes.config._resolve_tfvars_path`` so
that the same security-critical sanitizer is used everywhere a project
name is mapped to disk. Duplicating this logic would make path-traversal
hardening drift between endpoints — keep it in one place.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


# Drafts and the "all" fleet-view sentinel never round-trip through the
# config endpoints — they're transient UI states with no on-disk tfvars.
RESERVED_PROJECT_NAMES = {"__draft__", "__all__"}


def sanitize_project_name(project_param: Optional[str]) -> str:
    """Reduce an arbitrary project name to a filesystem-safe slug.

    Allowed characters: alphanumerics, ``-``, ``_``. Everything else is
    replaced with ``_``. Empty / sentinel input returns an empty string,
    which the caller should treat as "use global tfvars".
    """
    if not project_param or project_param in RESERVED_PROJECT_NAMES:
        return ""
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in project_param)


def resolve_tfvars_path(
    project_param: Optional[str],
    config_dir: Path,
    default_tfvars: Path,
) -> Path:
    """Resolve the on-disk tfvars file for a ``?project=`` value.

    - No param / empty / sentinel → ``default_tfvars`` (legacy global).
    - Real name → ``config_dir/<sanitized>.tfvars``.

    The name is sanitized to only allow alphanumerics, ``-``, and ``_`` so
    no path-traversal characters survive. The resolved path is then
    re-rooted under ``config_dir`` as a defense-in-depth guard against
    symlink shenanigans. If sanitization yields an empty name, or the
    resolved path escapes ``config_dir``, falls back to ``default_tfvars``.
    """
    safe = sanitize_project_name(project_param)
    if not safe:
        return default_tfvars
    candidate = (config_dir / f"{safe}.tfvars").resolve()
    try:
        candidate.relative_to(config_dir.resolve())
    except ValueError:
        return default_tfvars
    return candidate


def is_reserved_sentinel(project_param: Optional[str]) -> bool:
    """True for ``__draft__`` / ``__all__`` — never write per-project state for these."""
    return bool(project_param) and project_param in RESERVED_PROJECT_NAMES
