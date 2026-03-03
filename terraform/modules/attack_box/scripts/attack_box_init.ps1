# Windows Server 2022 Attack Box Init - Standalone Module
# =============================================================================
# Optimized for Red Team Operations across all deployment types:
# - C2-only: Accessed via bastion RDP tunnel
# - GOAD-only: Accessed via jumpbox SSH tunnel
# - Combined: Accessed via bastion RDP tunnel
#
# Phases:
# 1. Remove server bloat & optimize for workstation
# 2. Disable Windows Defender completely
# 3. System configuration (hostname, password, RDP, SSH, tools)
# 4. Clone red team tools repo to C:\Tools
# 5. Install Cobalt Strike Client from S3
# 6. WSL2 setup with Ubuntu
# 7. SSH key exchange (GOAD deployments only)
# 8. Desktop shortcuts and final configuration
# =============================================================================

$ErrorActionPreference = "Continue"

# Create deployment logs folder on Desktop
$DeploymentLogsDir = "C:\Users\Administrator\Desktop\Deployment-Logs-Scripts"
New-Item -ItemType Directory -Path $DeploymentLogsDir -Force | Out-Null

$LogFile = "$DeploymentLogsDir\attackbox-init.log"
$ScriptsDir = $DeploymentLogsDir

function Write-Log { param([string]$Message); "$(Get-Date -Format 'HH:mm:ss') - $Message" | Out-File -Append $LogFile; Write-Host $Message }

Write-Log "=== Windows Server 2022 Attack Box Init Started ==="
Write-Log "Deployment logs and scripts will be stored in: $DeploymentLogsDir"

$C2ServerIP = "${c2_server_ip}"
$C2ServerPort = "${c2_server_port}"
$AdminPassword = "${admin_password}"
$DeploymentBucket = "${deployment_bucket}"
$DeploymentId = "${deployment_id}"
$AwsRegion = "${aws_region}"
$Hostname = "${hostname}"
$CSClientS3Path = "${cs_client_s3_path}"
$ToolsRepoUrl = "${tools_repo_url}"
$ToolsRepoBranch = "${tools_repo_branch}"
$EnableKeyExchange = "${enable_key_exchange}"
$S3KeyPrefix = "${s3_key_prefix}"

# =============================================================================
# PHASE 1: REMOVE SERVER BLOAT & OPTIMIZE FOR WORKSTATION USE
# =============================================================================

Write-Log "PHASE 1: Removing server bloat and optimizing for workstation use..."

# Disable Server Manager auto-start
Get-ScheduledTask -TaskName ServerManager -ErrorAction SilentlyContinue | Disable-ScheduledTask -ErrorAction SilentlyContinue

# Disable IE Enhanced Security Configuration
$AdminKey = "HKLM:\SOFTWARE\Microsoft\Active Setup\Installed Components\{A509B1A7-37EF-4b3f-8CFC-4F3A74704073}"
$UserKey = "HKLM:\SOFTWARE\Microsoft\Active Setup\Installed Components\{A509B1A8-37EF-4b3f-8CFC-4F3A74704073}"
Set-ItemProperty -Path $AdminKey -Name "IsInstalled" -Value 0 -ErrorAction SilentlyContinue
Set-ItemProperty -Path $UserKey -Name "IsInstalled" -Value 0 -ErrorAction SilentlyContinue

# Optimize for programs (not background services)
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\PriorityControl" -Name "Win32PrioritySeparation" -Value 38 -ErrorAction SilentlyContinue

# Disable unnecessary server services
$servicesToDisable = @("W3SVC","WAS","MSSQLSERVER","MSDTC","RemoteRegistry","SNMP","SNMPTrap")
foreach ($service in $servicesToDisable) {
    if (Get-Service -Name $service -ErrorAction SilentlyContinue) {
        try { Stop-Service -Name $service -Force -ErrorAction SilentlyContinue; Set-Service -Name $service -StartupType Disabled -ErrorAction SilentlyContinue } catch { }
    }
}

Write-Log "Phase 1 complete"

# =============================================================================
# PHASE 2: COMPLETELY DISABLE WINDOWS DEFENDER
# =============================================================================

Write-Log "PHASE 2: Disabling Windows Defender..."

$defenderPath = "HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender"
$realtimePath = "$defenderPath\Real-Time Protection"
$scanPath = "$defenderPath\Scan"
$spynetPath = "$defenderPath\Spynet"

@($defenderPath, $realtimePath, $scanPath, $spynetPath) | ForEach-Object {
    if (-not (Test-Path $_)) { New-Item -Path $_ -Force -ErrorAction SilentlyContinue | Out-Null }
}

