# Windows Server 2022 Attack Box Init - Standalone Module
# =============================================================================
# Optimized for Red Team Operations across all deployment types:
# - C2-only: Accessed via bastion RDP tunnel
# - GOAD-only: Accessed via jumpbox SSH tunnel
# - Combined: Accessed via bastion RDP tunnel
#
# Phases:
# 1. Remove server bloat & optimize for workstation
# 2. Configure Windows Defender (exclusions mode -- engine active for ThreatCheck)
# 3. System configuration (hostname, password, RDP, SSH, tools, Windows Terminal)
# 4. Clone red team tools repo to C:\Tools
# 5. Clone Cobalt Strike Community Kit to C:\CommunityTools
# 6. Install Cobalt Strike Client from S3 + automated license activation
# 7. WSL1 setup with Ubuntu (WSL1 -- EC2 lacks nested virt for WSL2)
# 7b. Configure Windows Terminal profiles (PowerShell, CMD, WSL, Team Server SSH)
# 8. SSH key exchange (GOAD deployments only)
# 9. Desktop shortcuts and final configuration
# =============================================================================

$ErrorActionPreference = "Continue"

# Create deployment logs folder on Desktop
$DeploymentLogsDir = "C:\Users\Administrator\Desktop\Deployment-Logs-Scripts"
New-Item -ItemType Directory -Path $DeploymentLogsDir -Force | Out-Null

$LogFile = "$DeploymentLogsDir\attackbox-init.log"

function Write-Log { param([string]$Message); "$(Get-Date -Format 'HH:mm:ss') - $Message" | Out-File -Append $LogFile; Write-Host $Message }

Write-Log "=== Windows Server 2022 Attack Box Init Started ==="
Write-Log "Deployment logs and scripts will be stored in: $DeploymentLogsDir"

$C2ServerIP = "${c2_server_ip}"
$C2ServerPort = "${c2_server_port}"
$DeploymentBucket = "${deployment_bucket}"
$DeploymentId = "${deployment_id}"
$AwsRegion = "${aws_region}"
$Hostname = "${hostname}"
$CSClientS3Path = "${cs_client_s3_path}"
$ToolsRepoUrl = "${tools_repo_url}"
$ToolsRepoBranch = "${tools_repo_branch}"
$EnableKeyExchange = "${enable_key_exchange}"
$S3KeyPrefix = "${s3_key_prefix}"
$PrimaryDomain = "${primary_domain}"
$C2Subdomain = "${c2_subdomain}"
$MalleableProfile = "${malleable_profile}"
$GitHubTokenSecretName = "${github_token_secret_name}"
$CSLicenseSecretName = "${cs_license_secret_name}"

# =============================================================================
# Setup Status Tracking (for Host Setup Checker dashboard feature)
# =============================================================================
$SetupStatusFile = "C:\ProgramData\setup-status.json"
$SetupStartedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$script:PhaseStartTime = Get-Date

function Write-SetupStatus {
    param([int]$Step, [string]$Name, [string]$Status, [string]$Message = "")
    $duration = [int]((Get-Date) - $script:PhaseStartTime).TotalSeconds
    $script:PhaseStartTime = Get-Date

    if (Test-Path $SetupStatusFile) {
        try {
            $data = Get-Content $SetupStatusFile -Raw | ConvertFrom-Json
        } catch {
            $data = $null
        }
    }
    if (-not $data) {
        $data = [PSCustomObject]@{
            host = $env:COMPUTERNAME
            role = "attackbox"
            total_steps = 9
            completed = 0
            failed = 0
            warnings = 0
            status = "running"
            steps = @()
            started_at = $SetupStartedAt
            finished_at = $null
        }
    }
    $stepObj = [PSCustomObject]@{ step=$Step; name=$Name; status=$Status; duration_s=$duration; message=$Message }
    $data.steps = @($data.steps) + @($stepObj)
    $data.completed = @($data.steps | Where-Object { $_.status -in @("ok","warning") }).Count
    $data.failed = @($data.steps | Where-Object { $_.status -eq "failed" }).Count
    $data.warnings = @($data.steps | Where-Object { $_.status -eq "warning" }).Count
    $data.finished_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    if ($data.failed -gt 0) { $data.status = "partial" }
    elseif ($data.completed -eq $data.total_steps) { $data.status = "complete" }
    try {
        $data | ConvertTo-Json -Depth 3 | Out-File $SetupStatusFile -Encoding UTF8
    } catch {
        Write-Log "WARNING: Failed to write setup status for step $Step"
    }
}

# Load AWS PowerShell module (pre-installed on Windows Server AMIs, unlike the AWS CLI)
Import-Module AWSPowerShell -ErrorAction SilentlyContinue
Set-DefaultAWSRegion -Region $AwsRegion

# Fetch IAM role credentials via IMDSv2 (bootstrap already did this, but re-fetch in case token expired)
try {
    $imdsToken = Invoke-RestMethod -Uri "http://169.254.169.254/latest/api/token" -Method PUT -Headers @{"X-aws-ec2-metadata-token-ttl-seconds"="300"} -TimeoutSec 5
    $roleName = Invoke-RestMethod -Uri "http://169.254.169.254/latest/meta-data/iam/security-credentials/" -Headers @{"X-aws-ec2-metadata-token"=$imdsToken} -TimeoutSec 5
    $creds = Invoke-RestMethod -Uri "http://169.254.169.254/latest/meta-data/iam/security-credentials/$roleName" -Headers @{"X-aws-ec2-metadata-token"=$imdsToken} -TimeoutSec 5
    Set-AWSCredential -AccessKey $creds.AccessKeyId -SecretKey $creds.SecretAccessKey -SessionToken $creds.Token
    Write-Log "IAM credentials loaded for role: $roleName"
} catch {
    Write-Log "Warning: Could not fetch IMDSv2 credentials: $($_.Exception.Message)"
}

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
Write-SetupStatus -Step 1 -Name "Bloat Removal" -Status "ok"

# =============================================================================
# PHASE 2: CONFIGURE WINDOWS DEFENDER (exclusions-based, keeps engine running)
# =============================================================================
# Defender is kept RUNNING so ThreatCheck can use its scan engine to identify
# detection signatures in payloads. Tool directories are excluded so existing
# offensive tools (mimikatz, Rubeus, etc.) are not quarantined.
#
# If Defender is fully disabled (DisableAntiSpyware=1), ThreatCheck cannot
# function because it relies on the MpSvc scanning engine being active.

Write-Log "PHASE 2: Configuring Windows Defender (exclusions mode -- engine stays active for ThreatCheck)..."

$defenderPath = "HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender"

# Ensure the GP key does NOT block Defender from starting
if (Test-Path $defenderPath) {
    Remove-ItemProperty -Path $defenderPath -Name "DisableAntiSpyware" -ErrorAction SilentlyContinue
    Remove-ItemProperty -Path $defenderPath -Name "DisableAntiVirus" -ErrorAction SilentlyContinue
}

# Disable cloud sample submission (OPSEC -- don't send payloads to Microsoft)
$spynetPath = "$defenderPath\Spynet"
if (-not (Test-Path $spynetPath)) { New-Item -Path $spynetPath -Force | Out-Null }
Set-ItemProperty -Path $spynetPath -Name "SpynetReporting" -Value 0 -Type DWord -ErrorAction SilentlyContinue
Set-ItemProperty -Path $spynetPath -Name "SubmitSamplesConsent" -Value 2 -Type DWord -ErrorAction SilentlyContinue

# Disable automatic remediation (don't quarantine without operator review)
try {
    Set-MpPreference -DisableAutoExclusions $false -ErrorAction SilentlyContinue
    Set-MpPreference -SubmitSamplesConsent 2 -ErrorAction SilentlyContinue
    Set-MpPreference -MAPSReporting 0 -ErrorAction SilentlyContinue
    Set-MpPreference -DisableBlockAtFirstSeen $true -ErrorAction SilentlyContinue
} catch { Write-Log "Some MpPreference settings not available (will apply after reboot)" }

# Add exclusions for all tool directories so existing offensive tools are NOT quarantined
$exclusionPaths = @(
    "C:\Tools",
    "C:\Payloads",
    "C:\CommunityTools",
    "C:\Tools\CobaltStrike",
    "C:\Users\Administrator\Desktop"
)
try {
    foreach ($path in $exclusionPaths) {
        Add-MpPreference -ExclusionPath $path -ErrorAction SilentlyContinue
    }
    Write-Log "Defender exclusions added: $($exclusionPaths -join ', ')"
} catch { Write-Log "Exclusion setup deferred (Defender service may not be ready yet)" }

# Ensure WinDefend service is enabled and running
try {
    Set-Service -Name WinDefend -StartupType Automatic -ErrorAction SilentlyContinue
    Start-Service WinDefend -ErrorAction SilentlyContinue
    Write-Log "WinDefend service started (engine active for ThreatCheck)"
} catch { Write-Log "WinDefend start deferred to post-reboot" }

# Disable Sense (Defender ATP/EDR telemetry) -- OPSEC, don't phone home
foreach ($service in @("Sense")) {
    if (Get-Service -Name $service -ErrorAction SilentlyContinue) {
        try { Stop-Service -Name $service -Force -ErrorAction SilentlyContinue; Set-Service -Name $service -StartupType Disabled -ErrorAction SilentlyContinue } catch { }
    }
}

Write-Log "Phase 2 complete - Defender configured (exclusions active, engine running, cloud/ATP disabled)"
Write-SetupStatus -Step 2 -Name "Defender Config" -Status "ok" -Message "Engine active for ThreatCheck, tool dirs excluded"

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
@("C:\Tools","C:\Payloads","C:\Tools\CobaltStrike","C:\Users\Administrator\.ssh","C:\ProgramData\ssh") | ForEach-Object { New-Item -ItemType Directory -Path $_ -Force | Out-Null }

