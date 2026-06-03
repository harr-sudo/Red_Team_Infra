# Legacy / Archived Documentation

> **This folder is an archive. Nothing in here is maintained.**

The material below is historical and planning/spec documentation, plus any
operator guides that have been **fully superseded** by the move to the
AWS-hosted Dashboard model (the single blessed onboarding path). It is kept
for reference and history only.

**Do not treat anything in this folder as current.** These documents may
describe features, flows, and architecture that **no longer exist**, including:

- **Local mode** as a production path (the dashboard now runs on an AWS-hosted
  EC2 control plane; local execution is dev-only)
- A **per-deployment SSH-relay bastion** (removed — the Dashboard Server is the
  sole SSH jump into every instance)
- **`mini` / `full` CCRTS** variants (the CCRTS lab shape has since changed)
- The legacy **"16 deployment types"** taxonomy (the deployment-type matrix has
  been reworked)
- CLI-only / pre-dashboard deployment workflows

## Where to find current documentation

| Looking for... | Go to |
|---|---|
| Project overview & setup | [`README.md`](../../README.md) (repo root) |
| Step-by-step onboarding | [`docs/GETTING_STARTED.md`](../GETTING_STARTED.md) |
| All current operator guides | the top-level [`docs/`](../) folder |

If a topic exists both here and in the current `docs/` tree, **the current
`docs/` version wins** without exception.

## What's in here

### `internal/` — historical planning, specs, audits, and status snapshots

Implementation plans, design specs, architecture reviews, gap analyses, legacy
audits, and dated status snapshots produced during development. Highlights:

- **Implementation & deployment plans** — `TERRAFORM_DEPLOYMENT_PLAN.md`,
  `GOAD_INTEGRATION_PLAN.md`, `VULNERABLE_LAB_BOLTON_PLAN.md`,
  `TOOLS_REPOSITORY_PLAN.md`, `WEBAPP_GITHUB_AUTH_PLAN.md`,
  `STATUS_TAB_UI_ENHANCEMENT_PLAN.md`, `IMPLEMENTATION_SUMMARY.md`
- **Design / direction docs** — `CONFIGURE_FLOW_DESIGN_DIRECTION.md`,
  `TESTLAB_DESIGN.md`, `M_V3_NATIVE_AGENT_BRIEF.md`,
  `WEB_APPLICATION_FEASIBILITY.md`, `WEBAPP_FILE_UPLOAD.md`,
  `WEBAPP_IMPLEMENTATION.md`, `WEBAPP_PERMISSIONS_CHECK.md`
- **Architecture & analysis** — `C2_ARCHITECTURE_REVIEW.md`,
  `CURRENT_INFRASTRUCTURE.md`, `GOAD_ARCHITECTURE_ANALYSIS.md`,
  `ATTACKBOX_S3_PATTERN_ANALYSIS.md`, `PHASE_BASED_OPERATIONS_ANALYSIS.md`,
  `DEPLOYMENT_MODE_SCALING.md`, `ENGAGEMENT_TYPES.md`, `NAMING_CONVENTIONS.md`,
  `CS_REST_API_GAP_ANALYSIS.md`, `DASHBOARD_EVALUATION.md`
- **Bolt-on R&D** — `BOLTON_REFINEMENT_compatibility.md`,
  `BOLTON_REFINEMENT_patch.md`, `BOLTON_REFINEMENT_ttp_elastic.md`,
  `BOLTON_ANSIBLE_AUDIT.md`, `BOLTON_HOST_APPLICABILITY.md`
- **Security analyses** — `S3_CONFUSED_DEPUTY_FIX.md`,
  `S3_SECURITY_ANALYSIS.md`, `SSH_KEY_MANAGEMENT.md`,
  `QUICK_START_SSH_KEYS.md`, `WHERE_CREDENTIALS_COME_FROM.md`
- **Diagrams & architecture pages** — `ARCHITECTURE_DIAGRAMS_SUMMARY.md`,
  `DIAGRAM_MAPPINGS.md`, `ARCHITECTURE_PAGE_FIX.md`,
  `ATTACKBOX_USERDATA_FIX.md`
- **Legacy audits** — `BACKEND_LEGACY_AUDIT.md`, `FRONTEND_LEGACY_AUDIT.md`,
  `TEST_PIPELINE_LEGACY_AUDIT.md`, `DEPLOY_SAFETY.md`
- **Dated status snapshots** — `STATUS_DEEP_DIVE_2026-05-16.md`,
  `TEST_COVERAGE_2026-05-20.md`, `UX_AUDIT_2026-05-20.md`
- **Early guides** — `deployment-guide.md`, `scripting-guide.md`,
  `GITHUB_SETUP.md`
- **`superpowers/`** — `plans/` and `specs/` produced during feature
  brainstorming/planning (beacon management, elastic-rules integration,
  per-project deployment data, file portal, centralized server)

### Superseded top-level guides

_None at the time of archival._ All current top-level guides remain in
[`docs/`](../). If a top-level guide is retired later, it will be moved here and
listed in this section.
