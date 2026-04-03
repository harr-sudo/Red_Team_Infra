# Elastic Detection Rules OPSEC Integration — Design Spec

## Context

Red team operators using the beacon console need to know **exactly which Elastic SIEM rules** their commands will trigger. Elastic's `detection-rules` repo (469 Windows rules, constantly updated) provides structured TOML rules with MITRE ATT&CK mappings, risk scores, severity levels, and EQL/KQL queries. This feature integrates that intelligence into the OPSEC detail panel so operators can make informed decisions during live engagements.

**Key insight**: Detection risk depends not just on the base CS command but on **command + tool + arguments**. `execute-assembly Rubeus.exe kerberoast` triggers both CLR loading rules AND kerberoasting rules. The data model must support this contextual matching.

## Architecture

```
Research/elastic-detection-rules/          ← shallow-cloned repo (git pull monthly)
        ↓
scripts/utilities/update-elastic-rules.py  ← parses TOML rules → generates JS data file
        ↓
webapp/frontend/js/elastic-rules.js        ← modular data file (ELASTIC_RULES map)
        ↓
webapp/frontend/js/app.js                  ← _buildOpsecDetailHtml reads ELASTIC_RULES
        ↓
OPSEC detail panel                         ← "ELASTIC DETECTIONS" section with rule cards
```

### Separation of concerns

- **`elastic-rules.js`**: Pure data — no logic, no DOM, no dependencies. Easy to regenerate.
- **`app.js`**: Rendering logic — reads ELASTIC_RULES, matches by command + context, renders cards.
- **`update-elastic-rules.py`**: Offline script — parses TOML, generates JS. Never runs in production.

## Data Model

### `elastic-rules.js` — Two-tier matching

```js
// Loaded as separate <script> before app.js
const ELASTIC_RULES = {
    // ── Tier 1: Base command mapping ──
    // Matches when the operator types the base command
    commands: {
        'getsystem': [
            {
                name: 'Privilege Escalation via Named Pipe Impersonation',
                severity: 'high',
                risk: 73,
                mitre_technique: 'T1134',
                mitre_technique_name: 'Access Token Manipulation',
                mitre_tactic: 'TA0004',
                mitre_tactic_name: 'Privilege Escalation',
                query_summary: 'Detects cmd.exe/powershell.exe writing to \\\\.\\pipe\\*',
                filename: 'privilege_escalation_named_pipe_impersonation.toml'
            },
            {
                name: 'Potential Privilege Escalation via Rogue Named Pipe',
                severity: 'high',
                risk: 73,
                mitre_technique: 'T1134',
                mitre_technique_name: 'Access Token Manipulation',
                mitre_tactic: 'TA0004',
                mitre_tactic_name: 'Privilege Escalation',
                query_summary: 'Detects unusual named pipe creation by non-system processes',
                filename: 'privilege_escalation_via_rogue_named_pipe.toml'
            }
        ],
        'logonpasswords': [ /* 8 rules, includes risk 99 critical */ ],
        'dcsync': [ /* 3 rules */ ],
        'powershell': [ /* top 5-8 most relevant of 74 */ ],
        // ... etc for all enriched commands
    },

    // ── Tier 2: Tool/argument context mapping ──
    // Matched when the command arguments contain a known tool name or keyword
    tools: {
        'rubeus': [
            {
                name: 'Kerberos Traffic from Unusual Process',
                severity: 'medium',
                risk: 47,
                mitre_technique: 'T1558',
                mitre_technique_name: 'Steal or Forge Kerberos Tickets',
                mitre_tactic: 'TA0006',
                mitre_tactic_name: 'Credential Access',
                query_summary: 'Detects Kerberos TGS requests from processes other than lsass.exe',
                filename: 'credential_access_kerberoasting_unusual_process.toml'
            },
            // + kerberos preauth disable, kerberos ticket dump rules
        ],
        'sharphound': [
            // AD enumeration rules (T1087, T1482)
        ],
        'certutil': [
            {
                name: 'Suspicious CertUtil Commands',
                severity: 'medium',
                risk: 47,
                mitre_technique: 'T1140',
                mitre_technique_name: 'Deobfuscate/Decode Files or Information',
                mitre_tactic: 'TA0005',
                mitre_tactic_name: 'Defense Evasion',
                query_summary: 'Detects certutil with -urlcache, -decode, -encode, -addstore flags',
                filename: 'defense_evasion_suspicious_certutil_commands.toml'
            }
        ],
        'mimikatz': [ /* 2+ rules including risk 99 critical */ ],
        'seatbelt': [ /* system enumeration rules */ ],
        'sharpview': [ /* AD enumeration rules */ ],
        'powerview': [ /* PowerShell AD enumeration rules */ ],
        'bloodhound': [ /* AD collection rules */ ],
        // Common tool names that appear in execute-assembly / shell / run arguments
    },

    // ── Tier 2b: Argument keyword context ──
    // Matched when specific keywords appear in arguments
    keywords: {
        'kerberoast': [ /* T1558.003 rules */ ],
        'asreproast': [ /* T1558.004 rules */ ],
        'dcsync': [ /* T1003.006 rules — catches 'mimikatz lsadump::dcsync' */ ],
        'sekurlsa': [ /* T1003.001 rules */ ],
        'wmi': [ /* T1047 WMI execution rules */ ],
        'winrm': [ /* WinRM lateral movement rules */ ],
        'psexec': [ /* T1021.002 service creation rules */ ],
    },

    // ── Metadata ──
    meta: {
        last_updated: '2026-03-20',
        elastic_repo_commit: 'abc1234',
        total_rules_mapped: 142,
        base_url: 'https://github.com/elastic/detection-rules/blob/main/rules/windows/'
    }
};
```

