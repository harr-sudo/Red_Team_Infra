# Changelog

All notable changes to the Red Team Infrastructure project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Conventions:
- **MAJOR** version: breaking changes to the operator workflow (e.g., dashboard tab structure)
- **MINOR** version: new features, deployment types, non-breaking enhancements
- **PATCH** version: bug fixes, docs, dependency bumps, no behavior change

For the full design rationale see `docs/internal/STATUS_DEEP_DIVE_2026-05-16.md` §24.

## [Unreleased]

### Added
- (entries go here as work lands on main between releases)

## [1.1.0] - 2026-05-XX (planned)

First numbered release of the refactor track. Combines the test framework
foundation (P1 #7.5) and the versioning system itself (P1 #7.6).

### Added
- Four-layer test stack: pytest + moto (Layer 1), CS OpenAPI contract tests
  via jsonschema + Prism mock server (Layer 1.5), Vitest + jsdom (Layer 2),
  Playwright + Chromium with deployment-type snapshot regression guard
  (Layer 3). See `docs/internal/STATUS_DEEP_DIVE_2026-05-16.md` §21.
- `make` targets: `dev`, `install-dev`, `test`, `test-backend`, `test-js`,
  `test-browser`, `test-browser-headed`, `test-fast`, `refresh-cs-spec`,
  `snapshot-bless`.
- `scripts/refresh-cs-spec.sh` — strips Fortra's CommonJS wrapper from
  `docs/cobalt-strike-api/spec.js` to produce `spec.json` for tooling.
- `VERSION` file at repo root + `/api/version` endpoint + UI footer
  (P1 #7.6).
- `CHANGELOG.md` (this file).
- `scripts/utilities/release.sh` (drafted in parallel by Wave 1 Agent C).

### Fixed
- `terraform/main.tf` `local.deploy_c2` → `local.deploy_c2_infra` typo
  in the in-flight EBS DLM block (P0 #1, commit 6d009e7).

## [1.0.0] - 2026-05-16

Baseline tag for the existing stable codebase, captured immediately
after the P0 #1 typo fix and before the refactor work begins.

This release includes everything operational as of mid-May 2026 —
the server-mode dashboard, 11 deployment types, file portal, domain
fronting, EBS DLM, 287 Flask routes, multi-operator infrastructure.

For the full context see `docs/internal/STATUS_DEEP_DIVE_2026-05-16.md`
§0 (executive summary) and §1 (where we are: git, AWS, transition).

### Notable historical commits

#### Added
- Add web application for infrastructure management (bba1bfa)
- Major webapp UI/UX improvements and new features (dbd0729)
- Add GOAD integration: add as submodule, update READMEs, add quick start guide (97b48ca)
- Integrate GOAD into web application (abd21bd)
- Add two deployment modes: GOAD-only (simplified) and Combined (full C2) (0029710)
- Enhanced deployment UX: progress tracking, lifecycle management, auto-project names (5d54f03)
- Major UI redesign, attack box module, domain fronting, and Terraform refactoring (a7cd962)
- Extend /deploy/outputs with config fields for per-project rendering (a38da08)
- Add per-project support to /goad/credentials endpoint (3019b0a)
- Add file portal Flask app and infrastructure to redirector bootstrap (e47e79b)
- Add themed HTML templates for file portal (Meridian + Plexura) (31314fe)
- Major webapp upgrade — topology graph, terminal tab, beacon improvements, infrastructure hardening (13cab47)
- Add operator identity middleware (/api/whoami) (3f2eb7c)
- Adaptive SSH routing — direct when reachable, ProxyJump when not (4c1eca7)
- Add dashboard server Terraform module (VPC, EC2, IAM, S3 state backend) (0d50a2e)
- Centralized server deployment, VPC peering, terminal fixes, docs reorganisation (05b01ab)
- GOAD VPC peering, direct REST API, topology operator node, terminal fixes (17e217f)
- Dynamic SG labels, server keypair automation, attack box fix (4846c9a)

#### Changed
- Per-project deployment data for multi-deployment support (aa79d6e)
- Remove local mode, server-only dashboard + security hardening (6431c39)

#### Fixed
- Address code review findings — variable shadowing, unused vars (a8d6620)
- Expand SSH key auto-detection to cover macOS, Linux, Windows (WSL/Git Bash) (f5d6427)
- Dynamic block bug in deployment_storage + main.tf try() guard (8b377ac)
- `local.deploy_c2` → `local.deploy_c2_infra` typo in DLM block (6d009e7)
