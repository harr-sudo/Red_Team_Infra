#!/usr/bin/env python3
"""
Audit bolt-on descriptor rule_uuid references against the Elastic detection-rules corpus.

For every descriptor in webapp/bolton/catalog/**/*.yaml, collect each
detection.elastic_rules[].rule_uuid and verify it exists somewhere in
Research/elastic-detection-rules/rules/**/*.toml under rule.rule_id.

Exit code:
  0  every UUID found in corpus
  1  one or more UUIDs missing
  2  unexpected error (e.g. corpus or catalog missing)

Output:
  Per-descriptor table of FOUND / MISSING UUIDs, followed by a totals row.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:  # py < 3.11 fallback
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        print("Error: Need Python 3.11+ (tomllib) or 'pip install tomli'", file=sys.stderr)
        sys.exit(2)

try:
    import yaml
except ImportError:
    print("Error: PyYAML required ('pip install pyyaml')", file=sys.stderr)
    sys.exit(2)


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CORPUS_DIR = PROJECT_ROOT / "Research" / "elastic-detection-rules" / "rules"
CATALOG_DIR = PROJECT_ROOT / "webapp" / "bolton" / "catalog"


def build_corpus_uuid_set(corpus_dir: Path) -> set[str]:
    """Walk every TOML rule in the corpus and collect rule.rule_id values."""
    uuids: set[str] = set()
    if not corpus_dir.is_dir():
        return uuids
    for toml_path in corpus_dir.rglob("*.toml"):
        try:
            with toml_path.open("rb") as f:
                data = tomllib.load(f)
        except Exception:
            continue
        rule = data.get("rule") or {}
        rid = rule.get("rule_id")
        if isinstance(rid, str) and rid:
            uuids.add(rid)
    return uuids


def collect_descriptor_uuids(catalog_dir: Path) -> dict[Path, list[str]]:
    """Map descriptor file -> list of declared rule_uuid strings (in document order)."""
    out: dict[Path, list[str]] = {}
    if not catalog_dir.is_dir():
        return out
    for yaml_path in sorted(catalog_dir.rglob("*.yaml")):
        try:
            with yaml_path.open() as f:
                doc = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"WARN: could not parse {yaml_path}: {e}", file=sys.stderr)
            continue
        detection = (doc or {}).get("detection") or {}
        rules = detection.get("elastic_rules") or []
        uuids: list[str] = []
        for entry in rules:
            if isinstance(entry, dict):
                rid = entry.get("rule_uuid")
                if isinstance(rid, str) and rid:
                    uuids.append(rid)
        out[yaml_path] = uuids
    return out


def main() -> int:
    if not CORPUS_DIR.is_dir():
        print(f"FATAL: corpus dir not found: {CORPUS_DIR}", file=sys.stderr)
        return 2
    if not CATALOG_DIR.is_dir():
        print(f"FATAL: catalog dir not found: {CATALOG_DIR}", file=sys.stderr)
        return 2

    corpus_uuids = build_corpus_uuid_set(CORPUS_DIR)
    print(f"Corpus: {len(corpus_uuids)} rule_ids across {sum(1 for _ in CORPUS_DIR.rglob('*.toml'))} TOML files")

    descriptor_uuids = collect_descriptor_uuids(CATALOG_DIR)

    descriptors_with_refs = {p: u for p, u in descriptor_uuids.items() if u}
    print(f"Descriptors with elastic_rules references: {len(descriptors_with_refs)}")
    print()

    total_refs = 0
    total_missing = 0
    rows: list[tuple[str, int, int, list[str]]] = []
    for path, uuids in sorted(descriptors_with_refs.items()):
        found = [u for u in uuids if u in corpus_uuids]
        missing = [u for u in uuids if u not in corpus_uuids]
        total_refs += len(uuids)
        total_missing += len(missing)
        rel = path.relative_to(PROJECT_ROOT)
        rows.append((str(rel), len(found), len(missing), missing))

    # Per-descriptor table
    name_w = max((len(r[0]) for r in rows), default=20)
    print(f"{'descriptor'.ljust(name_w)}  found  missing  missing_uuids")
    print(f"{'-' * name_w}  -----  -------  ----------------------------------------")
    for name, found, missing_n, missing_list in rows:
        miss_str = ", ".join(missing_list) if missing_list else ""
        print(f"{name.ljust(name_w)}  {found:>5}  {missing_n:>7}  {miss_str}")

    print()
    pct = ((total_refs - total_missing) / total_refs * 100.0) if total_refs else 100.0
    print(f"TOTALS: {total_refs - total_missing}/{total_refs} found ({pct:.1f}%); {total_missing} missing")

    return 1 if total_missing else 0


if __name__ == "__main__":
    sys.exit(main())