### Matching logic in app.js

When the operator types a command, the OPSEC system:

1. **Base match**: Look up `ELASTIC_RULES.commands[baseCommand]` → always shown
2. **Tool match**: Scan command arguments against `ELASTIC_RULES.tools` keys → append matching rules
3. **Keyword match**: Scan command arguments against `ELASTIC_RULES.keywords` keys → append matching rules
4. **Deduplicate**: Remove duplicate rules (same filename) from combined results
5. **Sort**: By risk score descending (critical first)

Example: Operator types `execute-assembly Rubeus.exe kerberoast`
- Base match: `commands['execute-assembly']` → CLR loading rules (risk 73)
- Tool match: `tools['rubeus']` → Kerberos traffic rules (risk 47)
- Keyword match: `keywords['kerberoast']` → Kerberoasting-specific rules
- Combined: 4-6 rules shown, sorted by risk score

Example: Operator types `shell certutil -urlcache -f http://...`
- Base match: `commands['shell']` → cmd.exe execution rules
- Tool match: `tools['certutil']` → Suspicious CertUtil Commands (risk 47)
- Combined: 3-4 rules shown

Example: Operator types `remote-exec wmi TARGET cmd.exe`
- Base match: `commands['remote-exec']` → service/WMI/WinRM rules
- Keyword match: `keywords['wmi']` → WMI-specific rules (T1047)
- Combined: 4-5 rules shown

## UI: ELASTIC DETECTIONS Section

Rendered inside the existing OPSEC detail panel, after MITIGATIONS and before EVENT IDS.

### Rule card layout

Each Elastic rule is rendered as a compact card:

```
┌─ HIGH (73) ──────────────────────────────────────────────────┐
│ Privilege Escalation via Named Pipe Impersonation        [↗] │
│ T1134 Access Token Manipulation · TA0004 Privilege Esc       │
│ Detects cmd.exe/powershell.exe writing to \\.\pipe\*         │
└──────────────────────────────────────────────────────────────┘
```

- **Severity badge**: Color-coded left border + label (critical=red, high=orange/danger, medium=yellow/warning, low=grey)
- **Rule name**: Bold, primary text color
- **[↗]**: External link to the TOML file on GitHub (opens in new tab)
- **MITRE line**: Technique ID + name · Tactic name — muted text
- **Query summary**: One-line description — secondary text

### CSS classes (new)

```css
.opsec-elastic-section { }                    /* Section wrapper */
.opsec-elastic-card { }                       /* Individual rule card */
.opsec-elastic-card--critical { }             /* Red left border */
.opsec-elastic-card--high { }                 /* Orange left border */
.opsec-elastic-card--medium { }               /* Yellow left border */
.opsec-elastic-card--low { }                  /* Grey left border */
.opsec-elastic-severity { }                   /* Severity + risk badge */
.opsec-elastic-name { }                       /* Rule name */
.opsec-elastic-link { }                       /* External [↗] link */
.opsec-elastic-mitre { }                      /* MITRE technique line */
.opsec-elastic-query { }                      /* Query summary line */
```

All colors use theme-switching variables (the detail panel sits on `--bg-card`, NOT `--bg-terminal`).

### Max rules shown

Show up to **5 rules** per command (highest risk first). If more exist, show a "Show all N rules ▼" toggle to expand.

