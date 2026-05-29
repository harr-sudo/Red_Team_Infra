# Test Lab — Design Spec

Captured 2026-05-20 from operator direction. Built to give the bolt-on
catalog a purpose-controlled set of vulnerable hosts that we own
end-to-end (rather than retrofitting GOAD).

## Decisions (locked-in)

- **Not a new deployment type.** Test lab is an **extension** —
  always sits alongside a C2 deployment (the operator needs C2 infra
  for beacons to call back into the lab from anyway).
- **Same VPC as the C2 deployment.** No peering, no second NAT
  gateway, no second IGW. Test lab hosts live on a new private
  subnet inside the existing C2 VPC. Saves cost + complexity.
- **Two deploy paths:**
  1. NEW c2-* deployment → operator ticks "+ Test Lab" in Configure
     V2 → terraform brings up c2-* infra + test-lab subnet + 4 hosts
     atomically
  2. EXISTING c2-* deployment → "+ Add test lab" action in Manage
     runs a follow-up terraform apply that adds the test-lab subnet
     + hosts to the already-running VPC (Phase 2)
- **Not offered for goad-* or combined-*** — they already have GOAD
  for their lab needs
- **Reuse:** GOAD stays as-is for training; test lab is for catalog
  validation
- **Provisioning:** Ansible on first boot via the existing jumpbox
  pattern. No AMI baking.
- **Naming:** `tl<role>NN` (tldc01, tlms01, tlws01, tllinux01)
- **OS choice:** Win 11 Pro for the workstation. Server 2022 for DC
  + member. Ubuntu 22.04 for Linux.
- **Office:** Microsoft Office free trial on tlms01 + tlws01 (30-day
  trial; lab is short-lived, then re-deploy)
- **AD forest functional level:** Windows Server 2022 (latest)
- **Default credentials:** weak hardcoded creds for the test lab —
  it's isolated and the WHOLE POINT is to be vulnerable. `Password1!`
  for Administrator, `ansible:Ansible123!` for ansible user. Not
  stored in Secrets Manager (no point — they're public knowledge in
  the catalog repo).
- **Operator access:** reuse existing models — RDP to lab Windows
  hosts via the Dashboard Server (the sole SSH/RDP jump, over VPC
  peering); SSM Session Manager for tllinux01. No new ingress points.
- **MSSQL:** deferred. No catalog descriptor needs it today; easy
  add later as a feature flag on tlms01 or a new tlms02.
- **Auto-shutdown / spot instances:** deferred to Phase 2.
- **Egress:** full internet via the existing C2 VPC NAT gateway.
  Some bolt-ons fetch payloads from GitHub etc; restrict later if it
  becomes operationally relevant.
- **Bolt-ons sub-pill visibility:** extend
  `APP.computeVisibleSubPills` so it appears for c2-* deployments
  that have `enable_test_lab=true`. This closes the original gap
  ("why doesn't Bolt-ons appear for existing deployments").
- **E2E test harness:** out of scope this round — handled
  separately as its own follow-up.

## Why not reuse GOAD

- GOAD module brings its own VPC + hostname conventions (dc01 / srv02
  baked into inventory)
- Adding GOAD post-deploy to a c2-only deployment requires tfvars
  mutation + terraform re-apply — fragile
- GOAD is upstream-aligned; we don't control its host matrix, can't
  guarantee a host exists for every bolt-on
- Keeping GOAD as the training-aligned option preserves its value;
  the test lab is for catalog validation, not red-team training

## What we're building

A new Terraform **module** `terraform/modules/test_lab/` instantiated
when the new `enable_test_lab = true` flag is set in tfvars on any
c2-* deployment. Four hosts on a new private subnet INSIDE the
existing C2 VPC.

### Host inventory (covers all 18 vuln descriptors)

