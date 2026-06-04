# Cobalt Strike REST API Reference

**Version:** 1.0.0-BETA | **OpenAPI:** 3.1.0 | **Source:** Official Fortra Documentation (CS 4.12, December 2025)

> Auto-generated from `spec.js` — the full OpenAPI specification is in this same directory.
> Swagger UI: open `index.html` in a browser (all required assets are local).

## Authentication

**Method:** JWT Bearer Token

```
POST /api/auth/login
Content-Type: application/json

Request:  {"username": "csrestapi", "password": "<teamserver_pass>", "durationMs": 3600000}
Response: {"access_token": "eyJhbG..."}

All subsequent requests:
Authorization: Bearer <access_token>
```

## Starting the REST API Server

```bash
# Team server must use --experimental-db flag
./teamserver <ip> <password> [profile] --experimental-db

# Start REST API (from cobaltstrike/server/rest-server/)
./csrestapi --pass <password> [--user csrestapi] [--host 127.0.0.1] [--port 50050]
# REST API listens on port 50443 (HTTPS)
# OpenAPI spec available at: https://teamserver:50443/v3/api-docs
```

## API Summary

| Metric | Value |
|--------|-------|
| Total Paths | 201 |
| Total Endpoints | 219 |
| Categories | 15 |

## Security (1 endpoints)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/auth/login` | Generate a token to access the Rest API Server |

## BeaconInfo (6 endpoints)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/beacons` | List Beacons |
| `GET` | `/api/v1/beacons/{bid}` | Get Beacons |
| `DELETE` | `/api/v1/beacons/{bid}` | Delete Beacon |
| `POST` | `/api/v1/beacons/{bid}/clearCommandQueue` | Clear Queue |
| `POST` | `/api/v1/beacons/{bid}/execute/checkIn` | DNS Beacon Checkin |
| `POST` | `/api/v1/beacons/{bid}/note` | Set Note |

## ConsoleCommand (3 endpoints)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/beacons/{bid}/consoleCommand` | Run Command |
| `GET` | `/api/v1/beacons/{bid}/help` | Help |
| `GET` | `/api/v1/beacons/{bid}/help/{command}` | Command Help |

## JobsAndTasks (8 endpoints)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/beacons/{bid}/execute/jobStop` | Stop Job |
| `POST` | `/api/v1/beacons/{bid}/state/jobs` | List Active Jobs |
| `GET` | `/api/v1/beacons/{bid}/tasks/detail` | List Beacon Tasks |
| `GET` | `/api/v1/beacons/{bid}/tasks/summary` | Get Beacon Tasks Summary |
| `GET` | `/api/v1/tasks` | List Tasks |
| `GET` | `/api/v1/tasks/{taskId}` | Get Task |
| `POST` | `/api/v1/tasks/{taskId}/error` | Log Error |
| `POST` | `/api/v1/tasks/{taskId}/log` | Log Message |

