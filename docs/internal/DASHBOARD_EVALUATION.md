# Dashboard Evaluation for Red/Purple Team Operators

## Current Feature Assessment

| Feature | Usefulness | Notes |
|---------|-----------|-------|
| **11 Deployment Types** | ★★★★★ | Covers every realistic engagement scenario. The combined modes (C2+GOAD) are particularly strong for purple team work. |
| **Configuration UI** | ★★★★★ | Eliminates manual tfvars editing. OPSEC guardrails (blocks `0.0.0.0/0`, password strength) prevent common mistakes. |
| **Malleable C2 Profile System** | ★★★★★ | Built-in presets + BC-SECURITY catalog + custom paste with auto-generated Nginx config and traffic preview. This alone saves hours per engagement. |
| **Domain Fronting Toggle** | ★★★★★ | One checkbox to go from direct redirectors to CloudFront-proxied C2. Backup domain pre-loading for instant rotation is excellent. |
| **GOAD Lab Management** | ★★★★★ | Full lifecycle: deploy, provision AD, poll status, extract credentials, start/stop. First-class purple team training. |
| **Pre-Reqs Validation** | ★★★★☆ | Catches missing tools, bad creds, wrong IAM perms before you waste 15 minutes on a failed deploy. Missing: validates terraform version compatibility. |
| **Deployment Manager (Start/Stop)** | ★★★★☆ | Cost savings by stopping instances overnight is real. Missing: scheduled stop/start (e.g., auto-stop at 6pm). |
| **Tools Upload (SCP to Attack Box)** | ★★★★☆ | Drag-and-drop file transfer through the Dashboard Server. Useful but limited to one-way push. |
| **CS Archive + Client Upload** | ★★★★☆ | S3 with content-hash dedup is clean. License activation from Secrets Manager removes manual step. |
| **SSL/TLS Configuration** | ★★★★☆ | Let's Encrypt auto-renewal is the right default. Self-signed OPSEC warning is a nice touch. |
| **Architecture Diagrams** | ★★★★☆ | 19 diagrams covering every deployment mode. Good for team briefings and engagement planning. |
| **Multi-Project Workspaces** | ★★★★☆ | Run concurrent engagements from one machine. Each project isolated in its own Terraform workspace. |
| **Connection Info** | ★★★☆☆ | Shows SSH commands and IPs, but the operator still has to copy-paste and manually connect. |
| **Deployment Logs** | ★★★☆☆ | Terraform output with phase tracking. Good for debugging deploys, less useful during actual operations. |
| **Settings Page** | ★★☆☆☆ | Only has auto-refresh interval. Feels empty. |

---

## What's Missing — High-Value Features

### 1. Attack Box Portability — ★★★★★

An operator's attack box accumulates customizations over weeks: tool configs, browser profiles, Cobalt Strike client settings, custom scripts, credential files. Rebuilding from scratch per engagement is wasteful.

**Implementation approach:**
- **AMI Snapshot**: Before teardown, snapshot the attack box EBS volume to a private AMI. On next engagement, launch from that AMI instead of the base Windows image.
- **Dashboard integration**: "Save Attack Box" button on the Deployment Manager page that creates a named AMI. "Restore Attack Box" dropdown on the Configuration page that lists saved AMIs.
- **Profile system**: Name snapshots by operator or engagement type (e.g., "harris-base-tools", "ad-engagement-v2").
- Keeps tools, configs, browser state, CS client setup, custom scripts — everything the operator has built up.

---

### 2. Engagement Tracker / Operations Log — ★★★★★

During an engagement, operators need to track: what they did, when, what they found. Right now there's no operational logging beyond Terraform deploy logs.

- Timestamped operations log (manual entries + auto-captured events)
- Credential/hash vault (store creds found during the engagement, searchable)
- Screenshot/evidence attachment
- MITRE ATT&CK technique tagging per entry
- Export to markdown/PDF for reporting

---

### 3. Infrastructure Health Dashboard — ★★★★★

The current dashboard only shows "is EC2 running." An operator needs:

- **C2 server health**: Is the team server process running? Listener port open? Last beacon callback time (via CS aggressor script or log parsing)
- **Redirector health**: Is Nginx up? SSL cert days until expiry? HTTP response code check on decoy site
- **DNS propagation status**: After deployment, show real-time propagation across major resolvers (Google, Cloudflare, etc.)
- **Beacon connectivity test**: Curl the redirector callback URI and verify the expected response

---

### 4. Redirector / Domain Rotation UI — ★★★★☆

If a redirector IP or domain gets burned mid-engagement:

- One-click "Rotate Redirector" that destroys the old redirector, creates a new one, updates DNS records
- Domain rotation: switch from primary to backup domain with a single button (update Route53 + CloudFront alias)
- IP reputation check integration before rotation (is the new IP already flagged?)

---

### 5. Scheduled Infrastructure Management — ★★★★☆

- Auto-stop instances at a set time (e.g., 6pm local) and auto-start at 8am
- Weekend shutdown schedule
- Estimated cost savings displayed
- "Engagement end date" with auto-destroy reminder/countdown

---

### 6. Live Cost Tracker — ★★★★☆

- Pull real-time AWS Cost Explorer data per project (tagged resources)
- Running total for the engagement
- Budget alert threshold (e.g., warn at $500)
- Cost breakdown by component (C2 servers vs. GOAD VMs vs. NAT gateway)

---

### 7. Quick Connect Panel — ★★★★☆

Replace copy-paste SSH commands with one-click actions:

- "Connect to Dashboard Server" — opens terminal with SSH command pre-filled
- "Tunnel to C2" — opens SSH tunnel through the Dashboard Server (`ssh -L 50050:...`)
- "RDP to Attack Box" — launches RDP client with correct IP and port
- "SSH to GOAD Jumpbox" — jumpbox connection through the Dashboard Server
- Generate `.ssh/config` entries for the current deployment

---

### 8. IOC Self-Tracking — ★★★★☆

Know what the blue team can find:

- Auto-catalog your IOCs: domain names, IPs, CS profile URIs, user agents, certificate fingerprints
- Export IOC list for deconfliction with the blue team (purple team use case)
- Pre-engagement: check if your domains/IPs are already flagged on VirusTotal, AbuseIPDB

---

### 9. Payload/Implant Inventory — ★★★☆☆

- Track which payloads are staged where (which redirector URI, which host)
- Associate payloads with their malleable profile
- Quick reference during operations: "what did I deploy to target X?"

---

### 10. Post-Engagement Cleanup Wizard — ★★★☆☆

- Guided teardown: archive logs → snapshot attack box → export credentials → destroy infrastructure → verify no orphaned resources
- "Evidence export" bundle: download all operational logs, CS logs, screenshots as a single archive
- Orphaned resource scan (find AWS resources that survived `terraform destroy`)

---

## Summary

The dashboard is already **well above average** for a self-hosted red team management tool. The deployment configuration system, malleable profile integration, GOAD first-class support, and domain fronting toggle are genuinely strong features that save significant operator time.

The biggest gaps are in the **during-operations** phase — once infrastructure is deployed, the dashboard mostly stops being useful until teardown. The features above (especially attack box portability, engagement tracker, health monitoring, and quick connect) would keep it valuable throughout the entire engagement lifecycle, not just at deploy/destroy time.

The attack box AMI idea is the single highest-ROI feature to build next. It's technically straightforward (EC2 `create-image` API call + an AMI picker in the config UI) and solves a real pain point every operator hits.