| Hostname | OS | Role | Bolt-ons it serves | Size | ~$/mo |
|---|---|---|---|---|---|
| `tldc01` | Windows Server 2022 | `domain_controller` | 11 descriptors (kerberoasting, ADCS ESC1/2, Zerologon, PetitPotam, LLMNR/NBT-NS, GPP-cpassword, LAPS-readable, AdminSDHolder, AS-REP, Generic-Write) | t3.medium | $30 |
| `tlms01` | Windows Server 2022 + ADCS + IIS + SMB + Office trial | `member_server` | 5 descriptors (PrintNightmare, Unconstrained-delegation-svc, Writable-share, SMB-signing-disabled, Macro-doc-share) | t3.medium | $30 |
| `tlws01` | Windows 11 Pro AD-joined + Office trial | `workstation` | Endpoint phishing target; macro execution context | t3.small | $15 |
| `tllinux01` | Ubuntu 22.04 + Docker | `linux_member` | 2 descriptors (DVWA-lite, Docker-socket-exposed) | t3.small | $15 |

Total: 4 hosts, **~$90 / month** in addition to the underlying c2-*
deployment costs. No additional NAT / IGW / peering charges
(reuses C2 VPC's existing infrastructure).

### Network layout — SAME VPC

- **Test lab subnet:** new private subnet at `10.0.20.0/24` inside
  the existing C2 VPC (`10.0.0.0/16`)
- **Same NAT Gateway** as C2 (already in the C2 module)
- **Same Internet Gateway** as C2
- **Same private route table** (or a dedicated test-lab route table
  that also routes 0.0.0.0/0 through C2's NAT)
- **No public IPs** on lab hosts — ingress only via the Dashboard
  Server (VPC peering) + SSM
- **Security groups:**
  - Lab hosts ⇄ Lab hosts: free communication for AD replication +
    bolt-on traffic
  - Dashboard Server (via peering) → Lab hosts: RDP (3389) + WinRM (5985, 5986)
  - GOAD jumpbox (if combined) → Lab hosts: WinRM for Ansible provisioning
  - SSM endpoints: standard

### AD topology

- Single forest: `testlab.local`. NetBIOS: `TESTLAB`
- Single domain (root)
- Forest functional level: Windows Server 2022
- `tldc01` = DC + DNS + AD CS — ADCS installed as Enterprise Root CA
  with NO default templates (so ESC1/ESC2 bolt-ons can author
  vulnerable templates from clean state)
- `tlms01` = Member server; SMB share + IIS + Office trial; SMBv1
  installed but disabled by default
- `tlws01` = Workstation joined to domain; local admin separate from
  domain admin; Office trial; macro execution context permissive
- `tllinux01` = Standalone Linux; not domain-joined; Docker pre-
  installed

### Pre-provisioning approach: Ansible on first boot

Terraform spins up the 4 EC2 instances + base AMIs (Server 2022,
Win 11 Pro, Ubuntu 22). Jumpbox runs the testlab playbook chain
post-instance-ready.

**Phases:**
1. `testlab_base.yml` — WinRM enable, base hardening reversal, set hostname, set DNS to tldc01
2. `testlab_dc.yml` — promote tldc01 to DC, install AD DS + DNS + AD CS, set 2022 forest level
3. `testlab_join.yml` — domain-join tlms01 + tlws01, create `ansible` user
4. `testlab_member.yml` — install ADCS sub-features, IIS, SMB shares, Office trial via winget
5. `testlab_workstation.yml` — base apps, AD-join, Office trial, set up macro execution context
6. `testlab_linux.yml` — install Docker, base hardening, no domain join

- Each playbook idempotent
- Total provision time: ~15-20 min after Terraform completes
- Inventory generated dynamically by a new
  `webapp/backend/routes/test_lab.py` route (mirrors `goad.py`) from
  terraform outputs

### Default credentials (LAB ONLY — intentional)

This lab is isolated and the WHOLE POINT is to be vulnerable.
Credentials are static and public:

- `TESTLAB\Administrator` → `Password1!` (intentionally weak so
  password-spray-style bolt-ons have known targets)
- `TESTLAB\ansible` → `Ansible123!` (for Ansible WinRM continuity)
- Local Administrator on each Windows host → `LocalLab1!`
- `ubuntu` on tllinux01 → SSH key from `key_pair_name` (same as
  jumpbox), no password
- Docker root on tllinux01 → none (Docker daemon socket exposed in
  the docker-socket-exposed bolt-on)

These are documented in the catalog descriptors that depend on them
(e.g., the kerberoastable-svc bolt-on uses Password1! as the SPN
account's weak password — that's the whole attack).

### Where the catalog descriptors get their target hosts

The catalog descriptors already declare `targets.required_roles`
(`domain_controller`, `member_server`, `workstation`, `linux_member`,
`standalone`). The test lab produces hosts whose role facts match:

- tldc01 → `domain_controller`
- tlms01 → `member_server`
- tlws01 → `workstation`
- tllinux01 → `linux_member`

So bolt-ons attached to a test lab pick the right host via the
existing dispatcher compatibility check; no schema changes needed.

The host facts service (`webapp/backend/services/bolton_facts_service.py`)
gets a small extension so when a deployment has `enable_test_lab=true`,
its host list includes the 4 testlab hosts with correctly-tagged
roles (replacing the current `_MOCK_HOST_FACTS` fallback).

## Roll-out

### Phase 1 — Now (this work)

1. **Terraform module** `terraform/modules/test_lab/` — 4 EC2
   instances + new private subnet inside the C2 VPC + per-host
   security groups + IAM. **No new VPC. No peering. No new NAT.**

2. **Main.tf integration** — add a `module "test_lab"` block gated on
   `local.enable_test_lab && local.deploy_c2`. Passes the C2 VPC ID
   + an available CIDR slot.

3. **Variables** — `variables.tf` gets `enable_test_lab`,
   `test_lab_subnet_cidr` (default `10.0.20.0/24`).

4. **Ansible** — new directory `ansible/playbooks/testlab/` with the
   6 phase playbooks. New roles `ansible/roles/testlab_dc`,
   `testlab_member`, `testlab_workstation`, `testlab_linux`.

5. **Dashboard wiring**
   - Configure V2 — add a "+ Test Lab" toggle inside the C2 sections
     (only visible for c2-* family selections). Live cost preview
     adds the testlab line items.
   - Bolt-ons sub-pill — when an existing c2-* deployment has
     `enable_test_lab=true`, Bolt-ons sub-pill becomes visible. The
     visibility logic `APP.computeVisibleSubPills` learns about a
     new helper `APP.activeDeployment.hasTestLab`.
   - Host facts — `bolton_facts_service.py` resolves real testlab
     hosts from the deployment state.

### Phase 2 — Deferred

- "+ Add test lab to existing deployment" action in Manage (post-
  deploy retrofit) — Phase 1 ships new-deployment only via Configure
  V2
- MSSQL on `tlms02` for future SQL bolt-ons
- Test lab variants beyond `mini`
- E2E catalog walk-through harness
- Cost optimization (spot instances, scheduled shutdown)
- Egress lockdown to approved domains only

## tfvars shape

```hcl
deployment_type      = "c2-adhoc"
enable_test_lab      = true            # new flag
test_lab_subnet_cidr = "10.0.20.0/24"  # default

project_name      = "c2_adhoc_dev_lab_alpha"
# ... rest of c2-adhoc config ...
```

When `enable_test_lab = false` (or unset), zero test-lab resources
are created — fully backwards-compatible with every existing c2-*
tfvars file on disk.

## Naming + conventions

- Hostnames: `tl<role>NN` (tldc01, tlms01, tlws01, tllinux01)
- Domain: `testlab.local`. NetBIOS: `TESTLAB`
- Default admin: `testlab\Administrator` with weak password
- Ansible user: `ansible` (matches GOAD pattern)
- AWS tags: `Lab = test-lab`, `Project = <project_name>`

## Quick win shipped alongside this work

Frontend filters the bolt-on Target Host dropdown by the selected
descriptor's `targets.required_roles` (data already in the catalog;
the dispatcher already refuses bad pairings at install time — this
just makes the UX surface it earlier).
