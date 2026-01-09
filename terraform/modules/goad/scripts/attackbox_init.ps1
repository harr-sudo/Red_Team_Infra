<powershell>
# =============================================================================
# Windows Attack Box Initialization Script
# =============================================================================
# Sets up a Windows attack workstation with:
# - PowerSploit and offensive PowerShell tools
# - WSL2 with Ubuntu for SSH access to Team Server
# - Pre-configured SSH keys and aliases
# - Cobalt Strike client ready to connect
# =============================================================================

$ErrorActionPreference = "Continue"
$LogFile = "C:\Windows\Temp\attackbox-init.log"

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp - $Message" | Out-File -Append -FilePath $LogFile
    Write-Host $Message
}

Write-Log "=============================================="
Write-Log "Windows Attack Box Initialization"
Write-Log "Started: $(Get-Date)"
Write-Log "=============================================="

# Variables from Terraform
$TeamServerIP = "${teamserver_ip}"
$TeamServerPort = "${teamserver_port}"
$AdminPassword = "${admin_password}"
# INTERNAL key - separate from jumpbox key for security
$InternalKey = @"
${internal_key}
"@

# =============================================================================
# 1. Create Directory Structure
# =============================================================================
Write-Log "[1/8] Creating directory structure..."

$directories = @(
    "C:\Tools",
    "C:\Tools\PowerSploit",
    "C:\Tools\SharpTools",
    "C:\Tools\Scripts",
    "C:\Users\Administrator\.ssh"
)

foreach ($dir in $directories) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Log "Created: $dir"
    }
}

# =============================================================================
# 2. Disable Windows Defender (for tools to work)
# =============================================================================
Write-Log "[2/8] Configuring Windows Defender..."

try {
    # Disable real-time monitoring
    Set-MpPreference -DisableRealtimeMonitoring $true -ErrorAction SilentlyContinue
    
    # Add exclusions for tools directories
    Add-MpPreference -ExclusionPath "C:\Tools" -ErrorAction SilentlyContinue
    Add-MpPreference -ExclusionPath "C:\Users\Administrator\Downloads" -ErrorAction SilentlyContinue
    
    # Disable behavior monitoring
    Set-MpPreference -DisableBehaviorMonitoring $true -ErrorAction SilentlyContinue
    
    Write-Log "Windows Defender configured with exclusions"
} catch {
    Write-Log "Warning: Could not fully configure Windows Defender: $_"
}

# =============================================================================
# 3. Install Chocolatey Package Manager
# =============================================================================
Write-Log "[3/8] Installing Chocolatey..."

try {
    if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
        Set-ExecutionPolicy Bypass -Scope Process -Force
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
        Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
        Write-Log "Chocolatey installed successfully"
    } else {
        Write-Log "Chocolatey already installed"
    }
} catch {
    Write-Log "Warning: Chocolatey installation failed: $_"
}

# Refresh environment
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# =============================================================================
# 4. Install Essential Tools via Chocolatey
# =============================================================================
Write-Log "[4/8] Installing essential tools..."

$chocoPackages = @(
    "git",
    "7zip",
    "notepadplusplus",
    "vscode",
    "python3",
    "openjdk11"
)

foreach ($package in $chocoPackages) {
    try {
        Write-Log "Installing $package..."
        choco install $package -y --no-progress 2>&1 | Out-Null
    } catch {
        Write-Log "Warning: Failed to install $package"
    }
}

# Refresh PATH
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# =============================================================================
# 5. Clone PowerSploit from GitHub
# =============================================================================
Write-Log "[5/8] Cloning PowerSploit and offensive tools..."

try {
    # Clone PowerSploit
    if (-not (Test-Path "C:\Tools\PowerSploit\.git")) {
        git clone https://github.com/PowerShellMafia/PowerSploit.git C:\Tools\PowerSploit 2>&1 | Out-Null
        Write-Log "PowerSploit cloned successfully"
    }
    
    # Create a README for tools
    @"
# Windows Attack Box Tools
# ========================

## PowerSploit Location
C:\Tools\PowerSploit\

## Key Modules:
- Recon\PowerView.ps1      - AD enumeration
- Exfiltration\Invoke-Mimikatz.ps1 - Credential dumping
- Privesc\PowerUp.ps1      - Privilege escalation

## Quick Import:
Import-Module C:\Tools\PowerSploit\Recon\PowerView.ps1
Import-Module C:\Tools\PowerSploit\Privesc\PowerUp.ps1

## Team Server Connection
IP: $TeamServerIP
Port: $TeamServerPort

## From WSL (Ubuntu):
ssh teamserver   # Pre-configured alias
"@ | Out-File -FilePath "C:\Tools\README.txt" -Encoding UTF8
    
} catch {
    Write-Log "Warning: Failed to clone PowerSploit: $_"
}

