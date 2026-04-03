# Per-Project Deployment Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Deployment Manager correctly display connection info, credentials, and post-deployment checklists for each project independently when multiple deployments coexist.

**Architecture:** Replace the global `cachedInfraData`/`cachedConfigData` singleton pattern with per-project lazy loading. Every deployment card fetches its own data via `/deploy/outputs?project=X` (already per-project) and a new `/goad/credentials?project=X` parameter. The post-deployment checklist and C2 connection info switch from reading global caches to accepting project data as a parameter.

**Tech Stack:** Flask (Python), vanilla JS, AWS boto3 (EC2 describe_instances)

---

### Task 1: Extend `/deploy/outputs` to include config and deployment_type fields

The `/deploy/outputs?project=X` endpoint already returns per-project instance data via AWS tags. It also reads some config fields. We need to ensure it returns everything that `buildPostDeployChecklist` and `renderC2ConnectionInfo` need.

**Files:**
- Modify: `webapp/backend/routes/deploy.py:4415-4530` (get_terraform_outputs function)

- [ ] **Step 1: Read current endpoint and verify fields**

The endpoint already returns these config-sourced fields (lines 4506-4511):
```python
outputs['redirector_domain'] = config.get('primary_domain_name', '')
outputs['c2_subdomain'] = config.get('c2_subdomain', 'api')
outputs['key_pair_name'] = config.get('key_pair_name', '')
outputs['cs_teamserver_password'] = config.get('cs_teamserver_password', '')
outputs['cobalt_strike_license_secret_name'] = config.get('cobalt_strike_license_secret_name', '')
outputs['deployment_type'] = config.get('deployment_type', '')
```

Add the missing fields that `buildPostDeployChecklist` needs:

```python
# After the existing config fields (after line 4511), add:
outputs['primary_domain_name'] = config.get('primary_domain_name', '')
outputs['malleable_profile'] = config.get('malleable_profile', '')
outputs['enable_domain_fronting'] = config.get('enable_domain_fronting', False)
outputs['ssl_provider'] = config.get('ssl_provider', 'letsencrypt')
```

- [ ] **Step 2: Add attack box password decryption**

The endpoint already has `attackbox_password` from a separate decryption flow at the deploy completion step, but `get_terraform_outputs` doesn't decrypt it live. Check if it's already handled. If not, add EC2 password decryption for the attack box instance (reading from the `tls_private_key` in Terraform state or from the stored password in deployment state).

Look at lines 942-949 in deploy.py for the existing `get_windows_password()` pattern. If the `/outputs` endpoint doesn't already call it, add it after instance discovery:

```python
# After the instance loop, before returning
if outputs.get('attackbox_instance_id') and not outputs.get('attackbox_password'):
    try:
        # Check deployment state for cached password
        state_file = project_root / "logs" / "deployment_state" / f"{project_name}.state.json"
        if state_file.exists():
            import json as json_mod
            state_data = json_mod.loads(state_file.read_text())
            stored_outputs = state_data.get("output", {})
            ab_pw = stored_outputs.get("attack_box_admin_password", {}).get("value")
            if ab_pw:
                outputs['attackbox_password'] = ab_pw
    except Exception:
        pass
```

- [ ] **Step 3: Verify endpoint returns complete data**

```bash
curl -s 'http://127.0.0.1:5000/api/deploy/outputs?project=c2_adhoc_dev_harriss_macbook_pro_01' | python3 -m json.tool | head -40
curl -s 'http://127.0.0.1:5000/api/deploy/outputs?project=goad_mini_dev_harriss_macbook_pro' | python3 -m json.tool | head -40
```

Verify both return `deployment_type`, `redirector_domain`, `c2_subdomain`, IPs for all relevant instances.

- [ ] **Step 4: Commit**

```bash
git add webapp/backend/routes/deploy.py
git commit -m "feat: extend /deploy/outputs with config fields for per-project rendering"
```

---

### Task 2: Add project parameter to `/goad/credentials` endpoint

Currently `/goad/credentials` reads from a single `current_deployment.json` marker. Add optional `?project=X` support that determines the lab type from the project's deployment type instead of the marker file.

**Files:**
- Modify: `webapp/backend/routes/goad.py:828-967` (get_credentials function)

- [ ] **Step 1: Add project-based lab type resolution**

At the top of `get_credentials()` (line 829), add project parameter handling that falls back to the existing marker logic:

