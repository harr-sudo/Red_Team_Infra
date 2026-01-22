<powershell>
# Windows Server 2022 Attack Box Init - Optimized for Red Team Operations
$ErrorActionPreference = "Continue"

# Create deployment logs folder on Desktop
$DeploymentLogsDir = "C:\Users\Administrator\Desktop\Deployment-Logs-Scripts"
New-Item -ItemType Directory -Path $DeploymentLogsDir -Force | Out-Null

$LogFile = "$DeploymentLogsDir\attackbox-init.log"
$ScriptsDir = $DeploymentLogsDir

function Write-Log { param([string]$Message); "$(Get-Date -Format 'HH:mm:ss') - $Message" | Out-File -Append $LogFile; Write-Host $Message }

Write-Log "=== Windows Server 2022 Attack Box Init Started ==="
Write-Log "Deployment logs and scripts will be stored in: $DeploymentLogsDir"

$TeamServerIP = "${teamserver_ip}"
$TeamServerPort = "${teamserver_port}"
$AdminPassword = "${admin_password}"
$DeploymentBucket = "${deployment_bucket}"
$DeploymentId = "${deployment_id}"
$AwsRegion = "${aws_region}"
$Hostname = "${hostname}"
$CSClientS3Path = "${cs_client_s3_path}"

# =============================================================================
# PHASE 1: REMOVE SERVER BLOAT & OPTIMIZE FOR WORKSTATION USE
# =============================================================================

Write-Log "Removing server bloat and optimizing for workstation use..."

# Disable Server Manager auto-start
Write-Log "Disabling Server Manager auto-start..."
Get-ScheduledTask -TaskName ServerManager -ErrorAction SilentlyContinue | Disable-ScheduledTask -ErrorAction SilentlyContinue

# Disable IE Enhanced Security Configuration (annoying popup blocker)
Write-Log "Disabling IE Enhanced Security Configuration..."
$AdminKey = "HKLM:\SOFTWARE\Microsoft\Active Setup\Installed Components\{A509B1A7-37EF-4b3f-8CFC-4F3A74704073}"
$UserKey = "HKLM:\SOFTWARE\Microsoft\Active Setup\Installed Components\{A509B1A8-37EF-4b3f-8CFC-4F3A74704073}"
Set-ItemProperty -Path $AdminKey -Name "IsInstalled" -Value 0 -ErrorAction SilentlyContinue
Set-ItemProperty -Path $UserKey -Name "IsInstalled" -Value 0 -ErrorAction SilentlyContinue

# Optimize for programs (not background services) - Better interactive performance
Write-Log "Optimizing for interactive workstation use..."
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\PriorityControl" -Name "Win32PrioritySeparation" -Value 38 -ErrorAction SilentlyContinue

# Disable unnecessary server services
Write-Log "Disabling unnecessary server services..."
$servicesToDisable = @(
    "W3SVC",              # IIS Web Server
    "WAS",                # Windows Process Activation Service
    "MSSQLSERVER",        # SQL Server
    "MSDTC",              # Distributed Transaction Coordinator
    "RemoteRegistry",     # Remote Registry (security risk)
    "SNMP",               # SNMP Service
    "SNMPTrap"            # SNMP Trap
)
foreach ($service in $servicesToDisable) {
    if (Get-Service -Name $service -ErrorAction SilentlyContinue) {
        try {
            Stop-Service -Name $service -Force -ErrorAction SilentlyContinue
            Set-Service -Name $service -StartupType Disabled -ErrorAction SilentlyContinue
            Write-Log "Disabled service: $service"
        } catch { }
    }
}

# =============================================================================
# PHASE 2: COMPLETELY DISABLE WINDOWS DEFENDER
# =============================================================================

Write-Log "Completely disabling Windows Defender via registry..."

# Disable Windows Defender via registry (most reliable method)
$defenderPath = "HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender"
$realtimePath = "$defenderPath\Real-Time Protection"
$scanPath = "$defenderPath\Scan"
$spynetPath = "$defenderPath\Spynet"

# Create registry keys if they don't exist
@($defenderPath, $realtimePath, $scanPath, $spynetPath) | ForEach-Object {
    if (-not (Test-Path $_)) {
        New-Item -Path $_ -Force -ErrorAction SilentlyContinue | Out-Null
    }
}

# Disable Windows Defender entirely
Set-ItemProperty -Path $defenderPath -Name "DisableAntiSpyware" -Value 1 -Type DWord -ErrorAction SilentlyContinue
Set-ItemProperty -Path $defenderPath -Name "DisableAntiVirus" -Value 1 -Type DWord -ErrorAction SilentlyContinue
Set-ItemProperty -Path $defenderPath -Name "ServiceKeepAlive" -Value 0 -Type DWord -ErrorAction SilentlyContinue

# Disable Real-Time Protection
Set-ItemProperty -Path $realtimePath -Name "DisableBehaviorMonitoring" -Value 1 -Type DWord -ErrorAction SilentlyContinue
Set-ItemProperty -Path $realtimePath -Name "DisableIOAVProtection" -Value 1 -Type DWord -ErrorAction SilentlyContinue
Set-ItemProperty -Path $realtimePath -Name "DisableOnAccessProtection" -Value 1 -Type DWord -ErrorAction SilentlyContinue
Set-ItemProperty -Path $realtimePath -Name "DisableRealtimeMonitoring" -Value 1 -Type DWord -ErrorAction SilentlyContinue
Set-ItemProperty -Path $realtimePath -Name "DisableScanOnRealtimeEnable" -Value 1 -Type DWord -ErrorAction SilentlyContinue

# Disable scanning
Set-ItemProperty -Path $scanPath -Name "DisableArchiveScanning" -Value 1 -Type DWord -ErrorAction SilentlyContinue
Set-ItemProperty -Path $scanPath -Name "DisableEmailScanning" -Value 1 -Type DWord -ErrorAction SilentlyContinue
Set-ItemProperty -Path $scanPath -Name "DisableRemovableDriveScanning" -Value 1 -Type DWord -ErrorAction SilentlyContinue

# Disable cloud-delivered protection
Set-ItemProperty -Path $spynetPath -Name "SpynetReporting" -Value 0 -Type DWord -ErrorAction SilentlyContinue
Set-ItemProperty -Path $spynetPath -Name "SubmitSamplesConsent" -Value 2 -Type DWord -ErrorAction SilentlyContinue