# Disable Defender entirely via registry
Set-ItemProperty -Path $defenderPath -Name "DisableAntiSpyware" -Value 1 -Type DWord -ErrorAction SilentlyContinue
Set-ItemProperty -Path $defenderPath -Name "DisableAntiVirus" -Value 1 -Type DWord -ErrorAction SilentlyContinue
Set-ItemProperty -Path $defenderPath -Name "ServiceKeepAlive" -Value 0 -Type DWord -ErrorAction SilentlyContinue

# Disable Real-Time Protection
Set-ItemProperty -Path $realtimePath -Name "DisableBehaviorMonitoring" -Value 1 -Type DWord -ErrorAction SilentlyContinue
Set-ItemProperty -Path $realtimePath -Name "DisableIOAVProtection" -Value 1 -Type DWord -ErrorAction SilentlyContinue
Set-ItemProperty -Path $realtimePath -Name "DisableOnAccessProtection" -Value 1 -Type DWord -ErrorAction SilentlyContinue
Set-ItemProperty -Path $realtimePath -Name "DisableRealtimeMonitoring" -Value 1 -Type DWord -ErrorAction SilentlyContinue
Set-ItemProperty -Path $realtimePath -Name "DisableScanOnRealtimeEnable" -Value 1 -Type DWord -ErrorAction SilentlyContinue

# Disable scanning and cloud protection
Set-ItemProperty -Path $scanPath -Name "DisableArchiveScanning" -Value 1 -Type DWord -ErrorAction SilentlyContinue
Set-ItemProperty -Path $spynetPath -Name "SpynetReporting" -Value 0 -Type DWord -ErrorAction SilentlyContinue
Set-ItemProperty -Path $spynetPath -Name "SubmitSamplesConsent" -Value 2 -Type DWord -ErrorAction SilentlyContinue

# Disable via PowerShell cmdlets
try {
    Set-MpPreference -DisableRealtimeMonitoring $true -ErrorAction SilentlyContinue
    Set-MpPreference -DisableBehaviorMonitoring $true -ErrorAction SilentlyContinue
    Set-MpPreference -DisableBlockAtFirstSeen $true -ErrorAction SilentlyContinue
    Set-MpPreference -DisableIOAVProtection $true -ErrorAction SilentlyContinue
    Set-MpPreference -DisableScriptScanning $true -ErrorAction SilentlyContinue
    Add-MpPreference -ExclusionPath "C:\Tools" -ErrorAction SilentlyContinue
    Add-MpPreference -ExclusionPath "C:\Payloads" -ErrorAction SilentlyContinue
    Add-MpPreference -ExclusionPath "C:\CobaltStrike" -ErrorAction SilentlyContinue
} catch { Write-Log "PowerShell Defender cmdlets not available yet (disabled via registry on reboot)" }

# Stop and disable Defender services
foreach ($service in @("WinDefend","WdNisSvc","WdNisDrv","WdBoot","WdFilter","Sense")) {
    if (Get-Service -Name $service -ErrorAction SilentlyContinue) {
        try { Stop-Service -Name $service -Force -ErrorAction SilentlyContinue; Set-Service -Name $service -StartupType Disabled -ErrorAction SilentlyContinue } catch { }
    }
}

Write-Log "Phase 2 complete - Windows Defender disabled"

# =============================================================================
# PHASE 3: SYSTEM CONFIGURATION
# =============================================================================

Write-Log "PHASE 3: System configuration..."

# Set hostname
if ($Hostname) {
    try { Rename-Computer -NewName $Hostname -Force -ErrorAction SilentlyContinue; Write-Log "Hostname set to: $Hostname" } catch { Write-Log "Error setting hostname: $_" }
}

# Create directories
Write-Log "Creating directories..."
@("C:\Tools","C:\Payloads","C:\CobaltStrike","C:\Users\Administrator\.ssh","C:\ProgramData\ssh") | ForEach-Object { New-Item -ItemType Directory -Path $_ -Force | Out-Null }

# Set Administrator password
Write-Log "Setting Administrator password..."
try {
    $SecurePassword = ConvertTo-SecureString $AdminPassword -AsPlainText -Force
    Set-LocalUser -Name "Administrator" -Password $SecurePassword -PasswordNeverExpires $true
    Enable-LocalUser -Name "Administrator"
    Write-Log "Administrator password set successfully"
} catch { Write-Log "Error setting Administrator password: $_" }