```python
@bp.route('/credentials', methods=['GET'])
def get_credentials():
    """Get credentials for the deployed GOAD lab"""
    # Support per-project lookup via query param
    project_name = request.args.get('project')
    lab_name = None

    if project_name:
        # Derive lab type from deployment type in config or logs
        from webapp.backend.utils.config_parser import ConfigParser, get_goad_lab_type
        project_root = get_project_root()
        # Check deployment state for this project's deployment_type
        state_file = project_root / "logs" / "deployment_state" / f"{project_name}.state.json"
        if state_file.exists():
            try:
                state_data = json.loads(state_file.read_text())
                deploy_type = state_data.get("deployment_type", "")
                lab_name = get_goad_lab_type(deploy_type)
            except Exception:
                pass
        # Fallback: parse from project name pattern (e.g., goad_mini_dev_... -> GOAD-Mini)
        if not lab_name:
            for dt, info in DEPLOYMENT_TYPE_MAP.items():
                if dt.replace('-', '_') in project_name and 'goad_lab' in info:
                    lab_name = info['goad_lab']
                    break

    # Existing marker-based fallback
    if not lab_name:
        goad_workspace = get_goad_workspace()
        deployment_marker = goad_workspace / 'current_deployment.json'
        if not deployment_marker.exists():
            return jsonify({
                'success': False,
                'error': 'No GOAD deployment found'
            }), 404
        try:
            with open(deployment_marker, 'r') as f:
                deployment = json.load(f)
            lab_name = deployment.get('lab_name')
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    # Rest of function continues with lab_name...
```

- [ ] **Step 2: Import DEPLOYMENT_TYPE_MAP at top of goad.py**

Near the existing imports in goad.py, add:

```python
from webapp.backend.utils.config_parser import DEPLOYMENT_TYPE_MAP
```

- [ ] **Step 3: Also store deployment_type in state files**

Check that the deploy thread in `deploy.py` saves `deployment_type` to the state file. Look at the `_persist_state` calls. The state dict should include `deployment_type`. If not present, add it where the state is initialized (around line 800 in deploy.py, in the deploy thread function):

```python
state["deployment_type"] = deploy_type
```

- [ ] **Step 4: Verify per-project credentials work**

```bash
curl -s 'http://127.0.0.1:5000/api/goad/credentials?project=goad_mini_dev_harriss_macbook_pro' | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK' if d.get('success') else d.get('error'))"
```

- [ ] **Step 5: Commit**

```bash
git add webapp/backend/routes/goad.py webapp/backend/routes/deploy.py
git commit -m "feat: add per-project support to /goad/credentials endpoint"
```

---

### Task 3: Replace global caches with per-project cache map in frontend

Replace the three global singletons with a single per-project cache map. SSH key data is user-global (same key for all projects) so it stays as a singleton.

**Files:**
- Modify: `webapp/frontend/js/app.js:13145-13147` (cache declarations)
- Modify: `webapp/frontend/js/app.js:12943-13059` (refreshDeployments)

- [ ] **Step 1: Replace cache declarations**

At `app.js:13145-13147`, replace:

```javascript
let cachedInfraData = (() => { try { const v = localStorage.getItem('red_team_cached_infra'); return v ? JSON.parse(v) : null; } catch { return null; } })();
let cachedConfigData = (() => { try { const v = localStorage.getItem('red_team_cached_config'); return v ? JSON.parse(v) : null; } catch { return null; } })();
let cachedSshKeyData = (() => { try { const v = localStorage.getItem('red_team_cached_ssh_key'); return v ? JSON.parse(v) : null; } catch { return null; } })();
```

With:

```javascript
// Per-project cache: { [projectName]: { outputs: {...}, config: {...} } }
let projectDataCache = (() => { try { const v = localStorage.getItem('red_team_project_cache'); return v ? JSON.parse(v) : {}; } catch { return {}; } })();
// SSH key data is user-global (same key for all projects)
let cachedSshKeyData = (() => { try { const v = localStorage.getItem('red_team_cached_ssh_key'); return v ? JSON.parse(v) : null; } catch { return null; } })();
// Keep old globals as thin wrappers for any code that still reads them during migration
let cachedInfraData = null;
let cachedConfigData = null;
```

- [ ] **Step 2: Add helper to get/set per-project cache**

Add right after the declarations:

```javascript
function getProjectData(projectName) {
    return projectDataCache[projectName] || null;
}

function setProjectData(projectName, data) {
    projectDataCache[projectName] = data;
    try { localStorage.setItem('red_team_project_cache', JSON.stringify(projectDataCache)); } catch {}
}
```

