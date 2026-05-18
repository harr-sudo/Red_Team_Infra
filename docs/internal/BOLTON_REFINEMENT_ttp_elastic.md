# Bolt-On Refinement — MITRE ATT&CK TTP + Elastic Detection Rule Tie-In

**Status:** Refinement proposal — extends `VULNERABLE_LAB_BOLTON_PLAN.md`
**Parent doc:** [`VULNERABLE_LAB_BOLTON_PLAN.md`](./VULNERABLE_LAB_BOLTON_PLAN.md)
**Owner:** Red Team Infra dashboard
**Target surface:** vulnerability descriptor schema, dashboard catalog UI, install confirm flow, post-install verification, audit log, Elastic Rules service
**Constraint:** no master-plan edits, no production code shipped with this doc, no commits

---

## 1. Executive summary

The master plan already includes a thin `detection:` block on every vulnerability descriptor (§4.1, lines 496–506), but it only carries free-text rule *names* alongside a `quiet | medium | loud` profile. That is insufficient for the user's stated requirement (2026-05-18):

> *"the vulnerability should be tied to a ttp / elastic — flag when not available"*

This refinement tightens the tie-in by making every bolt-on a **first-class purple-team artifact**:

1. **MITRE ATT&CK chain is mandatory metadata** on every descriptor (Tactic → Technique → Sub-technique), with explicit support for multi-technique mappings and an explicit `none` sentinel for vulns that genuinely don't map to ATT&CK (custom web app CVEs).
2. **Elastic detection rules are referenced by stable UUID** (the `rule_id` field on every TOML in `Research/elastic-detection-rules/rules/`), not by name — names drift, UUIDs don't.
3. **Coverage status is computed from the rule list** and surfaced as a four-state badge: `covered` / `partial` / `no-rule` / `rule-stale`. The worst rule in the list wins; `no-rule` is a prominent red badge.
4. **Coverage is a filter primitive** in the catalog — operators can isolate every bolt-on with no detection rule to deliberately practice red-team work against a gap, or pivot to authoring a detection.
5. **Post-install verification** optionally runs a synthetic exploit probe and queries Elastic for the expected rule firing within a configurable window. Result feeds back into the host's installed-on view: "Detection verified" or "Detection didn't fire — investigate."
6. **Detection gaps become a dedicated dashboard surface** via `GET /api/bolton/detection/gaps`, listing every installed-or-installable bolt-on without Elastic coverage. This is the lab's purple-team backlog.
7. **A `Generate detection rule` flow** seeds a starter Elastic TOML from a per-vuln template (process spawn pattern, registry write, network signature), giving the operator a draft to refine and submit upstream — the framework helps *close* the gap, not just flag it.
8. **MITRE Navigator export** (stretch): the lab's bolt-on inventory exports as a Navigator JSON layer, so the operator gets a heatmap of which techniques are covered, which aren't, and which detection rules apply.

The refinement is purely additive: existing descriptors continue to validate (the new fields default to `mitre: none` and `coverage_status: no-rule`), but the catalog UI surfaces those gaps in red. The schema bump from `schema_version: 1` to `schema_version: 2` is non-breaking — older descriptors are auto-promoted at load time with a warning.

This builds directly on the existing Elastic Rules integration (`webapp/frontend/js/elastic-rules.js`, 128 rules, monthly regen via `scripts/utilities/update-elastic-rules.py`), reusing its rule-fetch pipeline rather than introducing a parallel one.

---

## 2. Schema additions to the vulnerability descriptor

### 2.1 The current `detection:` block (master plan §4.1)

```yaml
detection:
  profile: quiet                            # quiet | medium | loud
  signal_sources:
    - "Windows Event 4720 (User account created)"
    - "Windows Event 5136 (Directory Service object modified — SPN write)"
  elastic_rules_suggested:
    - "Suspicious Service Account Creation"
    - "SPN Modification on User Account"
```

Problems:

- Rules are referenced by *name*, which drifts. The Elastic project renames rules frequently (e.g. `windows_credential_dump` → `credential_access_credential_dumping_via_lsass`).
- No notion of coverage *quality* — a rule that fires on one variant out of three is treated identically to one that fires on all.
- No `last_validated` date — over months, a rule we *think* covers a vuln may have been silently neutered by upstream tuning.
- The `mitre_attack:` block (lines 397–399) is on the descriptor, but it's a separate concern from the detection — the linkage between MITRE technique and rule is implicit.
- No place to point at a fallback rule template when no Elastic rule exists.
- No place to declare a synthetic exploit probe for end-to-end detection verification.

### 2.2 New schema fragment (v2)