# Administrator password -- managed by EC2Launch v2
# The password is auto-generated by EC2Launch v2 during PreReady stage and encrypted
# with the instance's RSA key pair. It's retrieved via aws ec2 get-password-data.
# No manual password setting needed -- this avoids silent failures with Set-LocalUser.
Write-Log "Administrator password managed by EC2Launch v2 (auto-generated)"
try {
    Enable-LocalUser -Name "Administrator"
    # Set password to never expire
    $user = [ADSI]"WinNT://./Administrator,user"
    $user.UserFlags.Value = $user.UserFlags.Value -bor 0x10000  # ADS_UF_DONT_EXPIRE_PASSWD
    $user.SetInfo()
    Write-Log "Administrator account enabled with password-never-expires"
} catch { Write-Log "Error configuring Administrator account: $_" }

# Enable RDP
Write-Log "Enabling Remote Desktop..."
try {
    Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -Name "fDenyTSConnections" -Value 0
    Enable-NetFirewallRule -DisplayGroup "Remote Desktop"
    Write-Log "Remote Desktop enabled"
} catch { Write-Log "Error enabling RDP: $_" }

# Ensure OpenSSH Server is running (already installed by bootstrap script)
Write-Log "Ensuring OpenSSH Server is running..."
try {
    $sshdService = Get-Service sshd -ErrorAction SilentlyContinue
    if ($sshdService) {
        if ($sshdService.Status -ne 'Running') { Start-Service sshd -ErrorAction SilentlyContinue }
        Set-Service -Name sshd -StartupType 'Automatic' -ErrorAction SilentlyContinue
        Write-Log "OpenSSH Server running (installed by bootstrap)"
    } else {
        Write-Log "WARNING: sshd service not found -- bootstrap OpenSSH install may have failed"
    }
} catch { Write-Log "OpenSSH check failed: $_" }

# Install Chocolatey
Write-Log "Installing Chocolatey..."
try { if (-not (Get-Command choco -ErrorAction SilentlyContinue)) { Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1')) } } catch {}
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# Install essential tools (Windows Terminal removed -- installed separately via GitHub release below)
Write-Log "Installing tools: Git, 7zip, Python, Java 17, AWS CLI, VS Code..."
@("git","7zip","python3","openjdk17","awscli","vscode") | ForEach-Object {
    Write-Log "Installing: $_"
    try { choco install $_ -y --no-progress 2>&1 | Out-Null } catch { Write-Log "Failed to install $_" }
}
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# Install Windows Terminal via GitHub release (portable ZIP)
# Why not MSIX? MSIX installs to C:\Program Files\WindowsApps which has TrustedInstaller-only
# ACLs on Windows Server 2022. Even Administrators can't run executables from that path via
# shortcuts without taking ownership first. The portable ZIP installs to a normal Program Files
# directory with standard permissions -- just works.
Write-Log "Installing Windows Terminal (portable) from GitHub release..."
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

    $wtApiUrl = "https://api.github.com/repos/microsoft/terminal/releases/latest"
    $headers = @{ "User-Agent" = "PowerShell" }
    $release = Invoke-RestMethod -Uri $wtApiUrl -Headers $headers -TimeoutSec 30

    # Get the x64 portable ZIP (NOT arm64, NOT msixbundle)
    $zipAsset = $release.assets | Where-Object { $_.name -match 'Microsoft\.WindowsTerminal.*x64\.zip$' } | Select-Object -First 1
    if (-not $zipAsset) {
        # Fallback: any ZIP that is not arm64/x86/msixbundle
        $zipAsset = $release.assets | Where-Object { $_.name -match '\.zip$' -and $_.name -notmatch 'arm64|x86|msixbundle|GroupPolicy' } | Select-Object -First 1
    }

    if ($zipAsset) {
        $zipUrl = $zipAsset.browser_download_url
        $zipDest = "$env:TEMP\WindowsTerminal_x64.zip"
        Write-Log "Downloading: $($zipAsset.name) ($([math]::Round($zipAsset.size/1MB,1)) MB)"
        (New-Object System.Net.WebClient).DownloadFile($zipUrl, $zipDest)

        $zipSize = (Get-Item $zipDest).Length
        if ($zipSize -gt 1000000) {
            $installDir = "C:\Program Files\WindowsTerminal"
            Remove-Item $installDir -Recurse -Force -ErrorAction SilentlyContinue
            Expand-Archive -Path $zipDest -DestinationPath $installDir -Force
            Remove-Item $zipDest -Force -ErrorAction SilentlyContinue

            $wtExe = Get-ChildItem $installDir -Recurse -Filter "wt.exe" | Select-Object -First 1
            if ($wtExe) {
                $wtDir = $wtExe.DirectoryName
                Write-Log "Windows Terminal installed to: $wtDir"

                # Create .portable marker so WT reads settings from its own directory
                [System.IO.File]::WriteAllText("$wtDir\.portable", "")

                # Add to system PATH
                $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
                if ($machinePath -notlike "*WindowsTerminal*") {
                    [System.Environment]::SetEnvironmentVariable("Path", "$machinePath;$wtDir", "Machine")
                }
                $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine")

                # Desktop shortcut
                $WshShell = New-Object -ComObject WScript.Shell
                $Shortcut = $WshShell.CreateShortcut("C:\Users\Administrator\Desktop\Windows Terminal.lnk")
                $Shortcut.TargetPath = $wtExe.FullName
                $Shortcut.WorkingDirectory = "C:\Tools"
                $Shortcut.Description = "Windows Terminal"
                $Shortcut.Save()

                # Start Menu shortcut
                $Shortcut2 = $WshShell.CreateShortcut("C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Windows Terminal.lnk")
                $Shortcut2.TargetPath = $wtExe.FullName
                $Shortcut2.WorkingDirectory = "C:\Tools"
                $Shortcut2.Description = "Windows Terminal"
                $Shortcut2.Save()

                Write-Log "Windows Terminal shortcuts created (Desktop + Start Menu)"
            } else {
                Write-Log "WARNING: wt.exe not found after extraction"
            }
        } else {
            Write-Log "WARNING: Downloaded file too small ($zipSize bytes), likely an error page"
        }
    } else {
        Write-Log "WARNING: Could not find Windows Terminal x64 ZIP in GitHub release"
    }
} catch {
    Write-Log "WARNING: Windows Terminal install failed: $($_.Exception.Message)"
    Write-Log "You can install it manually from: https://github.com/microsoft/terminal/releases"
}

# Install .NET build toolchain for compiling C# offensive tools (Rubeus, Seatbelt, Certify, etc.)
# These tools target .NET Framework 4.x and need MSBuild + targeting packs, not dotnet CLI
Write-Log "Installing VS Build Tools + .NET Framework dev pack (for compiling C# tools)..."
try {
    choco install netfx-4.8-devpack -y --no-progress 2>&1 | Out-Null
    Write-Log "Installed .NET Framework 4.8 Developer Pack"
} catch { Write-Log "Failed to install netfx-4.8-devpack" }

try {
    choco install visualstudio2022buildtools -y --no-progress --package-parameters "--add Microsoft.VisualStudio.Workload.ManagedDesktopBuildTools --add Microsoft.Net.Component.4.0.TargetingPack --add Microsoft.Net.Component.4.5.TargetingPack --add Microsoft.Net.Component.4.7.2.TargetingPack --add Microsoft.Net.Component.4.8.TargetingPack --includeRecommended --quiet --wait" 2>&1 | Out-Null
    Write-Log "Installed VS 2022 Build Tools with .NET desktop workload"
} catch { Write-Log "Failed to install VS Build Tools" }
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

Write-Log "Phase 3 complete"
Write-SetupStatus -Step 3 -Name "System Config" -Status "ok"

# =============================================================================
# PHASE 4: CLONE RED TEAM TOOLS REPOSITORY TO C:\Tools
# =============================================================================

Write-Log "PHASE 4: Cloning red team tools repository..."

# Fetch GitHub token from Secrets Manager at runtime (never stored in script)
$ToolsRepoToken = ""
if ($GitHubTokenSecretName -and $GitHubTokenSecretName -ne "") {
    Write-Log "Fetching GitHub token from AWS Secrets Manager..."
    try {
        $secretValue = Get-SECSecretValue -SecretId $GitHubTokenSecretName -Region $AwsRegion -ErrorAction Stop
        $ToolsRepoToken = $secretValue.SecretString
        Write-Log "GitHub token retrieved successfully"
    } catch {
        Write-Log "WARNING: Failed to get GitHub token: $($_.Exception.Message)"
        Write-Log "HINT: Check IAM role has secretsmanager:GetSecretValue for: $GitHubTokenSecretName"
    }
}

if ($ToolsRepoUrl -and $ToolsRepoUrl -ne "") {
    # Construct authenticated URL if token is available
    $CloneUrl = $ToolsRepoUrl
    if ($ToolsRepoToken -and $ToolsRepoToken -ne "") {
        Write-Log "Cloning tools repository with GitHub token authentication..."
        $CloneUrl = $ToolsRepoUrl -replace "https://", "https://$ToolsRepoToken@"
    } else {
        Write-Log "Cloning tools repository (no token - public repos only)..."
    }

    Write-Log "Cloning $ToolsRepoUrl (branch: $ToolsRepoBranch) to C:\Tools..."
    try {
        # Disable git credential manager to prevent hanging on private repos
        # when no token is provided (credential manager waits for interactive input)
        $env:GIT_TERMINAL_PROMPT = "0"
        & git config --global credential.helper "" 2>&1 | Out-Null

        # Clone tools repo into C:\Tools (directory already created, clone into it)
        $tempToolsDir = "C:\Windows\Temp\red-team-tools"
        if (Test-Path $tempToolsDir) { Remove-Item $tempToolsDir -Recurse -Force }
        git clone --recurse-submodules --branch $ToolsRepoBranch $CloneUrl $tempToolsDir 2>&1 | Out-Null

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
            if (-not $ToolsRepoToken -or $ToolsRepoToken -eq "") {
                Write-Log "HINT: No GitHub token provided - private repos require authentication"
            }
        }
    } catch {
        Write-Log "Failed to clone tools repository: $_"
    }

    # OPSEC: Clear token from memory
    $CloneUrl = ""
    $ToolsRepoToken = ""
    Write-Log "GitHub token cleared from memory (OPSEC)"
} else {
    Write-Log "No tools repo URL provided, skipping"
    # Fallback: clone PowerSploit individually
    Write-Log "Cloning PowerSploit as fallback..."
    try { git clone https://github.com/PowerShellMafia/PowerSploit.git "C:\Tools\PowerSploit" 2>&1 | Out-Null; Write-Log "PowerSploit cloned" } catch { Write-Log "PowerSploit clone failed: $_" }
}

# Download Sysinternals Suite
Write-Log "Downloading Sysinternals Suite..."
try {
    $sysintUrl = "https://download.sysinternals.com/files/SysinternalsSuite.zip"
    $sysintZip = "C:\Windows\Temp\SysinternalsSuite.zip"
    $sysintDir = "C:\Tools\SysinternalsSuite"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    (New-Object System.Net.WebClient).DownloadFile($sysintUrl, $sysintZip)
    if (Test-Path $sysintZip) {
        New-Item -ItemType Directory -Path $sysintDir -Force | Out-Null
        Expand-Archive -Path $sysintZip -DestinationPath $sysintDir -Force
        Remove-Item $sysintZip -Force -ErrorAction SilentlyContinue
        Write-Log "Sysinternals Suite installed to $sysintDir"
    }
} catch { Write-Log "Failed to download Sysinternals Suite: $_" }

# Download dotPeek (JetBrains .NET decompiler)
Write-Log "Downloading dotPeek..."
try {
    $dpReleasesUrl = "https://data.services.jetbrains.com/products/releases?code=DPK&latest=true&type=release"
    $dpJson = (New-Object System.Net.WebClient).DownloadString($dpReleasesUrl) | ConvertFrom-Json
    $dpRelease = $dpJson.DPK[0].downloads
    # JetBrains API uses varying keys: try windowsExe, windows64, windows in order
    $dpDownloadUrl = $null
    foreach ($key in @("windowsExe", "windows64", "windows")) {
        if ($dpRelease.PSObject.Properties[$key]) {
            $dpDownloadUrl = $dpRelease.$key.link
            if ($dpDownloadUrl) { break }
        }
    }
    if ($dpDownloadUrl) {
        $dpDest = "C:\Tools\dotPeek64.exe"
        (New-Object System.Net.WebClient).DownloadFile($dpDownloadUrl, $dpDest)
        if (Test-Path $dpDest) { Write-Log "dotPeek installed to $dpDest" }
    } else {
        Write-Log "WARNING: Could not find dotPeek download URL in JetBrains API (available keys: $($dpRelease.PSObject.Properties.Name -join ', '))"
    }
} catch { Write-Log "Failed to download dotPeek: $_" }

# Download Proxifier Portable (proxy client for tunneling traffic)
Write-Log "Downloading Proxifier Portable..."
try {
    $proxifierUrl = "https://www.proxifier.com/download/ProxifierPE.zip"
    $proxifierZip = "C:\Windows\Temp\ProxifierPE.zip"
    $proxifierDir = "C:\Tools\Proxifier"
    (New-Object System.Net.WebClient).DownloadFile($proxifierUrl, $proxifierZip)
    if (Test-Path $proxifierZip) {
        New-Item -ItemType Directory -Path $proxifierDir -Force | Out-Null
        Expand-Archive -Path $proxifierZip -DestinationPath $proxifierDir -Force
        Remove-Item $proxifierZip -Force -ErrorAction SilentlyContinue
        Write-Log "Proxifier Portable installed to $proxifierDir"
    }
} catch { Write-Log "Failed to download Proxifier: $_" }

# Auto-compile C# offensive tools (Rubeus, Seatbelt, Certify, SharpUp, etc.)
# These target .NET Framework 3.5-4.x -- retarget to 4.8 and build with MSBuild
$msbuild = Get-ChildItem "C:\Program Files (x86)\Microsoft Visual Studio" -Recurse -Filter MSBuild.exe -ErrorAction SilentlyContinue | Where-Object { $_.FullName -like "*Current*" } | Select-Object -First 1
if ($msbuild) {
    Write-Log "Auto-compiling C# tools with MSBuild..."
    $slnFiles = Get-ChildItem "C:\Tools" -Recurse -Filter "*.sln" -Depth 2 -ErrorAction SilentlyContinue
    $compiled = 0
    $failed = 0
    $skipped = 0
    # Skip non-C# solutions (C/C++ projects like mimikatz, BOF templates)
    $skipPatterns = @("mimikatz","sleepmask","bof-vs","Crystal-Kit")
    foreach ($sln in $slnFiles) {
        $toolName = $sln.Directory.Name
        if ($skipPatterns | Where-Object { $toolName -like "*$_*" }) {
            $skipped++
            Write-Log "  Skipped: $toolName (not a C# project)"
            continue
        }
        try {
            # Retarget .NET Framework 3.5-4.7 projects to 4.8 (old targeting packs unavailable)
            Get-ChildItem $sln.DirectoryName -Recurse -Filter "*.csproj" | ForEach-Object {
                $content = Get-Content $_.FullName -Raw
                if ($content -match "v[34]\.[0-7]") {
                    $content = $content -replace "v[34]\.[0-7](\.\d)?", "v4.8"
                    Set-Content -Path $_.FullName -Value $content
                }
            }
            # NuGet restore (some tools like Certify need package restore before build)
            & $msbuild.FullName $sln.FullName /t:Restore /p:Configuration=Release /verbosity:quiet /nologo 2>&1 | Out-Null
            & $msbuild.FullName $sln.FullName /p:Configuration=Release /verbosity:quiet /nologo 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                $compiled++
                # Rename output binaries to <ToolName>_DEFAULT.exe so operators know these are
                # non-evasion builds and must be modified/recompiled before use on targets
                Get-ChildItem $sln.DirectoryName -Recurse -Filter "*.exe" -ErrorAction SilentlyContinue |
                    Where-Object { $_.DirectoryName -like "*bin\Release*" } | ForEach-Object {
                        $defaultName = $_.BaseName + "_DEFAULT" + $_.Extension
                        $defaultPath = Join-Path $_.DirectoryName $defaultName
                        Copy-Item $_.FullName $defaultPath -Force
                    }
                Write-Log "  Compiled: $toolName (binaries renamed to *_DEFAULT.exe)"
            } else {
                $failed++
                Write-Log "  Failed: $toolName (MSBuild exit code $LASTEXITCODE)"
            }
        } catch {
            $failed++
            Write-Log "  Failed: $toolName ($_)"
        }
    }
    Write-Log "Auto-compile complete: $compiled succeeded, $failed failed, $skipped skipped"
} else {
    Write-Log "WARNING: MSBuild not found -- C# tools not compiled (build manually with VS Code)"
}