# Disable via PowerShell cmdlets (may fail on first boot, but try anyway)
try {
    Set-MpPreference -DisableRealtimeMonitoring $true -ErrorAction SilentlyContinue
    Set-MpPreference -DisableBehaviorMonitoring $true -ErrorAction SilentlyContinue
    Set-MpPreference -DisableBlockAtFirstSeen $true -ErrorAction SilentlyContinue
    Set-MpPreference -DisableIOAVProtection $true -ErrorAction SilentlyContinue
    Set-MpPreference -DisablePrivacyMode $true -ErrorAction SilentlyContinue
    Set-MpPreference -DisableScriptScanning $true -ErrorAction SilentlyContinue
    Set-MpPreference -SubmitSamplesConsent 2 -ErrorAction SilentlyContinue
    Set-MpPreference -MAPSReporting 0 -ErrorAction SilentlyContinue
    Add-MpPreference -ExclusionPath "C:\Tools" -ErrorAction SilentlyContinue
    Add-MpPreference -ExclusionPath "C:\Windows\Temp" -ErrorAction SilentlyContinue
    Write-Log "Windows Defender disabled via PowerShell"
} catch {
    Write-Log "PowerShell Defender cmdlets not available yet (will be disabled via registry on reboot)"
}

# Stop and disable Windows Defender services
Write-Log "Stopping and disabling Windows Defender services..."
$defenderServices = @(
    "WinDefend",          # Windows Defender Antivirus Service
    "WdNisSvc",           # Windows Defender Network Inspection Service
    "WdNisDrv",           # Windows Defender Network Inspection Driver
    "WdBoot",             # Windows Defender Boot Driver
    "WdFilter",           # Windows Defender Mini-Filter Driver
    "Sense"               # Windows Defender Advanced Threat Protection
)
foreach ($service in $defenderServices) {
    if (Get-Service -Name $service -ErrorAction SilentlyContinue) {
        try {
            Stop-Service -Name $service -Force -ErrorAction SilentlyContinue
            Set-Service -Name $service -StartupType Disabled -ErrorAction SilentlyContinue
            Write-Log "Disabled Defender service: $service"
        } catch { }
    }
}

Write-Log "Windows Defender completely disabled"

# =============================================================================
# PHASE 3: SYSTEM CONFIGURATION
# =============================================================================

# Set hostname
if ($Hostname) {
    Write-Log "Setting hostname to: $Hostname"
    try {
        Rename-Computer -NewName $Hostname -Force -ErrorAction SilentlyContinue
        Write-Log "Hostname set successfully (will apply after reboot)"
    } catch { Write-Log "Error setting hostname: $_" }
}

# Create directories
Write-Log "Creating tool directories..."
@("C:\Tools","C:\Tools\PowerSploit","C:\Tools\SharpTools","C:\Tools\CobaltStrike","C:\Users\Administrator\.ssh","C:\ProgramData\ssh") | ForEach-Object { New-Item -ItemType Directory -Path $_ -Force | Out-Null }

# Set Administrator password for RDP access
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

# Install OpenSSH Server for SSH access from jumpbox
Write-Log "Installing OpenSSH Server..."
try {
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 -ErrorAction SilentlyContinue
    Start-Service sshd -ErrorAction SilentlyContinue
    Set-Service -Name sshd -StartupType 'Automatic' -ErrorAction SilentlyContinue
    # Allow SSH through firewall
    New-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -DisplayName "OpenSSH Server (sshd)" -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -ErrorAction SilentlyContinue
    Write-Log "OpenSSH Server installed and started"
} catch { Write-Log "OpenSSH Server setup failed: $_" }