```yaml
# ── MITRE ATT&CK chain (mandatory; can be `none` with comment) ─────
mitre:
  # Primary chain — most descriptors have exactly one
  - tactic:
      id: TA0006
      name: "Credential Access"
    technique:
      id: T1558
      name: "Steal or Forge Kerberos Tickets"
    subtechnique:                         # optional — omit if technique has no sub
      id: T1558.003
      name: "Kerberoasting"
    notes: "Primary chain — kerberoastable service account."
  # Multiple entries allowed — see §2.3 worked example 2 (PrintNightmare)

# ── Detection coverage ────────────────────────────────────────────
detection:
  # Existing field — kept
  profile: quiet                          # quiet | medium | loud
  signal_sources:
    - "Windows Event 4769 (Kerberos service ticket requested)"
    - "Windows Event 5136 (Directory Service object modified — SPN write)"

  # NEW — replaces elastic_rules_suggested
  elastic_rules:
    - rule_uuid: "1d276579-3380-4d2a-8b6f-f8d3a7b1e2c4"
      rule_name: "Kerberoasting via Service Ticket Request"
      rule_filename: "credential_access_kerberoasting_unusual_process.toml"
      coverage: full                      # full | partial | indirect
      confidence: high                    # high | medium | low
      last_validated: "2026-04-15"        # ISO date; freshness check uses this
      notes: "Catches RC4-encrypted TGS requests by non-svc accounts."
    - rule_uuid: "897dc6b5-b39f-432a-8d75-d3730d50c782"
      rule_name: "Suspicious Service Account Modification"
      rule_filename: "credential_access_suspicious_svc_modification.toml"
      coverage: indirect
      confidence: medium
      last_validated: "2026-04-15"
      notes: "Catches the SPN-write side of the install, not the roast itself."

  # NEW — computed at load time from elastic_rules; can be overridden
  coverage_status: covered                # covered | partial | no-rule | rule-stale

  # NEW — pointer to a starter template if no Elastic rule exists
  fallback_rule_template: null            # e.g. "../elastic-rules/templates/kerberoasting.yml"

# ── NEW: synthetic exploit probe for E2E detection verification ───
exploit:
  trigger_probe:                          # optional — gates post-install detection check
    description: "Roast the SPN from the attack box; verify Elastic rule fires within 5min."
    engine: bash                          # bash | powershell | cs_beacon
    runner: attack_box                    # attack_box | jumpbox | beacon
    command: |
      impacket-GetUserSPNs -dc-ip {{ dc_ip }} {{ domain_fqdn }}/{{ test_user }}:{{ test_password }} -request
    expect_in_stdout: "$krb5tgs$"
    detection_window_seconds: 300         # how long to wait for Elastic alert
    expect_rule_uuids:                    # which UUIDs from detection.elastic_rules must fire
      - "1d276579-3380-4d2a-8b6f-f8d3a7b1e2c4"
```

**Field semantics.**

| Field | Meaning |
|---|---|
| `mitre[].tactic` | TA-prefixed ATT&CK tactic. `id` is the source of truth; `name` is for display. |
| `mitre[].technique` | T-prefixed technique without sub-suffix (e.g. `T1558`). |
| `mitre[].subtechnique` | T-prefixed with sub-suffix (`T1558.003`). Omit entirely if the technique has no sub. |
| `mitre: none` | Sentinel for vulns that genuinely don't map (custom web app, novel cred-store). `notes` required when `none`. |
| `detection.elastic_rules[].rule_uuid` | The TOML's `rule_id` field — UUID, stable across renames. **Source of truth.** |
| `detection.elastic_rules[].rule_filename` | Convenience — points at the TOML in `Research/elastic-detection-rules/rules/`. Lookup table at load time validates the UUID. |
| `coverage` | Per-rule: `full` (catches this exact vuln), `partial` (catches some variants), `indirect` (related but might miss). |
| `confidence` | Operator-set: how confident we are this rule will actually fire. Decays over time. |
| `last_validated` | ISO date. If `today - last_validated > 90 days`, rule is auto-flagged `rule-stale`. |
| `coverage_status` | Computed (worst-rule-wins, see §3.1). Optional override for edge cases. |
| `fallback_rule_template` | Path to a YAML/TOML starter that the "Generate detection rule" flow seeds from. |
| `exploit.trigger_probe` | Optional. If present, runs after install and queries Elastic for alert firing. |
| `expect_rule_uuids` | Subset of `elastic_rules[].rule_uuid` that MUST fire within the window for the probe to pass. |

### 2.3 Three worked examples

**Example 1 — 1:1 mapping (Kerberoastable Service Account).**

```yaml
id: bolton.identity.kerberoastable-svc
mitre:
  - tactic:       { id: TA0006, name: "Credential Access" }
    technique:    { id: T1558,  name: "Steal or Forge Kerberos Tickets" }
    subtechnique: { id: T1558.003, name: "Kerberoasting" }
detection:
  profile: quiet
  elastic_rules:
    - rule_uuid: "1d276579-3380-4d2a-8b6f-f8d3a7b1e2c4"
      rule_name: "Kerberoasting via Service Ticket Request"
      rule_filename: "credential_access_kerberoasting_unusual_process.toml"
      coverage: full
      confidence: high
      last_validated: "2026-04-15"
  coverage_status: covered
exploit:
  trigger_probe:
    runner: attack_box
    engine: bash
    command: "impacket-GetUserSPNs -request ..."
    detection_window_seconds: 300
    expect_rule_uuids: ["1d276579-3380-4d2a-8b6f-f8d3a7b1e2c4"]
```

**Example 2 — multi-technique mapping (PrintNightmare).**

