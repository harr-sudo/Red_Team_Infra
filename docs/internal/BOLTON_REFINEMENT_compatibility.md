# Bolt-on Refinement — Catalog-Time Compatibility Auto-Detection

**Status:** Design refinement to the master plan.
**Parent doc:** [`VULNERABLE_LAB_BOLTON_PLAN.md`](./VULNERABLE_LAB_BOLTON_PLAN.md)
**Scope:** Extends master plan §3 (taxonomy), §4 (schema), §5 (dependency resolution), §8 (UI/UX), §9 (backend API).
**Author:** Red Team Infra
**Date:** 2026-05-18

---

## 1. Executive summary

The master plan resolves dependencies and conflicts at **install time** — the operator drags a vulnerability onto a host, the resolver computes a plan, and a confirm-takeover surfaces issues. This refinement pushes that check **upstream into the catalog browse experience**: the moment an operator selects a target host, every card in the catalog is annotated and re-styled with one of eight compatibility states (Installable, Incompatible OS, Incompatible Role, Missing Prereq, Conflicts With Installed, Already Installed, Missing Software, Patched). Each state ships with a human-readable reason and a suggested next action, so the operator never wastes time discovering at confirm-takeover that the chosen vuln was never going to apply. Implementation adds three new endpoints under `/api/bolton/labs/<lab>/hosts/<host>/...`, a host-fact bundle gathered by Ansible setup at registration and refreshed on a 5-minute TTL, and a stateless resolver that runs <100 ms across the whole catalog for a single host so the UI stays live.

---

## 2. Host fact model

### 2.1 What the resolver needs to know

The compatibility resolver answers the question *"can vulnerability V install cleanly on host H right now?"* To answer that without round-tripping to the target, the system maintains a **host fact bundle** per host in a lab. The bundle is the union of what is needed by every `targets:` / `depends_on:` / `conflicts_with:` clause across the catalog.

### 2.2 Fact schema

```yaml
# webapp/state/bolton/host_facts/<lab>/<host>.yaml
host_id: dc01.sevenkingdoms.local
lab: combined-adhoc-light
collected_at: 2026-05-18T14:22:01Z      # last successful probe
collected_by: ansible_setup             # ansible_setup | live_probe | manual
ttl_expires_at: 2026-05-18T14:27:01Z    # collected_at + 5min
stale: false                            # derived: now > ttl_expires_at

# ── OS identity ──────────────────────────────────────────────
os:
  family: windows                       # windows | linux | macos | network | container
  distribution: WindowsServer           # e.g. Ubuntu, RHEL, WindowsServer
  version: "2019"                       # major version
  build: "17763.5458"                   # detailed build (Win) or kernel (Linux)
  edition: Datacenter                   # Datacenter | Standard | LTSC | Pro | etc.
  architecture: amd64

# ── Role & domain membership ────────────────────────────────
role: dc                                # dc | member | workstation | linux-member | ca-host | standalone
domain:
  joined: true
  fqdn: sevenkingdoms.local
  netbios: SEVENKINGDOMS
  function_level: "2016"                # 2008R2 | 2012 | 2012R2 | 2016 | 2025
  forest_function_level: "2016"
  schema_version: 87
  is_pdc_emulator: true
  is_global_catalog: true

# ── Installed services ──────────────────────────────────────
services:
  - { name: adcs, version: "ADCS-Cert-Authority", running: false }
  - { name: iis, version: "10.0", running: true }
  - { name: mssql, version: null, running: false }
  - { name: exchange, version: null, running: false }
  - { name: smb, version: "SMBv3", running: true, signing_required: false }

# ── Patch state ─────────────────────────────────────────────
patches:
  last_collected: 2026-05-18T13:00:00Z
  installed_kbs: [KB5034441, KB5034769, KB5022842]
  cve_coverage:                         # which CVEs are patched on this host
    - { cve: CVE-2021-34527, patched: true, kb: KB5005033 }   # PrintNightmare
    - { cve: CVE-2020-1472,  patched: true, kb: KB4556836 }   # Zerologon
    - { cve: CVE-2022-26923, patched: false }                 # Certifried

# ── Network position ────────────────────────────────────────
network:
  subnet: 10.0.10.0/24
  private_ip: 10.0.10.10
  reachable_from_operator: true         # via bastion / jumpbox tunnel
  reachable_from_jumpbox: true
  open_ports_observed: [53, 88, 135, 389, 445, 464, 636, 3268, 3269, 3389, 5985, 9389]

# ── Bolt-on state ───────────────────────────────────────────
installed_boltons:
  - { id: bolton.identity.weak-password-policy, version: "1.0.0", installed_at: 2026-05-18T12:00:00Z }
  - { id: bolton.identity.kerberoastable-svc,   version: "1.0.0", installed_at: 2026-05-18T12:05:00Z }

# ── Policy state ────────────────────────────────────────────
policies:
  gpos_applied:
    - { name: "Default Domain Policy", guid: "{31B2F340-016D-11D2-945F-00C04FB984F9}" }
    - { name: "Weak Password Policy (bolt-on)", guid: "{...}" }
  smb_signing_enforced: false
  ldap_signing_required: false
  ntlm_disabled: false
  laps_deployed: false

# ── Privilege / agent state ─────────────────────────────────
agents:
  ansible_user_present: true            # the `ansible` local user from §10.2 of master plan
  winrm_reachable: true
  ssm_managed: true
  edr_detected: null                    # null | defender | sentinelone | crowdstrike | etc.
```

