# Bolt-on Catalog vs. Upstream GOAD Ansible Roles — Reuse Audit

**Date:** 2026-05-19
**Scope:** evaluate whether the 22 bolt-on descriptors at `webapp/bolton/catalog/`
can be rewritten to `import_role: name: vulns/<upstream_role>` against the 26
unused upstream GOAD vuln roles at `tools/goad/ansible/roles/vulns/`.
**Outcome (TL;DR):** **zero rewrites landed.** Every upstream role that looked
like a candidate on the name alone fell apart on contract or scope inspection.
The dispatcher *was* extended to make `tools/goad/ansible/roles/` reachable via
a new `BOLTON_ROLES_SEARCH_PATH` env var so future descriptors can opt in
without further plumbing.

---

## 1. Methodology

For every descriptor under `webapp/bolton/catalog/**/*.yaml` I cross-referenced:

1. The `install.steps` block — what Ansible modules / inline PowerShell get
   invoked, with what variable surface.
2. The corresponding upstream role's `tasks/main.yml` — what it actually does
   on the target host, what variables it consumes, and what idempotency /
   rollback shape it has.
3. The dispatcher's playbook generator (`_step_to_task` in
   `webapp/backend/services/bolton_install_service.py`): step keys must be
   `ansible_role` + `role_vars` (schema is `extra="forbid"`), and a role name
   without `.` triggers `include_role`.

A "high confidence" rating requires:

- Same scope (host-local vs. GPO-wide vs. AD object-level).
- Same surface variables (or trivially mappable defaults).
- A clean uninstall path — either built into the upstream role via state, or
  a small inverse-task block we can author.
- The descriptor's `verify` probe continues to succeed against the upstream
  role's actual output.

Anything failing one of these criteria gets downgraded to LOW (with a
written reason) and is **not** rewritten.

## 2. Mapping table

| Catalog descriptor (slug) | Upstream role candidate | Confidence | Decision | Notes |
|---|---|---|---|---|
| `protocol-network/llmnr-nbtns-enabled` | `enable_llmnr`, `enable_nbt-ns` | **LOW** (downgraded from high) | keep as-is | Descriptor creates a domain-linked GPO `Bolton-Enable-LLMNR-NBTNS` with `New-GPO` / `New-GPLink` / `Set-GPRegistryValue`. Uninstall removes the GPO. Upstream `enable_llmnr` writes a single local `HKLM\Software\policies\…\EnableMulticast=1` registry value via `REG ADD`. **Scope mismatch — local vs. domain.** Verify probe (`Get-GPO -Name Bolton-Enable-LLMNR-NBTNS`) would fail. The hyphen in `enable_nbt-ns` would also force quoting in `import_role: name`. |
| `protocol-network/smb-signing-disabled` | (none) | n/a | keep as-is | Upstream has no SMB-signing role. `smbv1` enables the SMBv1 *feature*, which is a different vuln (protocol vs. signature header). |
| `service-misconfig/writable-share-everyone` | `openshares`, `shares` | **LOW** (downgraded from medium) | keep as-is | `openshares` is **destructive net-new** — creates *fixed* `public` + `all` shares plus enables the Guest account and `AllowInsecureGuestAuth`. `shares` is a generic dict-of-dicts looper expecting `vulns_vars` shape `{name: {path, full, read, …}}`. Our descriptor needs one specific share (`PublicShare`) with Everyone:Full and a SACL audit rule — uses three `ansible.windows` modules directly. Bolting on `shares` would require synthesising the `vulns_vars` dict per-step + globally enabling guest is unwanted. |
| `endpoint-phishing/macro-enabled-doc-share` | `files` | **LOW** | keep as-is | `files` copies arbitrary files from `../ad/{{domain_name}}/files/{{src}}` to a dest path — but the macro-enabled doc is *generated in-place* via `Word.Application` COM automation. No source artifact to copy. Net-new logic. |
| `identity-kerberos/kerberoastable-svc` | (none) | n/a | keep as-is (hand-authored role `bolton_kerberoastable_svc`) | Upstream has no kerberoasting setup role. Closest behavioural overlap is `credentials` which writes Credential Manager entries — different vuln. |
| `identity-kerberos/asrep-roastable-account` | (none) | n/a | keep as-is | Same as above. Descriptor uses `community.windows.win_domain_user` + `microsoft.ad.user` with `DONT_REQ_PREAUTH` flag. |
| `identity-kerberos/unconstrained-delegation-svc` | (none) | n/a | keep as-is | `microsoft.ad.computer` with `TRUSTED_FOR_DELEGATION` flag — no upstream equivalent. |
| `access-control/adminsdholder-acl-modified` | `acls` | **LOW** (downgraded from medium) | keep as-is | Upstream `acls` accepts (`for`, `to`, `right`, `inheritance`) and applies via `Set-Acl` on AD objects. Our descriptor: (a) captures baseline SDDL to `C:\ProgramData\bolton\adminsdholder-baseline.sddl` for clean revert, (b) triggers SDPROP immediately (`RunProtectAdminGroupsTask`), (c) accepts `lure_persist` lookup. Upstream role discards baseline + has no SDPROP step. Rewriting loses rollback fidelity. |
| `access-control/generic-write-user` | `acls` | **LOW** | keep as-is | Same baseline-capture concern as above. Descriptor specifically targets `Account Operators` group and persists SDDL for rollback. |
| `credential-exposure/gpp-cpassword-sysvol` | `files` | **LOW** | keep as-is | `files` copies pre-staged files; our descriptor *constructs* the SYSVOL Policies directory tree and writes `Groups.xml` inline via `community.windows.win_copy` with content payload. No source artifact in `../ad/{{domain_name}}/files/`. |
| `credential-exposure/laps-readable-by-domain-users` | `acls` | **LOW** | keep as-is | Same baseline-SDDL-capture concern as access-control rows. |
| `adcs/esc1-misconfigured-template` | `adcs_templates`, `adcs_esc6` … `adcs_esc15` | **LOW** | keep as-is | **No ESC1 upstream role.** Upstream covers ESC6/7/10/11/13/15 — completely disjoint set. `adcs_templates` is a *generic* installer for the `ADCSTemplate` PowerShell module + a `with_dict` loop over JSON template files (`{template_name, template_file}`). It does *not* embed the ESC1 vulnerable-template definition. Rewriting would require shipping the ESC1 JSON template separately. |
| `adcs/esc2-any-purpose-eku` | `adcs_templates` | **LOW** | keep as-is | Same as ESC1: upstream offers no ESC2 template, and `adcs_templates` is a generic installer requiring a JSON template artifact we don't have. |
| `known-cve/printnightmare` | (none) | n/a | keep as-is | No upstream PrintNightmare role. Descriptor handles Print Spooler policy + KB install (`ansible.windows.win_updates`). |
| `known-cve/zerologon` | (none) | n/a | keep as-is | No upstream ZeroLogon role. Descriptor uses `ansible.windows.win_regedit` + `win_updates` directly. |
| `known-cve/petitpotam` | (none) | n/a | keep as-is | No upstream PetitPotam role. Descriptor handles LSA + EFS service config directly. |
| `infrastructure/elastic-detection-stack` | (none) | n/a | keep as-is (hand-authored role `bolton_elastic_stack`) | Linux-target ELK install — completely outside upstream's Windows-AD scope. |
| `infrastructure/filebeat-shipper` | (none) | n/a | keep as-is | Linux shipper. Out of scope. |
| `infrastructure/winlogbeat-shipper` | (none) | n/a | keep as-is | Reuses `bolton_elastic_stack` with `shipper_component: winlogbeat`. |
| `infrastructure/sysmon` | (none) | n/a | keep as-is | Reuses `bolton_elastic_stack` with `shipper_component: sysmon`. |
| `web-app/dvwa-lite` | (none) | n/a | keep as-is | Linux + Docker — out of upstream's scope. |
| `cloud-container/docker-socket-exposed` | (none) | n/a | keep as-is | Linux + Docker — out of upstream's scope. |