```yaml
id: bolton.cve.printnightmare
mitre:
  - tactic:       { id: TA0004, name: "Privilege Escalation" }
    technique:    { id: T1068,  name: "Exploitation for Privilege Escalation" }
    notes: "CVE-2021-1675 / -34527 lpEx PE primitive."
  - tactic:       { id: TA0005, name: "Defense Evasion" }
    technique:    { id: T1574,  name: "Hijack Execution Flow" }
    subtechnique: { id: T1574.001, name: "DLL Search Order Hijacking" }
    notes: "Spooler loads the dropped DLL out of a writable path."
detection:
  profile: loud
  elastic_rules:
    - rule_uuid: "5cc6efb3-89f0-4f25-b4f6-b3a1c2d4e5f6"
      rule_name: "Print Spooler Suspicious File Deletion"
      rule_filename: "privilege_escalation_print_spooler_suspicious_file_deletion.toml"
      coverage: full
      confidence: high
      last_validated: "2026-04-15"
    - rule_uuid: "9a0d8e7c-1234-5678-9abc-def012345678"
      rule_name: "Suspicious DLL Loaded by spoolsv.exe"
      rule_filename: "defense_evasion_spoolsv_dll_load.toml"
      coverage: partial
      confidence: medium
      last_validated: "2026-04-15"
      notes: "Catches the DLL-load angle. Misses the registry-write variants."
  coverage_status: partial                # because one rule is `partial`
```

**Example 3 — no-mapping (custom web app CVE).**

```yaml
id: bolton.webapp.custom-deserialization
name: "Custom Java Deserialization (Internal App)"
mitre: none
mitre_notes: "Internal proprietary app; no published ATT&CK technique covers this exact path."
detection:
  profile: medium
  elastic_rules: []
  coverage_status: no-rule
  fallback_rule_template: "../elastic-rules/templates/java-deserialization.yml"
  # ^ when operator clicks "Generate detection rule", this template is the seed
```

### 2.4 Migration / back-compat

- Existing v1 descriptors with `mitre_attack:` (master plan §4.1, lines 397–399) and `elastic_rules_suggested:` (line 503) are auto-migrated at load time:
  - `mitre_attack` → `mitre` (tactic+technique only; subtechnique left empty)
  - `elastic_rules_suggested` (names) → `elastic_rules` (with `rule_uuid: null`, `coverage_status: rule-stale`, warning emitted)
- A migration script `scripts/bolton/migrate_descriptors_v1_to_v2.py` is provided. Operators run it once.
- The JSON schema at `bolton/schema/v2.json` validates the new shape. Schema v1 remains valid but emits a deprecation warning.

---

## 3. Coverage states + visual treatment per state

### 3.1 Computation rule (worst-rule-wins)

```
function compute_coverage_status(rules: List<ElasticRuleRef>) -> CoverageStatus
  if rules is empty:
    return no-rule
  if any rule.last_validated older than 90 days:
    return rule-stale
  worst_coverage = min(rules, by: severity_order(coverage))
  if worst_coverage == full:    return covered
  if worst_coverage == partial: return partial
  if worst_coverage == indirect: return partial   # treat indirect-only as partial
```

The descriptor's explicit `coverage_status` overrides the computation for edge cases (e.g. operator manually downgrades a `full` rule they don't trust).

### 3.2 Four states, visual treatment

| State | Pill color | Icon | Label | When |
|---|---|---|---|---|
| `covered` | green (`--success`) | check | "Detection: covered — N Elastic rule(s)" | All rules are `full`, freshness OK |
| `partial` | amber (`--warning`) | half-circle | "Detection: partial — may miss variants" | Any rule is `partial` or `indirect`, freshness OK |
| `no-rule` | **red prominent** (`--danger`, slightly larger pill) | warning triangle | "**No detection coverage — exploit would go unnoticed**" | `elastic_rules: []` |
| `rule-stale` | orange (`--accent-warning`) | clock | "Rule unvalidated > 90 days — refresh" | Any rule's `last_validated` is stale |

**CSS variables** (existing in `webapp/frontend/css/palette.css`):

- Use `--success` / `--warning` / `--danger` for pill backgrounds.
- Text is `--text-primary` on light pills, `--text-inverse` on red `no-rule` for AA contrast.
- The `no-rule` pill uses `.spec-pill--danger` modifier — a new modifier; slightly larger padding (10px vs 6px) and an icon prefix to make it impossible to miss in a scrolling catalog.

### 3.3 Light-mode safety (per CLAUDE.md)

- All four colors are pulled from `palette.css`, never inline hex.
- `--success` / `--warning` / `--danger` already resolve to sufficient contrast (>= 4.5:1) on both `--bg-card` and `--bg-card-hover` in both themes — verified in current `style.css` semantic-color audit.
- The `no-rule` red pill MUST be tested in light mode — if `--danger` resolves to a muted brick in light theme, the pill loses prominence. Add a `[data-theme="light"] .spec-pill--danger { background: var(--danger-vivid); color: var(--text-inverse); }` rule.

---

## 4. UI surfaces where TTP + detection info appears

All five surfaces reuse Phase 2b TASTE V3 primitives — `.spec-list`, `.spec-row`, `.spec-pill`, `.scrim-takeover`, `.takeover-card` — confirmed present in `webapp/frontend/css/style.css` (lines 6083–6139).

### 4.1 Catalog card (per vulnerability tile)

Existing layout from master plan §8.1, with a coverage badge added inline next to the category pill.

```html
<article class="spec-row spec-row--catalog-card" draggable="true"
         data-bolton-id="bolton.identity.kerberoastable-svc">
  <header class="spec-row__head">
    <span class="spec-row__value">Kerberoastable Svc</span>
    <span class="spec-pill spec-pill--category">identity-kerberos</span>
    <!-- NEW — coverage badge inline -->
    <span class="spec-pill spec-pill--success" title="Covered by 2 Elastic rules">
      <svg class="icon icon--check"></svg> T1558.003
    </span>
  </header>
  <p class="spec-row__hint">DC · 30s · quiet · deps: 1</p>
</article>
```

