"""Layer 1.5 — Cobalt Strike OpenAPI contract test fixtures.

Provides:
- `cs_spec`: loads docs/cobalt-strike-api/spec.json into a dict
- `prism_mock_cs`: starts `prism mock spec.json` on a random ephemeral port,
  yields the base URL, tears it down on test teardown. Falls back to a
  pytest.skip if prism cannot start (e.g. due to OpenAPI 3.1.0 incompatibility).
"""

import json
import os
import socket
import subprocess
import time
from pathlib import Path

import pytest
import requests

PROJECT_ROOT = Path(__file__).parent.parent.parent
SPEC_JSON = PROJECT_ROOT / "docs" / "cobalt-strike-api" / "spec.json"


def _get_free_port() -> int:
    """Return an unused TCP port (race-condition possible but minimal risk)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def cs_spec():
    """The full OpenAPI spec as a Python dict.

    Auto-runs `make refresh-cs-spec` if spec.json is missing (which it is by
    default since spec.json is gitignored).
    """
    if not SPEC_JSON.exists():
        subprocess.run(
            ["./scripts/refresh-cs-spec.sh"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
        )
    with SPEC_JSON.open() as f:
        return json.load(f)


@pytest.fixture(scope="session")
def prism_mock_cs(cs_spec):
    """Spin up `prism mock spec.json` on an ephemeral port and yield the
    base URL. If prism cannot start (e.g. doesn't support OpenAPI 3.1.0
    features in the spec), skip dependent tests gracefully.

    Lifetime: session-scoped — one mock server per pytest run.
    """
    if not SPEC_JSON.exists():
        pytest.skip("spec.json not generated; run `make refresh-cs-spec`")

    port = _get_free_port()
    proc = subprocess.Popen(
        ["npx", "prism", "mock", "-p", str(port), "-h", "127.0.0.1", str(SPEC_JSON)],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    base_url = f"http://127.0.0.1:{port}"

    # Poll for readiness (up to 15s). If prism crashes early, capture output
    # and skip the test rather than hanging the test suite.
    deadline = time.monotonic() + 15
    last_err = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            # Process exited before ready
            out = proc.stdout.read().decode("utf-8", errors="replace") if proc.stdout else ""
            pytest.skip(
                f"Prism failed to start (likely OpenAPI 3.1.0 compat issue). "
                f"Falling back is documented in §27.13. Output:\n{out[:500]}"
            )
        try:
            requests.get(base_url + "/", timeout=1)
            break  # got SOME response, prism is up
        except requests.RequestException as e:
            last_err = e
            time.sleep(0.3)
    else:
        proc.terminate()
        out = proc.stdout.read().decode("utf-8", errors="replace") if proc.stdout else ""
        pytest.skip(
            f"Prism did not become ready in 15s. Last error: {last_err}. "
            f"Output:\n{out[:500]}"
        )

    try:
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