# Install Chocolatey
Write-Log "Installing Chocolatey package manager..."
try { if (-not (Get-Command choco -ErrorAction SilentlyContinue)) { Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1')) } } catch {}
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# Install essential tools + Windows Terminal
Write-Log "Installing tools: Git, 7zip, Python, Java 17, AWS CLI, Windows Terminal..."
@("git","7zip","python3","openjdk17","awscli","microsoft-windows-terminal") | ForEach-Object { 
    Write-Log "Installing: $_"
    try { choco install $_ -y --no-progress 2>&1 | Out-Null } catch { Write-Log "Failed to install $_" }
}
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
Write-Log "Tool installation complete"

# Download jumpbox public key from S3 and configure SSH authorized_keys
if ($DeploymentBucket) {
    $s3Key = "s3://$DeploymentBucket/keys/$DeploymentId/jumpbox_internal.pub"
    Write-Log "Waiting for jumpbox public key from S3..."
    for ($i=1; $i -le 60; $i++) {
        try {
            & aws s3 cp $s3Key "C:\Windows\Temp\jumpbox.pub" --region $AwsRegion 2>&1 | Out-Null
            if (Test-Path "C:\Windows\Temp\jumpbox.pub") {
                Write-Log "Downloaded jumpbox public key"
                # Configure OpenSSH authorized_keys for Administrator
                $sshDir = "C:\ProgramData\ssh"
                $authKeysFile = "$sshDir\administrators_authorized_keys"
                Copy-Item "C:\Windows\Temp\jumpbox.pub" $authKeysFile -Force
                # Set proper permissions (only Administrators and SYSTEM)
                icacls $authKeysFile /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F" 2>&1 | Out-Null
                Write-Log "Configured SSH authorized_keys for Administrator"
                "KEY_CONFIGURED" | Out-File "C:\Tools\bootstrap-status.txt"
                break
            }
        } catch { Write-Log "Key download attempt $i failed: $_" }
        Start-Sleep -Seconds 10
    }
}

# =============================================================================
# PHASE 3.5: GENERATE ATTACK BOX SSH KEY FOR OUTBOUND CONNECTIONS
# =============================================================================
# Generate SSH key on attack box to connect to team server and other hosts
# Private key stays on this host, public key uploaded to S3

Write-Log "Generating SSH key for outbound connections to internal hosts..."

try {
    # Use WSL to generate SSH key (if WSL is not ready yet, use OpenSSH)
    $sshKeyPath = "C:\Users\Administrator\.ssh\attackbox_internal_key"
    $sshPubKeyPath = "$sshKeyPath.pub"
    
    # Check if key already exists
    if (-not (Test-Path $sshKeyPath)) {
        Write-Log "Generating ed25519 SSH key pair..."
        
        # Generate key using OpenSSH (installed earlier)
        & ssh-keygen -t ed25519 -f $sshKeyPath -N '""' -C "attackbox-$Hostname" 2>&1 | Out-Null
        
        if (Test-Path $sshKeyPath) {
            Write-Log "SSH key pair generated successfully"
            
            # Set proper permissions
            icacls $sshKeyPath /inheritance:r /grant:r "$env:USERNAME`:F" 2>&1 | Out-Null
            icacls $sshPubKeyPath /inheritance:r /grant:r "$env:USERNAME`:R" 2>&1 | Out-Null
            
            # Upload public key to S3 for team server to download
            if ($DeploymentBucket) {
                $s3AttackboxKey = "s3://$DeploymentBucket/keys/$DeploymentId/attackbox_internal.pub"
                Write-Log "Uploading attack box public key to S3..."
                
                for ($i=1; $i -le 10; $i++) {
                    try {
                        & aws s3 cp $sshPubKeyPath $s3AttackboxKey --region $AwsRegion 2>&1 | Out-Null
                        Write-Log "Attack box public key uploaded to S3 successfully"
                        "ATTACKBOX_KEY_UPLOADED" | Out-File -Append "C:\Tools\bootstrap-status.txt"
                        break
                    } catch {
                        Write-Log "S3 upload attempt $i failed, retrying..."
                        Start-Sleep -Seconds 5
                    }
                }
            }
            
            # Create SSH config for easy access to internal hosts
            Write-Log "Creating SSH config for internal hosts..."
            $sshConfigPath = "C:\Users\Administrator\.ssh\config"
            $sshConfig = @"
# Attack Box SSH Configuration - Internal Network Access
# Generated automatically during deployment

Host teamserver ts
    HostName $TeamServerIP
    User ubuntu
    IdentityFile C:\Users\Administrator\.ssh\attackbox_internal_key
    StrictHostKeyChecking accept-new

Host dc01 kingslanding
    HostName 192.168.56.10
    User Administrator
    IdentityFile C:\Users\Administrator\.ssh\attackbox_internal_key
    StrictHostKeyChecking accept-new

Host 192.168.56.*
    User ubuntu
    IdentityFile C:\Users\Administrator\.ssh\attackbox_internal_key
    StrictHostKeyChecking accept-new
"@
            $sshConfig | Out-File $sshConfigPath -Encoding UTF8
            Write-Log "SSH config created for internal hosts"
            
        } else {
            Write-Log "WARNING: SSH key generation may have failed"
        }
    } else {
        Write-Log "SSH key already exists, skipping generation"
    }
} catch {
    Write-Log "SSH key generation failed: $_"
}

# Download and extract Cobalt Strike Client from S3
if ($CSClientS3Path -and $CSClientS3Path -ne "") {
    Write-Log "Downloading Cobalt Strike Client from S3..."
    try {
        $csArchive = "C:\Windows\Temp\cs-client-archive"
        & aws s3 cp $CSClientS3Path $csArchive --region $AwsRegion 2>&1 | Out-Null
        
        if (Test-Path $csArchive) {
            Write-Log "Downloaded CS Client archive, extracting..."
            
            # Detect file type and extract
            $fileHeader = [System.IO.File]::ReadAllBytes($csArchive)[0..3]
            $csDir = "C:\Tools\CobaltStrike"
            
            # Check for ZIP (PK header)
            if ($fileHeader[0] -eq 0x50 -and $fileHeader[1] -eq 0x4B) {
                Write-Log "Extracting as ZIP..."
                Expand-Archive -Path $csArchive -DestinationPath $csDir -Force
            }
            # Check for GZIP (1F 8B header)
            elseif ($fileHeader[0] -eq 0x1F -and $fileHeader[1] -eq 0x8B) {
                Write-Log "Extracting as tar.gz using 7zip..."
                # Use 7zip to extract tar.gz
                $7zPath = "C:\ProgramData\chocolatey\tools\7z.exe"
                if (-not (Test-Path $7zPath)) { $7zPath = "C:\Program Files\7-Zip\7z.exe" }
                
                if (Test-Path $7zPath) {
                    # Extract .gz to .tar
                    & $7zPath x $csArchive -o"C:\Windows\Temp" -y 2>&1 | Out-Null
                    $tarFile = $csArchive -replace '\.gz$',''
                    if (-not (Test-Path $tarFile)) { $tarFile = "C:\Windows\Temp\cs-client-archive" }
                    
                    # Extract .tar
                    & $7zPath x $tarFile -o"$csDir" -y 2>&1 | Out-Null
                    Remove-Item $tarFile -Force -ErrorAction SilentlyContinue
                } else {
                    Write-Log "7zip not found, trying tar command..."
                    tar -xzf $csArchive -C $csDir 2>&1 | Out-Null
                }
            }
            # Try tar for other formats
            else {
                Write-Log "Trying tar extraction..."
                tar -xf $csArchive -C $csDir 2>&1 | Out-Null
            }
            
            # Clean up archive
            Remove-Item $csArchive -Force -ErrorAction SilentlyContinue
            
            # Check if extraction was successful
            if (Test-Path "$csDir\cobaltstrike.jar" -or (Get-ChildItem $csDir -Recurse -Filter "cobaltstrike.jar").Count -gt 0) {
                Write-Log "Cobalt Strike Client extracted successfully"
                "CS_CLIENT_INSTALLED" | Out-File "C:\Tools\cs-client-status.txt"
                
                # Create desktop shortcut for CS Client
                $WshShell = New-Object -ComObject WScript.Shell
                
                # Find cobaltstrike.jar location
                $csJar = Get-ChildItem $csDir -Recurse -Filter "cobaltstrike.jar" | Select-Object -First 1
                if ($csJar) {
                    $csJarDir = $csJar.DirectoryName
                    
                    # Create batch file to launch CS Client
                    @"
@echo off
cd /d "$csJarDir"
java -XX:ParallelGCThreads=4 -XX:+AggressiveHeap -XX:+UseParallelGC -jar cobaltstrike.jar
pause
"@ | Out-File "C:\Tools\CobaltStrike\Launch-CS-Client.bat" -Encoding ASCII
                    
                    # Create shortcut
                    $Shortcut = $WshShell.CreateShortcut("C:\Users\Administrator\Desktop\Cobalt Strike Client.lnk")
                    $Shortcut.TargetPath = "C:\Tools\CobaltStrike\Launch-CS-Client.bat"
                    $Shortcut.WorkingDirectory = $csJarDir
                    $Shortcut.IconLocation = "C:\Windows\System32\shell32.dll,13"
                    $Shortcut.Save()
                    
                    Write-Log "Created CS Client desktop shortcut"
                    
                    # Create auto-launch script for CS Client on user login
                    # This runs when Administrator logs in via RDP
                    @"
# CS Client Auto-Launch Script
`$csJarDir = "$csJarDir"
`$logFile = "C:\Windows\Temp\cs-client-autolaunch.log"

# Log function
function Write-LaunchLog { param([string]`$Message); "`$(Get-Date -Format 'HH:mm:ss') - `$Message" | Out-File -Append `$logFile }

Write-LaunchLog "CS Client auto-launch triggered"

# Wait for desktop to be ready
Start-Sleep -Seconds 5

# Check if CS Client is already running
`$csProcess = Get-Process -Name "java" -ErrorAction SilentlyContinue | Where-Object { `$_.MainWindowTitle -like "*Cobalt Strike*" }
if (`$csProcess) {
    Write-LaunchLog "CS Client already running, skipping launch"
    exit
}

# Launch CS Client
Write-LaunchLog "Launching CS Client from `$csJarDir"
try {
    Start-Process -FilePath "java" -ArgumentList "-XX:ParallelGCThreads=4 -XX:+AggressiveHeap -XX:+UseParallelGC -jar cobaltstrike.jar" -WorkingDirectory `$csJarDir
    Write-LaunchLog "CS Client launched successfully"
} catch {
    Write-LaunchLog "Failed to launch CS Client: `$_"
}
"@ | Out-File "C:\Tools\CobaltStrike\AutoLaunch-CS-Client.ps1" -Encoding UTF8
                    
                    # Register scheduled task to run on user login
                    $autoLaunchAction = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File C:\Tools\CobaltStrike\AutoLaunch-CS-Client.ps1"
                    $autoLaunchTrigger = New-ScheduledTaskTrigger -AtLogOn -User "Administrator"
                    $autoLaunchPrincipal = New-ScheduledTaskPrincipal -UserId "Administrator" -LogonType Interactive -RunLevel Highest
                    $autoLaunchSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
                    Register-ScheduledTask -TaskName "CS-Client-AutoLaunch" -Action $autoLaunchAction -Trigger $autoLaunchTrigger -Principal $autoLaunchPrincipal -Settings $autoLaunchSettings -Force | Out-Null
                    
                    Write-Log "Registered CS Client auto-launch on Administrator login"
                }
            } else {
                Write-Log "WARNING: CS Client extraction may have failed - cobaltstrike.jar not found"
            }
        } else {
            Write-Log "WARNING: Failed to download CS Client from S3"
        }
    } catch {
        Write-Log "Error downloading/extracting CS Client: $_"
    }
} else {
    Write-Log "No CS Client S3 path provided, skipping CS Client installation"
}

# Clone PowerSploit
Write-Log "Cloning PowerSploit repository..."
try { if (-not (Test-Path "C:\Tools\PowerSploit\.git")) { git clone https://github.com/PowerShellMafia/PowerSploit.git C:\Tools\PowerSploit 2>&1 | Out-Null; Write-Log "PowerSploit cloned successfully" } } catch { Write-Log "PowerSploit clone failed: $_" }

# =============================================================================
# PHASE 4: WSL1 SETUP - Fully Automated Ubuntu Installation
# =============================================================================
# Using WSL1 (not WSL2) because:
# - WSL2 requires nested virtualization (not available on standard EC2)
# - WSL1 works perfectly for red team tools (nmap, python, scripts)
# - WSL1 has better Windows file system access (C:\Tools)
# - All offensive tools work fine on WSL1

Write-Log "Setting up WSL1 with Ubuntu (fully automated)..."

# Enable WSL feature (WSL1 only - no Virtual Machine Platform needed)
try {
    Write-Log "Enabling WSL feature..."
    dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart 2>&1 | Out-Null
    Write-Log "WSL feature enabled (requires reboot)"
} catch {
    Write-Log "WSL feature enablement failed: $_"
}

# Post-reboot WSL1 configuration script - Fully Automated
Write-Log "Creating post-reboot WSL setup script..."
@"
# WSL1 Post-Reboot Configuration - Fully Automated Ubuntu Setup
`$logFile = "$DeploymentLogsDir\wsl-setup.log"

function Write-WSLLog { param([string]`$Message); "`$(Get-Date -Format 'HH:mm:ss') - `$Message" | Out-File -Append `$logFile; Write-Host `$Message }

Write-WSLLog "=== WSL Post-Reboot Setup Started ==="

# Wait for system to stabilize after reboot
Start-Sleep -Seconds 15

# Set WSL1 as default version (explicit - no WSL2)
Write-WSLLog "Setting WSL1 as default version..."
wsl --set-default-version 1 2>&1 | Out-File -Append `$logFile

# Wait for WSL service
Start-Sleep -Seconds 5

# Install Ubuntu distribution
Write-WSLLog "Installing Ubuntu distribution..."
wsl --install -d Ubuntu --no-launch 2>&1 | Out-File -Append `$logFile

# Wait for installation to complete
Write-WSLLog "Waiting for Ubuntu installation to complete..."
Start-Sleep -Seconds 90

# Check if Ubuntu was installed
Write-WSLLog "Checking WSL installation status..."
wsl --list --verbose 2>&1 | Out-File -Append `$logFile

# Initialize Ubuntu with default user automatically (no prompts)
Write-WSLLog "Initializing Ubuntu with default user 'redteam'..."
try {
    # First run creates the distribution
    wsl -d Ubuntu -u root bash -c "exit" 2>&1 | Out-File -Append `$logFile
    Start-Sleep -Seconds 5
    
    # Create redteam user with no password, sudo access
    wsl -d Ubuntu -u root bash -c "useradd -m -s /bin/bash -G sudo redteam && passwd -d redteam" 2>&1 | Out-File -Append `$logFile
    
    # Set redteam as default user
    wsl -d Ubuntu -u root bash -c "echo -e '[user]\ndefault=redteam' > /etc/wsl.conf" 2>&1 | Out-File -Append `$logFile
    
    # Configure passwordless sudo
    wsl -d Ubuntu -u root bash -c "echo 'redteam ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/redteam && chmod 0440 /etc/sudoers.d/redteam" 2>&1 | Out-File -Append `$logFile
    
    # Test the setup
    wsl -d Ubuntu -u redteam bash -c "whoami" 2>&1 | Out-File -Append `$logFile
    
    Write-WSLLog "Ubuntu user 'redteam' created successfully (no password, passwordless sudo)"
} catch {
    Write-WSLLog "Ubuntu initialization failed: `$_"
}

# Update Ubuntu and install common tools
Write-WSLLog "Updating Ubuntu and installing common red team tools..."
wsl -d Ubuntu -u redteam bash -c "sudo apt update 2>&1 && sudo apt install -y nmap python3-pip curl wget git net-tools openssh-client 2>&1" 2>&1 | Out-File -Append `$logFile

# =============================================================================
# GENERATE SEPARATE WSL SSH KEY (Option 3 - Most Secure)
# =============================================================================
# Create a dedicated SSH key for WSL environment
# This key is separate from the Windows SSH key for complete isolation

Write-WSLLog "=== Generating WSL SSH Key (Separate from Windows) ==="

# Generate SSH key in WSL Ubuntu
Write-WSLLog "Generating ed25519 SSH key in WSL..."
wsl -d Ubuntu -u redteam bash -c "mkdir -p ~/.ssh && chmod 700 ~/.ssh && ssh-keygen -t ed25519 -f ~/.ssh/wsl_attackbox_key -N '' -C 'wsl-attackbox-$Hostname' && chmod 600 ~/.ssh/wsl_attackbox_key && chmod 644 ~/.ssh/wsl_attackbox_key.pub" 2>&1 | Out-File -Append `$logFile

# Verify key was created
`$wslKeyCheck = wsl -d Ubuntu -u redteam bash -c "test -f ~/.ssh/wsl_attackbox_key && echo 'KEY_EXISTS'"
if (`$wslKeyCheck -like "*KEY_EXISTS*") {
    Write-WSLLog "WSL SSH key generated successfully"
    
    # Copy public key to Windows for S3 upload
    Write-WSLLog "Copying WSL public key to Windows for S3 upload..."
    wsl -d Ubuntu -u redteam bash -c "cat ~/.ssh/wsl_attackbox_key.pub" | Out-File "C:\Windows\Temp\wsl_attackbox.pub" -Encoding UTF8
    
    # Upload WSL public key to S3
    if ("$DeploymentBucket" -ne "") {
        Write-WSLLog "Uploading WSL public key to S3..."
        `$s3WslKey = "s3://$DeploymentBucket/keys/$DeploymentId/wsl_attackbox_internal.pub"
        
        for (`$i=1; `$i -le 10; `$i++) {
            try {
                & aws s3 cp "C:\Windows\Temp\wsl_attackbox.pub" `$s3WslKey --region "$AwsRegion" 2>&1 | Out-Null
                if (`$?) {
                    Write-WSLLog "WSL public key uploaded to S3 successfully"
                    "WSL_KEY_UPLOADED" | Out-File -Append "C:\Tools\bootstrap-status.txt"
                    break
                }
            } catch {
                Write-WSLLog "S3 upload attempt `$i failed, retrying..."
                Start-Sleep -Seconds 5
            }
        }
        
        # Clean up temp file
        Remove-Item "C:\Windows\Temp\wsl_attackbox.pub" -Force -ErrorAction SilentlyContinue
    }
    
    # Configure SSH in WSL for easy access to internal hosts
    Write-WSLLog "Configuring SSH config in WSL..."
    wsl -d Ubuntu -u redteam bash -c @"