Write-Log "Phase 4 complete"
Write-SetupStatus -Step 4 -Name "Tools Repo" -Status "ok"

# =============================================================================
# PHASE 5: COBALT STRIKE COMMUNITY KIT (C:\CommunityTools)
# =============================================================================

Write-Log "PHASE 5: Cloning Cobalt Strike Community Kit tools..."

$CommunityBase = "C:\CommunityTools"
New-Item -ItemType Directory -Path $CommunityBase -Force | Out-Null

# Category subfolders
$categories = @("BOF", "Aggressor", "Malleable-C2", "UDRL", "External-C2", "Infrastructure", "Logging", "REST-API", "UDC2", "RDLL")
foreach ($cat in $categories) {
    New-Item -ItemType Directory -Path "$CommunityBase\$cat" -Force | Out-Null
}

# Community Kit tool definitions: Category, Owner, Name
$communityTools = @(
    # --- BOF ---
    @("BOF", "The-Z-Labs", "bof-launcher"),
    @("BOF", "trustedsec", "CS-Situational-Awareness-BOF"),
    @("BOF", "trustedsec", "CS-Remote-OPs-BOF"),
    @("BOF", "mertdas", "PrivKit"),
    @("BOF", "Meckazin", "ChromeKatz"),
    @("BOF", "CodeXTF2", "bof_template"),
    @("BOF", "CodeXTF2", "ScreenshotBOF"),
    @("BOF", "nickvourd", "COM-Hunter"),
    @("BOF", "NtDallas", "BOF_Spawn"),
    @("BOF", "Cobalt-Strike", "bof-vs"),
    @("BOF", "NtDallas", "Draugr"),
    @("BOF", "rasta-mouse", "SpawnWith"),
    @("BOF", "fortra", "No-Consolation"),
    @("BOF", "fortra", "nanodump"),
    @("BOF", "CCob", "BOF.NET"),
    @("BOF", "Mr-Un1k0d3r", "BOFCode"),
    @("BOF", "Mr-Un1k0d3r", "Cookie-and-Handle-Stealer"),
    @("BOF", "m3rcer", "Chisel-Strike"),
    @("BOF", "outflanknl", "C2-Tool-Collection"),
    @("BOF", "outflanknl", "FindObjects-BOF"),
    @("BOF", "outflanknl", "WdToggle"),
    @("BOF", "rasta-mouse", "SCMUACBypass"),
    @("BOF", "rasta-mouse", "PPEnum"),
    @("BOF", "Cobalt-Strike", "unhook-bof"),
    @("BOF", "kyleavery", "inject-assembly"),
    @("BOF", "apokryptein", "secinject"),
    @("BOF", "Yaxser", "CobaltStrike-BOF"),
    @("BOF", "crypt0p3g", "bof-collection"),
    @("BOF", "connormcgarr", "tgtdelegation"),
    @("BOF", "securifybv", "Visual-Studio-BOF-template"),
    @("BOF", "trainr3kt", "NoteThief"),
    @("BOF", "trainr3kt", "Readfile_BoF"),
    @("BOF", "trainr3kt", "MemReader_BoF"),
    @("BOF", "EspressoCake", "DLL_Version_Enumeration_BOF"),
    @("BOF", "EspressoCake", "DLL-Exports-Extraction-BOF"),
    @("BOF", "EspressoCake", "DLL-Hijack-Search-Order-BOF"),
    @("BOF", "EspressoCake", "DLL_Imports_BOF"),
    @("BOF", "Octoberfest7", "KDStab"),
    @("BOF", "Octoberfest7", "Inline-Execute-PE"),
    @("BOF", "Octoberfest7", "EventViewerUAC_BOF"),
    @("BOF", "boku7", "whereami"),
    @("BOF", "boku7", "HOLLOW"),
    @("BOF", "boku7", "injectAmsiBypass"),
    @("BOF", "boku7", "spawn"),
    @("BOF", "N4kedTurtle", "PersistBOF"),
    @("BOF", "ScriptIdiot", "BOF-patchit"),
    @("BOF", "Henkru", "cs-token-vault"),
    @("BOF", "Sh0ckFR", "InlineWhispers2"),
    @("BOF", "netero1010", "RDPHijack-BOF"),
    @("BOF", "netero1010", "ServiceMove-BOF"),
    @("BOF", "Crypt0s", "DelegationBOF"),
    @("BOF", "ceramicskate0", "BOF-Builder"),
    @("BOF", "mandiant", "msi-search"),
    @("BOF", "erberkan", "dump-hives-BOF"),
    @("BOF", "Mr-Un1k0d3r", "Elevate-System-Trusted-BOF"),
    # --- Aggressor ---
    @("Aggressor", "exfiltrata", "redshell"),
    @("Aggressor", "Cobalt-Strike", "sleep2rest"),
    @("Aggressor", "Cobalt-Strike", "callback_examples"),
    @("Aggressor", "Cobalt-Strike", "sleep_python_bridge"),
    @("Aggressor", "nickvourd", "CS-Aggressor-Kit"),
    @("Aggressor", "0xbad53c", "OffSecOps-Arsenal"),
    @("Aggressor", "RedSiege", "AggressorAssessor"),
    @("Aggressor", "harleyQu1nn", "AggressorScripts"),
    @("Aggressor", "Und3rf10w", "Aggressor-scripts"),
    @("Aggressor", "x-stp", "beacon-jukebox"),
    @("Aggressor", "CodeXTF2", "cobaltstrike-headless"),
    @("Aggressor", "mgeeky", "cobalt-arsenal"),
    @("Aggressor", "EspressoCake", "RecreateCSDownloadsTree"),
    @("Aggressor", "EspressoCake", "BeaconDownloadSync"),
    @("Aggressor", "EspressoCake", "DynamicTabRename"),
    @("Aggressor", "NVISOsecurity", "pyCobaltHound"),
    @("Aggressor", "ScriptIdiot", "BeaconNotifier-Discord"),
    @("Aggressor", "Peco602", "cobaltstrike-aggressor-scripts"),
    @("Aggressor", "outflanknl", "HelpColor"),
    @("Aggressor", "RCStep", "CSSG"),
    # --- Malleable-C2 ---
    @("Malleable-C2", "Cobalt-Strike", "Malleable-C2-Profiles"),
    @("Malleable-C2", "Tylous", "SourcePoint"),
    @("Malleable-C2", "threatexpress", "malleable-c2"),
    @("Malleable-C2", "threatexpress", "cs2modrewrite"),
    @("Malleable-C2", "threatexpress", "random_c2_profile"),
    @("Malleable-C2", "CodeXTF2", "Burp2Malleable"),
    @("Malleable-C2", "xx0hcd", "Malleable-C2-Profiles", "Malleable-C2-Profiles-xx0hcd"),
    @("Malleable-C2", "RedSiege", "C2concealer"),
    @("Malleable-C2", "vestjoe", "cobaltstrike_services"),
    # --- UDRL ---
    @("UDRL", "boku7", "BokuLoader"),
    @("UDRL", "kyleavery", "AceLdr"),
    @("UDRL", "mgeeky", "ElusiveMice"),
    @("UDRL", "CodeXTF2", "CustomC2ChannelTemplate"),
    # --- External-C2 ---
    @("External-C2", "Cobalt-Strike", "External-C2"),
    @("External-C2", "Und3rf10w", "external_c2_framework"),
    # --- Infrastructure ---
    @("Infrastructure", "mgeeky", "RedWarden"),
    # --- Logging ---
    @("Logging", "Patrick-DE", "C2-logparser"),
    # --- REST-API ---
    @("REST-API", "Cobalt-Strike", "cobaltstrike-web-client"),
    @("REST-API", "Cobalt-Strike", "cobaltstrike-mcp-server"),
    @("REST-API", "Cobalt-Strike", "py2rest"),
    # --- UDC2 ---
    @("UDC2", "Cobalt-Strike", "udc2-vs"),
    @("UDC2", "Cobalt-Strike", "icmp-udc2"),
    # --- RDLL ---
    @("RDLL", "ScriptIdiot", "SysmonQuiet")
)

