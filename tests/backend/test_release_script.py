"""P1 #7.6 — Smoke tests for scripts/utilities/release.sh.

Verifies the release helper:
- Accepts `patch --dry-run` and exits 0 against the real repo (when VERSION and
  CHANGELOG.md are populated by Wave 1 Agents A and B respectively).
- Aborts cleanly when VERSION is missing (tested via an isolated fake-repo
  tmp_path so we never touch the real VERSION file).
- Aborts cleanly when the working tree is dirty (also via an isolated fake
  repo — the real repo's cleanliness is irrelevant to this assertion).

Plan ref: §24.1. Marked `slow` because it shells out to bash + git.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RELEASE_SCRIPT = PROJECT_ROOT / "scripts" / "utilities" / "release.sh"
VERSION_FILE = PROJECT_ROOT / "VERSION"
CHANGELOG_FILE = PROJECT_ROOT / "CHANGELOG.md"


def _has_unreleased_content() -> bool:
    """Return True iff CHANGELOG.md has a non-empty `## [Unreleased]` section."""
    if not CHANGELOG_FILE.exists():
        return False
    text = CHANGELOG_FILE.read_text(encoding="utf-8")
    lines = text.splitlines()
    in_unrel = False
    body: list[str] = []
    for line in lines:
        if line.startswith("## [Unreleased]"):
            in_unrel = True
            continue
        if in_unrel and line.startswith("## ["):
            break
        if in_unrel:
            body.append(line)
    # Strip blanks and subsection headers (### Added etc.)
    meaningful = [
        ln for ln in body
        if ln.strip() and not ln.strip().startswith("###")
    ]
    return bool(meaningful)


def _is_working_tree_clean() -> bool:
    """Return True iff `git status --porcelain` is empty in PROJECT_ROOT."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == ""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_release_script_exists_and_is_executable():
    """release.sh must ship in the repo and be executable."""
    assert RELEASE_SCRIPT.exists(), f"release.sh not found at {RELEASE_SCRIPT}"
    mode = RELEASE_SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR, "release.sh is not executable by owner"


@pytest.mark.slow
def test_release_script_help_flag_exits_zero():
    """`release.sh --help` must succeed and print usage info."""
    result = subprocess.run(
        [str(RELEASE_SCRIPT), "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"--help should exit 0, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "USAGE" in result.stdout or "usage" in result.stdout.lower()


@pytest.mark.slow
def test_release_script_dry_run_against_real_repo():
    """`release.sh patch --dry-run` should exit 0 when VERSION + CHANGELOG are valid.

    Skipped if Wave 1 Agents A/B haven't populated their files yet, or if the
    working tree is dirty (common on a feature branch with WIP), or if we're
    not on main (the script enforces main without --allow-non-main, and we
    don't want this smoke test to depend on operator branch state).
    """
    if not VERSION_FILE.exists():
        pytest.skip("VERSION file not yet present (Wave 1 Agent A pending).")
    if not CHANGELOG_FILE.exists():
        pytest.skip("CHANGELOG.md not yet present (Wave 1 Agent B pending).")
    if not _has_unreleased_content():
        pytest.skip(
            "CHANGELOG.md [Unreleased] section is empty — script would "
            "(correctly) refuse to release."
        )
    if not _is_working_tree_clean():
        pytest.skip(
            "Working tree is dirty (e.g., WIP on a refactor branch); the "
            "script would (correctly) refuse. Re-run on a clean checkout."
        )

    # Determine if we need --allow-non-main
    branch_result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    branch = branch_result.stdout.strip()
    args = [str(RELEASE_SCRIPT), "patch", "--dry-run"]
    if branch != "main":
        args.append("--allow-non-main")

    result = subprocess.run(
        args,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"dry-run should exit 0, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "Dry-run complete" in result.stdout, (
        "Expected 'Dry-run complete' marker in stdout. "
        f"stdout: {result.stdout}"
    )
    # No actual file mutations should have occurred.
    assert "Would write VERSION" in result.stdout or "DRY-RUN" in result.stdout


# ---------------------------------------------------------------------------
# Isolated-fake-repo tests (never touch real VERSION / CHANGELOG)
# ---------------------------------------------------------------------------

def _build_fake_repo(root: Path, *, with_version: bool, with_changelog: bool,
                     dirty: bool = False) -> Path:
    """Stand up an isolated git repo with our release.sh wired in.

    Layout mirrors PROJECT_ROOT/scripts/utilities/release.sh so the script's
    `../..` path resolution lands on `root`.
    """
    (root / "scripts" / "utilities").mkdir(parents=True, exist_ok=True)
    target_script = root / "scripts" / "utilities" / "release.sh"
    shutil.copy2(RELEASE_SCRIPT, target_script)
    target_script.chmod(0o755)

    if with_version:
        (root / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    if with_changelog:
        (root / "CHANGELOG.md").write_text(
            "# Changelog\n\n"
            "## [Unreleased]\n\n"
            "### Added\n- test entry\n\n"
            "## [1.0.0] - 2026-01-01\n\n"
            "### Added\n- initial\n",
            encoding="utf-8",
        )

    # Init git, default to `main`
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True, env=env)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=root, check=True, env=env)

    if dirty:
        (root / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")

    return target_script


@pytest.mark.slow
def test_release_script_aborts_when_version_missing(tmp_path):
    """Script must refuse to run if VERSION is missing."""
    script = _build_fake_repo(tmp_path, with_version=False, with_changelog=True)
    result = subprocess.run(
        [str(script), "patch", "--dry-run"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, "Script should fail when VERSION is missing"
    combined = result.stdout + result.stderr
    assert "VERSION" in combined and "missing" in combined.lower(), (
        f"Expected a 'VERSION file is missing' error. Got:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


@pytest.mark.slow
def test_release_script_aborts_when_working_tree_dirty(tmp_path):
    """Script must refuse to run when there are uncommitted changes."""
    script = _build_fake_repo(
        tmp_path, with_version=True, with_changelog=True, dirty=True
    )
    result = subprocess.run(
        [str(script), "patch", "--dry-run"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, "Script should fail when working tree is dirty"
    combined = result.stdout + result.stderr
    assert "dirty" in combined.lower() or "uncommitted" in combined.lower(), (
        f"Expected a 'dirty working tree' error. Got:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
