# Vulnerable Lab Bolt-On Feature — End-to-End Plan

**Status:** Proposal / planning
**Owner:** Red Team Infra dashboard
**Target surface:** existing GOAD lab deployments (goad-mini, goad-light, goad-sccm, goad-full, goad-nha) + combined-* modes
**Document scope:** architecture, taxonomy, schema, dependency resolver, install engine, agentic fallback, UI/UX, API, phases, risks, references
**Constraint:** no production code shipped with this doc; everything described here is implementation guidance for follow-up PRs.

---

## 1. Executive summary

Today the dashboard provisions five GOAD lab flavors as pre-baked vulnerable AD environments. Each flavor's vulnerabilities are fixed at provisioning time and tied to upstream Orange Cyberdefense Ansible playbooks. Operators cannot add or remove a single vulnerability without destroying and re-provisioning the lab — and they cannot bolt on the long tail of misconfigs (ADCS ESC1–16, NTLM relay variants, GPP cpassword, LAPS-misconfig, PrintNightmare, ZeroLogon, web app CVEs) that real engagements require.

This plan adds a **Vulnerability Bolt-On** subsystem: a catalog of declaratively-described vulnerabilities that operators drag onto hosts of an already-deployed lab. Each descriptor is a YAML manifest (schema modeled after Atomic Red Team + Ludus + Caldera abilities) backed by an Ansible role that installs the vulnerability, verifies it is exploitable, and can roll it back. A dependency/conflict resolver computes a safe install order; an agentic fallback (Claude API) intervenes when the role fails its post-install probe.

The architecture explicitly reuses what we already have: the GOAD jumpbox runs Ansible, hosts are already inventoried, the dashboard already has an audit-attributed Flask backend, and the frontend already has the `.spec-list` / `.spec-row` / `.spec-pill` / `.scrim-takeover` primitives needed for a high-density catalog UI. Six implementation phases, roughly two to four weeks each, end with a community-contributable plugin model.

---

## 2. Landscape research findings

The plan is grounded in a survey of nine projects/products. For each: what they do, what's stealable for our bolt-on, what to avoid.

### 2.1 Rogue Labs / Rogue Arena — https://www.roguelabs.io and https://landing.roguelabs.io/cyber-range

User flagged this specifically. The marketing landing is thin, but **the news article on Rogue Architect** (https://www.roguelabs.io/news-announcements/drag-amp-drop-scenario-building-how-were-equipping-teams-to-rapidly-build-robust-red-team-scenarios-part-1) is the most direct analog to what the user is asking for.

**What it does.** A 5-step visual scenario builder:

1. Add Containers + Configure Firewall Rules (VLANs / network segments)
2. Add Machines (OS templates)
3. Iterate/Modify Blueprint
4. **Add Plugins to Machines** — drag-and-drop. >100 plugins in the Rogue Architect plugin library
5. Launch — checkpoint/snapshot system rolls back to last clean state on failure

**Plugin categories** (their taxonomy, useful for ours):

- **Machine Action** — auto-login, PowerShell script execution
- **Applications** — Chrome, Notepad++
- **Roles** — domain controller promotion, role-level configurations
- **File Copies** — drop custom files onto a victim
- **Vulnerabilities** — labeled "upcoming library for exploitable conditions"

So the explicit *Vulnerabilities* category is on their roadmap; we are effectively building the same primitive, narrower in scope (AD-focused) and open / self-hosted. Their "Tool Test Harness" — run a tool against a clean snapshot and query Elastic for which detections fired — is also worth noting; it ties directly into our existing Elastic Detection Rules integration (see MEMORY: `project_elastic_rules_integration.md`).

**Stealable.**

- Drag-from-catalog-onto-host as the core interaction.
- Plugins binned into action / app / role / file-copy / **vulnerability** — even though we will collapse some, the distinction between "vulnerability" and "supporting config" is real.
- Snapshot/checkpoint per install step → recoverable failures (we cannot literally snapshot AWS EC2 disks per-step without huge cost, but we can use Ansible state markers + rollback playbooks).
- Brainstorm Mode (an AI assistant that designs the scenario end-to-end) → maps directly to our agentic fallback.

**To avoid.**

- Their full-fat checkpoint system per plugin (cost prohibitive on AWS for our scale).
- Lock-in to their proprietary plugin format.

### 2.2 GOAD (Orange Cyberdefense) — https://github.com/Orange-Cyberdefense/GOAD

The base we are bolting on. Vulnerabilities are **not** declaratively described in a catalog file — they are encoded in Ansible playbooks under `ad/<lab>/data/` and `ad/<lab>/providers/aws/`. Each lab flavor (GOAD-Mini, GOAD-Light, GOAD, SCCM, NHA) hard-codes a set of weaknesses (Kerberoastable accounts, unconstrained delegation, ACL paths, ADCS, SQL trusted links). There is **no add-a-vuln-after-provision flow** in upstream GOAD; you pick a lab flavor, you get its set.

**Stealable.** Their Ansible role layout — each role is idempotent, structured under `roles/<role-name>/{tasks,defaults,files,templates}`. We will continue that pattern for every bolt-on. The existing `webapp/backend/routes/goad.py` `/provision` endpoint already runs Ansible on the jumpbox via SSH for the initial deploy — we extend that same dispatch path for bolt-ons.

**To avoid.** Their attack catalog is a string list in our `GOAD_LABS` dict (e.g. `'attacks': ['Kerberoasting', 'AS-REP Roasting', ...]`) — purely descriptive, no machine semantics. We need a real schema.

### 2.3 BadBlood — https://github.com/davidprowe/BadBlood

PowerShell-only AD-weakness generator. Modules: `AD_Attack_Vectors`, `AD_OU_SetACL`, `AD_Permissions_Randomizer`, `AD_LAPS_Install`, `AD_Groups_Create`, `AD_Users_Create`, `AD_Computers_Create`. **All-or-nothing**, no per-vuln toggle, **no rollback documented**.

**Stealable.** The category split (groups / users / computers / ACL / LAPS) is a sensible breakdown for AD object misconfigs. The "fills with thousands of objects" pattern is useful as a single bolt-on of category *Identity Surface Generation*.

**To avoid.** No rollback. Not idempotent. PowerShell-only restricts us if we need cross-platform support later. We will wrap BadBlood as one selectable role (`bolton.badblood` with toggles per submodule), not as the architecture itself.

### 2.4 LOAD (Lord of Active Directory) — https://github.com/0xBallpoint/LOAD

The closest existing analog. AWS + Terraform + Ansible (same stack as us). Three interconnected domains. Modular Ansible playbooks executed in sequence:

| Playbook | Purpose |
|---|---|
| `prepare.yml` | OS updates |
| `ad-servers.yml` | DC setup |
| `ad-trusts.yml` | Inter-domain trusts |
| `ad-data.yml` | User/group imports |
| `ad-groups.yml` | Group memberships, permissions |
| `servers.yml` | IIS, MSSQL |
| `adcs.yml` | ADCS + ESC1, 2, 3, 4, 8 templates |
| `ad-acl.yml` | DACL/ACE config |
| `linux.yml` | GLPI Linux endpoint |
| `security.yml` | Windows Defender controls |
| `vulnerabilities.yml` | scenario-specific weaknesses |
| `vpn.yml` | optional WireGuard |

**Stealable.** Direct evidence the playbook-per-vuln-family model works in production on AWS. The `adcs.yml` style — one playbook owns ADCS, takes flags for which ESCs to enable — is exactly the role granularity we want.

**To avoid.** Dependencies are implicit (encoded in the run order, not declared) — operators must "maintain this order or execute plays individually if understanding prerequisites." That is a step backward from what we want. We need *declarative* deps.

### 2.5 Ludus (Bad Sector Labs) — https://docs.ludus.cloud + https://github.com/badsectorlabs

**The architectural reference for this plan.** Ludus is a self-hosted cyber range manager that already implements 90% of what we are building, with a clean YAML schema and a thriving role ecosystem.

**Range-config YAML** (paraphrased from docs):

```yaml
ludus:
  - vm_name: "{{ range_id }}-dc01"
    hostname: "DC01"
    template: win2022-server-x64-template
    vlan: 10
    ip_last_octet: 10
    ram_gb: 8
    cpus: 4
    windows:
      domain:
        fqdn: lab.local
        role: primary-dc
    roles:
      - badsectorlabs.ludus_adcs
    role_vars:
      ludus_adcs_esc1: true
      ludus_adcs_esc8: true
```

Role-level `depends_on`:

```yaml
roles:
  - name: badsectorlabs.ludus_elastic_agent
    depends_on:
      - vm_name: "{{ range_id }}-elastic"
        role: badsectorlabs.ludus_elastic_container
```

**Stealable — heavily.**

- `roles` array per VM + `role_vars` dict + `depends_on` list — adopt verbatim, rename `ludus_*` → `bolton_*`.
- `ludus ansible role add <galaxy-name>` for installing third-party role into the server — gives us a clean contribution model (drop a Galaxy role name, server pulls it).
- Per-user role isolation — translates to per-operator attribution; the `g.operator` middleware already gives us this.
- The Ludus ADCS role's `ludus_adcs_esc1 .. ludus_adcs_esc16` toggle pattern → adopt 1:1 (we don't need to reimplement ADCS; we can install the Ludus role and wrap it). Their note "this role is not idempotent — toggling esc1 false will NOT remove" is a known limitation we will fix in our wrapper by writing a real cleanup playbook.

**To avoid.** Ludus runs on Proxmox VMs — we are on AWS EC2. The role contract is portable (Ansible is Ansible) but Ludus-specific facts (`range_id`, Proxmox networking) need to be stubbed for AWS.

### 2.6 Splunk Attack Range — https://github.com/splunk/attack_range

Terraform + Ansible for AWS/Azure/GCP. Integrates Atomic Red Team for attack simulation. Has an `attack_data` directory (catalog), `config/<id>.yml` per range, `templates/{aws,azure,gcp}/`. Three control planes: Docker Compose, web UI, REST API + CLI.

**Stealable.** The web UI + REST API + CLI triad — proves the same backend can serve all three. Our existing `webapp/backend/routes/*.py` is already this shape; we extend it.

**To avoid.** Attack simulation is *post-deployment offensive action*, not *vulnerability installation*. They are downstream of what we are building. Reusable as the next layer (after a vuln is installed, run an Atomic against it to confirm it fires expected detections).

### 2.7 Atomic Red Team — https://github.com/redcanaryco/atomic-red-team

1,797 atomic tests, organized by MITRE ATT&CK technique (`atomics/T1003.001/T1003.001.yaml`). **The reference for our YAML descriptor shape.**

```yaml
attack_technique: T1003.001
display_name: "OS Credential Dumping: LSASS Memory"
atomic_tests:
  - name: <string>
    auto_generated_guid: <uuid>
    description: <multiline string>
    supported_platforms: [windows]
    input_arguments:
      <arg>:
        description: <string>
        type: path | string | url | integer | float
        default: <value>
    dependency_executor_name: powershell
    dependencies:
      - description: <string>
        prereq_command: <script>     # checks if dep exists
        get_prereq_command: <script> # installs dep if missing
    executor:
      name: command_prompt | powershell | bash | sh | manual
      elevation_required: true | false
      command: <script>
      cleanup_command: <script>
```

**Stealable.** Every field. `prereq_command` / `get_prereq_command` is the cleanest precondition pattern in the survey — adopt directly. Input arguments make tests parameterizable. Cleanup is first-class.