cat > ~/.ssh/config << 'SSHCONFIG'
# WSL Attack Box SSH Configuration - Internal Network Access
# Generated automatically during deployment

Host teamserver ts
    HostName $TeamServerIP
    User ubuntu
    IdentityFile ~/.ssh/wsl_attackbox_key
    StrictHostKeyChecking accept-new

Host dc01 kingslanding
    HostName 192.168.56.10
    User Administrator
    IdentityFile ~/.ssh/wsl_attackbox_key
    StrictHostKeyChecking accept-new

Host 192.168.56.*
    User ubuntu
    IdentityFile ~/.ssh/wsl_attackbox_key
    StrictHostKeyChecking accept-new
SSHCONFIG
chmod 600 ~/.ssh/config
"@ 2>&1 | Out-File -Append `$logFile

    Write-WSLLog "WSL SSH configuration complete"
    Write-WSLLog "Test with: wsl ssh teamserver"
} else {
    Write-WSLLog "WARNING: WSL SSH key generation failed"
}

Write-WSLLog "=== WSL SSH Key Setup Complete ==="

# Configure Windows Terminal to feature Ubuntu prominently
Write-WSLLog "Configuring Windows Terminal to feature Ubuntu..."
Start-Sleep -Seconds 10

`$terminalSettingsPath = "`$env:LOCALAPPDATA\Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json"

