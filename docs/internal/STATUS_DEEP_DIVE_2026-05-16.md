# Red Team Infrastructure — Deep-Dive Status Report

**Date:** 2026-05-16
**Scope:** Full-stack audit of the C2 framework as it stands today — git, live AWS, dashboard transition, docs, diagrams, audit/logging, security, secrets, backup, cost, code quality, Cobalt Strike integration, bootstrap reliability, drift — plus implications of Cobalt Strike's 2026-05-18 maintenance and a design proposal for vulnerable-target labs.
**Method:** 9 parallel research agents + direct verification of the most consequential claims. All file:line references and resource counts were verified against the repo + state files + live AWS.

---

## 0. Executive summary

### What's solid
- **C2 deployment for `c2_adhoc_dev_harriss_macbook_pro_01` is fully alive** (bastion + teamserver + 2× redirector + attack box) and state matches live AWS. 86 Terraform resources, serial 148.
- **Server-mode dashboard is the canonical entry point.** Local mode was removed in `6431c39`. Dashboard server runs on its own VPC (`10.100.0.0/16`) with VPC peering into deployed C2/GOAD VPCs.
- **S3 confused-deputy protection** is correctly implemented across all 3 layers (trust policy, permission policy, bucket policy) in `terraform/modules/deployment_storage/main.tf:229-342`.
- **EBS DLM snapshots** (daily, 7-day retention, tag-filtered on `Backup=true`) are in-flight in `terraform/main.tf` and tags exist on the right volumes (c2 teamserver, attack box).
- **Bootstrap status reporting** is in place — `/opt/setup-status.json` (Linux) / `C:\ProgramData\setup-status.json` (Windows) — and the dashboard's setup-check feature consumes it.
- **187 Cobalt Strike REST routes** registered in `webapp/backend/routes/beacon.py`. Major endpoint families covered.

### What's broken or imminent
1. **🔴 CRITICAL — Cobalt Strike download/auth flow changes on 2026-05-18 (in 2 days).** Our `install_cobalt_strike.sh` runs `./update` (line 268) which talks to `download.cobaltstrike.com` and `verify.cobaltstrike.com` — both endpoints called out in the maintenance notice. Any new C2 deployment after May 18 will likely fail license activation until we test and adjust. Existing running C2 server is unaffected operationally but cannot be rebuilt cleanly.
2. **🔴 CRITICAL — `terraform validate` is failing** in the in-flight DLM addition. `terraform/main.tf` lines 927, 943, 949 reference `local.deploy_c2` but the local is named `deploy_c2_infra` (definition at line 81). Anyone running `terraform plan` right now blocks on this.
3. **🔴 HIGH — Multi-operator dashboard has no auth, no per-action audit trail, no per-operator beacon attribution.** `get_operator()` exists at `webapp/backend/middleware/identity.py` but is wired into exactly **two** places (`/api/whoami` and `deploy.py:264`). 287 other routes — including every beacon command — execute unattributed.
4. **🟡 MED — No per-operator beacon attribution.** `webapp/backend/services/beacon_service.py:23-24` uses a shared `csrestapi:password` for the CS REST API. **This is intentional and acceptable** — the CS REST API is internal-only, behind the VPC + SSH-tunnel trust boundary. The real gap is that every beacon command goes through one shared session, so the dashboard cannot tell which operator issued which command. Fix is **dashboard-side audit logging via `get_operator()`**, not per-operator CS creds.
5. **🟡 MED — Architecture diagrams partially stale.** 4 diagrams predate the server-mode regeneration (`goad-sccm`, `goad-nha`, both `combined-full-*`). 5+ diagrams that *should* exist don't (operator→dashboard tunnel topology, multi-operator access flow, EBS DLM, audit logging, vuln-lab — if added).
6. **🟡 MED — Persona-B (joining operator) onboarding is scattered across 3 docs with zero verification checklist.** No `OPERATOR_JOINING.md`.
7. **🟡 MED — Terminal sessions and beacon commands are ephemeral.** No PTY recording, no Ghostwriter/oplog export. Engagement chain-of-custody cannot be reconstructed.

### The roadmap is at the bottom (§17). The most urgent items are:
- **Today/tomorrow:** fix the Terraform DLM typo so `plan`/`apply` works; test the May 18 CS impact in advance.
- **This week:** wire `get_operator()` into a Flask `before_request` hook so every API call is attributed; load CS REST creds from Secrets Manager, not hardcoded.
- **This month:** persona-B docs, missing diagrams, terminal/beacon command audit trail, prepare vuln-lab module.

---

## 1. Where we are: git, AWS, transition

### 1.1 Recent themes (last ~60 days)
| Theme | Commits | Window | Status |
|---|---|---|---|
| Server-mode migration (local mode removed) | `6431c39`, `4846c9a`, `8b377ac` | Apr 3-4 | ✅ shipped |
| Dashboard server module + VPC peering | several | early Apr | ✅ shipped |
| File portal (decoy login on redirectors) | several | Mar 24-26 | 🟡 designed, code partial |
| Architecture diagram regeneration | `e3ce6f0`, `0e7b339` | Apr 4 | 🟡 13/20 current, 4 stale, 5+ missing |
| Topology graph + terminal tab + beacon UX | `13cab47`, `17e217f` | Mar 26 → Apr | ✅ shipped |
| EBS DLM snapshots | uncommitted in `main.tf` | now | 🔴 has typo |
| Operator badge / SSM-based setup check | several | Apr 3-4 | ✅ shipped |
| Attack box Defender exclusions-mode refactor | uncommitted (+240 lines `attack_box_init.ps1`) | now | 🟡 in-flight, fragile |

### 1.2 Uncommitted in-flight work (verified)
```
terraform/main.tf                              +68    (EBS DLM — BROKEN)
terraform/modules/attack_box/main.tf           ~      (small)
terraform/modules/attack_box/scripts/init.ps1  +240   (Defender exclusions)
terraform/modules/c2_team_server/main.tf       ~
terraform/modules/dashboard_server/main.tf     +14    (SSM messaging perms)
terraform/scripts/install_cobalt_strike.sh     ~      (SSH key polling → systemd timer)
terraform/scripts/setup_redirector.sh          ~      (UI/CSS hardening)
terraform/variables.tf                         ~
webapp/frontend/js/app.js                      +81/-81 (setup-check UI polish)
```

