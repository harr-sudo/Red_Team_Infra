#!/usr/bin/env bash
#
# release.sh — version bump + tag helper for Red Team Infra
#
# Plan ref: §24.1 (P1 #7.6 — versioning system)
#
# Bumps VERSION (semver), promotes the CHANGELOG.md [Unreleased] section to a
# numbered release block dated today, commits, tags, and (optionally) pushes
# to origin.
#
# Usage:
#   ./scripts/utilities/release.sh patch|minor|major [--dry-run] [--no-push] [--allow-non-main]
#   ./scripts/utilities/release.sh --help
#

set -euo pipefail

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VERSION_FILE="${PROJECT_ROOT}/VERSION"
CHANGELOG_FILE="${PROJECT_ROOT}/CHANGELOG.md"

# ---------------------------------------------------------------------------
# Colors / logging
# ---------------------------------------------------------------------------
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' BLUE='' BOLD='' NC=''
fi

log_info()    { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
log_step()    { echo -e "${BLUE}[STEP]${NC} $*"; }
log_dryrun()  { echo -e "${YELLOW}[DRY-RUN]${NC} $*"; }

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
    cat <<'EOF'
release.sh — bump VERSION, update CHANGELOG.md, commit, tag, push.

USAGE:
    scripts/utilities/release.sh <patch|minor|major> [OPTIONS]
    scripts/utilities/release.sh --help

ARGUMENTS:
    patch              Bump patch component: 1.2.3 -> 1.2.4
    minor              Bump minor component: 1.2.3 -> 1.3.0
    major              Bump major component: 1.2.3 -> 2.0.0

OPTIONS:
    --dry-run          Show what would happen; make no changes, no commit, no push.
    --no-push          Commit and tag locally, but do NOT push to origin.
    --allow-non-main   Allow running off a branch other than main (for testing).
    -h, --help         Show this help and exit.

PRECONDITIONS:
    * Run from a clean git working tree (no uncommitted changes).
    * Current branch must be `main` (unless --allow-non-main).
    * VERSION and CHANGELOG.md must exist at the repo root.
    * CHANGELOG.md must have a non-empty `## [Unreleased]` section.
    * The new version tag (vX.Y.Z) must not already exist.

WHAT IT DOES:
    1. Validates preconditions (clean tree, branch, files, [Unreleased] non-empty).
    2. Computes the new version from the current VERSION.
    3. Writes new VERSION.
    4. Promotes CHANGELOG.md [Unreleased] block to [X.Y.Z] - YYYY-MM-DD,
       and inserts a fresh empty [Unreleased] block above it.
    5. git add VERSION CHANGELOG.md
    6. git commit -m "release: vX.Y.Z"
    7. git tag -a vX.Y.Z -m "Release vX.Y.Z"
    8. Unless --no-push: git push origin main && git push origin vX.Y.Z

EXAMPLES:
    scripts/utilities/release.sh patch --dry-run
    scripts/utilities/release.sh minor
    scripts/utilities/release.sh major --no-push
EOF
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
BUMP=""
DRY_RUN=0
NO_PUSH=0
ALLOW_NON_MAIN=0

if [ $# -eq 0 ]; then
    usage
    exit 2
fi

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --no-push)
            NO_PUSH=1
            shift
            ;;
        --allow-non-main)
            ALLOW_NON_MAIN=1
            shift
            ;;
        patch|minor|major)
            if [ -n "$BUMP" ]; then
                log_error "Multiple bump arguments given: '$BUMP' and '$1'"
                exit 2
            fi
            BUMP="$1"
            shift
            ;;
        *)
            log_error "Unknown argument: $1"
            usage
            exit 2
            ;;
    esac
done

if [ -z "$BUMP" ]; then
    log_error "Missing required bump argument (patch|minor|major)"
    usage
    exit 2
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
run_or_dry() {
    # $1 = description
    # rest = command
    local desc="$1"
    shift
    if [ "$DRY_RUN" -eq 1 ]; then
        log_dryrun "${desc}: $*"
    else
        log_step "${desc}: $*"
        "$@"
    fi
}

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
cd "$PROJECT_ROOT"

log_info "Repo root: ${PROJECT_ROOT}"

# Inside a git repo?
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    log_error "Not inside a git repository: ${PROJECT_ROOT}"
    exit 1
fi

