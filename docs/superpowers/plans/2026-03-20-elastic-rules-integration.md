# Elastic Detection Rules OPSEC Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate Elastic SIEM detection rules into the beacon console OPSEC helper so operators see exactly which Elastic rules their commands + tools trigger, with contextual matching on arguments.

**Architecture:** Standalone `elastic-rules.js` data file (pure data, no logic) loaded before `app.js`. Two-tier matching: base CS command → Elastic rules, plus tool/keyword argument scanning for contextual rules. `_buildOpsecDetailHtml` enhanced to render an "ELASTIC DETECTIONS" section with severity-colored rule cards. Offline Python script parses TOML rules from cloned repo to regenerate the data file monthly.

**Tech Stack:** Vanilla JS (data file + rendering), CSS (rule cards), Python 3 (TOML parser for update script)

**Spec:** `docs/superpowers/specs/2026-03-20-elastic-rules-opsec-integration-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `webapp/frontend/js/elastic-rules.js` | CREATE | Pure data — ELASTIC_RULES map (commands, tools, keywords, meta) |
| `webapp/frontend/css/style.css` | MODIFY | Add Elastic rule card CSS classes after existing OPSEC section |
| `webapp/frontend/index.html` | MODIFY | Add `<script>` tag for elastic-rules.js before app.js |
| `webapp/frontend/js/app.js` | MODIFY | Add `_matchElasticRules()` and enhance `_buildOpsecDetailHtml()` |
| `scripts/utilities/update-elastic-rules.py` | CREATE | TOML parser that generates elastic-rules.js from cloned repo |

---

### Task 1: Create elastic-rules.js data file

**Files:**
- Create: `webapp/frontend/js/elastic-rules.js`

This is the heaviest task — contains all curated Elastic rule mappings for ~28 CS commands, ~30 tools, and ~15 keywords. Data sourced from Research/elastic-detection-rules/ TOML files.

- [ ] **Step 1: Create elastic-rules.js with the ELASTIC_RULES constant**

The file exports a single `const ELASTIC_RULES` with three maps (`commands`, `tools`, `keywords`) plus `meta`. Each rule object has: `name`, `severity`, `risk`, `mitre_technique`, `mitre_technique_name`, `mitre_tactic`, `mitre_tactic_name`, `query_summary`, `filename`.

Structure:
```js
const ELASTIC_RULES = {
    commands: { /* CS command → [rules] */ },
    tools: { /* tool name → [rules] */ },
    keywords: { /* keyword → [rules] */ },
    meta: { last_updated, total_rules_mapped, base_url }
};
```

Commands to map (Tier 1): powershell, powershell-import, powerpick, psinject, execute-assembly, shell, run, execute, logonpasswords, hashdump, dcsync, mimikatz, chromedump, make_token, steal_token, kerberos_ticket_use, pth, keylogger, inject, shinject, dllinject, getsystem, elevate, jump, remote-exec, psexec, wmi, winrm, scshell, spawn, spawnas, screenshot, timestomp, portscan, browserpivot, socks, rportfwd

Tools to map (Tier 2 — from attack box inventory):
- AD: rubeus, sharphound, bloodhound, certify, forgecert, whisker, standin, adsearch, sharpADWS, powerupsql, sqlrecon
- PostEx: mimikatz, seatbelt, sharpdpapi, sharpup, sharpview, sharpwmi, powersploit, sweetpotato, sharpsystemtriggers, scshell
- BOFs: nanodump, chromekatz, chisel, inject-assembly, persistbof, dump-hives
- Evasion: invoke-obfuscation, certutil, ysoserial

Keywords to map (Tier 2b):
kerberoast, asreproast, dcsync, sekurlsa, golden, silver, s4u, dpapi, shadow, schtasks, sc create, sc config, reg add, net user, wmic, winrm, psexec, certutil, ntds, sam

- [ ] **Step 2: Verify the file loads without errors**

Open browser console, confirm `typeof ELASTIC_RULES` returns `'object'` and `Object.keys(ELASTIC_RULES.commands).length` returns expected count.

- [ ] **Step 3: Commit**

```bash
git add webapp/frontend/js/elastic-rules.js
git commit -m "feat: add Elastic detection rules data file (OPSEC integration)"
```

---

### Task 2: Add script tag to index.html

**Files:**
- Modify: `webapp/frontend/index.html:2059` (before app.js script tag)

- [ ] **Step 1: Add elastic-rules.js script tag before app.js**

Insert before the existing `<script src="js/app.js"></script>` line:
```html
<script src="js/elastic-rules.js"></script>
```

- [ ] **Step 2: Verify load order**

Open browser dev tools Network tab, confirm elastic-rules.js loads before app.js.

- [ ] **Step 3: Commit**

```bash
git add webapp/frontend/index.html
git commit -m "feat: load elastic-rules.js before app.js"
```

---

### Task 3: Add Elastic rule card CSS

**Files:**
- Modify: `webapp/frontend/css/style.css` (after existing OPSEC detail panel section, before `/* --- Beacon Console */`)

- [ ] **Step 1: Add CSS classes for Elastic detection cards**

All colors must use theme-switching variables (`--text-primary`, `--text-secondary`, `--text-muted`, `--danger-text`, `--warning-text`, `--info-text`, `--success-text`) — the detail panel sits on `--bg-card`, NOT `--bg-terminal`.

```css
/* --- Elastic Detection Rule Cards ---
   Rendered inside .opsec-live-detail panel (on --bg-card, NOT --bg-terminal).
   Use theme-switching variables only. */