## Update Script: `scripts/utilities/update-elastic-rules.py`

Python script (not bash — TOML parsing is cleaner in Python) that:

1. Reads all `rules/windows/*.toml` files from `Research/elastic-detection-rules/`
2. Extracts: name, risk_score, severity, MITRE technique/tactic, query type, and generates a 1-line query summary from the description
3. Maps rules to CS commands using a maintained mapping table (CS command → MITRE technique IDs)
4. Maps rules to tools/keywords using a maintained keyword list
5. Generates `webapp/frontend/js/elastic-rules.js`
6. Prints summary: rules mapped, new rules since last update, unmapped rules

### Mapping table (maintained in the script)

```python
# CS command → MITRE technique IDs that trigger detection
COMMAND_TECHNIQUES = {
    'powershell': ['T1059.001'],
    'shell': ['T1059.003'],
    'execute-assembly': ['T1055', '1106'],
    'logonpasswords': ['T1003.001'],
    'hashdump': ['T1003.002'],
    'dcsync': ['T1003.006'],
    'inject': ['T1055.001', 'T1055.002'],
    'getsystem': ['T1134', 'T1134.001'],
    'jump': ['T1021.002'],
    'remote-exec': ['T1021.002', 'T1021.003', 'T1047'],
    'pth': ['T1550.002'],
    'kerberos_ticket_use': ['T1550.003'],
    'keylogger': ['T1056.001'],
    'make_token': ['T1134.003'],
    'steal_token': ['T1134.001'],
    # ... etc
}

# Tool name → MITRE technique IDs
TOOL_TECHNIQUES = {
    'rubeus': ['T1558', 'T1558.003'],
    'mimikatz': ['T1003', 'T1003.001', 'T1003.006'],
    'certutil': ['T1140', 'T1105'],
    'sharphound': ['T1087', 'T1482'],
    'seatbelt': ['T1082', 'T1057'],
    # ... etc
}
```

### Monthly update process

```bash
cd /path/to/Red_Team_Infra_Local
git -C Research/elastic-detection-rules pull
python3 scripts/utilities/update-elastic-rules.py
# Output: "Updated elastic-rules.js: 142 rules mapped (3 new since last update)"
```

## Scope of initial implementation

### Commands to map (Tier 1 — base commands): 28

All enriched CS commands from the existing OPSEC data get Elastic rules:
powershell, powershell-import, powerpick, psinject, execute-assembly, shell, run, execute, logonpasswords, hashdump, dcsync, mimikatz, chromedump, make_token, steal_token, kerberos_ticket_use, pth, keylogger, inject, shinject, dllinject, getsystem, jump, remote-exec, psexec, wmi, winrm, portscan, browserpivot, spawn, spawnas, screenshot, timestomp

### Tools to map (Tier 2): 12

rubeus, mimikatz, sharphound/bloodhound, seatbelt, certutil, sharpview/powerview, certify, nanodump, covenant, chisel, psexec, wmic

### Keywords to map (Tier 2b): 10

kerberoast, asreproast, dcsync, sekurlsa, wmi, winrm, psexec, scshell, ntds, sam

## Files to create/modify

| File | Action |
|------|--------|
| `webapp/frontend/js/elastic-rules.js` | **CREATE** — Modular Elastic rules data |
| `webapp/frontend/index.html` | **MODIFY** — Add `<script src="js/elastic-rules.js">` before app.js |
| `webapp/frontend/js/app.js` | **MODIFY** — Enhance `_buildOpsecDetailHtml` + add `_matchElasticRules` |
| `webapp/frontend/css/style.css` | **MODIFY** — Add Elastic rule card CSS classes |
| `scripts/utilities/update-elastic-rules.py` | **CREATE** — TOML parser + JS generator |

## Verification

1. Type `getsystem` → OPSEC detail shows "ELASTIC DETECTIONS" section with named pipe impersonation rule card (high, 73)
2. Type `execute-assembly Rubeus.exe kerberoast` → Shows CLR rules (base) + kerberoasting rules (tool+keyword context)
3. Type `shell certutil -urlcache` → Shows cmd.exe rules (base) + certutil rules (tool context)
4. Type `logonpasswords` → Shows LSASS rules including critical risk 99
5. Type `ls` → No Elastic section (safe command, no rules)
6. Click [↗] link → Opens GitHub TOML file in new tab
7. Run `python3 scripts/utilities/update-elastic-rules.py` → Generates updated elastic-rules.js
8. Toggle dark/light mode → All rule cards readable in both themes