# Branch check
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [ "$CURRENT_BRANCH" != "main" ] && [ "$ALLOW_NON_MAIN" -ne 1 ]; then
    log_error "Current branch is '${CURRENT_BRANCH}', expected 'main'."
    log_error "Pass --allow-non-main to override (testing only)."
    exit 1
fi
log_info "Branch: ${CURRENT_BRANCH}"

# Clean working tree
if [ -n "$(git status --porcelain)" ]; then
    log_error "Working tree is dirty. Commit or stash changes before releasing."
    git status --short >&2
    exit 1
fi
log_info "Working tree is clean."

# Required files
if [ ! -f "$VERSION_FILE" ]; then
    log_error "VERSION file is missing: ${VERSION_FILE}"
    exit 1
fi
if [ ! -f "$CHANGELOG_FILE" ]; then
    log_error "CHANGELOG.md is missing: ${CHANGELOG_FILE}"
    exit 1
fi

# Read + validate current version
CURRENT_VERSION="$(tr -d '[:space:]' < "$VERSION_FILE")"
if ! echo "$CURRENT_VERSION" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    log_error "VERSION file does not contain a valid semver: '${CURRENT_VERSION}'"
    exit 1
fi
log_info "Current version: ${CURRENT_VERSION}"

# Validate [Unreleased] section is non-empty
# Strategy: extract everything between '## [Unreleased]' and the next '## ['
# (or EOF), strip section headers and blank lines, ensure something remains.
UNRELEASED_BODY="$(awk '
    BEGIN { in_unrel = 0 }
    /^## \[Unreleased\]/ { in_unrel = 1; next }
    /^## \[/ && in_unrel == 1 { exit }
    in_unrel == 1 { print }
' "$CHANGELOG_FILE")"

if [ -z "$(echo "$UNRELEASED_BODY" | tr -d '[:space:]')" ]; then
    log_error "CHANGELOG.md [Unreleased] section is missing or empty."
    log_error "Add at least one entry (Added/Changed/Fixed/...) before releasing."
    exit 1
fi

# Strip subsection headers (### Added) + blank lines to confirm real content
UNRELEASED_CONTENT="$(echo "$UNRELEASED_BODY" \
    | grep -Ev '^[[:space:]]*$' \
    | grep -Ev '^###[[:space:]]' || true)"

if [ -z "$UNRELEASED_CONTENT" ]; then
    log_error "CHANGELOG.md [Unreleased] section has subsection headers but no entries."
    log_error "Add at least one bullet under Added/Changed/Fixed/... before releasing."
    exit 1
fi
log_info "[Unreleased] section has content."

# ---------------------------------------------------------------------------
# Compute next version
# ---------------------------------------------------------------------------
IFS='.' read -r MAJOR MINOR PATCH <<EOF
${CURRENT_VERSION}
EOF

case "$BUMP" in
    patch) PATCH=$((PATCH + 1)) ;;
    minor) MINOR=$((MINOR + 1)); PATCH=0 ;;
    major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
esac

NEW_VERSION="${MAJOR}.${MINOR}.${PATCH}"
NEW_TAG="v${NEW_VERSION}"
TODAY="$(date -u +%Y-%m-%d)"

echo -e "${BOLD}Bumping version: ${CURRENT_VERSION} -> ${NEW_VERSION}${NC}"
log_info "New tag will be: ${NEW_TAG}"
log_info "Release date:    ${TODAY}"

# Idempotency: tag must not already exist
if git rev-parse -q --verify "refs/tags/${NEW_TAG}" >/dev/null; then
    log_error "Tag ${NEW_TAG} already exists. Did a previous release half-ship?"
    log_error "Delete the tag (git tag -d ${NEW_TAG}) if it's safe, or pick a different bump."
    exit 1
fi
log_info "Tag ${NEW_TAG} does not yet exist."

# ---------------------------------------------------------------------------
# Build the new CHANGELOG.md
# ---------------------------------------------------------------------------
# We promote:
#   ## [Unreleased]
#   <content>
#   ## [prev] - date
#
# into:
#   ## [Unreleased]
#
#   ## [NEW_VERSION] - YYYY-MM-DD
#   <content>
#   ## [prev] - date