**To avoid.** Their atomics are *exploits/tests*, not *installations*. We are inverting the polarity: install the condition, then verify with something Atomic-test-like. So a bolt-on descriptor will reference an Atomic test by ID as its **verification probe**, but the install body is bespoke.

### 2.8 MITRE Caldera — https://github.com/mitre/caldera, https://caldera.readthedocs.io

Plugin-extensible adversary emulation. Core terms: *Agent* (paw-id'd endpoint), *Ability* (single technique, YAML), *Adversary* (group of abilities), *Operation* (run abilities on agents against an adversary profile using a *Planner*), *Plugin* (extensions). Abilities chain via **facts** — output of one ability is parsed into facts that satisfy requirements for the next. No explicit `depends_on`; dependency is implicit via fact availability.

**Stealable.** Plugin model. The *Adversary = group of abilities* idea maps to our **Scenarios** primitive (e.g. an "ESC1 + Kerberoast Chain" scenario bundles vulns into one drag).

**To avoid.** Fact-based chaining is brittle for declarative installation. We will use explicit `depends_on` (Ludus pattern) instead.

### 2.9 vulhub — https://github.com/vulhub/vulhub

Docker-Compose-per-CVE. ~200+ entries. Path layout: `<software>/<CVE-id>/docker-compose.yml`. Per-environment README. No machine-readable catalog index, no inter-vuln dep model.

**Stealable.** Path-as-identity (`<category>/<id>`). Inclusion of CVE ID as primary key. The container-based isolation pattern is useful for **web app vulns and software-CVE bolt-ons** that don't belong on the DC itself — we can deploy them onto a domain-joined Linux member.

**To avoid.** No catalog index means consumers have to scrape directory listings. We will maintain a real `index.yaml`.

### 2.10 DetectionLab — https://github.com/clong/DetectionLab (deprecated 2023-01-01)

Vagrant + Terraform + Ansible + Packer. Pre-configured logging stack (Splunk, Sysmon, osquery, WEF). Vulnerabilities are baked into provisioning, not addable post-deploy. **Project archived.**

**Stealable.** Mostly nothing for bolt-on architecture itself. But: their host-categorization (DC / WEF collector / member / monitoring) maps to **target role** in our schema.

**To avoid.** Deprecated; do not depend on it.

### 2.11 Vulnerable-AD — https://github.com/safebuffer/vulnerable-AD

PowerShell DC script that injects: ACL abuse, Kerberoast, AS-REP, DnsAdmins abuse, passwords-in-description, default `Changeme123!`, password spray surface, DCSync, Silver/Golden ticket, PtH, PtT, SMB signing disabled. All-or-nothing, single `Invoke-VulnAD` entry.

**Stealable.** The list of weaknesses is a near-perfect bolt-on **bundle** for an introductory training scenario. Wrap as a single bolt-on (`bolton.vulnad_classic`) with a flag to enable/disable subcomponents.

**To avoid.** All-or-nothing. Not idempotent. Wrap, don't adopt as-is.

### 2.12 Projects checked but not central

- **PurpleSharp** (https://github.com/mvelazc0/PurpleSharp) — adversary simulation, sibling to Atomic Red Team. Useful for verification probes; not for install.
- **Microsoft Defend The Flag** — instructor-led Azure labs. Closed source. No stealable primitives.
- **HackTheBox Sherlocks / BOTS** — pre-built lab delivery models. SaaS / dataset-style. Inform our **scenario-as-bundle** UX but don't map to install architecture.

### 2.13 Four headline takeaways

1. **Ludus's range-config YAML + Ansible role + `depends_on`** is the single best architectural reference. We borrow heavily.
2. **Atomic Red Team's per-test YAML schema** (input_arguments, prereq_command, executor with cleanup) is the cleanest descriptor format. We borrow the shape.
3. **Rogue Architect's drag-from-catalog-onto-host UX** validates that operators want a visual scenario builder. We replicate the interaction, not the proprietary backend.
4. **Caldera's adversary = bundle of abilities** gives us "Scenarios" as a UX layer above individual vulns.

---

## 3. Vulnerability taxonomy

Ten top-level categories, each with named subcategories and concrete vulnerabilities. Every entry annotated with: typical target (DC / member server / workstation / web app / network / container), install complexity (low/med/high), detectability (loud/quiet), notable dependencies.

### 3.1 Identity & Kerberos misconfigurations

| Subcategory | Concrete vuln | Target | Complexity | Detect | Deps |
|---|---|---|---|---|---|
| Kerberoasting | Kerberoastable service account (`servicePrincipalName` on user with weak password) | DC (creates account) | low | quiet | none |
| AS-REP Roasting | `DONT_REQ_PREAUTH` flag on user | DC | low | quiet | none |
| Constrained delegation | `msDS-AllowedToDelegateTo` on user/computer | DC | med | loud | computer must exist |
| Unconstrained delegation | `TRUSTED_FOR_DELEGATION` flag on computer | DC | med | loud | computer must exist |
| Resource-based constrained delegation | `msDS-AllowedToActOnBehalfOfOtherIdentity` write | DC | med | quiet | computer + user must exist |
| Weak password policy | min length 4, no complexity, no lockout | DC | low | quiet | none |
| Plaintext password in description | service account with creds in `description` | DC | low | quiet | none |
| Default credentials | bulk users with `Changeme123!` | DC | low | quiet | none |
| Password spray surface | 100s of accounts with predictable seasonal password | DC | low | loud | none |
| DCSync rights to non-admin | extend DACL with `DS-Replication-Get-Changes-All` | DC | med | quiet | target user must exist |
| Pre-Windows 2000 compatible access | add Authenticated Users to group | DC | low | quiet | none |

### 3.2 Access control (DACL/ACE abuse, AdminSDHolder, group nesting)

| Subcategory | Concrete vuln | Target | Complexity | Detect | Deps |
|---|---|---|---|---|---|
| AdminSDHolder write | grant FullControl on `CN=AdminSDHolder,...` to non-admin | DC | high | loud | none |
| GenericAll on user | grant non-admin GenericAll to a privileged user | DC | low | quiet | target user exists |
| GenericWrite + SPN | grant GenericWrite so attacker can add SPN | DC | med | quiet | target user exists |
| WriteDACL on OU | write DACL on OU containing privileged accounts | DC | med | quiet | OU exists |
| ForceChangePassword right | extended right on a privileged user | DC | low | quiet | target user exists |
| Group nesting (Domain Users → tier-0) | nest "Domain Users" into a privileged group two levels deep | DC | low | quiet | privileged group exists |
| Owner abuse | change owner of object to a low-priv user | DC | low | quiet | object exists |
| Tier-0 sprawl | service account in Domain Admins | DC | low | quiet | none |

### 3.3 ADCS / Certificate Services (ESC1–16)

We wrap the existing `badsectorlabs.ludus_adcs` role (see §2.5) and expose each ESC as a toggle. Concrete entries:

| ID | What it is | Target | Complexity | Detect | Deps |
|---|---|---|---|---|---|
| ESC1 | Cert template with `ENROLLEE_SUPPLIES_SUBJECT` + client auth EKU + enrollable by low-priv | DC + CA host | med | quiet | ADCS installed |
| ESC2 | Cert template with `Any Purpose` EKU | CA host | med | quiet | ADCS |
| ESC3 | Enroll On Behalf Of misconfig | CA host | med | quiet | ADCS |
| ESC4 | Write DACL on a cert template | CA host | low | quiet | ADCS |
| ESC5 | Vulnerable PKI object DACLs | CA host | med | quiet | ADCS |
| ESC6 | `EDITF_ATTRIBUTESUBJECTALTNAME2` flag on CA | CA host | low | quiet | ADCS |
| ESC7 | Vulnerable CA Manager access | CA host | med | quiet | ADCS |
| ESC8 | HTTP Web Enrollment + NTLM relay surface | CA host | high | loud | ADCS, web enrollment |
| ESC9 | `CT_FLAG_NO_SECURITY_EXTENSION` on template | CA host | med | quiet | ADCS |
| ESC10 | Registry-driven cert mapping (weak) | DC | med | quiet | ADCS |
| ESC11 | NTLM relay to ICPR (RPC) | CA host | high | loud | ADCS |
| ESC13 | Issuance policy linked to privileged group | CA host | med | quiet | ADCS |
| ESC14 | Weak explicit cert mapping | DC | med | quiet | ADCS |
| ESC15 | Arbitrary application policy injection (CVE-2024-49019) | CA host | med | quiet | ADCS |
| ESC16 | Disabled security extension policy | CA host | med | quiet | ADCS |

Note: ESC12 (shell access via YubiHSM) is intentionally omitted — physical-token dependent, out of scope.

### 3.4 Known-CVE software vulnerabilities

| Vuln | CVE | Target | Complexity | Detect | Deps |
|---|---|---|---|---|---|
| EternalBlue | CVE-2017-0144 | unpatched Server 2008/2012 SMBv1 | high | loud | need legacy Windows image (replace AMI) |
| PrintNightmare | CVE-2021-1675 + CVE-2021-34527 | DC or member with Spooler service + specific patch level | med | loud | rollback patches; risky |
| ZeroLogon | CVE-2020-1472 | DC with August 2020 patch reverted | high | loud | rollback patches; **NEVER on prod-adjacent** |
| NoPac (sAMAccountName spoofing) | CVE-2021-42278 + CVE-2021-42287 | DC | med | quiet | patch state |
| PetitPotam | CVE-2021-36942 | DC EFS-RPC | low | loud | none |
| HiveNightmare / SeriousSAM | CVE-2021-36934 | workstation | low | loud | SAM file readable to non-admin |
| Spoolfool | CVE-2022-21999 | Spooler | low | loud | none |
| sAMSpoofing relayed cred theft | n/a | DC | high | loud | NTLM relay infra |

### 3.5 Web application vulnerabilities

Containerized on a domain-joined Linux member (via vulhub pattern). Examples:

| Vuln | Vector | Target | Complexity | Detect | Deps |
|---|---|---|---|---|---|
| DVWA classic | SQLi, XSS, CSRF, file upload, CMD injection | Linux member | low | loud | docker |
| GLPI SQL injection (LOAD-style) | SQL injection on auth endpoint | Linux member | low | loud | docker |
| Log4Shell (CVE-2021-44228) | JNDI lookup in vuln Java app | Linux member | med | loud | docker, vuln Java app image |
| Tomcat default creds + JSP upload | manager-gui | Linux member | low | loud | docker |
| Confluence template injection (CVE-2023-22515) | CVE | Linux member | med | loud | docker |
| WordPress with vuln plugin chain | RCE chain | Linux member | low | loud | docker, mysql |
| GitLab arbitrary file read (CVE-2023-2825) | CVE | Linux member | low | loud | docker |

### 3.6 Protocol / network surface

| Vuln | Target | Complexity | Detect | Deps |
|---|---|---|---|---|
| LLMNR / NBT-NS enabled (default) | all Windows | low | loud | none |
| IPv6 stateless autoconfig + mitm6 surface | all Windows | low | loud | none |
| SMB signing disabled | member servers | low | loud | none |
| LDAP signing not enforced | DC | low | quiet | none |
| WPAD over DHCP | workstation | low | loud | none |
| WinRM HTTP (not HTTPS) | member | low | quiet | none |
| Insecure DNS (dynamic updates allowed by unauthenticated) | DC | low | quiet | none |
| Print spooler running on DC | DC | low | quiet | none |

### 3.7 Credential exposure

| Vuln | Target | Complexity | Detect | Deps |
|---|---|---|---|---|
| GPP cpassword in SYSVOL (MS14-025 reverted) | DC | med | loud | GPO write |
| LAPS misconfigured (readable by Everyone) | DC | low | quiet | LAPS installed |
| LAPS not deployed (all local-admin same password) | members | low | quiet | none |
| Service account password in registry | member | low | quiet | none |
| Plaintext creds in scheduled task | member | low | quiet | none |
| Creds in `cmdkey` / Credential Manager | workstation | low | quiet | none |
| Creds in SCCM Network Access Account | SCCM (SCCM lab only) | high | quiet | SCCM installed (already in our `goad-sccm`) |

### 3.8 Service misconfigurations

| Vuln | Target | Complexity | Detect | Deps |
|---|---|---|---|---|
| MSSQL trusted DB links (xp_cmdshell enabled) | member with MSSQL | med | loud | MSSQL installed |
| MSSQL sysadmin to a low-priv user | member with MSSQL | low | quiet | MSSQL installed |
| IIS with anonymous + write enabled | member with IIS | low | loud | IIS installed |
| Unquoted service path with writeable directory | member | low | quiet | none |
| Service binary writable by non-admin (DACL) | member | low | quiet | none |
| SeImpersonatePrivilege on IIS app pool (PrintSpoofer / JuicyPotato) | member with IIS | med | loud | IIS installed |
| WSUS over HTTP (Sherlock/Magnitude) | member | high | loud | none |

### 3.9 Cloud / container misconfigurations

| Vuln | Target | Complexity | Detect | Deps |
|---|---|---|---|---|
| Docker socket exposed | Linux member | low | quiet | docker |
| Vulnerable Kubernetes pod (privileged + hostPath /) | Linux member | med | quiet | k3s/minikube |
| AWS IMDSv1 enabled + over-permissive role | any EC2 (already partially true in GOAD) | low | quiet | IAM |
| S3 bucket public + secrets | n/a (cloud) | low | quiet | bucket exists |
| Secrets in EC2 user-data | any EC2 | low | quiet | none |

### 3.10 Endpoint / phishing surfaces

| Vuln | Target | Complexity | Detect | Deps |
|---|---|---|---|---|
| Outlook autodiscover misconfig | workstation | med | loud | Outlook installed |
| Office macros allowed (no warning) | workstation | low | quiet | Office installed |
| LNK auto-execution via Desktop drop | workstation | low | loud | none |
| AppLocker / WDAC absent | workstation | low | quiet | none |
| Defender exclusions wide (e.g. `C:\`) | workstation | low | quiet | none |
| AMSI bypass-friendly PowerShell config | workstation | low | quiet | none |
| RDP NLA disabled | workstation | low | loud | none |

**Total taxonomy: 10 categories, 80 named vulnerabilities** (excluding ESC12 which is out-of-scope).

---

## 4. Vulnerability data schema

The descriptor lives at `bolton/catalog/<category>/<slug>.yaml`. Shape, formalized below, with one fully worked example.

### 4.1 Schema (annotated)

```yaml
# bolton/catalog/identity-kerberos/kerberoastable-svc.yaml

# ── Identity ─────────────────────────────────────────────────────────
id: bolton.identity.kerberoastable-svc      # globally unique, dotted
slug: kerberoastable-svc                    # filename-safe
name: "Kerberoastable Service Account"      # display
version: "1.0.0"                            # semver of descriptor + role
schema_version: 1                           # of this schema format itself

# ── Categorization ───────────────────────────────────────────────────
category: identity-kerberos                 # one of the 10 in §3
subcategory: kerberoasting
mitre_attack:
  - tactic: TA0006                          # Credential Access
    technique: T1558.003                    # Kerberoasting
cve: []                                     # empty for misconfigs
references:
  - "https://attack.mitre.org/techniques/T1558/003/"
  - "https://www.thehacker.recipes/ad/movement/kerberos/kerberoast"

# ── Targeting ────────────────────────────────────────────────────────
targets:
  supported_os:                             # OS-level constraint
    - { family: windows, min_version: "2016", max_version: "2022" }
  required_roles:                           # logical role required
    - dc                                    # one of dc | member | workstation | linux-member | ca-host
  required_services: []                     # e.g. ['adcs', 'mssql', 'iis']
  compatible_labs:                          # which of our 5 GOAD flavors
    - goad-mini
    - goad-light
    - goad-sccm
    - goad-full
    - goad-nha

# ── Dependencies ─────────────────────────────────────────────────────
depends_on:                                 # other bolt-ons that MUST be installed first
  - id: bolton.identity.weak-password-policy
    reason: "service account password must be weak enough to crack"
    optional: false
conflicts_with:                             # CANNOT coexist
  - id: bolton.identity.strong-password-policy
    reason: "directly inverse policies"

# ── Side effects ─────────────────────────────────────────────────────
side_effects:
  global:                                   # changes that affect domain-wide state
    - "creates user 'svc_kerb_<random>' in CN=Users"
    - "sets servicePrincipalName 'HTTP/kerb-target.<domain>' on that user"
  per_host: []
  reversible: true

# ── Install ──────────────────────────────────────────────────────────
install:
  engine: ansible                           # ansible | bash | powershell | composite
  role: bolton_identity_kerberoastable_svc  # name of role under bolton/roles/
  inputs:
    spn_value:
      description: "SPN string to set on the account"
      type: string
      default: "HTTP/kerb-target.{{ domain_fqdn }}"
    account_password:
      description: "Cleartext password (weak)"
      type: string
      default: "Summer2025!"
    account_username:
      description: "sAMAccountName for the service account"
      type: string
      default: "svc_kerb_{{ short_random() }}"
  pre_check:                                # ARC-style prereq_command
    description: "Verify DC is reachable and AD module is loaded"
    command: |
      Import-Module ActiveDirectory
      Get-ADDomain
    on_fail: install_prereq                 # install_prereq | abort | warn
  get_prereq:                               # how to install the prereq if pre_check fails
    description: "Install RSAT-AD-PowerShell"
    command: "Install-WindowsFeature -Name RSAT-AD-PowerShell"
  elevation_required: true
  estimated_install_seconds: 30

# ── Verification probe ───────────────────────────────────────────────
verify:
  description: "Confirm the account exists, has an SPN, and is Kerberoastable"
  engine: ansible
  command: |
    Get-ADUser -Filter "sAMAccountName -eq '{{ install.inputs.account_username.default }}'" -Properties ServicePrincipalName |
      Where-Object { $_.ServicePrincipalName -ne $null }
  expect:
    exit_code: 0
    stdout_contains: "{{ install.inputs.spn_value.default }}"
  external_probe:                           # optional — run from attack box
    description: "Request a TGS for the SPN from the attack box; assert encryption type is RC4 or AES with crackable hash"
    engine: bash
    command: |
      impacket-GetUserSPNs -dc-ip {{ dc_ip }} {{ domain_fqdn }}/{{ test_user }}:{{ test_password }} -request
    expect:
      stdout_contains: "$krb5tgs$"

# ── Cleanup / rollback ───────────────────────────────────────────────
cleanup:
  description: "Remove the service account and SPN"
  engine: ansible
  command: |
    Remove-ADUser -Identity '{{ install.inputs.account_username.default }}' -Confirm:$false
  verify_cleanup:
    description: "Account no longer exists"
    command: |
      Get-ADUser -Filter "sAMAccountName -eq '{{ install.inputs.account_username.default }}'"
    expect:
      stdout_empty: true

# ── Detection profile ────────────────────────────────────────────────
detection:
  profile: quiet                            # quiet | medium | loud
  signal_sources:                           # log sources that touch this vuln
    - "Windows Event 4720 (User account created)"
    - "Windows Event 4738 (User account changed)"
    - "Windows Event 5136 (Directory Service object modified — SPN write)"
  elastic_rules_suggested:                  # links to our existing Elastic integration
    - "Suspicious Service Account Creation"
    - "SPN Modification on User Account"

# ── Cost / resource impact ───────────────────────────────────────────
resource_impact:
  new_aws_resources: []                     # this one installs onto existing host; no new EC2
  estimated_monthly_cost_usd_delta: 0
  disk_delta_mb: 0
  ram_delta_mb: 0

# ── Authorship & lifecycle ───────────────────────────────────────────
author: "Red Team Infra"
maintainer: "operator@example.com"
created: "2026-05-18"
updated: "2026-05-18"
license: "MIT"
status: stable                              # stable | beta | experimental | deprecated
known_issues: []
```

### 4.2 Worked example: ADCS ESC1 (cross-check)

Because ESC1 is more complex than the Kerberoastable example, an abbreviated form:

```yaml
id: bolton.adcs.esc1
category: adcs
subcategory: esc1
name: "ADCS ESC1 — Enrollee Supplies Subject (Client Auth)"
mitre_attack: [{ tactic: TA0004, technique: T1649 }]
targets:
  required_roles: [ca-host]
  required_services: [adcs]
  compatible_labs: [goad-light, goad-sccm, goad-full, goad-nha]
depends_on:
  - id: bolton.adcs.install-adcs
    reason: "ADCS role and CA must exist"
install:
  engine: ansible
  role: badsectorlabs.ludus_adcs            # wrap existing role
  inputs:
    ludus_adcs_esc1: { type: bool, default: true }
verify:
  external_probe:
    command: |
      certipy-ad find -u {{ test_user }} -p {{ test_pw }} -dc-ip {{ dc_ip }} -vulnerable -stdout
    expect:
      stdout_contains: "ESC1"
cleanup:
  description: "Remove the ESC1-vulnerable template"
  command: |
    Remove-CATemplate -Name "ESC1-Vulnerable" -Force
```

---

## 5. Dependency / conflict resolution

### 5.1 Graph semantics

- **Vertices:** descriptors (`bolton.*`) currently installed OR proposed for install on a given host scope.
- **Edges:** `depends_on` (directed: A → B means "B must be installed before A"), `conflicts_with` (bidirectional exclusion).
- **Scope:** per-lab. Some deps target other hosts (e.g. `bolton.adcs.esc8` may require an HTTP listener on the CA host, but a relay-target host elsewhere). The dep edge carries an optional `target_host_role`.

### 5.2 Resolver algorithm

```
function resolve(installed: Set, requested: List<vuln>) -> InstallPlan | Error
  # 1. Build proposed final state
  proposed = installed ∪ requested

  # 2. Conflict check
  for each pair (A, B) in proposed:
    if A.conflicts_with contains B.id OR B.conflicts_with contains A.id:
      return Error.ConflictDetected(A, B)

  # 3. Build DAG of all requested + their transitive deps
  deps_graph = {}
  for v in requested:
    walk v.depends_on recursively, adding edges
    if any dep refers to a vuln in conflicts_with proposed final state:
      return Error.UnsatisfiableDep(v, dep)

  # 4. Cycle check
  if cycle_exists(deps_graph):
    return Error.CycleInDeps(cycle_path)

  # 5. Topological sort → install order
  order = topo_sort(deps_graph)

  # 6. Per-host grouping: serialize within host, parallelize across hosts
  per_host_plan = group_by(order, key=v.target_host)

  return InstallPlan(per_host_plan, order)
```

### 5.3 Partial failure handling

- If step N fails install + verification + agentic-fallback, the resolver halts and surfaces:
  - Successfully-installed steps 1..N-1 (remain in place — operator can choose to roll back via UI).
  - The failed step with full logs.
  - Skipped subsequent steps (with reason: "blocked by failed dep").

### 5.4 UX implications

- After drag-drop, the dashboard **always shows the resolved plan in a takeover** before dispatching install. Operator sees: "Installing X on dc01 requires also installing Y on dc01 and Z on ca-host first. Proceed?"
- Batch install vs one-at-a-time: support both. One-at-a-time is the default for safety; batch enabled by an explicit "Plan & install all" button after explicit confirmation.
- Cycle errors are rare in practice (descriptors are authored, not user-generated); when one occurs the UI shows the cycle path explicitly so the descriptor author can fix it.

---

## 6. Install engine architecture

### 6.1 Dispatch path

Reuse what works. The existing path: `webapp/backend/routes/goad.py::provision_goad()` SSH'es to the jumpbox and runs `ansible-playbook` under `nohup` with a remote PID file and exit-code file. Bolt-on installs follow the **exact same pattern**:

```
operator clicks install in dashboard
  → POST /api/labs/<lab>/hosts/<host>/install
  → backend constructs ad-hoc playbook (bolton-runner.yml) that:
      - imports the bolt-on role
      - sets role_vars from descriptor inputs
      - targets the specific host
  → SSH to jumpbox, scp the playbook, run via nohup, log to /home/ubuntu/bolton-<job-id>.log
  → return job_id immediately
  → frontend polls GET /api/jobs/<job-id> for status + tail log
```

The ad-hoc playbook is generated server-side from a Jinja template (`webapp/backend/templates/bolton_runner.yml.j2`).

### 6.2 Why Ansible and not direct SSM / WinRM

- We already run Ansible on the jumpbox for GOAD initial provisioning. Operators have the inventory, keys, and Python env there.
- Ansible Windows modules cover the 80% case (`win_user`, `win_group`, `win_domain_user`, `win_acl`, `win_regedit`, `win_feature`).
- SSM works for one-off commands but lacks Ansible's idempotency, retry, and rollback semantics.
- For Linux container vulns (vulhub-style), we use the same Ansible from the jumpbox to `docker compose up` on a Linux member.

### 6.3 State tracking

A per-lab state file on the dashboard server: `webapp/state/labs/<lab-name>/installed.json`. Shape:

```json
{
  "lab": "goad-light",
  "installed": [
    {
      "vuln_id": "bolton.identity.kerberoastable-svc",
      "version": "1.0.0",
      "host": "dc01",
      "installed_at": "2026-05-18T10:30:00Z",
      "installed_by": "operator@example.com",
      "job_id": "job_abc123",
      "inputs_used": { "spn_value": "HTTP/kerb-target.sevenkingdoms.local", "account_username": "svc_kerb_x7q" },
      "verified": true,
      "cleanup_available": true
    }
  ]
}
```

This file is the source of truth for "what is installed where" and is read by the catalog UI to disable already-installed items, and by the topology view to render host annotations.

### 6.4 Concurrency

- Per-host lock file: `webapp/state/labs/<lab>/locks/<host>.lock`. Held for the duration of an install/cleanup job.
- Lock attempt returns 409 with the holder's operator name + job_id.
- Locks expire if the holder's job is stale > install timeout × 2.

### 6.5 Idempotency

- Every descriptor's `install.role` MUST be idempotent (re-running yields no change). This is mandatory per Ansible style and we enforce it in CI by running each role twice and asserting `changed=0` on the second run (à la molecule).
- If the state file already shows the vuln installed at the requested version, the dashboard refuses dispatch and offers "Reinstall" / "Skip".

### 6.6 Composite installs

Some descriptors need both Ansible **and** a follow-up step from the attack box (e.g. external verification probe). These are described as `engine: composite`:

```yaml
install:
  engine: composite
  steps:
    - { engine: ansible, role: bolton_adcs_esc8 }
    - { engine: bash, target: attack_box, command: "echo 'ESC8 ready'" }
```

The dispatcher executes steps in order, on the right host, with per-step retries.

---

## 7. Agentic fallback workflow

The non-trivial part. Goal: when scripted install fails, surface to an agent that can diagnose and propose a fix, while keeping the human in the loop.

### 7.1 When the agent is invoked

The Ansible role exits non-zero **or** the `verify` probe fails. The job state transitions to `STUCK` rather than `FAILED`. The dashboard shows an "Invoke Agent" button.

Optionally, on a per-vuln flag (`auto_agent_on_fail: true`), the agent is invoked automatically — useful for known-flaky descriptors where the install often needs a small fix-up (e.g. ADCS template issuance is async; sometimes a retry after 30s succeeds).

### 7.2 What the agent receives

A structured prompt context:

```yaml
job:
  id: job_abc123
  vuln: bolton.adcs.esc1
  host: ca01
  lab: goad-light
  attempt: 1

descriptor:
  <full YAML of the descriptor>

run_log:
  ansible_stderr: <last 200 lines>
  ansible_stdout: <last 200 lines>
  exit_code: 2
  verify_output: <stdout + stderr of verify probe>

host_facts:
  os: Windows Server 2019
  domain: sevenkingdoms.local
  roles_installed: [dc, adcs]
  recent_events: <last 20 relevant Windows event log entries>

policy:
  allowed_actions: [retry_with_modified_inputs, run_diagnostic_command, request_operator_input]
  forbidden_actions: [bypass_verify, install_unrelated_vuln, modify_descriptor, ssh_to_other_hosts]
  max_iterations: 3
```

### 7.3 What the agent is allowed to do

A bounded action surface (tools the agent calls):

| Tool | Purpose | Bounds |
|---|---|---|
| `run_diagnostic_command(host, command)` | Read-only Windows/Linux command on the target host | Whitelist: `Get-*`, `certutil -ping`, `klist`, `nltest`, `Get-CATemplate`, `ipconfig`, `eventvwr` queries; no `Set-*`, no `Remove-*` |
| `retry_install(modified_inputs)` | Re-dispatch the install with different `inputs` values | Must justify the change; modified inputs validated against descriptor schema |
| `request_operator_input(question)` | Ask the operator a question, pause job | Free-text; surfaces in UI as a chat-style prompt |
| `mark_failed(reason)` | Give up; surface explanation to operator | Always allowed |

The agent **cannot**:

- Modify the descriptor YAML itself (only the operator can; the agent can suggest a PR-like diff in its `mark_failed` reason).
- SSH/run commands on hosts other than the target.
- Skip the verification probe.
- Install something not in the explicit allowed plan.

### 7.4 Safety rails

- Every action the agent takes is logged with timestamp, action, args, result.
- A hard limit of 3 iterations per job (configurable per descriptor).
- A cumulative time budget per job (default 5 minutes of agent wall-clock).
- The agent runs against the **target host only** via the existing SSH-to-jumpbox-then-WinRM/SSH path; never directly internet-facing.
- All retries pass through the same install + verify path — the agent cannot bypass verification.

### 7.5 Operator UX

A "stuck job" surface inside the install progress modal:

```
┌────────────────────────────────────────────────────────────────────┐
│ Installing bolton.adcs.esc1 on ca01    [STUCK — agent investigating]│
├────────────────────────────────────────────────────────────────────┤
│ STDERR (Ansible):                                                  │
│ │ TASK [Configure ESC1 template] *** FAILED                       │
│ │ "Certificate template name already exists with conflicting ACE" │
├────────────────────────────────────────────────────────────────────┤
│ AGENT (iter 1/3):                                                  │
│ │ I ran: Get-CATemplate -Name "ESC1-Vulnerable"                   │
│ │ Output: template exists from a prior install attempt that was   │
│ │ rolled back partially. Suggesting retry with --force flag set.  │
│ │ [Retry with modified inputs]   [Reject suggestion]              │
└────────────────────────────────────────────────────────────────────┘
```

The operator approves each suggested retry (or the system auto-approves if `auto_agent_on_fail` is set and the action is in the read-only or retry-with-same-inputs subset).

### 7.6 Audit logging

Every agent intervention writes to `webapp/state/audit/bolton_agent.jsonl`. Schema:

```json
{"ts":"...","job_id":"...","operator":"...","action":"retry_install","modified_inputs":{...},"reasoning":"...","outcome":"success|failed"}
```

This stream is queryable via an existing dashboard audit endpoint.

### 7.7 Model choice

Claude API (project already uses Anthropic SDK, see CLAUDE.md `claude-api` skill). Configurable via `BOLTON_AGENT_MODEL` env var. Token budget: input ~10K, output ~2K per iteration; well within reasonable cost.

Prompt caching enabled on the static portion (descriptor YAML + tool definitions) so iteration 2 and 3 only pay for delta tokens.

### 7.8 Phase 3a implementation status

Phase 3a (this revision) ships the real agent invocation end-to-end:

- `webapp/backend/services/bolton_agent_service.py` — `invoke_agent(job_id, operator) -> AgentProposal`.
- Bounded tool surface: 9 read-only diagnostics (`read_event_log`, `check_service_status`, `list_installed_kbs`, `check_ad_object`, `check_ad_ca_template`, `list_certificate_templates`, `check_kerberos_tickets`, `check_domain_trusts`, `test_network_path`). Tool dispatch is a single Python dict that maps tool name → `(ansible_module, command_template)`.
- Hard limits enforced server-side: `MAX_TOOL_INVOCATIONS = 3`, `MAX_WALL_CLOCK_SECONDS = 300`. The agent loop checks both every iteration — the model cannot self-regulate past them.
- Routes: `POST /api/bolton/jobs/<job_id>/agent-intervene` returns the proposal; `POST /agent-approve` dispatches the retry; `POST /agent-reject` audits the rejection. Job stays STUCK on reject — no implicit state transition.
- `bolton_install_service.retry_with_modifications(job_id, modifications, operator)` re-queues a STUCK job with descriptor input overrides, skipping the compatibility backstop (the original dispatch already cleared it).
- Frontend: `APP.bolton._showAgentPanel(jobId)` appends a panel inside the install progress overlay when a job hits STUCK. Operator approves → retry dispatch; rejects → panel closes, audit-only.

### 7.9 Operator configuration

The agent requires an Anthropic API key. **It is never bundled with the dashboard image** — operators wire their own key per deployment.

#### Obtaining a key

1. Sign in at <https://console.anthropic.com>.
2. **Settings → API Keys → Create Key**.
3. Scope: workspace-level, role `developer`. Name it after the operator (audit trail).
4. Copy the `sk-ant-...` literal — Anthropic only displays it once.

#### Setting `ANTHROPIC_API_KEY`

Three supported deployment patterns, in order of preference:

**A — Dashboard server systemd drop-in (preferred for production):**

```bash
# On the dashboard EC2:
sudo systemctl edit dashboard.service
# Add:
[Service]
Environment="ANTHROPIC_API_KEY=sk-ant-..."
sudo systemctl restart dashboard.service
```

The override lives at `/etc/systemd/system/dashboard.service.d/override.conf` — readable only by root. Survives reboots; rotates without code changes.

**B — AWS Secrets Manager (preferred for multi-operator deployments):**

```bash
aws secretsmanager create-secret \
  --name red-team/dashboard/anthropic-api-key \
  --secret-string "sk-ant-..."
```

Then in the dashboard server's IAM role attach `secretsmanager:GetSecretValue` for that ARN, and have `dashboard-manage.sh start` pull the secret + export it before exec'ing the Flask process (existing pattern from the bastion-secret path).

**C — Local development `.env` (NOT for production):**

```bash
# In the project root, never committed (already in .gitignore):
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> .env
source .env
python -m webapp.backend.app
```

#### Optional: model override

`BOLTON_AGENT_MODEL` overrides the default Claude model. The default tracks the current Sonnet snapshot suitable for diagnostic reasoning (~$3/M input, $15/M output as of this writing). Stick with Sonnet — Haiku does not have strong enough reasoning for failure diagnosis, Opus is overkill.

#### Verifying configuration

After setting the key:

```bash
# 1. Confirm the env var is visible to the Flask process:
ps auxe | grep -i 'webapp.backend.app' | grep -o 'ANTHROPIC_API_KEY=[^ ]*' | head -1

# 2. Trigger a STUCK job (the install simulator has a `-stuck` test hook):
curl -X POST http://localhost:5050/api/bolton/labs/test/hosts/h1/install/bolton-stuck \
  -H "Content-Type: application/json" -d '{}'

# 3. Wait for STUCK, then invoke the agent:
JOB_ID=...  # from the response above
curl -X POST http://localhost:5050/api/bolton/jobs/$JOB_ID/agent-intervene
# Expect: 200 + a `proposal` object. If 503 with "ANTHROPIC_API_KEY not
# configured" → the env var didn't propagate to the Flask process.
```

#### Audit verification

Every agent invocation writes three audit-log action types you can grep for:

```bash
grep '"action":"bolton.agent.invoke"'    ~/.dashboard/audit.log
grep '"action":"bolton.agent.tool_call"' ~/.dashboard/audit.log
grep '"action":"bolton.agent.approve"'   ~/.dashboard/audit.log
grep '"action":"bolton.agent.reject"'    ~/.dashboard/audit.log
grep '"action":"bolton.agent.retry"'     ~/.dashboard/audit.log
```

The `bolton.agent.invoke` entry records the budget limits (`limit_tool_calls`, `limit_wall_clock_s`) at the moment of invocation, so future audits can reconstruct exactly what the agent was allowed to do.

---

## 8. UI / UX design

Reuses existing Phase 2b TASTE primitives. New surface lives at `/vulnerabilities` in the dashboard nav, sub-tabbed under the existing GOAD section.

### 8.1 Catalog page (`/vulnerabilities`)

Three-column grid, each card a `.spec-row` variant.

```
┌─────────────────── VULNERABILITY CATALOG ────────────────────┐
│ Filters: [Category ▾] [Target ▾] [Complexity ▾] [Search …]   │
│                                                              │
│ ┌────────────────────┐ ┌────────────────────┐ ┌────────────┐ │
│ │ Kerberoastable Svc │ │ ADCS ESC1          │ │ PrintNight.│ │
│ │ ⋮ identity-kerb   │ │ ⋮ adcs            │ │ ⋮ cve     │ │
│ │ ▲ DC · 30s · quiet│ │ ▲ CA · 90s · quiet│ │ ▲ DC · 4m │ │
│ │ deps: 1 · conflicts│ │ deps: 1 · conflicts│ │ · loud    │ │
│ │ : 1                │ │ : 0                │ │ deps: 0   │ │
│ │                   ⋯│ │                   ⋯│ │           ⋯│ │
│ └────────────────────┘ └────────────────────┘ └────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

Each card uses:

- `.spec-pill` for the category badge (left).
- `.spec-row__hint` line for "DC · 30s · quiet" (target / install time / detect profile).
- A small dependency-count chip and conflict-count chip.
- Card is draggable (HTML5 drag-and-drop) — `dragstart` carries the vuln id as `text/x-bolton-id`.
- Clicking the card opens a `.scrim-takeover` / `.takeover-card` with the full descriptor rendered as a `.spec-list`.

Filters operate as a left-rail multi-select. URL state — filters reflected in query string for share-linking.

### 8.2 Lab topology view (`/labs/<lab>/topology`)

Force-directed or hierarchical layout of hosts in a lab. Each host node:

```
┌──────────────────┐
│  dc01            │
│  Win2019 · DC    │
│  sevenkingdoms…  │
│ ┌──────────────┐ │
│ │ INSTALLED:   │ │
│ │ • kerb-svc   │ │  ← .spec-pill per installed vuln
│ │ • weak-pwpol │ │
│ └──────────────┘ │
│  [drop zone]     │  ← visual indicator on drag
└──────────────────┘
```

- Hosts laid out by subnet / role.
- Drop a vuln card from the catalog (catalog opens in a slide-over panel to the right when topology is active) — the topology highlights compatible hosts in green, incompatible in red (with hover tooltip explaining why).
- Drop → open the install confirm takeover.

### 8.3 Drag-drop interaction → install confirm takeover

```
┌────────────────── CONFIRM INSTALL ──────────────────────┐
│ ADCS ESC1 → ca01                                        │
├─────────────────────────────────────────────────────────┤
│ DEPENDENCIES (will be installed first):                 │
│   ✓ bolton.adcs.install-adcs            (ca01, 4m)      │
├─────────────────────────────────────────────────────────┤
│ INPUTS:                                                 │
│   ludus_adcs_esc1:           [✓]                        │
│   template_display_name:     [ESC1-Vulnerable        ]  │
├─────────────────────────────────────────────────────────┤
│ DETECTION PROFILE: quiet                                │
│ EST. INSTALL TIME: ~5 minutes                           │
├─────────────────────────────────────────────────────────┤
│           [Cancel]   [Plan only]   [Install ▸]          │
└─────────────────────────────────────────────────────────┘
```

### 8.4 Install progress modal

Live streaming log (existing `xterm.js` terminal widget — already in `frontend/js/`). Top bar shows: job id, current step (M of N), status pill (RUNNING / VERIFYING / STUCK / DONE / FAILED).

If status hits STUCK, the agent intervention surface (§7.5) replaces the bottom of the modal.

### 8.5 Installed-on view (per host)

A `.spec-list` of every vuln on that host, each `.spec-row`:

- left: vuln name + category pill
- center: installed at, by whom
- right: action buttons — `[Verify]` (re-run probe), `[Cleanup]` (rollback)

A `[Cleanup All]` button at the top of the list, with the same dep resolver running in reverse (cleanup leaves of the DAG first).

### 8.6 Scenario bundles (stretch — Caldera adversary pattern)

A pre-curated YAML at `bolton/scenarios/<slug>.yaml`:

```yaml
id: bolton.scenario.adcs-kerberoast-chain
name: "ADCS + Kerberoast Chain"
description: "Walks operator from a low-priv user → DA via ESC1 → kerberoast → silver ticket"
vulns:
  - { id: bolton.identity.weak-password-policy, target: dc01 }
  - { id: bolton.identity.kerberoastable-svc,   target: dc01 }
  - { id: bolton.adcs.install-adcs,             target: ca01 }
  - { id: bolton.adcs.esc1,                     target: ca01 }
```

UI: a "Scenarios" tab next to the catalog. Drag a scenario onto a *lab* (not a host) — the resolver maps targets to actual host names in the lab.

---

## 9. Backend API design

All under the existing Flask blueprint pattern. New blueprint at `webapp/backend/routes/bolton.py`, registered in `app.py`. Path prefix: `/api/bolton`.

| Method | Path | Purpose | Request | Response |
|---|---|---|---|---|
| GET | `/api/bolton/vulns` | List all descriptors with filtering | query: `category, target_os, complexity, lab` | `{ vulns: [VulnSummary], total }` |
| GET | `/api/bolton/vulns/<id>` | Single descriptor with full YAML | — | `{ vuln: VulnDescriptor }` |
| GET | `/api/bolton/categories` | List of categories with counts | — | `{ categories: [{ id, name, count }] }` |
| GET | `/api/bolton/labs/<lab>/hosts` | Hosts in a deployed lab | — | `{ hosts: [{ name, role, os, ip, installed_count }] }` |
| GET | `/api/bolton/labs/<lab>/hosts/<host>/installed` | What is installed | — | `{ installed: [InstalledRecord] }` |
| POST | `/api/bolton/labs/<lab>/plan` | Resolve a proposed install plan | `{ requests: [{ vuln_id, host, inputs? }] }` | `{ plan: [{ vuln_id, host, order, deps }], conflicts: [], cycles: [] }` |
| POST | `/api/bolton/labs/<lab>/install` | Dispatch install of a plan | `{ plan_id }` or inline plan | `{ job_id, status: "QUEUED" }` |
| GET | `/api/bolton/jobs/<job_id>` | Job status + tail log | query: `since=<offset>` | `{ status, steps: [...], log_tail: "...", agent_state? }` |
| GET | `/api/bolton/jobs/<job_id>/stream` | SSE stream of log lines | — | text/event-stream |
| POST | `/api/bolton/jobs/<job_id>/agent-intervene` | Manually invoke agent on stuck job | `{ }` | `{ status: "AGENT_RUNNING" }` |
| POST | `/api/bolton/jobs/<job_id>/agent-decision` | Operator approves/rejects an agent suggestion | `{ approve: bool, modified_inputs?: {} }` | `{ status }` |
| POST | `/api/bolton/labs/<lab>/uninstall` | Cleanup one or many vulns | `{ vuln_ids: [...], host?: "..." }` | `{ job_id }` |
| GET | `/api/bolton/scenarios` | List scenario bundles | — | `{ scenarios: [...] }` |
| POST | `/api/bolton/labs/<lab>/scenarios/<scenario_id>/apply` | Apply scenario | `{ host_map: { logical_name: actual_host } }` | `{ job_id }` |
| GET | `/api/bolton/audit` | Per-operator audit log | query: `operator, since, vuln_id` | `{ events: [...] }` |

### 9.1 Auth / attribution

Existing `g.operator` middleware (per CLAUDE.md and the existing routes) decorates every request. Every install + cleanup writes the operator to the state file and audit log.

### 9.2 Job model

Job states: `QUEUED → RUNNING → VERIFYING → DONE | STUCK | FAILED | CANCELED`. Jobs persist in `webapp/state/jobs/<job_id>.json`. Tail log persisted in `webapp/state/jobs/<job_id>.log`.

Hostside execution: the existing pattern of SSH-to-jumpbox + nohup + remote PID file (mirroring `provision_goad`). PID + exit-code file on jumpbox; backend polls remotely on `GET /api/bolton/jobs/<id>`.

---

## 10. Integration with the existing system

### 10.1 Dashboard nav placement

Add a "Vulnerabilities" tab to the existing GOAD section nav. Sub-pills inside that view: `Catalog`, `Scenarios`, `Topology`, `Installed`, `Audit`. Hidden when no GOAD lab is deployed.

### 10.2 Manage / Cleanup sub-pill integration

The existing dashboard has Manage and Cleanup sub-pills per deployment. Extend:

- **Manage** → adds a "Bolt-on installed: N" `.spec-pill` with link to `/bolton/labs/<lab>/installed`.
- **Cleanup** → when destroying a lab with bolt-ons installed, prompt: "Remove M bolt-ons first (recommended)?" with options to (a) cleanup-then-destroy, (b) destroy-anyway (cleanup state is lost but AWS resources are destroyed).

### 10.3 Per-operator audit

The `g.operator` middleware already attributes calls. Every `POST /api/bolton/*` writes to the audit log with operator id. The existing audit endpoint is extended to include a `bolton` action category for filtering.

### 10.4 AWS resource implications

Most bolt-ons modify software state on existing EC2 instances — no new AWS resources. Exceptions, with their implications:

- **Web app vulns (vulhub)** require a Linux member with Docker. If the lab has no Linux member, the descriptor's `pre_check` fails and the resolver suggests installing `bolton.infra.linux-member` (a meta-descriptor that provisions an EC2 instance via Terraform from a small dedicated module under `terraform/modules/bolton_linux_member/`).
- **EternalBlue** requires a Server 2008/2012 image — replacing an existing instance's AMI is destructive. The resolver flags this as a high-risk operation and routes to a separate "destructive install" confirm flow.

### 10.5 Cost tracking

Existing `webapp/backend/routes/costs.py` is extended to read `resource_impact.estimated_monthly_cost_usd_delta` from each installed descriptor and surface a per-bolt-on cost line in the Cost view.

### 10.6 Cleanup integration

When destroy of a lab is initiated, the destroy flow first lists outstanding bolt-on state. Orphan state (vulns marked installed but whose host has been destroyed) is auto-cleared with a "Orphaned bolt-on state cleared" audit event.

### 10.7 Elastic detection rules integration (forward-compat)

The existing Elastic Rules integration (see MEMORY: `project_elastic_rules_integration.md`) is the natural pair for `detection.elastic_rules_suggested`. After a bolt-on is verified, a button "Show suggested detections" links to the Elastic Rules UI pre-filtered to the suggested rule names. Purple-team feedback loop.

**Validation (task #55, 2026-05-19):** the corpus-refresh flow has been end-to-end validated. `scripts/utilities/update-elastic-rules.py` parses 469 Windows TOMLs and regenerates `webapp/frontend/js/elastic-rules.js` (128 unique rules mapped across 31 commands / 19 tools / 19 keywords, exit 0). The `POST /api/config/update-elastic-rules` endpoint returns `{success: true, results: {git_pull, generate}}` and now writes a `config.update_elastic_rules` row to the audit log on every invocation (success + failure paths both audited). All 29 `rule_uuid` references across the 12 descriptors that declare `detection.elastic_rules` were cross-checked against the 1,739-rule corpus and 100% resolved — no stale UUIDs. Re-run `scripts/utilities/audit-bolton-rule-uuids.py` whenever the corpus is refreshed; exit code 1 signals at least one descriptor needs its UUID list updated.

---

## 11. Implementation phases

Six phases. Sizing in "developer-weeks" assuming one engineer.

### Phase 1 — Schema + manual install (2–3 dev-weeks)

**Goal:** prove the descriptor model end-to-end with no UI.

- Define and document the schema (§4) under `bolton/schema/v1.json` (JSON Schema for validation).
- Author 5 descriptors covering the spread of categories: Kerberoastable, ESC1, GPP cpassword, LLMNR enabled, DVWA container.
- Author the matching Ansible roles under `bolton/roles/`.
- Write a CLI script `scripts/bolton/install.sh <vuln-id> <lab> <host>` that runs an install end-to-end via the jumpbox.
- Document molecule-style idempotency CI (`scripts/bolton/test_role.sh`).
- Deliverable: operator can SSH and `./scripts/bolton/install.sh bolton.identity.kerberoastable-svc goad-light dc01` and verify it worked.

**Dependencies:** existing GOAD lab deployed.

**Risks:** Ansible Windows-against-domain quirks; some operators' jumpbox missing `pywinrm`. Mitigation: bake pywinrm into jumpbox init.

### Phase 2 — Backend API + dependency resolver (3 dev-weeks)

**Goal:** all endpoints in §9 working without UI; tested via curl.

- `webapp/backend/routes/bolton.py` blueprint.
- Descriptor loader + JSON schema validator.
- Dependency resolver (§5).
- Job dispatch + state persistence + SSE log streaming.
- State files under `webapp/state/labs/*/installed.json` and `webapp/state/jobs/`.
- Wire `g.operator` audit attribution.
- Tests: pytest suite covering resolver, schema validation, conflict detection, cycle detection.

**Risks:** SSE infrastructure compatibility with existing reverse proxy on dashboard server. Mitigation: long-poll fallback.

#### Phase 2 status (2026-05-19)

Real Ansible execution machinery is wired into
`bolton_install_service._run_ansible_job` and replaces the Phase 1
simulator. Key bits:

- Per-job playbook materialised under `/tmp/bolton-playbook-<job_id>.yml`,
  one task per descriptor step (`include_role` for project-local roles,
  module-FQCN invocations for collection roles, `win_shell` / `shell`
  for inline `script` steps).
- Inventory resolution: prefers `ansible/inventory/<lab>/hosts`; falls
  back to a dynamic inventory synthesised from cached `HostFacts`.
- Hard timeout = `block.estimated_time_seconds × BOLTON_ANSIBLE_TIMEOUT_X`
  (default 3×) with a configurable floor (`_HARD_TIMEOUT_FLOOR_SECONDS`).
  A daemon watchdog SIGTERMs the subprocess on expiry.
- `cancel_job` SIGTERMs the live subprocess via the in-process registry;
  audit log records the cancellation.
- Verify probe runs as a second ad-hoc playbook; install / uninstall /
  patch_revert transition to **STUCK** on probe failure, PATCH transitions
  to **AS_PATCHED_BUT_VULN**.
- Simulation fallback preserved when `BOLTON_SIMULATE_ANSIBLE=1` is set
  *or* `ansible-playbook` is not on PATH — keeps CI green.

**1 of 5 descriptors has a working role; remaining 4 need role-authoring
work.**

| Descriptor                                     | Role under `ansible/roles/` | Status |
|------------------------------------------------|-----------------------------|--------|
| `bolton.identity-kerberos.kerberoastable-svc`  | `bolton_kerberoastable_svc` | shipped (install / uninstall / patch / patch_revert / verify) |
| `bolton.adcs.esc1-misconfigured-template`      | `bolton_esc1_template` (TBD) | inline PowerShell in descriptor only |
| `bolton.windows.printnightmare` (planned)      | `bolton_printnightmare` (TBD) | pending |
| `bolton.windows.zerologon` (planned)           | `bolton_zerologon` (TBD)    | pending |
| `bolton.network.llmnr-enabled` (planned)       | `bolton_llmnr_enabled` (TBD) | pending |

### Phase 3 — Catalog UI + lab topology view (2–3 dev-weeks)

**Goal:** the visual surface.

- `/vulnerabilities` page with `.spec-row`-based grid.
- Filter rail (category, target, complexity, search).
- Descriptor takeover (full YAML rendered as a `.spec-list`).
- `/labs/<lab>/topology` view (use d3 force-directed or simple flexbox layout for v1).
- Dark + light theme verified per CLAUDE.md.

**Dependencies:** Phase 2 API.

**Risks:** topology layout for SCCM/NHA (5 hosts) — needs careful information density; do not over-engineer with d3 if a static flexbox grid suffices.

### Phase 4 — Drag-drop + install progress UI (2 dev-weeks)

**Goal:** end-to-end operator flow without agent fallback.

- HTML5 drag-and-drop from catalog to topology host.
- Install-confirm takeover with rendered plan.
- Live install progress modal with xterm.js streaming.
- Installed-on per-host view with verify / cleanup actions.
- Cleanup dispatch (reverse-topo-order).

**Dependencies:** Phase 3.

**Risks:** browser drag-drop event semantics across Safari/Chrome/Firefox. Mitigation: a click-to-select fallback.

### Phase 5 — Agentic fallback (2–3 dev-weeks)

**Goal:** agent intervention on stuck jobs.

- Anthropic SDK integration with prompt caching (CLAUDE.md `claude-api` skill).
- Tool surface (§7.3): `run_diagnostic_command`, `retry_install`, `request_operator_input`, `mark_failed`.
- Agent context builder (§7.2).
- Stuck-job UI: chat-style intervention panel inside install progress modal.
- Operator approve/reject flow.
- Per-job iteration + time budget enforcement.
- Audit logging (§7.6).

**Dependencies:** Phase 4 (UI surface for stuck jobs); ANTHROPIC_API_KEY in dashboard env.

**Risks:** agent over-confidence — proposing destructive retries. Mitigation: action whitelist; auto-approve only when action is `run_diagnostic_command` (read-only) or `retry_install` with identical inputs.

### Phase 6 — Catalog expansion + community model (ongoing)

**Goal:** 50+ descriptors; contribution workflow.

- Author the remaining ~75 descriptors per §3.
- Document `CONTRIBUTING.md` for new bolt-ons.
- Build a `bolton-validate` CLI tool (schema + idempotency + cleanup test).
- Optional: a "Submit to Galaxy" GitHub Action mirroring the Ludus role template (§2.5).
- Scenario bundles (§8.6).

**Dependencies:** Phase 5 complete; community of authors.

**Risks:** keeping descriptors aligned with upstream tool versions (Certipy, Impacket, GOAD). Mitigation: pin tool versions in descriptors; monthly CI run against latest.

### Total

~14 dev-weeks for Phases 1–5; Phase 6 is open-ended catalog work that runs in parallel after Phase 5.

---

## 12. Risks / open questions

1. **Idempotency of wrapped third-party roles.** `badsectorlabs.ludus_adcs` is explicitly not idempotent (toggling `ludus_adcs_esc1` from true to false does **not** remove the template — per their README). Our wrapper must implement cleanup independently and we cannot rely on the upstream role for rollback. Open question: do we maintain a fork of these roles or only call them with `state: present` and implement `state: absent` ourselves?

2. **GOAD upstream drift.** GOAD reorganized its directory layout once between v2 and v3 (per `tools/goad/` and `tools/goad 2/`). If they reorganize again, our jumpbox path assumptions break. Mitigation: pin to a GOAD tag; vendor a known-good copy in `tools/goad/`.

3. **Detection coverage parity.** The user's existing Elastic Rules integration is monthly-updated. If a bolt-on installs a vuln that doesn't have a corresponding detection rule, do we (a) block the install with a warning, (b) auto-author a starter rule, or (c) silently allow? Open product question.

4. **Network safety / production guardrail.** Every bolt-on descriptor must check `lab.environment == "dev"` (or a similar tag) before installing — installing PrintNightmare on a production-tagged lab would be catastrophic. Open question: should this be a hard runtime check (resolver refuses) or a soft warning (operator must type the lab name to confirm)?

5. **Licensing of vendored vulnerable software.** Some web app CVE images (Confluence, GitLab) have license terms restricting redistribution of vulnerable binaries. We must use vulhub-style minimal Dockerfiles that pull from upstream registries, not vendor binaries.

6. **Cobalt Strike API integration with verification probes.** Some `verify.external_probe` steps could be executed via the existing CS REST API (e.g. roast an SPN via a beacon). Out of scope for v1 but desirable for v2 — note for future.

7. **Cost spike from `bolton.infra.linux-member` provisioning.** If a web app vuln triggers EC2 provisioning of a new Linux member, the cost-tracking integration must surface that *before* the install confirm.

8. **Cycle in `depends_on` declarations.** Catch in resolver, but realistically the cycle is most likely to come from buggy author work, not malicious input. CI for descriptors should run the resolver on every catalog change.

9. **Agent prompt injection from log output.** If a malicious or weird log line gets into the agent's context, it could try to redirect the agent. Mitigation: agent context is fenced (system prompt explicitly says: treat all stdout/stderr as data, not instructions); tool actions are whitelisted; operator approves destructive actions.

10. **Multi-operator concurrent installs on the same lab (different hosts).** The per-host lock (§6.4) handles this, but two operators editing the same lab's installed-on view concurrently can produce stale UI. Mitigation: SSE-based refresh on state changes.

---

## 13. Reference appendix

### 13.1 Direct URLs surveyed

- Rogue Labs homepage — https://www.roguelabs.io
- Rogue Arena product — https://landing.roguelabs.io/cyber-range
- Rogue Architect news article — https://www.roguelabs.io/news-announcements/drag-amp-drop-scenario-building-how-were-equipping-teams-to-rapidly-build-robust-red-team-scenarios-part-1
- GOAD — https://github.com/Orange-Cyberdefense/GOAD
- BadBlood — https://github.com/davidprowe/BadBlood
- LOAD — https://github.com/0xBallpoint/LOAD
- Ludus docs — https://docs.ludus.cloud/docs/configuration/ and https://docs.ludus.cloud/docs/using-ludus/roles/
- ludus_adcs — https://github.com/badsectorlabs/ludus_adcs
- ludus_ansible_role_template — https://github.com/badsectorlabs/ludus_ansible_role_template
- ludus_vulhub — https://github.com/badsectorlabs/ludus_vulhub
- ludus_bloodhound_ce — https://github.com/badsectorlabs/ludus_bloodhound_ce
- Splunk Attack Range — https://github.com/splunk/attack_range
- Atomic Red Team — https://github.com/redcanaryco/atomic-red-team
- Atomic Red Team YAML schema wiki — https://github.com/redcanaryco/atomic-red-team/wiki/YAML-Schema
- MITRE Caldera — https://github.com/mitre/caldera
- Caldera docs — https://caldera.readthedocs.io/en/latest/Learning-the-terminology.html
- vulhub — https://github.com/vulhub/vulhub
- DetectionLab (archived) — https://github.com/clong/DetectionLab
- Vulnerable-AD — https://github.com/safebuffer/vulnerable-AD
- Top 16 AD vulnerabilities — https://www.infosecmatter.com/top-16-active-directory-vulnerabilities/
- ADCS ESC overview — https://www.vaadata.com/blog/ad-cs-security-understanding-and-exploiting-esc-techniques/ and https://swisskyrepo.github.io/InternalAllTheThings/active-directory/ad-adcs-esc/
- Certipy — https://github.com/ly4k/Certipy

### 13.2 Rogue Labs key quotes

> "Modern Red Team training + Next-generation cyber range + Rigorous certification" — https://www.roguelabs.io

> "Add Plugins to Machines … browse and add plugins from the Rogue Architect plugin library featuring over 100 plugins!" — Rogue Architect news article

> "Rogue Architect automatically creates build snapshots as it progresses creating an entire Checkpoint System." — Rogue Architect news article

> "Rogue Arena supports multi-domain AD forest scenarios … Brainstorm Mode, where Claude AI assists in designing complete scenarios end-to-end." — landing.roguelabs.io/cyber-range

> Plugin categories: "Machine Action, Applications, Roles, File Copies, Vulnerabilities" — Rogue Architect news article

### 13.3 Worked descriptor (referenced in §4)

See §4.1 for the full Kerberoastable Service Account descriptor and §4.2 for the abbreviated ADCS ESC1 descriptor.

### 13.4 Glossary

- **ACE** — Access Control Entry. A single permission entry in a DACL.
- **ADCS** — Active Directory Certificate Services. Microsoft's PKI.
- **AdminSDHolder** — Special AD object whose DACL is periodically copied onto protected privileged accounts; write access enables persistence.
- **AS-REP Roasting** — extraction of a hash from a Kerberos AS-REP response when pre-authentication is disabled.
- **BadBlood** — PowerShell tool that fills AD with weaknesses (§2.3).
- **Caldera** — MITRE adversary emulation framework (§2.8).
- **Certipy** — Python ADCS abuse tool — https://github.com/ly4k/Certipy
- **CME / NetExec / NXC** — credential testing and post-exploitation framework.
- **DACL** — Discretionary Access Control List; per-object ACL in AD.
- **DCSync** — replicating AD secrets by leveraging the directory replication right.
- **ESC1–16** — sixteen named ADCS misconfiguration classes from the "Certified Pre-Owned" research line.
- **GOAD** — Game Of Active Directory; the vulnerable AD lab project we deploy.
- **GPP cpassword** — pre-MS14-025 Group Policy Preferences exposed an AES-encrypted password in SYSVOL with a known static key.
- **Kerberoasting** — extraction of a TGS for an SPN-bound user account, offline crack to recover the cleartext password.
- **LAPS** — Local Administrator Password Solution.
- **Ludus** — self-hosted Proxmox-based cyber range platform with the Ansible-role-per-bolt-on model we are adopting.
- **NTLM relay** — relaying captured NTLM authentication to a target service.
- **PetitPotam** — MS-EFSRPC coercion forcing a target to authenticate to attacker-controlled host (CVE-2021-36942).
- **PrintNightmare** — Print Spooler RCE (CVE-2021-1675 + CVE-2021-34527).
- **Rogue Architect** — Rogue Labs' drag-and-drop scenario builder.
- **SPN** — Service Principal Name; Kerberos identifier for a service.
- **TGS / TGT** — Ticket Granting Service / Ticket Granting Ticket; Kerberos tickets.
- **vulhub** — Docker-Compose-per-CVE vulnerable application catalog.
- **ZeroLogon** — Netlogon elevation of privilege (CVE-2020-1472).

---

## 14. Refinements (post-review, 2026-05-18)

After reviewing the master plan above, the user requested three refinements. Each is detailed in its own sibling document; this section is a pointer index and integration map so the master plan reads coherently with them. **Treat the refinement docs as authoritative for their scope; this section summarizes how they amend the sections above.**

### 14.1 Compatibility auto-detection + catalog filtering — [BOLTON_REFINEMENT_compatibility.md](BOLTON_REFINEMENT_compatibility.md)

> User: *"The lab should auto detect when an incompatible vulnerability is trying to be added on — filter at that point as to what can / can not be added."*

**What it amends:** §5 (dependency / conflict resolution) — extends from install-time check to **proactive catalog-time filtering**. §8 (UI) — catalog cards now display per-host compatibility state. §9 (backend API) — three new endpoints.

**Headline additions:**
- Eight compatibility states (`INSTALLABLE` / `INCOMPATIBLE_OS` / `INCOMPATIBLE_ROLE` / `MISSING_PREREQ` / `CONFLICTS_WITH_INSTALLED` / `ALREADY_INSTALLED` / `MISSING_SOFTWARE` / `PATCHED`), each with human-readable reason + suggested action.
- Host facts model: OS family + version, role, domain functional level, installed services + versions, applied KBs, network position, currently-installed bolt-ons, active GPOs.
- New endpoints: `GET /api/bolton/labs/<lab>/hosts/<host>/facts`, `GET /api/bolton/labs/<lab>/hosts/<host>/catalog` (annotated per-vuln with state), `POST /api/bolton/labs/<lab>/hosts/<host>/facts/refresh`.
- 5-minute TTL caching on per-host YAML files at `webapp/state/bolton/host_facts/<lab>/<host>.yaml`. Install-time backstop re-runs `evaluate_compatibility` against fresh facts and 409s if state changed.
- Open question: WebSocket invalidation for concurrent operators in v2.

### 14.2 Patch / clean-remove workflow — [BOLTON_REFINEMENT_patch.md](BOLTON_REFINEMENT_patch.md)

> User: *"for cleanup — why can't we add a clean remove / patch vulnerability?"*

**What it amends:** §4 (schema) — replaces single `cleanup` field with three explicit blocks (`uninstall` / `patch` / `patch_revert`). §8 (UI) — Cleanup tab gains a new section "Installed bolt-on vulnerabilities" with per-row Patch / Uninstall / View actions. §10 (integration) — patch operations flow through the same job-progress + agentic-fallback machinery as installs.

**Headline additions:**
- 22 schema fields across three blocks. **Patch** applies the real-world fix (KB install, GPO change, template flag fix, password rotation) that closes the CVE semantically; **Uninstall** removes the install artifacts and returns the host to pre-install state; **Patch revert** un-patches for training-cycle scenarios (only when `patch.rollback_supported = true`).
- Five worked examples with vendor-accurate remediation: PrintNightmare (CVE-2021-34527 KB + `RestrictDriverInstallationToAdministrators` reg key), ZeroLogon (monthly rollup + enforcement reg key), ADCS ESC1 (clear `ENROLLEE_SUPPLIES_SUBJECT` bitmask + add Manager Approval), Kerberoastable SPN (30+ char password rotation + AES-only encryption), LLMNR/NBT-NS (GPO disable).
- New terminal failure state `AS_PATCHED_BUT_VULN`: post-patch exploit probe still succeeds → red surface, agent invoked automatically.
- Bulk patch operations: multi-select installed bolt-ons on a host, patch as a batch with resolver-computed order.
- Open question: domain-scope lock for cross-host patches (ZeroLogon, GPO writes) where two operators on different hosts race.

### 14.3 MITRE ATT&CK TTP + Elastic Detection Rule tie-in — [BOLTON_REFINEMENT_ttp_elastic.md](BOLTON_REFINEMENT_ttp_elastic.md)

> User: *"the vulnerability should be tied to a ttp / elastic — flag when not available."*

**What it amends:** §4 (schema) — every descriptor gains `mitre` + `detection` blocks. §8 (UI) — catalog cards show coverage badges; install confirmation surfaces coverage status; post-install verification probe confirms the detection rule fires. §9 (backend API) — six new endpoints. §10 (integration) — builds on existing `Research/elastic-detection-rules/rules/*.toml` corpus indexed by `rule_id` UUID.

**Headline additions:**
- Schema gains `mitre: {tactic, technique, subtechnique}` + `detection: {elastic_rules[], coverage_status, fallback_rule_template, exploit.trigger_probe}`.
- Four coverage states with explicit visual treatment: `covered` (green), `partial` (amber), `no-rule` (**red prominent**), `rule-stale` (orange, > 90 days unvalidated). Worst-rule-wins with explicit override allowed.
- Six new endpoints incl. `/coverage`, `/probe`, `/probes/<id>`, `/detection/gaps`, `/generate-rule`, `/coverage/navigator-layer`.
- "Generate detection rule" flow with 8 Jinja starter templates shipping in v1 (Kerberoasting, ADCS, GPP cpassword, PrintNightmare, DLL hijack, Java deserialization, PetitPotam, NTLM relay). Backend renders template with descriptor's MITRE chain + UUIDv4; frontend offers copy / download / open-draft-PR-upstream via `gh` CLI.
- Post-install synthetic exploit probe queries Elastic alerts API for rule firing within a configurable window (5 min default). Result feeds into the host's "installed" view as "Detection verified ✓" or "Detection didn't fire — investigate."
- MITRE Navigator layer export (lab-wide coverage heatmap).
- Three worked examples covering 1:1 mapping (Kerberoasting → T1558.003), multi-technique (PrintNightmare → T1068 + T1574.001), and `mitre: none` with fallback template (custom Java deserialization).
- Open question: where the Elastic alerts API lives in our deployment — most engagements won't have a reachable Kibana instance; degraded `probe-only` mode runs the probe but skips alert correlation. Should an optional Elastic-stack bolt-on lab component ship for purple-team scenarios?

### 14.4 Integration sequence

The three refinements compose cleanly. Recommended implementation order:
1. **Schema additions first** (14.2 + 14.3) — these touch the descriptor format; lock the YAML shape before writing any code.
2. **Compatibility filtering** (14.1) — host facts + catalog annotation; gives the operator a useful catalog before any install machinery is wired.
3. **Install + patch + uninstall engine** (master §6 + 14.2) — wire the Ansible roles + verify probes + audit.
4. **Detection probe loop** (14.3) — depends on installs working; closes the loop with post-install rule-firing verification.
5. **Generate-rule + Navigator export** (14.3) — value-add once basic detection wiring exists.

### 14.5 Cross-refinement open questions consolidated

| # | Question | Refinement | Suggested resolution |
|---|---|---|---|
| OQ-A | WebSocket invalidation for concurrent operators? | Compatibility | Defer to v2; v1 uses 5-min TTL + install-time backstop |
| OQ-B | Domain-scope lock for cross-host patches (GPO/AD writes)? | Patch | Recommend AD-stored lock object (survives Flask restart, visible to other tools); needs prototyping |
| OQ-C | Elastic Kibana availability in engagement deployments? | TTP/Elastic | **RESOLVED 2026-05-18 — user confirmed: ship the optional Elastic-stack bolt-on lab component.** See §14.6 below for the component design. Degraded `probe-only` mode remains as a fallback when the component isn't installed (or for cost-sensitive engagements where the operator doesn't want the Elastic infra spun up). |
| OQ-D | (master §12) Production guardrail — hard block or soft warning on prod-tagged labs? | Original | **RESOLVED 2026-05-18 — user confirmed: dropped entirely.** All labs are architecturally isolated by the AWS infrastructure — separate VPCs per project, project-tagged resources, no shared blast radius. There is no "production" concept in this system; everything is operator-owned training/engagement infrastructure. Destructive actions still surface a normal confirmation modal (consistent with the operator-management Delete pattern) but the special "type the lab name to override" gate is unnecessary. |
| OQ-E | (master §12) Detection coverage parity at descriptor authoring time? | Original ↔ TTP/Elastic | TTP refinement resolves: descriptors REQUIRED to declare MITRE; detection rules linkable post-hoc; `no-rule` is a visible but non-blocking state |

### 14.6 Elastic-stack bolt-on lab component (resolves OQ-C)

**Status (2026-05-19): Phase 3b IMPLEMENTED.** See "Phase 3b implementation status" at the end of this section for the audit of what landed, what is scaffolded, and what is deferred to Phase 3c.

User decision 2026-05-18: ship an optional Elastic stack as a **lab infrastructure component** that operators can bolt onto any GOAD or C2 lab. This makes the TTP/Elastic refinement's post-install rule-firing verification fully operational rather than degraded-mode.

**Distinct from vulnerability bolt-ons.** This is a new descriptor *class* — `infrastructure` — used for installing detection/observability infrastructure into a lab, not for installing vulnerabilities. Same descriptor schema, same install/uninstall machinery, same Ansible engine — different `category: infrastructure` tag and slightly different UI surface.

**Component shape:**

- One new descriptor: `webapp/bolton/catalog/infrastructure/elastic-detection-stack.yaml`
- Targets: Linux server in the lab's management subnet (or a dedicated EC2 instance — see "Hosting topology" below)
- Installs:
  - Elasticsearch (single-node) — log + alert storage
  - Kibana — UI + detection rule management
  - Fleet Server — agent management
  - Default detection rule pack — imported from the existing `Research/elastic-detection-rules/rules/*.toml` corpus, plus any starter rules generated from bolt-on `fallback_rule_template`s
- Optional secondary bolt-ons that wire each lab host into the stack:
  - `infrastructure/winlogbeat-shipper.yaml` — for Windows hosts (DCs, members, workstations)
  - `infrastructure/filebeat-shipper.yaml` — for Linux/Unix hosts (jumpbox, redirectors, GOAD member servers running Linux)
  - `infrastructure/sysmon.yaml` — Sysmon with the SwiftOnSecurity config for richer Windows endpoint telemetry
- Each shipper bolt-on `depends_on: infrastructure/elastic-detection-stack` so the resolver auto-installs the stack first if any shipper is selected.

**Hosting topology** — two options the descriptor supports:

| Option | Where it runs | Cost impact | When to pick |
|---|---|---|---|
| **Inline** | Spun up as a small EC2 instance within the lab's management subnet (t3.large or similar) | +~$60/mo while running | Default — keeps the stack lifecycle tied to the lab, gets destroyed when lab is destroyed |
| **Shared** | Bolted onto the existing dashboard server (which already has spare capacity) | $0 additional | Cost-sensitive engagements where the dashboard server can handle it, or for very small labs |

Operator picks via the install confirmation modal. Cost chip in the catalog card reflects this.

**Lifecycle integration:**

- `infrastructure/elastic-detection-stack` is listed in the catalog under a new "Lab Infrastructure" category (NOT in the regular 10 vulnerability categories).
- When installed, the Cleanup tab's "Installed bolt-on vulnerabilities" section gains a sibling: **"Installed lab infrastructure"** — same row treatment but the per-row actions are Uninstall + Configure (Patch doesn't apply to infrastructure).
- Audit log records the install/uninstall as `bolton.infra.install` etc. — distinct action namespace.

**Probe / verification integration:**

The TTP/Elastic refinement's `POST /api/bolton/vulns/<id>/probe` endpoint already supports `degraded` mode (probe runs but no alert correlation). When the Elastic component is installed, the probe endpoint upgrades to full mode:

1. Run the synthetic exploit probe on the target host
2. Wait the configurable window (default 5 min)
3. Query the lab's Kibana alerts API for any rule firing where `rule_uuid` matches the descriptor's declared rules AND `host.name` matches the target
4. Return `{fired: true|false, rule_uuid, alert_id, timestamp}` or `{fired: false, degraded: true}` if no Elastic instance is reachable

The Kibana endpoint is discovered via a new `infrastructure/elastic-detection-stack` host fact — the bolt-on registers its endpoint when installed, the probe service queries it.

**Update to Phase numbering** (master plan §11):

This adds a new sub-phase to **Phase 5 (agentic fallback integration)**, since both depend on the install machinery:

- **Phase 5a** — agentic fallback (already planned)
- **Phase 5b** — Elastic-stack bolt-on infrastructure component (~3-4d)
- **Phase 5c** — Beats shipper bolt-ons + probe endpoint upgrade to full mode (~2-3d)

Total dev-time impact: +5-7 days to Phase 5. The detection probe loop value is significantly higher with this component shipped — the lab becomes a real purple-team training surface, not just a red-team playground.

**Open follow-on questions** (deferred until implementation begins):

- Should we maintain the rule pack in-tree, or pull fresh from `Research/elastic-detection-rules/` (which is already monthly-updated by the existing integration)? Lean: pull fresh.
- Multi-lab Elastic — should one inline Elastic instance be reusable across multiple labs in the same VPC? Likely no — keep one-stack-per-lab for blast-radius isolation, matching the user's "all labs are isolated" architectural principle.
- License — Elastic Basic is free for this use, but the rule corpus is licensed Elastic-2.0; document that operators can fork/modify rules but uploading them to commercial Elastic offerings requires checking the license.

#### Phase 3b implementation status (2026-05-19)

What landed in this Phase:

| Surface | File(s) | Status |
|---|---|---|
| Schema widening for `infrastructure` class | `webapp/bolton/schema.py` | **Implemented.** `BoltOnDescriptor.patch` is now `PatchBlock | None`. New `_patch_required_unless_infrastructure` validator forbids `patch:` for `category: infrastructure` and requires it for every other category. The existing `_patch_revert_iff_rollback_supported` validator short-circuits when `patch is None`. |
| Stack descriptor | `webapp/bolton/catalog/infrastructure/elastic-detection-stack.yaml` | **Implemented.** Validates against the schema. `mitre: null`, `patch: null`. Carries install + uninstall blocks + cost (`storage_mb: 30720`). |
| Shipper descriptors (3) | `webapp/bolton/catalog/infrastructure/{winlogbeat-shipper,filebeat-shipper,sysmon}.yaml` | **Implemented.** Each declares `depends_on: [bolton.infrastructure.elastic-detection-stack]` so the resolver auto-installs the stack first. |
| Ansible role — entry + dispatch | `ansible/roles/bolton_elastic_stack/tasks/main.yml` | **Implemented.** Branches on `state` + `shipper_component` so one role serves all four descriptors. |
| Ansible role — Elasticsearch install | `tasks/install_es.yml` + `templates/elasticsearch.yml.j2` | **Implemented end-to-end** (subject to a live Ubuntu run). Adds Elastic APT repo, installs the package, renders single-node config, resets the `elastic` user password, registers `es_password` as a host fact. |
| Ansible role — Kibana install | `tasks/install_kibana.yml` + `templates/kibana.yml.j2` | **Implemented end-to-end.** Installs Kibana, waits for it to come up, registers `kibana_endpoint` as a cacheable fact, writes `/etc/bolton/elastic-stack.facts`. |
| Ansible role — Fleet Server | `tasks/install_fleet.yml` | **Scaffolded.** Service-token POST + agent enroll command are written but un-tested. Phase 3c will add Fleet agent policies + integration assignment. |
| Ansible role — rule import | `tasks/import_rules.yml` | **Scaffolded.** Calls `python3 -m detection_rules kibana upload-rule` against every TOML in the corpus. Per-rule loop should be replaced with a single `--directory` invocation in Phase 3c. |
| Ansible role — shipper installs | `tasks/install_{winlogbeat,filebeat,sysmon}.yml` | **Scaffolded.** Each installs the package + drops a minimal config. Full Fleet-managed enrollment + module-specific configs (Security/Sysmon/PowerShell channels, Filebeat modules) are Phase 3c. |
| Ansible role — uninstall | `tasks/uninstall.yml` | **Implemented.** Branches on `shipper_component` and tears down the full stack OR a single shipper. |
| Probe service upgrade | `webapp/backend/services/bolton_probe_service.py` | **Implemented.** New `_discover_elastic_endpoint(lab)` walks the facts service's installed_boltons map looking for the stack id, reads `kibana_endpoint` / `es_password` off the cached HostFacts. New `correlate_alerts(...)` POSTs to `/api/detection_engine/signals/search` with the descriptor's rule UUIDs + target host + probe-start timestamp. `run_probe()` records full or degraded mode + fired/alert_id shape in the probe JSON. |
| Tests | `tests/backend/test_bolton_elastic_stack.py` | **Implemented.** Covers schema widening (infrastructure descriptor accepts `patch: null`, rejects `patch:` set), all four descriptor files validate + shippers depend on the stack, resolver auto-includes the stack, probe service full-mode + three degraded-mode fallback paths. Kibana is mocked via `monkeypatch.setattr(bolton_probe_service, "requests", SimpleNamespace(post=...))`. |

Follow-up work tagged in code with `TODO (Phase 3c)`:

- Full rule corpus upload via `detection_rules kibana upload-rule --directory` rather than per-rule loop (`tasks/import_rules.yml`).
- Fleet agent policy POST + per-integration assignment (`tasks/install_fleet.yml`).
- Winlogbeat / Filebeat / Sysmon module configs beyond the minimal placeholder (`tasks/install_{winlogbeat,filebeat,sysmon}.yml`).
- Real Kibana auth flow — currently the probe service reads `es_password` off a HostFacts cache. Production should retrieve it from AWS Secrets Manager instead (`webapp/backend/services/bolton_probe_service.py`).
- Front-end "Lab Infrastructure" tab + Installed lab infrastructure section in the Cleanup tab (master plan §14.6).
- Cost-aware install confirmation modal exposing the `inline` vs `shared` topology choice (currently the descriptor pins `topology: inline`).
