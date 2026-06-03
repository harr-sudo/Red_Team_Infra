# Bolton Catalog Descriptor Host Applicability Inventory

## Descriptor Applicability by Host Role

| ID | Slug | Category | Description | Target Host Role(s) |
|---|---|---|---|---|
| bolton.known-cve.petitpotam | petitpotam | known-cve | MS-EFSRPC coercion allowing DC machine account forced authentication to NTLM relay. | Domain Controller |
| bolton.known-cve.zerologon | zerologon | known-cve | Netlogon privilege escalation (CVE-2020-1472) via AES-CFB8 all-zero authentication pattern. | Domain Controller |
| bolton.known-cve.printnightmare | printnightmare | known-cve | Print Spooler RCE via Point-and-Print policy bypass and DLL injection. | Domain Controller, Domain Member Server |
| bolton.adcs.esc1-misconfigured-template | esc1-misconfigured-template | adcs | Certificate template allows enrollee-supplied subject with Client Authentication EKU. | CA Host (Domain Member Server with ADCS role) |
| bolton.adcs.esc2-any-purpose-eku | esc2-any-purpose-eku | adcs | Certificate template with Any Purpose EKU allowing PKINIT abuse. | CA Host (Domain Member Server with ADCS role) |
| bolton.identity-kerberos.asrep-roastable-account | asrep-roastable-account | identity-kerberos | User account with DONT_REQ_PREAUTH flag set, enabling offline AS-REP cracking. | Domain Controller (creates domain user) |
| bolton.identity-kerberos.kerberoastable-svc | kerberoastable-svc | identity-kerberos | Service account with registered SPN and weak password enabling Kerberoasting. | Domain Controller (creates domain user) |
| bolton.identity-kerberos.unconstrained-delegation-svc | unconstrained-delegation-svc | identity-kerberos | Computer account flagged for unconstrained Kerberos delegation. | Domain Member Server |
| bolton.access-control.adminsdholder-acl-modified | adminsdholder-acl-modified | access-control | Non-privileged user granted GenericAll on AdminSDHolder with SDPROP propagation. | Domain Controller |
| bolton.access-control.generic-write-user | generic-write-user | access-control | Non-privileged user granted GenericWrite on privileged AD group (Account Operators). | Domain Controller |
| bolton.service-misconfig.writable-share-everyone | writable-share-everyone | service-misconfig | SMB share with Everyone:Full permissions enabling lateral movement. | Domain Member Server |
| bolton.protocol-network.llmnr-nbtns-enabled | llmnr-nbtns-enabled | protocol-network | Domain GPO re-enables LLMNR/NBT-NS broadcast resolution for Responder hash capture. | Domain Controller (GPO deployment) |
| bolton.protocol-network.smb-signing-disabled | smb-signing-disabled | protocol-network | SMB signing disabled on member server to enable NTLM relay attacks. | Domain Member Server |
| bolton.endpoint-phishing.macro-enabled-doc-share | macro-enabled-doc-share | endpoint-phishing | Macro-enabled .docm file dropped on writable share for phishing training. | Domain Member Server (requires Office + SMB) |
| bolton.credential-exposure.gpp-cpassword-sysvol | gpp-cpassword-sysvol | credential-exposure | Group Policy Preferences XML with static-AES-key-encrypted cpassword in SYSVOL. | Domain Controller |
| bolton.credential-exposure.laps-readable-by-domain-users | laps-readable-by-domain-users | credential-exposure | ACL modification allowing Domain Users to read LAPS ms-Mcs-AdmPwd attribute. | Domain Controller (Computers OU ACL) |
| bolton.web-app.dvwa-lite | dvwa-lite | web-app | Vulnerable web application (SQLi, XSS, RCE) deployed via Docker on Linux. | Standalone Linux (jumpbox with Docker) |
| bolton.cloud-container.docker-socket-exposed | docker-socket-exposed | cloud-container | Docker socket bind-mounted inside container enabling trivial host escape. | Standalone Linux (Docker host) |
| bolton.infrastructure.sysmon | sysmon | infrastructure | Sysmon with SwiftOnSecurity configuration for endpoint telemetry. | Any Windows host (DC, member, workstation) + Standalone Linux member |
| bolton.infrastructure.winlogbeat-shipper | winlogbeat-shipper | infrastructure | Winlogbeat log shipper forwarding Security/Sysmon/PowerShell events. | Any Windows host (DC, member, workstation) |
| bolton.infrastructure.elastic-detection-stack | elastic-detection-stack | infrastructure | Elasticsearch + Kibana + Fleet Server single-node deployment. | Standalone Linux |
| bolton.infrastructure.filebeat-shipper | filebeat-shipper | infrastructure | Filebeat log shipper forwarding syslog/auditd journal to Elastic stack. | Standalone Linux, Linux Domain Member |