For `no-rule` state, the badge replaces the technique label with **"NO DETECTION"** in `--danger` red.

### 4.2 Catalog filter chip — Coverage filter

Existing master-plan filters (`Category`, `Target`, `Complexity`, `Search`) get a fifth filter:

```
Filters: [Category ▾] [Target ▾] [Complexity ▾] [Coverage ▾] [Search …]
                                                 │
                                                 └ All | Covered | Partial | No-rule | Stale
```

Multi-select. Filter state is encoded in the URL query string (`?coverage=no-rule,partial`) for share-linking — useful for screenshotting "here are all the bolt-ons we have no detection for, let's fix that this sprint."

### 4.3 Detail modal (`.scrim-takeover` + `.takeover-card`)

Opens when the catalog card is clicked. Layout:

```
┌─────────────────────── VULNERABILITY DETAIL ──────────────────────────┐
│ Kerberoastable Service Account                                  [×]   │
│ bolton.identity.kerberoastable-svc · v1.0.0                           │
├───────────────────────────────────────────────────────────────────────┤
│ MITRE ATT&CK CHAIN                                                    │
│                                                                       │
│   Credential Access (TA0006)                                          │
│     └─ Steal or Forge Kerberos Tickets (T1558) ↗                      │
│         └─ Kerberoasting (T1558.003) ↗                                │
│                                                                       │
│   [view on attack.mitre.org ↗]                                        │
├───────────────────────────────────────────────────────────────────────┤
│ DETECTION COVERAGE                  [● COVERED]                       │
│                                                                       │
│   .spec-list                                                          │
│     .spec-row                                                         │
│       Rule: Kerberoasting via Service Ticket Request                  │
│       UUID: 1d276579…b1e2c4  [copy]  [view source ↗]                  │
│       Coverage: full · Confidence: high · Validated: 2026-04-15       │
│       "Catches RC4-encrypted TGS requests by non-svc accounts."       │
│     .spec-row                                                         │
│       Rule: Suspicious Service Account Modification                   │
│       UUID: 897dc6b5…c50c782  [copy]  [view source ↗]                 │
│       Coverage: indirect · Confidence: medium · Validated: 2026-04-15 │
│                                                                       │
│   [Run synthetic probe]  [Show in Elastic Rules UI ↗]                 │
├───────────────────────────────────────────────────────────────────────┤
│ … rest of descriptor (deps, conflicts, side effects, inputs) …       │
└───────────────────────────────────────────────────────────────────────┘
```

- MITRE chain is a tree. Each level is a separate `.spec-row` with external-link icon to `https://attack.mitre.org/tactics/<id>/` etc.
- Detection coverage section is a `.spec-list` of `.spec-row` per rule.
- UUID is mono-font with `.spec-row__value--mono` modifier, plus a copy-to-clipboard button.
- "view source" link opens the TOML file in the existing GitHub viewer (the Elastic Rules UI already has this — reuse).
- "Show in Elastic Rules UI" links into the existing OPSEC integration, pre-filtered by `rule_uuid`.

For `no-rule` state, the detection section becomes:

```
DETECTION COVERAGE                  [▲ NO DETECTION]

  No Elastic rule covers this vulnerability.
  Fallback template available: java-deserialization.yml

  [Generate detection rule from template]  [Mark as won't-fix]
```

### 4.4 Install confirm modal (drag-drop → install)

Existing modal from master plan §8.3, with a new "Detection" line:

```
┌────────────────── CONFIRM INSTALL ──────────────────────┐
│ ADCS ESC1 → ca01                                        │
├─────────────────────────────────────────────────────────┤
│ DEPENDENCIES (will be installed first):                 │
│   ✓ bolton.adcs.install-adcs            (ca01, 4m)      │
├─────────────────────────────────────────────────────────┤
│ MITRE: T1649 — Steal or Forge Authentication Certificates │
│ DETECTION: ● Covered by 1 Elastic rule (full, high)     │
├─────────────────────────────────────────────────────────┤
│ INPUTS:                                                 │
│   …                                                     │
├─────────────────────────────────────────────────────────┤
│ DETECTION PROFILE: quiet                                │
│ EST. INSTALL TIME: ~5 minutes                           │
│                                                         │
│ [✓] Run synthetic exploit probe after install (5min)    │
├─────────────────────────────────────────────────────────┤
│           [Cancel]   [Plan only]   [Install ▸]          │
└─────────────────────────────────────────────────────────┘
```

For `no-rule` state, a red banner above the inputs:

```
┌─────────────────────────────────────────────────────────┐
│ ▲ NO DETECTION COVERAGE                                 │
│   This vulnerability has no Elastic detection rule.     │
│   Exploitation will go unnoticed in normal monitoring.  │
│   Proceed only if this is a red-team exercise where     │
│   detection gap is intentional.                         │
│                                                         │
│   [Generate detection rule first]                       │
└─────────────────────────────────────────────────────────┘
```

The "Install" button stays enabled — the operator can still proceed — but the confirmation flow now requires checking a "I understand this has no detection coverage" checkbox first.

### 4.5 Post-install verification

Triggered when `exploit.trigger_probe` is defined AND operator checked the "Run synthetic probe" box.

Flow:

1. Install completes successfully.
2. Backend runs `exploit.trigger_probe.command` on the configured runner (`attack_box`, `jumpbox`, or via CS beacon — `cs_beacon` is forward-compat for v2).
3. Backend polls Elastic alerts API for `detection_window_seconds` (default 300s) looking for any of `expect_rule_uuids` firing on the target host.
4. Results displayed in the install progress modal's bottom section:

```
┌────────── POST-INSTALL DETECTION VERIFICATION ───────────┐
│ Probe: impacket-GetUserSPNs -request …                   │
│ Probe ran on: attack_box (ip: 10.0.1.20)                 │
│                                                          │
│ Expected rule firings:                                   │
│   1d276579-3380-4d2a-8b6f-f8d3a7b1e2c4                   │
│                                                          │
│ Waiting for Elastic alerts … (4:32 remaining)            │
│   ●●●●●○○○○○ alerts received: 0                          │
└──────────────────────────────────────────────────────────┘
```

On completion, three outcomes:

- **Detection verified** — green: "Elastic rule fired within 1m 12s. Detection: ✓"
- **Detection didn't fire** — red: "No matching Elastic alert within 5min. Detection regression suspected — open issue?" (with a one-click "Open issue against detection-rules repo" button)
- **Probe failed** — neutral: "Probe didn't produce expected output. Install state OK, detection unverified."

The result is recorded on the installed-on view as a small `.spec-pill`:

- `[● Detection verified 2026-05-18]` (green)
- `[▲ Detection didn't fire 2026-05-18]` (red, clickable to re-run)
- `[○ Detection not verified]` (gray, default)

### 4.6 Audit log entries

Existing audit service in `webapp/backend/routes/audit.py` writes entries via `audit_service.write(actor, action, details)`. Each bolt-on install/uninstall/probe event includes the MITRE technique in `details`:

```json
{
  "ts": "2026-05-18T14:32:09Z",
  "actor": "alice@example.com",
  "action": "bolton.install",
  "details": {
    "vuln_id": "bolton.identity.kerberoastable-svc",
    "vuln_name": "Kerberoastable Service Account",
    "mitre_technique": "T1558.003",
    "mitre_tactic": "TA0006",
    "host": "dc01-domain1",
    "lab": "goad-light-eng1",
    "coverage_status": "covered",
    "elastic_rule_count": 2,
    "probe_result": "verified"
  }
}
```

The activity feed renders these as:

> 14:32 — **alice** installed **T1558.003 Kerberoasting** on dc01-domain1 *(detection verified)*

Clicking the technique ID links to the detail modal pre-scrolled to the detection section.

### 4.7 Detection-gaps dashboard widget

A dedicated section under the existing GOAD section nav: **Detection Gaps** (sub-pill alongside `Catalog`, `Scenarios`, `Topology`, `Installed`, `Audit`).

Shows three counters at top:

```
┌──────────────────────────────────────────────────────────┐
│  COVERAGE OVERVIEW                                       │
│                                                          │
│   12  Covered    3  Partial    5  No-rule    2  Stale    │
└──────────────────────────────────────────────────────────┘
```

Below, a `.spec-list` of bolt-ons grouped by coverage state, with row-level actions:

- `no-rule` → `[Generate detection rule]` `[Mark won't-fix]`
- `partial` → `[View rule(s)]` `[Improve coverage]`
- `rule-stale` → `[Mark validated today]` `[View rule(s)]`

This widget is the operator's purple-team backlog.

---

## 5. Backend integration

### 5.1 New endpoints

Added to the existing `/api/bolton` blueprint (master plan §9, `webapp/backend/routes/bolton.py`).

| Method | Path | Purpose | Request | Response |
|---|---|---|---|---|
| GET | `/api/bolton/vulns/<id>/coverage` | Detection coverage detail for one vuln | — | `{ coverage_status, rules: [...], mitre: [...], probe_history: [...] }` |
| POST | `/api/bolton/vulns/<id>/probe` | Run synthetic exploit + Elastic poll | `{ host, lab, window_seconds? }` | `{ probe_job_id }` |
| GET | `/api/bolton/probes/<probe_job_id>` | Probe status + alert correlation | — | `{ status, probe_stdout, alerts_received: [...], result: verified \| no-alert \| probe-failed }` |
| GET | `/api/bolton/detection/gaps` | All bolt-ons without coverage | query: `state=no-rule\|partial\|stale, lab?` | `{ gaps: [{ vuln_id, name, coverage_status, fallback_template? }], summary: { covered, partial, no_rule, stale } }` |
| POST | `/api/bolton/vulns/<id>/generate-rule` | Seed draft Elastic rule from template | `{ rule_inputs?: {} }` | `{ draft_rule_toml: "...", template_used, github_pr_url? }` |
| GET | `/api/bolton/coverage/navigator-layer` | Export MITRE Navigator JSON | query: `lab?, installed_only=bool` | `{ layer: <navigator_layer_json> }` |

### 5.2 Integration with the existing Elastic rules service

Existing artifact: `webapp/frontend/js/elastic-rules.js` (5829 lines, 128 rules, generated by `scripts/utilities/update-elastic-rules.py` from `Research/elastic-detection-rules/`).

Refactor: split into a backend service + a thin frontend exporter, both reading the same source of truth.

**New backend service** at `webapp/backend/services/elastic_rules_service.py`:

```python
class ElasticRulesService:
    def __init__(self, rules_root: Path):
        self.rules_root = rules_root  # Research/elastic-detection-rules/rules/
        self._index = self._build_index()  # uuid -> {name, filename, mitre, severity, ...}

    def get_by_uuid(self, rule_uuid: str) -> dict | None: ...
    def get_by_uuids(self, rule_uuids: list[str]) -> list[dict]: ...
    def validate_uuid(self, rule_uuid: str) -> bool: ...
    def find_by_technique(self, technique_id: str) -> list[dict]: ...
    def freshness_days(self, rule_uuid: str) -> int: ...  # vs file mtime
```

The service builds an index at startup by walking `Research/elastic-detection-rules/rules/**/*.toml`, parsing the TOML `rule_id`, `name`, `severity`, `risk_score`, MITRE annotations, and file mtime. Cached in memory; rebuilt on SIGHUP or when the regen script runs.

**Frontend keeps its existing OPSEC view** but pulls rule data from `GET /api/elastic-rules/<uuid>` (new endpoint) instead of the embedded JS object. The 5829-line embedded data file becomes a fallback for offline mode or can be deprecated entirely. The choice is left to a follow-up — this refinement only requires the *backend* service to exist.

**The bolt-on coverage endpoint composes both:**

```python
@bp.route("/api/bolton/vulns/<vuln_id>/coverage")
def coverage(vuln_id):
    desc = descriptor_service.load(vuln_id)
    rules = elastic_rules_service.get_by_uuids(
        [r["rule_uuid"] for r in desc.detection.elastic_rules]
    )
    # Merge: descriptor's coverage/confidence/notes + Elastic's name/severity/mitre
    enriched = [
        {**desc_rule, **rules_index[desc_rule["rule_uuid"]]}
        for desc_rule in desc.detection.elastic_rules
    ]
    return jsonify({
        "coverage_status": compute_coverage_status(enriched),
        "rules": enriched,
        "mitre": desc.mitre,
        "probe_history": probe_service.history(vuln_id, host=request.args.get("host")),
    })
```

### 5.3 Probe execution

`POST /api/bolton/vulns/<id>/probe`:

1. Backend resolves the runner — `attack_box` IP from Terraform output, `jumpbox` likewise, `cs_beacon` from beacon service (v2).
2. Backend SSHes to the runner, executes the `trigger_probe.command` with rendered Jinja vars (`{{ dc_ip }}`, `{{ test_user }}`, etc. — sourced from lab inventory).
3. Captures stdout, checks `expect_in_stdout`.
4. Records probe start time.
5. Polls Elastic alerts API (`POST /api/detection_engine/signals/search` or similar — depends on whether the operator has Elastic stood up; this refinement does *not* require an Elastic deployment, only the schema and UI to support it when present) for any alerts where `kibana.alert.rule.rule_id` is in `expect_rule_uuids` AND `host.name` matches, within `detection_window_seconds`.
6. Reports back via the probe-job endpoint.

**If no Elastic instance is configured**, the probe still runs but skips the alert-correlation step and reports `result: probe-only` instead of `verified`. The UI surfaces this honestly: "Probe ran successfully but no Elastic instance to correlate against."

### 5.4 Audit integration

Per master plan §9.1, every state-changing route writes via `audit_service.write(actor, action, details)`. Bolt-on routes write actions:

- `bolton.install` — details include `mitre_technique`, `coverage_status`, `elastic_rule_count`
- `bolton.uninstall` — same metadata
- `bolton.probe` — details include `probe_result` and any fired rule UUIDs
- `bolton.generate_rule` — details include `template_used` and where the draft was written
- `bolton.coverage_override` — when an operator manually marks `coverage_status`

The activity feed filter is extended with a `mitre_technique` filter chip — operators can answer "show me everything that's ever touched T1558.003 in this lab."

---

## 6. Source-of-truth + update process

### 6.1 The descriptor is the source of truth for the mapping

- The `mitre:` and `detection.elastic_rules:` blocks live in the YAML descriptor, version-controlled in `bolton/catalog/`.
- The Elastic rule TOMLs themselves (`Research/elastic-detection-rules/rules/`) are the source of truth for rule *content* (the actual KQL query, what it fires on).
- The descriptor cross-references rules by UUID; the backend service resolves UUIDs to rule metadata at runtime.

### 6.2 Update cadence

| Trigger | Action | Owner |
|---|---|---|
| Monthly | `git -C Research/elastic-detection-rules pull && python3 scripts/utilities/update-elastic-rules.py` | Existing automation, extended to also validate that every descriptor's `rule_uuid` still resolves to an extant rule |
| MITRE publishes new technique | Affected descriptors get a PR; `mitre:` updated; old technique kept in `mitre_legacy:` for one release | Descriptor maintainer (operator) |
| Elastic renames a rule | UUID unchanged → no descriptor change needed; the lookup keeps working. The `rule_name` field on the descriptor is updated on the next monthly regen | Automation |
| Elastic deprecates a rule | The monthly script detects the UUID is no longer in the index, flags all referring descriptors with a warning, sets `coverage_status: rule-stale` | Automation + operator triage |
| Descriptor adds a new vuln | Author chooses MITRE chain manually; if no Elastic rule exists, `coverage_status: no-rule`, and they're encouraged to create the `fallback_rule_template` | Descriptor author |
| Quarterly | Re-validate `last_validated` dates on all `elastic_rules[]`; bulk-update via a CI job that re-runs probes against a clean lab | Maintenance |

### 6.3 CI validation

A new CI job `validate-bolton-coverage` runs on every PR touching `bolton/catalog/`:

1. Schema-validates every descriptor against `bolton/schema/v2.json`.
2. For every `rule_uuid`, confirms it resolves in the current Elastic rules index.
3. For every MITRE `T*` / `TA*` ID, validates against a vendored MITRE ATT&CK STIX bundle (`bolton/mitre/enterprise-attack.json`, refreshed quarterly).
4. Confirms `coverage_status` matches the worst-rule-wins computation (or has an explicit override comment).
5. Confirms `expect_rule_uuids` is a subset of `elastic_rules[].rule_uuid`.

Failures block merge.

---

## 7. Fallback rule templates + the "Generate detection rule" flow

### 7.1 Templates live in the repo

Templates live under `bolton/elastic-rules/templates/`. Each template is a partial Elastic TOML with placeholders:

```toml
# bolton/elastic-rules/templates/kerberoasting.yml.j2
[metadata]
creation_date = "{{ today }}"
maturity = "development"
updated_date = "{{ today }}"

[rule]
author = ["Red Team Infra Bolt-On Framework"]
description = "{{ vuln_name }} — auto-generated draft."
name = "{{ rule_name_suggestion }}"
risk_score = {{ risk_score | default(47) }}
rule_id = "{{ new_uuid }}"
severity = "{{ severity | default('medium') }}"
type = "eql"

query = '''
sequence by host.id with maxspan=5m
  [process where event.action == "started" and process.name : "{{ trigger_process | default('*.exe') }}"]
  [authentication where event.outcome == "success" and event.action == "logged-in"
     and winlog.event_data.TicketEncryptionType in ("0x17", "0x18")]
'''

[[rule.threat]]
framework = "MITRE ATT&CK"

  [rule.threat.tactic]
  id   = "{{ tactic_id }}"
  name = "{{ tactic_name }}"
  reference = "https://attack.mitre.org/tactics/{{ tactic_id }}/"

  [[rule.threat.technique]]
  id   = "{{ technique_id }}"
  name = "{{ technique_name }}"
  reference = "https://attack.mitre.org/techniques/{{ technique_id }}/"
```

Templates are *seeded* by the framework but *refined* by the operator — they're starting points, not finished rules.

### 7.2 The flow

When the operator clicks **Generate detection rule from template** (in the detail modal or detection-gaps dashboard):

1. Frontend POSTs to `/api/bolton/vulns/<id>/generate-rule` with optional input overrides.
2. Backend:
   - Loads the descriptor, extracts MITRE chain (must be set; refuse if `mitre: none` without explicit override).
   - Loads `fallback_rule_template` (or falls back to a generic template per `category` if not set).
   - Renders the Jinja template with:
     - `today` → ISO date
     - `vuln_name`, `mitre.tactic.id`, `mitre.technique.id`, `mitre.technique.name`, etc. from the descriptor
     - `new_uuid` → freshly generated UUIDv4
     - `trigger_process`, `risk_score`, `severity` → from descriptor or sane defaults
3. Returns the rendered TOML in the response body.
4. Frontend offers three actions:
   - **Copy to clipboard** — paste into local detection-rules workspace
   - **Download .toml** — single-file download
   - **Open draft PR upstream** — uses the `gh` CLI (already required per CLAUDE.md prereqs) to create a draft PR against `elastic/detection-rules` with the new file. The PR title is `[draft] T<technique>: <vuln_name> — auto-generated by bolt-on framework`. Body includes the descriptor's vuln_id and a note that the rule was AI-seeded and needs human review.

### 7.3 What templates we ship in v1

Eight starter templates covering the common detection-gap patterns from the master plan §3 taxonomy:

| Template | Covers | MITRE focus |
|---|---|---|
| `kerberoasting.yml.j2` | TGS request anomalies | T1558.003 |
| `adcs-template-enroll.yml.j2` | Suspicious cert enrollment | T1649 |
| `gpp-cpassword.yml.j2` | Group Policy XML reads | T1552.006 |
| `printnightmare.yml.j2` | Spooler DLL load | T1068 + T1574.001 |
| `dll-hijack.yml.j2` | Process load of writable-path DLL | T1574.001 |
| `web-app-deserialization.yml.j2` | Java/PHP deserialization | T1190 |
| `coerce-petitpotam.yml.j2` | MS-EFSRPC coercion | T1187 |
| `ntlm-relay.yml.j2` | SMB-to-LDAP relay patterns | T1557.001 |

### 7.4 What this is NOT

Not a substitute for a security engineer reviewing the rule. The generated TOML is a **draft** — the operator must:

- Tune the EQL/KQL query to their environment
- Validate the rule against benign traffic to avoid FPs
- Run the existing Elastic CI (`detection-rules` repo has its own validation suite)
- Have it reviewed before submitting upstream

The framework's value is removing the "blank page" problem — from "no rule exists" to "here's a 70%-correct first draft."

---

## 8. MITRE Navigator export (stretch goal)

### 8.1 What it produces