### 2.3 How facts are gathered

| Source | When | What it provides |
|---|---|---|
| **Ansible setup module** | At lab registration; first contact with the host | OS, distribution, version, architecture, network, basic services |
| **`win_get_servers_info` / `setup` filter** | At registration | Domain join, role, function level (Windows) |
| **Custom Ansible role `bolton_factgather`** | At registration + every refresh | Patches/KBs, installed services with versions, GPO list, SMB/LDAP/NTLM policy, EDR fingerprint |
| **Bolt-on state file** | Updated by every install/cleanup job | `installed_boltons` |
| **Lightweight network probe (TCP banner / port scan)** | On `refresh` only | `open_ports_observed`, `reachable_from_*` |
| **CVE → KB map** | Static asset at `bolton/cve_kb_map.yaml`, refreshed monthly | Resolves `installed_kbs` → `cve_coverage` without re-probing |

All gathering runs against the lab jumpbox over the existing SSH + nohup pattern (mirroring `provision_goad` in `webapp/backend/routes/goad.py`). Output JSON is written to `webapp/state/bolton/host_facts/<lab>/<host>.yaml`.

### 2.4 Refresh strategy

- **TTL:** 5 minutes. After expiry, facts are still served from cache, but flagged `stale: true` and the UI shows a "Refresh" affordance in the host header.
- **Forced refresh:** Operator clicks "Refresh" → `POST /api/bolton/labs/<lab>/hosts/<host>/facts/refresh` → blocking probe (returns within ~10–15 s for a healthy host) → fresh bundle.
- **Auto-invalidation:** Any successful install/cleanup job that touches host H invalidates H's facts immediately (deletes the cached file). The next catalog open re-probes.
- **Cross-host invalidation:** Bolt-ons with `side_effects.global` (per master plan §4.1) invalidate facts for **all hosts in the lab**, not just the target. Example: installing a domain-wide GPO mutates every member server's policy state.

### 2.5 Storage

Plain YAML on disk in `webapp/state/bolton/host_facts/<lab>/<host>.yaml`, mirroring the existing per-lab state pattern. No new database. Atomic writes (write to `.tmp`, `os.replace()`). Read path is cheap enough that no in-memory cache is required for catalog evaluation; the OS page cache handles it.

---

## 3. Compatibility evaluation states

Eight terminal states, evaluated per `(host, vuln)` pair. The resolver returns exactly one. Each state carries a `reason` string and a `suggested_action` enum.

### 3.1 State enum

| State | When emitted | Suggested action |
|---|---|---|
| **`INSTALLABLE`** | All `targets:` constraints satisfied, no conflicts with `installed_boltons`, all `depends_on` already satisfied or installable, required services present and running, not already installed, not patched. | `install` — primary CTA enabled |
| **`INCOMPATIBLE_OS`** | `targets.supported_os` does not include host's `os.family` / `os.version`. | `pick_different_host` — list compatible hosts inline |
| **`INCOMPATIBLE_ROLE`** | `targets.required_roles` does not contain host's `role` (e.g. requires `dc`, host is `workstation`). | `pick_different_host` — list compatible hosts inline |
| **`MISSING_PREREQ`** | `depends_on` contains a bolt-on that is NOT in `installed_boltons` (recursive) AND would itself be `INSTALLABLE` on the same/required host. | `install_prereq_first` — link jumps to the prereq card |
| **`CONFLICTS_WITH_INSTALLED`** | `conflicts_with` intersects `installed_boltons`, OR an installed bolt-on lists this vuln in its own `conflicts_with`. | `uninstall_conflicting` — link to the installed conflict for one-click cleanup |
| **`ALREADY_INSTALLED`** | `installed_boltons[*].id == vuln.id`. | `re_verify` or `uninstall` — surface verify + cleanup actions |
| **`MISSING_SOFTWARE`** | `targets.required_services` contains a service that is not present or not running (e.g. ADCS ESC1 needs ADCS role installed). | `install_software_bolton` — if a bolt-on exists to install the missing service (e.g. `bolton.adcs.install-adcs`), link to it; otherwise show "Manual setup required" with the service name |
| **`PATCHED`** | Vuln has `cve:` entries AND every CVE is `patched: true` in `patches.cve_coverage`. The bolt-on may install but verify probe will fail. | `view_alternatives` — show vulns in the same subcategory that are not patched |

### 3.2 Evaluation order

States are checked in priority order. The first match wins (so `ALREADY_INSTALLED` always trumps a deeper analysis, etc.):

```
1. ALREADY_INSTALLED        # cheapest; short-circuits everything
2. INCOMPATIBLE_OS          # static targets check
3. INCOMPATIBLE_ROLE        # static targets check
4. PATCHED                  # static CVE check (CVE-bearing vulns only)
5. MISSING_SOFTWARE         # service presence check
6. CONFLICTS_WITH_INSTALLED # set intersection
7. MISSING_PREREQ           # recursive descent into depends_on
8. INSTALLABLE              # default if nothing above triggered
```

### 3.3 Response shape per state

```json
{
  "vuln_id": "bolton.adcs.esc1",
  "state": "MISSING_SOFTWARE",
  "reason": "Requires ADCS role to be installed on this host. The ADCS service is not present.",
  "suggested_action": "install_software_bolton",
  "suggested_action_payload": {
    "kind": "install_bolton",
    "vuln_id": "bolton.adcs.install-adcs"
  },
  "compatible_hosts": ["ca01.sevenkingdoms.local"],
  "blocking_items": [
    { "kind": "service", "name": "adcs", "fix_bolton": "bolton.adcs.install-adcs" }
  ]
}
```