### 1.3 Untracked artifacts — recommended action
| Path | Size | What | Action |
|---|---|---|---|
| `.c2lint_cache/` | 12 MB | c2lint binary cache (`TeamServerImage`) | **gitignore** |
| `.mcp.json` | 467 B | aws-diagram + aws-documentation MCP config, no secrets | **commit** (tooling baseline) |
| `CS Client output log.rtf` | 329 KB | Mar 22 CS client local log | **delete** |
| `Research/` | 117 MB | BOF_DEV, CRTL_Labs, CRTO_Exam, elastic-detection-rules clone, LRQA Training | **move to private wiki / external repo** (don't keep 117M of training notes in infra repo) |
| `c2-adhoc-architecture.png` (root) | 445 KB, Mar 9 | duplicate of `generated-diagrams/c2-adhoc-architecture.png` | **delete** |
| `domain_categorization_results.csv` | 600 KB | output of `check_domain_categorization.py` | **gitignore** |
| `generated-diagrams/local-mode-backup/` | 3 MB, 16 PNGs | pre-server-mode snapshot | **delete** (already superseded; git history is enough) |
| `goad_workspace/current_deployment.json` | 183 B | runtime state | **gitignore** |
| `scripts/utilities/check_domain_categorization.py` | small | TrustedSource SWG checker — actively useful for OPSEC | **commit** |

### 1.4 Live AWS — verified

**Region:** `eu-central-1` (sole active region).

**EC2 (10 running, 0 stopped):**

| Project tag | Name | Type | State | Notes |
|---|---|---|---|---|
| c2_adhoc_..._01 | bastion | t3.micro | running | EIP 18.156.147.134 |
| c2_adhoc_..._01 | c2-teamserver-ubuntu-1 | t3.medium | running | 10.0.10.10, **LIVE — protected** |
| c2_adhoc_..._01 | redirector-ubuntu-1 | t3.small | running | EIP 3.77.179.167 |
| c2_adhoc_..._01 | redirector-ubuntu-2 | t3.small | running | EIP 63.182.232.123 |
| c2_adhoc_..._01 | attackbox-windows | t2.large | running | 10.0.10.50 |
| **goad_mini_dev_harriss_macbook_pro (tag drift)** | **redteam-dashboard-server** | t3.medium | running | EIP 3.75.17.232 — **tag drift bug** |
| goad_mini | teamserver-ubuntu | t2.medium | running | 192.168.56.40 |
| goad_mini | dc01 | t2.medium | running | 192.168.56.10, **no SSM agent (Windows DC)** |
| goad_mini | jumpbox-ubuntu | t2.small | running | EIP 63.182.129.63 |
| goad_mini | attackbox-windows | t2.large | running | 192.168.56.50 |

**VPCs:** 3 non-default — `c2_adhoc-dev-vpc` (10.0.0.0/16), `redteam-dashboard-vpc` (10.100.0.0/16), `goad_mini-vpc` (192.168.56.0/24). Peering routes verified per `MEMORY.md`.

**S3:** 4 buckets. `c2-adhoc-...-deploy-files-5fcd0f9f`, `goad-mini-...-deploy-files-65160a43`, `redteam-dashboard-tfstate-20260403160245245900000001`, **`pt-sl-test-bucket-1` (orphan from another project, confirmed not referenced anywhere in this repo — leave alone)**.

**Other:**
- 7 EIPs, all associated — $0/month overhead.
- 2 Route53 zones: `plexuramanagedsolutions.com` (2 records, looks unused), `meridianfinancialgroup.org` (9 records, active for redirectors).
- 1 ACM cert (eu-central-1, `meridianfinancialgroup.org` + wildcard), `InUse=False` — redirectors are using Let's Encrypt instead.
- 3 Secrets Manager secrets: `cs-license-key`, `c2-adhoc-...-github-token`, `goad-mini-...-github-token`.
- 9/10 SSM-managed; DC01 not (expected — Windows DC image).
- SSM agents all report `IsLatestVersion=False` — cosmetic.

**Drift / orphans:**
- 🟡 `redteam-dashboard-server` is tagged `Project=goad_mini_dev_harriss_macbook_pro` — likely leftover from a workspace switch when applying. Cosmetic, not functional, but should be re-tagged.
- 🟡 ACM cert in eu-central-1 is orphaned (`InUse=False`). No cost. Either delete or wire it into the redirector module instead of Let's Encrypt.
- 🟡 `pt-sl-test-bucket-1` is from another project — leave alone.

### 1.5 Stale Terraform workspaces (verified)
8 empty workspaces under `terraform/terraform.tfstate.d/` with 0 resources:
- `goad_mini_dev_harriss_macbook_pro_001`, `_005`, `_006`, `_007`, `_008`, `_009`, `_010`, `_12`

Not referenced by code, configs, or webapp. Safe to delete (after a `tar` backup just in case).

### 1.6 Transition assessment (single-host → server-hosted dashboard)
**Status: ~70% complete. Infrastructure done. Application layer treats all operators as equivalent.**

| Dimension | State | Evidence |
|---|---|---|
| Network isolation | ✅ done | Dashboard VPC + peering, SSH-only ingress |
| Loopback binding | ✅ done | `app.py:109` binds 127.0.0.1, `enforce_loopback()` guard at `app.py:37-39` |
| Per-operator Linux users | ✅ done | `setup-dashboard.sh:287-308` |
| Workspace-based deployment isolation | ✅ done | `terraform_service.py` workspaces |
| State backend (S3 + DynamoDB lock) | ✅ done | `dashboard_server/main.tf` |
| **Authentication** | 🔴 missing | No login. SSH key + loopback is the only barrier. |
| **Authorization / RBAC** | 🔴 missing | All operators have full IAM scope |
| **Per-action operator audit** | 🔴 missing | `get_operator()` called in 2 of 289 routes |
| **Per-operator CS REST credentials** | N/A (by design) | Shared `csrestapi:password` is intentional — CS REST API is internal-only. Per-operator attribution belongs at the dashboard audit layer, not the CS auth layer. |
| **Per-operator terminal session audit** | 🔴 missing | PTY relay ephemeral, no recording |
| **Concurrency safety** | 🟡 partial | `STATE_LOCK` global, `deployment_states` dict race condition (see §4) |
| **Code sync mechanism** | 🟡 partial | manual `rsync` from operator laptop, no CI, no version pinning |

---

## 2. Architecture diagrams — what's current, what's stale, what's missing

### 2.1 Inventory
20 PNGs in `generated-diagrams/`, 16 in `generated-diagrams/local-mode-backup/`. No source files committed — diagrams are regenerated manually via the `awslabs.aws-diagram-mcp-server` MCP (now configured in `.mcp.json`).

### 2.2 Staleness
| Diagram | Status | Issue | Priority |
|---|---|---|---|
| c2-adhoc-architecture.png | ✅ current | regenerated Apr 4 | — |
| c2-purple-architecture.png | ✅ current | — | — |
| c2-full-architecture.png | ✅ current | — | — |
| c2-adhoc-domain-fronting.png | ✅ current | — | — |
| goad-mini-architecture.png | ✅ current | — | — |
| goad-light-architecture.png | ✅ current | — | — |
| goad-full-architecture.png | ✅ current | — | — |
| **goad-sccm-architecture.png** | 🔴 stale (Feb 27) | no dashboard VPC, no peering | **HIGH** |
| **goad-nha-architecture.png** | 🔴 stale (Feb 27) | no dashboard VPC, no peering | **HIGH** |
| combined-c2-goad-mini.png | ✅ current | — | — |
| **combined-full-c2-goad-light.png** | 🟡 stale (Mar 4) | missing white-bg + landscape style update | MED |
| **combined-full-c2-goad-full.png** | 🟡 stale (Mar 4) | same | MED |
| attackbox-architecture.png | ✅ current | — | — |
| iam-security-architecture.png | ✅ current | — | — |
| ssh-key-architecture.png | ✅ current | — | — |
| s3-storage-security-architecture.png | ✅ current | — | — |
| server-mode-c2-adhoc.png | ⚠ legacy | superseded; consider deleting | LOW |
| server-mode-goad-mini.png | ⚠ legacy | superseded; consider deleting | LOW |
| server-mode-full-overview.png | ✅ current | — | — |
| ssl-options-comparison.png | ✅ current | — | — |

### 2.3 Missing diagrams (should exist)
1. **`operator-dashboard-tunnel-topology.png`** — operator laptop → SSH tunnel → dashboard (10.100.x) → peering → deployment VPCs. Today this lives only in CENTRALIZED_DASHBOARD_DESIGN.md prose. High value.
2. **`multi-operator-access-flow.png`** — N operators tunnelled in concurrently, per-user Linux accounts, shared Terraform state, identity badges. Needed for engagement onboarding decks.
3. **`audit-logging-architecture.png`** — once audit is built. Shows operator → API → identity middleware → audit log → CloudWatch.
4. **`ebs-dlm-backup-architecture.png`** — tag-based volume selection, daily snapshot schedule, 7-day retention, IAM role. Needed once DLM is fixed and applied.
5. **`vuln-lab-target-architecture.png`** — once the new vuln-lab module exists (see §16). Shows isolated target VPC peered into C2 VPC for beacon → target traversal.
6. **`cs-rest-api-data-flow.png`** — dashboard → Flask → BeaconService (TLS to CS team server REST API) → beacon. Helps onboard backend devs.
7. **`bastion-http-proxy-c2.png`** — alternative for corp-proxy bypass scenarios (mentioned in c2-adhoc.md, not visualized).

### 2.4 Doc references
- `docs/architectures/DIAGRAMS_INDEX.md` references 14 diagrams; combined-full ones link to stale files.
- `docs/internal/ARCHITECTURE_DIAGRAMS_SUMMARY.md` is itself stale (pre-Apr regeneration).
- `webapp/frontend/js/app.js` Architecture tab serves diagrams via `/api/architecture/diagram/<filename>` — if regenerated with same filename, UI updates automatically (low risk).

---

## 3. Onboarding / startup guides — per persona

### 3.1 Persona A: First operator / project owner
✅ Entry path clear (README → GETTING_STARTED → QUICK_REFERENCE).
🟡 GETTING_STARTED.md splits 50/50 Local vs Server mode even though Local Mode is removed in code. Confusing for new operators.
🟡 No mid-step verification — operator can't tell whether step 3 actually succeeded before moving to step 4.
🔴 No dashboard-specific troubleshooting (Flask won't start, terraform locked, VPC peering broken).

### 3.2 Persona B: Joining operator (second/Nth)
🔴 No dedicated doc. Info scattered across:
- README.md:55 (1 sentence)
- GETTING_STARTED.md:545-557 (Server Mode subsection, brief)
- CENTRALIZED_DASHBOARD_DESIGN.md:113-125 (design spec, not a runbook)
🔴 SSH key format/distribution unspecified.
🔴 No "Day 1 dashboard tour" — what tabs do you actually use, in what order.
🔴 No verification checklist (can I SSH? does the tunnel work? do I see existing deployments?).
🔴 No SSH key rotation procedure.

### 3.3 Persona C: AI agent (Claude/Cursor)
✅ CLAUDE.md is rich on tech stack, deployment modes, CS REST API constraints, theming, SSM preference.
🟡 No "what NOT to touch" explicit list (e.g., never `terraform destroy -target=...c2-teamserver-1` for c2_adhoc_dev_harriss_macbook_pro_01).
🟡 No memory of which workspaces are protected vs scratch.
🟡 No `AGENTS.md` describing programmatic API access patterns.

### 3.4 Recommended new docs
1. **`docs/OPERATOR_JOINING.md`** — Persona B step-by-step: SSH key gen → email/Slack delivery → admin adds via tfvars + apply → tunnel command → Day 1 tour → verification checklist.
2. **`docs/TROUBLESHOOTING.md`** — common failure modes: Flask not running, terraform locked, VPC peering, instance bootstrap, SSM session, beacon callback issues.
3. **`docs/MULTI_OPERATOR_WORKFLOW.md`** — concurrent applies, state lock recovery, audit via deployment_history, key rotation, operator offboarding.
4. **`docs/SAFE_CHANGES_FOR_AI.md`** — what NOT to touch, rollback procedures, task isolation, memory hints.
5. **`AGENTS.md`** at repo root — `programmatic API surface` for AI tools (read-only endpoints, write paths that need confirmation, dangerous endpoints).

---

## 4. Audit / logging / session tracking

### 4.1 Current state — confirmed
- `webapp/backend/app.py` imports `logging` but never initializes handlers/file destinations.
- Only structured persistence is `logs/deployment_history.json` and `logs/deployment_state/{project}.state.json`.
- `get_operator()` (`webapp/backend/middleware/identity.py`) wired into exactly **2 places**:
  - `/api/whoami` (returns name)
  - `deploy.py:264` (adds `initiated_by` to deployment history entry)
- 287+ other routes execute **without operator attribution**.

### 4.2 Audit coverage by action (verified)
| Action | Operator attributed | Persisted | Severity |
|---|---|---|---|
| Terraform plan/apply/destroy | ✅ yes (`initiated_by`) | ✅ deployment_history.json | OK |
| Beacon console commands | 🔴 no | 🔴 no | **CRITICAL** |
| Beacon file ops (upload/download/rm) | 🔴 no | 🔴 no | **CRITICAL** |
| Cred extraction (hashdump/dcsync) | 🔴 no | 🔴 no | **CRITICAL** |
| Terminal session commands | 🔴 no | 🔴 no | **CRITICAL** |
| Config writes (tfvars) | 🔴 no | 🟡 file on disk only | HIGH |
| SSH key add/remove | 🔴 no | 🟡 terraform state | HIGH |
| API authentication/access | 🔴 no | 🔴 no | HIGH |
| Beacon config changes (sleep, spawnto, blockdlls) | 🔴 no | 🔴 no | **CRITICAL** |

### 4.3 External logging — none of it exists
- CloudWatch Logs: no `aws_cloudwatch_log_group` in terraform.
- CloudTrail: not enabled by this project.
- VPC Flow Logs: not enabled.
- S3 access logs on state bucket: not enabled.
- SSH access centralization: only local `/var/log/auth.log` on each EC2.

### 4.4 Top 5 logging gaps blocking engagement use
1. **Beacon command audit** — every `consoleCommand` and every task POST should record `(operator, beacon_id, command, timestamp, taskId, ack, result)`.
2. **Terminal session recording** — PTY/SSH sessions are ephemeral. Need a `script(1)`-style wrapper or websocket → file tee per operator.
3. **System-wide operator middleware** — Flask `before_request` hook to inject operator into `g.operator`, plus per-request access log: `(timestamp, operator, method, path, status, latency)`.
4. **Centralized external storage** — CloudWatch Logs Agent on dashboard + ship `/opt/redteam/logs/audit.log` to a dedicated log group.
5. **Ghostwriter / Sigma-compatible oplog export** — engagement reporting requires it. None of `oplog|ghostwriter|operation_log|beacon_log` appears in the codebase.

---

## 5. Security posture

### 5.1 Findings — verified
**Solid:**
- S3 confused-deputy protection (3 layers, `deployment_storage/main.tf:229-342`).
- All sensitive variables in `terraform/variables.tf` marked `sensitive = true`.
- EBS encryption enabled across modules.
- GitHub PAT and CS license in Secrets Manager.
- Bastion + dashboard SSH ingress scoped to `/32` operator IP.

**Risky:**
- 🟡 Redirector HTTP/HTTPS = `0.0.0.0/0` when domain fronting is disabled (intentional for C2 ops; lock down via `enable_domain_fronting=true` for engagements).
- 🟡 Dashboard IAM policy has `*` resource on `s3:*`, `route53:*`, `acm:*`, `dynamodb:*`, `logs:*`, `cloudwatch:*` (`dashboard_server/main.tf:186-282`). Scope to project prefix where possible.
- 🟡 EBS uses AWS-managed KMS, not CMK. Acceptable for lab, consider CMK for engagement data.
- 🔴 No VPC Flow Logs — incident response blind.
- 🔴 No GuardDuty / Security Hub — no continuous threat detection on the C2 fleet itself.
- 🟡 C2 team server has SSH fallback ingress from management IPs (`security/main.tf:28-35`) alongside bastion-only rule. Remove fallback if bastion is sole vector.

### 5.2 Secrets
- **Hardcoded `csrestapi:password`** in `beacon_service.py:23-24` — **by design, accepted.** CS REST API is internal-only behind VPC + SSH-tunnel trust boundary; operator auth lives at the dashboard SSH layer. No action.
- **Windows RSA private key in Terraform state** (via `tls_private_key` resource). Local state on disk is unencrypted. **Fix:** move state to remote S3 backend immediately.
- **Public key in tfvars** — fine, public keys are not secrets.
- **Git history clean** — no `*.tfvars`/`*.env`/`*.key` ever committed (verified).

---

## 6. Backup & disaster recovery

### 6.1 EBS DLM (in-flight)
- Daily 03:00 UTC, 7-day retention, 7-snapshot cap.
- Targets volumes tagged `Backup="true"`.
- Tags verified present on `c2_team_server/main.tf:94` and `attack_box/main.tf:163`.
- **🔴 BLOCKED — `local.deploy_c2` typo at `terraform/main.tf:927, 943, 949` — `terraform validate` fails. Definition is `local.deploy_c2_infra` at line 81. One-line fix.**
- ❌ Dashboard server volume **NOT tagged** for backup — should be (it stores operational config and logs).
- ❌ GOAD instances **NOT tagged** for backup — fine for ephemeral labs, but the GOAD jumpbox holds Ansible inventory + lab state.

### 6.2 State backup
- S3 versioning enabled on tfstate bucket (`dashboard_server/main.tf:309-313`).
- AES256 SSE on bucket.
- Local-state-only for ad-hoc workspaces — risky.

### 6.3 DR gaps
- No runbook for "we lost the dashboard, how do we recover."
- CS profiles / Malleable C2 config — only preserved if in deployment_storage S3 (which is versioned, so OK).
- Beacon logs / downloaded files — no persistence outside CS team server's own EBS.

---

## 7. Cost posture (eu-central-1)

| Item | Qty | $/mo each | Subtotal |
|---|---|---|---|
| t3.micro | 1 (bastion) | $8 | $8 |
| t3.small | 2 (redirectors) | $17 | $34 |
| t3.medium | 2 (c2-team, dashboard) | $33 | $66 |
| t2.medium | 2 (goad team, goad dc) | $36 | $72 |
| t2.small | 1 (goad jumpbox) | $18 | $18 |
| t2.large | 2 (c2 attackbox, goad attackbox) | $72 | $144 |
| EIPs (7, all associated) | | free | $0 |
| S3 (4 buckets) | | ~$2-3 | $10 |
| EBS (~400 GB gp3) | | $0.10/GB | $40 |
| DLM snapshots (once fixed) | | $0.05/GB | ~$5-10 |
| Data egress (~100 GB/mo) | | $0.09/GB | $9 |
| Route 53 (2 zones) | | $0.50 | $1 |
| ACM | | free | $0 |
| **Total** | | | **~$407/mo** |

**Quick wins:**
- Auto-stop attack boxes off-hours via EventBridge + Lambda. Both run 24/7 at $72/mo each. Stopping 16 h/day saves ~$96/mo. **Highest-ROI cost change.**
- Schedule GOAD lab teardown after sessions (t2.medium/large fleet = ~$162/mo idle).
- Consider t3.medium for GOAD instead of t2 (minor savings + nitro features).

---

## 8. Multi-deployment state management

### 8.1 Confirmed
- 1 active C2 workspace (`c2_adhoc_dev_harriss_macbook_pro_01`, 86 resources, serial 148, TF 1.5.7).
- 1 active GOAD workspace (`goad_mini_dev_harriss_macbook_pro`, serial 86).
- 8 empty cruft workspaces (`_001` through `_010`, `_12`) — safe to delete.
- Per-project state JSON at `logs/deployment_state/<workspace>.state.json`.
- Single global `STATE_LOCK = threading.Lock()` at `deploy.py:165`.

### 8.2 Concurrency risks
- `STATE_LOCK` protects disk writes but NOT in-memory `deployment_states` dict mutations. Two operators clicking Deploy on the same project simultaneously can race.
- `terraform_service.py:257` `workspace_select()` is not atomic relative to subsequent deploy. Two threads could select the same workspace.
- DynamoDB lock prevents simultaneous `terraform apply` on same workspace — but does NOT prevent concurrent `terraform plan` reading stale state, then one apply invalidating the other's plan.
- No project ownership / RBAC — every operator sees every project in the UI.

### 8.3 Fixes (low effort, high value)
1. Per-project `RLock` keyed by workspace name, acquired before any state mutation.
2. Validate workspace ownership/lease before allowing deploy/destroy.
3. Add `current_owner` field to deployment_state JSON; reject mutations if owner mismatches and lease not expired.

---

## 9. MCP server integration

### 9.1 `.mcp.json` contents (verified)
```json
{
  "mcpServers": {
    "aws-diagram-mcp-server":        { "type": "stdio", "command": "uvx", "args": ["awslabs.aws-diagram-mcp-server"],         "env": { "FASTMCP_LOG_LEVEL": "ERROR" } },
    "aws-documentation-mcp-server":  { "type": "stdio", "command": "uvx", "args": ["awslabs.aws-documentation-mcp-server@latest"], "env": { "FASTMCP_LOG_LEVEL": "ERROR" } }
  }
}
```
No secrets. **Should be committed** — establishes a tooling baseline for everyone working with AI agents on the repo.

### 9.2 Recommended additions for red team workflow
- **Cobalt Strike REST API MCP** — wrap `docs/cobalt-strike-api/spec.js` (14K lines) so AI agents can query the spec deterministically rather than re-reading. Highest-value addition.
- **Terraform State MCP** — query live state via `terraform show -json` rather than subprocess wrangling.
- **CloudWatch Logs MCP** — once audit logging is in place.
- **Burp MCP** — already in user's global config; document it as part of recommended setup.

### 9.3 Documentation gap
CLAUDE.md has nothing about MCP setup. Add a short section pointing at `.mcp.json` and what it provides.

---

## 10. Dashboard webapp — code quality

### 10.1 Size
- Backend: 28 Python files, ~15.4K LoC. Largest: `deploy.py` (5,423 LoC).
- Frontend: `app.js` (21,187 LoC) + `index.html` (2,419 LoC). No modules.

### 10.2 TODOs / debt
- `webapp/backend/utils/validators.py:86` — CIDR containment check stubbed.
- `deploy.py:3683` — deprecated SSH key download endpoint, migration in progress.
- `app.js:12130` — `@deprecated` UI key-gen logic, XXX-placeholder detection (lines 7367-7410).
- Zero tests anywhere (`test_*.py`, `tests/` — none).
- Type hints inconsistent: `terraform_service.py` fully typed, `deploy.py` ~5% typed.

### 10.3 Top 3 refactor candidates
1. **`deploy.py`** (5,423 LoC) — split into `routes/deploy_state.py`, `routes/deploy_orchestration.py`, `routes/file_mgmt.py`, `routes/workspace.py`. Each <1K LoC.
2. **`app.js`** (21K LoC) — modularize via ES6 imports. Start with extracting `BeaconController`, `TERMINAL`, `Topology` into separate files. Add a bundler (esbuild is the lightest).
3. **`terraform_service.py`** — extract `TerraformOutputParser` class so service.py is purely subprocess management and parser is unit-testable.

### 10.4 Code smells
- Global `deployment_states` dict mutated without consistent locking.
- Silent `try/except` blocks (e.g., `deploy.py:147-148, 223-224, 338-339`) swallow errors and only `print` them.
- Magic strings for deployment types (`'c2-adhoc'`, etc.) duplicated in ~11 places.
- 73 `console.log/error` calls in `app.js` — debug-heavy, not production.
- 553 inline `style=` in `index.html` (40% non-semantic).
- 15+ raw hex colors in `style.css` lines 273-305, 2527-2564, 3535 — bypass the palette.css theming.

---

## 11. Frontend UX

### 11.1 Feature tabs (verified in `index.html`)
1. Dashboard — overview + Elastic detection rules
2. Pre Reqs — AWS prereqs
3. Configuration — deployment type selector
4. Deploy — orchestration + status
5. Deployment Manager — multi-deployment lifecycle
6. Tools — utilities
7. Architecture — diagrams + docs
8. Beacon — CS C2 control
9. Terminal — PTY-over-WebSocket
10. Settings — preferences

Plus operator badge + theme toggle.

### 11.2 Concurrency issues
**Multiple concurrent pollers** with no jitter or visibility-aware pause:
- Beacon status polling (`app.js:2719`)
- Last-seen ticker every 1s (`app.js:2729`)
- Task feed every 3s (`app.js:3841`)
- Activity log every 5s (`app.js:5129`)

With 3+ operators on the Beacon tab, backend sees 3× independent 3-5s polls — synchronized spikes. **Fix:** add 0.5-1s jitter, pause when document.hidden, exponential backoff on 5xx.

### 11.3 Error UX — primitive
- Mostly `console.error(...)` with silent `.catch(() => {})` (lines 121, 58, 801-803).
- No toast library. Errors render as inline HTML or vanish.
- No error boundary; one route crash blanks the UI.

### 11.4 Accessibility
- 1 ARIA label in the entire frontend (line 25, theme toggle).
- One @media query (768px). At 1280px the dashboard horizontally scrolls in places.

### 11.5 In-flight `app.js` changes
`+81/-81` refining the setup-check tab — preventing re-render flashes during content loading, fixing `var(--danger-text)` references, improving polling to avoid wiping lazy-loaded host details, tightening badge/button styling. UI polish only, not feature work.

### 11.6 File portal
Separate Flask micro-app, designed (commits 2026-03-26), partially wired into dashboard config. Per-redirector decoy login (`/login`) with bcrypt-hashed shared cred, session expiry, fail2ban, two themed templates (Meridian + Plexura). **Status: config UI exists in dashboard; Terraform + systemd wiring not done.** Tracking in `webapp/backend/utils/config_parser.py` config blocks.

---

## 12. Cobalt Strike REST API integration

### 12.1 Coverage (verified)
- **187 Flask routes** in `webapp/backend/routes/beacon.py`.
- Categories: BeaconInfo, ConsoleCommand, JobsAndTasks, CredsAndTokens, FileAndRegistry, NetworkRecon, PayloadAndArtifacts, Pivoting, ProcessAndExecution, Capture (partial), Tunneling (partial), BeaconConfig, Listeners, ServerConfig (minimal).
- **Estimated coverage: 75-80% operational, 85% structural** vs the OpenAPI spec.

### 12.2 Major gaps
- No keystroke retrieval (`GET /data/keystrokes`).
- No browser pivot start.
- No .NET assembly execution endpoints.
- ServerConfig: only health check; missing killdate, profile, systeminformation.

### 12.3 Spec adherence
- Field names mostly correct (sleep, spawnto, blockdlls, fakeArguments).
- 🔴 **Task polling is incomplete.** `pollTaskOutput()` in `app.js:3734-3828` retries only 3× at 500ms. The spec is explicit: tasks like `sleep`/`checkin` stay `IN_PROGRESS` forever — frontend should distinguish `taskAcknowledgements` from `result` and stop polling appropriately. Today, long-task output (anything that doesn't complete in <1.5s) is silently abandoned.

### 12.4 Auth / multi-operator
- ✅ Shared `csrestapi:password` (`beacon_service.py:23-24`) is **intentional and accepted** — CS REST API is internal-only, reached over VPC peering / SSH tunnel only. No fix needed.
- 🟡 Single shared session token means all operators appear as the same user to the CS team server. Per-operator attribution must come from the dashboard audit layer (`get_operator()` + audit log), not the CS auth layer.
- 1-hour token TTL, refresh 5 min before expiry — refresh is global, can interrupt other operators' tasks. Worth tightening: shared singleton service should serialize refresh + retry vs. dropping in-flight tasks.

### 12.5 Resilience
- No reconnect logic if CS team server goes down.
- No cache TTL on listeners (must manually refresh).
- No circuit breaker; 10s timeout per request, no backoff.

### 12.6 Top 5 CS integration gaps
1. Multi-operator command attribution at the dashboard audit layer (every `consoleCommand` and task POST writes `(operator, beacon_id, command, ts, taskId, result)` to `audit.log`). Optionally also tag the beacon via `/beacons/{bid}/note` with the operator who last acted on it. Do **not** rework CS REST creds — they're fine as shared.
2. Fix long-task polling (configurable max attempts, exponential backoff, distinguish ack from result).
3. Add reconnect + circuit breaker for CS team server downtime.
4. Implement GET endpoints for current beacon config (sleep, spawnto, ppid, blockdlls) — already SET, need READ for verification.
5. Serialize token refresh so it doesn't interrupt other operators' in-flight tasks.

---

## 13. Cobalt Strike May 2026 maintenance — operational impact

### 13.1 What's changing
- **Date: Monday 2026-05-18 (in 2 days).**
- "Small change to the Cobalt Strike download and authentication workflow." (per Cobalt Strike blog snippet; full post returned HTTP 403 to our fetch — Fortra blocks bots).
- Affected endpoints: `download.cobaltstrike.com` (download), `verify.cobaltstrike.com` (auth file verification + version hash check), `authgen.slp` (auth file generator).
- Historical precedent: previous changes (e.g., 4.8 release) rotated TLS certs on these endpoints. The old `update` binary had to be replaced.

### 13.2 What this project does today (verified)
- `terraform/scripts/install_cobalt_strike.sh:268` runs `./update` piped with the license key from Secrets Manager:
  ```
  echo "$CS_LICENSE_KEY" | sudo ./update > /tmp/cs-update-output.log 2>&1
  ```
- This `./update` binary contacts `download.cobaltstrike.com` and produces `cobaltstrike.auth.server`.
- Without this step succeeding, **no new C2 team server can be deployed.**

### 13.3 Impact
- **Existing running team server:** unaffected day-to-day. License is already activated. ✅
- **Re-deploying that team server after May 18:** likely fails until we test and adjust. 🔴
- **Any new C2 deployment after May 18:** likely fails the same way. 🔴
- **Beacon REST API** (separate, runs on CS team server itself): unaffected. ✅
- **License rotation:** if the operator generates a new auth file via the auth-gen workflow, that flow is what's changing — so this WILL be affected.

### 13.4 Action plan (priority order)
- **P0 (now):** Take a fresh AMI/EBS snapshot of the live `c2_adhoc...teamserver` BEFORE May 18 so we have a known-good baseline that doesn't need re-activation. (Tag a manual snapshot in addition to the DLM cycle once DLM is fixed.)
- **P0 (May 18):** Watch the Cobalt Strike blog (`https://www.cobaltstrike.com/blog`) and release notes (`https://download.cobaltstrike.com/releasenotes.txt`) for the maintenance post-mortem. Note any new version/binary required.
- **P1 (May 18-20):** Test `install_cobalt_strike.sh` end-to-end on a throwaway team server in a sandbox workspace. Fix anything broken.
- **P1:** Once Fortra publishes the change details, update `install_cobalt_strike.sh` and `docs/COBALT_STRIKE_DEPLOYMENT.md` accordingly.
- **P2:** Consider hosting our own internal mirror of the CS update artifacts in a private S3 bucket as a fallback for future maintenance windows. (License auth still has to go through Fortra; the artifact mirror is just for resilience.)
- **P2:** Update CLAUDE.md note about CS install scripts being affected by Fortra's maintenance windows.

Sources: see §18.

---

## 14. Terraform code health

### 14.1 Blocker (verified)
🔴 `terraform/main.tf` lines 927, 943, 949 reference `local.deploy_c2` — local is named `deploy_c2_infra` at line 81. `terraform validate` fails. One-line fix.

### 14.2 Other findings
- `terraform fmt -check -recursive` would fail — 20+ alignment drifts in main.tf.
- Terraform core pinned to `>= 1.0` (no upper bound) — recommend `>= 1.0, < 2.0`.
- AWS provider pinned `~> 5.0` uniformly across all 13 modules ✅.
- 6 inline `aws_iam_role_policy` resources in `deployment_storage/main.tf` — deprecated pattern, prefer `aws_iam_role_policy_attachment` + managed policies.
- 4 dashboard VPC peering resources at `main.tf:713-747` use the same complex conditional — candidate for extraction into a small module.
- `var.deployment_type` has no `validation { condition = ... }` — typos silently fall through to "none". Add a check.
- Hardcoded IPs in main.tf (`10.0.0.10` bastion, `10.0.10.50` attackbox, `10.0.10.10`, `10.0.11.10` c2, `192.168.56.x` goad) — should be variables for multi-tenant.

---

## 15. Bootstrap reliability

| Script | Strict | Idempotent | Logged | Status JSON | Risk |
|---|---|---|---|---|---|
| `install_cobalt_strike.sh` | `set -e` (no -uo) | partial | ✅ `/var/log/cs-install.log` | ✅ `/opt/setup-status.json` | **MED** (May 18 risk) |
| `setup_redirector.sh` | `set -e` (no -uo) | partial | ✅ `/var/log/redirector-setup.log` | ✅ | LOW |
| `attack_box_init.ps1` | `$ErrorActionPreference = "Continue"` | partial | ✅ | ✅ `C:\ProgramData\setup-status.json` | **MED** (Defender exclusions mode in-flight) |
| `bastion/user_data.sh` | `set -euo pipefail` ✅ | yes | ✅ | ✅ | LOW |
| `goad/jumpbox_init.sh` | `set -e` (no -uo) | partial | ✅ | ❌ missing | MED |
| `dashboard_server/user_data.sh` | `set -euo pipefail` ✅ | yes | ✅ | ❌ missing | LOW |

**The big in-flight change** — `attack_box_init.ps1` +240 lines — switches Defender from *fully disabled* to *engine-active with exclusions* (for ThreatCheck dependency). Significantly safer for OPSEC analysis but fragile post-reboot (exclusions may not apply until service restart). Add a post-reboot verification step.

**Gaps:** missing `set -uo`, no status JSON for jumpbox or dashboard server, no automated retry for download steps in some scripts.

---

## 16. Vulnerable target lab — design proposal

### 16.1 Why
The framework deploys attackers (CS team server, redirectors, attack box) and a vulnerable AD lab (GOAD). It does **not** deploy isolated targets for tool development / detection rule testing / CVE replication. A purpose-built vuln-lab module would let operators stand up known-bad targets next to GOAD for end-to-end tool validation.

### 16.2 Landscape — what's out there (key projects)
| Project | Form | Strength | Fit for us |
|---|---|---|---|
| **Vulhub** (`vulhub/vulhub`) | docker-compose, ~100+ CVEs | huge CVE library, no infra needed | ⭐⭐⭐ wrap in a Terraform module that boots EC2 + docker-compose pulls |
| **Splunk Attack Range** (`splunk/attack_range`) | Terraform + Ansible, AWS/Azure/GCP | full purple-team stack with PurpleSharp, Zeek, Splunk integration | ⭐⭐ heavyweight but inspirational for instrumented design |
| **GOAD** (already in this repo) | Vagrant + Ansible | vulnerable AD lab | already integrated |
| **APT-Lab-Terraform** (`DefensiveOrigins/APT-Lab-Terraform`) | Terraform (Azure), 3 systems | small purple-team kit, DC + member + HELK | ⭐ reference for module shape |
| **AWSGoat** (`ine-labs/AWSGoat`) | Terraform | vulnerable AWS *infrastructure* (IAM, S3, Lambda, ECS) | ⭐⭐ different category — for cloud security testing, not endpoint targets |
| **CloudGoat** (rhinosecuritylabs) | Python + Terraform | vulnerable AWS scenarios | ⭐⭐ same niche as AWSGoat |
| **IAM Vulnerable** (`BishopFox/iam-vulnerable`) | Terraform | 250+ IAM resources for priv-esc practice | ⭐⭐ great for IAM-focused engagements |
| **CISA Vulnerable Instances** (`cisagov/vulnerable-instances`) | Packer + Vagrant | gov-published vulnerable VMs | ⭐ niche but trustworthy provenance |
| **vulnlab_aws** (`DarkRelay-Security-Labs/vulnlab_aws`) | Terraform | vulnerable pentest lab on AWS | ⭐ smallest reference module |
| **ExpanseAzureLab** | Terraform (Azure) | vulnerable Azure resources | not our cloud |
| **DetectionLab** (`clong/DetectionLab`) | Vagrant + Packer | DC + Win10 + Splunk + Sysmon | **NO LONGER MAINTAINED** — reference only |

### 16.3 Recommended approach — three target categories
Build `terraform/modules/vuln_lab/` with selectable "target sets":

1. **`vuln_lab_web`** — single Ubuntu EC2 running docker-compose with selectable Vulhub stacks (Log4Shell, Spring4Shell, GitLab CVE-X, etc.).
   - Operator picks targets via tfvars: `vuln_lab_targets = ["log4j-CVE-2021-44228", "spring-CVE-2022-22965"]`.
   - Vulhub repo cloned at boot via Ansible, `docker compose up -d` for selected dirs.
   - Networking: place in C2 VPC, in a dedicated **target subnet** (`10.0.20.0/24`), routable from attack box and C2 team server only.

2. **`vuln_lab_windows`** — Windows Server 2019/2022 with selectable role configurations:
   - SMB v1 enabled (EternalBlue)
   - Print Spooler (PrintNightmare CVE-2021-34527)
   - Old service binaries with weak permissions
   - Stored creds in registry / GPP cpassword
   - LAPS NOT configured + reused local admin password
   - Operator selects via `vuln_lab_win_scenarios = ["printnightmare", "smb-v1", "weak-services"]`.

3. **`vuln_lab_iam`** — vendored IAM-Vulnerable scenarios from BishopFox, scoped to a dedicated test AWS account or sub-OU (not the production AWS account hosting C2). Optional, only for cloud-pentest engagements.

### 16.4 Integration with existing stack
- New deployment type: `c2-with-vulnlab` (extension of `c2-adhoc`) that provisions C2 + vuln_lab targets in the same VPC.
- VPC peering already supports cross-VPC; the simpler model is shared-VPC + separate-subnet for targets.
- Targets get the standard `Backup="false"` tag (snapshots not needed for throwaway targets).
- Targets get a distinct security group that *only* allows ingress from the attack box and C2 team server. **No public IPs. No internet ingress.**
- Dashboard UI: new "Targets" tab listing live target hosts + their CVE/scenario metadata + a "destroy targets" button independent of the C2 destroy flow.

### 16.5 Operator workflow
1. Operator selects deployment type `c2-with-vulnlab` in dashboard.
2. Picks target set from a dropdown (web / windows / iam — multi-select).
3. Picks specific scenarios (Log4Shell + PrintNightmare + weak-services).
4. `terraform apply` → targets boot, Ansible/docker-compose configures them, scenario metadata written to S3.
5. Dashboard Targets tab shows: host, scenarios active, suggested attack tools, expected detection rules (cross-ref with `Research/elastic-detection-rules`).
6. Operator runs payload from attack box → callback to C2 → beacon executes against target.
7. At end of engagement, `terraform destroy -target=module.vuln_lab` cleans up targets but leaves C2 alone.

### 16.6 Why this is well-suited
- We already have the C2 + AD stack (GOAD). Vuln-lab fills the missing *non-AD endpoint targets* gap.
- Vulhub's catalogue is huge and well-maintained — wrap it, don't reinvent.
- Aligns with the project's existing pattern (deployment_type → module selection → Ansible config).
- Lets the same dashboard drive attack + target lifecycle.

### 16.7 Effort estimate
| Phase | Effort | Deliverable |
|---|---|---|
| Phase 1 | ~1 week | `vuln_lab_web` module (Vulhub-on-EC2) + dashboard tab + one scenario (Log4Shell) |
| Phase 2 | ~1 week | Add 5-10 more Vulhub scenarios as scenario presets, document each |
| Phase 3 | ~2 weeks | `vuln_lab_windows` module with 3-4 scenarios (PrintNightmare, SMBv1, weak-services, GPP creds) |
| Phase 4 | ~1 week | Detection-rule cross-ref UI (Elastic rules → scenario mapping) |
| Phase 5 | optional | `vuln_lab_iam` for cloud-pentest engagements |

Sources for all of the above are in §18.

---

## 17. Prioritized roadmap

> Cross-references: dashboard tab refactor (D-phases below) is fully specified in §19 (proposal) and §20 (sanity-check + per-element migration map). CS May 2026 maintenance impact is detailed in §13. Vuln-lab module design is in §16. **All items below are estimates — none are started; user has not yet authorised any code changes.**

### P0 — this week (operational risk)
1. **Fix `local.deploy_c2` → `local.deploy_c2_infra`** at `terraform/main.tf:927, 943, 949`. Run `terraform validate` to confirm green. *5 minutes.* — unblocks every `terraform plan`/`apply` on the in-flight DLM change.
2. **Watch for the CS May 2026 maintenance post-mortem on Mon 2026-05-18.** No pre-emptive action needed — live `c2_adhoc...teamserver` already has `cobaltstrike.auth.server`, unaffected day-to-day. Risk is **only** for rebuilds and new deployments after May 18. See §13.
3. **(If a rebuild becomes needed)** Test `install_cobalt_strike.sh` on a throwaway workspace; patch the `./update` flow if Fortra changed the auth handshake. *2-4 hours when the day comes.* — **If P1 #7.5 (test framework) has shipped by then**, also re-pull Fortra's spec → `make refresh-cs-spec && make test` surfaces every API drift as named failures (Layer 1.5, §21.2 + §21.12). **If it hasn't shipped yet (likely, since today is 2026-05-16 and framework needs 8-10h), fall back to manual install/test loop.** See §26.8 item 1.

### P1 — next 2 weeks (multi-operator readiness + dashboard refactor foundation)

**Audit + multi-operator (4 items)**

4. **Wire `get_operator()` into a Flask `before_request` hook** that puts it on `g.operator` and emits a structured access log per request. Add `audit.log` in `logs/`. *Half-day.* (Unlocks per-operator beacon attribution at the dashboard layer — shared `csrestapi:password` stays as-is per §5.2.)
5. **Fix beacon long-task polling** in `app.js:3734-3828` — distinguish acknowledgements from results, configurable max attempts, exponential backoff. *1 day.*
6. **Persona-B onboarding doc** — `docs/OPERATOR_JOINING.md` with SSH key gen, tunnel, day-1 tour, verification checklist. *Half-day.*
7. **Per-project RLock** in `deploy.py` keyed by workspace name — fix the race condition where two operators clicking Deploy on the same project corrupt each other's state. *Half-day.*

**Test framework + versioning (must ship before D-phases)**

7.5 **Stand up test framework** — see §21 + §22 + §23. **Revised estimate: 8-10h, 9-10 commits** on branch `refactor/test-framework` per §26.2. Includes Playwright Chromium download (~500 MB), Prism 3.1.0 verification, snapshot capture across 27 DEPLOYMENT_CONFIGS. Layer 2 (Vitest) scoped to mock-infra only or skipped (see §26.3).

7.6 **Versioning system** — Tag current `main` as **`v1.0.0`** (first numbered release of existing stable code). Add `VERSION` file + `/api/version` endpoint + UI footer + `CHANGELOG.md` (auto-generate initial entry from recent git log) + `scripts/utilities/release.sh` helper. After this lands, bump to `v1.1.0` (test framework + versioning together). See §24 for full spec; supersedes the `v0.1.0` framing per Decision #10. *~2-3h, 2 commits on branch `refactor/versioning`.*

7.7 **T1 — Design pilot** (taste-skill A/B comparison). Build the D1 global header TWICE on branch `refactor/design-pilot`: once as baseline (no taste-skill), once with taste-skill at dials `6/3/6` (Decision #13). Both rendered on a throwaway `/preview/header` Flask route with side-by-side comparison + theme toggle. User picks the winner; decision propagates to D1 final + D3/D4 pill switchers + D5 widgets. Artifacts deleted at D1 end. **Slots between P1 #7.6 and D0 per Decision #14.** *~3-4h, ~4 commits.*

**Dashboard refactor — foundation (D0–D2, must ship in order)**

8. **D0 — Routing alias layer + sub-pill awareness** in `APP.navigateTo()` / `APP.loadPageContent()` / `sessionStorage` / URL hash. **Includes JSON-vs-string `sessionStorage` backwards-compat** (existing operator browsers have stale string values; D0 must try/catch + fallback per §26.4 item 4). **No DOM changes, no user-visible effect.** Prerequisite for D3–D4 so they can land independently without touching any of the 14 existing cross-link call sites (§20.3, §20.8 item 5). **Revised estimate: 2-3 hours, 3-4 commits.**
9. **D1 — Global header strip** above the tab nav: active-deployment selector + cost indicator + (existing) operator badge + theme toggle. Per-tab dropdowns stay (removed in D4). Pure additive. (§19.5 Phase 1, §20.4) *Half-day.*
10. **D2 — Move AWS Pre Reqs into Settings** as a new "AWS & SSH Prerequisites" section ABOVE Cost Tracker. Remove the top-level "Pre Reqs" nav button. Yellow first-run banner on Dashboard if any check has never passed. Nav: 10 → 9 tabs. (§19.5 Phase 2, §20.7) *Half-day.*

### P2 — next month (dashboard refactor body + depth + polish)

**Dashboard refactor — body (D3–D5)**

11. **D3 — Merge Configuration + Deploy + Deployment Manager → "Deployments" tab** with 3 sub-pills (Configure / Deploy / Manage). **Re-parent the three existing `tab-page` subtrees verbatim — do not rewrite.** **The "Edit Config" button in Deploy sub-pill must be an inline collapsible panel, NOT a pill-flip** — preserves operator form state + scroll position mid-engagement (§26.9 polish). Add sub-view lifecycle hooks so `deploymentPollInterval` / `_destroyPollInterval` cleanup logic mirrors today's tab-leave semantics at the sub-pill level (§20.6 + §26.4 item 2). **D3.0 snapshot capture must pass green against unmodified `main` FIRST** or the refactor stalls — see §26.8. Nav: 9 → 7 tabs. (§19.5 Phase 3, §20.2, §20.6, §20.9) **Revised estimate: 2-3 days, 8-9 commits.**
12. **D4 — Merge Beacon + Terminal + Tools → "Operations" tab** with 3 sub-pills. **Keep the three per-tab selectors as per-sub-pill overrides of the global active-deployment** (per Decision #9 — do NOT delete them outright; they default to mirroring global but can be locally overridden). Wire `BEACON.onDeploymentSelected`, `TERMINAL.onDeploymentSelected`, `loadToolsConnectionInfo` to read both global state + local override. **Apply sub-view lifecycle hooks in the same commit as each sub-view re-parent — non-optional per Decision #8** (§26.9 Blocker A). Nav: 7 → 5 tabs. (§19.5 Phase 4, §20.4 partial, §20.6) **Revised estimate: 2-3 days, 7-8 commits.**
13. **D5 — Dashboard launchpad (expanded per Decision #19)** — 10 widgets, action-dense: (1) primary "+ New Deployment" hero CTA, (2) "Resume last deployment", (3) AWS prereqs nudge, (4) Live deployments grid (3 clickable cards), (5) Active beacons widget, (6) Recent activity feed (placeholder pre-P1#4), (7) Cost trend tile, (8) Budget alert callout, (9) Failed deployments alert, (10) Existing Elastic Detection Rules card. Cost view defaults to aggregate (uses D5.0's `/api/costs/aggregate`). Orphan + CS-license-expiring alerts defer to D7 (depend on D8). (§19.5 Phase 5, Decision #19) *~1 day, ~6-8 commits.*

**Audit + engagement (2 items)**

14. **Beacon command audit log** — every consoleCommand and task POST records `(operator, beacon_id, command, ts, taskId, result_summary)`. Write to `audit.log` + ship to CloudWatch. (§4.4) *2-3 days.*
15. **Terminal session recording** — `script(1)`-style wrapper or websocket tee. Default-on, opt-out per-session if needed. (§4.4) *1-2 days.*

**Vuln-lab + documentation + housekeeping (5 items)**

16. **Vuln-lab Phase 1** — `terraform/modules/vuln_lab_web` with Log4Shell as the first Vulhub scenario in a dedicated target subnet, ingress-locked to attack box + C2 only. (§16.5, §16.7) *1 week.*
17. **Regenerate stale diagrams** (goad-sccm, goad-nha, both combined-full). (§2.2) *2 hours.*
18. **Create missing diagrams** — operator-dashboard-tunnel, multi-operator-access-flow, audit-logging, ebs-dlm. (§2.3) *1 day.*
19. **`docs/TROUBLESHOOTING.md`** — Flask issues, terraform lock, VPC peering, instance bootstrap. (§3.4) *Half-day.*
20. **Untracked-files cleanup**: commit `.mcp.json`, gitignore `.c2lint_cache/` + `goad_workspace/` + `domain_categorization_results.csv`, delete the root-level `c2-adhoc-architecture.png` + `CS Client output log.rtf` + `generated-diagrams/local-mode-backup/`, move `Research/` (117 MB) to a private wiki/external repo. (§1.3) *30 minutes.*
21. **Re-tag `redteam-dashboard-server`** EIP/instance to `Project=redteam-dashboard` (currently inherits `goad_mini` tag — §1.4). *5 minutes via import-and-apply.*
22. **Clean up the 8 empty Terraform workspaces** under `terraform/terraform.tfstate.d/` after a quick tar backup. (§1.5) *15 minutes.*

### P3 — quarterly (depth, polish, cost)

**Dashboard refactor — polish (D6)**

23. **D6 — Bookmarkable URLs** for sub-pills (`#operations/beacons?dep=...`). Extends the already-existing `window.location.hash = pageName` line in `navigateTo()` to support `parent/subpill?query`. (§19.5 Phase 6, §20.8 item 4) *Half-day.*

**Observability + cost (2 items)**

24. **Enable VPC Flow Logs + GuardDuty** on dashboard + C2 VPCs. (§5.1)
25. **Auto-stop attack boxes off-hours** via EventBridge + Lambda (saves ~$96/mo per §7).

**Code health (3 items)**

26. **Refactor `deploy.py`** (5,423 LoC) into 4 smaller route files: `deploy_state.py`, `deploy_orchestration.py`, `file_mgmt.py`, `workspace.py`. (§10.3)
27. **Modularize `app.js`** (21K LoC) with ES6 imports + esbuild. Extract `BeaconController`, `TERMINAL`, `Topology` first. (§10.3)
28. **Add toast notifications** for async ops; pause-on-hidden + jitter for pollers. (§11.2, §11.3)

**Engagement reporting + vuln-lab + Terraform polish (4 items)**

### Interleaved + post-D6 V3 design propagation (Decisions #16, #17)

29a. **D3.8 — V3 polish on Deployments sub-views** — between D3.7 and D4 start. Configuration form / Deploy controls / Deployment Manager grid get V3 typography (13px base + 9.5px mono caps), spacing, palette tokens, focus states, 280ms cubic-bezier hover. Behavior unchanged. ~1-2 days, ~4-6 commits, branch `refactor/dashboard-d3-8-polish`.

29b. **D4.7 — V3 polish on Operations sub-views** — between D4.6 and D5 start. Same treatment for Beacon UI / Terminal / Tools. ~1-2 days, ~4-6 commits, branch `refactor/dashboard-d4-7-polish`.

29c. **D5.0 — Cost + Inventory backend prep** (Decision #18, prerequisite for D5) — between D4.7 and D5 start. Fix the Cost Project Selector bug at `webapp/frontend/js/app.js:19264` (currently hardcoded `'account'`, ignores dropdown). Add `GET /api/costs/aggregate` endpoint summing monthly burn across active deployments. Add `?region=` query param to Cost Explorer fetcher. Extend `/api/deploy/resources/all-projects` to also query us-east-1 for cross-region resources (CloudFront ACM certs). ~half-day, ~3-4 commits, branch `refactor/dashboard-d5-0-cost-inventory-backend`.

29d. **D8 — AWS Inventory & Cleanup** (Decision #18) — between D6 and D7. Settings → 3 new section cards (Domains & DNS, Secrets Manager, Infrastructure Services). Deployments tab → new 4th sub-pill "Cleanup" (consumes `/api/deploy/resources/all-projects` + us-east-1 query). Per-row actions: Adopt into Terraform / Destroy manually / Mark as known-external. ~1-2 days, ~6-8 commits, branch `refactor/dashboard-d8-aws-inventory`.

29e. **D7 — Internal V3 refresh** — after D8 (or D6 if skipping D8) lands. Final pass: Dashboard pre-D5 internals, Settings internal sections (now incl. the new D8 cards), Architecture tab, all modals, remaining buttons/forms/tables. Tag `v2.1.0` on merge. ~2-4 days, ~8-12 commits, branch `refactor/dashboard-d7-internal-v3`.

29. **Vuln-lab Phase 2/3** — more Vulhub scenarios (Phase 2) + Windows targets with PrintNightmare/SMBv1/weak-services (Phase 3). (§16.7)
30. **Ghostwriter / Sigma-compatible oplog export** for engagement reporting. (§4.4)
31. **Add `validation { condition = ... }`** to `var.deployment_type` so typos fail-fast instead of silently falling through to "none". (§14.2)
32. **Convert inline `aws_iam_role_policy` resources** in `terraform/modules/deployment_storage/main.tf` (6 instances) to attached managed policies. (§14.2)

---

### Cross-references summary (so you can find any item's deep design quickly)

| Topic | Roadmap items | Deep section(s) |
|---|---|---|
| CS May 2026 maintenance | P0 #2, #3 | §13 |
| `terraform validate` blocker | P0 #1 | §0, §14.1 |
| Multi-operator audit middleware | P1 #4, P2 #14, #15 | §4 |
| Beacon long-task polling | P1 #5 | §12.3 |
| Persona-B onboarding | P1 #6 | §3.2 |
| Concurrency safety (RLock) | P1 #7 | §8.2 |
| Dashboard refactor (D-phases) | P1 #8-10, P2 #11-13, P3 #23 | §19, §20 |
| Vuln-lab module | P2 #16, P3 #29 | §16 |
| Architecture diagrams | P2 #17, #18 | §2 |
| Troubleshooting doc | P2 #19 | §3 |
| Untracked-files cleanup | P2 #20 | §1.3 |
| Tag drift / workspace cruft | P2 #21, #22 | §1.4, §1.5 |
| Security observability | P3 #24 | §5.1 |
| Cost auto-stop | P3 #25 | §7 |
| Code refactors | P3 #26, #27, #28 | §10, §11 |
| Engagement reporting | P3 #30 | §4 |
| Terraform polish | P3 #31, #32 | §14 |
| Test framework + commit-sized D-phase split | new D0.x / D1.x... commits | §21 |

---

## 21. Test framework + commit-sized refactor splits

The user requested: small isolated dashboard changes + a test loop that verifies each change without deploying real infra. This section specifies (a) the test stack, (b) the per-change workflow, and (c) the smallest-commit-size split of every D-phase from §17.

### 21.1 Current testing state (verified)
- **Zero tests** in the repo (`find . -name "test_*.py" -o -name "*_test.py" -o -name "tests/" -type d` returns nothing).
- **No `package.json`**, no `pytest.ini`, no `pyproject.toml`, no `Makefile`.
- Backend deps live in `requirements.txt`: Flask, boto3, jinja2, requests.
- Frontend is vanilla JS — no module bundler, no test runner.
- Python venv exists at `venv/` running 3.13.

We're adding tests onto a clean slate. Good — no legacy test rot to fight.

### 21.2 Proposed four-layer test stack

```
                    Speed       Catches                              When to use
─────────────────────────────────────────────────────────────────────────────────
Layer 1: pytest    <1s/test    backend route logic,                 every PR touching
         + moto                service contracts,                   webapp/backend/
         + mocks               validators, config parsing

Layer 1.5:         <1s/test    BeaconService ↔ CS REST API          every PR touching
   CS OpenAPI                  contract: every request body         beacon_service.py
   contract                    validates against spec schema;       or beacon.py routes;
   (jsonschema                 every documented response shape      AND every time we
   + Prism                     is exercised. Catches Fortra spec    re-pull spec.js
   mock server)                drift (e.g. May 18 changes).         from Fortra

Layer 2: Vitest    <100ms/test pure JS logic: router,               every PR touching
         + jsdom               state, deployment-type cascade,      app.js or index.html
                               sub-pill switcher

Layer 3: Play-     1-5s/test   real browser, real DOM, full tab     every PR touching
         wright                navigation, conditional visibility,  the dashboard UX
         (head-                drag-drop, theme toggle, regression  + nightly smoke run
         less                  snapshots of "for deployment-type X,
         Chrome)               these IDs visible / these hidden"
```

**Total expected runtime for full suite once warm: ~45-90 seconds.** Layers 1 + 1.5 + 2 should run on every keystroke (watch mode). Layer 3 runs on demand + pre-commit.

### 21.3 No infra ever touched

Each layer mocks the boundary:

- **Layer 1:** `moto` decorates pytest functions, intercepts every `boto3` call → returns fake AWS responses. `subprocess.run` calls to `terraform` get patched with `unittest.mock` → return canned plan output strings.
- **Layer 1.5:** `docs/cobalt-strike-api/spec.js` is the contract. Two sub-modes (use both, they catch different things):
  - **Schema validation** — every request `BeaconService` would send is validated against the spec's `requestBody.content['application/json'].schema` for that endpoint via `jsonschema`. Catches field-name typos (`sleepTime` vs `sleep`), missing required fields, wrong types. Pure unit test, no network.
  - **Mock CS team server (Prism)** — `prism mock` runs the spec as a stand-in CS team server on localhost. pytest fixture spins it up, points `BeaconService` at it, exercises every documented endpoint. Catches request-shape and response-parsing bugs end-to-end. Still no real CS, no real beacons.
- **Layer 2:** jsdom is a JS-implementation of the DOM. No browser, no network. `fetch()` is stubbed.
- **Layer 3:** Playwright `page.route('**/api/**', mockHandler)` intercepts every backend call. Real DOM, real CSS, real JS — but the backend is a fixture.

**Zero AWS calls. Zero real-Terraform calls. Zero real-CS calls. Zero EC2 spinups.** The full suite runs offline on a laptop.

#### How Layer 1.5 catches Fortra spec drift

The CS REST API spec is version-pinned in our repo (`docs/cobalt-strike-api/spec.js` — `version: "1.0.0-BETA"` per the file header). The full lifecycle:

1. Fortra ships an API change (e.g. as part of the May 18 maintenance, or any future release).
2. We re-pull the latest spec from Fortra's docs and drop it into `docs/cobalt-strike-api/spec.js`.
3. CI/`make test` re-runs Layer 1.5 against the new spec.
4. Anywhere our `BeaconService` request body or response handler doesn't conform, **the test fails with exact field/endpoint pointers.**
5. We fix `beacon_service.py` to conform; tests go green; ship.

This is the contract-test pattern. **It replaces "manual smoke against the live team server"** for spec drift — you only need manual smoke for behavioural differences that Fortra didn't document.

A spec-conversion helper (T0.2 below) strips the `var spec = ` CommonJS wrapper to produce `spec.json` once on setup. Any future spec re-pulls do the same one-liner.

### 21.4 Initial setup (one-time, ~30 min)

Files to add:
```
pytest.ini                          # pytest config + path
tests/
├── conftest.py                     # shared fixtures (mock boto3, mock terraform, prism mock CS server)
├── backend/
│   ├── test_routes_deploy.py       # one file per route module
│   ├── test_routes_beacon.py
│   ├── test_services_terraform.py
│   └── ...
├── cs_contract/                    # Layer 1.5 — CS REST API contract tests
│   ├── conftest.py                 # spec loader fixture, prism mock fixture
│   ├── test_beacon_request_shapes.py   # every BeaconService.* outbound request validates against spec schema
│   ├── test_listener_request_shapes.py
│   ├── test_response_handlers.py   # every documented response shape is correctly parsed
│   └── test_endpoint_coverage.py   # which spec endpoints we've implemented vs not (Coverage Report)
├── js/
│   ├── vitest.config.js
│   ├── test_navigate.spec.js       # tests for APP.navigateTo + alias map
│   ├── test_deployment_type.spec.js# tests for updateDeploymentType cascade
│   └── ...
└── browser/
    ├── playwright.config.js
    ├── fixtures/
    │   ├── api_mocks.js            # mock GET /api/whoami, /api/config, etc.
    │   └── deployment_snapshots.js # "deployment-type=goad-mini → visible IDs"
    ├── test_tab_navigation.spec.js
    ├── test_conditional_sections.spec.js
    └── test_refactor_regression.spec.js  # the snapshot guard

docs/cobalt-strike-api/
├── spec.js                         # existing — Fortra's CommonJS-wrapped OpenAPI 3.1
└── spec.json                       # NEW — generated, gitignored: stripped JSON for tooling

scripts/
└── refresh-cs-spec.sh              # NEW — one-liner: strip `var spec = ` wrapper → spec.json

package.json                        # for vitest + playwright + @stoplight/prism-cli
Makefile                            # `make test` / `make test-watch` / `make test-browser` / `make refresh-cs-spec`
requirements-dev.txt                # pytest, pytest-mock, moto, jsonschema, ...
.github/workflows/test.yml          # optional CI later
```

Deps added:
- `requirements-dev.txt`: `pytest>=7`, `pytest-mock>=3`, `moto>=4`, `jsonschema>=4`, `freezegun` (time mocking)
- `package.json`: `vitest`, `jsdom`, `@playwright/test`, `@stoplight/prism-cli`

### 21.5 The snapshot-guard pattern — the heart of the refactor safety net

Before D3 (Deployments merge) is touched, we run **one script** that captures the current behavior as a JSON snapshot:

```
tests/browser/fixtures/deployment_snapshots.js
[
  {
    deploymentType: "c2-adhoc",
    visibleSectionIds:   ["domain-config-section", "ssl-config-section", "domain-fronting-section",
                          "decoy-theme-section", "malleable-profile-section", "file-portal-section",
                          "attack-box-config-section", "deployment-overview"],
    hiddenSectionIds:    ["goad-network-config-section"],
    enabledInputs:       ["c2-server-count", "c2-instance-type", "key-pair-name"],
    disabledInputs:      []
  },
  {
    deploymentType: "goad-mini",
    visibleSectionIds:   ["malleable-profile-section", "attack-box-config-section",
                          "goad-network-config-section", "deployment-overview"],
    hiddenSectionIds:    ["domain-config-section", "ssl-config-section", "domain-fronting-section",
                          "decoy-theme-section", "file-portal-section"],
    enabledInputs:       [],
    disabledInputs:      ["c2-server-count", "c2-instance-type", "key-pair-name"]
  },
  // ... one entry per 11 deployment types
]
```

The capture script picks each deployment-type from the dropdown, waits for `updateDeploymentType()` to settle, and records which IDs are visible/hidden/enabled/disabled.

Then `test_refactor_regression.spec.js` does:
```js
for (const snap of snapshots) {
  await selectDeploymentType(snap.deploymentType);
  for (const id of snap.visibleSectionIds) {
    expect(await page.locator(`#${id}`)).toBeVisible();
  }
  for (const id of snap.hiddenSectionIds) {
    expect(await page.locator(`#${id}`)).toBeHidden();
  }
  // ... same for inputs
}
```

**After every refactor commit, this snapshot must still pass.** That's how we know D3 (Configuration merge) didn't accidentally break the 10-section conditional cascade documented in §20.2.

Cross-link snapshots work the same way:
```
[
  { trigger: "click APP.navigateTo('configuration')", expectedParentTab: "deployments", expectedSubPill: "configure" },
  { trigger: "click 'Edit Config' button",            expectedParentTab: "deployments", expectedSubPill: "configure" },
  // ... one per cross-link from §20.3
]
```

### 21.6 Per-change workflow

```
1. Pick the next D-commit (see §21.7 splits below)
2. Look at what it changes — one of:
     (a) routing / state           → write Layer 2 test (vitest)
     (b) DOM re-parenting          → run Layer 3 snapshot guard, must stay green
     (c) backend behavior          → write Layer 1 test (pytest)
3. Write the test FIRST (or in the same commit)
4. Make the smallest change that turns it green
5. `make test` → all green
6. Commit
7. Push (or merge to a feature branch)
```

For non-trivial visual changes: also take a Playwright screenshot of the affected tab(s) and visually diff against the previous commit. Tooling: `playwright test --update-snapshots` to bless intentional visual changes, otherwise pixel-diff fails the test.

### 21.7 Commit-sized splits for every D-phase

Each commit below is ≤ ~50 LoC of net change, ships a single concept, and is independently testable.

#### D0 — Routing alias layer (P1 item #8, 1-2 hours)
| # | Commit | Test to add | Verifies |
|---|---|---|---|
| D0.1 | Add `NAVIGATE_ALIASES = { 'configuration': ['deployments','configure'], 'deployment': ['deployments','deploy'], ... }` map to top of `app.js`. No behavior change. | vitest unit test of the map shape | All 7 old tab names map to a valid (parent, subPill) tuple |
| D0.2 | Extend `APP.navigateTo(name)` to accept either a flat name (existing) or look up the alias and route to `parent` (sub-pill is ignored until D3). | vitest: `navigateTo('configuration')` calls `navigateTo('deployments')` internally | Backwards compat preserved |
| D0.3 | Extend `sessionStorage.setItem('currentPage', pageName)` to store `{parent, subPill}` JSON; extend URL hash to `#parent/subPill` (subPill optional). | vitest: after `navigateTo('configuration')`, `sessionStorage.currentPage === '{"parent":"deployments","subPill":"configure"}'` | State persists for next page load |

#### D1 — Global header (P1 item #9, half-day)
| # | Commit | Test |
|---|---|---|
| D1.1 | Add header DOM scaffold above tab nav in `index.html` (empty containers for selector + cost indicator). | Playwright: header exists, has correct IDs |
| D1.2 | Implement `window.APP.activeDeployment` state object with `.set()` / `.subscribe()`. Initial value = first deployment from `/api/deployments`. | vitest: subscribers are called when set; supports multiple subscribers |
| D1.3 | Wire global selector to `APP.activeDeployment.set`. Existing per-tab selectors stay (deleted in D4). | Playwright: changing header selector also updates Beacon/Tools/Terminal dropdowns (they should subscribe) |
| D1.4 | Add cost indicator that reads `/api/cost/summary` and renders `$XXX/mo`; click goes to Settings → cost section. | Playwright: click on cost indicator navigates to settings tab, scrolls to cost section |

#### D2 — Pre Reqs → Settings (P1 item #10, half-day)
| # | Commit | Test |
|---|---|---|
| D2.1 | Move the `tab-page[data-page="aws-check"]` subtree into Settings as a new section card "AWS & SSH Prerequisites" placed ABOVE Cost Tracker. Keep all IDs (`system-deps-status`, `aws-credentials-status`, etc.). | Playwright: navigate to Settings, find all 5 check buttons + status divs; clicking each still triggers the right handler |
| D2.2 | Remove the Pre Reqs nav button from `index.html:14`. Remove the `tab-page[data-page="aws-check"]` empty wrapper. Add alias `'aws-check' → ['settings', 'aws-prereqs']` to the D0 alias map. | Playwright: navigating to `#aws-check` (legacy URL) lands on Settings with the AWS Prereqs section visible (anchor scroll) |
| D2.3 | Add yellow first-run banner on Dashboard if any prereq has never passed (read from a new `/api/prereqs/status` cache endpoint). | pytest: `/api/prereqs/status` returns the cached state; Playwright: dashboard shows banner when state is missing |

#### D3 — Deployments merge (P2 item #11, 1-2 days)
| # | Commit | Test |
|---|---|---|
| D3.0 | **Pre-flight: capture deployment-type snapshot** (§21.5). Add `tests/browser/fixtures/deployment_snapshots.json` + regression test that consumes it. **Must be green against unchanged code FIRST.** | Playwright: regression test passes against current `main` |
| D3.1 | Add new `tab-page[data-page="deployments-tab"]` empty wrapper to `index.html` with pill-switcher scaffold for `configure | deploy | manage`. Add new nav button. **Do NOT remove old tabs yet.** | Playwright: new tab exists, pill buttons render |
| D3.2 | Re-parent the entire `tab-page[data-page="configuration"]` subtree under the new wrapper's `configure` pill. Update `loadPageContent` switch so navigating to `deployments-tab` with sub-pill `configure` runs `loadConfig()`. | Playwright: regression snapshot still passes; pill switcher to `configure` shows the form |
| D3.3 | Re-parent the entire `tab-page[data-page="deployment"]` subtree under `deploy` pill. Run the 7 init functions (`resetDeployValidation`, `loadConfigSummary`, etc.) on pill activation. | Playwright: regression still green; the "Edit Config" button now flips pill to `configure` instead of changing tab |
| D3.4 | Re-parent the entire `tab-page[data-page="deployments"]` subtree under `manage` pill. Wire `loadDeploymentsPage` + `startAutoRefresh` to pill activation; wire cleanup (`stopAutoRefresh`, `_destroyPollInterval`) to pill deactivation. | Playwright: switching pill from `manage` to `configure` cancels auto-refresh (no leak) |
| D3.5 | Add sub-view lifecycle hooks: on pill change, run prev-pill cleanup then next-pill init (§20.6). | vitest: subview-lifecycle.spec.js — pill change triggers cleanup + init in correct order |
| D3.6 | Remove the three old nav buttons (Configuration, Deploy, Deployment Manager). Add aliases `'configuration' → ['deployments-tab','configure']`, etc. to D0 alias map. | Playwright: legacy `APP.navigateTo('configuration')` still works (lands on the right pill) |
| D3.7 | **Final smoke:** all snapshots green, manual click-through of 11 deployment types in the new Configure pill. | snapshot regression + Playwright tab-navigation tests all green |

#### D4 — Operations merge (P2 item #12, 1-2 days)
| # | Commit | Test |
|---|---|---|
| D4.1 | Add `tab-page[data-page="operations-tab"]` wrapper with pill switcher for `beacons | terminal | payloads`. Don't remove old tabs yet. | Playwright: new tab + pills render |
| D4.2 | Re-parent `tab-page[data-page="beacon"]` under `beacons` pill. Wire BEACON.init / stopHealthPoll to pill activate/deactivate. | Playwright: beacon empty states still render, polling stops on pill change |
| D4.3 | Re-parent `tab-page[data-page="terminal"]` under `terminal` pill. Wire TERMINAL.init / stopBackgroundRefresh. | Playwright: terminal tab shows correctly |
| D4.4 | Re-parent `tab-page[data-page="tools"]` under `payloads` pill (rename label "Payload upload"). Wire `loadToolsPage`. | Playwright: drag-drop UI still works |
| D4.5 | **Delete** `beacon-deployment-select`, `terminal-deployment-select`, `tools-project-select` from their respective tabs. Wire `BEACON.onDeploymentSelected`, `TERMINAL.onDeploymentSelected`, `loadToolsConnectionInfo` to subscribe to `APP.activeDeployment` changes. | vitest: changing `APP.activeDeployment` triggers all three handlers; Playwright: per-tab dropdowns are gone, but switching deployment in the header header still re-loads each sub-view |
| D4.6 | Remove old nav buttons (Beacon, Terminal, Tools). Add aliases to D0 map. | Playwright: `APP.navigateTo('beacon')` still works |

#### D5 — Dashboard upgrade (P2 item #13, half-day, depends on item 4 audit)
| # | Commit | Test |
|---|---|---|
| D5.1 | Add live deployments grid widget reading from `/api/deployments`. | Playwright: grid renders one card per deployment with status |
| D5.2 | Add recent activity feed reading from `/api/audit/recent` (requires audit middleware from P1 item #4). | pytest: `/api/audit/recent` returns last 20 events; Playwright: feed renders |
| D5.3 | Add cost trend tile reading `/api/cost/trend?days=14`. | Playwright: sparkline renders |
| D5.4 | Add "Create new deployment" CTA → `APP.navigateTo('deployments-tab', 'configure')`. | Playwright: click lands on Configure pill |

#### D6 — Bookmarkable URLs (P3 item #23, half-day)
| # | Commit | Test |
|---|---|---|
| D6.1 | Parse URL hash on page load: `#parent/subPill?dep=name` → `navigateTo(parent, subPill)` + `APP.activeDeployment.set(dep)`. | Playwright: opening `/#operations-tab/beacons?dep=c2_adhoc_dev_harriss_macbook_pro_01` lands on Beacons pill with that deployment active |
| D6.2 | Push URL state on every pill change + active-deployment change (via `history.pushState`). | Playwright: navigating updates URL; browser-back returns to previous state |

### 21.8 Total: 26 commits for the whole dashboard refactor

D0: 3 commits • D1: 4 • D2: 3 • D3: 8 (incl. D3.0 snapshot capture) • D4: 6 • D5: 4 • D6: 2 = **30 small commits.**

Each is independently shippable. Each has at least one test that proves it didn't break anything. If you stop after D3.7 you have 7 tabs and the dominant flow merged. If you stop after D4.6 you have the final 5-tab layout.

### 21.9 What this test framework does NOT cover (be honest)

- **Real AWS behavior** — moto fakes are good but not perfect; some IAM edge cases differ.
- **Real Terraform behavior** — we mock `subprocess.run`, so we never run an actual `terraform plan`. That's the right tradeoff for this work — D-phases don't touch Terraform — but the framework itself can't catch a Terraform regression.
- **Undocumented Cobalt Strike behavior** — Layer 1.5 catches every drift that's reflected in the OpenAPI spec. It does NOT catch behaviour Fortra changes silently without updating the spec (e.g. response timing changes, race conditions inside the CS server, beacon-side bugs). For those, manual smoke against the live team server is still useful — but it's a rare class of issue compared to spec drift.
- **CSS visual regression in light vs dark mode at the same time** — Playwright can do dual-theme screenshot diffing, but it doubles test time. Recommend doing it for D5 dashboard widget commits only, not every D-commit.
- **Multi-operator concurrency** — testing two simultaneous SSH-tunneled operators against the same Flask is hard to mock realistically. Out of scope; relies on the manual MEMORY.md notes + the per-project RLock work (P1 item #7) instead.

### 21.10 Effort breakdown to stand up the framework (P1 prerequisite)

| Commit | Effort | Purpose |
|---|---|---|
| T0.1 | 15 min | Add `requirements-dev.txt` + `package.json` + `Makefile` + `pytest.ini` + `vitest.config.js` + `playwright.config.js`. |
| T0.2 | 20 min | Add `scripts/refresh-cs-spec.sh` (one-liner: strip `var spec = ` wrapper from `docs/cobalt-strike-api/spec.js` → `spec.json`). Gitignore `spec.json`. Add `make refresh-cs-spec` target. |
| T0.3 | 30 min | `tests/conftest.py` with shared fixtures: `mock_aws` (moto), `mock_terraform_subprocess`, `flask_test_client`. |
| T0.4 | 45 min | `tests/cs_contract/conftest.py` with two fixtures: (a) `cs_spec` loads `spec.json` and yields the parsed dict; (b) `prism_mock_cs` spins up `prism mock spec.json` on a random localhost port, yields the URL, tears it down. |
| T0.5 | 30 min | Write the first pytest (e.g., `test_routes_health.py` — `GET /api/health` returns 200). Proves Layer 1 works. |
| T0.6 | 45 min | Write the first CS contract test (`test_beacon_request_shapes.py` — `BeaconService.sleep(1, 0)` produces a body that validates against the spec's `SleepRequest` schema; `BeaconService.spawnto(...)` validates against `SpawntoRequest`; etc.). Proves Layer 1.5 works. |
| T0.7 | 30 min | Write the first vitest (e.g., `test_navigate.spec.js` — `APP.navigateTo('dashboard')` updates `currentPage`). Proves Layer 2 works. |
| T0.8 | 1 hour | Write Playwright config + first browser test (`test_smoke.spec.js` — page loads, every tab nav button exists). Proves Layer 3 works. |
| T0.9 | 1 hour | Write D3.0 snapshot capture script + the regression test that consumes it. Verify green against current `main`. |

**Total: ~5 hours to stand up the framework before any D-commit lands.** Slot this as a new **P1 item #7.5** in §17, before D0 starts.

### 21.11 New P1 item to add to the roadmap

> **7.5 Stand up test framework** — pytest + moto (Layer 1), CS OpenAPI contract tests via jsonschema + Prism mock server (Layer 1.5), Vitest + jsdom (Layer 2), Playwright + Chromium (Layer 3). Snapshot-capture the current `updateDeploymentType()` cascade behavior as the refactor regression guard. Includes `scripts/refresh-cs-spec.sh` so future Fortra spec drops produce a clean test failure list instead of silent breakage. *5 hours.*

This is the prerequisite for D0–D6 having any safety net. Without it, the refactor proceeds blind.

### 21.12 Layer 1.5 also helps with §13 (CS May 18 maintenance)

When Fortra publishes the post-mortem on Mon 2026-05-18 (or shortly after):

1. Pull the new spec file from `docs.cobaltstrike.com` (or wherever they publish it).
2. Drop it into `docs/cobalt-strike-api/spec.js`.
3. `make refresh-cs-spec && make test`.
4. **Every drift surfaces as a named test failure** with the exact endpoint + field that changed.
5. We patch `beacon_service.py` accordingly; tests go green; we know we're safe to rebuild a team server.

This is exactly the "fix-forward plan documented" piece referenced in P0 item #3 of §17 — Layer 1.5 IS the fix-forward plan.

---

## 22. Decisions log

Choices the user has made that pin down implementation details. Anyone reading this plan should treat these as fixed.

| # | Decision | Date | Implication |
|---|---|---|---|
| 1 | Hardcoded `csrestapi:password` is OK (intentional, internal-only) | 2026-05-16 | Per-operator beacon attribution comes from dashboard audit layer, not CS creds. Saved as memory `feedback_csrestapi_hardcoded_creds_ok.md`. |
| 2 | Test framework built first (5h, 9 commits T0.1–T0.9) before any dashboard merge | 2026-05-16 | P1 #7.5 ships before D0. No D-commits without test infrastructure. |
| 3 | Test files live in `tests/` at repo root | 2026-05-16 | Structure: `tests/backend/`, `tests/cs_contract/`, `tests/js/`, `tests/browser/`. Standard pytest discovery. |
| 4 | Feature branch per phase + PR review | 2026-05-16 | Branches: `refactor/test-framework`, `refactor/dashboard-d0-alias`, `refactor/dashboard-d1-header`, `refactor/dashboard-d2-prereqs`, `refactor/dashboard-d3-deployments`, `refactor/dashboard-d4-operations`, `refactor/dashboard-d5-overview`, `refactor/dashboard-d6-urls`. Each merged via PR. |
| 5 | Verification cadence: tests on every commit + my own eyeball at phase boundaries | 2026-05-16 | I won't ask for visual confirmation per commit. At each phase end I'll surface a screenshot + a summary; user reviews before PR merge. |
| 6 | Transient UI during D3 / D4: feature flag (`?legacyTabs=1`) hides the in-progress UI by default | 2026-05-16 | New tabs/layout default-on from D3.1. Old buttons accessible via `?legacyTabs=1` for A/B comparison. Both flag check and old buttons deleted at D3.6 / D4.6. |
| 7 | Full SemVer + footer + CHANGELOG + git tags + release script | 2026-05-16 | New P1 item #7.6 in §17. See §24.1 for full spec. **Superseded by Decision #11 below** (version numbering reframed). |
| 8 | Operations tab = Beacons + Terminal + Payloads sub-pills + **mandatory lifecycle hooks in same commit as each re-parent** | 2026-05-16 | Beacon and Terminal don't need to be used at the same time per user clarification — sub-pills work. But §20.6 hooks are non-optional v1 work. If user later prefers Beacon as its own top-level tab, that's a 5-min flag change. See §26.9 Blocker A. |
| 9 | Multi-engagement: global active-deployment selector in header + **per-sub-pill override** (each Operations sub-pill keeps its own selector that can override global) | 2026-05-16 | Operator running 2 engagements concurrently (c2_adhoc + goad_mini) can have Beacons on one and Terminal on the other. Some UI clutter, full flexibility. Reverses part of §20.4 (do NOT delete the three per-tab selectors entirely — they become overrides). See §26.9 Blocker C. |
| 10 | Version numbering: **current state = `v1.0.0`** (first numbered release of existing stable codebase) → test framework = `v1.1.0` → versioning system itself = `v1.1.1` (or part of v1.1.0) → audit middleware = `v1.2.0` → dashboard refactor complete = `v2.0.0` (breaking UI) | 2026-05-16 | Honest about what's in production today. SemVer from a real baseline. Operators see meaningful versions. Supersedes the older `v0.1.0` framing in Decision #7. See §26.6. |
| 11 | EC2 cutover flow: **rsync from laptop** (existing as-built mechanism) — `setup-dashboard.sh` sync path → `dashboard-manage.sh upgrade` (pip install + systemctl restart). Switch to git-pull is deferred to a P3 item. | 2026-05-16 | Matches what works today. `dashboard-manage.sh upgrade` does NOT do git pull — plan §25 was incorrect, see §26.5. Operator runs upgrade **as themselves** (not `sudo -u dashboard`). Pre-cutover EBS snapshot of dashboard volume becomes a checklist item. |
| 12 | Install taste-skill (full suite, 13 variants) to `~/.claude/skills/taste-suite/` | 2026-05-18 | Manual install via `git clone` + `cp`, user-wide (not project-scoped) so available across all Claude sessions. Per user choice (full suite vs single skill). Adds `design-taste-frontend`, `brutalist-skill`, `minimalist-skill`, `redesign-skill`, etc. as available skills. |
| 13 | Dial settings for taste-skill on this project: `DESIGN_VARIANCE=6, MOTION_INTENSITY=3, VISUAL_DENSITY=6` | 2026-05-18 | More creative than the dashboard-conservative defaults (4/2/7). Moderate variance, low motion (still an ops dashboard — beacon callbacks need attention, not animations), medium density. Overrides taste-skill's own baseline of 8/6/4. **Must be communicated at every invocation** along with the vanilla-HTML + palette.css constraint (skill defaults to React + Tailwind). |
| 14 | A/B comparison via **T1 design pilot** inserted between P1 #7.6 (versioning) and D0 (routing). Build D1 header twice (baseline + taste-skill) on a throwaway preview route, user picks the winner once, decision propagates to D1/D3/D4 pill switchers/D5 widgets. | 2026-05-18 | ~3-4h pilot phase, throwaway artifacts deleted at D1 end. Branch: `refactor/design-pilot`. Lets user compare real pixels rather than skill descriptions before committing to a design language across the whole refactor. |
| 15 | **V3 locked with motion +2 bump** (dials 5/6/5). After comparing baseline + V1 (6/3/6) + V2 (8/2/7) + V3 original (5/4/5) + V4 (10/10/7), user selected V3 with motion bumped from 4 to 6. Design language: "alive without being theatrical — quiet hum across the dashboard rather than a parade of effects." Distinct from V4 by: no magnetic chips, no scribble/diagonal accents, no particle drift, no continuous brand-mark rotation. | 2026-05-18 | V3 design propagates to D1 header (final), D3 pill switchers, D4 pill switchers, D5 dashboard widgets. The other variants + the preview routes get deleted at the end of D1. New design tokens established: 280ms cubic-bezier transitions for hover, spring overshoot allowed for micro-feedback only, one gentle continuous shimmer per major element (brand mark, cost number, sparkline, dial spec card), `prefers-reduced-motion` strips all loops. See §28.4 + §28.2 D1/D3/D4/D5 rows for taste-skill invocation rules. |
| 16 | **Interleave V3 polish into sub-views.** Add two new phases to the plan: **D3.8 — V3 polish on Deployments sub-views** (Configuration form / Deploy controls / Deployment Manager grid) between D3.7 and D4 start; **D4.7 — V3 polish on Operations sub-views** (Beacon UI / Terminal / Tools) between D4.6 and D5 start. Without these, the sub-views would still look like the legacy dashboard after the merge — only the chrome (header + pill switchers) would carry V3. | 2026-05-18 | Adds ~1-2 days per polish phase. Scope: form input styling, button hierarchy, table/grid treatment, section-card rhythm, V3 typography (13px base + 9.5px mono caps captions), palette tokens everywhere (no raw hex), focus-visible states, hover transitions at 280ms cubic-bezier. ui-quality-check skill mandatory. Does NOT redesign control behavior — purely cosmetic. Updates §28.2 table: D3.8 and D4.7 are full `frontend-design` + `ui-quality-check`. |
| 17 | **D7 — Internal V3 refresh (post-D6).** After the structural refactor completes at D6 (tag `v2.0.0`), one more phase walks through everything D3.8/D4.7 didn't touch and applies V3 design tokens consistently across the whole app. Scope: Dashboard tab pre-D5 internals (anything D5 didn't replace), Settings tab internal sections (Cost Tracker / Roadmap / AWS Prereqs styling polish), Architecture tab, all modals (`session-logs-modal`, `archived-logs-modal`, `screenshot-overlay`, beacon panels), any remaining buttons/forms/tables that still look like the legacy dashboard. | 2026-05-18 | New phase added between D6 and the cutover. Estimate: 2-4 days, ~8-12 commits, branch `refactor/dashboard-d7-internal-v3`. Tag `v2.1.0` on merge. Goal: complete visual consistency end-to-end — no surface still looking like the old dashboard. Does NOT change behavior, only styling. All UI commits run `ui-quality-check`. Re-uses `frontend-design` + taste-skill where new visual constructs are needed (e.g. unified empty states, consistent loading skeletons). |
| 18 | **AWS inventory + cleanup gaps surfaced** (post-D3 review): The global deployment picker handles per-deployment resources well, but shared/orphan/cross-region resources (domains, CS license secret, GitHub tokens, dashboard server, orphan EIPs/snapshots/buckets, us-east-1 CloudFront ACM certs) had no UI surfacing. Two new phases added: **D5.0 — Cost + Inventory backend prep** (~half-day, prerequisite for D5) and **D8 — AWS Inventory & Cleanup** (~1-2 days, slots between D6 and D7). | 2026-05-18 | D5.0 scope: fix cost selector bug at app.js:19264 (was hardcoded to project='account', ignoring dropdown); add `GET /api/costs/aggregate` endpoint summing monthly burn across all active deployments; add optional `?region=` filter to Cost Explorer queries; extend `/api/deploy/resources/all-projects` to also query us-east-1 for CloudFront ACM certs. D8 scope: Settings → new "Domains & DNS" section card (lists Route 53 zones + expiry warnings + per-zone deployment usage); Settings → new "Secrets Manager" section card (CS license + GitHub tokens, status + last rotation); Settings → new "Infrastructure Services" section card (dashboard server status + cost); Deployments tab → new 4th sub-pill "Cleanup" (lists orphan resources from /api/deploy/resources/all-projects + us-east-1, with Adopt/Destroy/Mark-known-external actions). D5 cost tile defaults to aggregate "all deployments" with drill-down to per-deployment. Total scope addition: ~2-2.5 days. |
| 19 | **D5 expanded into an action-dense launchpad** (per user request). The minimum spec (live grid + activity feed + cost trend + CTA) was too sparse — operators need more visible quick-actions on the landing page. Expanded D5 widgets: **(1)** Primary "+ New Deployment" CTA (top-of-page, hero treatment), **(2)** "Resume last deployment" affordance (when `localStorage.activeDeployment` is set), **(3)** AWS prereqs nudge (when checks have never passed), **(4)** Live deployments grid — 3 clickable cards, each opens Manage sub-pill for that project, **(5)** Active beacons widget — count + last-seen indicator, clicks to Operations → Beacons, **(6)** Recent activity feed (placeholder until P1 #4 audit middleware ships), **(7)** Cost trend tile with sparkline + % change + click → Settings → Cost Tracker, **(8)** Budget alert callout (when `/api/costs/budget-alert` returns warn/danger), **(9)** Failed deployments alert (any in error state), **(10)** Existing Elastic Detection Rules card retained. | 2026-05-18 | D5 estimate goes from half-day → ~1 day (one extra half-day for the additional widgets). All listed widgets except (3) and (6) work with TODAY's backend (no D8 dependencies). Orphan-resources alert and CS-license-expiring alert defer to D7 (depend on D8 shipping the necessary backend surfacing). Decision #19 supersedes the bare 4-widget D5 in §19.4 Phase 5. |
| 20 | **M-phase bundling restructure** — instead of dripping V3 polish across structural-then-polish phases, bundle each tab into ONE page-complete branch + PR + minor version bump. Sequence: M-Operations (replaces D4.1-D4.7, ~9-12 commits, tag `v1.2.0`) → M-Dashboard (replaces D5.0+D5, tag `v1.3.0`) → D6 URLs (kept standalone, tag `v2.0.0`) → M-Settings (replaces D8 + Settings parts of D7, tag `v2.1.0`) → M-Modals + Cleanup (replaces Modal/Cleanup parts of D7, tag `v2.2.0`). Each M-phase ships a fully polished page in one merge. | 2026-05-18 | Reduces 9 remaining phases → 6 milestones. Larger PRs but operator sees "complete tab" per merge. Per-M-phase versioning (Decision #20 sub-choice) makes CHANGELOG read as "v1.2.0 = Operations merged + polished; v1.3.0 = Dashboard launchpad live" instead of dozens of mini-phases. |
| 21 | **Architecture tab folded into Dashboard widget + modal** (per user UX call). Architecture is reference content — operators visit once per engagement then ignore it. Top-nav real estate is the wrong placement. Becomes a contextual widget on the M-Dashboard launchpad showing the diagram for the currently-active deployment, with a "Browse all" modal that contains the existing deployment selector + diagram + markdown docs. Legacy `APP.navigateTo('architecture')` aliases redirect to the modal. | 2026-05-18 | **Nav drops to 4 final tabs** (Dashboard / Deployments / Operations / Settings) — was going to be 5 with Architecture. Folded into M-Dashboard scope: +1 widget (Architecture, total 12 widgets) + 1 modal + delete Architecture tab + update alias map. Architecture content moves out of `<div data-page="architecture">` into a modal mounted on Dashboard. Estimate addition to M-Dashboard: ~half-day. M-Architecture milestone REMOVED from the schedule (its content lives inside M-Dashboard now). |
| 22 | **Wider V3 redesign promoted to v2.0.0** (per user request: "do the redesign right after the dashboard"). Reorder remaining milestones — **M-Redesign** ships **immediately after M-Dashboard** as the big visual-completeness cutover (`v2.0.0`), before D6 URLs and other small items. Scope expands beyond pure CSS polish into actual **page-structure** improvements (Settings reorganization, modal sizing/positioning standardization, unified empty states, loading states, error states, consistent typography end-to-end) — "like the V3 taste demo + more fluidity." | 2026-05-18 | New ordering: M-Operations ✅ → M-Dashboard (in flight, `v1.3.0`) → **M-Redesign (new big phase, `v2.0.0`)** → D6 URLs (`v2.1.0`) → M-Settings absorbed into M-Redesign → M-Modals absorbed into M-Redesign → Cleanup sub-pill = trailing micro-phase (`v2.2.0`). M-Redesign estimate: 3-5 days, ~15-20 commits. Touches every surface that's not already V3 (Settings interior, all modals, Architecture modal interior, Cost Tracker, Roadmap section, any remaining legacy buttons/forms/tables). Adds "fluidity" via consistent micro-motion (page transitions, sub-pill animations, list item enter/leave choreography). |

Open decisions still pending (deferred, will revisit when relevant):
- **Pre-commit hook** (auto-run tests on `git commit`) — defer until after T0 framework is up; revisit then.
- **CI / GitHub Actions** — defer to P2; framework runs locally first.
- **node_modules location** — default to repo root (gitignored), revisit if it becomes annoying.
- **Snapshot update flow** — `make test-update-snapshots` (manual blessing); will codify when T0.9 is written.
- **Terminal session recording tool** — defer to P2 item #15.
- **Layer 2 (Vitest) scope** — likely scoped to mock-infra-only or skipped entirely; will pin when T0.7 is approached.
- **Beacon as its own top-level tab vs Operations sub-pill** — proceeding with sub-pill per Decision #8; trivially reversible if user requests later.

---

## 23. Dev workflow — how to see changes live + how testing surfaces results

The user asked: *"how can I view the changes you make to the dashboard for example?"* and *"how will the testing work?"* Concrete walkthrough below.

### 23.1 The "see changes live" loop (no AWS, no SSH tunnel needed)

The dashboard is just Flask serving static HTML/JS. It runs on your laptop the same way it runs on the EC2 dashboard server — only difference is access (loopback vs SSH tunnel).

**One-time setup** (will be wrapped into `make dev` in T0.1):
```bash
cd /Users/harriskhalid/Desktop/Red_Team_Infra_Local
source venv/bin/activate
# (already done — Flask 3.1.3 is installed)
```

**Daily workflow:**

Terminal window (I run this in the background while working):
```bash
make dev
# expands to:
# FLASK_APP=webapp.backend.app python -m flask run --debug --port 5000 --host 127.0.0.1
```

`--debug` means **Flask auto-restarts whenever a Python file changes.** You never restart it manually.

Browser (you keep this open the whole session):
```
http://127.0.0.1:5000
```
DevTools (Cmd+Opt+I) → Network tab → tick **"Disable cache"**. Stays disabled as long as DevTools is open.

**The loop:**
1. I edit `webapp/backend/...` or `webapp/frontend/...` and save.
2. If Python: Flask auto-reloads (you don't notice).
3. You **Cmd+R** in the browser → see the change.
4. We talk about it; I iterate.

The loopback guard at `app.py:35-39` is what blocks anything that isn't 127.0.0.1 — it lets your local browser through fine.

### 23.2 During the dashboard refactor specifically — the feature flag

Per decision #6 (§22), from D3.1 onwards the in-progress merged UI is **the default**. The legacy tabs are still in the DOM but hidden by default; visible only at:
```
http://127.0.0.1:5000/?legacyTabs=1
```

So while I'm working on D3 you'll see:
- Default URL → the new "Deployments" tab in progress (whatever's been re-parented so far)
- `?legacyTabs=1` → the old Configuration / Deploy / Deployment Manager buttons, fully functional, for direct comparison

You can have two browser tabs open and Cmd+Tab between them to A/B as I work. At D3.6 the flag and old buttons are deleted.

### 23.3 How testing surfaces results (your view)

You don't have to run tests yourself. I'll run them and surface results in chat. But here's what's happening under the hood so you understand:

**Layer 1 (pytest)** — terminal output:
```
$ make test-backend
tests/backend/test_routes_health.py::test_health_returns_200 PASSED
tests/backend/test_routes_deploy.py::test_deploy_requires_config PASSED
tests/cs_contract/test_beacon_request_shapes.py::test_sleep_request_schema PASSED
...
======= 47 passed in 1.83s =======
```

If something fails, the failure message includes the file, line, expected vs actual.

**Layer 1.5 (CS contract)** — runs as part of Layer 1; same output format. Failures look like:
```
FAILED tests/cs_contract/test_beacon_request_shapes.py::test_sleep_request_schema
  jsonschema.exceptions.ValidationError:
    'sleepTime' is not one of the allowed properties on SleepRequest;
    expected one of: ['sleep', 'jitter']
```
That tells me exactly which field is wrong.

**Layer 2 (Vitest)** — terminal output, watch mode auto-runs on file save:
```
✓ tests/js/test_navigate.spec.js (3)
  ✓ APP.navigateTo('dashboard') updates currentPage
  ✓ APP.navigateTo unknown name logs error
  ✓ alias map resolves legacy names to (parent, subPill)
```

**Layer 3 (Playwright)** — two modes you can choose between:
- **Headless** (default, fast): no browser window, just terminal output. Fast for CI / batch runs.
- **Headed** (`make test-browser-headed`): a Chromium window pops up on your screen and you **watch the tests click around the dashboard in real time**. This is great for confidence — you literally see "the test selected goad-mini, then verified file-portal-section is hidden, then verified goad-network-config-section is visible." Use it any time you want to feel sure the snapshot guard is actually exercising what it claims.

Failed Playwright tests automatically save a **screenshot of the failing state** to `test-results/<test-name>/test-failed-1.png` — useful to share with you in chat when a regression shows up.

### 23.4 What you'll see at each phase boundary

After each D-phase completes (per decision #5):
1. I post a short status comment with: commits landed, tests passing, screenshots of the affected tab(s), and any caveats.
2. You Cmd+R in your browser and look (or you've been looking the whole time — either works).
3. You approve → I open a PR (per decision #4) → you merge → next phase starts.

So your active involvement is roughly **one review per phase**, not per commit. Phases are ~half-day to 2 days each, so call it ~7 reviews over the whole refactor.

### 23.5 What I'll commit to the chat each turn

When I'm actively coding I'll keep updates terse:
- Started: which commit (e.g., "T0.1 — adding requirements-dev.txt + Makefile")
- Finished: tests passing? what specifically did this commit change? anything user-visible?
- Blocked: if I hit something I need a decision on

You won't see a wall of code unless you ask for it. Files are written; the diff is in the file, not in chat.

---

## 24. Versioning strategy (proposed — needs your call)

The user asked: *"does the plan include a proper versioning system too?"*

Today the repo has **no versioning at all** — no git tags, no `VERSION` file, no `__version__` in `app.py`, no displayed version in the UI. Commit messages follow conventional-commit style (`feat:`, `fix:`, `refactor:`) but that's the extent. The `dashboard-manage.sh upgrade` flow does `git pull` and restarts the systemd unit, which means **operators have no way to know which version of the dashboard is running on the EC2 server** — they just know "whatever was latest on main when upgrade was last run."

For a multi-operator dashboard this is a real gap. When operator B says "the file portal page is broken," operator A needs to know which version they're both looking at.

### 24.1 Proposed scheme (a recommendation — your call to confirm)

**Semantic versioning (SemVer): `MAJOR.MINOR.PATCH`**
- **MAJOR** — bumped on breaking changes to the operator workflow (e.g., tab structure changing — the dashboard refactor itself = v2.0.0).
- **MINOR** — new features (vuln-lab module, beacon audit log, new deployment type).
- **PATCH** — bug fixes, docs, dependency bumps, no behaviour change.

**Where it lives:**
1. **`VERSION` file at repo root** — single source of truth, plain text, one line: `1.0.0`.
2. **`webapp/backend/app.py`** reads `VERSION` at startup and exposes via `GET /api/version`.
3. **`/api/version` returns** `{"version": "1.0.0", "git_sha": "8b377ac", "built_at": "2026-05-16T14:30:00Z"}`.
4. **Dashboard UI footer** displays `v1.0.0 (8b377ac)` always-visible in the bottom-right. Click → modal with full info + release notes link.
5. **Git tags on `main`** — `v1.0.0`, `v1.1.0`, etc. at each released milestone. Tag = source of truth for "what was actually shipped."
6. **`CHANGELOG.md` at repo root** — Keep a Changelog format. Operator-readable summary per version.
7. **`scripts/server/dashboard-manage.sh upgrade`** — after `git pull`, checks new version against running version; if MAJOR bump, shows release notes diff before proceeding; logs the upgrade event to `audit.log` (operator + from-version + to-version + timestamp).
8. **Release process** — bumping `VERSION` + adding `CHANGELOG.md` entry + tagging commit + opening a release PR is a single `scripts/utilities/release.sh patch|minor|major` invocation (added in P1 alongside the test framework, or P2 if it slips).

**Versioning the test framework itself:** The test framework lands as `v0.1.0` (since the project has never been versioned — first numbered release). Each D-phase merge bumps MINOR. The whole dashboard refactor completion = `v1.0.0`. The current pre-versioning state would be reconstructable as "the commit just before T0.1."

**Versioning the CS OpenAPI spec:** The spec file itself carries Fortra's version (`"version": "1.0.0-BETA"` today). On every spec re-pull we record `(fortra_spec_version, pulled_at)` in a small `docs/cobalt-strike-api/SPEC_HISTORY.md` so we can correlate "after we pulled spec X.Y.Z, beacon test N started failing" with a git commit.

---

## 25. What happens to the live EC2 dashboard during this work

The user asked: *"during this upgrade, what happens to the current dashboard that is living in aws right now?"* **Short answer: nothing. It stays running, untouched, for the entire refactor.** Long answer below.

### 25.1 Two completely separate environments

| | Local dev (your laptop) | Production (EC2) |
|---|---|---|
| Where | `127.0.0.1:5000` via `make dev` | `redteam-dashboard-server` (10.100.1.89 / EIP 3.75.17.232) |
| Access | Direct browser open | SSH tunnel: `ssh -L 5000:localhost:5000 <user>@3.75.17.232` |
| Code | This git checkout under `~/Desktop/Red_Team_Infra_Local/` | `/opt/redteam/` on the EC2 instance |
| Service | `flask --debug` foreground | `systemctl status dashboard` (systemd unit, per `setup-dashboard.sh:456-479`) |
| Operators connected today | Just you (us, while testing) | Whoever has SSH tunnels open right now |
| Affected by my edits | Yes, immediately on save | **No.** Stays at whatever version was last `git pull`-ed into `/opt/redteam/`. |

There is **no automatic sync** between them. The EC2 dashboard runs whatever code was last manually pulled via `scripts/server/dashboard-manage.sh upgrade`. Every edit I make goes to the laptop checkout only.

### 25.2 What this means for the refactor

- **For the full ~5h test framework + ~30 commit dashboard refactor** (T0.1 → D6.2): zero EC2 impact. Production dashboard keeps serving whoever is on it. Operators using the existing dashboard via SSH tunnel see the existing UI unchanged.
- **No AWS deploys.** The dashboard refactor is HTML/JS/Python only. No `terraform apply` runs at any point. The live `c2_adhoc...teamserver`, redirectors, bastion, attack box, dashboard server EC2, and S3 buckets are all untouched.
- **No new infra spinups.** I won't create EC2 instances, EIPs, Route53 records, or anything billable while refactoring. Cost stays flat at ~$407/mo.

### 25.3 The eventual cutover (only when YOU say so)

After the refactor is done, tested, and merged to `main`, you (not me) decide when to deploy it to the EC2 dashboard. The process:

```bash
ssh <user>@3.75.17.232
cd /opt/redteam
sudo -u dashboard /opt/redteam/scripts/server/dashboard-manage.sh upgrade
```

That script:
1. `git pull` on the EC2 (pulls the new merged code)
2. `pip install -r requirements.txt` (catches any new deps)
3. `systemctl restart dashboard` (cycles the Flask process)

**Downtime: ~10-30 seconds.** Any operator tunnelled in during that window sees a "connection refused" for that interval, then refresh → new UI is live.

**Existing operator SSH tunnels stay open** during the restart — they just need to refresh the browser tab.

### 25.4 Impact on the live `c2_adhoc...teamserver` and beacons during cutover

Zero. Beacons callback to redirectors → forward to the team server's REST API. The dashboard is a **client** of that REST API, not a relay. Beacons keep checking in, queuing tasks, and storing results in the CS team server's own database while the dashboard is restarting. When dashboard comes back up, it polls the REST API and picks up everything that happened in the gap.

### 25.5 Rollback plan (if a deployed version turns out broken)

Versioning (§24) makes this clean:
```bash
ssh <user>@3.75.17.232
cd /opt/redteam
sudo -u dashboard git checkout v1.0.0   # or whatever was the previous tag
sudo -u dashboard pip install -r requirements.txt
sudo systemctl restart dashboard
```

Same ~30s downtime, same beacon-impact (zero).

### 25.6 What I will NOT do during this refactor (commitments)

- ❌ I will not push any code to the EC2 instance.
- ❌ I will not run `dashboard-manage.sh upgrade` on the EC2.
- ❌ I will not run `terraform apply`, `terraform destroy`, or any AWS CLI write operation.
- ❌ I will not modify any file under `/opt/redteam/` on the EC2 (no SSM commands, no SSH).
- ❌ I will not touch the active `c2_adhoc_dev_harriss_macbook_pro_01` workspace's state file.

Everything happens in this laptop checkout. AWS reads (e.g. `aws ec2 describe-instances` for verification) only.

### 25.7 If you want to test locally with the SAME backend data as production

Optional: the local Flask reads `terraform.tfvars` and `logs/deployment_state/*.state.json` from the checkout. If you want your local dashboard to display the same active deployments as production (handy for verifying the refactor doesn't break the deployment list rendering), copy them down:

```bash
scp <user>@3.75.17.232:/opt/redteam/configs/terraform.tfvars configs/terraform.tfvars.from-ec2
scp -r <user>@3.75.17.232:/opt/redteam/logs/deployment_state logs/deployment_state.from-ec2
# read-only — don't write back
```

Or skip this and just verify against synthetic test data (which is what the test framework will use anyway).

### 25.8 Summary

> **Throughout the entire refactor (test framework + 30 D-commits + however many days that takes), the EC2 dashboard at `3.75.17.232` keeps running its current version, unaffected, serving whichever operators are connected. The live red team infra (`c2_adhoc...`, `goad_mini...`, all 10 EC2 instances) is untouched. No AWS writes. No downtime. The only time anything changes on EC2 is when YOU run `dashboard-manage.sh upgrade` after merging the refactor — and that's a ~30s controlled cutover with a known rollback path.**

> ⚠️ **Important corrections from §26 review:** The upgrade flow as described above does NOT match the actual `dashboard-manage.sh` script (which uses rsync from operator laptop, NOT git pull on the EC2). The cutover plan must be updated before any production change. See §26.5 for the actual mechanism and required fixes.

---

## 26. Pre-implementation review findings

Before starting T0.1, I ran a 6-agent parallel review of (1) the plan's internal consistency, (2) every code claim vs the actual codebase, (3) test framework feasibility against the actual app.js / spec.js, (4) refactor hidden coupling and lifecycle leaks, (5) the versioning + cutover process against the actual dashboard-manage.sh, and (6) an independent skeptic looking for what will go wrong. This section consolidates findings that change the plan.

### 26.1 Code-vs-plan verification: 24/25 claims confirmed

Every concrete file:line claim in the plan was spot-checked against the live codebase. All confirmed except one minor stat:
- The `git diff --stat` for `terraform/main.tf` shows the headline number differently than the +68 lines claimed in §1.2 (the +68 is the size of the DLM block itself; the stat reflects net repository change). Not wrong, just framed differently.

Notable confirmations:
- `webapp/backend/services/beacon_service.py:23-24`: `username = "csrestapi"` / `password = "password"` ✅
- `webapp/backend/app.py:35-39`: `enforce_loopback()` guard ✅
- `webapp/backend/routes/deploy.py:264`: `entry['initiated_by'] = get_operator()` ✅
- `webapp/backend/routes/`: **287 Flask routes** total registered (matches plan's "287+") ✅
- `webapp/frontend/index.html`: 10 tabs, line numbers all match §20.1 ✅
- `app.js:7517`: `updateDeploymentType()` defined here ✅
- `app.js:189`: `APP.navigateTo()` ✅, cleanup at lines 198-222 ✅
- `terraform/main.tf:927, 943, 949`: `local.deploy_c2` typo confirmed (definition is `deploy_c2_infra` at line 81) ✅
- `terraform/scripts/install_cobalt_strike.sh:268`: `./update` piped with license key ✅
- `webapp/frontend/js/app.js`: **21,187 lines** ✅
- `webapp/frontend/index.html`: **2,419 lines** ✅
- `terraform/terraform.tfstate.d/c2_adhoc_dev_harriss_macbook_pro_01/terraform.tfstate`: serial 148, 86 resources, TF 1.5.7 ✅
- `Research/`: 117 MB ✅

Conclusion: **the plan's factual base is solid.** The fixes below are about plan logic and missing scope, not bad facts.

### 26.2 Test framework — 5h estimate is wrong; 8-10h is realistic

Estimate adjustments from feasibility audit:

| Item | Plan | Revised | Why |
|---|---|---|---|
| T0.1 config files | 15 min | 20 min | Prism 3.1.0 compat verification needed in `package.json` |
| T0.2 spec strip | 20 min | 30 min | Must test the strip produces valid JSON + spot-check schemas |
| T0.3 conftest.py | 30 min | 45 min | `mock_terraform_subprocess` is fiddly (canned output parsing) |
| T0.4 CS contract fixtures | 45 min | **1.5h** | Prism setup + lifecycle + port mgmt + 3.1.0 features verification |
| T0.5 first pytest | 30 min | 30 min | `/api/health` is simple |
| T0.6 first CS contract test | 45 min | **1h** | Spec schema path navigation, Prism response handling |
| T0.7 first vitest | 30 min | **defer or 1h** | See §26.3 below — Vitest on app.js is mostly useless |
| T0.8 Playwright setup | 1h | **1.5h** | WebSocket handling needs Flask fixture thread, not just route mocking |
| T0.9 snapshot capture | 1h | **2h** | DEPLOYMENT_CONFIGS has **27 entries not 11** — snapshot is bigger |

**Revised total: ~7.5-9 hours, call it 8-10h end-to-end with pre-flight setup time.**

Also missing from the estimate: Playwright Chromium download is **~500 MB** (~10-15 min on first install). Add to pre-flight (§26.7).

### 26.3 Vitest on monolithic app.js is mostly useless — defer Layer 2

`webapp/frontend/js/app.js` is 21,187 lines, has **no ES module exports**, uses globals (`APP`, `BEACON`, `TERMINAL`, `DEPLOYMENT_CONFIGS`), and attaches event listeners at `DOMContentLoaded` (line 21172).

Vitest can technically load it into jsdom and call `window.updateDeploymentType()`, but:
- You can't test functions in isolation — must load the entire 21K-line file
- Must fabricate a full DOM with all expected element IDs
- Tests will be slow and fragile (closer to integration tests than unit tests)

**Decision needed:** Skip T0.7 entirely (Vitest tests deferred until app.js is modularized in P3 #27), OR keep T0.7 but scope it to test only the mock infrastructure itself (fetch interception, localStorage shims), not app.js logic. Both options eliminate Vitest as a layer that catches app.js bugs.

**Net effect:** Layer 2 collapses. Tests that would have been Vitest move to Layer 3 (Playwright) where the full DOM + CSS + async behavior is already exercised. This is actually fine — Playwright is the right tool for testing a non-modular vanilla JS app — but the plan's "4 layers" becomes effectively 3.

### 26.4 Critical hidden coupling the snapshot guard cannot catch

The risk audit surfaced 6 classes of bug the §21.5 snapshot guard will NOT detect:

1. **Modal/overlay orphans** — 3 modals (`session-logs-modal`, `archived-logs-modal`, `screenshot-overlay` at `app.js:4972`, `15710`, `16024`) are appended to `document.body`, not to their owning tab subtree. When sub-pill changes, the modal stays visible above a hidden sub-view. **Fix needed in D3/D4:** sub-view leave hook closes attached modals.

2. **Polling timer leaks** — `BEACON.pollInterval` (3s), `_taskFeedTimer` (3s), `_activityLogTimer` (5s), and `deploymentPollInterval` are cleared on **tab leave** today (app.js:198-222). After the merge, switching from Beacons → Terminal within Operations tab does NOT trigger tab-leave, so these timers leak. **The sub-view lifecycle hooks (§20.6) MUST ship in the same commit as each sub-view re-parent, not afterward.** This is non-optional.

3. **Inline `onclick` handlers in HTML** — 6 of 7 empty-state CTAs use `onclick="APP.navigateTo('configuration')"` directly in HTML, not via `addEventListener`. The alias map intercepts `APP.navigateTo()` calls, but ONLY if the handler still goes through `APP.navigateTo()`. Confirmed: all 6 use `APP.navigateTo(...)` so the alias map covers them — **good news, the plan's approach works**. But verify each one specifically in the test snapshot.

4. **`sessionStorage.setItem('currentPage', pageName)` (app.js:256) stores a string today.** Post-D0 it must store JSON `{parent, subPill}`. **Backwards-compat issue:** existing operator browsers have stale strings from before the refactor. First load after D0 ships, `JSON.parse()` on a plain string fails. **D0 must include a try/catch + fallback** ("if parse fails, navigate to default tab and overwrite storage"). Not currently in plan.

5. **Async update-after-detach bugs** — `BEACON.selectBeacon()` (app.js:3421) fires `refreshBeaconDetail()` as an unawaited Promise. If the sub-view is hidden mid-flight, the async response tries to update DOM that's no longer visible. Race condition, intermittent. **The snapshot guard takes one screenshot per state and won't see this** — it's a sequence-of-events bug. Mitigation: `waitForIdleAndSnapshot()` helper that drains pending fetches + timers before snapshotting.

6. **Feature flag `?legacyTabs=1` is NOT trivial** — implementation surface is ~60 LoC across HTML/JS/CSS:
   - Nav-rendering branch (~20 LoC)
   - CSS hide rules (~10 LoC)
   - `APP.navigateTo()` legacy-mode branch (~30 LoC)
   - Session-persistence question (does the flag survive reload?) — undecided
   Plan called this "simple"; it's a half-day on its own.

### 26.5 §25 EC2 cutover plan is WRONG — fix before any production change

The cutover review found that `scripts/server/dashboard-manage.sh upgrade` does NOT match what §25 describes:

| What §25.3 claims | What `dashboard-manage.sh upgrade` actually does |
|---|---|
| `git pull` on EC2 | **No git pull.** Asks operator to manually rsync from laptop first. |
| `pip install` then `systemctl restart` | Sources venv, pip install, then **`sudo systemctl restart dashboard`** |
| Runs as `sudo -u dashboard` | Service user has `/usr/sbin/nologin`; **the sudo call inside will fail** because service users can't elevate |

The actual sync mechanism is **rsync from laptop → EC2**, configured in `scripts/server/setup-dashboard.sh:85-118`. Not git-pull. The `.git/` does exist on the EC2 (initialized at `setup-dashboard.sh:158`), but no part of the operational flow uses it for code sync.

**Three fixes needed:**

1. **Reconcile the sync story.** Either:
   - (a) **Keep rsync.** Update §25 wording to say "after merge, rsync the updated code from laptop to EC2 via the existing `setup-dashboard.sh sync` path, then restart." This is the as-built reality.
   - (b) **Switch to git pull.** Modify `dashboard-manage.sh upgrade` to actually do `git pull` (the `.git/` is there). Better long-term, but is a script change that itself needs to ship + be tested before the dashboard refactor cutover.

2. **Fix the `sudo -u dashboard` claim.** Operators run the upgrade as themselves (their own SSH-logged-in user, which has sudo). Not as the `dashboard` service user.

3. **Add a pre-cutover EBS snapshot step.** §25 currently has no backup before cutover. Manually snapshot the dashboard EBS volume (`aws ec2 create-snapshot --volume-id <vol> --description "dashboard-pre-vX.Y.Z"`) before pulling new code. Gives a fast rollback path if anything catastrophic happens.

### 26.6 Versioning bootstrap — files don't exist yet

- **No `VERSION` file** at repo root.
- **No `CHANGELOG.md`.**
- **No `scripts/utilities/release.sh`.**
- **`webapp/backend/app.py:90`** has a hardcoded `'version': '1.0.0'` in the `/api/` endpoint — not a separate `/api/version`, not read from a file.

P1 #7.6 needs to create all four. None exist. Estimate stays ~2h (the items are small, just lots of small) but it's net-new work, not editing existing files.

**First-version-number ambiguity (Decision #7 says `v0.1.0`):**
- Current state of repo = months of production work. Calling it `v0.1.0` implies pre-release/beta and confuses operators ("Why am I on v0.1.0 in production?").
- Cleaner alternative: **Current state = `v1.0.0`** (first numbered release of the existing stable codebase). Test framework + versioning system = `v1.1.0`. Dashboard refactor completion = `v2.0.0` (breaking UI change). This is more honest about what's actually in production today.
- Or: `v0.1.0` = the bootstrap commit (test framework only), `v0.2.0` = post-D2, `v1.0.0` = dashboard refactor complete. Treats current state as pre-numbered, future state as semver from scratch.
- **Question still open** — see end of this section for decision request.

### 26.7 Pre-flight checks BEFORE T0.1 (mandatory)

The skeptic agent identified that the plan assumes a working environment that may not exist. Run these BEFORE starting the 5-9h test framework timer:

```bash
# 1. Fix the Terraform blocker (P0 #1) so we can verify deployments are safe
#    Replace `local.deploy_c2` → `local.deploy_c2_infra` at main.tf:927, 943, 949
cd terraform && terraform validate

# 2. Confirm Python venv + deps installed and Flask app boots
source venv/bin/activate
python3 -c "import flask, boto3, requests; print('OK')"
FLASK_APP=webapp.backend.app python3 -m flask run --help

# 3. Node baseline (Playwright needs 18+)
node --version    # already v24.7.0 per earlier check ✓
npm --version

# 4. Playwright Chromium pre-download (~500 MB, 10-15 min)
# After T0.1 writes package.json:
npx playwright install chromium

# 5. Flask actually serves
python3 webapp/backend/app.py &
curl -sf http://127.0.0.1:5000/api/ | jq .
kill %1

# 6. Snapshot-guard input verification
grep -c 'id="[a-z-]*-section"' webapp/frontend/index.html   # should be ~20
grep -c "': {" webapp/frontend/js/app.js | head -5         # count DEPLOYMENT_CONFIGS entries

# 7. Git workspace clean OR intentionally dirty
git status
# If dirty: stash the in-flight DLM/attack_box work OR confirm we work on top of it

# 8. GitHub auth + push permission
gh auth status
git remote -v
```

If any of these fail, **STOP** and fix before T0.1.

### 26.8 Plan inconsistencies to clean up

From the internal-consistency review:

1. **P0 #3 (CS May 18 response) depends on P1 #7.5 (test framework), but P1 hasn't shipped.** Today is 2026-05-16; framework needs 8-10h to build, and Monday is 2026-05-18. If Fortra drops the post-mortem Monday, "make test against new spec" won't exist. **Honest plan: P0 #3 falls back to manual install/test of `install_cobalt_strike.sh` if it triggers before the framework ships.** Update P0 #3 wording.

2. **§17 P1 #7.5 / #7.6 numbering is awkward** (decimal sub-items vs sequential). Cosmetic; defer.

3. **D3.0 snapshot must pass green against unchanged code FIRST** — this is a gate not currently flagged in §17. If the snapshot test itself doesn't work on `main`, the refactor stalls at commit 1. Explicit gate added to D3 description.

4. **D5 dependency on P1 #4 (audit middleware) — placeholder strategy undefined.** If audit ships late, D5 ships with empty activity feed OR moves to P3. Pin the answer.

5. **Cross-reference table** (end of §17) is accurate; no fixes needed there.

### 26.9 Workflow validation surfaces 3 v1 blockers

The operator-workflow validation agent flagged 3 concerns the current plan treats as "v2 polish" or undecided but which actually block v1 usability:

**Blocker A: Sub-view lifecycle hooks are mandatory for v1, not v2.** Without them, switching from Beacons → Terminal within the Operations tab leaks the beacon health-poll and the operator misses callbacks while in Terminal. The plan says "sub-pill lifecycle hooks" (§20.6) but treats them as a single commit at end of D3/D4. **They must be wired in the same commit as each sub-view re-parent**, not bolted on after.

**Blocker B: Sub-pills are insufficient for concurrent Beacon+Terminal+Tools work.** In real engagements, operators watch beacon callbacks while typing SSH commands in Terminal in parallel. Sub-pills hide one when showing the other. Options:
- (a) Ship sub-pills for v1 with explicit lifecycle hooks (acceptable but slightly degraded UX)
- (b) Keep Beacon and Terminal as separate top-level tabs for v1 (6 tabs not 5)
- (c) Build the split-pane layout immediately for Operations (adds ~1 day to D4 but matches actual workflows)

**Blocker C: Global active-deployment selector breaks multi-engagement workflows.** If operator is running `c2_adhoc` AND `goad_mini` engagements concurrently, the single global selector forces them to pick one. The plan deletes the three per-tab selectors. Options:
- (a) Keep the global selector AND keep the per-sub-pill selectors as overrides (some clutter, full flexibility)
- (b) Use only the global selector (simpler UI, breaks multi-engagement)
- (c) Make each Operations sub-pill remember its own active deployment (Beacons on c2_adhoc, Terminal on goad_mini simultaneously)

All three blockers need a decision before D4 starts (or arguably before D0 starts, since D0's alias layer might need to handle deployment context).

Additional v1 polish recommendations:
- **"Edit Config" button in Deploy sub-pill MUST NOT be a pill-flip** — implement as inline collapsible panel so form state + scroll position are preserved.
- **First-time operator landing on Dashboard needs a wizard-like "Create your first deployment" CTA**, not a generic button.
- **Sub-pill ARIA/keyboard accessibility** — add `aria-selected`, `tabindex=0` on active pill, keyboard nav.

### 26.10 Things the plan doesn't mention at all

From the skeptic agent:
- **Browser compatibility** — Playwright tests only Chrome. Operators may use Safari/Firefox. Add at least a manual smoke for one non-Chromium browser before any cutover.
- **Narrow viewport / iPad** — global header + sub-pills must reflow gracefully on iPad widths.
- **Accessibility regression risk** — adding sub-pill nesting deepens keyboard nav, risks focus traps.
- **`make test-fast` vs `make test-full`** — full Playwright run is slow; devs will skip it. Split targets so the inner loop is fast.
- **PR review overhead for solo operator** — 30 commits across 8 PRs means high context-switching cost. Could collapse small PRs (D0, D1, D2 = one PR; D3 = one PR; D4 = one PR; etc.) to reduce overhead.

### 26.11 Decisions still needed (raised back to user)

Per §22 (decisions log), the following are now needed before T0.1 starts. **Top 3 are blocking.**

| # | Decision | Default if no answer | Blocking? |
|---|---|---|---|
| 8 | Layer 2 Vitest strategy: skip entirely vs scope to mock infra | scope to mock infra (1h, defer real JS tests) | not blocking but should be settled |
| 9 | Operations sub-pills: ship with lifecycle hooks (a) vs keep 6 tabs (b) vs split-pane immediately (c) | (a) with mandatory hooks per D-commit | **BLOCKING for D3/D4** |
| 10 | Multi-engagement: global selector + per-sub-pill override (a) vs global only (b) vs per-sub-pill memory (c) | (a) — operators can override per-sub-pill | **BLOCKING for D4** |
| 11 | First version number: current = v1.0.0 then refactor = v2.0.0 (a) vs framework = v0.1.0 (b) | (a) — honest about what's in production | **BLOCKING for P1 #7.6** |
| 12 | dashboard-manage.sh upgrade: rsync-based (a) vs switch to git pull (b) | (a) — match as-built reality, defer git refactor | **BLOCKING for cutover, not for refactor** |
| 13 | Test framework time budget: keep 5h scope by cutting Vitest (a) vs accept 8-10h for full stack (b) | (b) — already chose "test framework first" | should confirm |

---

## 27. Failure-mode planning & recovery paths

For every commit/phase in the plan, what's most likely to fail, what it looks like, and how to recover without losing momentum. Ordered by execution sequence.

### 27.1 Pre-flight checks (before T0.1)

| # | Failure | Symptom | Recovery | Time |
|---|---|---|---|---|
| 1 | `terraform validate` fails (the `deploy_c2` typo) | `Error: Reference to undeclared local value` at main.tf:927 | Fix the typo: `local.deploy_c2` → `local.deploy_c2_infra` at lines 927, 943, 949. Re-run validate. **This is P0 #1; do it as part of pre-flight, not during it.** | 5 min |
| 2 | Python venv missing or broken | `python3 -m flask` → `ModuleNotFoundError: No module named 'flask'` | `python3 -m venv venv --clear && source venv/bin/activate && pip install -r requirements.txt` | 5 min |
| 3 | Flask doesn't start cleanly (missing env var, import error) | App crashes on `python3 webapp/backend/app.py` | Run with `PYTHONPATH=. python3 webapp/backend/app.py` to fix import path; add to `make dev` target | 5 min |
| 4 | Node version too old (< 18) | `npx playwright --version` → fails | `brew install node@22` (or upgrade via your version manager) | 5-10 min |
| 5 | Playwright Chromium download fails (network, corporate proxy) | `npx playwright install chromium` hangs or 403s | Manually download from `https://playwright.azureedge.net/builds/chromium/...` to `~/.cache/ms-playwright/`. Set `PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright` | 15-30 min |
| 6 | `pip install` of dev deps fails (wheel build issues for `moto`, `jsonschema`) | Compile error | Pin specific versions: `moto==4.2.0`, `jsonschema==4.20.0`. Or install pre-built wheels via `pip install --only-binary :all:` | 10-20 min |
| 7 | Existing dirty working tree (12 modified files per §1.2) collides with new branch | `git checkout -b refactor/test-framework` works, but in-flight DLM/attack-box work tags along | **Choose:** commit the in-flight work to its own branch first (`refactor/in-flight-work`), then start fresh. OR stash it and continue. **Don't lose the +240 lines of attack_box_init.ps1 work.** | 15 min |

### 27.2 T0 — Test framework (8-10h, 9-10 commits)

| Commit | Failure | Symptom | Recovery |
|---|---|---|---|
| **T0.2 (spec strip)** | `var spec = ` wrapper isn't stripped cleanly | `spec.json` is invalid JSON | Manual inspection: open `spec.js`, find the closing `};` and any trailing JS. Adjust the sed regex. If Fortra changes the wrapper format later, this script breaks — that's a known coupling. |
| **T0.4 (Prism mock)** | **CRITICAL: Prism doesn't fully support OpenAPI 3.1.0** | `prism mock spec.json` errors on `type: ["string", "null"]` unions or `oneOf` with discriminators | **Three fallbacks:** (1) write a small Flask-based mock that loads spec.json and validates requests with jsonschema (loses Prism's smart response generation but works); (2) downgrade spec to 3.0 using `openapi-spec-converter` (lossy but workable); (3) skip Prism entirely, do schema-only validation in Layer 1.5. Pick (1) if blocked. **+1-2h.** |
| **T0.4** | Prism port collision with Flask (both want 5000) | `EADDRINUSE` | Pin Prism to random ephemeral port in fixture (`get_random_port()`), pass URL to BeaconService via env var |
| **T0.5 (first pytest)** | `enforce_loopback()` rejects pytest test_client requests | Test returns 403 | test_client uses `remote_addr=127.0.0.1` by default. If not, set `app.config['TESTING'] = True` and disable the guard in test mode (1-line check) |
| **T0.5** | Flask blueprint registration triggers actual subprocess/AWS calls on import | First `import app` takes 10s or errors | Audit `webapp/backend/routes/*.py` for module-level side effects (likely none, but verify). If found, lazy-load |
| **T0.6 (first CS contract test)** | BeaconService request body fails schema validation against spec | `jsonschema.ValidationError: 'sleepTime' is not in spec` | This is the test working as intended — find the field-name typo in beacon_service.py and fix. If the spec itself is wrong, file a Fortra issue and skip the test with `@pytest.mark.xfail(reason="spec issue", strict=False)` |
| **T0.7 (Vitest)** | jsdom can't load app.js without errors | `ReferenceError: window is not defined` or syntax errors | **Decision #8 already plans for this** — scope Layer 2 to mock-infra only OR skip entirely. The 21K-line app.js is fundamentally not unit-testable in jsdom without major refactoring. Move tests to Layer 3 (Playwright) |
| **T0.8 (Playwright)** | WebSocket mocking doesn't work for Terminal tab tests | Test hangs waiting for WebSocket | Two paths: (a) start a real Flask backend in a pytest fixture thread, point Playwright at it; (b) skip Terminal-specific tests in Layer 3, exercise them via Layer 1 (Flask test_client) instead |
| **T0.9 (snapshot capture)** | `updateDeploymentType()` is non-deterministic (async state) | Snapshot for c2-adhoc differs run-to-run | Find the async path. Likely a `setTimeout` or `fetch().then()` that updates DOM after the synchronous render. Add `await page.waitForLoadState('networkidle')` + 200ms settle delay before snapshot |
| **T0.9** | 27 DEPLOYMENT_CONFIGS snapshot file is unwieldy | `deployment_snapshots.json` is 1000+ lines | Split into 27 small files, one per deployment type. Easier to diff in PRs |

**T0 fail-loud rule:** if T0.4 (Prism) is fundamentally broken on 3.1.0, **stop and decide before proceeding**. Don't write more tests on top of a broken contract layer. Worst-case fallback: ship Layer 1 + Layer 3 only, defer Layer 1.5 to a P2 item. Plan still works, just less spec coverage.

### 27.3 P1 #7.6 — Versioning (2-3h, 2 commits)

| Failure | Symptom | Recovery |
|---|---|---|
| `release.sh patch` fails partway (e.g. tag exists but commit didn't push) | Repo in half-baked state | Script must be idempotent: re-run = no-op if version already bumped + tagged. If not, manual `git tag -d <ver>` + retry |
| `/api/version` endpoint conflicts with existing route | `app.py` registration fails | Search for existing `/api/version` (confirmed unused in §26.6); shouldn't happen but if so, use `/api/v1/version` |
| VERSION file read fails at Flask startup (permissions, missing) | App crashes on boot | Wrap read in try/except, fall back to `"unknown"` and log warning. Never let version read kill the app |
| CHANGELOG.md auto-generation from git log produces noisy output | Initial CHANGELOG is 200+ unhelpful lines | Hand-edit: keep only feat/fix/breaking, drop chore/style/refactor. Or skip auto-gen and write 5-line initial entry by hand |

### 27.4 D0 — Routing alias layer (2-3h, 3-4 commits)

| Failure | Symptom | Recovery |
|---|---|---|
| Existing operator browsers have stale string `sessionStorage.currentPage = 'configuration'` | After D0 ships, `JSON.parse('configuration')` throws on first load → blank page | **Planned in §26.4 item 4** — D0 includes try/catch: `try { state = JSON.parse(saved) } catch { state = {parent: saved} }`. Verify this path with a manual test |
| Alias map misses a cross-link call site | `APP.navigateTo('configuration')` lands on undefined tab → blank screen | Add a `default` clause in alias map that logs warning + falls back to `dashboard`. Audit all 14 cross-links from §20.3 |
| URL hash and sessionStorage disagree on first load | User lands on the wrong tab after refresh | Define precedence: URL hash wins > sessionStorage > default. Document in code |

### 27.5 D1 — Global header (half-day, 4 commits)

| Failure | Symptom | Recovery |
|---|---|---|
| Header pushes nav off-screen on narrow viewports | Tab buttons hidden behind header on iPad/small windows | CSS media query: `@media (max-width: 1024px) { .global-header { flex-wrap: wrap; } }` |
| `active-deployment` state object leaks subscribers | Memory grows over time as sub-views init/teardown | Use explicit `subscribe()` / `unsubscribe()` returning a disposer function; lifecycle hooks call disposer on sub-view leave |
| `/api/costs/summary` slow or rate-limited (Cost Explorer hard limits per account) | Cost indicator shows spinner forever | Cache cost data for 5 min in service worker / memory. Debounce: only refresh on explicit user action, not every deployment-selector change |
| Selector renders blank on first load if `/api/deployments` errors | Header looks broken | Fall back to empty selector with "(no deployments)" placeholder. Don't block header render on API success |

### 27.6 D2 — Pre Reqs → Settings (half-day, 3 commits)

| Failure | Symptom | Recovery |
|---|---|---|
| CSS selectors keyed to `.tab-page[data-page="aws-check"]` stop matching after move | Pre Reqs section unstyled inside Settings | `grep -n 'aws-check' webapp/frontend/css/style.css` — likely zero matches (per §20.8) but verify. If found, rename selectors |
| `checkAWSPermissions()` etc. handlers break because they assume specific DOM ancestry | Clicking "Check AWS Credentials" does nothing | Handlers use `getElementById` so ancestry doesn't matter. Verify with Playwright smoke test |
| First-run banner fires when prereqs are already passing | Annoying yellow banner on every load | Cache pass/fail state in localStorage with a 24h TTL. Banner only shows if state is missing OR last-fail timestamp < 24h |

### 27.7 D3 — Deployments merge (2-3 days, 8-9 commits)

| Failure | Symptom | Recovery |
|---|---|---|
| **D3.0 snapshot fails to capture cleanly against unmodified main** | Snapshot test is red on first run, before any refactor | This is the gate — the entire D3 stalls. Debug the capture script: add explicit waits, log what was visible/hidden, run in headed mode to watch. **Budget 1h to fix this if it hits.** If unfixable, drop snapshot guard and rely on manual click-through (much riskier) |
| Re-parenting Configuration subtree breaks event listeners attached at parent | `updateDeploymentType()` stops firing on dropdown change | `onchange` is inline HTML attribute (verified line 68); survives re-parenting. If JS-attached listeners exist elsewhere, audit with `grep "addEventListener"` for matches inside the moved subtree |
| Duplicate IDs after re-parenting (e.g., two `#deployment-overview` if both old and new tabs exist transiently) | DOM ambiguity, `getElementById` returns wrong element | **Feature flag (Decision #6) is what prevents this** — old tab is hidden by default, only shows with `?legacyTabs=1`. CSS `display:none` is enough to make `getElementById` return the visible one... wait, no, `getElementById` returns the FIRST one regardless of visibility. **Fix:** add `data-legacy="true"` to old tab subtree, scope all post-D3 `getElementById` calls to `document.querySelector('[data-page="deployments-tab"] #foo')`. **Or:** physically remove old tabs immediately and use the flag only for fallback navigation. Choose now |
| Sub-pill lifecycle hook calls cleanup for the wrong sub-pill | Active pill's polling stops mid-use | Test order: cleanup-prev → init-new, never both at once. Verify with manual click-spam test |
| "Edit Config" inline collapsible breaks scroll position on collapse | Operator loses where they were on the page | Save scroll position on collapse, restore on next expand |
| Beacon empty-state CTA still navigates to old tab name after D3 | Click goes to dead route | The alias map (D0) should catch this. If not, audit each empty state CTA manually after D3.6 |

### 27.8 D4 — Operations merge (2-3 days, 7-8 commits)

| Failure | Symptom | Recovery |
|---|---|---|
| **Polling timer leaks despite lifecycle hooks** | After switching Beacons → Terminal, `BEACON.pollInterval` keeps firing in background | Verify each sub-pill's leave hook clears ALL its timers. Add a test that switches sub-pills 10x rapidly and asserts no orphaned `setInterval` IDs (track them in `window._activeTimers` for debug) |
| **Modal orphaning** (§26.4 item 1) | User opens session-logs modal on Beacons, switches to Terminal — modal stays open above a hidden Beacon subtree | Sub-pill leave hook calls `closeAttachedModals()`: enumerates known modal IDs (`session-logs-modal`, `archived-logs-modal`, `screenshot-overlay`), removes them from DOM |
| Per-sub-pill deployment override (Decision #9) gets out of sync with global | Operator changes global selector; Operations sub-pill keeps showing old deployment data | When a sub-pill has its local override set, ignore global changes. When override is cleared (operator clicks "use global"), snap back to global. Visual indicator: pill shows "📌 c2_adhoc (local)" vs "c2_adhoc (global)" |
| Terminal WebSocket gets stale `deployment` context after sub-pill switch | Terminal connects to wrong host | WebSocket established at sub-pill enter with the active deployment. If deployment changes mid-session, leave the existing tunnel and offer a "Reconnect for new deployment" banner |
| Async `BEACON.refreshBeaconDetail()` completes after sub-pill is hidden (§26.4 item 5) | `Cannot read properties of null (reading 'innerHTML')` in console | Either: (a) abort fetch on sub-pill leave using AbortController; (b) check `BEACON.currentSubPill === 'beacons'` before updating DOM in the .then handler |

### 27.9 D5 — Dashboard upgrade (half-day, 4 commits, depends on P1 #4)

| Failure | Symptom | Recovery |
|---|---|---|
| `/api/audit/recent` doesn't exist yet (P1 #4 hasn't shipped) | Recent activity feed renders empty | Ship D5.2 with placeholder data + visible "Audit middleware not yet active" badge. Backfill when P1 #4 lands |
| Cost trend tile hits Cost Explorer rate limits | Tile shows "limit exceeded" | Cache last successful response for 1 hour. Show stale data with `(last updated 47 min ago)` indicator |
| Deployments grid render is slow with many deployments | Dashboard takes 3s+ to render | Paginate or virtualize the grid. Lazy-load instance details on click |

### 27.10 D6 — Bookmarkable URLs (half-day, 2 commits)

| Failure | Symptom | Recovery |
|---|---|---|
| `history.pushState` triggers infinite loop with sessionStorage save | URL changes → load → save → URL changes... | Guard `pushState` with `if (window.location.hash !== newHash)` |
| URL params encode deployment names with special chars (slashes, spaces) | URL `#operations/beacons?dep=my deployment` breaks | URL-encode + decode deployment names. Test with `c2_adhoc_dev_harriss_macbook_pro_01` (underscores are safe, but verify edge cases) |
| Bookmark resolves to a sub-pill that no longer exists (renamed) | Blank screen | Alias map handles renames. Add a fallback: unknown sub-pill → first sub-pill of that parent |

### 27.11 Production cutover (post-merge, operator-initiated)

| Failure | Symptom | Recovery |
|---|---|---|
| Operator has dirty working tree on EC2 (someone edited `/opt/redteam/` directly) | rsync would overwrite their changes | **Pre-cutover check (add to script):** `cd /opt/redteam && git status --porcelain` — if non-empty, abort and warn. Operator must commit/stash before cutover |
| rsync overwrites `/opt/redteam/.git/` | Loses git history on EC2 | rsync command MUST include `--exclude='.git'`. Verify in `setup-dashboard.sh:85-118` |
| `pip install` fails on EC2 (network blip, dep resolution) | systemctl restart fails to start Flask | Roll back: `git checkout v1.0.0 && pip install -r requirements.txt && systemctl restart dashboard`. If pip still fails, manually pip install missing wheels |
| `systemctl restart dashboard` succeeds but Flask hangs at startup (e.g. waiting on AWS API) | Browser hangs on connect | `journalctl -u dashboard -n 100 -f` — find the hung call. Most likely cause: AWS API throttle or missing IAM permission. Verify with `aws sts get-caller-identity` from the EC2 |
| Operator tunnelled in during cutover loses dashboard but tunnel stays open | Browser shows "connection refused" for 30s | Expected. Operator refreshes after restart completes. **Add to operator playbook:** wait 60s after running upgrade before refreshing |
| **No EBS snapshot taken before cutover** | If cutover bricks the EC2, no fast recovery | **Pre-cutover step in playbook:** `aws ec2 create-snapshot --volume-id $(aws ec2 describe-instances --instance-ids $DASHBOARD_INSTANCE --query 'Reservations[].Instances[].BlockDeviceMappings[0].Ebs.VolumeId' --output text) --description "dashboard-pre-v$NEW_VERSION"`. Tag with `Retain=manual` so DLM doesn't expire it |
| In-flight `terraform apply` running on the EC2 dashboard when restart happens | Apply may complete (subprocess survives Flask restart) but Flask doesn't see the result | Pre-cutover check: `pgrep -f "terraform apply" || echo 'safe'`. If running, wait for it OR abort cutover |

### 27.12 Cross-cutting failure modes

**PR review blockers (solo operator workflow):**
- If you context-switch mid-refactor (CS incident, real engagement) and a PR sits for days, branches drift from main. Recovery: rebase the branch (`git rebase main`), resolve conflicts, force-push to PR branch.
- Mitigation: merge each phase's PR within 24h of opening. If you can't, close the PR and re-open later from a fresh branch.

**Test framework regresses unexpectedly:**
- A new commit makes `make test` red. You can't tell if the test is wrong or the code is wrong.
- Recovery: bisect. `git bisect start && git bisect bad HEAD && git bisect good <last-known-green>`. Run `make test` per bisect step.

**Live engagement happening during the refactor:**
- An operator on the LIVE dashboard hits a real-engagement issue while you're mid-D3. They need fixes shipped fast.
- Recovery: hotfix branch from `main` (not from your refactor branch). Ship hotfix, tag patch version (e.g. v1.0.1). Rebase your refactor branch onto the new main when convenient.

**Snapshot guard becomes a tax instead of a safety net:**
- After D3, the snapshot fails on legitimate UI changes you intended to make. You spend 30 min per commit blessing the diff.
- Recovery: lower the snapshot bar. Capture only the most-important conditional sections (the 10 from §20.2), not every DOM element. Or shift to property-based assertions ("c2-adhoc shows file-portal section" — yes/no) instead of pixel-perfect snapshots.

### 27.13 Stop-the-line triggers

These conditions should stop the work immediately and force a re-plan, not iterate around:

1. **Prism cannot mock OpenAPI 3.1.0 well enough.** Plan Layer 1.5 falls back to schema-validation-only. Add note + continue. Don't sink hours fighting Prism. Time-box T0.4 to 2h max.
2. **`updateDeploymentType()` is non-deterministic and the snapshot test is flaky.** Three retries with delays; if still flaky, the snapshot guard for D3 won't work. Re-evaluate the refactor approach (do D3 with manual click-through instead, or refactor `updateDeploymentType` to be sync-only).
3. **Cutover bricks the EC2 dashboard.** Use the EBS snapshot to restore the volume. Don't try to fix in place under pressure. Then post-mortem.
4. **A live engagement needs the dashboard during the refactor.** Pause refactor. Ship hotfixes from main. Resume when the engagement is over.

### 27.14 Summary: total realistic worst-case timeline

| Phase | Best case | Realistic | Worst case (if a 27.x failure hits) |
|---|---|---|---|
| Pre-flight (§27.1) | 30 min | 45 min | 2h (Playwright download + dep resolution) |
| T0 (test framework) | 8h | 10h | 14h (Prism fallback + Vitest skip + snapshot debugging) |
| Versioning | 2h | 2.5h | 3h |
| D0 | 2h | 3h | 4h (sessionStorage backwards-compat edge cases) |
| D1 | 4h | 5h | 7h (cost API + selector polish) |
| D2 | 4h | 4h | 5h |
| D3 | 16h | 20h | 28h (snapshot debugging + duplicate-ID resolution + Edit Config inline polish) |
| D4 | 16h | 22h | 32h (modal cleanup + WebSocket re-connect + lifecycle hooks per commit) |
| D5 | 4h | 5h | 8h (cost API rate limits) |
| D6 | 4h | 4h | 6h |
| **Total** | **~60h** | **~76h** | **~109h** |

Best case ~7-8 working days. Realistic ~10 working days. Worst case ~14 days. Plan for realistic; have a hard stop at 14 days to reassess.

**No additional decisions needed from this section** — all recovery paths are within scope of the existing plan and decisions log.

---

## 28. Skills used per phase

Two relevant skills available in the harness; documented here so it's explicit which gets invoked when.

### 28.1 `ui-quality-check` — MANDATORY for every UI-touching commit
Covers dual-theme verification (dark/light), color variable safety (no raw hex), contrast ≥ 4.5:1, centralized component reuse. The CLAUDE.md theming notes make this non-negotiable for this codebase. Invoked before completing ANY commit that modifies `webapp/frontend/*.html`, `*.css`, or `*.js`.

### 28.2 `frontend-design` — used where NEW UI is generated, not where existing UI is re-parented

| Phase | Touches frontend? | `ui-quality-check`? | `frontend-design`? | Notes |
|---|---|---|---|---|
| **T0** (test framework) | No | — | — | Pure infra |
| **P1 #7.6** (versioning) | Adds version footer (~10 LoC) | ✅ | 🟡 light touch | Footer is small enough to write directly; ui-quality-check verifies theme + contrast |
| **D0** (routing aliases) | No DOM | — | — | Pure JS plumbing |
| **D1** (global header) | NEW UI | ✅ | ✅ **YES** | Header is fresh real estate — selector + cost indicator + operator badge + theme toggle layout. Use frontend-design for polish |
| **D2** (Pre Reqs → Settings) | Moves existing | ✅ | ❌ | Re-parent verbatim — no design work |
| **D3** (Deployments merge) | Pill switcher = new, sub-views = re-parented | ✅ | 🟡 **YES for pill switcher only** | Sub-pill component is new (use frontend-design). The 3 sub-view subtrees are re-parented verbatim per Decision #6 / §20.2 |
| **D4** (Operations merge) | Pill switcher = new, sub-views = re-parented | ✅ | 🟡 **YES for pill switcher only** | Same pattern as D3. Pill component shared with D3 if possible |
| **D5** (Dashboard upgrade) | All new widgets | ✅ | ✅ **YES** | Live deployments grid, recent activity feed, cost trend tile, "Create new deployment" CTA — all net-new components. Highest design-leverage phase |
| **D6** (URL routing) | No DOM | — | — | Pure JS |

### 28.3 Other harness skills relevant to execution

- **`superpowers:dispatching-parallel-agents`** — used for every D-commit where multiple independent sub-tasks exist (e.g., re-parenting Configure + Deploy + Manage subtrees in D3 can be three parallel agents after D3.1 lands).
- **`superpowers:verification-before-completion`** — invoked before marking any commit done (run `make test`, confirm green, screenshot the affected UI region).
- **`superpowers:test-driven-development`** — applies to D-phases (write the snapshot guard / unit test, then make it green). Does not apply to T0 framework setup itself (we ARE building the tests there).
- **`superpowers:requesting-code-review`** — invoked at each phase boundary when opening the PR for user review.

---

## 29. UI-side deployment configuration inventory

Exhaustive trace of every conditional UI element that depends on `deployment_type`, captured BEFORE D3 starts so nothing gets dropped during the merge. Source-of-truth check for the upcoming Configuration tab re-parenting.

### 29.1 Visibility matrix — 11 deployment types × 11 sections

| Deployment Type | domain-config | ssl-config | domain-fronting | file-portal | attack-box | decoy-theme | malleable-profile | goad-network | c2-server-count | c2-instance-type | key-pair-name |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **c2-adhoc** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | enabled |
| **c2-purple** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | enabled |
| **c2-full** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ (fixed=3) | ✓ | enabled |
| **goad-mini** | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✓ | ✓ | ✗ | ✗ | **disabled** |
| **goad-light** | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✓ | ✓ | ✗ | ✗ | **disabled** |
| **goad-sccm** | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✓ | ✓ | ✗ | ✗ | **disabled** |
| **goad-full** | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✓ | ✓ | ✗ | ✗ | **disabled** |
| **goad-nha** | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✓ | ✓ | ✗ | ✗ | **disabled** |
| **combined-adhoc-mini** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | enabled |
| **combined-adhoc-light** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | enabled |
| **combined-full-full** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ (fixed=3) | ✓ | enabled |

Each cell maps to a `display: block | none` decision in `updateDeploymentType()` (app.js:7517-7783) — 121 visibility combinations must survive D3 re-parenting.

### 29.2 Cross-deployment features

- **Domain Fronting (CloudFront)** — `enable-domain-fronting` toggle in `domain-fronting-section`. Visible only for C2/Combined. When checked, **cascades** to: SSL section (forces self-signed + disables manual options + shows override banner), malleable profile section (front-domain input appears + profile preview re-renders with domain-fronting snippet), security (redirector SG locks to CloudFront prefix list). Single Terraform var: `enable_domain_fronting`. Not deployment_type-dependent — purely a feature flag, but only meaningful for C2 deployments.
- **File Portal** — `enable-file-portal` only for C2 deployments WITH redirectors (excludes goad-only, c2-only-with-no-redirector — currently no such config). Hosted at `https://www.<domain>/login`. Three fields: username, password, session timeout.
- **Malleable Profile** — present for ALL 11 types (always shown when CS is in scope, which is all of them). Selector has built-in (default/amazon/google/microsoft/wikipedia), catalog (loaded dynamically), or custom. Custom path opens 4 nested conditional sub-sections: paste textarea, validation status, URI preview, nginx preview.
- **Attack Box** — visible for ALL 11 types. Subnet placement varies (C2 VPC for c2-* and combined-*, GOAD VPC for goad-*).
- **GOAD Provisioning** — `goad_lab_type` derived from `deployment_type`. UI shows `goad-vpc-cidr` + read-only derived `goad-ip-range`.

### 29.3 Field count per section (for sizing the D3 work)

- `domain-config-section`: 6 inputs (primary, backups, 3 subdomains, check button)
- `ssl-config-section`: 4 inputs + override banner
- `domain-fronting-section`: 2 inputs (toggle + front-domain)
- `file-portal-section`: 4 inputs (toggle + username + password + timeout)
- `attack-box-config-section`: 5 inputs (toggle + type + disk + pw-mode radios + custom pw)
- `decoy-theme-section`: 1 select
- `malleable-profile-section`: 1 selector + 1 paste textarea + 6 dynamic preview/status sub-sections + 3 preview tabs
- `goad-network-config-section`: 2 inputs (CIDR + derived range)
- C2 server count/instance type groups: 2 inputs

**Total: ~35 distinct input fields in Configuration. Plus Deploy-tab fields (~15 more in CS archive / CS client / password mode / license mode / REST API / SSH key sections).**

### 29.4 Top 5 D3 fragility risks (regression tests required)

1. **Domain Fronting SSL Override Chain** — cascade from `enable-domain-fronting` to SSL section + front-domain visibility + malleable profile preview. 5 elements involved, 1 event listener at app.js:517-538.
2. **Malleable Profile Conditional Rendering** — `malleable-profile` value drives 7+ nested elements (status banners, paste area, validation, preview tabs, URI/nginx previews).
3. **GOAD-only Disable/Hide Logic** — `key-pair-name` (disabled + placeholder text change), c2-server-count-group (hidden), c2-instance-type-group (hidden). Three coupled state changes.
4. **Deploy Tab Prerequisites Chain** — `updateDeploymentPrerequisites()` disables deploy button until domain prereq + CS file + SSH key all pass. Cross-section dependency.
5. **Inline `onchange` Handlers** — 6 inline `onchange="updateDeploymentType()"`-style attributes + setupDomainFrontingHandlers / setupFilePortalHandlers / setupMalleableProfileHandlers added at runtime. If HTML re-parents, attributes can be lost or duplicated.

### 29.5 The "must not break" constraint

When `<div data-page="configuration">` re-parents into the new Deployments tab Configure sub-pill:
- All ~50 `id="..."` attributes inside the subtree must remain accessible to `document.getElementById()` (100+ call sites in app.js).
- All inline `onchange` attributes must keep firing.
- All setup* functions called on tab init must re-bind.
- CSS selectors keyed to `.tab-page[data-page="configuration"]` will likely need updating (audit before D3).

**The §21.5 snapshot guard captures the visibility-matrix portion of this (Part 1). The remaining concerns — input values, validation, side effects — need explicit Playwright tests added during D3.0 (snapshot capture phase).**

---

## 30. Terraform-side deployment configuration inventory

Companion to §29 — what Terraform actually provisions per deployment_type. Captured BEFORE D3 to ensure module count logic, secrets flow, and bootstrap chain are documented.

### 30.1 Module instantiation matrix

| Deployment Type | vpc | security | dns | certs | c2_team_server | c2_phase_servers | redirector | bastion | attack_box | goad | vpc_peering | dep_storage | domain_fronting |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| c2-adhoc | 1 | 1 | cond | cond | 1 | 0 | 1 | 1 | cond | 0 | 0 | cond | cond |
| c2-purple | 1 | 1 | cond | cond | 1 (count=2) | 0 | 1 | 1 | cond | 0 | 0 | cond | cond |
| c2-full | 1 | 1 | cond | cond | 0 | for_each×3 | 1 | 1 | cond | 0 | 0 | cond | cond |
| goad-* (×5) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | cond | 1 | 0 | cond | 0 |
| combined-adhoc-mini | 1 | 1 | cond | cond | 1 | 0 | 1 | 1 | cond | 1 | 1 | cond | cond |
| combined-adhoc-light | 1 | 1 | cond | cond | 1 | 0 | 1 | 1 | cond | 1 | 1 | cond | cond |
| combined-full-full | 1 | 1 | cond | cond | 0 | for_each×3 | 1 | 1 | cond | 1 | 1 | cond | cond |

Conditions: `cond` = depends on a feature toggle (`enable_attack_box`, `enable_ssl_certificate`, `enable_domain_fronting`) or other input (`primary_domain_name != ""`), not on `deployment_type` alone.

### 30.2 Variable groups (~90 variables total)

- **Always used** (7): `project_name`, `environment`, `aws_region`, `deployment_type`, `availability_zones`, `enable_attack_box`, `tags`
- **C2/Combined only** (~30): VPC, security, c2_team_server (or c2_phases map), proxy_redirector, bastion, CS config, domain/DNS, SSL, malleable profile, decoy theme, file portal
- **GOAD/Combined only** (~5): `goad_lab_type`, `goad_vpc_cidr`, `goad_public_subnet_cidr`, `goad_private_subnet_cidr`
- **Phase-mode-only** (`c2-full`, `combined-full-full`): `c2_phases` map with 3 entries (staging, post-ex, long-haul)
- **Domain Fronting only** (4): `enable_domain_fronting` + reused domain vars (no separate CloudFront vars — single distribution per deployment)
- **Optional features**: `enable_nacls`, `enable_nat_gateway`, `enable_bastion`, `enable_file_portal`, `enable_cs_rest_api`, `enable_dashboard_server`
- **Tools/secrets** (8): `tools_repo_*`, `cs_teamserver_password`, `attack_box_admin_password`, `cobalt_strike_license_secret_name`, `user_public_key`, `key_pair_name`

### 30.3 Domain Fronting deep-dive (the user's explicit callout)

**Module:** `terraform/modules/domain_fronting/`
**Provisioned when:** `local.deploy_domain_fronting = (is_c2_only || is_combined) && var.enable_domain_fronting`
**Resources:**
- 1× CloudFront distribution with primary + backup domains as aliases, caching fully disabled (`min_ttl=0, default_ttl=0, max_ttl=0` — critical for C2 beacons), all methods + headers + cookies forwarded
- 1× ACM certificate in **us-east-1** (CloudFront requirement; auto-validated via Route53)
- Route 53 alias records replace direct A records (handled in `dns` module via `enable_domain_fronting` toggle)
- Security group rules on redirectors restricted to CloudFront managed prefix list `com.amazonaws.global.cloudfront.origin-facing` (~120 CIDR ranges — may hit SG quota)

**Operator workflow** (not in Terraform): use FindFrontableDomains → pick a frontable domain → update CS Malleable profile with that domain as `Host` header → no infrastructure change needed (alias already pre-loaded on the CloudFront distribution).

**Domain rotation:** instant (just change CS profile). No redeploy.

### 30.4 Bootstrap chain per deployment_type

| Script | Runs on | Triggered by | Status file | Idempotent |
|---|---|---|---|---|
| `install_cobalt_strike.sh` | c2_team_server OR c2_phase_servers OR (goad jumpbox in goad-only) | `cobalt_strike_archive_s3_path != ""` AND C2 mode (or goad-only with `install_cobalt_strike=true`) | `/opt/setup-status.json` | partial |
| `setup_redirector.sh` | proxy_redirector | `primary_domain_name != ""` AND C2/combined | `/opt/setup-status.json`, `/opt/ssl-status.json` | yes |
| `attack_box_init.ps1` | attack_box (all deployment types when `enable_attack_box=true`) | always (when enabled) | `C:\ProgramData\setup-status.json` | partial |
| bastion `user_data.sh` | bastion (C2/combined) | always | `/opt/setup-status.json` | yes |
| goad jumpbox init | goad jumpbox | always (in goad/combined) | (no status file — gap) | partial |
| dashboard_server `user_data.sh` | dashboard EC2 (separate workspace) | when `enable_dashboard_server=true` | none | yes |

### 30.5 Secrets flow (where each lives + how it's consumed)

| Secret | Source | Storage | Runtime path | In TF state? |
|---|---|---|---|---|
| `cs_teamserver_password` | terraform.tfvars (sensitive) | Terraform state + EC2 user_data | install_cobalt_strike.sh → `/opt/cobaltstrike/c2.profile` | **YES** (in state) |
| `cs_license_key` | AWS Secrets Manager (pre-created by operator) | Secrets Manager | install_cobalt_strike.sh fetches via IAM at install time → `./update` | NO (not in state) |
| `tools_repo_https_token` | terraform.tfvars (sensitive) | AWS Secrets Manager (auto-created by `deployment_storage` module) | attack_box_init.ps1 fetches via IAM | encrypted in state |
| `attack_box_admin_password` | terraform.tfvars OR auto-generated `random_password` | Terraform state (sensitive) | EC2 user_data → RDP password | **YES** (in state) |
| Windows SSH private key | `tls_private_key.windows` auto-generated | Terraform state | EC2 key pair | **YES** (in state) |
| `portal_password` | terraform.tfvars (sensitive) | Terraform state + EC2 user_data → nginx config | redirector file portal auth | **YES** (in state) |
| Operator SSH keys (dashboard) | dashboard.tfvars (`operator_ssh_public_keys` map) | dashboard EC2 user_data | Linux user authorized_keys | NO (public keys only) |

**Local terraform state is unencrypted on disk.** Remote S3 backend (with SSE-KMS) recommended for production — currently commented out in main.tf.

### 30.6 Configuration not in terraform.tfvars

- **CS archives** (team server `.tar.gz` + client `.exe`/`.zip`): uploaded by operator to S3 BEFORE `terraform apply`. Path stored as Terraform output `cs_storage_upload_command`. Bootstrap downloads from S3 via IAM instance profile.
- **Malleable profile catalog**: hardcoded in redirector script; UI shows dropdown loaded from a static catalog.
- **Domain DNS records**: operator updates registrar nameservers AFTER Terraform creates the Route 53 hosted zone (manual step, 24-48h propagation).
- **Domain Fronting front domain selection**: operator uses FindFrontableDomains tool, picks operationally — never in Terraform.
- **Operator identity**: NO per-operator audit for C2 servers today (P1 #4 audit middleware will add it at dashboard layer); dashboard.tfvars has `operator_ssh_public_keys` for dashboard SSH access only.

### 30.7 Runtime-mutable vs requires-apply vs requires-destroy

| Change | Runtime | Apply | Destroy+Recreate |
|---|---|---|---|
| Beacon listeners (CS REST API) | ✓ | — | — |
| Domain rotation (CloudFront alias switch) | ✓ | — | — |
| C2 instance type | — | ✓ | — |
| Redirector count | — | ✓ | — |
| Enable/disable domain fronting | — | ✓ (destroys/creates CloudFront) | — |
| Enable/disable file portal | — | ✓ | — |
| Malleable profile change | — | ✓ (redirector restart) | — |
| GOAD lab size (mini→light→full) | — | — | ✓ |
| VPC CIDR change | — | — | ✓ |
| Bucket name change | — | — | ✓ |

D3 UI must surface this distinction — "save + redeploy" vs "save only" indicators per field.

### 30.8 Top 5 Terraform-side risks for D3

1. **`enable_domain_fronting` is easy to miss** — defaults to false, hidden behind a checkbox, no warning on apply if a C2 deployment lacks CloudFront. D3 must surface this toggle PROMINENTLY in the Configure sub-pill with a clear description and a "test domain frontability" callout.
2. **CS archive upload is manual + silent-fail-prone** — Terraform output shows the upload command but operators forget. D3 Deploy sub-pill should auto-check S3 for archive presence before allowing apply.
3. **Phase-mode (c2-full) confuses operators** — three independent servers, not redundancy. D3 Manage sub-pill must show staging / post-ex / long-haul as separate cards with separate connection commands and a warning: "No automatic failover; manual phase switching."
4. **dashboard.tfvars vs terraform.tfvars conflation risk** — D3 must keep them visually + operationally distinct. Dashboard config gets its own sub-section or warning banner.
5. **Custom Malleable profile validation** — if `custom_profile_content` is set but `malleable_profile != "custom"`, the custom content is silently ignored. D3 should force-set the selector when content is pasted, or validate the mismatch.

### 30.9 Pre-D3 audit checklist

Before D3.1 lands, verify:
- [ ] All 11 deployment types' Terraform plans are unchanged (compare `terraform plan -out=tfplan` before + after D3.0 baseline)
- [ ] CS archive presence check added to Deploy sub-pill workflow
- [ ] Domain fronting toggle prominently placed (not buried in collapsed section)
- [ ] Phase-mode docs explicit in Manage sub-pill
- [ ] dashboard.tfvars distinction preserved (separate section, clear labeling)
- [ ] Custom profile content + selector mismatch validation

---

### 28.4 Taste-skill (Leonxlnx/taste-skill, 13 variants installed)

Installed manually per Decision #12 at `~/.claude/skills/taste-suite/` (user-wide, not project-scoped). Available variants:
- `taste-skill` (main `design-taste-frontend`) — the core
- `gpt-tasteskill` — stricter GPT/Codex-oriented variant
- `brutalist-skill`, `minimalist-skill`, `soft-skill` — aesthetic presets
- `redesign-skill` — improve an existing codebase
- `image-to-code-skill` — image → analyze → code
- `imagegen-frontend-web`, `imagegen-frontend-mobile`, `brandkit`, `stitch-skill` — image deliverables
- `output-skill` — formatting helpers

**Dial settings for this project (Decision #13):**
- `DESIGN_VARIANCE=6` (vs taste-skill's own 8 default)
- `MOTION_INTENSITY=3` (vs 6 default — ops dashboard, low motion)
- `VISUAL_DENSITY=6` (vs 4 default — operators need state visible)

**Critical adapter notes** (must be passed at every invocation):
- The skill defaults to React + Next.js + Tailwind. **Override:** "use vanilla HTML/JS only, no React, no Tailwind, no JSX."
- The skill assumes greenfield. **Override:** "use existing `webapp/frontend/css/palette.css` CSS variables (--accent, --gold-muted, --bg-section, etc.). Never use raw hex."
- The skill is theme-agnostic. **Override:** "all output must work in both `[data-theme="dark"]` and default (light) per CLAUDE.md `### Frontend CSS / Light Mode`."
- The skill has an "ANTI-EMOJI POLICY [CRITICAL]" — happily aligns with this project's no-emoji preference.

**Comparison via T1 pilot phase** (per Decision #14, see §17 item 7.7) — before applying taste-skill across the refactor, build D1 header twice on `refactor/design-pilot` branch: baseline (no taste-skill) and taste-skill-styled. User compares pixel-for-pixel and picks the design direction. Decision then locks in for D1/D3/D4/D5.

### 28.4 Skills NOT used (for explicitness)

- **`superpowers:brainstorming`** — not used during execution. The plan IS the brainstorming output. We're in execution mode per Decision #5.
- **`superpowers:writing-plans`** — not used; this document is the plan.
- **`init`, `review`, `security-review`, `claude-api`, etc.** — not relevant to this workstream.

### 24.2 Alternatives if you want something lighter

- **Just git SHAs**: skip SemVer, display short SHA in footer (`8b377ac`), use commit messages as release notes. Simpler, but operators have to read commit log to understand what changed.
- **CalVer (`2026.05.0`)**: date-based versioning. Easier to manage (every release is just today's date) but less semantic about what changed.
- **`VERSION` + footer only, no git tags**: minimal — just shows operators what's running, no release ceremony.

### 24.3 Recommendation

**Full SemVer + footer + CHANGELOG + tags + release script.** It's ~2 hours of one-time setup (one new commit), pays for itself the first time an operator asks "wait, which version am I on?", and gives us a clean way to talk about "v1.0.0 dashboard refactor complete" as a deliverable.

I've added it to §17 as a new **P1 item #7.6 "Versioning system"** below the test framework — see roadmap update. Wants your confirmation before I include it.

---

## 18. Sources

### Cobalt Strike maintenance
- [Blog index — Cobalt Strike](https://www.cobaltstrike.com/blog)
- [Cobalt Strike auth file generator (download.cobaltstrike.com)](https://download.cobaltstrike.com/authgen.slp)
- [Cobalt Strike download (download.cobaltstrike.com)](https://download.cobaltstrike.com/download)
- [Cobalt Strike release notes](https://download.cobaltstrike.com/releasenotes.txt)
- [License authorization files documentation](https://hstechdocs.helpsystems.com/manuals/cobaltstrike/current/userguide/content/topics/install_authorization-files.htm)
- [Cobalt Strike 4.8 release notes — TLS cert rotation precedent](https://www.cobaltstrike.com/blog/cobalt-strike-4-8-system-call-me-maybe)
- [Reset license key — historical context](https://www.cobaltstrike.com/blog/howto-reset-your-cobalt-strike-license-key)
- The May 2026 maintenance blog URL itself (`/blog/cobalt-strike-infrastructure-maintenance-may-2026`) returned HTTP 403 to automated fetch — Fortra blocks bots. The change date (Mon 2026-05-18) and the affected workflow (download + authentication) were extracted from Google's search snippet of that page.

### Vulnerable-lab solutions
- [Vulhub — vulhub/vulhub on GitHub](https://github.com/vulhub/vulhub) (docker-compose CVE library)
- [Vulhub.org documentation](https://vulhub.org/documentation/getting-started)
- [Splunk Attack Range — splunk/attack_range](https://github.com/splunk/attack_range)
- [Splunk Attack Range v5 announcement](https://www.splunk.com/en_us/blog/security/splunk-attack-range-v5-security-lab-guide.html)
- [APT-Lab-Terraform — DefensiveOrigins](https://github.com/DefensiveOrigins/APT-Lab-Terraform)
- [AWSGoat — ine-labs](https://github.com/ine-labs/AWSGoat)
- [CloudGoat — Rhino Security Labs](https://rhinosecuritylabs.com/aws/cloudgoat-vulnerable-design-aws-environment/)
- [IAM Vulnerable — BishopFox](https://github.com/BishopFox/iam-vulnerable)
- [CISA Vulnerable Instances — cisagov](https://github.com/cisagov/vulnerable-instances)
- [DarkRelay vulnlab_aws](https://github.com/DarkRelay-Security-Labs/vulnlab_aws)
- [DetectionLab (reference only — unmaintained)](https://github.com/clong/DetectionLab)
- [OWASP Vulnerable Container Hub](https://github.com/OWASP/vulnerable-container-hub)

### Red team infra automation references
- [Automating Red Team Infrastructure with Terraform — Red Team Notes](https://www.ired.team/offensive-security/red-team-infrastructure/automating-red-team-infrastructure-with-terraform)
- [Applied Purple Teaming Lab on Azure — Black Hills](https://www.blackhillsinfosec.com/how-to-applied-purple-teaming-lab-build-on-azure-with-terraform/)
- [Infrastructure as Code (Terraform + Ansible) — Rasta Mouse](https://rastamouse.me/infrastructure-as-code-terraform-ansible/)

---

## 19. Dashboard user flows — evaluation and tab merge proposal

### 19.1 Current tab inventory (verified from `index.html`)
10 top-level tabs in the order they appear in the nav:

| # | Tab (label) | `data-target` | HTML line | Primary purpose | Lifecycle |
|---|---|---|---|---|---|
| 1 | Dashboard | `dashboard` | 35 | infra overview + Elastic detection rules card | always-on |
| 2 | Pre Reqs | `aws-check` | 1227 | AWS prerequisites validation | one-time / per-laptop |
| 3 | Configuration | `configuration` | 61 | edit `terraform.tfvars` via UI | every deploy cycle |
| 4 | Deploy | `deployment` | 807 | run plan/apply/destroy + watch status | every deploy cycle |
| 5 | Deployment Manager | `deployments` | 2228 | lifecycle (stop/start/destroy/purge), per-deployment status grid | always-on |
| 6 | Tools | `tools` | 1277 | SCP-upload files to attack box via bastion | mid-engagement |
| 7 | Architecture | `architecture` | 1378 | view static architecture diagrams + per-deployment docs | reference / onboarding |
| 8 | Beacon | `beacon` | 1420 | CS REST API beacon control panel | mid-engagement |
| 9 | Terminal | `terminal` | 2011 | local shell + SSH PTY via WebSocket | mid-engagement |
| 10 | Settings | `settings` | 2056 | theme, cost budget, prefs | rare |

### 19.2 Real operator user flows
For each persona, I mapped the natural click sequence and counted tab switches.

**Flow A — First operator provisioning a new C2 engagement**
1. `Pre Reqs` → verify AWS access (one-time, often skipped on re-visits)
2. `Configuration` → pick deployment type, fill domains, CS license secret name, malleable profile, attack box admin password
3. `Deploy` → click "Plan", review, click "Apply", watch logs stream
4. `Deployment Manager` → confirm running, see EIPs, SSH commands, S3 bucket
5. `Tools` → upload Outflank / custom payloads
6. `Architecture` → maybe glance at the diagram for the deployment type
7. `Beacon` → wait for first callback, issue commands
8. `Terminal` → SSH into bastion if needed

**Tab switches: 7-8.** Configuration ↔ Deploy ↔ Deployment Manager is the dominant trio. The Deploy tab already has an `Edit Config` button (`onclick="APP.navigateTo('configuration')"` — index.html:829) that bounces back. That cross-link IS the symptom: the user lives in three tabs that are really three stages of one workflow.

**Flow B — Joining operator on day 2 of an engagement**
1. (Tunnel in, dashboard loads on `Dashboard`)
2. `Deployment Manager` → see what's running, get IPs
3. `Beacon` → pick deployment → check live beacons → issue commands
4. `Terminal` → tunnel SSH for non-beacon ops
5. `Tools` → upload a quick payload

**Tab switches: 4-5.** Beacon/Terminal/Tools is the operational triangle. Today the operator can only see one at a time. Real engagement work would benefit from a split-pane.

**Flow C — Mid-engagement adjustment (e.g., add a redirector or change malleable profile)**
1. `Deployment Manager` → confirm running deployment
2. `Configuration` → edit
3. `Deploy` → re-apply
4. `Deployment Manager` → verify

**Tab switches: 4 just to make one change.** Should be 1 (configure-in-place + re-apply button on Deployment Manager).

**Flow D — End-of-engagement teardown**
1. `Deployment Manager` → Destroy / Stop / Purge buttons

✅ Single tab. Already correct.

### 19.3 Friction points found
| Friction | Where | Severity | Evidence |
|---|---|---|---|
| **Configuration / Deploy / Deployment Manager** are the same workflow split into 3 tabs | nav order 3-4-5 | **HIGH** | "Edit Config" button on Deploy bounces to Configuration (index.html:829). Operator context-switches mid-task. |
| **Beacon tab requires a deployment selector** — can't easily compare beacons across deployments | beacon-deployment-select (line 1426) | MED | If running 2 engagements, operator must keep switching deployments in this dropdown. |
| **Tools tab is one feature** (SCP upload to attack box) dressed as a top-level concept | line 1277 | MED | This is 1 task in the broader Operations flow. Doesn't deserve top-level real estate. |
| **Pre Reqs** is one-time but always visible | nav order 2 | LOW-MED | Once verified, this tab is never re-visited. Wastes a top-level slot for ~99% of sessions. |
| **Architecture** tab is reference content, not action | nav order 7 | LOW | Operators view it once for onboarding then ignore. Better as a side-panel or modal from Configuration. |
| **Dashboard is underused** — currently shows status + Elastic rules card only | line 35 | MED | Should be the launchpad: live deployments, recent activity, alerts, cost trend, quick "create new deployment" CTA. |
| **No persistent "active deployment" context** — operator picks deployment in Beacon, then has to pick it again in Tools, again in Architecture | various dropdowns | MED | Should be one global context selector in the header. |
| **No back/forward affordance** — `APP.navigateTo()` doesn't update URL or history | js/app.js | LOW | Operator can't bookmark "Beacon for project-X" or browser-back. |
| **Settings buries cost** — budget alert only surfaces on Deployment Manager (`cost-budget-alert`, line 2238) and Settings | line 2056 | MED | Cost should be a Dashboard tile + a header indicator. |
| **Beacon "No Active Deployments" empty state** sends operator to Configuration with one click but no "create new" affordance on Beacon | line 1442 | LOW | Empty-state CTAs scattered. |

### 19.4 Proposed information architecture — 5 tabs instead of 10

```
[ Header ]  Operator badge  •  Active-deployment context  •  Cost indicator  •  Theme

  1. Dashboard      —  Launchpad
  2. Deployments    —  Configure + Deploy + Manage  (merge of 3 → 1)
  3. Operations     —  Beacons + Terminal + Payload upload  (merge of 3 → 1)
  4. Architecture   —  Reference diagrams + docs  (keep or fold into Configuration side-panel)
  5. Settings       —  AWS Pre-Reqs + Cost + Theme + Prefs  (merge Pre Reqs in)
```

**Tab-by-tab spec:**

**1. Dashboard (launchpad)**
- Live deployments grid (count, status, age, EIPs at a glance)
- Recent activity feed (deploys, beacon callbacks, alerts) — depends on §4 audit work landing
- Cost trend tile + monthly burn
- Elastic Detection Rules card (keep)
- "Create new deployment" CTA → opens Deployments → Configure sub-tab in a guided wizard mode
- Alerts: failed deploys, beacon disconnects, budget thresholds

**2. Deployments (workflow workspace)**
Sub-views in a single tab, navigable via in-tab pill switcher:
- **Configure** — current Configuration tab content
- **Deploy** — current Deploy tab content, with `Edit Config` collapsing back to Configure sub-view inline (no page change, no scroll loss)
- **Manage** — current Deployment Manager grid, lifecycle buttons (stop/start/destroy/purge)
- Selector at top: "Active deployment" dropdown that all three sub-views share

Why: maps to the natural Configure → Deploy → Manage progression. Reduces the dominant Flow A from 7 tab-switches to 3 sub-view clicks within the same workspace. Operator doesn't lose context (form state, scroll position).

**3. Operations (engagement workspace)**
Sub-views or a split-pane layout:
- **Beacons** — current Beacon tab (top half)
- **Terminal** — current Terminal tab (bottom half OR right pane)
- **Payload upload** — current Tools tab (collapsible drawer or "Upload" button on the Beacons toolbar)
- Active-deployment selector pulled out of each individual tab and into the workspace header (one selector drives all three).

Why: Beacon + Terminal + Tools are all "I'm running an engagement" tabs. Today the operator can't see a beacon AND a terminal at once. A split-pane lets them watch beacon output while doing a parallel SSH check.

**4. Architecture (reference)**
Two options:
- **Option A (preferred):** keep as a top-level tab, but reduce visual weight. Operators only visit during onboarding.
- **Option B:** fold into Configuration sub-view as a side panel that shows the diagram + brief notes for the currently-selected deployment type. Then delete the top-level tab entirely.

Option B is cleaner but makes ad-hoc diagram browsing harder. Recommend Option A initially, B once we have time.

**5. Settings**
- **AWS Pre-Reqs** (the current Pre Reqs content, moved here — one-time check, doesn't need top-level real-estate)
- **Cost & Budgets** (alerts, monthly burn, per-deployment cost)
- **Theme & display**
- **Audit log preferences** (once §4 lands)
- **Operator profile** (your SSH key, your name, your last login)
- **Sessions** (active operators / connections — once auth/audit lands)

### 19.5 Migration plan (preserve all functionality, lower risk)

| Phase | Effort | Change |
|---|---|---|
| 1 | half-day | Add global header: active-deployment selector, cost indicator. Existing tabs read from this single source. |
| 2 | 1 day | Move "Pre Reqs" into Settings. Remove the top-level button. Add a Settings → "AWS Prereqs" anchor link. |
| 3 | 1-2 days | Merge Configuration + Deploy + Deployment Manager into a single "Deployments" tab with 3 sub-view pills. Keep all existing IDs and JS handlers; just collapse the page-switching layer. |
| 4 | 1-2 days | Merge Beacon + Terminal + Tools into an "Operations" tab with split-pane (or pill switcher initially, split-pane as v2). |
| 5 | half-day | Dashboard upgrade: live deployments grid + recent activity + cost trend tile + create-new CTA. Depends on §4 audit data being available. |
| 6 | optional | URL-routing (e.g., `#/operations/beacons?deployment=c2_adhoc...`) so operators can bookmark/share links. Pulls `APP.navigateTo()` into a real router. |

**Backwards compatibility:** all existing `APP.navigateTo(<old-tab-name>)` calls can be aliased to route to the new sub-views without breaking the ~30+ existing cross-links in `app.js`. Aliases live in one place.

### 19.6 Things to keep as-is (don't over-merge)
- **Beacon REST API empty-states** ("No Active Deployments", "REST API Not Enabled") with CTAs to Configuration are good UX. Just point those CTAs at the new Configure sub-view.
- **Per-deployment dropdowns** in each tab solve a real problem (running 2 engagements concurrently). Keep them, but de-duplicate to one in the workspace header rather than per-tab.
- **Dark/light theme toggle** in the header. Already done well.
- **Architecture deployment selector** with C2 / GOAD / Combined / Component optgroups (index.html:1387) — good IA. Don't flatten it.

### 19.7 Score the proposed change
| Metric | Today | Proposed |
|---|---|---|
| Top-level tabs | 10 | 5 |
| Tab switches for Flow A (new C2 engagement) | 7-8 | 3-4 |
| Tab switches for Flow B (joining operator) | 4-5 | 2 |
| Tab switches for Flow C (mid-engagement edit) | 4 | 1 |
| Concurrent visibility of beacon + terminal | no | yes |
| Persistent "active deployment" context | no | yes |
| Cost visibility | buried in Settings | always in header |

Net: roughly halves operator click cost during deployment cycles and engagement work, makes the deployment context global, and surfaces cost without burying it.

---

## 20. Refactor sanity-check — every conditional, cross-link, and side-effect mapped

This section traces every element that needs to survive the merge, before any code is touched. Verified by reading `webapp/frontend/index.html` (2,419 lines) and `webapp/frontend/js/app.js` (21,187 lines) directly.

### 20.1 Tab boundaries (verified, source-of-truth)
| Tab nav order | `data-target` | `data-page` HTML line | Initial loader (app.js) | On-leave cleanup (app.js:198-222) |
|---|---|---|---|---|
| 1 | `dashboard` | 35 | `loadDashboard()` (app.js:1974) | — |
| 2 | `aws-check` | 1227 | (interactive only, no auto-load) | — |
| 3 | `configuration` | 61 | `loadConfig()` (app.js:6750) | — |
| 4 | `deployment` | 807 | `resetDeployValidation()` + `loadConfigSummary()` + `checkDeploymentStatus()` + `checkDomainConfig()` + `checkCobaltStrikeFile()` + `checkCSClientFile()` + `checkSSHPublicKey()` | clear `deploymentPollInterval` |
| 5 | `deployments` | 2228 | `loadDeploymentsPage()` + `startAutoRefresh()` | `stopAutoRefresh()` + clear `_destroyPollInterval` |
| 6 | `tools` | 1277 | `loadToolsPage()` | — |
| 7 | `architecture` | 1378 | `initArchitecturePage()` | — |
| 8 | `beacon` | 1420 | `BEACON.init()` | `BEACON.stopHealthPoll()` |
| 9 | `terminal` | 2011 | `TERMINAL.init()` | `TERMINAL.stopBackgroundRefresh()` |
| 10 | `settings` | 2056 | (presumed inline init via `loadCostSettings()` etc.) | — |

**Implication for the merge:** sub-views that today live in separate tabs must keep their entering side-effects bound to *sub-view activation*, and their on-leave cleanup must fire when switching *between sub-views* (not only when leaving the parent tab). Otherwise the Beacon health-poll keeps running while you're on the Terminal sub-view of the same parent tab — leaks.

### 20.2 Configuration tab — conditional sections (verified)
The Configuration tab has **10 sections that show/hide based on `deployment-type`**, driven by `updateDeploymentType()` at app.js:7517-7783. Any merge that touches Configuration MUST preserve this logic identity-preservingly.

| DOM id | Default | Show when | Hide when |
|---|---|---|---|
| `deployment-overview` (line 91) | hidden | a `deployment-type` is selected | no type / reset |
| `domain-config-section` (line 104) | shown | `config.requiresDomain` is truthy | otherwise |
| `ssl-config-section` (line 248) | hidden | `config.type === 'c2' \|\| 'combined'` | goad-only |
| `domain-fronting-section` (line 368) | hidden | `config.type === 'c2' \|\| 'combined'` | goad-only |
| `file-portal-section` (line 473) | hidden | `deploymentType IN {c2-adhoc, c2-purple, c2-full, combined-adhoc-mini, combined-adhoc-light, combined-full-full}` (i.e. has redirectors) | goad-only, sccm, nha |
| `attack-box-config-section` (line 506) | hidden | always shown when a type is selected | type cleared |
| `decoy-theme-section` (line 574) | hidden | `config.type === 'c2' \|\| 'combined'` | goad-only |
| `malleable-profile-section` (line 591) | hidden | `config.requiresCS !== false` (i.e. CS is part of the deploy) | non-CS lab |
| `goad-network-config-section` (line 757) | hidden | `config.type === 'goad' \|\| 'combined'` | c2-only |
| `c2-server-count-group` / `c2-instance-type-group` | shown | non-goad | goad-only (display:none, not just disabled) |
| `key-pair-name` (free input + hint) | enabled | non-goad-only | goad-only (auto-generated, disabled w/ message) |

Additionally inside `malleable-profile-section` there are 6 nested conditional sub-sections (`front-domain-group`, `profile-catalog-status`, `profile-custom-status`, `custom-profile-paste`, `profile-validation-status`, `custom-uri-preview`, `custom-nginx-preview` + 2 preview tabs) that toggle based on the **chosen malleable profile** (default / amazon / google / microsoft / wikipedia / custom). These are within the parent section — no extra logic needed if we keep the section intact.

Inside `attack-box-config-section`: `attack-box-custom-pw` toggles based on radio choice (line 553).

Inside the upload card area: `upload-progress`, `cs-file-status`, `cs-file-info`, `cs-client-*` toggle based on file selection / upload progress.

**Verdict:** Configuration is far more conditional than the original §19 plan implied. The merge into a "Configure" sub-pill of the new Deployments tab MUST keep the entire `tab-page[data-page="configuration"]` DOM subtree intact and only re-parent it under the new sub-pill container. Do not rewrite the sections; just move and re-scope.

### 20.3 Cross-tab navigation links — every one (verified)
| Source | Line | Goes to | Why | Post-merge rewrite |
|---|---|---|---|---|
| `index.html:825` ("Edit Config" button on Deploy) | inside `deployment` page | `configuration` | back to config | flip Deployments sub-pill from `deploy` → `configure` |
| `index.html:1141` ("destroy infra" link on Deploy) | inside `deployment` | `deployments` | go to lifecycle/destroy | flip sub-pill from `deploy` → `manage` |
| `index.html:1440` ("Go to Configuration" — Beacon empty state #1) | inside `beacon` | `configuration` | enable REST API | navigate to Deployments parent + sub-pill `configure` |
| `index.html:1451` ("Go to Configuration" — Beacon empty state #2: REST API not enabled) | inside `beacon` | `configuration` | enable REST API | same |
| `index.html:2133` ("Go to Deploy" — under deployments overview empty) | inside `deployments` | `deployment` | start a deploy | flip sub-pill from `manage` → `deploy` (or `configure` if no project yet) |
| `index.html:2400` ("Go to Deploy Tab" — deployments cost empty) | inside `deployments` | `deployment` | same | same |
| `app.js:8695` ("Open Deployment Manager") | dashboard render | `deployments` | jump to manage | parent tab Deployments + sub-pill `manage` |
| `app.js:8846`, `8856` (same) | dashboard render | `deployments` | same | same |
| `app.js:10129`, `10154`, `10168` ("Go to Pre Reqs") | error states | `aws-check` | trigger prereq check | navigate to Settings → AWS Prereqs anchor |
| `app.js:10143` ("Go to Configuration") | error state | `configuration` | fix config | parent Deployments + sub-pill `configure` |
| `app.js:10899` ("Deploy New Infrastructure →") | dashboard | `deployment` | new deploy | parent Deployments + sub-pill `deploy` |
| `app.js:18771` ("View details in Settings") | cost alert | `settings` | cost breakdown | unchanged |
| `app.js:97` (initial load from URL hash / sessionStorage) | startup | restored page | persist last tab | needs to also restore sub-pill — add `?sub=` query param to hash |
| `app.js:180` (nav-button click) | nav | clicked target | tab switch | also needs sub-pill aware routing |

**14 cross-links total**, of which **11 cross between tabs that will be merged**. None of them break if we add an alias layer: have the old page names (`configuration`, `deployment`, `deployments`) map to `(parentTab="deployments", subPill="configure"|"deploy"|"manage")`. Same for `beacon`, `terminal`, `tools` → `(parentTab="operations", subPill=...)`. One small router. ~30 lines of JS.

### 20.4 Per-tab dropdowns / context selectors
Three tabs duplicate "which deployment am I working on" UI today:
- `beacon-deployment-select` (index.html:1427) — onChange `BEACON.onDeploymentSelected()`
- `terminal-deployment-select` (index.html:2026) — onChange `TERMINAL.onDeploymentSelected()`
- `tools-project-select` (index.html:1287) — onChange triggers `loadToolsConnectionInfo()`

Plus the deployment-creation `deployment-type` selector (line 68) — a *different* concept (picking what TO deploy, not which existing deploy to act on).

**Post-merge:** keep `deployment-type` where it is (it belongs inside Configure sub-pill). Replace the three operational dropdowns with a **single global header selector** that all three Operations sub-views read. `BEACON.onDeploymentSelected`, `TERMINAL.onDeploymentSelected`, and `loadToolsConnectionInfo` become subscribers to a `window.APP.activeDeployment` state change. The three dropdowns themselves can either:
- (a) disappear entirely (header is canonical), or
- (b) become read-only mirrors showing the global selection

Recommend (a) — less confusion, less DOM. The handlers stay; only the trigger source changes.

### 20.5 Empty states — every one (verified)
These must continue to work after the merge:
| ID | Location | Shown when | Post-merge fate |
|---|---|---|---|
| `beacon-no-deployment` (1434) | Beacon | no active deployments at all | Operations → Beacons sub-pill, same message, CTA now goes to Deployments → Configure |
| `beacon-not-enabled` (1445) | Beacon | selected deployment has `enable_rest_api = false` | same, CTA points at Configure sub-pill |
| `beacon-empty-state` (1520) | Beacon table | API works but zero beacons | unchanged |
| `terminal-dep-warning` (2050) | Terminal | no deployment selected | unchanged |
| `cost-empty-state` (2130) | Settings cost section | no deployments to cost | unchanged |
| Deployments overview empty (2133 CTA) | Deployments | no live deployments | CTA stays "Configure new deployment" pointing at Configure sub-pill |
| `cost-empty-state` inside deployments tab (around 2400) | Deployments | same | same |

### 20.6 Tab-leave cleanup — what could leak after a merge
Current `navigateTo()` cleanup logic (app.js:198-222):
```
on leave beacon       → BEACON.stopHealthPoll()
on leave terminal     → TERMINAL.stopBackgroundRefresh()
on leave deployment   → clearInterval(deploymentPollInterval)
on leave deployments  → stopAutoRefresh() + clear destroyPollInterval
```

**Risk after merge:** If user moves Beacon → Terminal *within the Operations tab*, today's leave-cleanup never fires because the parent tab didn't change. BEACON.stopHealthPoll() never runs → background polling continues on a hidden sub-view.

**Fix:** wrap each sub-view in a "sub-view activate / sub-view deactivate" hook that mirrors the current tab-level lifecycle. Specifically:
- on Operations sub-pill change: run the leave-cleanup for the previous sub-pill, run the load-init for the new sub-pill
- on Deployments sub-pill change: same

This is the single thing that takes the merge from "works fine" to "doesn't leak resources." Should be ~50 lines of JS.

### 20.7 Settings tab — what's already there (verified)
Currently in `data-page="settings"` (line 2056):
- `auto-refresh-interval` select (Deployment Manager refresh prefs) — line 2073
- **Cost Tracker section** — buttons, summary cards, budget bar, trend chart, breakdown table, untracked callout, empty state — full cost UI is HERE, not in Deployments
- **Roadmap section** — P1/P2/P3 dev roadmap rendered in-app (interesting that this is in Settings!)
- Theme toggle is in the header, not in Settings

**Implication:** the cost tracker is already in Settings — that's good, our plan was already aligned. The header cost-indicator (Phase 1) just needs to read the same data and link to this existing section.

**Where AWS Pre Reqs goes:** add a new section in Settings *above* Cost Tracker:
- "AWS & SSH Prerequisites" section card with all 5 current checks (`checkSystemDeps`, `checkAWSCredentials`, `checkAWSPermissions`, `checkSSHKey`, `checkGitHubCLI`).
- A first-run hint: on Dashboard load, if any of those have never run / last failed, show a yellow banner "Verify prereqs in Settings →".

**Where Roadmap goes:** honestly, it's odd to ship a dev roadmap as a user-facing tab section. Keep it for now (low-effort to leave alone), but consider moving it to a hidden `?debug=1` toggle later.

### 20.8 What was missed in §19 — additions to the plan

1. **Sub-view lifecycle hooks are required** (§20.6) — the merge isn't just CSS/DOM; it needs ~50 lines of JS to mirror the existing `navigateTo()` cleanup semantics at the sub-pill level. Without this, Beacon polling leaks.
2. **Configuration is 10× more conditional than implied** (§20.2). Don't rewrite — re-parent the whole `tab-page[data-page="configuration"]` subtree under the new Configure sub-pill. Same DOM ids, same handlers.
3. **`loadPageContent()` switch statement** (app.js:267-309) needs to learn about sub-pills. Currently `case 'deployment'` runs 7 functions; in the merged world, *entering Deployments parent tab* should preserve the previously-active sub-pill (e.g., if user was on Manage, stay on Manage; don't always reset to Configure).
4. **URL hash routing already exists partially** (`window.location.hash = pageName` at app.js:257). Extend to `#deployments/configure`, `#operations/beacons`, etc. That gives Phase 6 (bookmarkable URLs) basically for free.
5. **Aliases for backwards-compat** — keep `APP.navigateTo('configuration' | 'deployment' | 'deployments' | 'beacon' | 'terminal' | 'tools' | 'aws-check')` working forever via a tiny alias map. The 14 existing cross-links in §20.3 don't need touching at all if aliases route correctly.
6. **Settings already hosts Cost Tracker** (§20.7). Plan was right; no movement needed. AWS Pre Reqs goes ABOVE Cost Tracker as a new section.
7. **Operator badge** (line 24) is in the header and stays. No change.

### 20.9 Final mapping — every old element → new home

| Old tab | Old DOM id(s) | New parent tab | New sub-pill | Notes |
|---|---|---|---|---|
| Dashboard | `dashboard-status`, Elastic rules card | Dashboard | n/a (single page) | enrich with deployments grid + activity feed (depends on §4 audit) |
| Pre Reqs | `system-deps-status`, `aws-credentials-status`, `aws-permissions-status`, `ssh-key-status`, `github-cli-status` | **Settings** | n/a | new section "AWS & SSH Prerequisites" above Cost Tracker |
| Configuration | full `tab-page[data-page="configuration"]` subtree (lines 61-806) | **Deployments** | **Configure** | re-parent verbatim; `updateDeploymentType()` keeps working |
| Deploy | full `tab-page[data-page="deployment"]` subtree (lines 807-1226) | **Deployments** | **Deploy** | re-parent verbatim; "Edit Config" button just flips sub-pill |
| Deployment Manager | full `tab-page[data-page="deployments"]` subtree (lines 2228-2418) | **Deployments** | **Manage** | re-parent verbatim; `cost-budget-alert` stays here |
| Tools | full `tab-page[data-page="tools"]` subtree (lines 1277-1377) | **Operations** | **Payload upload** | drop per-tab `tools-project-select` (uses global header selector); rename label to "Payloads" |
| Architecture | full `tab-page[data-page="architecture"]` subtree (lines 1378-1419) | **Architecture** | n/a (keep top-level) | unchanged for now |
| Beacon | full `tab-page[data-page="beacon"]` subtree (lines 1420-2010) | **Operations** | **Beacons** | drop per-tab `beacon-deployment-select`; uses global selector |
| Terminal | full `tab-page[data-page="terminal"]` subtree (lines 2011-2055) | **Operations** | **Terminal** | drop per-tab `terminal-deployment-select`; uses global selector |
| Settings | full `tab-page[data-page="settings"]` subtree (lines 2056-2227) | **Settings** | n/a | add AWS Pre Reqs section + Operator profile section + Audit Log Prefs section (Audit section comes once §4 lands) |

### 20.10 Things that could break — gotchas to watch

1. **Polling leaks if sub-view lifecycle hooks aren't added** (§20.6) — ship the hooks in the same PR as the merge.
2. **`deployment-type` change cascades 10+ sections** (§20.2) — never rewrite, only re-parent the Configuration subtree. Verify with a smoke test: pick each of the 11 deployment types and confirm the right sections appear.
3. **`beacon-deployment-select` and `terminal-deployment-select` and `tools-project-select` have onChange handlers** with side-effects — if we delete the elements, we must call the same handlers when the global selector changes. Concretely: `window.APP.activeDeployment.subscribe(d => { BEACON.onDeploymentSelected(d); TERMINAL.onDeploymentSelected(d); loadToolsConnectionInfo(d); })`.
4. **`sessionStorage.setItem('currentPage', pageName)`** (app.js:256) — needs to start storing `pageName + subPill`, else after refresh the user lands on the parent tab but the wrong sub-pill (or no sub-pill, blank screen).
5. **URL hash on direct-link / refresh** — if someone shares `#operations`, where do they land? Default the sub-pill to the last-active one for that tab, or `Beacons` if none.
6. **Cost budget alert is duplicated** — `cost-budget-alert` (line 2238) is inside the Deployments tab AND there's a budget bar in Settings. Keep both — they serve different purposes (alert vs detail).
7. **`refreshAll()` button** (line 2233) is currently scoped to Deployments — after the merge it should still only refresh that sub-pill's data, not also Configure/Deploy.
8. **The 84 `display: none` elements** — none of them are tab-specific styling; they're all state-driven within their parent tab. Re-parenting preserves them all.

### 20.11 Confirmed plan (after sanity check)

The §19 plan stands, **with these refinements:**

- Phase 1 (global header + active-deployment selector) — **unchanged**.
- Phase 2 (Pre Reqs → Settings) — confirmed; goes ABOVE Cost Tracker as new section "AWS & SSH Prerequisites".
- Phase 3 (Configuration + Deploy + Deployment Manager → Deployments) — **add sub-view lifecycle hooks** as part of this phase, not as an afterthought.
- Phase 4 (Beacon + Terminal + Tools → Operations) — confirmed; delete the three per-tab selectors and bind handlers to global active-deployment state.
- Phase 5 (Dashboard upgrade) — confirmed.
- Phase 6 (URL routing) — confirmed; extends the already-existing `window.location.hash = pageName` line.
- **New Phase 0:** add the alias layer (`navigateTo('configuration')` → new home) BEFORE doing any merge. That way Phase 3 and 4 can land independently without touching any of the 14 cross-link call sites.

### 20.12 Order of operations to ship safely

1. **Phase 0 (1-2 hours):** add `NAVIGATE_ALIASES` map + sub-pill awareness to `APP.navigateTo()` and `APP.loadPageContent()`. New routing infra. No DOM changes. No user-visible effect yet.
2. **Phase 1 (half-day):** ship the header with active-deployment selector + cost indicator. Tabs untouched. Per-tab selectors stay (they'll be removed in Phase 4).
3. **Phase 2 (half-day):** move AWS Pre Reqs section into Settings, remove nav button. Nav goes 10 → 9.
4. **Phase 3 (1-2 days):** create "Deployments" parent tab with 3 sub-pills, re-parent the 3 existing tab-page subtrees. Add sub-view lifecycle hooks. Nav goes 9 → 7.
5. **Phase 4 (1-2 days):** create "Operations" parent tab with 3 sub-pills, re-parent the 3 subtrees. Delete the three per-tab dropdowns and wire handlers to global selector. Nav goes 7 → 5.
6. **Phase 5 (depends on §4 audit):** Dashboard upgrade.
7. **Phase 6 (half-day):** sub-pill URL routing (`#operations/beacons?dep=...`).

**Each phase is independently shippable.** If we stop after Phase 3, we have 7 tabs and the dominant Configure→Deploy→Manage flow is already merged. If we stop after Phase 4, we have the final 5-tab layout. Phases 5 and 6 are polish.

