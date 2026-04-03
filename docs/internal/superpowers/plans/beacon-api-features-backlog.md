# Beacon Web App — Unimplemented API Features Backlog

Features available via the CS REST API (219 endpoints) that are not yet exposed in the web app UI.
Backend service methods exist for most of these — the work is primarily frontend UI.

## Priority 1 — High Impact

### Payload Generation
- `POST /api/v1/payloads/generate/stageless` — Create stageless payload
- `POST /api/v1/payloads/generate/stager` — Create stager payload
- `GET /api/v1/payloads/{fileName}` — Download generated payload
- `GET /api/v1/artifacts` — List available artifacts
- **Value:** Operators can generate payloads directly from the web app without needing the CS client GUI

### Credential Store Viewer
- `GET /api/v1/data/credentials` — List all harvested credentials (cross-beacon)
- `POST /api/v1/data/credentials` — Add credential manually
- `GET /api/v1/data/credentials/{id}` — Get credential detail
- `DELETE /api/v1/data/credentials/{id}` — Delete credential
- **Value:** Single pane of glass for all creds harvested across all beacons (passwords, hashes, tickets)

### Screenshot & Keystroke Gallery
- `GET /api/v1/data/screenshots` — List all screenshots (cross-beacon)
- `GET /api/v1/data/screenshots/{id}` — Get screenshot image
- `DELETE /api/v1/data/screenshots/{id}` — Delete screenshot
- `GET /api/v1/data/keystrokes` — List all keystrokes (cross-beacon)
- `GET /api/v1/beacons/{bid}/keystrokes` — List keystrokes for specific beacon
- `DELETE /api/v1/data/keystrokes/{id}` — Delete keystrokes
- **Value:** Visual gallery of captured screenshots with timeline, keystroke viewer with search

### Lateral Movement
- `GET /api/v1/beacons/{bid}/remoteExec/beacon` — List jump methods (psexec, winrm, etc.)
- `POST /api/v1/beacons/{bid}/remoteExec/beacon` — Jump to another host
- `GET /api/v1/beacons/{bid}/remoteExec/command` — List remote-exec methods
- `POST /api/v1/beacons/{bid}/remoteExec/command` — Remote command execution
- **Value:** Move laterally from web app — critical for operations

### Execute-Assembly (.NET)
- `POST /api/v1/beacons/{bid}/spawn/dotnetAssembly` — Run .NET assembly in-memory
- **Value:** Run Rubeus, Seatbelt, SharpHound, etc. from the web app

## Priority 2 — Medium Impact

### Privilege Escalation
- `GET /api/v1/beacons/{bid}/elevate/beacon` — List privesc methods
- `POST /api/v1/beacons/{bid}/elevate/beacon` — Elevate beacon
- `GET /api/v1/beacons/{bid}/elevate/command` — List runasadmin methods
- `POST /api/v1/beacons/{bid}/elevate/command` — Run command elevated
- **Value:** One-click privesc from web app

### Kerberos Ticket Management
- `POST /api/v1/beacons/{bid}/execute/kerberos/ticket/use` — Load ticket (.kirbi)
- `POST /api/v1/beacons/{bid}/execute/kerberos/ticket/purge` — Purge tickets
- **Value:** Pass-the-ticket attacks from web app

### SSH Pivoting
- `POST /api/v1/beacons/{bid}/spawn/ssh` — SSH with password
- `POST /api/v1/beacons/{bid}/spawn/sshKey` — SSH with key
- `POST /api/v1/beacons/{bid}/inject/ssh` — SSH inject variant
- `POST /api/v1/beacons/{bid}/inject/sshKey` — SSH key inject variant
- **Value:** Pivot to Linux hosts from a Windows beacon