# Wait for Terminal settings to be created on first launch
`$maxWait = 30
`$waited = 0
while (-not (Test-Path `$terminalSettingsPath) -and `$waited -lt `$maxWait) {
    Start-Sleep -Seconds 2
    `$waited += 2
}

if (Test-Path `$terminalSettingsPath) {
    try {
        `$settings = Get-Content `$terminalSettingsPath -Raw | ConvertFrom-Json
        
        # Find Ubuntu profile
        `$ubuntuProfile = `$settings.profiles.list | Where-Object { `$_.name -like "*Ubuntu*" } | Select-Object -First 1
        
        if (`$ubuntuProfile) {
            Write-WSLLog "Found Ubuntu profile: `$(`$ubuntuProfile.name)"
            
            # Set Ubuntu as default profile
            `$settings.defaultProfile = `$ubuntuProfile.guid
            Write-WSLLog "Set Ubuntu as default profile"
            
            # Customize Ubuntu profile
            `$ubuntuProfile.startingDirectory = "~"
            `$ubuntuProfile.colorScheme = "One Half Dark"
            if (-not `$ubuntuProfile.icon) {
                `$ubuntuProfile.icon = "ms-appx:///ProfileIcons/{9acb9455-ca41-5af7-950f-6bca1bc9722f}.png"
            }
            
            # Add custom profiles for quick access
            Write-WSLLog "Adding custom Windows Terminal profiles..."
            
            # PowerShell in Tools directory profile
            `$toolsGuid = [guid]::NewGuid().ToString()
            `$toolsProfile = @{
                guid = `$toolsGuid
                name = "📦 PowerShell → Tools"
                commandline = "powershell.exe -NoExit -Command `"Set-Location C:\Tools`""
                startingDirectory = "C:\Tools"
                icon = "ms-appx:///ProfileIcons/pwsh.png"
                colorScheme = "Campbell"
                hidden = `$false
            }
            
            # Ubuntu in Tools directory profile
            `$ubuntuToolsGuid = [guid]::NewGuid().ToString()
            `$ubuntuToolsProfile = @{
                guid = `$ubuntuToolsGuid
                name = "🐧 Ubuntu → /Tools"
                commandline = "wsl.exe -d Ubuntu -- bash -c `"cd /mnt/c/Tools && exec bash`""
                startingDirectory = "%USERPROFILE%"
                icon = "ms-appx:///ProfileIcons/{9acb9455-ca41-5af7-950f-6bca1bc9722f}.png"
                colorScheme = "One Half Dark"
                hidden = `$false
            }
            
            # SSH to Team Server profile (using WSL with its own key)
            `$teamServerGuid = [guid]::NewGuid().ToString()
            `$teamServerProfile = @{
                guid = `$teamServerGuid
                name = "🔴 SSH → Team Server"
                commandline = "wsl.exe -d Ubuntu -u redteam -- bash -c `"ssh teamserver`""
                startingDirectory = "%USERPROFILE%"
                icon = "ms-appx:///ProfileIcons/{9acb9455-ca41-5af7-950f-6bca1bc9722f}.png"
                colorScheme = "Campbell Powershell"
                hidden = `$false
                tabTitle = "Team Server SSH"
            }
            
            # Check if profiles already exist before adding
            `$existingProfiles = `$settings.profiles.list | Select-Object -ExpandProperty name
            
            if (`$existingProfiles -notcontains "📦 PowerShell → Tools") {
                `$settings.profiles.list += `$toolsProfile
                Write-WSLLog "Added PowerShell→Tools profile"
            }
            
            if (`$existingProfiles -notcontains "🐧 Ubuntu → /Tools") {
                `$settings.profiles.list += `$ubuntuToolsProfile
                Write-WSLLog "Added Ubuntu→Tools profile"
            }
            
            if (`$existingProfiles -notcontains "🔴 SSH → Team Server") {
                `$settings.profiles.list += `$teamServerProfile
                Write-WSLLog "Added SSH→TeamServer profile"
            }
            
            # Save settings
            `$settings | ConvertTo-Json -Depth 10 | Out-File `$terminalSettingsPath -Encoding UTF8
            Write-WSLLog "Windows Terminal configured - Ubuntu default + quick shortcuts + SSH profiles!"
        } else {
            Write-WSLLog "Ubuntu profile not found yet - will auto-detect on next Terminal launch"
        }
    } catch {
        Write-WSLLog "Windows Terminal configuration error: `$_"
    }
} else {
    Write-WSLLog "Windows Terminal settings file not created yet - will configure on first launch"
}

# Create a helper script to set Ubuntu as default (in case Terminal config didn't work)
`$helperScript = @"
# Windows Terminal Ubuntu Quick Configurator
`$settingsPath = "`$env:LOCALAPPDATA\Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json"

if (Test-Path `$settingsPath) {
    try {
        `$config = Get-Content `$settingsPath -Raw | ConvertFrom-Json
        `$ubuntu = `$config.profiles.list | Where-Object { `$_.name -like "*Ubuntu*" } | Select-Object -First 1
        
        if (`$ubuntu) {
            if (`$config.defaultProfile -ne `$ubuntu.guid) {
                `$config.defaultProfile = `$ubuntu.guid
                `$config | ConvertTo-Json -Depth 10 | Out-File `$settingsPath -Encoding UTF8
                Write-Host "✅ Ubuntu set as default Windows Terminal profile!"
            } else {
                Write-Host "✅ Ubuntu is already the default profile!"
            }
        } else {
            Write-Host "❌ Ubuntu profile not found. Launch Windows Terminal first to detect it."
        }
    } catch {
        Write-Host "❌ Error: `$_"
    }
} else {
    Write-Host "❌ Windows Terminal not launched yet. Open it once, then run this script."
}