`blocking_items` is the structured form of `reason` and drives the badge text on the card.

---

## 4. Resolver algorithm

Pseudocode for the per-vulnerability compatibility evaluator. Extends master plan §5.2 (which is the install-time resolver — this one is the catalog-time resolver and is *non-recursive about installation order*, only about state classification).

```python
def evaluate_compatibility(vuln: VulnDescriptor, host_facts: HostFacts,
                            lab_state: LabState) -> CompatibilityResult:
    # ---------- 1. ALREADY_INSTALLED ----------
    if vuln.id in host_facts.installed_boltons:
        return CompatibilityResult(
            state="ALREADY_INSTALLED",
            reason=f"{vuln.name} is already installed on {host_facts.host_id}.",
            suggested_action="re_verify",
        )

    # ---------- 2. INCOMPATIBLE_OS ----------
    if not _os_matches(vuln.targets.supported_os, host_facts.os):
        compat_hosts = _hosts_with_matching_os(vuln, lab_state)
        return CompatibilityResult(
            state="INCOMPATIBLE_OS",
            reason=f"Requires {_os_summary(vuln.targets.supported_os)}; "
                   f"this host is {host_facts.os.distribution} {host_facts.os.version}.",
            compatible_hosts=compat_hosts,
            suggested_action="pick_different_host",
        )

    # ---------- 3. INCOMPATIBLE_ROLE ----------
    if vuln.targets.required_roles and host_facts.role not in vuln.targets.required_roles:
        compat_hosts = _hosts_with_role(vuln.targets.required_roles, lab_state)
        return CompatibilityResult(
            state="INCOMPATIBLE_ROLE",
            reason=f"Requires role(s): {vuln.targets.required_roles}; "
                   f"this host is role '{host_facts.role}'.",
            compatible_hosts=compat_hosts,
            suggested_action="pick_different_host",
        )

    # ---------- 4. PATCHED ----------
    if vuln.cve:
        cves_patched = [c for c in vuln.cve
                        if _is_patched(c, host_facts.patches.cve_coverage)]
        if cves_patched and len(cves_patched) == len(vuln.cve):
            alts = _siblings_in_subcategory(vuln, exclude_patched_on=host_facts)
            return CompatibilityResult(
                state="PATCHED",
                reason=f"All underlying CVEs ({', '.join(vuln.cve)}) are patched "
                       f"on this host. Bolt-on can be installed but verification "
                       f"will fail.",
                suggested_alternatives=alts,
                suggested_action="view_alternatives",
            )

    # ---------- 5. MISSING_SOFTWARE ----------
    missing_services = []
    for svc in vuln.targets.required_services:
        if not _service_present_and_running(svc, host_facts.services):
            fix = _find_bolton_that_installs(svc)  # e.g. adcs -> bolton.adcs.install-adcs
            missing_services.append({"name": svc, "fix_bolton": fix})
    if missing_services:
        return CompatibilityResult(
            state="MISSING_SOFTWARE",
            reason=f"Missing service(s): {', '.join(s['name'] for s in missing_services)}.",
            blocking_items=missing_services,
            suggested_action="install_software_bolton" if any(m["fix_bolton"] for m in missing_services)
                             else "manual_setup_required",
        )

    # ---------- 6. CONFLICTS_WITH_INSTALLED ----------
    conflicts = _conflicts_with_installed(vuln, host_facts.installed_boltons, lab_state)
    if conflicts:
        return CompatibilityResult(
            state="CONFLICTS_WITH_INSTALLED",
            reason=f"Conflicts with installed: {', '.join(c.id for c in conflicts)}.",
            blocking_items=[{"kind": "bolton", "id": c.id, "name": c.name} for c in conflicts],
            suggested_action="uninstall_conflicting",
        )

    # ---------- 7. MISSING_PREREQ ----------
    missing_prereqs = []
    for dep in vuln.depends_on:
        if dep.optional:
            continue
        if not _is_satisfied(dep, host_facts, lab_state):
            missing_prereqs.append(dep)
    if missing_prereqs:
        # Determine whether prereqs are themselves installable now
        prereq_resolutions = [
            (p, evaluate_compatibility(_lookup(p.id), host_facts, lab_state))
            for p in missing_prereqs
        ]
        return CompatibilityResult(
            state="MISSING_PREREQ",
            reason=f"Requires: {', '.join(p.id for p in missing_prereqs)}.",
            blocking_items=[
                {"kind": "bolton", "id": p.id, "state": r.state}
                for (p, r) in prereq_resolutions
            ],
            suggested_action="install_prereq_first",
        )

    # ---------- 8. INSTALLABLE ----------
    return CompatibilityResult(
        state="INSTALLABLE",
        reason="All compatibility requirements met.",
        suggested_action="install",
    )
```

### 4.1 Notes on the algorithm