### PowerShell Variants
- `POST /api/v1/beacons/{bid}/execute/powershell/import` — Import .ps1 script
- `POST /api/v1/beacons/{bid}/spawn/powershell` — Managed PowerShell (spawn)
- `POST /api/v1/beacons/{bid}/spawn/powershell/unmanaged` — Unmanaged PowerShell / powerpick
- `POST /api/v1/beacons/{bid}/inject/powershell/unmanaged` — psinject
- **Value:** Full PowerShell execution options with OPSEC choices

### Browser Pivot
- `POST /api/v1/beacons/{bid}/inject/browserpivot` — Start browser pivot (not in spec but likely exists)
- `POST /api/v1/beacons/{bid}/execute/browserpivotStop` — Stop browser pivot
- **Value:** Man-in-the-browser attacks

## Priority 3 — Nice to Have

### Shellcode & DLL Injection
- `POST /api/v1/beacons/{bid}/spawn/shellcode` — Execute shellcode (spawn)
- `POST /api/v1/beacons/{bid}/inject/shellcode` — Execute shellcode (inject)
- `POST /api/v1/beacons/{bid}/inject/dll` — Reflective DLL loading
- `POST /api/v1/beacons/{bid}/inject/loadDll` — Load library from disk
- `POST /api/v1/beacons/{bid}/spawn/postExDll` — PostEx DLL (spawn)
- `POST /api/v1/beacons/{bid}/inject/postExDll` — PostEx DLL (inject)
- **Value:** Advanced injection for custom tooling

### Missing File Operations
- `POST /api/v1/beacons/{bid}/execute/cp` — Copy file
- `POST /api/v1/beacons/{bid}/execute/mv` — Move file
- `POST /api/v1/beacons/{bid}/execute/timestomp` — Timestomp (OPSEC)
- `POST /api/v1/beacons/{bid}/execute/pwd` — Print working directory
- **Value:** Complete file browser functionality

### Registry Browser
- `POST /api/v1/beacons/{bid}/execute/reg/query` — Query registry key
- `POST /api/v1/beacons/{bid}/execute/reg/queryv` — Query registry value
- **Value:** Registry enumeration for persistence discovery

### Clipboard
- `POST /api/v1/beacons/{bid}/execute/clipboard` — Get clipboard content
- **Value:** Grab passwords/data from clipboard

### Pass-the-Hash
- `POST /api/v1/beacons/{bid}/spawn/pth` — PTH (spawn)
- `POST /api/v1/beacons/{bid}/inject/pth` — PTH (inject)
- **Value:** Use NTLM hashes for lateral movement

### Team Server Info
- `GET /api/v1/system/killdate` — Get kill date
- `GET /api/v1/system/malleableProfile` — Get loaded profile
- `GET /api/v1/system/information` — Server diagnostics
- `GET /api/v1/system/teamserverIp` — Team server IP
- **Value:** Dashboard diagnostics panel

### Make Token (UPN variant)
- `POST /api/v1/beacons/{bid}/execute/makeToken/upn` — Make token with UPN format
- **Value:** Alternative token creation for cross-domain scenarios

## Already Implemented in Web App

For reference, these are already working:
- Beacon list, detail, delete, interact
- Sleep/jitter configuration
- File browser (ls, cd, drives, mkdir, rm, download, upload)
- Process list with tree view, kill process
- Token management (make, steal, rev2self, token store)
- Screenshots, screenwatch
- Credential harvesting (hashdump, logonpasswords, dcsync, mimikatz, chromedump)
- Network recon (net domain/computers/users/groups/shares/sessions/logons/trusts/dclist/view)
- Port scanning
- SOCKS proxy (start/stop)
- Reverse port forward (start/stop)
- Beacon config (spawnto, ppid, blockdlls, argue, beacon gate, syscall method)
- Listeners (list, create, delete)
- BOF execution (string, pack, packed)
- Console command (fallback for anything without a dedicated endpoint)
- Task history sync (full CS client console history on connect)
- C2 host management (hold, release, delete, profiles, failover)
- Jobs management (list, kill)
- Downloads management (list, cancel, active downloads)