$cloneSuccess = 0
$cloneFailed = 0
$cloneSkipped = 0

foreach ($tool in $communityTools) {
    $category = $tool[0]
    $owner = $tool[1]
    $name = $tool[2]
    $folderName = if ($tool.Length -ge 4) { $tool[3] } else { $name }
    $targetDir = "$CommunityBase\$category\$folderName"

    if (Test-Path $targetDir) {
        $cloneSkipped++
        continue
    }

    $repoUrl = "https://github.com/$owner/$name.git"
    try {
        $gitOutput = git clone --depth 1 $repoUrl $targetDir 2>&1
        if ($LASTEXITCODE -eq 0) {
            $cloneSuccess++
        } else {
            Write-Log "  FAILED: $category/$name - $gitOutput"
            $cloneFailed++
        }
    } catch {
        Write-Log "  ERROR: $category/$name - $_"
        $cloneFailed++
    }
}

Write-Log "Community Kit clone complete: $cloneSuccess succeeded, $cloneFailed failed, $cloneSkipped skipped"

# Create Community Tools README on desktop
@"
=== COBALT STRIKE COMMUNITY KIT ===
Location: C:\CommunityTools\

Organized by category:

BOF\                Beacon Object Files (55 tools)
  - nanodump, No-Consolation, CS-Situational-Awareness-BOF,
    CS-Remote-OPs-BOF, ChromeKatz, Inline-Execute-PE, BOF.NET,
    inject-assembly, PersistBOF, bof-launcher, and more

Aggressor\          Aggressor scripts (17 tools)
  - cobalt-arsenal, AggressorScripts, HelpColor, redshell,
    pyCobaltHound, OffSecOps-Arsenal, and more

Malleable-C2\       C2 profile generators and collections (9 tools)
  - Malleable-C2-Profiles, SourcePoint, C2concealer,
    malleable-c2 (reference guide), cs2modrewrite, and more

UDRL\               User-Defined Reflective Loaders (4 tools)
  - BokuLoader, AceLdr, ElusiveMice, CustomC2ChannelTemplate

External-C2\        External C2 specifications (2 tools)
Infrastructure\     C2 infrastructure tools (1 tool)
  - RedWarden (C2 reverse proxy)

Logging\            Log parsing tools (1 tool)
REST-API\           REST API clients (3 tools)
UDC2\               User-Defined C2 channels (2 tools)
RDLL\               Reflective DLL tools (1 tool)

Source: https://cobalt-strike.github.io/community_kit/
"@ | Out-File "$CommunityBase\README.txt" -Encoding UTF8

Write-Log "Phase 5 complete"
Write-SetupStatus -Step 5 -Name "Community Kit" -Status "ok"

# =============================================================================
# PHASE 6: INSTALL COBALT STRIKE CLIENT FROM S3
# =============================================================================

Write-Log "PHASE 6: Installing Cobalt Strike Client..."