.opsec-elastic-section {
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid var(--border);
}
.opsec-elastic-section .opsec-detail-heading {
    margin-bottom: 6px;
}
.opsec-elastic-card {
    padding: 6px 8px 6px 12px;
    margin-bottom: 4px;
    border-radius: 3px;
    border-left: 3px solid var(--text-muted);
    background: rgba(0, 0, 0, 0.04);
}
.opsec-elastic-card--critical {
    border-left-color: var(--danger-text);
}
.opsec-elastic-card--high {
    border-left-color: var(--warning-text);
}
.opsec-elastic-card--medium {
    border-left-color: var(--info-text);
}
.opsec-elastic-card--low {
    border-left-color: var(--text-muted);
}
.opsec-elastic-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
}
.opsec-elastic-severity {
    font-weight: 700;
    font-size: 0.85em;
    text-transform: uppercase;
}
.opsec-elastic-card--critical .opsec-elastic-severity { color: var(--danger-text); }
.opsec-elastic-card--high .opsec-elastic-severity { color: var(--warning-text); }
.opsec-elastic-card--medium .opsec-elastic-severity { color: var(--info-text); }
.opsec-elastic-card--low .opsec-elastic-severity { color: var(--text-muted); }
.opsec-elastic-name {
    font-weight: 600;
    color: var(--text-primary);
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.opsec-elastic-link {
    color: var(--info-text);
    text-decoration: none;
    font-size: 0.9em;
    flex-shrink: 0;
}
.opsec-elastic-link:hover {
    text-decoration: underline;
}
.opsec-elastic-mitre {
    color: var(--text-muted);
    font-size: 0.88em;
    margin-top: 1px;
}
.opsec-elastic-query {
    color: var(--text-secondary);
    font-size: 0.88em;
    margin-top: 1px;
}
.opsec-elastic-expand {
    background: none;
    border: none;
    color: var(--info-text);
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: inherit;
    padding: 4px 0;
}
.opsec-elastic-expand:hover {
    text-decoration: underline;
}
.opsec-elastic-nocover {
    padding: 6px 8px;
    border-left: 3px solid var(--warning-text);
    background: rgba(0, 0, 0, 0.04);
    color: var(--text-secondary);
    border-radius: 3px;
}
```

- [ ] **Step 2: Invoke ui-quality-check skill to verify theme safety**

- [ ] **Step 3: Commit**

```bash
git add webapp/frontend/css/style.css
git commit -m "feat: add Elastic detection rule card CSS classes"
```

---

### Task 4: Add _matchElasticRules() and enhance _buildOpsecDetailHtml()

**Files:**
- Modify: `webapp/frontend/js/app.js` — add `_matchElasticRules(inputValue)` method and modify `_buildOpsecDetailHtml(entry)` to append Elastic section

- [ ] **Step 1: Add _matchElasticRules method to BEACON object**

Insert after `_useAlternative()` method. This performs the two-tier matching:

```js
_matchElasticRules(inputValue) {
    if (typeof ELASTIC_RULES === 'undefined') return [];
    const parts = inputValue.trim().split(/\s+/);
    const base = parts[0]?.toLowerCase();
    const args = parts.slice(1).join(' ').toLowerCase();
    const seen = new Set();
    const results = [];

    const addRules = (rules) => {
        if (!rules) return;
        rules.forEach(r => {
            if (!seen.has(r.filename)) {
                seen.add(r.filename);
                results.push(r);
            }
        });
    };

    // Tier 1: Base command match
    addRules(ELASTIC_RULES.commands?.[base]);

    // Tier 2: Tool name match (scan args for known tool names)
    if (args && ELASTIC_RULES.tools) {
        for (const [tool, rules] of Object.entries(ELASTIC_RULES.tools)) {
            if (args.includes(tool)) addRules(rules);
        }
    }

    // Tier 2b: Keyword match (scan args for known keywords)
    if (args && ELASTIC_RULES.keywords) {
        for (const [kw, rules] of Object.entries(ELASTIC_RULES.keywords)) {
            if (args.includes(kw)) addRules(rules);
        }
    }

    // Sort by risk score descending (critical first)
    results.sort((a, b) => (b.risk || 0) - (a.risk || 0));
    return results;
},
```

- [ ] **Step 2: Add _buildElasticHtml helper method**

Insert after `_matchElasticRules`. Renders the rule cards with a 5-rule cap and expand toggle:

```js
_buildElasticHtml(rules) {
    if (!rules.length) return '';
    const baseUrl = (typeof ELASTIC_RULES !== 'undefined' && ELASTIC_RULES.meta?.base_url) || 'https://github.com/elastic/detection-rules/blob/main/rules/windows/';
    const MAX_SHOW = 5;
    const buildCard = (r) => {
        const sev = r.severity || 'low';
        const url = baseUrl + this.escapeAttr(r.filename);
        return `<div class="opsec-elastic-card opsec-elastic-card--${sev}">`
            + `<div class="opsec-elastic-header">`
            + `<span class="opsec-elastic-severity">${this.escapeHtml(sev)} (${r.risk || '?'})</span>`
            + `<span class="opsec-elastic-name" title="${this.escapeAttr(r.name)}">${this.escapeHtml(r.name)}</span>`
            + `<a class="opsec-elastic-link" href="${url}" target="_blank" rel="noopener" onclick="event.stopPropagation()">↗</a>`
            + `</div>`
            + `<div class="opsec-elastic-mitre">${this.escapeHtml(r.mitre_technique || '')} ${this.escapeHtml(r.mitre_technique_name || '')} · ${this.escapeHtml(r.mitre_tactic_name || '')}</div>`
            + `<div class="opsec-elastic-query">${this.escapeHtml(r.query_summary || '')}</div>`
            + `</div>`;
    };

    let html = '<div class="opsec-elastic-section">';
    html += `<span class="opsec-detail-heading">Elastic Detections (${rules.length})</span>`;
    const visible = rules.slice(0, MAX_SHOW);
    const hidden = rules.slice(MAX_SHOW);
    visible.forEach(r => { html += buildCard(r); });
    if (hidden.length) {
        const hiddenId = 'elastic-hidden-' + Date.now();
        html += `<div id="${hiddenId}" style="display:none;">`;
        hidden.forEach(r => { html += buildCard(r); });
        html += '</div>';
        html += `<button class="opsec-elastic-expand" onclick="event.stopPropagation(); var el=document.getElementById('${hiddenId}'); el.style.display=el.style.display==='none'?'block':'none'; this.textContent=el.style.display==='none'?'Show all ${rules.length} rules ▼':'Show less ▲'">Show all ${rules.length} rules ▼</button>`;
    }
    html += '</div>';
    return html;
},
```

- [ ] **Step 3: Modify _buildOpsecDetailHtml to include Elastic section**

In `_buildOpsecDetailHtml(entry)`, after the Event IDs section (before `return html;`), add:

```js
// Elastic detection rules (contextual matching on full input)
const inputEl = document.getElementById('beacon-command-input');
const inputVal = inputEl?.value || entry.cmd || '';
const elasticRules = this._matchElasticRules(inputVal);
if (elasticRules.length) {
    html += this._buildElasticHtml(elasticRules);
} else if (entry.opsec === 'loud' || entry.opsec === 'moderate') {
    // No Elastic coverage warning
    html += '<div class="opsec-elastic-section">';
    html += '<span class="opsec-detail-heading">Elastic Detections</span>';
    html += '<div class="opsec-elastic-nocover">No Elastic SIEM rules mapped — network-layer or behavioral detection may still apply</div>';
    html += '</div>';
}
```

- [ ] **Step 4: Verify rendering**

Start webapp, navigate to beacon tab, type `powershell` → verify Elastic section appears with rule cards. Type `execute-assembly Rubeus.exe kerberoast` → verify CLR + kerberoasting rules shown. Type `ls` → verify no Elastic section.

- [ ] **Step 5: Commit**

```bash
git add webapp/frontend/js/app.js
git commit -m "feat: add Elastic detection rules rendering to OPSEC detail panel"
```

---

### Task 5: Create update-elastic-rules.py

**Files:**
- Create: `scripts/utilities/update-elastic-rules.py`

- [ ] **Step 1: Create the Python script**

The script:
1. Reads all `rules/windows/*.toml` from the cloned Elastic repo
2. Parses TOML metadata (name, risk_score, severity, MITRE technique/tactic)
3. Maps rules to CS commands via COMMAND_TECHNIQUES table
4. Maps rules to tools via TOOL_TECHNIQUES table
5. Maps rules to keywords via KEYWORD_TECHNIQUES table
6. Generates `webapp/frontend/js/elastic-rules.js`
7. Prints summary

Requires: `pip install toml` (or uses Python 3.11+ `tomllib`)

```python
#!/usr/bin/env python3
"""Generate elastic-rules.js from Elastic detection-rules TOML files.

Usage:
    python3 scripts/utilities/update-elastic-rules.py

Reads: Research/elastic-detection-rules/rules/windows/*.toml
Writes: webapp/frontend/js/elastic-rules.js
"""
import json, os, sys
from pathlib import Path
from datetime import date

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # pip install tomli
    except ImportError:
        print("Error: Need Python 3.11+ or 'pip install tomli'")
        sys.exit(1)

# ... (COMMAND_TECHNIQUES, TOOL_TECHNIQUES, KEYWORD_TECHNIQUES mapping tables)
# ... (parse logic, JS generation)
```

The mapping tables are maintained manually and documented in the script. Monthly process: `git pull` the Elastic repo, run the script, commit the updated JS file.

- [ ] **Step 2: Run the script and verify output**

```bash
python3 scripts/utilities/update-elastic-rules.py
# Verify: webapp/frontend/js/elastic-rules.js updated
# Verify: console output shows rule counts
```

- [ ] **Step 3: Commit**

```bash
git add scripts/utilities/update-elastic-rules.py
git commit -m "feat: add Elastic rules TOML parser and JS generator"
```

---

### Task 6: Staleness indicator in OPSEC bar

**Files:**
- Modify: `webapp/frontend/js/app.js` — enhance `_updateOpsecBar` to show staleness warning
- Modify: `webapp/frontend/css/style.css` — add staleness badge class

- [ ] **Step 1: Add staleness check to _updateOpsecBar**

After building the compact bar HTML, check `ELASTIC_RULES.meta.last_updated` against current date. If > 14 days, show amber badge. If > 30 days, show red badge.

```js
// Staleness indicator
if (typeof ELASTIC_RULES !== 'undefined' && ELASTIC_RULES.meta?.last_updated && hasDetail) {
    const updated = new Date(ELASTIC_RULES.meta.last_updated);
    const days = Math.floor((Date.now() - updated) / 86400000);
    if (days > 30) {
        compactHtml += '<span class="opsec-stale opsec-stale--red" title="Elastic rules ' + days + ' days old">Rules: ' + days + 'd old</span>';
    } else if (days > 14) {
        compactHtml += '<span class="opsec-stale opsec-stale--amber" title="Elastic rules ' + days + ' days old">Rules: ' + days + 'd old</span>';
    }
}
```

- [ ] **Step 2: Add CSS for staleness badges**

```css
.opsec-stale {
    font-size: 0.85em;
    padding: 1px 6px;
    border-radius: 3px;
    margin-left: 8px;
}
.opsec-stale--amber {
    color: var(--warning-text);
    border: 1px solid var(--warning-border);
}
.opsec-stale--red {
    color: var(--danger-text);
    border: 1px solid var(--danger-border);
}
```

- [ ] **Step 3: Commit**

```bash
git add webapp/frontend/js/app.js webapp/frontend/css/style.css
git commit -m "feat: add Elastic rules staleness indicator"
```

---

### Task 7: Final integration test and UI quality check

- [ ] **Step 1: Run through all verification scenarios**

1. Type `getsystem` → OPSEC detail shows "ELASTIC DETECTIONS" with named pipe rules
2. Type `execute-assembly Rubeus.exe kerberoast` → CLR rules (base) + kerberoasting rules (tool+keyword)
3. Type `shell certutil -urlcache` → cmd.exe rules (base) + certutil rules (tool)
4. Type `logonpasswords` → LSASS rules including critical risk 99
5. Type `ls` → No Elastic section (safe command)
6. Type `socks` → "No Elastic SIEM rules mapped" warning
7. Click [↗] link → Opens GitHub TOML file in new tab
8. Toggle dark/light mode → All rule cards readable
9. Check staleness indicator appears if rules are old

- [ ] **Step 2: Invoke ui-quality-check skill**

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete Elastic detection rules OPSEC integration"
```