# Enable RDP
Write-Log "Enabling Remote Desktop..."
try {
    Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -Name "fDenyTSConnections" -Value 0
    Enable-NetFirewallRule -DisplayGroup "Remote Desktop"
    Write-Log "Remote Desktop enabled"
} catch { Write-Log "Error enabling RDP: $_" }

# Install OpenSSH Server
Write-Log "Installing OpenSSH Server..."
try {
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 -ErrorAction SilentlyContinue
    Start-Service sshd -ErrorAction SilentlyContinue
    Set-Service -Name sshd -StartupType 'Automatic' -ErrorAction SilentlyContinue
    New-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -DisplayName "OpenSSH Server (sshd)" -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -ErrorAction SilentlyContinue
    Write-Log "OpenSSH Server installed and started"
} catch { Write-Log "OpenSSH Server setup failed: $_" }

# Install Chocolatey
Write-Log "Installing Chocolatey..."
try { if (-not (Get-Command choco -ErrorAction SilentlyContinue)) { Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1')) } } catch {}
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# Install essential tools
Write-Log "Installing tools: Git, 7zip, Python, Java 17, AWS CLI, Windows Terminal..."
@("git","7zip","python3","openjdk17","awscli","microsoft-windows-terminal") | ForEach-Object {
    Write-Log "Installing: $_"
    try { choco install $_ -y --no-progress 2>&1 | Out-Null } catch { Write-Log "Failed to install $_" }
}
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

Write-Log "Phase 3 complete"

# =============================================================================
# PHASE 4: CLONE RED TEAM TOOLS REPOSITORY TO C:\Tools
# =============================================================================

Write-Log "PHASE 4: Cloning red team tools repository..."

if ($ToolsRepoUrl -and $ToolsRepoUrl -ne "") {
    Write-Log "Cloning $ToolsRepoUrl (branch: $ToolsRepoBranch) to C:\Tools..."
    try {
        # Clone tools repo into C:\Tools (directory already created, clone into it)
        $tempToolsDir = "C:\Windows\Temp\red-team-tools"
        if (Test-Path $tempToolsDir) { Remove-Item $tempToolsDir -Recurse -Force }
        git clone --branch $ToolsRepoBranch $ToolsRepoUrl $tempToolsDir 2>&1 | Out-Null

        if (Test-Path "$tempToolsDir\.git") {
            # Move contents into C:\Tools (preserving existing dirs like Payloads)
            Get-ChildItem $tempToolsDir | ForEach-Object {
                $dest = Join-Path "C:\Tools" $_.Name
                if (Test-Path $dest) { Remove-Item $dest -Recurse -Force -ErrorAction SilentlyContinue }
                Move-Item $_.FullName $dest -Force
            }
            Remove-Item $tempToolsDir -Recurse -Force -ErrorAction SilentlyContinue
            Write-Log "Red team tools repository cloned to C:\Tools successfully"
        } else {
            Write-Log "WARNING: Git clone may have failed - .git directory not found"
        }
    } catch {
        Write-Log "Failed to clone tools repository: $_"
    }
} else {
    Write-Log "No tools repo URL provided, skipping"
    # Fallback: clone PowerSploit individually
    Write-Log "Cloning PowerSploit as fallback..."
    try { git clone https://github.com/PowerShellMafia/PowerSploit.git "C:\Tools\PowerSploit" 2>&1 | Out-Null; Write-Log "PowerSploit cloned" } catch { Write-Log "PowerSploit clone failed: $_" }
}

Write-Log "Phase 4 complete"

# =============================================================================
# PHASE 5: INSTALL COBALT STRIKE CLIENT FROM S3
# =============================================================================

Write-Log "PHASE 5: Installing Cobalt Strike Client..."

if ($CSClientS3Path -and $CSClientS3Path -ne "") {
    Write-Log "Downloading CS Client from S3: $CSClientS3Path"
    try {
        $csArchive = "C:\Windows\Temp\cs-client-archive"
        & aws s3 cp $CSClientS3Path $csArchive --region $AwsRegion 2>&1 | Out-Null

        if (Test-Path $csArchive) {
            Write-Log "Downloaded CS Client archive, extracting..."
            $csDir = "C:\CobaltStrike"

            # Detect format and extract
            $fileHeader = [System.IO.File]::ReadAllBytes($csArchive)[0..3]

            if ($fileHeader[0] -eq 0x50 -and $fileHeader[1] -eq 0x4B) {
                # ZIP format
                Expand-Archive -Path $csArchive -DestinationPath $csDir -Force
            } elseif ($fileHeader[0] -eq 0x1F -and $fileHeader[1] -eq 0x8B) {
                # tar.gz format
                $7zPath = "C:\ProgramData\chocolatey\tools\7z.exe"
                if (-not (Test-Path $7zPath)) { $7zPath = "C:\Program Files\7-Zip\7z.exe" }
                if (Test-Path $7zPath) {
                    & $7zPath x $csArchive -o"C:\Windows\Temp" -y 2>&1 | Out-Null
                    $tarFile = "C:\Windows\Temp\cs-client-archive"
                    & $7zPath x $tarFile -o"$csDir" -y 2>&1 | Out-Null
                    Remove-Item $tarFile -Force -ErrorAction SilentlyContinue
                } else {
                    tar -xzf $csArchive -C $csDir 2>&1 | Out-Null
                }
            } else {
                tar -xf $csArchive -C $csDir 2>&1 | Out-Null
            }

            Remove-Item $csArchive -Force -ErrorAction SilentlyContinue

            # Create CS Client launcher and desktop shortcut
            $csJar = Get-ChildItem $csDir -Recurse -Filter "cobaltstrike.jar" | Select-Object -First 1
            if ($csJar) {
                $csJarDir = $csJar.DirectoryName
                Write-Log "CS Client found at: $csJarDir"

                # Create launch batch file
                @"
@echo off
cd /d "$csJarDir"
java -XX:ParallelGCThreads=4 -XX:+AggressiveHeap -XX:+UseParallelGC -jar cobaltstrike.jar
pause
"@ | Out-File "C:\CobaltStrike\Launch-CS-Client.bat" -Encoding ASCII

                # Create desktop shortcut
                $WshShell = New-Object -ComObject WScript.Shell
                $Shortcut = $WshShell.CreateShortcut("C:\Users\Administrator\Desktop\Cobalt Strike Client.lnk")
                $Shortcut.TargetPath = "C:\CobaltStrike\Launch-CS-Client.bat"
                $Shortcut.WorkingDirectory = $csJarDir
                $Shortcut.IconLocation = "C:\Windows\System32\shell32.dll,13"
                $Shortcut.Save()

                Write-Log "Created CS Client desktop shortcut"
                "CS_CLIENT_INSTALLED" | Out-File "C:\CobaltStrike\status.txt"
            } else {
                Write-Log "WARNING: cobaltstrike.jar not found after extraction"
            }
        } else {
            Write-Log "WARNING: Failed to download CS Client from S3"
        }
    } catch {
        Write-Log "Error downloading/extracting CS Client: $_"
    }
} else {
    Write-Log "No CS Client S3 path provided, skipping"
}

Write-Log "Phase 5 complete"

# =============================================================================
# PHASE 6: WSL2 SETUP WITH UBUNTU
# =============================================================================

Write-Log "PHASE 6: Setting up WSL..."

try {
    # Enable WSL feature
    Write-Log "Enabling WSL Windows feature..."
    dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart 2>&1 | Out-Null

    # Enable Virtual Machine Platform (for WSL2)
    Write-Log "Enabling Virtual Machine Platform..."
    dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart 2>&1 | Out-Null

    # Set WSL default version to 1 (more compatible with EC2, no nested virt needed)
    wsl --set-default-version 1 2>&1 | Out-Null

    # Install Ubuntu
    Write-Log "Installing Ubuntu for WSL..."
    wsl --install -d Ubuntu --no-launch 2>&1 | Out-Null

    Write-Log "WSL setup complete (Ubuntu will finalize on first login)"
} catch {
    Write-Log "WSL setup failed: $_"
}

Write-Log "Phase 6 complete"

# =============================================================================
# PHASE 7: SSH KEY EXCHANGE (GOAD deployments only)
# =============================================================================

if ($EnableKeyExchange -eq "true" -and $DeploymentBucket) {
    Write-Log "PHASE 7: SSH key exchange enabled (GOAD mode)..."

    # Download jumpbox public key from S3
    $s3JumpboxKey = "s3://$DeploymentBucket/$S3KeyPrefix/jumpbox_internal.pub"
    Write-Log "Waiting for jumpbox public key from S3..."
    for ($i=1; $i -le 60; $i++) {
        try {
            & aws s3 cp $s3JumpboxKey "C:\Windows\Temp\jumpbox.pub" --region $AwsRegion 2>&1 | Out-Null
            if (Test-Path "C:\Windows\Temp\jumpbox.pub") {
                Write-Log "Downloaded jumpbox public key"
                $sshDir = "C:\ProgramData\ssh"
                $authKeysFile = "$sshDir\administrators_authorized_keys"
                Copy-Item "C:\Windows\Temp\jumpbox.pub" $authKeysFile -Force
                icacls $authKeysFile /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F" 2>&1 | Out-Null
                Write-Log "Configured SSH authorized_keys for Administrator"
                break
            }
        } catch { Write-Log "Key download attempt $i failed: $_" }
        Start-Sleep -Seconds 10
    }

    # Generate attack box SSH key and upload public key to S3
    Write-Log "Generating SSH key for outbound connections..."
    $sshKeyPath = "C:\Users\Administrator\.ssh\attackbox_internal_key"
    if (-not (Test-Path $sshKeyPath)) {
        & ssh-keygen -t ed25519 -f $sshKeyPath -N "" -C "attackbox-$Hostname" 2>&1 | Out-Null
        if (Test-Path $sshKeyPath) {
            Write-Log "SSH key pair generated"
            icacls $sshKeyPath /inheritance:r /grant:r "$env:USERNAME`:F" 2>&1 | Out-Null

            # Upload public key to S3
            $s3AttackboxKey = "s3://$DeploymentBucket/$S3KeyPrefix/attackbox_internal.pub"
            for ($i=1; $i -le 10; $i++) {
                try {
                    & aws s3 cp "$sshKeyPath.pub" $s3AttackboxKey --region $AwsRegion 2>&1 | Out-Null
                    Write-Log "Attack box public key uploaded to S3"
                    break
                } catch { Start-Sleep -Seconds 5 }
            }
        }
    }

    Write-Log "Phase 7 complete"
} else {
    Write-Log "PHASE 7: SSH key exchange disabled (C2/combined mode) - skipping"
}

# =============================================================================
# PHASE 8: SSH CONFIG & DESKTOP SHORTCUTS
# =============================================================================

Write-Log "PHASE 8: Creating SSH config and desktop shortcuts..."

# Create SSH config for C2 team server access
if ($C2ServerIP) {
    $sshConfigPath = "C:\Users\Administrator\.ssh\config"
    $sshConfig = @"
# Attack Box SSH Configuration
# Generated automatically during deployment

Host teamserver ts c2
    HostName $C2ServerIP
    User ubuntu
    StrictHostKeyChecking accept-new
"@

    # Add identity file for GOAD mode (key exchange enabled)
    if ($EnableKeyExchange -eq "true") {
        $sshConfig += "`n    IdentityFile C:\Users\Administrator\.ssh\attackbox_internal_key"
    }

    $sshConfig | Out-File $sshConfigPath -Encoding UTF8
    Write-Log "SSH config created for C2 server at $C2ServerIP"
}

# Create desktop info file with connection details
$infoContent = @"
=== ATTACK BOX CONNECTION INFO ===
Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')

HOSTNAME:       $Hostname
C2 SERVER:      $C2ServerIP`:$C2ServerPort

FOLDER LAYOUT:
  C:\Tools\          Red team tools (GitHub repo)
  C:\Payloads\       Payload staging area
  C:\CobaltStrike\   CS Client installation

TOOLS INSTALLED:
  - Cobalt Strike Client (if S3 path provided)
  - Git, Python 3, Java 17, 7-Zip, VS Code
  - AWS CLI, Windows Terminal
  - WSL with Ubuntu
  - PowerSploit (in C:\Tools)

CS CLIENT:
  Double-click "Cobalt Strike Client" on Desktop
  Connect to: $C2ServerIP`:$C2ServerPort

SECURITY NOTES:
  - Windows Defender: DISABLED
  - Windows Firewall: RDP + SSH allowed
  - This box has NO public IP (private subnet only)
"@

$infoContent | Out-File "C:\Users\Administrator\Desktop\ATTACK-BOX-INFO.txt" -Encoding UTF8

# Create Payloads shortcut on desktop
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("C:\Users\Administrator\Desktop\Payloads.lnk")
$Shortcut.TargetPath = "C:\Payloads"
$Shortcut.Save()

# Create Tools shortcut on desktop
$Shortcut = $WshShell.CreateShortcut("C:\Users\Administrator\Desktop\Tools.lnk")
$Shortcut.TargetPath = "C:\Tools"
$Shortcut.Save()

Write-Log "Phase 8 complete"

# =============================================================================
# DONE
# =============================================================================

Write-Log "=== Attack Box Init Completed Successfully ==="
Write-Log "Folders: C:\Tools (repo), C:\Payloads (staging), C:\CobaltStrike (client)"
Write-Log "A reboot may be required for hostname change and WSL to finalize"

# Mark completion
"INIT_COMPLETE" | Out-File "C:\Users\Administrator\Desktop\Deployment-Logs-Scripts\init_status.txt"