- **Pure function.** Takes `(vuln, host_facts, lab_state)`, returns a result. No I/O. Allows trivial unit testing and lets the catalog endpoint compute *N* results in a tight loop.
- **`lab_state`** is a thin index: `{host_id → host_facts}` for the whole lab, used by `_hosts_with_matching_os` etc. to compute `compatible_hosts` for the suggested-action payload. Loaded once per request.
- **Recursive prereq check** stops at depth 1 for catalog-time. Deeper chains are still resolved at install-time by master plan §5.2. Catalog only needs to tell the operator "you can't install X right now," not "here is the 4-step install path."
- **Backstop at install time:** the install endpoint re-runs `evaluate_compatibility` against fresh facts before dispatching. If stale catalog said `INSTALLABLE` but live facts say otherwise, the install is refused with a clear error. See §7.

---

## 5. UI behavior in the catalog

Extends master plan §8.1. Reuses Phase 2b TASTE V3 primitives: `.spec-row`, `.spec-pill`, `.scrim-takeover`, `.icon`, plus a small additional set of compatibility-state utility classes.

### 5.1 Host selector header

Always visible at the top of the `/vulnerabilities` page, sticky below the main nav. When no host selected:

```
┌──────────────────────────────────────────────────────────────────┐
│ [icon: server]  Target host: NONE SELECTED                       │
│                  [Select host ▾]                                 │
│ Catalog shows all vulnerabilities (no compatibility filtering).  │
└──────────────────────────────────────────────────────────────────┘
```

When a host IS selected — the fact summary is visible inline:

```
┌────────────────────────────────────────────────────────────────────────┐
│ [icon: server]  dc01.sevenkingdoms.local           [Refresh] [Change]  │
│  ┌─ .spec-row ──────────────────────────────────────────────────────┐  │
│  │ OS:    Windows Server 2019 Datacenter (build 17763.5458)         │  │
│  │ Role:  Domain Controller · Forest 2016 · PDC Emulator            │  │
│  │ Svcs:  IIS 10.0, SMBv3 (signing off)                             │  │
│  │ Bolt:  2 installed — weak-password-policy, kerberoastable-svc    │  │
│  │ Probe: 4m ago  ⓘ                                                  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

Markup primitives:

- `.spec-row` wraps each fact line.
- `.spec-pill` for "PDC Emulator", "Forest 2016", etc.
- `.icon` for the leading server glyph; `.icon.icon--stale` (amber) when `host_facts.stale == true`.
- "Refresh" is a button that triggers `POST /api/bolton/labs/<lab>/hosts/<host>/facts/refresh`; while in flight the entire header gets `.is-loading` and a `.spec-pill--pending` reads "Refreshing host facts…".

### 5.2 Filter chips above the catalog

A new row above the existing category/target/complexity filters:

```
┌──────────────────────────────────────────────────────────────────────┐
│  [ All (47) ] [ Installable (12) ] [ Incompatible (28) ] [ Installed (2) ]  │
│  [ Patched (3) ] [ Missing Prereq (2) ]                              │
└──────────────────────────────────────────────────────────────────────┘
```

Each chip is a `.spec-pill` button — `.spec-pill--active` for selected. Counts are computed server-side and arrive in the catalog response. Selecting a chip filters the grid in-place (no reload — pure CSS class toggle on cards).

### 5.3 Card styling per state

Each card already carries `data-vuln-id`. Add `data-compat-state` set to one of the eight states. CSS targets that attribute to re-style the card.

| State | Card styling |
|---|---|
| `INSTALLABLE` | Default — `.spec-row` border, primary CTA `[Install]` enabled. |
| `INCOMPATIBLE_OS` | `opacity: 0.45`; small `.spec-pill.spec-pill--warn` badge reading "Wrong OS"; CTA `[Install]` becomes `[Install] (disabled)`. Hover anywhere on the card shows tooltip with full `reason`. |
| `INCOMPATIBLE_ROLE` | Same as above, badge reads "Needs <role>" (e.g. "Needs DC"). |
| `MISSING_PREREQ` | Full color, but yellow left-border (`border-left: 3px solid var(--accent-warn)`). Inline `.spec-row__hint` reads "Needs: <prereq slug>". The prereq slug is a link that scrolls + flashes the prereq card via `:target` styling. |
| `CONFLICTS_WITH_INSTALLED` | Red-tinted border (`border: 1px solid var(--accent-danger)`). Badge `.spec-pill--danger` reads "Conflicts with <slug>". CTA replaced with `[Resolve conflict ▸]` which opens a `.scrim-takeover` listing the installed conflicts and offering one-click uninstall. |
| `ALREADY_INSTALLED` | Subtle green left-border. `.spec-pill.spec-pill--success` reads "Installed". CTA row shows `[Verify]` `[Uninstall]` (in place of `[Install]`). |
| `MISSING_SOFTWARE` | Yellow tint similar to `MISSING_PREREQ`. Badge reads "Needs: <service>". If a `fix_bolton` exists, a secondary link reads "Install <service> first ▸" and jumps to that card. |
| `PATCHED` | Grey-tinted card, italic CTA label `[Install anyway]`. Badge `.spec-pill--muted` reads "Patched". A small text link `View alternatives ▸` opens a `.scrim-takeover` listing same-subcategory bolt-ons that are not patched. |

### 5.4 ASCII layout: host-selected catalog state

```
╔═════════════════════ VULNERABILITY CATALOG ═════════════════════╗
║ [icon] dc01.sevenkingdoms.local · Win2019 DC · 2 bolt-ons  [↻]  ║
╠═════════════════════════════════════════════════════════════════╣
║ [All 47] [Installable 12] [Incompat 28] [Installed 2] [Patch 3] ║
║ Filters: [Category ▾] [Target ▾] [Complexity ▾] [Search …]      ║
╠═════════════════════════════════════════════════════════════════╣
║                                                                 ║
║ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐     ║
║ │ Kerberoastable  │ │ ADCS ESC1       │ │ PrintNightmare  │     ║
║ │ Svc             │ │ ⋮ adcs         │ │ ⋮ cve          │     ║
║ │ ⋮ identity-kerb│ │ ▲ CA · 90s     │ │ ▲ DC · 4m       │     ║
║ │ ▲ DC · 30s     │ │                 │ │                 │     ║
║ │                 │ │  [Needs DC]     │ │  [Patched]      │     ║
║ │ [Installed]     │ │  opacity 0.45   │ │  grey tint      │     ║
║ │ [Verify][Uninst]│ │  [Install]✕    │ │ [Install anyway]│     ║
║ └─────────────────┘ └─────────────────┘ └─────────────────┘     ║
║                                                                 ║
║ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐     ║
║ │ AS-REP Roast    │ │ ESC8 NTLM Relay │ │ Weak Pwd Policy │     ║
║ │ ⋮ identity-kerb│ │ ⋮ adcs         │ │ ⋮ identity     │     ║
║ │ ▲ DC · 20s     │ │ ▲ CA · 3m      │ │ ▲ DC · 10s     │     ║
║ │                 │ │                 │ │                 │     ║
║ │  [Installable]  │ │  Needs ADCS ▸  │ │  Conflicts w/   │     ║
║ │  green CTA      │ │  yellow border  │ │  strong-pwpol   │     ║
║ │ [Install ▸]    │ │ [Install] ✕     │ │ red border      │     ║
║ │                 │ │  [Install ADCS] │ │ [Resolve ▸]    │     ║
║ └─────────────────┘ └─────────────────┘ └─────────────────┘     ║
╚═════════════════════════════════════════════════════════════════╝
```

### 5.5 Hover/tooltip detail

Every non-`INSTALLABLE` card surfaces an `.icon.icon--info` glyph in the top-right corner. Hover opens a small `.scrim-takeover` (the lightweight popover variant) showing:

- The state string
- The full `reason`
- `blocking_items` rendered as a `.spec-list`
- The suggested action button

Keyboard: `?` while a card has focus opens the popover; `Esc` closes.

### 5.6 Drag/drop interaction with state

Drag is **only enabled** for `INSTALLABLE`, `MISSING_PREREQ` (drag dispatches the prereq chain), and `PATCHED` (drag with `[Install anyway]` semantics — confirm-takeover warns about verification failure). Other states have `draggable="false"` on the card element. Attempting to drag an incompatible card produces a brief shake animation + `.spec-row__hint--error` flash explaining why.

---

## 6. Backend API additions

Extends master plan §9. All under the existing `/api/bolton` blueprint. Auth attribution rules from §9.1 apply unchanged.

### 6.1 New endpoints

| Method | Path | Purpose |
|---|---|---|
| **GET** | `/api/bolton/labs/<lab>/hosts/<host>/facts` | Return cached host facts bundle. |
| **GET** | `/api/bolton/labs/<lab>/hosts/<host>/catalog` | Return full catalog annotated with per-vuln compatibility state for this host. |
| **POST** | `/api/bolton/labs/<lab>/hosts/<host>/facts/refresh` | Force a fresh probe. Blocking; returns refreshed bundle. |

The existing `GET /api/bolton/vulns` (master plan §9) becomes the **raw catalog** — schema-only, no host context. The new `/hosts/<host>/catalog` is the **host-contextualized catalog**.

### 6.2 `GET /api/bolton/labs/<lab>/hosts/<host>/facts`

**Request:** None.

**Query params:**

- `force_refresh=true` — equivalent to calling the refresh endpoint then returning facts. Default `false`.
- `include_raw=true` — include raw Ansible setup output. Default `false`.

**Response 200:**

```json
{
  "host_id": "dc01.sevenkingdoms.local",
  "lab": "combined-adhoc-light",
  "collected_at": "2026-05-18T14:22:01Z",
  "collected_by": "ansible_setup",
  "ttl_expires_at": "2026-05-18T14:27:01Z",
  "stale": false,
  "facts": { /* full bundle per §2.2 */ }
}
```

**Errors:**

- `404 Not Found` — host not in lab, or facts never collected (point operator at refresh endpoint).
- `503 Service Unavailable` — host unreachable on last attempt; serves last-known facts with `stale: true` + a `last_error` field.

### 6.3 `GET /api/bolton/labs/<lab>/hosts/<host>/catalog`

**Query params:**

- `category=<id>` — filter by master plan §3 category.
- `state=<state>` — filter by compatibility state (one of the 8). Repeatable.
- `search=<q>` — substring match on name/slug.

**Response 200:**

```json
{
  "host_id": "dc01.sevenkingdoms.local",
  "host_facts_summary": {
    "os": "Windows Server 2019 Datacenter",
    "role": "dc",
    "installed_count": 2,
    "stale": false,
    "collected_at": "2026-05-18T14:22:01Z"
  },
  "counts_by_state": {
    "INSTALLABLE": 12,
    "INCOMPATIBLE_OS": 18,
    "INCOMPATIBLE_ROLE": 10,
    "MISSING_PREREQ": 2,
    "CONFLICTS_WITH_INSTALLED": 0,
    "ALREADY_INSTALLED": 2,
    "MISSING_SOFTWARE": 0,
    "PATCHED": 3
  },
  "vulns": [
    {
      "id": "bolton.identity.kerberoastable-svc",
      "name": "Kerberoastable Service Account",
      "category": "identity-kerberos",
      "summary_meta": { "target_role": "dc", "install_seconds": 30, "detection_profile": "quiet" },
      "compatibility": {
        "state": "ALREADY_INSTALLED",
        "reason": "Already installed on dc01.sevenkingdoms.local.",
        "suggested_action": "re_verify",
        "suggested_action_payload": { "kind": "verify_bolton", "vuln_id": "bolton.identity.kerberoastable-svc" },
        "blocking_items": [],
        "compatible_hosts": []
      }
    },
    {
      "id": "bolton.adcs.esc1",
      "name": "ADCS ESC1 — Enrollee Supplies Subject",
      "category": "adcs",
      "summary_meta": { "target_role": "ca-host", "install_seconds": 90, "detection_profile": "quiet" },
      "compatibility": {
        "state": "INCOMPATIBLE_ROLE",
        "reason": "Requires role(s): ['ca-host']; this host is role 'dc'.",
        "suggested_action": "pick_different_host",
        "compatible_hosts": ["ca01.sevenkingdoms.local"],
        "blocking_items": []
      }
    }
    // … all other vulns
  ]
}
```

**Errors:**

- `404 Not Found` — host or lab not found.
- `409 Conflict` — facts never collected; payload includes a hint to call the refresh endpoint.

### 6.4 `POST /api/bolton/labs/<lab>/hosts/<host>/facts/refresh`

**Request body:** (optional)

```json
{
  "deep_probe": false   // if true, also runs the network probe step (slower, ~30s)
}
```

**Response 200:** Same shape as `GET /facts`, with fresh `collected_at`.

**Response 202 Accepted:** If the probe is configured async (future enhancement), returns a `job_id` to poll. For v1, the call is blocking and returns 200 directly.

**Errors:**

- `503 Service Unavailable` — host unreachable. Body: `{ "error": "host_unreachable", "last_known_collected_at": "...", "last_error": "Connection refused on WinRM 5985" }`.
- `504 Gateway Timeout` — Ansible setup module timed out (>30 s). Operator can retry; nothing was changed on the host.

### 6.5 Frontend integration changes

The `Catalog` page (master plan §8.1) is rewritten to:

1. On mount, fetch `/labs/<lab>/hosts` and render the host selector dropdown.
2. On host select, fetch `/labs/<lab>/hosts/<host>/catalog` and render annotated cards.
3. On host unselect, fall back to the unannotated `/api/bolton/vulns` raw catalog.
4. Filter chip clicks call the same `/catalog` endpoint with a `state=` query param.
5. The host header's "Refresh" button calls the refresh endpoint and then re-fetches `/catalog`.

---

## 7. Performance + caching strategy

### 7.1 Targets

- **Catalog evaluation:** <100 ms p95 for the full catalog (assume ~200 descriptors over time) × one host.
- **Cached fact read:** <10 ms (single file read).
- **Forced refresh:** <15 s p95 for a healthy host (Ansible setup module + bolton_factgather role).

### 7.2 Where time goes (per request)

```
GET /labs/<lab>/hosts/<host>/catalog
  ├─ load host_facts from disk           ~5 ms
  ├─ load full descriptor index in mem   ~0 ms (in-process, lazy on first request)
  ├─ load lab_state index in mem         ~10 ms (reads each host facts file once)
  ├─ evaluate_compatibility() × N vulns  ~50 ms (200 vulns × ~250 µs each)
  ├─ serialize JSON                      ~5 ms
  └─ total                               ~70 ms