Read-Host "Press Enter to exit"
"@
    `$helperScript | Out-File "$DeploymentLogsDir\Set-Ubuntu-Default.ps1" -Encoding UTF8
    Write-WSLLog "Created helper script: Set-Ubuntu-Default.ps1"

Write-WSLLog "=== WSL Setup Complete ==="
Write-WSLLog "Ubuntu is ready! Access via:"
Write-WSLLog "  - Windows Terminal (opens Ubuntu by default)"
Write-WSLLog "  - Type 'wsl' or 'ubuntu' in any terminal"
Write-WSLLog "  - User: redteam (no password, passwordless sudo)"

# Create desktop info file
`$infoText = @"
🐧 UBUNTU ON WSL1 - READY TO USE!

Quick Access:
-------------
1. Windows Terminal (Start Menu) - Opens Ubuntu by default
2. Type 'wsl' or 'ubuntu' in PowerShell/CMD
3. Click [+] dropdown in Windows Terminal top bar

Default User:
-------------
Username: redteam
Password: (none - passwordless)
Sudo: Enabled (no password required)

SSH ACCESS TO INTERNAL HOSTS 🔐
--------------------------------
✨ WSL has its own dedicated SSH key (separate from Windows)!

SSH Key: ~/.ssh/wsl_attackbox_key (ed25519)
Public Key: Automatically shared with team server via S3

SSH Commands (from Ubuntu):
  ssh teamserver               # SSH to team server (192.168.56.40)
  ssh ts                       # Short alias
  ssh dc01                     # SSH to DC01
  ssh 192.168.56.10            # Direct IP

Or use Windows Terminal:
  Click [+] → "🔴 SSH → Team Server" (uses WSL key automatically)

SECURE KEY ARCHITECTURE:
------------------------
✅ WSL generated its own SSH key (stays in WSL)
✅ Windows has separate SSH key (stays in Windows)
✅ Both public keys shared with team server via S3
✅ Private keys NEVER transmitted
✅ Complete isolation between environments

Example Commands:
-----------------
wsl                          # Enter Ubuntu
ssh teamserver               # SSH to team server (no password!)
sudo apt update              # Update packages
sudo apt install impacket-scripts -y
cd /mnt/c/Tools             # Access Windows files
python3 script.py           # Run scripts

Installed Tools:
----------------
✅ nmap, python3-pip, curl, wget, git, net-tools, openssh-client

