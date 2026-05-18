"""Catalog loader, dependency resolver, and conflict checker.

This module is intentionally pure (no I/O at import time, no Flask).
Used by:
    - Phase 2 backend routes (`webapp/backend/routes/bolton.py`)
    - Phase 3 CLI tool (`scripts/bolton/install.sh` etc.)
    - Phase 1 tests
"""

from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path

from webapp.bolton.schema import (
    BoltOnDescriptor,
    load_descriptor_yaml,
    validate_cross_references,
    validate_unique_ids,
)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CatalogError(Exception):
    """Base error for catalog-level problems."""


class CyclicDependencyError(CatalogError):
    """Raised when depends_on edges form a cycle."""

    def __init__(self, cycle: list[str]) -> None:
        self.cycle = cycle
        super().__init__(
            "Cyclic dependency detected: " + " -> ".join(cycle + [cycle[0]])
        )


class UnknownDescriptorError(CatalogError):
    """Raised when a requested id is not in the catalog."""


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_catalog(
    root: Path = Path("webapp/bolton/catalog"),
) -> dict[str, BoltOnDescriptor]:
    """Walk the catalog directory, load every .yaml, validate, return a dict
    keyed by descriptor id.

    Performs three layers of validation:
        1. Per-file: Pydantic schema validation
        2. Cross-file: unique ids
        3. Cross-file: depends_on / conflicts_with references resolve

    Raises:
        FileNotFoundError: if `root` doesn't exist
        pydantic.ValidationError: per-file schema errors
        ValueError: catalog-level errors (duplicates, dangling refs)
    """
    root = Path(root)
    if not root.exists():
        raise FileNotFoundError(f"catalog root does not exist: {root}")

    descriptors: list[BoltOnDescriptor] = []
    for yaml_path in sorted(root.rglob("*.yaml")):
        descriptor = load_descriptor_yaml(yaml_path)
        descriptors.append(descriptor)

    validate_unique_ids(descriptors)
    validate_cross_references(descriptors)

    return {d.id: d for d in descriptors}


# ---------------------------------------------------------------------------
# Dependency resolver — topological sort
# ---------------------------------------------------------------------------


def _collect_transitive_deps(
    catalog: dict[str, BoltOnDescriptor],
    target_ids: list[str],
) -> set[str]:
    """Return the set of every id reachable from target_ids via depends_on."""
    out: set[str] = set()
    stack: list[str] = []
    for t in target_ids:
        if t not in catalog:
            raise UnknownDescriptorError(
                f"target id {t!r} is not in the catalog"
            )
        stack.append(t)
    while stack:
        cur = stack.pop()
        if cur in out:
            continue
        out.add(cur)
        d = catalog.get(cur)
        if d is None:
            raise UnknownDescriptorError(
                f"transitive dep id {cur!r} is not in the catalog"
            )
        for dep in d.depends_on:
            if dep not in out:
                stack.append(dep)
    return out


def resolve_install_order(
    catalog: dict[str, BoltOnDescriptor],
    target_ids: list[str],
) -> list[str]:
    """Topological sort of `target_ids` plus their transitive `depends_on`.

    The returned order satisfies: for each id `x` in the list, every id in
    `catalog[x].depends_on` appears at an earlier index.

    Order within an independence level is alphabetical (stable, debuggable).

    Raises:
        UnknownDescriptorError: any target or transitive dep not in catalog
        CyclicDependencyError: depends_on edges form a cycle
    """
    if not target_ids:
        return []

    needed = _collect_transitive_deps(catalog, target_ids)

    # Kahn's algorithm with alphabetical tie-breaking
    indeg: dict[str, int] = {n: 0 for n in needed}
    children: dict[str, list[str]] = defaultdict(list)
    for n in needed:
        for dep in catalog[n].depends_on:
            if dep in needed:
                indeg[n] += 1
                children[dep].append(n)

    # Initial frontier: all nodes with indegree 0
    frontier = deque(sorted([n for n, deg in indeg.items() if deg == 0]))
    order: list[str] = []
    while frontier:
        cur = frontier.popleft()
        order.append(cur)
        for child in sorted(children[cur]):
            indeg[child] -= 1
            if indeg[child] == 0:
                # Insert into the frontier in sorted position to keep the
                # output deterministic.
                if not frontier or child > frontier[-1]:
                    frontier.append(child)
                else:
                    items = list(frontier) + [child]
                    items.sort()
                    frontier = deque(items)

    if len(order) != len(needed):
        # Reconstruct one cycle for the error message
        remaining = [n for n in needed if n not in set(order)]
        cycle = _find_cycle(catalog, remaining)
        raise CyclicDependencyError(cycle)

    return order


def _find_cycle(
    catalog: dict[str, BoltOnDescriptor],
    candidates: list[str],
) -> list[str]:
    """DFS-based cycle finder restricted to a candidate subset."""
    candidate_set = set(candidates)
    color: dict[str, int] = {n: 0 for n in candidates}  # 0=white,1=gray,2=black
    parent: dict[str, str | None] = {n: None for n in candidates}

    def dfs(start: str) -> list[str] | None:
        stack: list[tuple[str, int]] = [(start, 0)]
        while stack:
            node, idx = stack.pop()
            if idx == 0:
                color[node] = 1
            deps = [d for d in catalog[node].depends_on if d in candidate_set]
            if idx < len(deps):
                stack.append((node, idx + 1))
                nxt = deps[idx]
                c = color.get(nxt, 0)
                if c == 1:
                    # Found a back edge — reconstruct the cycle
                    cyc = [nxt, node]
                    p = parent[node]
                    while p is not None and p != nxt:
                        cyc.append(p)
                        p = parent[p]
                    cyc.reverse()
                    return cyc
                if c == 0:
                    parent[nxt] = node
                    stack.append((nxt, 0))
            else:
                color[node] = 2
        return None

    for n in candidates:
        if color[n] == 0:
            cyc = dfs(n)
            if cyc:
                return cyc
    # Should never happen: caller guarantees a cycle exists
    return candidates[:1] if candidates else []


# ---------------------------------------------------------------------------
# Conflict checker
# ---------------------------------------------------------------------------


def check_conflicts(
    catalog: dict[str, BoltOnDescriptor],
    install_set: list[str],
) -> list[tuple[str, str]]:
    """Return pairs of conflicting ids within `install_set`.

    Conflicts are bidirectional: if `A.conflicts_with` lists `B` OR
    `B.conflicts_with` lists `A`, the pair is reported (canonicalized so the
    smaller id appears first; each pair appears once).

    Empty list means no conflicts.
    """
    install_set_unique = list(dict.fromkeys(install_set))  # preserve order, dedupe
    pairs: set[tuple[str, str]] = set()

    # Validate all ids exist
    for vid in install_set_unique:
        if vid not in catalog:
            raise UnknownDescriptorError(
                f"install-set id {vid!r} is not in the catalog"
            )

    for i, a in enumerate(install_set_unique):
        for b in install_set_unique[i + 1 :]:
            a_conflicts = set(catalog[a].conflicts_with)
            b_conflicts = set(catalog[b].conflicts_with)
            if b in a_conflicts or a in b_conflicts:
                pair = (a, b) if a < b else (b, a)
                pairs.add(pair)

    return sorted(pairs)


__all__ = [
    "CatalogError",
    "CyclicDependencyError",
    "UnknownDescriptorError",
    "check_conflicts",
    "load_catalog",
    "resolve_install_order",
]