**Total:** 22 descriptors evaluated. 0 high-confidence rewrites. 11 LOW-confidence
candidates (all downgraded with documented reasons). 11 net-new with no
upstream candidate.

## 3. Why every "obvious" match failed on inspection

Three recurring patterns explain the universal downgrade:

### 3.1 Scope mismatch — local registry vs. GPO

The catalog deliberately uses **domain GPOs** for protocol toggles
(`Bolton-Enable-LLMNR-NBTNS`) so a single install reaches every member
host. Uninstall is a single `Remove-GPO`. Upstream's `enable_llmnr` and
`enable_nbt-ns` set the registry on the *host where the role runs* —
even if the target is a DC, the effect doesn't replicate to members.
The two are doing different things despite the matching name.

### 3.2 Baseline-capture rollback contract

`access-control/adminsdholder-acl-modified`, `generic-write-user`, and
`credential-exposure/laps-readable-by-domain-users` all write the
pre-modification ACL SDDL to `C:\ProgramData\bolton\<vuln>-baseline.sddl`
before adding the malicious ACE. The patch revert (or uninstall) reads
the baseline and restores the original DACL exactly. The upstream `acls`
role offers no equivalent — it just adds an ACE and leaves no breadcrumb.
Swapping to `import_role: name: vulns/acls` would silently lose the
clean-rollback guarantee, which is the operational value the descriptor
exists to provide.

### 3.3 Upstream-role variable contract: `vulns_vars` as dict-of-dicts

Most upstream vuln roles (`shares`, `openshares`, `permissions`,
`schedule`, `mssql`, `credentials`, `adcs_templates`, `adcs_esc7`,
`adcs_esc13`, `directory`, `files`, `autologon`) loop with
`with_dict: "{{ vulns_vars }}"` and expect domain-username /
domain-password vars set by the upstream `vulnerabilities.yml` playbook
loop. The bolt-on descriptor's `role_vars` are flat key/value pairs.
Translating one to the other requires either:

- Synthesising a single-entry `vulns_vars` dict per-call (gross, leaky),
  *and*
- Plumbing `domain_username`/`domain_password` lookups from
  `bolton_facts_service` or a vault, which doesn't exist today.

The dispatch surface is too thin for this without a meaningful
re-architecture of how facts and credentials are passed into plays.

### 3.4 Disjoint ESC coverage

| Catalog has | Upstream has |
|---|---|
| ESC1, ESC2 | ESC6, ESC7, ESC10 (case1/case2), ESC11, ESC13, ESC15 |

There is **no overlap at all** in ADCS ESC numbers. If we add catalog
descriptors for ESC6/7/10/11/13/15 in a future phase, the upstream roles
are real candidates — see §5 below.

## 4. Dispatcher configuration change

The dispatcher previously set `ANSIBLE_ROLES_PATH` to
`<project>/ansible/roles` only. To make upstream GOAD roles discoverable
without per-descriptor path gymnastics, I added a new env var:

```
BOLTON_ROLES_SEARCH_PATH   colon-separated list of role search paths.
                           default: "<project>/ansible/roles:<project>/tools/goad/ansible/roles"
```

The default is split into two segments precisely so a future descriptor
can write `import_role: name: vulns/enable_llmnr` and have Ansible
resolve it. Existing project-local roles (`bolton_kerberoastable_svc`,
`bolton_elastic_stack`) still resolve via the first segment. Tests don't
care because the simulate path doesn't shell out to ansible-playbook.

See `webapp/backend/services/bolton_install_service.py` `_run_ansible_job`
(env construction block, around the existing `ANSIBLE_ROLES_PATH` line).

## 5. Remaining gaps — Phase 3d candidates

Catalog descriptors that **still need hand-authored Ansible roles or
inline-PowerShell discipline**:

1. **Identity / Kerberos** — `kerberoastable-svc` (already has
   `ansible/roles/bolton_kerberoastable_svc/`), `asrep-roastable-account`,
   `unconstrained-delegation-svc`. The latter two are short enough that
   inline `microsoft.ad.user` / `microsoft.ad.computer` steps are fine.
2. **Access-control** — `adminsdholder-acl-modified` and
   `generic-write-user` are inline PowerShell with baseline-SDDL capture.
   A new `bolton_ad_acl_with_baseline` role would consolidate the
   capture/apply/revert pattern across both descriptors. Estimated effort:
   one half-day.
3. **Credential-exposure** — `gpp-cpassword-sysvol` (SYSVOL Policies
   construction + Groups.xml drop) and `laps-readable-by-domain-users`
   (Computers-OU ACL with baseline capture). Same ACL-baseline pattern as
   access-control row 2.
4. **ADCS ESC6 / ESC7 / ESC10 / ESC11 / ESC13 / ESC15** — if the catalog
   gets these in Phase 3d, the upstream roles ARE direct candidates with
   the caveat that the dispatcher would need to pass `domain_username` /
   `domain_password` / `domain` into the play. See §3.3.
5. **Infrastructure (Elastic)** — `bolton_elastic_stack` covers all four
   infra descriptors via `shipper_component` discriminator. No upstream
   equivalent; keep as-is.
6. **Web-app / Cloud-container** — `dvwa-lite`, `docker-socket-exposed`.
   Linux-target via `community.docker` modules. No upstream coverage
   (GOAD is Windows-AD only). Keep as-is.
7. **CVE bolt-ons** — `printnightmare`, `zerologon`, `petitpotam`. These
   are inline registry-write + `ansible.windows.win_updates` + service
   restart. Each is short; a hand-authored role would be over-engineering.
   Keep as inline steps.

## 6. Recommended follow-up work

- **Phase 3d (proposed):** add catalog descriptors for ADCS ESC6/7/13/15
  with `import_role: name: vulns/adcs_esc<N>`, gated on a small
  bolton-facts extension that injects `domain_username` + `domain_password`
  as role_vars. This is the single highest-value upstream-reuse
  opportunity in the tree.
- **Phase 3e (proposed):** consolidate the ACL-baseline-capture
  pattern into a new role at `ansible/roles/bolton_ad_acl_with_baseline/`
  with inputs `target_dn`, `grantee`, `right`, `baseline_path`. Refactor
  `adminsdholder-acl-modified`, `generic-write-user`, and
  `laps-readable-by-domain-users` to invoke it. Effort: half-day.
- **No action this phase:** every existing catalog descriptor stays
  as-authored. The dispatcher gains the role-path knob so the choice
  to reuse upstream is per-descriptor, not all-or-nothing.

## 7. Test impact

All 116 bolton tests (`test_bolton_real_ansible.py`,
`test_bolton_schema.py`, `test_bolton_services.py`) pass against the
modified dispatcher. The simulate path is untouched. The roles-path env
var only takes effect on the real-ansible code path which is
end-to-end-tested manually, not in CI.