---

## Host Role Applicability Summary

### Domain Controller (DC)
**10 descriptors** targeting DC-only or DC-primary vulnerabilities:
- petitpotam, zerologon, esc1-misconfigured-template, esc2-any-purpose-eku, asrep-roastable-account, kerberoastable-svc, adminsdholder-acl-modified, generic-write-user, llmnr-nbtns-enabled, gpp-cpassword-sysvol, laps-readable-by-domain-users

### Domain Member Server
**7 descriptors** targeting member-server-specific misconfigurations:
- printnightmare (also DC), unconstrained-delegation-svc, writable-share-everyone, smb-signing-disabled, macro-enabled-doc-share

### Standalone Linux
**4 descriptors** targeting Linux infrastructure or containers:
- dvwa-lite, docker-socket-exposed, elastic-detection-stack, filebeat-shipper (also accepts linux_member)

### Any Windows Host (DC, Member, Workstation)
**3 infrastructure descriptors** applicable to all Windows roles:
- sysmon, winlogbeat-shipper

### Domain Workstation
**0 descriptors** explicitly target workstations in required_roles (infrastructure tools apply but don't "target" the workstation role uniquely).

---

## Ambiguous Descriptors

**None.** Each descriptor declares required_roles explicitly. Two descriptors have multi-role applicability:
- **printnightmare:** DC and member_server (RCE via spooler exists on both)
- **unconstrained-delegation-svc:** member_server only (applies to member server computer accounts, not DC which has its own delegation model)

---

## Descriptors Without Clean Host-Role Mapping

**3 infrastructure descriptors** (category: infrastructure) are observability/detection tooling, not vulnerabilities. They have role applicability but are not "attack surfaces":

1. **sysmon** → requires_roles: [domain_controller, member_server, workstation, linux_member]
   - *Not a vulnerability.* Installs endpoint telemetry collection.

2. **winlogbeat-shipper** → requires_roles: [domain_controller, member_server, workstation]
   - *Not a vulnerability.* Forwards Windows event channels to Elastic.

3. **elastic-detection-stack** → requires_roles: [standalone]
   - *Not a vulnerability.* Deploys centralized detection and alerting infrastructure.

4. **filebeat-shipper** → requires_roles: [standalone, linux_member]
   - *Not a vulnerability.* Forwards Linux syslog/auditd to Elastic.

These four **infrastructure** descriptors are explicitly allowed by the schema to omit `patch` blocks (see schema.py `_patch_required_unless_infrastructure`). They support the lab but don't represent exploitation surfaces.

---

## Proposed Schema Addition

Add an optional field to descriptor YAML to explicitly declare target host role eligibility. This enables UI filtering:

```yaml
applicable_host_roles:
  - domain-controller
  - domain-member-server
  - domain-workstation
  - standalone-linux
  - linux-domain-member
  - ca-host
```

**Benefits:**
- Bolt-on dropdown can filter catalog by selected host type
- Prevents accidental deployment of DC-specific exploits to members
- Makes host-role dependencies machine-readable
- Simplifies schema validation (ensure at least one role in applicable_host_roles matches required_roles)

**Example integration:**
```yaml
# In UI host-selection dropdown
if host.role == "domain_controller":
  show_descriptors = [d for d in catalog if "domain-controller" in d.applicable_host_roles]
```

---

## Document Metadata

- **Inventory Date:** 2026-05-20
- **Catalog Version:** 1.0.0 (stable)
- **Total Descriptors:** 22
- **Infrastructure Components:** 4
- **Vulnerability/Exploit Descriptors:** 18
- **Generated from:** `webapp/bolton/catalog/**/*.yaml`