If Ubuntu is not default in Terminal:
--------------------------------------
Run: Desktop\Deployment-Logs-Scripts\Set-Ubuntu-Default.ps1
"@
    `$infoText | Out-File "C:\Users\Administrator\Desktop\Ubuntu-Quick-Start.txt" -Encoding UTF8

# Unregister this scheduled task (only needs to run once)
Unregister-ScheduledTask -TaskName "WSL-Setup" -Confirm:`$false -ErrorAction SilentlyContinue
Write-WSLLog "Setup task unregistered"
"@ | Out-File "$ScriptsDir\wsl-post-reboot.ps1" -Encoding UTF8

# Register scheduled task for WSL setup after reboot
Write-Log "Registering WSL post-reboot task..."
$action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File $ScriptsDir\wsl-post-reboot.ps1"
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -Delay (New-TimeSpan -Seconds 45)
Register-ScheduledTask -TaskName "WSL-Setup" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Log "WSL will be configured 45 seconds after reboot"

# README
$csClientNote = if ($CSClientS3Path) { "CS Client: C:\Tools\CobaltStrike\ (Desktop shortcut available, auto-launches on login)" } else { "CS Client: Will auto-launch when uploaded to C:\Tools\CobaltStrike\" }

@"
================================================================================
               WINDOWS SERVER 2022 ATTACK BOX - Quick Start
================================================================================

SYSTEM OPTIMIZATIONS
--------------------
✅ Server bloat removed (Server Manager, unnecessary services disabled)
✅ Windows Defender COMPLETELY DISABLED (registry + services)
✅ Optimized for interactive workstation use
✅ Windows Terminal installed for better shell experience
✅ WSL1 with Ubuntu - FULLY AUTOMATED (no setup prompts!)

DEPLOYMENT LOGS & SCRIPTS
--------------------------
All deployment logs and scripts are stored on your Desktop:
  Desktop\Deployment-Logs-Scripts\

Files:
- attackbox-init.log         : Main installation log
- AutoLaunch-CS-Client.ps1   : CS Client auto-launch script
- cs-client-autolaunch.log   : CS Client launch attempts log
- wsl-setup.log              : WSL post-reboot setup log
- wsl-post-reboot.ps1        : WSL configuration script
- Set-Ubuntu-Default.ps1     : Helper to set Ubuntu as default profile

Desktop Files:
- Ubuntu-Quick-Start.txt     : Ubuntu access guide and commands

TEAM SERVER CONNECTION
----------------------
Team Server IP:   $TeamServerIP
Team Server Port: $TeamServerPort

COBALT STRIKE CLIENT
--------------------
$csClientNote

✨ AUTO-LAUNCH: CS Client will automatically launch when you RDP into this machine!
   A popup will confirm the launch and show connection details.

TOOLS INSTALLED
---------------
- PowerSploit:       C:\Tools\PowerSploit\
- Java 17:           For Cobalt Strike Client
- Python 3:          Available in PATH
- Git:               Available in PATH
- AWS CLI:           Available in PATH
- Windows Terminal:  Modern terminal with tabs (Start Menu)
- WSL1 Ubuntu:       Full Linux environment (fully automated!)

UBUNTU ON WSL1 - QUICK ACCESS 🐧
---------------------------------
✨ FULLY AUTOMATED - NO SETUP REQUIRED!

After reboot, Ubuntu is ready with:
  User: redteam
  Password: (none - passwordless login)
  Sudo: Enabled (no password required)

Access Ubuntu:
1. Windows Terminal → Opens Ubuntu by default
2. Type 'wsl' or 'ubuntu' in any terminal
3. Click [+] dropdown in Windows Terminal → Select Ubuntu

Pre-installed: nmap, python3-pip, curl, wget, git, net-tools

Example Commands:
  wsl                          # Enter Ubuntu
  sudo apt install metasploit  # Install tools (no password)
  cd /mnt/c/Tools              # Access Windows Tools folder
  python3 /mnt/c/Tools/script.py   # Run Python scripts

WINDOWS TERMINAL USAGE
----------------------
Launch: Start Menu → "Windows Terminal" or Win+X

✨ Quick Access Profiles (in [+] dropdown):
- 🐧 Ubuntu (DEFAULT) - Opens Ubuntu terminal
- 🔴 SSH → Team Server - Direct SSH to team server
- 📦 PowerShell → Tools - Opens PowerShell in C:\Tools
- 🐧 Ubuntu → /Tools - Opens Ubuntu in /mnt/c/Tools
- Windows PowerShell - Standard PowerShell
- Command Prompt - CMD

Keyboard shortcuts:
- New tab: Ctrl+Shift+T
- Split pane: Alt+Shift+D
- Switch tabs: Ctrl+Tab
- Close tab: Ctrl+Shift+W

SSH ACCESS TO INTERNAL HOSTS
-----------------------------
✨ Attack box has its own SSH key for connecting to internal hosts!

SSH Key Location: C:\Users\Administrator\.ssh\attackbox_internal_key
Public Key: Automatically shared with team server via S3

Quick SSH Commands (from PowerShell or Ubuntu):
  ssh teamserver               # SSH to team server
  ssh dc01                     # SSH to DC01
  ssh 192.168.56.40            # Direct IP access

Or use Windows Terminal profile:
  Click [+] → "🔴 SSH → Team Server"

SECURE KEY ARCHITECTURE
------------------------
✅ Attack box generates its own SSH key (stays on this host)
✅ Public key shared via S3 to team server
✅ Private key NEVER transmitted
✅ No manual key management needed

WHY WSL1 (not WSL2)?
--------------------
✅ WSL1 works on all EC2 instances (no nested virtualization needed)
✅ All red team tools work perfectly (nmap, python, Impacket, etc.)
✅ Better Windows file access (faster C:\Tools access)
✅ Simpler networking (shares Windows IP)
✅ Less memory overhead

You DON'T lose anything for red team work!
Docker won't work, but you don't need it on an attack box.

ACCESS OPTIONS
--------------
1. SSH from Jumpbox:
   ssh attackbox
   (or: ssh Administrator@192.168.56.50)

2. RDP via SSH Tunnel (from your local machine):
   ssh -L 3389:192.168.56.50:3389 ubuntu@<JUMPBOX_PUBLIC_IP>
   Then RDP to: localhost:3389
   Login: Administrator / $AdminPassword

CONNECTING CS CLIENT TO TEAM SERVER
-----------------------------------
The Attack Box can connect directly to the Team Server via internal network:
- Host: $TeamServerIP
- Port: $TeamServerPort

Or from your LOCAL machine via SSH tunnel:
   ssh -L 50050:$TeamServerIP`:$TeamServerPort ubuntu@<JUMPBOX_PUBLIC_IP>
   Then connect CS Client to: localhost:50050

QUICK START WORKFLOW
--------------------
1. RDP to attack box
2. CS Client auto-launches
3. Windows Terminal auto-opens Ubuntu
4. Install tools: sudo apt install nmap impacket-scripts
5. Run scans from Ubuntu, results in /mnt/c/Tools
6. Use PowerSploit from Windows PowerShell
7. Coordinate everything via CS Client

SECURITY NOTES
--------------
⚠️  Windows Defender is COMPLETELY DISABLED for red team operations
⚠️  This is intentional - do NOT enable it (will interfere with tools)
⚠️  C:\Tools is excluded from all scanning
⚠️  Ubuntu user 'redteam' has passwordless sudo (for convenience)
⚠️  Use this system for authorized red team engagements only

TROUBLESHOOTING
---------------
- CS Client logs: Desktop\Deployment-Logs-Scripts\cs-client-autolaunch.log
- Installation logs: Desktop\Deployment-Logs-Scripts\attackbox-init.log
- WSL logs: Desktop\Deployment-Logs-Scripts\wsl-setup.log
- Ubuntu not default? Run: Desktop\Deployment-Logs-Scripts\Set-Ubuntu-Default.ps1
- WSL issues: Check Desktop\Ubuntu-Quick-Start.txt

================================================================================
"@ | Out-File "C:\Users\Administrator\Desktop\README.txt" -Encoding UTF8

# Shortcuts
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("C:\Users\Administrator\Desktop\Tools.lnk"); $Shortcut.TargetPath = "C:\Tools"; $Shortcut.Save()
$Shortcut = $WshShell.CreateShortcut("C:\Users\Administrator\Desktop\Deployment Logs.lnk"); $Shortcut.TargetPath = $DeploymentLogsDir; $Shortcut.Save()

# Create Universal CS Client Auto-Launch Script
# This works whether CS was installed from S3 or uploaded manually
Write-Log "Creating universal CS Client auto-launch script..."
@"
# Universal CS Client Auto-Launch Script
# Works for both S3-installed and manually-uploaded CS Client
`$logFile = "$DeploymentLogsDir\cs-client-autolaunch.log"

# Log function
function Write-LaunchLog { param([string]`$Message); "`$(Get-Date -Format 'HH:mm:ss') - `$Message" | Out-File -Append `$logFile }

Write-LaunchLog "CS Client auto-launch triggered"

# Wait for desktop to be ready
Start-Sleep -Seconds 5

# Check if CS Client is already running
`$csProcess = Get-Process -Name "java" -ErrorAction SilentlyContinue | Where-Object { `$_.MainWindowTitle -like "*Cobalt Strike*" }
if (`$csProcess) {
    Write-LaunchLog "CS Client already running, skipping launch"
    exit
}

# Search for CS Client in multiple possible locations
`$csPaths = @(
    "C:\Tools\CobaltStrike\cobaltstrike.jar",
    "C:\Tools\CobaltStrike\cobaltstrike.exe"
)

# Also search recursively in CobaltStrike folder
if (Test-Path "C:\Tools\CobaltStrike") {
    `$foundJar = Get-ChildItem "C:\Tools\CobaltStrike" -Recurse -Filter "cobaltstrike.jar" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (`$foundJar) {
        `$csPaths += `$foundJar.FullName
    }
    
    `$foundExe = Get-ChildItem "C:\Tools\CobaltStrike" -Recurse -Filter "cobaltstrike.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (`$foundExe) {
        `$csPaths += `$foundExe.FullName
    }
}