`GET /api/bolton/coverage/navigator-layer?lab=<lab>&installed_only=true` returns a [MITRE Navigator layer JSON](https://github.com/mitre-attack/attack-navigator):

```json
{
  "name": "goad-light-eng1 — Bolt-On Coverage",
  "versions": { "attack": "14", "navigator": "4.9", "layer": "4.4" },
  "domain": "enterprise-attack",
  "description": "Auto-generated by Red Team Infra Bolt-On Framework — installed bolt-ons mapped to ATT&CK techniques, colored by Elastic detection coverage.",
  "techniques": [
    {
      "techniqueID": "T1558.003",
      "score": 100,
      "color": "#2ecc71",
      "comment": "bolton.identity.kerberoastable-svc — covered by 2 Elastic rules",
      "enabled": true,
      "metadata": [
        { "name": "vuln_id", "value": "bolton.identity.kerberoastable-svc" },
        { "name": "coverage_status", "value": "covered" },
        { "name": "elastic_rule_uuids", "value": "1d276579…,897dc6b5…" }
      ]
    },
    {
      "techniqueID": "T1068",
      "score": 50,
      "color": "#f39c12",
      "comment": "bolton.cve.printnightmare — partial coverage",
      "enabled": true
    }
  ],
  "gradient": { "colors": ["#ff0000", "#f39c12", "#2ecc71"], "minValue": 0, "maxValue": 100 }
}
```

Scoring: `covered=100`, `partial=50`, `no-rule=0`, `rule-stale=25`.

### 8.2 How operators use it

1. Hit the endpoint, get JSON.
2. Open https://mitre-attack.github.io/attack-navigator/ in browser.
3. "Open Existing Layer" → upload JSON.
4. Visual heatmap of which techniques the lab covers, colored by detection state.

The dashboard surfaces a button **"Open in MITRE Navigator"** on the detection-gaps widget — clicking generates the JSON, hosts it via a short-lived signed URL, and opens Navigator pre-loaded.

### 8.3 Scope

- **In v1**: produce the JSON; operator manually opens Navigator.
- **In v2**: embed Navigator iframe in the dashboard for inline viewing (the project is MIT-licensed and self-hostable).
- **Out of scope**: editing the layer back to descriptors — Navigator is read-only in our flow.

---

## 9. Open questions

1. **Where does the Elastic alerts API live in our deployment?** This refinement assumes the operator has a Kibana / Elastic Security instance reachable from the dashboard backend. If not (most engagements probably don't), the post-install probe degrades to `probe-only` mode. Open product question: do we ship a minimal Elastic deployment as an *optional* bolt-on lab component for purple-team scenarios?

2. **Rule UUID stability — what if Elastic rotates them?** Currently the `rule_id` field in detection-rules TOMLs is treated as stable by upstream policy, but there is no contractual guarantee. If they ever break it, we'd need to fall back to filename-based lookup. The CI validator catches drift; mitigation strategy needs documenting.

3. **Multi-rule "OR" vs "AND" semantics for `expect_rule_uuids`.** Current draft treats it as "any one fires = verified." Should we support "all must fire"? Most use cases are OR, but layered defenses (e.g. ESC1 — both the enrollment AND the use of the cert should alert) might want AND. Probably add a `mode: any | all` field.

4. **Should `no-rule` block installs by default?** Master plan §12 risk #3 already flagged this. Current refinement says no (operator can proceed with a checkbox), but a configurable `bolton.config.block_no_rule_installs: true` could be exposed for strict purple-team environments.

5. **MITRE technique deprecation handling.** Some techniques (e.g. T1208 legacy Kerberoasting → T1558.003) have been superseded. Should `mitre_legacy:` be machine-checked against a deprecation list, or just left as documentation? Probably the former — bundled `mitre/deprecations.json`.

6. **"Generate detection rule" — what about non-Elastic SIEMs?** Templates are Elastic-flavored TOMLs today. Operators on Splunk / Sentinel / Chronicle would want their own templating. Out of scope for v1, but the template engine should be SIEM-agnostic-ready (template format is the only thing that's Elastic-specific; the rendering pipeline is generic).

7. **Probe results — where do they live?** Per-probe results need persistence for the "Detection verified 2026-05-18" pill on installed-on view. Suggest `webapp/state/bolton/probes/<vuln_id>__<host>.jsonl` (append-only log) — single source for the activity feed and the inline pill.

8. **Performance — rebuilding the Elastic rules index on every backend start.** With 469+ rules per the existing OPSEC integration, a cold parse of every TOML on startup is non-trivial. Cache the index to `webapp/state/elastic-rules-index.json` keyed by directory mtime; rebuild only when stale. Existing `update-elastic-rules.py` already does similar work — share the index format.

9. **Audit log size growth.** Adding `mitre_technique` to every audit event is fine, but if we add `elastic_rule_uuids` (could be a list of 5+ UUIDs per event), audit JSONL files balloon. Suggest: keep audit entries small (just the technique), and fetch rule UUIDs on-demand via the coverage endpoint when rendering.

10. **Operator confusion — "covered" doesn't mean "secure."** The framework's UI says `[● Covered]` which an operator might read as "this vuln is safe to install because it'll be caught." That's true *only if* the operator's Elastic instance has the rule enabled AND tuned. Mitigation: tooltip on every `covered` badge — "Detection coverage means an Elastic rule exists. It does not mean your monitoring stack has it deployed."

---

## 10. Summary

This refinement converts every vulnerability bolt-on from a red-team toy into a purple-team artifact. The schema additions are non-breaking, the UI changes reuse existing primitives, and the backend integration extends the already-monthly Elastic rules pipeline. The four coverage states give operators an at-a-glance signal of detection posture; the "Generate detection rule" flow closes the gap when needed; MITRE Navigator export wraps the lab's coverage into a portable heatmap.

The single most important property: **every install decision now surfaces detection status before the operator commits.** No vuln gets installed without the operator knowing whether their monitoring stack will see it.
