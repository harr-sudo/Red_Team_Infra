#!/usr/bin/env python3
"""
Generate elastic-rules.js from Elastic detection-rules TOML files.

Reads:  Research/elastic-detection-rules/rules/windows/*.toml
Writes: webapp/frontend/js/elastic-rules.js

Usage:
    # First time: clone the repo
    git clone --depth 1 https://github.com/elastic/detection-rules.git Research/elastic-detection-rules

    # Update rules
    git -C Research/elastic-detection-rules pull
    python3 scripts/utilities/update-elastic-rules.py

Requires Python 3.11+ (tomllib) or: pip install tomli
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("Error: Need Python 3.11+ (tomllib) or 'pip install tomli'")
        sys.exit(1)

# ─── Configuration ───────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RULES_DIR = PROJECT_ROOT / "Research" / "elastic-detection-rules" / "rules" / "windows"
OUTPUT_FILE = PROJECT_ROOT / "webapp" / "frontend" / "js" / "elastic-rules.js"

# CS command → MITRE technique IDs that trigger detection
COMMAND_TECHNIQUES = {
    'powershell':       ['T1059.001', 'T1059'],
    'powershell-import':['T1059.001'],
    'powerpick':        ['T1059.001', 'T1055', 'T1106'],
    'psinject':         ['T1055', 'T1055.001', 'T1059.001'],
    'execute-assembly': ['T1055', 'T1055.012', 'T1106'],
    'shell':            ['T1059.003'],
    'run':              ['T1059.003', 'T1059'],
    'logonpasswords':   ['T1003', 'T1003.001'],
    'hashdump':         ['T1003', 'T1003.002'],
    'dcsync':           ['T1003.006'],
    'mimikatz':         ['T1003', 'T1003.001'],
    'chromedump':       ['T1555', 'T1555.003'],
    'make_token':       ['T1134', 'T1134.003'],
    'steal_token':      ['T1134', 'T1134.001'],
    'pth':              ['T1550', 'T1550.002'],
    'keylogger':        ['T1056', 'T1056.001'],
    'inject':           ['T1055', 'T1055.001', 'T1055.002'],
    'shinject':         ['T1055', 'T1055.005'],
    'dllinject':        ['T1055', 'T1055.001'],
    'getsystem':        ['T1134', 'T1134.001'],
    'elevate':          ['T1068'],
    'jump':             ['T1021.002', 'T1543.003', 'T1569.002'],
    'remote-exec':      ['T1021.002', 'T1021.003', 'T1047', 'T1569.002'],
    'psexec':           ['T1021.002', 'T1569.002'],
    'wmi':              ['T1047'],
    'winrm':            ['T1021.006'],
    'scshell':          ['T1021.002', 'T1543.003'],
    'spawn':            ['T1055'],
    'spawnas':          ['T1134'],
    'screenshot':       ['T1113'],
    'timestomp':        ['T1070.006'],
    'portscan':         ['T1046'],
    'browserpivot':     ['T1185'],
}

# Tool name → MITRE technique IDs
TOOL_TECHNIQUES = {
    'rubeus':           ['T1558', 'T1558.003', 'T1550.003'],
    'mimikatz':         ['T1003', 'T1003.001', 'T1003.006'],
    'sharphound':       ['T1087', 'T1482', 'T1069'],
    'bloodhound':       ['T1087', 'T1482'],
    'certify':          ['T1649'],
    'seatbelt':         ['T1082', 'T1057'],
    'sharpdpapi':       ['T1555', 'T1555.003'],
    'sharpview':        ['T1087', 'T1069'],
    'sharpwmi':         ['T1047'],
    'powersploit':      ['T1059.001'],
    'sweetpotato':      ['T1134'],
    'nanodump':         ['T1003', 'T1003.001'],
    'chromekatz':       ['T1555', 'T1555.003'],
    'certutil':         ['T1140', 'T1105'],
    'scshell':          ['T1021.002'],
    'invoke-obfuscation': ['T1027', 'T1059.001'],
    'whisker':          ['T1556'],
    'forgecert':        ['T1649'],
    'standin':          ['T1136', 'T1087'],
    'sharpsystemtriggers': ['T1187'],
    'sharpup':          ['T1068'],
}

# Keyword → MITRE technique IDs
KEYWORD_TECHNIQUES = {
    'kerberoast':   ['T1558', 'T1558.003'],
    'asreproast':   ['T1558', 'T1558.004'],
    'dcsync':       ['T1003.006'],
    'sekurlsa':     ['T1003', 'T1003.001'],
    'wmi':          ['T1047'],
    'winrm':        ['T1021.006'],
    'psexec':       ['T1569.002', 'T1021.002'],
    'schtasks':     ['T1053.005'],
    'ntds':         ['T1003.003'],
    'sam':          ['T1003.002'],
    'dpapi':        ['T1555'],
    'shadow':       ['T1556'],
    'golden':       ['T1558.001'],
    'silver':       ['T1558.002'],
    's4u':          ['T1558.003'],
    'sc create':    ['T1543.003'],
    'sc config':    ['T1543.003'],
    'reg add':      ['T1547.001'],
    'net user':     ['T1136.001', 'T1087.001'],
}

MAX_RULES_PER_COMMAND = 8  # Cap to avoid overwhelming the UI


def parse_rule(filepath):
    """Parse a TOML rule file and extract metadata."""
    try:
        with open(filepath, 'rb') as f:
            data = tomllib.load(f)
    except Exception as e:
        return None

    rule = data.get('rule', {})
    if not rule.get('name'):
        return None

    # Extract MITRE technique IDs
    techniques = []
    tactics = []
    for threat in rule.get('threat', []):
        tactic = threat.get('tactic', {})
        if tactic.get('id'):
            tactics.append({'id': tactic['id'], 'name': tactic.get('name', '')})
        for tech in threat.get('technique', []):
            if tech.get('id'):
                techniques.append({'id': tech['id'], 'name': tech.get('name', '')})
            for sub in tech.get('subtechnique', []):
                if sub.get('id'):
                    techniques.append({'id': sub['id'], 'name': sub.get('name', '')})

    # Generate query summary from description (first sentence, capped at 100 chars)
    desc = rule.get('description', '').strip().replace('\n', ' ')
    summary = desc.split('.')[0].strip() if desc else ''
    if len(summary) > 100:
        summary = summary[:97] + '...'

    return {
        'filename': filepath.name,
        'name': rule['name'],
        'risk': rule.get('risk_score', 0),
        'severity': rule.get('severity', 'low'),
        'techniques': techniques,
        'tactics': tactics,
        'query_summary': summary,
    }


def match_techniques(rule_techniques, target_techniques):
    """Check if any rule technique matches any target technique."""
    rule_ids = {t['id'] for t in rule_techniques}
    for target in target_techniques:
        if target in rule_ids:
            return True
        # Also match parent technique (e.g., T1003 matches T1003.001)
        for rule_id in rule_ids:
            if rule_id.startswith(target + '.') or target.startswith(rule_id + '.'):
                return True
    return False


def format_rule(parsed):
    """Format a parsed rule into the JS data structure."""
    tech = parsed['techniques'][0] if parsed['techniques'] else {'id': '', 'name': ''}
    tactic = parsed['tactics'][0] if parsed['tactics'] else {'id': '', 'name': ''}
    return {
        'name': parsed['name'],
        'severity': parsed['severity'],
        'risk': parsed['risk'],
        'mitre_technique': tech['id'],
        'mitre_technique_name': tech['name'],
        'mitre_tactic': tactic['id'],
        'mitre_tactic_name': tactic['name'],
        'query_summary': parsed['query_summary'],
        'filename': parsed['filename'],
    }


def main():
    if not RULES_DIR.exists():
        print(f"Error: Rules directory not found: {RULES_DIR}")
        print("Run: git clone --depth 1 https://github.com/elastic/detection-rules.git Research/elastic-detection-rules")
        sys.exit(1)

    # Parse all Windows rules
    print(f"Parsing rules from {RULES_DIR}...")
    all_rules = []
    for toml_file in sorted(RULES_DIR.glob('*.toml')):
        parsed = parse_rule(toml_file)
        if parsed:
            all_rules.append(parsed)
    print(f"  Parsed {len(all_rules)} rules")

    # Build command mappings
    commands = {}
    for cmd, techniques in COMMAND_TECHNIQUES.items():
        matched = [format_rule(r) for r in all_rules if match_techniques(r['techniques'], techniques)]
        matched.sort(key=lambda r: r['risk'], reverse=True)
        if matched:
            commands[cmd] = matched[:MAX_RULES_PER_COMMAND]

    # Build tool mappings
    tools = {}
    for tool, techniques in TOOL_TECHNIQUES.items():
        matched = [format_rule(r) for r in all_rules if match_techniques(r['techniques'], techniques)]
        matched.sort(key=lambda r: r['risk'], reverse=True)
        if matched:
            tools[tool] = matched[:MAX_RULES_PER_COMMAND]

    # Build keyword mappings
    keywords = {}
    for kw, techniques in KEYWORD_TECHNIQUES.items():
        matched = [format_rule(r) for r in all_rules if match_techniques(r['techniques'], techniques)]
        matched.sort(key=lambda r: r['risk'], reverse=True)
        if matched:
            keywords[kw] = matched[:MAX_RULES_PER_COMMAND]

    # Count total unique rules
    all_filenames = set()
    for rules in list(commands.values()) + list(tools.values()) + list(keywords.values()):
        for r in rules:
            all_filenames.add(r['filename'])

    # Generate JS
    data = {
        'commands': commands,
        'tools': tools,
        'keywords': keywords,
        'meta': {
            'last_updated': date.today().isoformat(),
            'elastic_repo_url': 'https://github.com/elastic/detection-rules',
            'total_rules_mapped': len(all_filenames),
            'base_url': 'https://github.com/elastic/detection-rules/blob/main/rules/windows/',
        }
    }

    js_content = f"""/**
 * Elastic Detection Rules — OPSEC Intelligence Data
 * Auto-generated by scripts/utilities/update-elastic-rules.py
 * Source: https://github.com/elastic/detection-rules
 * Last updated: {date.today().isoformat()}
 * Total rules mapped: {len(all_filenames)}
 *
 * DO NOT EDIT MANUALLY — regenerate with:
 *   git -C Research/elastic-detection-rules pull
 *   python3 scripts/utilities/update-elastic-rules.py
 */

const ELASTIC_RULES = {json.dumps(data, indent=2)};
"""

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(js_content)

    # Summary
    print(f"\n{'='*60}")
    print(f"  Generated: {OUTPUT_FILE}")
    print(f"  Commands mapped: {len(commands)}")
    print(f"  Tools mapped: {len(tools)}")
    print(f"  Keywords mapped: {len(keywords)}")
    print(f"  Total unique rules: {len(all_filenames)}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