- [ ] **Step 3: Update refreshDeployments to fetch SSH key only (remove global infra fetch)**

In `refreshDeployments()` (app.js:12943), the parallel fetches currently populate global caches. Change to only fetch the user-global data (SSH key). Per-project data will be lazy-loaded by each card.

Replace the parallel fetch block (lines 12955-12984) with:

```javascript
// Fetch user-global data only; per-project data is lazy-loaded by each card
const [goadResponse, sshKeyResponse] = await Promise.all([
    fetch(`${API_BASE}/goad/status`),
    fetch(`${API_BASE}/deploy/ssh-public-key`).catch(() => null),
]);

const goadData = await goadResponse.json();

// Cache SSH key (user-global, same for all projects)
try {
    if (sshKeyResponse && sshKeyResponse.ok) {
        const sshData = await sshKeyResponse.json();
        cachedSshKeyData = (sshData.success && sshData.has_key) ? sshData : null;
        localStorage.setItem('red_team_cached_ssh_key', cachedSshKeyData ? JSON.stringify(cachedSshKeyData) : '');
    }
} catch (e) { cachedSshKeyData = null; }
```

Remove the `cachedInfraData` and `cachedConfigData` localStorage writes entirely. Keep the rest of `refreshDeployments` unchanged (GOAD panel rendering, timeline rendering).

- [ ] **Step 4: Commit**

```bash
git add webapp/frontend/js/app.js
git commit -m "refactor: replace global infra caches with per-project cache map"
```

---

### Task 4: Create `loadProjectData(projectName)` helper

A single async function that fetches and caches per-project data from `/deploy/outputs?project=X`. Used by connection info, checklist, and credentials rendering.

**Files:**
- Modify: `webapp/frontend/js/app.js` (add new function near `loadConnectionInfo` around line 10670)

- [ ] **Step 1: Add the helper function**

Insert before `loadConnectionInfo`:

```javascript
/**
 * Fetch and cache per-project deployment data (outputs + config).
 * Returns cached data immediately if available, otherwise fetches from API.
 */
async function loadProjectData(projectName) {
    if (!projectName) return null;

    // Return cached if available
    const cached = getProjectData(projectName);
    if (cached) return cached;

    try {
        const response = await fetch(`${API_BASE}/deploy/outputs?project=${encodeURIComponent(projectName)}`);
        const data = await response.json();

        if (!data.success || !data.outputs) return null;

        const outputs = data.outputs;

        // Normalize into the shape that rendering functions expect
        const projectData = {
            outputs: outputs,
            deployment_type: outputs.deployment_type || '',
            // Structured bastion object
            bastion: {
                public_ip: outputs.bastion_public_ip || '',
                private_ip: outputs.bastion_private_ip || '',
                instance_id: outputs.bastion_instance_id || '',
                enabled: !!outputs.bastion_public_ip,
            },
            // Structured c2_servers object
            c2_servers: {
                servers: (outputs.c2_servers || []).reduce((acc, s, i) => {
                    acc[`server-${i}`] = s;
                    return acc;
                }, {}),
                private_ips: (outputs.c2_servers || []).map(s => s.private_ip),
                instance_ids: (outputs.c2_servers || []).map(s => s.instance_id),
            },
            // Structured redirectors object
            redirectors: {
                public_ips: (outputs.redirectors || []).map(r => r.public_ip),
                private_ips: (outputs.redirectors || []).map(r => r.private_ip),
                instance_ids: (outputs.redirectors || []).map(r => r.instance_id),
            },
            // Attack box
            attack_box: {
                enabled: !!outputs.attackbox_private_ip,
                private_ip: outputs.attackbox_private_ip || '',
                admin_password: outputs.attackbox_password || '',
                instance_id: outputs.attackbox_instance_id || '',
            },
            // Config fields
            config: {
                redirector_domain: outputs.redirector_domain || outputs.primary_domain_name || '',
                primary_domain_name: outputs.primary_domain_name || outputs.redirector_domain || '',
                c2_subdomain: outputs.c2_subdomain || 'api',
                cs_teamserver_password: outputs.cs_teamserver_password || '',
                cobalt_strike_license_secret_name: outputs.cobalt_strike_license_secret_name || '',
                malleable_profile: outputs.malleable_profile || '',
                deployment_type: outputs.deployment_type || '',
            },
            // GOAD fields
            jumpbox_public_ip: outputs.jumpbox_public_ip || '',
            teamserver_private_ip: outputs.teamserver_private_ip || '',
        };

        setProjectData(projectName, projectData);
        return projectData;
    } catch (e) {
        console.error(`Failed to load project data for ${projectName}:`, e);
        return null;
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add webapp/frontend/js/app.js
git commit -m "feat: add loadProjectData helper for per-project cache"
```