# =============================================================================
# 6. Download Pre-compiled Sharp Tools
# =============================================================================
Write-Log "[6/8] Setting up Sharp tools directory..."

try {
    # Create placeholder scripts for common tools
    # Users will need to compile or download these themselves due to licensing
    
    @"
# Sharp Tools Directory
# =====================
# Place your compiled .NET tools here:
# - Rubeus.exe
# - SharpHound.exe  
# - Certify.exe
# - Seatbelt.exe
# - SharpUp.exe

# Download locations:
# - Rubeus: https://github.com/GhostPack/Rubeus
# - SharpHound: https://github.com/BloodHoundAD/SharpHound
# - Certify: https://github.com/GhostPack/Certify
# - Seatbelt: https://github.com/GhostPack/Seatbelt

# Note: These tools need to be compiled from source
# or obtained from trusted pre-compiled sources.
"@ | Out-File -FilePath "C:\Tools\SharpTools\README.txt" -Encoding UTF8

    Write-Log "Sharp tools directory prepared"
} catch {
    Write-Log "Warning: Failed to setup Sharp tools: $_"
}

# =============================================================================
# 7. Install and Configure WSL2
# =============================================================================
Write-Log "[7/8] Installing WSL2..."

try {
    # Enable WSL feature
    dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart 2>&1 | Out-Null
    dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart 2>&1 | Out-Null
    
    Write-Log "WSL features enabled - will configure after reboot"
    
    # Save the SSH private key to a temp file for WSL to use
    # This is the INTERNAL key - only works for Team Server, not Jumpbox
    $keyPath = "C:\Windows\Temp\teamserver_key.pem"
    $InternalKey | Out-File -FilePath $keyPath -Encoding ASCII -NoNewline
    Write-Log "Internal SSH key saved to $keyPath"
    
    # Create post-reboot script to complete WSL setup
    $wslSetupScript = @"
# WSL2 Post-Reboot Setup Script
`$ErrorActionPreference = "Continue"

# Set WSL2 as default
wsl --set-default-version 2 2>&1 | Out-Null

# Install Ubuntu
wsl --install -d Ubuntu --no-launch 2>&1 | Out-Null

# Wait for installation
Start-Sleep -Seconds 60

# Create the WSL setup script
`$wslBashScript = @'
#!/bin/bash
# Create SSH directory
mkdir -p ~/.ssh
chmod 700 ~/.ssh

# Copy the SSH key from Windows
cp /mnt/c/Windows/Temp/teamserver_key.pem ~/.ssh/teamserver_key
chmod 600 ~/.ssh/teamserver_key

# Create SSH config for easy access to Team Server
cat > ~/.ssh/config << 'SSHCONFIG'
Host teamserver
    HostName $TeamServerIP
    User ubuntu
    IdentityFile ~/.ssh/teamserver_key
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null

Host ts
    HostName $TeamServerIP
    User ubuntu
    IdentityFile ~/.ssh/teamserver_key
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
SSHCONFIG
chmod 600 ~/.ssh/config

# Add aliases to bashrc
echo '' >> ~/.bashrc
echo '# Team Server shortcuts' >> ~/.bashrc
echo 'alias teamserver="ssh teamserver"' >> ~/.bashrc
echo 'alias ts="ssh ts"' >> ~/.bashrc
echo 'echo ""' >> ~/.bashrc
echo 'echo "=== Windows Attack Box - WSL Ubuntu ===" ' >> ~/.bashrc
echo 'echo "Type: ssh teamserver (or ts) to connect to CS Team Server"' >> ~/.bashrc
echo 'echo "Team Server IP: $TeamServerIP"' >> ~/.bashrc
echo 'echo ""' >> ~/.bashrc

echo "WSL Ubuntu configured for Team Server access"
echo "SSH key installed at ~/.ssh/teamserver_key"
'@

# Save the bash script
`$wslBashScript | Out-File -FilePath "C:\Windows\Temp\wsl-setup.sh" -Encoding UTF8 -NoNewline

# Convert line endings to Unix format
`$content = Get-Content "C:\Windows\Temp\wsl-setup.sh" -Raw
`$content = `$content -replace "`r`n", "`n"
[System.IO.File]::WriteAllText("C:\Windows\Temp\wsl-setup.sh", `$content)

# Run the setup script in WSL
wsl -d Ubuntu -e bash /mnt/c/Windows/Temp/wsl-setup.sh

# Clean up the key from Windows temp (it's now in WSL)
# Remove-Item "C:\Windows\Temp\teamserver_key.pem" -Force -ErrorAction SilentlyContinue

Write-Host "WSL2 configuration complete!"
"@
    
    $wslSetupScript | Out-File -FilePath "C:\Windows\Temp\wsl-post-reboot.ps1" -Encoding UTF8
    
    # Schedule the post-reboot script
    $action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-ExecutionPolicy Bypass -File C:\Windows\Temp\wsl-post-reboot.ps1"
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    Register-ScheduledTask -TaskName "WSL2-Setup" -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
    
    Write-Log "WSL2 post-reboot setup scheduled"
    
} catch {
    Write-Log "Warning: WSL2 setup encountered issues: $_"
}

# =============================================================================
# 8. Create Helper Scripts
# =============================================================================
Write-Log "[8/8] Creating helper scripts..."

# PowerShell profile with tool imports
$profileContent = @'
# Attack Box PowerShell Profile
# =============================

Write-Host "=== Windows Attack Box ===" -ForegroundColor Cyan
Write-Host "Team Server: TEAMSERVER_IP:TEAMSERVER_PORT" -ForegroundColor Yellow
Write-Host ""
Write-Host "Quick Commands:" -ForegroundColor Green
Write-Host "  Import-PowerView    - Load PowerView for AD enum"
Write-Host "  Import-PowerUp      - Load PowerUp for privesc"
Write-Host "  Connect-TeamServer  - Instructions to connect CS"
Write-Host "  wsl                 - Open WSL Ubuntu (ssh teamserver)"
Write-Host ""

function Import-PowerView {
    Import-Module C:\Tools\PowerSploit\Recon\PowerView.ps1
    Write-Host "PowerView loaded! Try: Get-DomainUser" -ForegroundColor Green
}

function Import-PowerUp {
    Import-Module C:\Tools\PowerSploit\Privesc\PowerUp.ps1
    Write-Host "PowerUp loaded! Try: Invoke-AllChecks" -ForegroundColor Green
}

function Connect-TeamServer {
    Write-Host ""
    Write-Host "=== Cobalt Strike Connection ===" -ForegroundColor Cyan
    Write-Host "1. Open WSL terminal: wsl" -ForegroundColor Yellow
    Write-Host "2. SSH to Team Server: ssh teamserver" -ForegroundColor Yellow
    Write-Host "3. Or launch CS Client and connect to:" -ForegroundColor Yellow
    Write-Host "   Host: TEAMSERVER_IP" -ForegroundColor White
    Write-Host "   Port: TEAMSERVER_PORT" -ForegroundColor White
    Write-Host ""
}

# Set execution policy for this session
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force
'@

$profileContent = $profileContent -replace 'TEAMSERVER_IP', $TeamServerIP
$profileContent = $profileContent -replace 'TEAMSERVER_PORT', $TeamServerPort

# Create profile directory and file
$profileDir = Split-Path $PROFILE -Parent
if (-not (Test-Path $profileDir)) {
    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
}
$profileContent | Out-File -FilePath $PROFILE -Encoding UTF8

# Create desktop shortcut for tools
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("C:\Users\Administrator\Desktop\Tools.lnk")
$Shortcut.TargetPath = "C:\Tools"
$Shortcut.Save()

# Create desktop shortcut for WSL
$Shortcut2 = $WshShell.CreateShortcut("C:\Users\Administrator\Desktop\WSL Ubuntu.lnk")
$Shortcut2.TargetPath = "wsl.exe"
$Shortcut2.Arguments = "-d Ubuntu"
$Shortcut2.Save()

# Create comprehensive README on Desktop
$desktopReadme = @"
================================================================================
                    WINDOWS ATTACK BOX - QUICK START GUIDE
================================================================================

ROLE: Red Team Attack Workstation (CS Client + Offensive Tools)

================================================================================
                              SSH KEY INFORMATION
================================================================================

This machine has an INTERNAL SSH key installed for accessing the Team Server.
The key is located at:

  Windows: C:\Windows\Temp\teamserver_key.pem
  WSL:     ~/.ssh/teamserver_key

IMPORTANT SECURITY NOTE:
  - This INTERNAL key can ONLY access the Team Server
  - This key CANNOT access the Jumpbox (different key!)
  - This key CANNOT access your local machine

================================================================================
                            CONNECTING TO TEAM SERVER
================================================================================

OPTION 1: Via WSL (Recommended)
  1. Open WSL: Click 'WSL Ubuntu' shortcut or run: wsl
  2. Connect:  ssh teamserver   (or: ssh ts)

OPTION 2: From PowerShell
  Run: Connect-TeamServer (shows instructions)

================================================================================
                              COBALT STRIKE CLIENT
================================================================================

To run Cobalt Strike Client from this machine:
  1. Download/copy your cobaltstrike folder to C:\Tools\
  2. Run: java -jar C:\Tools\cobaltstrike\cobaltstrike.jar
  3. Connect to:
     - Host: $TeamServerIP
     - Port: $TeamServerPort
     - Password: (from deployment)

================================================================================
                              OFFENSIVE TOOLS
================================================================================

PowerSploit Location: C:\Tools\PowerSploit\

Quick Import Commands (in PowerShell):
  Import-PowerView    - AD enumeration (Get-DomainUser, etc.)
  Import-PowerUp      - Privilege escalation checks

Sharp Tools: C:\Tools\SharpTools\ (add your compiled tools)

================================================================================
                              NETWORK ACCESS
================================================================================

From this Attack Box, you can reach:

  Team Server:     $TeamServerIP (SSH via WSL, CS port $TeamServerPort)
  GOAD AD VMs:     192.168.56.10-25 (DC01, DC02, Servers)
  
You CANNOT directly reach:
  Jumpbox:         (no key, different trust boundary)
  Internet:        (private subnet, NAT only for outbound)

================================================================================
                              TROUBLESHOOTING
================================================================================

WSL not working?
  - Wait 2-3 minutes after first login for setup to complete
  - Run: wsl --status
  - Check: C:\Windows\Temp\wsl-post-reboot.ps1 log

SSH key permission denied?
  - In WSL, run: chmod 600 ~/.ssh/teamserver_key
  - Check key exists: ls -la ~/.ssh/

Can't reach Team Server?
  - Check Team Server is running: ping $TeamServerIP
  - Verify CS port: nc -zv $TeamServerIP $TeamServerPort

================================================================================
                              CREDENTIALS
================================================================================

This Attack Box:
  User: Administrator
  Pass: $AdminPassword

Team Server SSH:
  User: ubuntu
  Key:  ~/.ssh/teamserver_key (in WSL)

================================================================================
Created by Red Team Infrastructure Deployment Tool
================================================================================
"@

$desktopReadme | Out-File -FilePath "C:\Users\Administrator\Desktop\README - ATTACK BOX.txt" -Encoding UTF8
Write-Log "Desktop README created"

Write-Log "Helper scripts and shortcuts created"

# =============================================================================
# Complete
# =============================================================================
Write-Log ""
Write-Log "=============================================="
Write-Log "Attack Box Initialization Complete!"
Write-Log "Finished: $(Get-Date)"
Write-Log "=============================================="
Write-Log ""
Write-Log "=== Tools Installed ==="
Write-Log "  PowerSploit: C:\Tools\PowerSploit\"
Write-Log "  Sharp Tools: C:\Tools\SharpTools\ (add your compiled tools)"
Write-Log ""
Write-Log "=== Team Server Connection ==="
Write-Log "  IP: $TeamServerIP"
Write-Log "  Port: $TeamServerPort"
Write-Log ""
Write-Log "=== WSL2 ==="
Write-Log "  After reboot, WSL2 will be configured"
Write-Log "  Use: wsl -> ssh teamserver"
Write-Log ""
Write-Log "A reboot is required to complete WSL2 setup."

# Create completion marker
"Installation completed at $(Get-Date)" | Out-File -FilePath "C:\Tools\.install-complete" -Encoding UTF8

# Reboot to complete WSL installation
Write-Log "Scheduling reboot in 60 seconds..."
shutdown /r /t 60 /c "Attack Box setup complete. Rebooting to finish WSL2 installation."
</powershell>

