#!/usr/bin/env bash
#
# refresh-cs-spec.sh — T0.2
#
# Strips Fortra's CommonJS-ish wrapper (`var spec = { ... };`) from the
# Cobalt Strike OpenAPI spec shipped in docs/cobalt-strike-api/spec.js and
# writes a pure JSON document to docs/cobalt-strike-api/spec.json.
#
# The output (spec.json) is gitignored — it's a derived artifact regenerated
# on demand. Source of truth remains spec.js.
#
# Edge cases handled:
#   - UTF-8 BOM at the start of spec.js (Fortra ships it that way)
#   - Tolerates `var spec = {`, `var spec ={`, `var spec= {`, `var spec={`
#   - Tolerates an optional trailing semicolon (may be absent on last line)
#   - Cross-platform: uses Python instead of sed/awk to avoid BSD/GNU drift

set -euo pipefail

# Resolve repo root from script location regardless of caller's cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SRC="${REPO_ROOT}/docs/cobalt-strike-api/spec.js"
DST="${REPO_ROOT}/docs/cobalt-strike-api/spec.json"

if [[ ! -f "${SRC}" ]]; then
    echo "ERROR: source spec not found at ${SRC}" >&2
    exit 1
fi

# Strip the wrapper using Python (portable, no sed dialect concerns).
python3 - "${SRC}" "${DST}" <<'PYEOF'
import re
import sys
from pathlib import Path

src_path = Path(sys.argv[1])
dst_path = Path(sys.argv[2])

# Read as bytes first so we can strip the UTF-8 BOM cleanly, then decode.
raw = src_path.read_bytes()
if raw.startswith(b"\xef\xbb\xbf"):
    raw = raw[3:]
text = raw.decode("utf-8")

# Strip leading `var spec =` with flexible whitespace around `=`.
# We anchor at start-of-string and require the `{` to remain for JSON parsing.
stripped = re.sub(r"^\s*var\s+spec\s*=\s*", "", text, count=1)

# Strip an optional trailing semicolon (with surrounding whitespace).
stripped = re.sub(r";\s*$", "", stripped)
stripped = stripped.rstrip()

# Sanity check before we hand off to json.loads: must start with `{`.
if not stripped.lstrip().startswith("{"):
    sys.stderr.write(
        "ERROR: after stripping wrapper, content does not start with '{'\n"
        f"first 80 chars: {stripped[:80]!r}\n"
    )
    sys.exit(2)

# Validate by parsing — this catches any subtle wrapper leftover.
import json
try:
    parsed = json.loads(stripped)
except json.JSONDecodeError as exc:
    sys.stderr.write(f"ERROR: stripped content is not valid JSON: {exc}\n")
    sys.exit(3)

# Re-serialize with stable formatting (2-space indent) so the file is
# diff-friendly if anyone inspects it.
dst_path.write_text(json.dumps(parsed, indent=2) + "\n", encoding="utf-8")
PYEOF

# Validate the written file with the exact assertions from the T0.2 spec.
python3 - "${DST}" <<'PYEOF'
import json
import sys
from pathlib import Path

dst = Path(sys.argv[1])
with dst.open() as f:
    spec = json.load(f)

openapi_version = spec.get("openapi", "")
assert openapi_version.startswith("3."), (
    f"Expected OpenAPI 3.x, got {openapi_version!r}"
)
paths = spec.get("paths", {})
schemas = spec.get("components", {}).get("schemas", {})
print(f"OK: OpenAPI {openapi_version}, {len(paths)} paths, {len(schemas)} schemas")
PYEOF