---

### Task 5: Convert `buildPostDeployChecklist` to accept project data

Change from reading global `cachedInfraData`/`cachedConfigData` to accepting a data parameter. Make it async since it may need to fetch data.

**Files:**
- Modify: `webapp/frontend/js/app.js:15507-15525` (function signature and data reads)
- Modify: `webapp/frontend/js/app.js:14309` (call site in timeline template)

- [ ] **Step 1: Change function to accept projectData parameter**

At line 15507, change:

```javascript
function buildPostDeployChecklist(sessionId) {
    if (!cachedInfraData) return '';

    const bastion = cachedInfraData.bastion || {};
    const bastionIp = bastion.public_ip || '<BASTION_IP>';
    const c2Servers = cachedInfraData.c2_servers || {};
    const servers = c2Servers.servers || {};
    const serverIps = c2Servers.private_ips || [];
    const c2Ip = Object.values(servers)[0]?.private_ip || serverIps[0] || '<C2_PRIVATE_IP>';
    const redirectors = cachedInfraData.redirectors || {};
    const redirPublicIps = redirectors.public_ips || [];
    const redirIp = redirPublicIps[0] || '<REDIRECTOR_IP>';
    const attackBox = cachedInfraData.attack_box || {};
    const config = cachedConfigData || {};
    const primaryDomain = config.redirector_domain || config.primary_domain_name || '';
    const c2Sub = config.c2_subdomain || 'api';
    const domain = primaryDomain ? `${c2Sub}.${primaryDomain}` : '<YOUR_DOMAIN>';
    const csPassword = config.cs_teamserver_password || '';
    const csLicenseKey = config.cobalt_strike_license_secret_name || '';
```

To:

```javascript
function buildPostDeployChecklist(sessionId, projectData) {
    if (!projectData) return '';

    const bastion = projectData.bastion || {};
    const bastionIp = bastion.public_ip || '<BASTION_IP>';
    const c2Servers = projectData.c2_servers || {};
    const servers = c2Servers.servers || {};
    const serverIps = c2Servers.private_ips || [];
    const c2Ip = Object.values(servers)[0]?.private_ip || serverIps[0] || '<C2_PRIVATE_IP>';
    const redirectors = projectData.redirectors || {};
    const redirPublicIps = redirectors.public_ips || [];
    const redirIp = redirPublicIps[0] || '<REDIRECTOR_IP>';
    const attackBox = projectData.attack_box || {};
    const config = projectData.config || {};
    const primaryDomain = config.redirector_domain || config.primary_domain_name || '';
    const c2Sub = config.c2_subdomain || 'api';
    const domain = primaryDomain ? `${c2Sub}.${primaryDomain}` : '<YOUR_DOMAIN>';
    const csPassword = config.cs_teamserver_password || '';
    const csLicenseKey = config.cobalt_strike_license_secret_name || '';
```

The `cachedSshKeyData` reference further down (lines 15529-15539) stays as-is since SSH key data is user-global.

- [ ] **Step 2: Convert call site to lazy-load with ontoggle**

At line 14309, the checklist currently renders inline:

```javascript
${isSuccess && isC2Deployment ? buildPostDeployChecklist(sessionId) : ''}
```

Replace with a lazy-loaded `<details>` block:

```javascript
${isSuccess && isC2Deployment ? `
    <details class="details-card" data-details-id="${sessionId}-checklist"
             ontoggle="if(this.open){loadPostDeployChecklist('${projectName}','${sessionId}')}">
        <summary style="font-weight: 600;">Post-Deployment Checklist</summary>
        <div id="${sessionId}-checklist-content">
            Loading checklist...
        </div>
    </details>
` : ''}
```

- [ ] **Step 3: Add the lazy-load wrapper function**

Add near `loadConnectionInfo`:

```javascript
async function loadPostDeployChecklist(projectName, sessionId) {
    const contentDiv = document.getElementById(`${sessionId}-checklist-content`);
    if (!contentDiv) return;

    // Skip if already loaded
    const text = contentDiv.textContent.trim();
    if (text !== 'Loading checklist...' && text !== '') return;

    const projectData = await loadProjectData(projectName);
    const html = buildPostDeployChecklist(sessionId, projectData);
    contentDiv.innerHTML = html || '<div class="t-secondary">No checklist data available. Expand Connection Info to load infrastructure data first.</div>';
}
window.loadPostDeployChecklist = loadPostDeployChecklist;
```

- [ ] **Step 4: Commit**

```bash
git add webapp/frontend/js/app.js
git commit -m "refactor: convert post-deploy checklist to per-project lazy loading"
```

---

### Task 6: Convert `renderC2ConnectionInfo` to accept project data

Same pattern as the checklist — stop reading global caches, accept data as a parameter.

**Files:**
- Modify: `webapp/frontend/js/app.js:15772-15810` (function signature and data reads)
- Modify: `webapp/frontend/js/app.js:14157-14162` (call site)

- [ ] **Step 1: Change function signature**

At line 15772, change:

```javascript
function renderC2ConnectionInfo() {
    if (!cachedInfraData) return '<div class="t-secondary">Loading infrastructure data...</div>';
    const config = cachedConfigData || {};
    const bastion = cachedInfraData.bastion || {};
    // ... rest reads from cachedInfraData
```

To:

```javascript
function renderC2ConnectionInfo(projectData) {
    if (!projectData) return '<div class="t-secondary">Loading infrastructure data...</div>';
    const config = projectData.config || {};
    const bastion = projectData.bastion || {};
```

Then replace every remaining `cachedInfraData.` reference in the function body with `projectData.`:
- `cachedInfraData.c2_servers` -> `projectData.c2_servers`
- `cachedInfraData.redirectors` -> `projectData.redirectors`
- `cachedInfraData.attack_box` -> `projectData.attack_box`
- `cachedInfraData.deployment_type` -> `projectData.deployment_type`
- `cachedInfraData.goad` -> `projectData.goad` (if present)

Also replace `cachedConfigData` references with `projectData.config`.

- [ ] **Step 2: Update the connection section template**

At lines 14152-14162, the C2 path currently renders inline from global cache. Change to always lazy-load for both C2 and GOAD:

```javascript
const connectionSection = isSuccess ? `
    <details class="details-card" data-details-id="${sessionId}-connection"
             ontoggle="if(this.open){loadConnectionInfo('${projectName}','${sessionId}')}">
        <summary>Connection Info</summary>
        <div id="${sessionId}-connection-content">
            Loading connection details...
        </div>
    </details>
` : '';
```

Remove the `c2ConnectionHtml` variable and the `renderC2ConnectionInfo()` inline call at line 14151. The C2 connection info will now be rendered by `loadConnectionInfo` which already handles both C2 and GOAD deployments.

- [ ] **Step 3: Update `loadConnectionInfo` to use `loadProjectData` and render C2 checklist-style info**

In `loadConnectionInfo` (line 10674), add: after fetching outputs, also cache as project data:

```javascript
// Near the top of loadConnectionInfo, after the fetch succeeds (around line 10692):
// Cache this data for other consumers (checklist, etc.)
// Build the normalized projectData shape
const pd = {
    outputs: outputs,
    deployment_type: outputs.deployment_type || '',
    bastion: { public_ip: outputs.bastion_public_ip || '', private_ip: outputs.bastion_private_ip || '', enabled: !!outputs.bastion_public_ip },
    c2_servers: {
        servers: (outputs.c2_servers || []).reduce((acc, s, i) => { acc[`server-${i}`] = s; return acc; }, {}),
        private_ips: (outputs.c2_servers || []).map(s => s.private_ip),
        instance_ids: (outputs.c2_servers || []).map(s => s.instance_id),
    },
    redirectors: {
        public_ips: (outputs.redirectors || []).map(r => r.public_ip),
        private_ips: (outputs.redirectors || []).map(r => r.private_ip),
        instance_ids: (outputs.redirectors || []).map(r => r.instance_id),
    },
    attack_box: { enabled: !!outputs.attackbox_private_ip, private_ip: outputs.attackbox_private_ip || '', admin_password: outputs.attackbox_password || '' },
    config: {
        redirector_domain: outputs.redirector_domain || '', primary_domain_name: outputs.primary_domain_name || '',
        c2_subdomain: outputs.c2_subdomain || 'api', cs_teamserver_password: outputs.cs_teamserver_password || '',
        cobalt_strike_license_secret_name: outputs.cobalt_strike_license_secret_name || '',
        deployment_type: outputs.deployment_type || '',
    },
    jumpbox_public_ip: outputs.jumpbox_public_ip || '',
    teamserver_private_ip: outputs.teamserver_private_ip || '',
};
setProjectData(projectName, pd);
```