`$csClientFound = `$false
foreach (`$csPath in `$csPaths) {
    if (Test-Path `$csPath) {
        Write-LaunchLog "Found CS Client at: `$csPath"
        `$csClientFound = `$true
        
        try {
            `$csDir = Split-Path `$csPath -Parent
            
            # Launch based on file type
            if (`$csPath -like "*.jar") {
                Write-LaunchLog "Launching CS Client JAR..."
                Start-Process -FilePath "java" -ArgumentList "-XX:ParallelGCThreads=4 -XX:+AggressiveHeap -XX:+UseParallelGC -Xmx1024M -jar ```"`$csPath```"" -WorkingDirectory `$csDir
            } elseif (`$csPath -like "*.exe") {
                Write-LaunchLog "Launching CS Client EXE..."
                Start-Process -FilePath `$csPath -WorkingDirectory `$csDir
            }
            
            Write-LaunchLog "CS Client launched successfully"
            
            # Create desktop info message
            `$msgBoxScript = @"
Add-Type -AssemblyName PresentationFramework
[System.Windows.MessageBox]::Show('Cobalt Strike Client is launching...``n``nTeam Server: $TeamServerIP`:$TeamServerPort``n``nConnection details are in the README on your desktop.', 'Cobalt Strike Auto-Launch', 'OK', 'Information')
"@
            Start-Process powershell -ArgumentList "-WindowStyle Hidden -Command ```"`$msgBoxScript```"" -NoNewWindow
            
            break
        } catch {
            Write-LaunchLog "Failed to launch CS Client: `$_"
        }
    }
}

if (-not `$csClientFound) {
    Write-LaunchLog "CS Client not found in C:\Tools\CobaltStrike - may need to be uploaded manually"
}
"@ | Out-File "$ScriptsDir\AutoLaunch-CS-Client.ps1" -Encoding UTF8

# Register scheduled task to run on Administrator login
Write-Log "Registering CS Client auto-launch task..."
$autoLaunchAction = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File $ScriptsDir\AutoLaunch-CS-Client.ps1"
$autoLaunchTrigger = New-ScheduledTaskTrigger -AtLogOn -User "Administrator"
$autoLaunchPrincipal = New-ScheduledTaskPrincipal -UserId "Administrator" -LogonType Interactive -RunLevel Highest
$autoLaunchSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName "CS-Client-AutoLaunch" -Action $autoLaunchAction -Trigger $autoLaunchTrigger -Principal $autoLaunchPrincipal -Settings $autoLaunchSettings -Force | Out-Null
Write-Log "CS Client auto-launch registered successfully"

"Complete" | Out-File "C:\Tools\.install-complete"
Write-Log "=== Attack Box Init Complete ==="
shutdown /r /t 60 /c "Attack Box setup complete. Rebooting for WSL2."
</powershell>