build_new_changelog() {
    awk -v new_ver="$NEW_VERSION" -v today="$TODAY" '
        BEGIN { state = "before" }
        # Match the [Unreleased] header
        state == "before" && /^## \[Unreleased\]/ {
            print "## [Unreleased]"
            print ""
            print "## [" new_ver "] - " today
            state = "inside_unreleased"
            next
        }
        # End of [Unreleased] block — next versioned section
        state == "inside_unreleased" && /^## \[/ {
            state = "after"
            print
            next
        }
        # Default passthrough
        { print }
    ' "$CHANGELOG_FILE"
}

NEW_CHANGELOG_CONTENT="$(build_new_changelog)"

if [ -z "$NEW_CHANGELOG_CONTENT" ]; then
    log_error "Internal error: rewritten CHANGELOG.md content is empty."
    exit 1
fi

# ---------------------------------------------------------------------------
# Apply changes (or dry-run preview)
# ---------------------------------------------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
    log_dryrun "Would write VERSION: ${NEW_VERSION}"
    log_dryrun "Would rewrite CHANGELOG.md to promote [Unreleased] -> [${NEW_VERSION}] - ${TODAY}"
    log_dryrun "Would run: git add VERSION CHANGELOG.md"
    log_dryrun "Would run: git commit -m 'release: ${NEW_TAG}'"
    log_dryrun "Would run: git tag -a ${NEW_TAG} -m 'Release ${NEW_TAG}'"
    if [ "$NO_PUSH" -eq 1 ]; then
        log_dryrun "(--no-push) Would NOT push."
    else
        log_dryrun "Would run: git push origin ${CURRENT_BRANCH}"
        log_dryrun "Would run: git push origin ${NEW_TAG}"
    fi
    log_info "Dry-run complete. No changes made."
    exit 0
fi

# Real run -----------------------------------------------------------------
log_step "Writing new VERSION: ${NEW_VERSION}"
printf '%s\n' "$NEW_VERSION" > "$VERSION_FILE"

log_step "Rewriting CHANGELOG.md ([Unreleased] -> [${NEW_VERSION}] - ${TODAY})"
printf '%s\n' "$NEW_CHANGELOG_CONTENT" > "$CHANGELOG_FILE"

log_step "git add VERSION CHANGELOG.md"
git add VERSION CHANGELOG.md

# Commit — if hooks fail, abort BEFORE tagging
log_step "git commit -m 'release: ${NEW_TAG}'"
if ! git commit -m "release: ${NEW_TAG}"; then
    log_error "git commit failed (pre-commit hook?). Aborting before tag."
    log_error "Your VERSION + CHANGELOG.md changes remain staged for inspection."
    exit 1
fi

COMMIT_SHA="$(git rev-parse --short HEAD)"
log_info "Created commit: ${COMMIT_SHA}"

# Tag — if this fails, the commit is already in place; surface clearly
log_step "git tag -a ${NEW_TAG} -m 'Release ${NEW_TAG}'"
if ! git tag -a "${NEW_TAG}" -m "Release ${NEW_TAG}"; then
    log_error "git tag failed. Commit ${COMMIT_SHA} is in place; tag missing."
    log_error "Inspect and either tag manually or 'git reset --soft HEAD~1' to undo."
    exit 1
fi
log_info "Created tag: ${NEW_TAG}"

# Push
PUSHED="no"
if [ "$NO_PUSH" -eq 1 ]; then
    log_warn "(--no-push) Skipping push to origin. Run manually when ready:"
    log_warn "    git push origin ${CURRENT_BRANCH} && git push origin ${NEW_TAG}"
else
    log_step "git push origin ${CURRENT_BRANCH}"
    if ! git push origin "${CURRENT_BRANCH}"; then
        log_error "git push of branch failed. Commit + tag are local only."
        log_error "Retry manually: git push origin ${CURRENT_BRANCH} && git push origin ${NEW_TAG}"
        exit 1
    fi
    log_step "git push origin ${NEW_TAG}"
    if ! git push origin "${NEW_TAG}"; then
        log_error "git push of tag failed. Branch is pushed; tag is local only."
        log_error "Retry: git push origin ${NEW_TAG}"
        exit 1
    fi
    PUSHED="yes (origin)"
fi

echo ""
echo -e "${BOLD}${GREEN}Released ${NEW_TAG} (commit ${COMMIT_SHA}, tag ${NEW_TAG}, pushed: ${PUSHED}).${NC}"