This ensures that when Connection Info is expanded first, the data is cached for the checklist too.

- [ ] **Step 4: Commit**

```bash
git add webapp/frontend/js/app.js
git commit -m "refactor: convert C2 connection info to per-project lazy loading"
```

---

### Task 7: Update `loadCredentials` to pass project parameter

**Files:**
- Modify: `webapp/frontend/js/app.js:11431` (fetch call)

- [ ] **Step 1: Add project parameter to fetch**

At line 11431, change:

```javascript
const response = await fetch(`${API_BASE}/goad/credentials`);
```

To:

```javascript
const response = await fetch(`${API_BASE}/goad/credentials?project=${encodeURIComponent(projectName)}`);
```

- [ ] **Step 2: Commit**

```bash
git add webapp/frontend/js/app.js
git commit -m "feat: pass project name to /goad/credentials endpoint"
```

---

### Task 8: Clean up dead global cache references

Remove any remaining reads of `cachedInfraData` and `cachedConfigData` that aren't already converted. The only remaining global should be `cachedSshKeyData`.

**Files:**
- Modify: `webapp/frontend/js/app.js` (search and replace remaining references)

- [ ] **Step 1: Search for remaining global cache reads**

```bash
grep -n 'cachedInfraData\|cachedConfigData' webapp/frontend/js/app.js
```

For each hit that isn't the declaration itself:
- If it's in `refreshDeployments`: already removed in Task 3
- If it's in `buildPostDeployChecklist`: already converted in Task 5
- If it's in `renderC2ConnectionInfo`: already converted in Task 6
- If it's elsewhere (e.g., dashboard page, GOAD panel): evaluate if it needs the per-project pattern or can be removed

Common locations to check:
- Dashboard overview stats (may read `cachedInfraData.summary`) — these can use the first project in `projectDataCache` or be removed
- GOAD panel rendering in `refreshDeployments` — uses `goadData` from `/goad/status`, not `cachedInfraData`

- [ ] **Step 2: Remove old localStorage keys**

In `refreshDeployments`, remove:
```javascript
localStorage.setItem('red_team_cached_infra', ...);
localStorage.setItem('red_team_cached_config', ...);
```

These were replaced by `red_team_project_cache` in Task 3.

- [ ] **Step 3: Remove the `/deploy/infrastructure` fetch from `refreshDeployments`**

This was already done in Task 3, but verify it's fully removed — no fetch to `/deploy/infrastructure` in `refreshDeployments` anymore.

- [ ] **Step 4: Verify no runtime errors**

Open the web app, navigate to Deployment Manager, expand both deployment cards, open Connection Info, Credentials, and Checklist for each. Check browser console for errors.

- [ ] **Step 5: Commit**

```bash
git add webapp/frontend/js/app.js
git commit -m "chore: remove dead global cache references"
```

---

### Task 9: End-to-end verification

**Files:** None (testing only)

- [ ] **Step 1: Restart backend**

```bash
lsof -ti :5000 | xargs kill; sleep 1; python3 webapp/backend/app.py &
```

- [ ] **Step 2: Hard refresh browser (Cmd+Shift+R)**

- [ ] **Step 3: Verify c2-adhoc deployment card**

1. Navigate to Deployment Manager
2. Expand `c2_adhoc_dev_harriss_macbook_pro_01` card
3. Click "Connection Info" — should show bastion IP, C2 server, redirectors
4. Click "Post-Deployment Checklist" — should show all steps with real IPs from this project
5. Verify no GOAD data leaks into this card

- [ ] **Step 4: Verify goad-mini deployment card**

1. Expand `goad_mini_dev_harriss_macbook_pro` card
2. Click "Connection Info" — should show jumpbox IP, team server, attack box, DC01
3. Click "GOAD Credentials" — should show GOAD-Mini credentials
4. Verify no C2 data leaks into this card

- [ ] **Step 5: Verify caching works**

1. Collapse and re-expand Connection Info — should load instantly (no spinner)
2. Collapse and re-expand Post-Deploy Checklist — should load instantly
3. Navigate away and back to Deployment Manager — cached data persists

- [ ] **Step 6: Commit all remaining changes**

```bash
git add -A
git commit -m "feat: per-project deployment data - multi-deployment support"
```