```

### 7.3 Caching layers

| Layer | Where | TTL | Invalidation |
|---|---|---|---|
| **Descriptor index** | In-process module-level dict. Loaded from `bolton/catalog/**/*.yaml` on first use, watched for changes via `os.path.getmtime` polling on every request (cheap). | Process lifetime | mtime change on any catalog file |
| **Host facts** | `webapp/state/bolton/host_facts/<lab>/<host>.yaml` | 5 min TTL via `collected_at` + `ttl_expires_at` | After any install/cleanup touching the host; after any global-side-effect bolt-on |
| **Lab state index** | Built on-the-fly per catalog request (loop over `host_facts/<lab>/*.yaml`) | Request scope | N/A |
| **Catalog response** | NOT cached. Always recomputed. Cheap enough. | — | — |

### 7.4 Why no Redis / no cache server

- Single-server dashboard (per `CLAUDE.md`); no horizontal fan-out.
- Disk reads of a YAML file are ~µs after OS page-cache warm.
- 200 descriptors × ~250 µs evaluator = 50 ms. Even at 1000 descriptors it remains under the 100 ms target.

Adding Redis or sqlite would add operational surface for zero current benefit. Revisit only if catalog grows past ~5000 descriptors or the dashboard scales to multi-process.

### 7.5 Cross-host invalidation

When a job dispatched via `POST /labs/<lab>/install` completes, the post-install hook:

1. Reads the descriptor's `side_effects` field.
2. If `side_effects.global` is non-empty → invalidates **all** host facts files in that lab.
3. Else → invalidates only the target host's facts file.

Invalidation is a `unlink` on the YAML file; the next read triggers a refresh.

### 7.6 Concurrent operator behavior

The catalog endpoint is read-only; concurrent reads are fine. Writes (refresh, install completion) take a per-host filelock (`fcntl.flock`) on the YAML file's `.lock` sidecar. Read-during-write is impossible because writes are atomic (write-tmp + rename).

---

## 8. Edge cases + open questions

### 8.1 Stale-facts false-positive (operator install succeeds catalog check, then fails)

**Scenario:** Catalog says `INSTALLABLE`, but host facts are 4 minutes old. In the interim, operator B installed the conflicting vuln. Operator A clicks Install.

**Resolution:** The install endpoint (master plan §9) re-runs `evaluate_compatibility` against fresh facts as a backstop. If the state is no longer `INSTALLABLE`, the install is refused with a 409 + the new state's `reason`. Operator A's UI shows a `.scrim-takeover` with a "Refresh and retry" CTA.

### 8.2 Stale-facts false-negative (catalog says incompatible but reality is fine)

**Scenario:** Operator manually patched a CVE outside the bolt-on system; facts haven't been refreshed.

**Resolution:** The host header always shows facts age + a refresh button. The operator is trained (via inline help) to refresh before assuming a card is genuinely incompatible. State `PATCHED` and `MISSING_SOFTWARE` cards both surface a "Stale — refresh ▸" affordance when `host_facts.stale == true`.

### 8.3 Concurrent lab modification

**Scenario:** Operator A is browsing the catalog for dc01; Operator B installs `bolton.adcs.install-adcs` on ca01 in the same lab.

**Resolution:** The install completion hook invalidates ca01's facts. Operator A's catalog for dc01 is unaffected (their request targets dc01). If Operator A switches to ca01, the next catalog fetch sees the invalidated cache and triggers a refresh. The 5-minute TTL bounds the worst case.

**Open question:** Should the dashboard push a WebSocket event to all connected operators when a fact bundle is invalidated, so the catalog auto-refreshes without a click? Likely yes in a v2; not in v1.

### 8.4 Ambiguous OS specifications

**Scenario:** A descriptor lists `supported_os: [windows 10, windows 11]`. The host is Windows 10 LTSC 2021 which receives a different patch cadence than Windows 10 22H2. A CVE patched in 22H2 may not be patched in LTSC.

**Resolution v1:** Match on `family + version` only. LTSC vs SAC distinction is captured in `host_facts.os.edition` but not used by the resolver unless the descriptor explicitly narrows via:

```yaml
supported_os:
  - family: windows
    min_version: "10"
    max_version: "10"
    edition_in: ["Pro", "Enterprise", "LTSC"]
    excluded_kb_streams: ["LTSC"]
```

**Open question:** Adopting an SBOM/SWID-style identifier (e.g. `urn:swid:microsoft.windows:10.0.19044.4291:LTSC:x64`) per host would let descriptors target with more precision. Out of scope for v1; revisit if PATCHED false-negatives become common in practice.

### 8.5 Bolt-on that targets multiple host roles in one descriptor (e.g. ESC8 relay)

**Scenario:** ESC8 requires an HTTP listener on the CA AND an NTLM-relayable target elsewhere. Per master plan §5.1, dep edges carry a `target_host_role`. The catalog-time evaluator currently checks compatibility for *the selected host*, not the multi-host setup.

**Resolution v1:** Multi-host bolt-ons declare a `primary_role` in `targets`. Catalog evaluation runs against the primary host. The install-time resolver (master plan §5.2) handles cross-host dependencies; the install confirm takeover lists every host that will be touched.

**Open question:** Should the catalog show multi-host bolt-ons as a special card style ("Requires 2 hosts ▸") with its own selector? Likely a v2 enhancement.

### 8.6 Descriptor authoring errors

**Scenario:** A descriptor lists `required_services: [adcs]` but the only existing "install ADCS" bolt-on has a typo and ID lookup fails. Suggested action falls back to `manual_setup_required` with a generic string.

**Resolution:** Add a `bolton_lint` CLI that runs over the catalog at CI time. Verifies every `depends_on.id` and every `required_services` → fix_bolton mapping resolves. Fails CI on broken refs. Not a runtime concern.

### 8.7 GOAD upstream-aligned hostnames

Per MEMORY.md, GOAD-Light/Mini/Full hostnames match upstream exactly. The fact gather role must be careful to use the **upstream-aligned hostnames** (not arbitrary EC2 instance names) when keying `host_facts/<lab>/<host>.yaml`. This is already true via the Ansible inventory.

### 8.8 Open questions consolidated

1. **WebSocket push for live invalidation** — defer to v2.
2. **Multi-host catalog cards** — defer to v2.
3. **SBOM-precision OS matching** — defer; collect false-negative data first.
4. **Should the resolver suggest cross-host alternatives in `compatible_hosts`** (e.g. for `INCOMPATIBLE_ROLE`)? — v1 says yes, computed via `_hosts_with_role`. Open: should the card support one-click "switch target to ca01" without a new catalog fetch? Probably yes; track as a UX polish item.
5. **Stale facts during high-rate install bursts** — if 10 jobs complete in 30 s, we'll be hammering invalidation. Open: should invalidation be coalesced via a 2-second debounce? Likely yes — track for implementation.

---

## 9. Acceptance criteria

The refinement is **done** when all of the following hold:

### 9.1 Functional

- [ ] An operator opens `/vulnerabilities` with no host selected — catalog shows every descriptor, no state badges, no opacity changes.
- [ ] Operator selects host `dc01` — every card is annotated with one of the 8 compatibility states within 200 ms of selection (perceived as instant).
- [ ] The host header shows OS, role, installed bolt-on count, and last-collected timestamp.
- [ ] Cards in state `INSTALLABLE` are full-color, draggable, primary CTA enabled.
- [ ] Cards in state `INCOMPATIBLE_OS` are dimmed to opacity 0.45, carry a "Wrong OS" badge, are not draggable, and the primary CTA is disabled.
- [ ] Cards in state `INCOMPATIBLE_ROLE` carry a "Needs <role>" badge and list `compatible_hosts` on hover.
- [ ] Cards in state `MISSING_PREREQ` carry a yellow left-border, an inline "Needs: <slug>" hint, and the slug links to the prereq card.
- [ ] Cards in state `CONFLICTS_WITH_INSTALLED` carry a red border and a "Conflicts with <slug>" badge. The CTA `[Resolve conflict ▸]` opens a takeover offering one-click uninstall of the conflict.
- [ ] Cards in state `ALREADY_INSTALLED` show a "Installed" pill and the CTAs are replaced with `[Verify]` and `[Uninstall]`.
- [ ] Cards in state `MISSING_SOFTWARE` show "Needs: <service>" and link to a `fix_bolton` when one exists.
- [ ] Cards in state `PATCHED` are grey-tinted with `[Install anyway]` and a "View alternatives ▸" link that lists same-subcategory bolt-ons not currently patched.

### 9.2 Filtering

- [ ] Filter chips `[All] [Installable] [Incompatible] [Installed] [Patched] [Missing Prereq]` are present, show live counts, and narrow the grid on click.
- [ ] Selecting two chips combines (OR semantics within state filters).
- [ ] Filter state is reflected in the URL query string for share-linking.

### 9.3 Refresh / staleness

- [ ] Host header indicates fact age in human-relative form ("4m ago", "1h ago").
- [ ] When `host_facts.stale == true`, the refresh button has an amber dot.
- [ ] Clicking Refresh triggers the refresh endpoint and re-fetches the catalog. The header shows a "Refreshing host facts…" pending state for the duration.

### 9.4 Backend

- [ ] `GET /api/bolton/labs/<lab>/hosts/<host>/facts` returns the cached bundle with `stale` flag.
- [ ] `GET /api/bolton/labs/<lab>/hosts/<host>/catalog` returns annotated catalog with `counts_by_state`.
- [ ] `POST /api/bolton/labs/<lab>/hosts/<host>/facts/refresh` triggers a probe and returns a fresh bundle within 15 s for a healthy host.
- [ ] Install endpoint re-runs `evaluate_compatibility` as a backstop before dispatching and refuses with 409 if state is no longer `INSTALLABLE`.

### 9.5 Performance

- [ ] `/catalog` p95 latency is <100 ms for a lab with 5 hosts and a catalog of up to 200 descriptors.
- [ ] `/facts` (cache hit) p95 latency is <20 ms.
- [ ] Forced refresh p95 latency is <15 s for a healthy host.

### 9.6 Tooltips & a11y

- [ ] Every non-`INSTALLABLE` card shows full `reason` in a tooltip on hover and on `?` keypress while focused.
- [ ] Disabled CTAs are properly `aria-disabled` and `tabindex="-1"`.
- [ ] Filter chip counts are announced to screen readers via `aria-live`.

### 9.7 Theme

- [ ] Dual-theme verified per `CLAUDE.md` — every state's card colors meet contrast 4.5:1 in both light and dark themes. No raw hex; all colors via `palette.css` variables (`--accent-warn`, `--accent-danger`, `--accent-success`, `--text-secondary`, etc.).

---

## 10. Cross-references to master plan

| Master plan section | This refinement extends |
|---|---|
| §3 Vulnerability taxonomy | No change — categories drive `category:` field used in catalog filter |
| §4.1 Schema | Reuses `targets`, `depends_on`, `conflicts_with`, `cve`, `side_effects` as-is. No schema changes required for catalog-time compatibility |
| §5 Dependency / conflict resolution | This refinement is the **catalog-time** companion to §5.2's **install-time** resolver. Both share the same descriptor fields; the catalog-time resolver is a stateless per-vuln classifier, the install-time resolver is a DAG planner |
| §5.4 UX implications | The install-confirm takeover from §5.4 still fires after drag-drop. This refinement reduces the chance that the takeover shows an unsatisfiable plan by filtering at browse time |
| §8.1 Catalog page | This refinement is the primary modifier — adds host selector, filter chips, state-driven card styling |
| §9 Backend API design | Adds 3 endpoints under existing `/api/bolton` blueprint, none replace existing ones |
| §10.3 Per-operator audit | Refresh and catalog fetch events do not write to audit (read-only). Install endpoint backstop refusals DO write to audit (operator attempted install of incompatible vuln) |

---

## 11. Future extensions (out of scope for v1)

- **WebSocket-driven live updates** so concurrent operators see fact invalidations without manual refresh.
- **Per-vuln preview mode** — clicking a non-installable card opens a takeover showing what the install would do if the operator forced it (useful for training / agent labs).
- **Bulk host evaluation** — `GET /api/bolton/labs/<lab>/catalog?for_hosts=dc01,ca01,ws01` returns a matrix view (rows = vulns, cols = hosts, cells = state). Lets operators answer "where can I install this?" rather than "what can I install here?".
- **Compatibility score** — instead of binary state, surface a 0–100 score factoring in detection profile, install reliability history, and cost. Useful for ranking suggested alternatives.
- **SBOM-precision OS matching** per §8.4.