## CredsAndTokens (31 endpoints)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/beacons/{bid}/elevate/beacon` | List Privesc methods |
| `POST` | `/api/v1/beacons/{bid}/elevate/beacon` | Run a Beacon elevated (elevate) |
| `POST` | `/api/v1/beacons/{bid}/execute/kerberos/ticket/purge` | Purge Kerberos Ticket |
| `POST` | `/api/v1/beacons/{bid}/execute/kerberos/ticket/use` | Use Kerberos Ticket |
| `POST` | `/api/v1/beacons/{bid}/execute/makeToken/logonName` | Make Token with Logon Name |
| `POST` | `/api/v1/beacons/{bid}/execute/makeToken/upn` | Make Token with UPN |
| `POST` | `/api/v1/beacons/{bid}/execute/rev2self` | Revert Token |
| `POST` | `/api/v1/beacons/{bid}/execute/stealToken` | Steal Token |
| `POST` | `/api/v1/beacons/{bid}/execute/tokenStore/remove` | Delete Token |
| `POST` | `/api/v1/beacons/{bid}/execute/tokenStore/removeAll` | Delete All Tokens |
| `POST` | `/api/v1/beacons/{bid}/execute/tokenStore/steal` | Steal and Store Token |
| `POST` | `/api/v1/beacons/{bid}/execute/tokenStore/stealAndUse` | Steal and Use Token |
| `POST` | `/api/v1/beacons/{bid}/execute/tokenStore/use` | Use Token |
| `POST` | `/api/v1/beacons/{bid}/inject/chromedump` | Chromedump (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/dcsync` | DCSYNC (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/hashdump` | HashDump (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/logonPasswords` | Dump Credentials (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/mimikatz` | Mimikatz (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/postExDll` | Inject PostEx Dll (Inject) |
| `POST` | `/api/v1/beacons/{bid}/spawn/chromedump` | Chromedump (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/command/runNoOutput` | Run without output (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/dcsync` | DCSYNC (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/hashdump` | HashDump (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/logonPasswords` | Dump Credentials (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/mimikatz` | Mimikatz (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/postExDll` | Execute PostEx DLL (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/state/tokenStore` | List Tokens |
| `GET` | `/api/v1/data/credentials` | List Credentials |
| `POST` | `/api/v1/data/credentials` | Add Credential |
| `GET` | `/api/v1/data/credentials/{id}` | Get Credential |
| `DELETE` | `/api/v1/data/credentials/{id}` | Delete Credential |

## FileAndRegistry (18 endpoints)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/beacons/{bid}/activeDownloads` | List Active Downloads |
| `POST` | `/api/v1/beacons/{bid}/execute/cancelFileDownload` | Cancel Download |
| `POST` | `/api/v1/beacons/{bid}/execute/cd` | Change Current Directory |
| `POST` | `/api/v1/beacons/{bid}/execute/cp` | Copy File |
| `POST` | `/api/v1/beacons/{bid}/execute/download` | Download File |
| `POST` | `/api/v1/beacons/{bid}/execute/drives` | List Drives |
| `POST` | `/api/v1/beacons/{bid}/execute/ls` | List Directory contents |
| `POST` | `/api/v1/beacons/{bid}/execute/mkdir` | Create Directory |
| `POST` | `/api/v1/beacons/{bid}/execute/mv` | Move File |
| `POST` | `/api/v1/beacons/{bid}/execute/pwd` | Get Current Directory |
| `POST` | `/api/v1/beacons/{bid}/execute/reg/query` | Get Registry Key |
| `POST` | `/api/v1/beacons/{bid}/execute/reg/queryv` | Get Registry SubKey |
| `POST` | `/api/v1/beacons/{bid}/execute/rm` | Remove File or Folder |
| `POST` | `/api/v1/beacons/{bid}/execute/timestomp` | Timestomp |
| `POST` | `/api/v1/beacons/{bid}/execute/upload` | Upload File |
| `GET` | `/api/v1/data/downloads` | List Downloads |
| `GET` | `/api/v1/data/downloads/{id}` | Get Download |
| `DELETE` | `/api/v1/data/downloads/{id}` | Delete Download |

## NetworkRecon (29 endpoints)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/beacons/{bid}/execute/net/domain` | Get Domain |
| `POST` | `/api/v1/beacons/{bid}/inject/net/computers` | List Specified Groups (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/net/dclist` | List Domain Controllers (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/net/domainControllers` | List Domain Controllers Hosts (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/net/domainTrusts` | List Domain Trusts (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/net/group` | List Domain Groups (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/net/localGroup` | List Local Groups (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/net/logons` | List Logged in Users (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/net/sessions` | List Sessions (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/net/share` | List Shares (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/net/time` | Get System Time (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/net/user` | List Users (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/net/user/detail` | Get User (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/net/view` | List Domain Hosts (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/portscan` | Port Scan (Inject) |
| `POST` | `/api/v1/beacons/{bid}/spawn/net/computers` | List Specified Groups (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/net/dclist` | List Domain Controllers (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/net/domainControllers` | List Domain Controllers Hosts (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/net/domainTrusts` | List Domain Trusts (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/net/group` | List Domain Groups (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/net/localGroup` | List Local Groups (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/net/logons` | List Logged in Users (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/net/sessions` | List Sessions (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/net/share` | List Shares (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/net/time` | Get System Time (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/net/user` | List Users (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/net/user/detail` | Get User (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/net/view` | List Domain Hosts (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/portscan` | Port Scan (Spawn) |

## PayloadAndArtifacts (4 endpoints)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/artifacts` | List Artifacts |
| `POST` | `/api/v1/payloads/generate/stageless` | Create Stageless Payload |
| `POST` | `/api/v1/payloads/generate/stager` | Create Stager Payload |
| `GET` | `/api/v1/payloads/{fileName}` | Retrieve payload |

## Pivoting (7 endpoints)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/beacons/{bid}/execute/link/smb` | Connect to SMB Beacon |
| `POST` | `/api/v1/beacons/{bid}/execute/link/tcp` | Connect to TCP Beacon |
| `POST` | `/api/v1/beacons/{bid}/execute/unlink` | Disconnect Pivot Beacon |
| `POST` | `/api/v1/beacons/{bid}/inject/ssh` | Connect via SSH using User/Password (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/sshKey` | Connect via SSH using Key (Inject) |
| `POST` | `/api/v1/beacons/{bid}/spawn/ssh` | Connect via SSH using User/Password (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/sshKey` | Connect via SSH using Key (Spawn) |

## ProcessAndExecution (35 endpoints)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/beacons/{bid}/elevate/command` | List Command Privilege Elevators |
| `POST` | `/api/v1/beacons/{bid}/elevate/command` | Run a Command elevated (runasadmin) |
| `POST` | `/api/v1/beacons/{bid}/execute/bof/pack` | Pack Arguments and Run BOF |
| `POST` | `/api/v1/beacons/{bid}/execute/bof/packed` | Run BOF with Packed Arguments |
| `POST` | `/api/v1/beacons/{bid}/execute/bof/string` | Run BOF |
| `POST` | `/api/v1/beacons/{bid}/execute/exit` | Exit |
| `POST` | `/api/v1/beacons/{bid}/execute/getPrivs` | Enable all available privileges |
| `POST` | `/api/v1/beacons/{bid}/execute/getSystem` | Attempt to obtain System Privileges |
| `POST` | `/api/v1/beacons/{bid}/execute/getUid` | Get current User ID |
| `POST` | `/api/v1/beacons/{bid}/execute/killProcess` | Kill Process |
| `POST` | `/api/v1/beacons/{bid}/execute/powershell/import` | Import Powershell Script |
| `POST` | `/api/v1/beacons/{bid}/execute/ps` | List Process information |
| `POST` | `/api/v1/beacons/{bid}/execute/setenv` | Set Environment variable |
| `POST` | `/api/v1/beacons/{bid}/inject/beacon` | Execute Beacon Shellcode (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/dll` | Load DLL via reflective DLL loading (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/loadDll` | Load Library from disk (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/powershell/unmanaged` | Execute unmanaged Powershell  / psinject (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/pth` | Pass-the-Hash (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/shellcode` | Execute Shellcode (Inject) |
| `GET` | `/api/v1/beacons/{bid}/remoteExec/beacon` | List Remote Beacon Execution methods |
| `POST` | `/api/v1/beacons/{bid}/remoteExec/beacon` | Remote Beacon Execution (jump) |
| `GET` | `/api/v1/beacons/{bid}/remoteExec/command` | List Remote Command Execution methods |
| `POST` | `/api/v1/beacons/{bid}/remoteExec/command` | Remote Command Execution (remote-exec) |
| `POST` | `/api/v1/beacons/{bid}/spawn/beacon` | Execute Beacon Shellcode (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/beacon/asUser` | Execute Beacon Shellcode as User (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/beacon/under` | Execute Beacon Shellcode under parentPID (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/command/run` | Run (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/command/runAs` | Run As (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/command/runUnder` | Run under parentPID (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/command/shell` | Run Shell Command (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/dotnetAssembly` | Execute .NET assembly  (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/powershell` | Execute Managed Powershell (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/powershell/unmanaged` | Execute unmanaged Powershell  / powerpick (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/pth` | Pass-the-Hash (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/shellcode` | Execute Shellcode (Spawn) |

## Capture (15 endpoints)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/beacons/{bid}/execute/clipboard` | Get Clipboard content |
| `POST` | `/api/v1/beacons/{bid}/inject/keylogger` | Start Keylogger (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/printscreen` | Print Screen (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/screenshot` | Take Screenshot (Inject) |
| `POST` | `/api/v1/beacons/{bid}/inject/screenwatch` | Start Screenwatch (Inject) |
| `GET` | `/api/v1/beacons/{bid}/keystrokes` | List Beacon Keystrokes |
| `POST` | `/api/v1/beacons/{bid}/spawn/keylogger` | Start Keylogger (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/printscreen` | Print Screen (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/screenshot` | Take Screenshot (Spawn) |
| `POST` | `/api/v1/beacons/{bid}/spawn/screenwatch` | Start Screenwatch (Spawn) |
| `GET` | `/api/v1/data/keystrokes` | List Keystrokes |
| `DELETE` | `/api/v1/data/keystrokes/{id}` | Delete Keystrokes |
| `GET` | `/api/v1/data/screenshots` | List Screenshots |
| `GET` | `/api/v1/data/screenshots/{id}` | Get Screenshot |
| `DELETE` | `/api/v1/data/screenshots/{id}` | Delete Screenshot |

## Tunneling (8 endpoints)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/beacons/{bid}/execute/browserpivotStop` | Stop Browser Pivot |
| `POST` | `/api/v1/beacons/{bid}/execute/rportfwdStart/onTeamserver` | Start Remote Port Forwarding |
| `POST` | `/api/v1/beacons/{bid}/execute/rportfwdStop/onTeamserver` | Stop Reverse Port Forwarding |
| `POST` | `/api/v1/beacons/{bid}/execute/socks4Start` | Start SOCKS4a Server |
| `POST` | `/api/v1/beacons/{bid}/execute/socks5Start` | Start SOCKS5 Server |
| `POST` | `/api/v1/beacons/{bid}/execute/socksStop/all` | Stop All SOCKS Servers |
| `POST` | `/api/v1/beacons/{bid}/execute/socksStop/{port}` | Stop SOCKS Server |
| `POST` | `/api/v1/beacons/{bid}/inject/browserpivotStart` | Start Browser Pivot (Inject) |

## BeaconConfig (27 endpoints)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/beacons/{bid}/execute/beaconInfo` | Get Beacon Info |
| `POST` | `/api/v1/beacons/{bid}/state/beaconGate/disable` | Disable Beacon Gate |
| `POST` | `/api/v1/beacons/{bid}/state/beaconGate/enable` | Enable Beacon Gate |
| `POST` | `/api/v1/beacons/{bid}/state/blockdlls/disable` | Disable Block Dlls |
| `POST` | `/api/v1/beacons/{bid}/state/blockdlls/enable` | Enable Block Dlls |
| `GET` | `/api/v1/beacons/{bid}/state/c2/failoverNotification` | Get Failover Notification config |
| `POST` | `/api/v1/beacons/{bid}/state/c2/failoverNotification/disable` | Disable Failover Notification |
| `POST` | `/api/v1/beacons/{bid}/state/c2/failoverNotification/enable` | Enable Failover Notification |
| `GET` | `/api/v1/beacons/{bid}/state/c2/host` | Get Beacon Callback Information |
| `PUT` | `/api/v1/beacons/{bid}/state/c2/host` | Update Host in Beacon Callback hosts list |
| `POST` | `/api/v1/beacons/{bid}/state/c2/host` | Add Host to Beacon Callback hosts list |
| `DELETE` | `/api/v1/beacons/{bid}/state/c2/host` | Delete Host |
| `POST` | `/api/v1/beacons/{bid}/state/c2/host/hold` | Hold Host |
| `GET` | `/api/v1/beacons/{bid}/state/c2/host/profiles` | List Host Profiles |
| `POST` | `/api/v1/beacons/{bid}/state/c2/host/release` | Release Host |
| `POST` | `/api/v1/beacons/{bid}/state/c2/host/reset` | Reset Hosts Stats |
| `POST` | `/api/v1/beacons/{bid}/state/dnsMode` | Set DNS Beacon Mode |
| `POST` | `/api/v1/beacons/{bid}/state/ppid` | Set Initial Beacon PID |
| `DELETE` | `/api/v1/beacons/{bid}/state/ppid` | Reset the specified parent PID |
| `POST` | `/api/v1/beacons/{bid}/state/sleepTime` | Set Sleep |
| `POST` | `/api/v1/beacons/{bid}/state/spawnto` | Set executable that is used when spawning |
| `DELETE` | `/api/v1/beacons/{bid}/state/spawnto` | Reset the executable that is used when spawning to default |
| `GET` | `/api/v1/beacons/{bid}/state/spoofedArguments` | List Argue / Command Line Argument Spoofing  |
| `POST` | `/api/v1/beacons/{bid}/state/spoofedArguments` | Add Command Line Argument Spoofing  |
| `DELETE` | `/api/v1/beacons/{bid}/state/spoofedArguments` | Remove Argument Spoofing Configuration |
| `GET` | `/api/v1/beacons/{bid}/state/syscallMethod` | Get Syscall Method |
| `POST` | `/api/v1/beacons/{bid}/state/syscallMethod` | Set Syscall Method |

## Listeners (21 endpoints)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/listeners` | List Listeners |
| `POST` | `/api/v1/listeners/dns` | Add DNS Listener |
| `PUT` | `/api/v1/listeners/dns/{name}` | Update DNS Listener |
| `POST` | `/api/v1/listeners/externalC2` | Add External C2 Listener |
| `PUT` | `/api/v1/listeners/externalC2/{name}` | Update External C2 Listener |
| `POST` | `/api/v1/listeners/foreignHttp` | Add Foreign HTTP Listener |
| `PUT` | `/api/v1/listeners/foreignHttp/{name}` | Update Foreign HTTP Listener |
| `POST` | `/api/v1/listeners/foreignHttps` | Add Foreign HTTPS Listener |
| `PUT` | `/api/v1/listeners/foreignHttps/{name}` | Update Foreign HTTPs Listener |
| `POST` | `/api/v1/listeners/http` | Add HTTP Listener |
| `PUT` | `/api/v1/listeners/http/{name}` | Update HTTP Listener |
| `POST` | `/api/v1/listeners/https` | Add HTTPS Listener |
| `PUT` | `/api/v1/listeners/https/{name}` | Update HTTPS Listener |
| `POST` | `/api/v1/listeners/smb` | Add SMB Listener |
| `PUT` | `/api/v1/listeners/smb/{name}` | Update SMB Listener |
| `POST` | `/api/v1/listeners/tcp` | Add TCP Listener |
| `PUT` | `/api/v1/listeners/tcp/{name}` | Update TCP Listener |
| `POST` | `/api/v1/listeners/userDefinedC2` | Add UDC2 Listener |
| `PUT` | `/api/v1/listeners/userDefinedC2/{name}` | Update UDC2 Listener |
| `GET` | `/api/v1/listeners/{name}` | Get Listener |
| `DELETE` | `/api/v1/listeners/{name}` | Delete Listener |

## ServerConfig (6 endpoints)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1` | Entry point to the API |
| `GET` | `/api/v1/config/killdate` | Get the Beacon kill date configured on the team server |
| `GET` | `/api/v1/config/profile` | Get Malleable Profile |
| `DELETE` | `/api/v1/config/resetData` | Reset Data Model |
| `GET` | `/api/v1/config/systeminformation` | Get System Information |
| `GET` | `/api/v1/config/teamserverIp` | Get team server IP |

## Known Limitations (Beta)

- REST API does not support file uploads (use SSH/SCP)
- Server-side Aggressor Scripts restricted to Sleep/Aggressor only (no Java bindings)
- BOF pack endpoint has known issues in some versions
- API is labeled v1.0.0-BETA