if ($CSClientS3Path -and $CSClientS3Path -ne "") {
    Write-Log "Downloading CS Client from S3: $CSClientS3Path"
    try {
        $csArchive = "C:\Windows\Temp\cs-client-archive"
        # Parse s3://bucket/key format
        $csParts = $CSClientS3Path -replace '^s3://','' -split '/',2
        Read-S3Object -BucketName $csParts[0] -Key $csParts[1] -File $csArchive -Region $AwsRegion

        if (Test-Path $csArchive) {
            Write-Log "Downloaded CS Client, detecting format..."
            $csDir = "C:\Tools\CobaltStrike"
            New-Item -ItemType Directory -Path $csDir -Force | Out-Null

            # Detect format by magic bytes
            $fileHeader = [System.IO.File]::ReadAllBytes($csArchive)[0..3]
            $isExe = ($fileHeader[0] -eq 0x4D -and $fileHeader[1] -eq 0x5A)  # MZ header = PE executable
            $isZip = ($fileHeader[0] -eq 0x50 -and $fileHeader[1] -eq 0x4B)
            $isGzip = ($fileHeader[0] -eq 0x1F -and $fileHeader[1] -eq 0x8B)

            if ($isExe) {
                # Raw .exe -- just move it into place
                $exeName = if ($CSClientS3Path -match '([^/]+\.exe)$') { $Matches[1] } else { "cobaltstrike-client.exe" }
                $exeDest = "$csDir\$exeName"
                Move-Item -Path $csArchive -Destination $exeDest -Force
                Write-Log "CS Client is a standalone .exe: $exeDest"

                # Create desktop shortcut directly to the exe
                $WshShell = New-Object -ComObject WScript.Shell
                $Shortcut = $WshShell.CreateShortcut("C:\Users\Administrator\Desktop\Cobalt Strike Client.lnk")
                $Shortcut.TargetPath = $exeDest
                $Shortcut.WorkingDirectory = $csDir
                $Shortcut.IconLocation = "$exeDest,0"
                $Shortcut.Save()

                Write-Log "Created CS Client desktop shortcut (exe)"
                "CS_CLIENT_INSTALLED" | Out-File "$csDir\status.txt"
            } else {
                # Archive format -- extract it
                if ($isZip) {
                    Expand-Archive -Path $csArchive -DestinationPath $csDir -Force
                } elseif ($isGzip) {
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

                # Look for key CS files after extraction
                $csJar = Get-ChildItem $csDir -Recurse -Filter "cobaltstrike.jar" | Select-Object -First 1
                $updateBat = Get-ChildItem $csDir -Recurse -Filter "update.bat" | Select-Object -First 1
                $updateJar = Get-ChildItem $csDir -Recurse -Filter "update.jar" | Select-Object -First 1
                $csExe = Get-ChildItem $csDir -Recurse -Filter "cobaltstrike.exe" | Select-Object -First 1

                # Determine the CS root directory (where update.jar/bat and cobaltstrike.jar live)
                $csRoot = $csDir
                if ($csJar) { $csRoot = $csJar.DirectoryName }
                elseif ($updateBat) { $csRoot = $updateBat.DirectoryName }
                elseif ($updateJar) { $csRoot = $updateJar.DirectoryName }

                if ($csJar -or $updateBat -or $updateJar) {
                    Write-Log "CS distribution extracted to: $csRoot"

                    # Create "Update CS" desktop shortcut -- user can run this for manual license activation
                    if ($updateBat) {
                        $WshShell = New-Object -ComObject WScript.Shell
                        $UpdateShortcut = $WshShell.CreateShortcut("C:\Users\Administrator\Desktop\CS - Run Update (License Key Required).lnk")
                        $UpdateShortcut.TargetPath = $updateBat.FullName
                        $UpdateShortcut.WorkingDirectory = $csRoot
                        $UpdateShortcut.IconLocation = "C:\Windows\System32\shell32.dll,46"
                        $UpdateShortcut.Save()
                        Write-Log "Created 'Run Update' desktop shortcut (update.bat)"
                    } elseif ($updateJar) {
                        # Linux-style distribution: create a .bat wrapper for update.jar
                        $updateWrapperBat = "$csRoot\Update-CS-License.bat"
                        @"
@echo off
cd /d "$csRoot"
echo Running Cobalt Strike license update...
echo Enter your license key when prompted.
java -XX:ParallelGCThreads=4 -XX:+AggressiveHeap -XX:+UseParallelGC -jar update.jar
pause
"@ | Out-File $updateWrapperBat -Encoding ASCII

                        $WshShell = New-Object -ComObject WScript.Shell
                        $UpdateShortcut = $WshShell.CreateShortcut("C:\Users\Administrator\Desktop\CS - Run Update (License Key Required).lnk")
                        $UpdateShortcut.TargetPath = $updateWrapperBat
                        $UpdateShortcut.WorkingDirectory = $csRoot
                        $UpdateShortcut.IconLocation = "C:\Windows\System32\shell32.dll,46"
                        $UpdateShortcut.Save()
                        Write-Log "Created 'Run Update' desktop shortcut (update.jar wrapper)"
                    }

                    # Create CS Client launcher shortcut
                    # CS v4.x structure: client/cobaltstrike-client.jar is the actual client,
                    # cobaltstrike.jar in the root is the distribution package (not launchable).
                    $csClientJar = Get-ChildItem $csRoot -Recurse -Filter "cobaltstrike-client.jar" | Select-Object -First 1
                    if ($csClientJar) {
                        # Use the dedicated client jar (CS v4.x layout)
                        $clientDir = $csClientJar.DirectoryName
                        @"
@echo off
cd /d "$clientDir"
java -XX:ParallelGCThreads=4 -XX:+AggressiveHeap -XX:+UseParallelGC -jar cobaltstrike-client.jar
pause
"@ | Out-File "$csDir\Launch-CS-Client.bat" -Encoding ASCII
                        Write-Log "CS Client launcher targets client/cobaltstrike-client.jar"

                        $WshShell = New-Object -ComObject WScript.Shell
                        $Shortcut = $WshShell.CreateShortcut("C:\Users\Administrator\Desktop\Cobalt Strike Client.lnk")
                        $Shortcut.TargetPath = "$csDir\Launch-CS-Client.bat"
                        $Shortcut.WorkingDirectory = $clientDir
                    } elseif ($csJar) {
                        # Fallback: older CS layout where cobaltstrike.jar is the client
                        @"
@echo off
cd /d "$csRoot"
java -XX:ParallelGCThreads=4 -XX:+AggressiveHeap -XX:+UseParallelGC -jar cobaltstrike.jar
pause
"@ | Out-File "$csDir\Launch-CS-Client.bat" -Encoding ASCII

                        $WshShell = New-Object -ComObject WScript.Shell
                        $Shortcut = $WshShell.CreateShortcut("C:\Users\Administrator\Desktop\Cobalt Strike Client.lnk")
                        $Shortcut.TargetPath = "$csDir\Launch-CS-Client.bat"
                        $Shortcut.WorkingDirectory = $csRoot
                        $Shortcut.IconLocation = "C:\Windows\System32\shell32.dll,13"
                        $Shortcut.Save()
                        Write-Log "Created CS Client launcher shortcut (jar)"
                    } elseif ($csExe) {
                        $WshShell = New-Object -ComObject WScript.Shell
                        $Shortcut = $WshShell.CreateShortcut("C:\Users\Administrator\Desktop\Cobalt Strike Client.lnk")
                        $Shortcut.TargetPath = $csExe.FullName
                        $Shortcut.WorkingDirectory = $csExe.DirectoryName
                        $Shortcut.IconLocation = "$($csExe.FullName),0"
                        $Shortcut.Save()
                        Write-Log "Created CS Client launcher shortcut (exe)"
                    }

                    "CS_CLIENT_EXTRACTED" | Out-File "$csDir\status.txt"
                    Write-Log "CS Client files extracted successfully"
                } else {
                    Write-Log "WARNING: No cobaltstrike.jar, update.bat, or update.jar found after extraction"
                }
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

# Automated CS Client license activation via Secrets Manager
# Same pattern as team server: secret NAME in script, VALUE fetched at runtime
# Handles both Windows (update.bat) and Linux (update.jar) CS distributions
$csDir = "C:\Tools\CobaltStrike"
$updateBatPath = Get-ChildItem $csDir -Recurse -Filter "update.bat" -ErrorAction SilentlyContinue | Select-Object -First 1
$updateJarPath = Get-ChildItem $csDir -Recurse -Filter "update.jar" -ErrorAction SilentlyContinue | Select-Object -First 1
$hasUpdateMethod = ($updateBatPath -or $updateJarPath)

if ($hasUpdateMethod -and $CSLicenseSecretName -and $CSLicenseSecretName -ne "") {
    Write-Log "Fetching CS license key from AWS Secrets Manager for client activation..."
    # Retry loop: IAM instance profile credentials can take 10-30s to propagate after launch.
    # The bootstrap script runs at first boot, often before IMDS credentials are available.
    $csLicenseKey = $null
    for ($attempt = 1; $attempt -le 7; $attempt++) {
        try {
            $csLicenseKey = (Get-SECSecretValue -SecretId $CSLicenseSecretName -Region $AwsRegion -ErrorAction Stop).SecretString
            if ($csLicenseKey) {
                Write-Log "License key retrieved from Secrets Manager (attempt $attempt/7)"
                break
            }
        } catch {
            Write-Log "Waiting for IAM credentials to propagate... (attempt $attempt/7)"
            $csLicenseKey = $null
            Start-Sleep -Seconds 45
        }
    }
    try {
        if ($csLicenseKey) {
            # Determine CS root and update method
            if ($updateBatPath) {
                $csRoot = $updateBatPath.DirectoryName
                Write-Log "Running update.bat in $csRoot for license activation..."
            } else {
                $csRoot = $updateJarPath.DirectoryName
                Write-Log "Running update.jar in $csRoot for license activation (Linux-style CS distribution)..."
            }

            # Run the update with license key piped to stdin
            $updateProcess = New-Object System.Diagnostics.Process
            $updateProcess.StartInfo.UseShellExecute = $false
            $updateProcess.StartInfo.RedirectStandardInput = $true
            $updateProcess.StartInfo.RedirectStandardOutput = $true
            $updateProcess.StartInfo.RedirectStandardError = $true
            $updateProcess.StartInfo.CreateNoWindow = $true
            $updateProcess.StartInfo.WorkingDirectory = $csRoot

            if ($updateBatPath) {
                $updateProcess.StartInfo.FileName = "cmd.exe"
                $updateProcess.StartInfo.Arguments = "/c update.bat"
            } else {
                # Linux distribution: call java -jar update.jar directly
                $updateProcess.StartInfo.FileName = "java"
                $updateProcess.StartInfo.Arguments = "-XX:ParallelGCThreads=4 -XX:+AggressiveHeap -XX:+UseParallelGC -jar update.jar"
            }

            $updateProcess.Start() | Out-Null

            # Write the license key to stdin (update.jar prompts for it)
            $updateProcess.StandardInput.WriteLine($csLicenseKey)
            $updateProcess.StandardInput.Close()

            $updateProcess.WaitForExit(180000)  # 3 minute timeout (downloads licensed binaries)

            $exitCode = $updateProcess.ExitCode
            $updateOutput = $updateProcess.StandardOutput.ReadToEnd()
            $updateErrors = $updateProcess.StandardError.ReadToEnd()

            # Log non-sensitive lines only (filter out anything that might contain the key)
            ($updateOutput + "`n" + $updateErrors) -split "`n" | Where-Object {
                $_ -match "(?i)(error|fail|success|complete|download|install|update|version|connect|http)" -and
                $_ -notmatch $csLicenseKey
            } | ForEach-Object {
                Write-Log "  update: $_"
            }

            if ($exitCode -eq 0) {
                Write-Log "CS Client license activation completed (exit code 0)"
            } else {
                Write-Log "WARNING: Update exited with code $exitCode"
            }

            # Check if auth files were created
            # CS v4.x creates: client/cobaltstrike.auth.client, server/cobaltstrike.auth.server
            # Older CS creates: cobaltstrike.auth in root
            $authFile = Get-ChildItem $csRoot -Recurse -Filter "cobaltstrike.auth" -ErrorAction SilentlyContinue | Select-Object -First 1
            $authClientFile = Get-ChildItem $csRoot -Recurse -Filter "cobaltstrike.auth.client" -ErrorAction SilentlyContinue | Select-Object -First 1
            $authServerFile = Get-ChildItem $csRoot -Recurse -Filter "cobaltstrike.auth.server" -ErrorAction SilentlyContinue | Select-Object -First 1

            if ($authFile -or $authClientFile -or $authServerFile) {
                Write-Log "CS Client license: ACTIVATED (auth file created)"
                "CS_CLIENT_ACTIVATED" | Out-File "$csDir\status.txt"
                $csLicenseStatus = "activated"
            } else {
                Write-Log "WARNING: Update completed but no auth file found -- may need manual activation"
                Write-Log "Check output above for errors. Common issues: invalid key, no internet, firewall blocking"
                $csLicenseStatus = "activation_failed"
            }

            # OPSEC: Clear license key from memory immediately
            $csLicenseKey = $null
            [System.GC]::Collect()
            Write-Log "CS license key cleared from memory (OPSEC)"
        } else {
            Write-Log "WARNING: Failed to retrieve CS license key from Secrets Manager after 7 attempts"
            $csLicenseStatus = "secret_fetch_failed"
        }
    } catch {
        Write-Log "WARNING: CS Client activation failed: $($_.Exception.Message)"
        Write-Log "Manual activation: run 'java -jar update.jar' in $csDir\cobaltstrike"
        $csLicenseStatus = "error"
    }
} elseif ($hasUpdateMethod -and (-not $CSLicenseSecretName -or $CSLicenseSecretName -eq "")) {
    Write-Log "No CS license secret configured -- manual activation required"
    Write-Log "Run: cd C:\Tools\CobaltStrike\cobaltstrike && java -jar update.jar"
    $csLicenseStatus = "not_configured"
} else {
    $csLicenseStatus = "no_update_method"
}

# After activation, update.jar creates client/cobaltstrike-client.jar -- regenerate launcher
$csClientJarPost = Get-ChildItem $csDir -Recurse -Filter "cobaltstrike-client.jar" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($csClientJarPost) {
    $clientDir = $csClientJarPost.DirectoryName
    @"
@echo off
cd /d "$clientDir"
java -XX:ParallelGCThreads=4 -XX:+AggressiveHeap -XX:+UseParallelGC -jar cobaltstrike-client.jar
pause
"@ | Out-File "$csDir\Launch-CS-Client.bat" -Encoding ASCII
    Write-Log "CS Client launcher updated to use client/cobaltstrike-client.jar (post-activation)"
}

Write-Log "Phase 6 complete (license: $csLicenseStatus)"
if ($csLicenseStatus -eq "activated") {
    Write-SetupStatus -Step 6 -Name "CS Client" -Status "ok" -Message "License activated via Secrets Manager"
} elseif ($csLicenseStatus -eq "not_configured" -or $csLicenseStatus -eq "no_update_method") {
    Write-SetupStatus -Step 6 -Name "CS Client" -Status "ok" -Message "Installed (license: $csLicenseStatus)"
} else {
    Write-SetupStatus -Step 6 -Name "CS Client" -Status "warning" -Message "License $csLicenseStatus -- manual activation required"
}

# =============================================================================
# PHASE 7: WSL2 SETUP WITH UBUNTU
# =============================================================================

Write-Log "PHASE 7: Setting up WSL (feature enable -- Ubuntu installs after reboot)..."

try {
    # Enable WSL feature (requires reboot to take effect)
    Write-Log "Enabling WSL Windows feature..."
    dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart 2>&1 | Out-Null

    # Enable Virtual Machine Platform (requires reboot to take effect)
    Write-Log "Enabling Virtual Machine Platform..."
    dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart 2>&1 | Out-Null

    # NOTE: wsl --set-default-version and wsl --install CANNOT run until after reboot.
    # DISM feature enable is pending until reboot. Any wsl.exe commands will fail with
    # WSL_E_WSL_OPTIONAL_COMPONENT_REQUIRED.
    Write-Log "WSL features enabled (reboot required before Ubuntu can be installed)"

    # Stage Ubuntu rootfs so operator can finish import in one command after RDP login.
    # Auto-install via SYSTEM/SSM fails on Windows Server 2022 (no Microsoft Store, and
    # Add-AppxPackage rejects SYSTEM context). Operator must run wsl --import manually
    # from their interactive RDP session.
    Write-Log "Staging Ubuntu rootfs for manual import..."
    try {
        $bundle = "C:\Windows\Temp\ubuntu_bundle.zip"
        $extractDir = "C:\Windows\Temp\wsl_bundle"
        $appxZip = "C:\Windows\Temp\ubuntu_x64.zip"
        $rootfsDir = "C:\Windows\Temp\ubuntu_x64"
        if (-not (Test-Path "$rootfsDir\install.tar.gz")) {
            (New-Object System.Net.WebClient).DownloadFile("https://wslstorestorage.blob.core.windows.net/wslblob/Ubuntu2204-221101.AppxBundle", $bundle)
            Expand-Archive -Path $bundle -DestinationPath $extractDir -Force
            Copy-Item "$extractDir\Ubuntu_2204.1.7.0_x64.appx" $appxZip -Force
            Expand-Archive -Path $appxZip -DestinationPath $rootfsDir -Force
            Remove-Item $bundle, $extractDir, $appxZip -Recurse -Force -ErrorAction SilentlyContinue
            Write-Log "Ubuntu rootfs staged: $rootfsDir\install.tar.gz ($((Get-Item "$rootfsDir\install.tar.gz").Length) bytes)"
        } else {
            Write-Log "Ubuntu rootfs already staged at $rootfsDir\install.tar.gz"
        }
    } catch {
        Write-Log "WARNING: Failed to stage Ubuntu rootfs: $_"
    }
} catch {
    Write-Log "WSL feature enable failed: $_"
}

Write-Log "Phase 7 complete"
Write-SetupStatus -Step 7 -Name "WSL Setup" -Status "ok" -Message "Features enabled, Ubuntu installs after reboot"

# =============================================================================
# PHASE 7b: CONFIGURE WINDOWS TERMINAL PROFILES
# =============================================================================
# Pre-seed settings.json with useful profiles: PowerShell, CMD, WSL Ubuntu,
# and SSH to team server. Windows Terminal reads this on first launch.

Write-Log "PHASE 7b: Configuring Windows Terminal profiles..."
try {
    # Find the portable WT install directory (created in Phase 3)
    $wtExeSearch = Get-ChildItem "C:\Program Files\WindowsTerminal" -Recurse -Filter "wt.exe" -ErrorAction SilentlyContinue | Select-Object -First 1

    if ($wtExeSearch) {
        $wtDir = $wtExeSearch.DirectoryName

        # Build profiles list using PowerShell objects (avoids here-string escaping issues)
        $profileList = @(
            @{
                guid = "{574e775e-4f2a-5b96-ac1e-a2962a402336}"
                name = "PowerShell"
                commandline = "powershell.exe"
                colorScheme = "Campbell Powershell"
                startingDirectory = "C:\Tools"
                hidden = $false
            },
            @{
                guid = "{0caa0dad-35be-5f56-a8ff-afceeeaa6101}"
                name = "Command Prompt"
                commandline = "cmd.exe"
                colorScheme = "Campbell"
                startingDirectory = "C:\Tools"
                hidden = $false
            },
            @{
                # WT portable mode can't resolve wsl.exe directly -- launch via powershell wrapper
                name = "WSL Ubuntu"
                commandline = "powershell.exe -NoProfile -Command wsl.exe -d Ubuntu"
                icon = "ms-appx:///ProfileIcons/{9acb9455-ca41-5af7-950f-6bca1bc9722f}.png"
                colorScheme = "One Half Dark"
                startingDirectory = "~"
                tabTitle = "Ubuntu"
            }
        )

        # Add Team Server SSH profile if C2 server IP is set
        if ($C2ServerIP -and $C2ServerIP -ne "") {
            if ($EnableKeyExchange -eq "true") {
                $sshCmd = "ssh -i C:\Users\Administrator\.ssh\attackbox_internal_key ubuntu@$C2ServerIP"
            } elseif (Test-Path "C:\Users\Administrator\.ssh\id_ed25519") {
                $sshCmd = "ssh -i C:\Users\Administrator\.ssh\id_ed25519 ubuntu@$C2ServerIP"
            } else {
                $sshCmd = "ssh ubuntu@$C2ServerIP"
            }
            $profileList += @{
                name = "Team Server (SSH)"
                commandline = $sshCmd
                colorScheme = "One Half Dark"
                startingDirectory = "C:\Tools\CobaltStrike"
                tabTitle = "Team Server"
            }
        }

        $wtSettings = @{
            "`$schema" = "https://aka.ms/terminal-profiles-schema"
            defaultProfile = "{574e775e-4f2a-5b96-ac1e-a2962a402336}"
            profiles = @{
                defaults = @{
                    fontFace = "Consolas"
                    fontSize = 11
                    cursorShape = "filledBox"
                }
                list = $profileList
            }
            schemes = @()
            actions = @(
                @{ command = @{ action = "copy"; singleLine = $false }; keys = "ctrl+c" }
                @{ command = "paste"; keys = "ctrl+v" }
                @{ command = "find"; keys = "ctrl+shift+f" }
                @{ command = @{ action = "splitPane"; split = "auto" }; keys = "alt+shift+d" }
            )
        } | ConvertTo-Json -Depth 5

        # Write settings.json to the portable WT settings subdirectory (where WT actually reads from)
        # Create the settings subdirectory if it doesn't exist (WT only creates it on first launch)
        $wtSettingsDir = "$wtDir\settings"
        if (-not (Test-Path $wtSettingsDir)) {
            New-Item -ItemType Directory -Path $wtSettingsDir -Force | Out-Null
        }
        [System.IO.File]::WriteAllText("$wtSettingsDir\settings.json", $wtSettings)
        Write-Log "Windows Terminal settings written to: $wtSettingsDir\settings.json"
        # Also write to root dir as fallback for older WT versions
        [System.IO.File]::WriteAllText("$wtDir\settings.json", $wtSettings)
        Write-Log "Windows Terminal profiles configured (PowerShell, CMD, WSL Ubuntu, Team Server SSH)"
    } else {
        Write-Log "WARNING: Windows Terminal not found in C:\Program Files\WindowsTerminal -- skipping profile config"
    }
} catch {
    Write-Log "WARNING: Failed to configure Windows Terminal profiles: $($_.Exception.Message)"
}
Write-SetupStatus -Step 8 -Name "Terminal Config" -Status "ok"

# =============================================================================
# PHASE 8: SSH KEY EXCHANGE (GOAD deployments only)
# =============================================================================

if ($EnableKeyExchange -eq "true" -and $DeploymentBucket) {
    Write-Log "PHASE 8: SSH key exchange enabled (GOAD mode)..."

    # Download jumpbox public key from S3
    Write-Log "Waiting for jumpbox public key from S3..."
    for ($i=1; $i -le 60; $i++) {
        try {
            Read-S3Object -BucketName $DeploymentBucket -Key "$S3KeyPrefix/jumpbox_internal.pub" -File "C:\Windows\Temp\jumpbox.pub" -Region $AwsRegion
            if (Test-Path "C:\Windows\Temp\jumpbox.pub") {
                Write-Log "Downloaded jumpbox public key"
                $sshDir = "C:\ProgramData\ssh"
                $authKeysFile = "$sshDir\administrators_authorized_keys"
                # APPEND jumpbox key -- do NOT overwrite (bootstrap already added user's key)
                $jumpboxKey = (Get-Content "C:\Windows\Temp\jumpbox.pub" -Raw).Trim()
                if (Test-Path $authKeysFile) {
                    $existing = (Get-Content $authKeysFile -Raw).TrimEnd()
                    [System.IO.File]::WriteAllText($authKeysFile, "$existing`n$jumpboxKey`n")
                } else {
                    [System.IO.File]::WriteAllText($authKeysFile, "$jumpboxKey`n")
                }
                icacls $authKeysFile /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F" 2>&1 | Out-Null
                Remove-Item "C:\Windows\Temp\jumpbox.pub" -Force -ErrorAction SilentlyContinue
                Write-Log "Jumpbox key appended to authorized_keys (user key preserved)"
                break
            }
        } catch { Write-Log "Key download attempt $i failed: $_" }
        Start-Sleep -Seconds 10
    }

    # Generate attack box SSH key and upload public key to S3
    Write-Log "Generating SSH key for outbound connections..."
    $sshKeyPath = "C:\Users\Administrator\.ssh\attackbox_internal_key"
    if (-not (Test-Path $sshKeyPath)) {
        # Windows ssh-keygen hangs with -N "" -- use stdin pipe instead
        cmd /c "echo. | ssh-keygen -t ed25519 -f `"$sshKeyPath`" -q -C attackbox-$Hostname" 2>&1 | Out-Null
        if (Test-Path $sshKeyPath) {
            Write-Log "SSH key pair generated"
            icacls $sshKeyPath /inheritance:r /grant:r "$env:USERNAME`:F" 2>&1 | Out-Null

            # Upload public key to S3
            for ($i=1; $i -le 10; $i++) {
                try {
                    Write-S3Object -BucketName $DeploymentBucket -Key "$S3KeyPrefix/attackbox_internal.pub" -File "$sshKeyPath.pub" -Region $AwsRegion
                    Write-Log "Attack box public key uploaded to S3"
                    break
                } catch { Start-Sleep -Seconds 5 }
            }
        }
    }

    Write-Log "Phase 8 complete (GOAD key exchange)"
} else {
    Write-Log "PHASE 8: C2/combined mode - generating SSH key for team server access..."

    # Generate a dedicated key pair for attack box -> team server SSH
    # Upload public key to S3 so team server can add it to authorized_keys
    if ($DeploymentBucket) {
        $sshKeyPath = "C:\Users\Administrator\.ssh\id_ed25519"
        if (-not (Test-Path $sshKeyPath)) {
            Write-Log "Generating ed25519 key pair..."
            # Windows ssh-keygen hangs with -N "" -- use stdin pipe instead
            cmd /c "echo. | ssh-keygen -t ed25519 -f `"$sshKeyPath`" -q -C attackbox-$Hostname" 2>&1 | Out-Null

            if (Test-Path $sshKeyPath) {
                Write-Log "SSH key pair generated"
                # Fix permissions using cmd /c to avoid PowerShell parenthesis issue
                cmd /c "icacls `"$sshKeyPath`" /inheritance:r /remove Users /remove `"Authenticated Users`" /remove SYSTEM /grant Administrator:(R)" 2>&1 | Out-Null
                Write-Log "SSH key permissions set"

                # Upload public key to S3 for team server to pick up
                for ($i=1; $i -le 10; $i++) {
                    try {
                        $s3Key = if ($S3KeyPrefix) { "$S3KeyPrefix/attackbox_internal.pub" } else { "$DeploymentId/ssh-keys/attackbox_internal.pub" }
                        Write-S3Object -BucketName $DeploymentBucket -Key $s3Key -File "$sshKeyPath.pub" -Region $AwsRegion
                        Write-Log "Attack box public key uploaded to S3"
                        break
                    } catch {
                        Write-Log "S3 upload attempt $i failed: $_"
                        Start-Sleep -Seconds 5
                    }
                }
            } else {
                Write-Log "ERROR: Failed to generate SSH key"
            }
        }
    }

    Write-Log "Phase 8 complete (C2 mode key generation)"
}

# =============================================================================
# PHASE 9: SSH CONFIG & DESKTOP SHORTCUTS
# =============================================================================

Write-Log "PHASE 9: Creating SSH config and desktop shortcuts..."

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

    # Add identity file -- use GOAD internal key or user's deployment key
    if ($EnableKeyExchange -eq "true") {
        $sshConfig += "`n    IdentityFile C:\Users\Administrator\.ssh\attackbox_internal_key"
    } elseif (Test-Path "C:\Users\Administrator\.ssh\id_ed25519") {
        $sshConfig += "`n    IdentityFile C:\Users\Administrator\.ssh\id_ed25519"
    }

    [System.IO.File]::WriteAllText($sshConfigPath, $sshConfig)
    Write-Log "SSH config created for C2 server at $C2ServerIP"
}

# Create desktop info file with connection details
$infoContent = @"
=== ATTACK BOX CONNECTION INFO ===
Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')

HOSTNAME:       $Hostname
C2 SERVER:      $C2ServerIP`:$C2ServerPort

FOLDER LAYOUT:
  C:\Tools\                Red team tools (GitHub repo)
  C:\Tools\CobaltStrike\   CS Client installation
  C:\CommunityTools\       Cobalt Strike Community Kit (100+ tools)
  C:\Payloads\             Payload staging area

TOOLS INSTALLED (C:\Tools):
  - 40 red team tool repos (git submodules from tools repo)
    AD: ADSearch, BloodHound, Certify, ForgeCert, Rubeus, Whisker, SharpADWS,
        StandIn, PowerUpSQL, SQLRecon, DRSAT
    PostEx: mimikatz, Seatbelt, SharpDPAPI, SharpUp, SharpView, SharpWMI,
            PowerSploit, SweetPotato, SharpSystemTriggers, SCShell
    BOFs: CS-Remote-OPs-BOF, CS-Situational-Awareness-BOF, Kerbeus-BOF,
          SQL-BOF, Crystal-Kit, sleepmask-vs
    Evasion: Invoke-Obfuscation, GadgetToJScript, PackMyPayload, DLL-Template,
             ThreatCheck, ysoserial.net, WDACTools
    Other: Misc-Powershell-Scripts, protections-artifacts, ghidra, hashcat,
           HeidiSQL, ligolo-ng
  - SysinternalsSuite (auto-downloaded)
  - dotPeek64.exe (auto-downloaded)
  - Proxifier Portable (auto-downloaded)
  - Cobalt Strike Client (if S3 path provided)

SOFTWARE INSTALLED:
  - Git, Python 3, Java 17, 7-Zip
  - AWS CLI, Windows Terminal
  - VS Build Tools 2022 + .NET Framework 4.8 Dev Pack (MSBuild for C# tools)
  - VS Code (lightweight editor for source code)
  - WSL with Ubuntu (auto-installed on first RDP login via RunOnce)

AUTO-COMPILED C# TOOLS:
  C# tools (Rubeus, Seatbelt, Certify, SharpUp, etc.) are auto-compiled
  during deployment. Binaries are in each tool's bin\Release\ folder.

  *** IMPORTANT: These are DEFAULT builds (non-evasion, unobfuscated). ***
  They WILL be detected by AV/EDR on targets.
  For operational use, modify source and recompile before deployment:
    1. Open the .sln in VS Code
    2. Rename classes, change strings, strip metadata
    3. Rebuild: MSBuild <tool>.sln /p:Configuration=Release

CS CLIENT:
  Double-click "Cobalt Strike Client" on Desktop
  Connect to: $C2ServerIP`:$C2ServerPort

SECURITY NOTES:
  - Windows Defender: RUNNING (exclusions mode for ThreatCheck compatibility)
      Excluded paths: C:\Tools, C:\Payloads, C:\CommunityTools, C:\Tools\CobaltStrike
      Cloud submission: DISABLED (OPSEC)
      Defender ATP (Sense): DISABLED
  - Windows Firewall: RDP + SSH allowed
  - This box has NO public IP (private subnet only)
"@

$infoContent | Out-File "C:\Users\Administrator\Desktop\ATTACK-BOX-INFO.txt" -Encoding UTF8

# CS Listener Configuration Guide
if ($PrimaryDomain) {
    $C2Fqdn = "$C2Subdomain.$PrimaryDomain"
    $guideContent = @"
===============================================================
 COBALT STRIKE LISTENER CONFIGURATION GUIDE
 Auto-generated during deployment - $(Get-Date -Format 'yyyy-MM-dd')
===============================================================

DOMAIN:           $C2Fqdn
TEAM SERVER:      $C2ServerIP`:$C2ServerPort
CS CLIENT:        localhost:50050 (via SSH tunnel from bastion)
MALLEABLE C2:     $MalleableProfile

---------------------------------------------------------------
 HTTPS LISTENER SETUP (Recommended)
---------------------------------------------------------------
 1. Open Cobalt Strike > Listeners > Add
 2. Configure:

    Name:           HTTPS
    Payload:        Beacon HTTPS
    HTTPS Host:     $C2Fqdn
    HTTPS Port:     443
    HTTPS Hosts:    $C2Fqdn
    Profile:        $MalleableProfile

 NOTE: Use the DOMAIN NAME, not redirector IPs.
       Route 53 round-robins across all redirectors.
       Let's Encrypt cert on redirectors matches the domain.

---------------------------------------------------------------
 HTTP LISTENER SETUP (Fallback)
---------------------------------------------------------------
    Name:           HTTP
    Payload:        Beacon HTTP
    HTTP Host:      $C2Fqdn
    HTTP Port:      80

---------------------------------------------------------------
 DNS LISTENER SETUP (Optional)
---------------------------------------------------------------
    Name:           DNS
    Payload:        Beacon DNS
    DNS Host:       $C2Fqdn
    DNS Port:       53

---------------------------------------------------------------
 SSL CHAIN
---------------------------------------------------------------
 Target <--HTTPS (Let's Encrypt)--> Redirector <--HTTPS (internal)--> Team Server

 The redirector handles SSL termination with a trusted Let's Encrypt
 certificate. No certificate configuration needed in Cobalt Strike.

---------------------------------------------------------------
 TRAFFIC FLOW
---------------------------------------------------------------
 Beacon callback:
   Target -> $C2Fqdn (DNS lookup) -> Redirector EIP -> nginx -> Team Server

 Operator access (from your laptop):
   ssh -L 50050:$C2ServerIP`:50050 ubuntu@bastion_eip
   Then open CS Client -> Connect to localhost:50050

===============================================================
"@
} else {
    $guideContent = @"
===============================================================
 COBALT STRIKE LISTENER CONFIGURATION GUIDE
===============================================================

 No domain configured for this deployment.

 To use HTTPS listeners with domain-based C2:
   1. Set 'primary_domain_name' in your deployment configuration
   2. Redeploy - this guide will auto-populate with your domain
      and listener settings

 For now, connect CS Client to: $C2ServerIP`:$C2ServerPort

===============================================================
"@
}
$guideContent | Out-File "C:\Users\Administrator\Desktop\CS-LISTENER-GUIDE.txt" -Encoding UTF8
Write-Log "CS Listener Guide created on Desktop"

# Create Payloads shortcut on desktop
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("C:\Users\Administrator\Desktop\Payloads.lnk")
$Shortcut.TargetPath = "C:\Payloads"
$Shortcut.Save()

# Create Tools shortcut on desktop
$Shortcut = $WshShell.CreateShortcut("C:\Users\Administrator\Desktop\Tools.lnk")
$Shortcut.TargetPath = "C:\Tools"
$Shortcut.Save()

# Create Community Tools shortcut on desktop
$Shortcut = $WshShell.CreateShortcut("C:\Users\Administrator\Desktop\Community Tools.lnk")
$Shortcut.TargetPath = "C:\CommunityTools"
$Shortcut.Save()

Write-Log "Phase 9 complete"
Write-SetupStatus -Step 9 -Name "SSH Config & Shortcuts" -Status "ok"

# =============================================================================
# DONE
# =============================================================================

Write-Log "=== Attack Box Init Completed Successfully ==="
Write-Log "Folders: C:\Tools (repo), C:\CommunityTools (community kit), C:\Payloads (staging), C:\Tools\CobaltStrike (client)"

# Mark completion
"INIT_COMPLETE" | Out-File "C:\Users\Administrator\Desktop\Deployment-Logs-Scripts\init_status.txt"

# Upload bootstrap status to S3 (so the deployment UI can track completion)
try {
    $imdsToken2 = Invoke-RestMethod -Uri "http://169.254.169.254/latest/api/token" -Method PUT -Headers @{"X-aws-ec2-metadata-token-ttl-seconds"="60"} -TimeoutSec 5
    $InstanceId = Invoke-RestMethod -Uri "http://169.254.169.254/latest/meta-data/instance-id" -Headers @{"X-aws-ec2-metadata-token"=$imdsToken2} -TimeoutSec 5
    if (-not $InstanceId) { $InstanceId = "unknown" }
    if ($DeploymentBucket) {
        $StatusJson = @{status="complete"; instance_id=$InstanceId; role="attackbox"; timestamp=(Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")} | ConvertTo-Json -Compress
        $TempFile = "$env:TEMP\bootstrap_status.json"
        $StatusJson | Out-File -FilePath $TempFile -Encoding UTF8
        Write-S3Object -BucketName $DeploymentBucket -Key "status/$InstanceId-attackbox.json" -File $TempFile -Region $AwsRegion
        Remove-Item $TempFile -Force -ErrorAction SilentlyContinue
        Write-Log "Bootstrap status uploaded to S3"
    }
} catch {
    Write-Log "WARNING: Failed to upload bootstrap status to S3 (non-fatal): $_"
}

# =============================================================================
# POST-REBOOT: WSL Ubuntu Installation via RunOnce
# =============================================================================
# DISM enabled WSL + VirtualMachinePlatform features above, but they require a
# reboot before wsl.exe commands work. This creates a RunOnce script that runs
# on next boot (as SYSTEM) to install Ubuntu for WSL.

Write-Log "Creating post-reboot WSL setup script..."

$postRebootScript = @'
# Post-reboot: Import Ubuntu rootfs into WSL
# Runs once via HKLM RunOnce on next interactive logon (executes AS the logging-in user,
# typically Administrator via RDP). HKLM RunOnce runs in user context, not SYSTEM,
# which is critical because WSL --import requires a real user profile.
#
# We use wsl --import (not wsl --install -d Ubuntu) because Windows Server 2022 has
# no Microsoft Store, so --install always fails with 0x8000ffff. The init script
# pre-staged the Ubuntu rootfs at C:\Windows\Temp\ubuntu_x64\install.tar.gz.
$logFile = "C:\Users\Administrator\Desktop\Deployment-Logs-Scripts\post-reboot-wsl.log"
Start-Transcript -Path $logFile -Append
Write-Output "Post-reboot WSL setup started: $(Get-Date)"
Write-Output "Running as: $env:USERNAME"

try {
    $rootfs = "C:\Windows\Temp\ubuntu_x64\install.tar.gz"
    if (-not (Test-Path $rootfs)) {
        Write-Output "ERROR: Rootfs not found at $rootfs -- staging step failed during init"
        Stop-Transcript
        exit 1
    }

    Write-Output "Setting WSL default version to 1 (EC2 lacks nested virt for WSL2)..."
    wsl --set-default-version 1 2>&1

    Write-Output "Importing Ubuntu rootfs into WSL..."
    New-Item -ItemType Directory -Path C:\WSL\Ubuntu -Force | Out-Null
    wsl --import Ubuntu C:\WSL\Ubuntu $rootfs 2>&1

    Write-Output "Verifying installation..."
    $wslList = wsl --list --verbose 2>&1 | Out-String
    Write-Output $wslList

    # Clean up staged rootfs (~530 MB)
    Remove-Item $rootfs -Force -ErrorAction SilentlyContinue
    Remove-Item C:\Windows\Temp\ubuntu_x64 -Recurse -Force -ErrorAction SilentlyContinue
    Write-Output "Cleaned up staged rootfs"

    Write-Output "Ubuntu WSL distro imported successfully"
    Write-Output "Windows Terminal WSL Ubuntu profile (commandline: powershell wsl.exe -d Ubuntu) will work after WT restart"

    # Update setup-status.json so the dashboard reflects the post-reboot Ubuntu install
    $statusFile = "C:\ProgramData\setup-status.json"
    if (Test-Path $statusFile) {
        try {
            $status = Get-Content $statusFile -Raw | ConvertFrom-Json
            $wslStep = $status.steps | Where-Object { $_.step -eq 7 }
            if ($wslStep) {
                $wslStep.message = "Features enabled, Ubuntu imported successfully (post-reboot)"
            }
            $status | ConvertTo-Json -Depth 3 | Out-File $statusFile -Encoding UTF8
            Write-Output "Updated setup-status.json with WSL post-reboot success"
        } catch {
            Write-Output "WARNING: Failed to update setup-status.json: $_"
        }
    }
} catch {
    Write-Output "WSL Ubuntu import failed: $_"
    # Mark step as warning in setup-status.json
    $statusFile = "C:\ProgramData\setup-status.json"
    if (Test-Path $statusFile) {
        try {
            $status = Get-Content $statusFile -Raw | ConvertFrom-Json
            $wslStep = $status.steps | Where-Object { $_.step -eq 7 }
            if ($wslStep) {
                $wslStep.status = "warning"
                $wslStep.message = "Ubuntu import failed post-reboot: $($_.Exception.Message)"
            }
            $status.warnings = ($status.steps | Where-Object { $_.status -eq "warning" }).Count
            $status | ConvertTo-Json -Depth 3 | Out-File $statusFile -Encoding UTF8
        } catch {}
    }
}

Stop-Transcript
'@

$postRebootScript | Out-File "C:\ProgramData\post-reboot-wsl-setup.ps1" -Encoding UTF8
Write-Log "Post-reboot script written to C:\ProgramData\post-reboot-wsl-setup.ps1"

# Register RunOnce (runs as SYSTEM on next boot, before any user logon)
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce" `
    -Name "PostRebootWSLSetup" `
    -Value 'powershell.exe -ExecutionPolicy Bypass -File "C:\ProgramData\post-reboot-wsl-setup.ps1"'
Write-Log "RunOnce registry key set for post-reboot WSL Ubuntu install"

# =============================================================================
# AUTO-REBOOT (required for WSL features + hostname change)
# =============================================================================
Write-Log "Scheduling reboot in 30 seconds for WSL finalization + hostname change..."
Write-Log "Post-reboot: Ubuntu will be installed via RunOnce script"
shutdown /r /t 30 /c "Attack Box setup complete - rebooting for WSL and hostname change"
