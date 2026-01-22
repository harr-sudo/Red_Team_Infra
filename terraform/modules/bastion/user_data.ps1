# PowerShell User Data Script for Windows Bastion with WSL2
# This script configures Windows Server and installs WSL2 with Ubuntu

<powershell>
# Set execution policy
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Force

# Set hostname
$Hostname = "${hostname}"
if ($Hostname) {
    Write-Host "Setting hostname to: $Hostname"
    try {
        Rename-Computer -NewName $Hostname -Force -ErrorAction SilentlyContinue
        Write-Host "Hostname set successfully (will apply after reboot)"
    } catch {
        Write-Host "Error setting hostname: $_"
    }
}

# Enable WSL feature
Write-Host "Enabling WSL feature..."
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux -NoRestart

# Enable Virtual Machine Platform (required for WSL2)
Write-Host "Enabling Virtual Machine Platform..."
Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform -NoRestart

# Download and install WSL2 kernel update
Write-Host "Downloading WSL2 kernel update..."
$wslUpdateUrl = "https://wslstorestorage.blob.core.windows.net/wslblob/wsl_update_x64.msi"
$wslUpdatePath = "$env:TEMP\wsl_update_x64.msi"
Invoke-WebRequest -Uri $wslUpdateUrl -OutFile $wslUpdatePath
Start-Process msiexec.exe -ArgumentList "/i $wslUpdatePath /quiet /norestart" -Wait

# Set WSL2 as default version
Write-Host "Setting WSL2 as default version..."
wsl --set-default-version 2

# Install Ubuntu from Microsoft Store (using winget or direct download)
Write-Host "Installing Ubuntu for WSL2..."
# Note: This requires manual installation or using winget
# For automated installation, you may need to download Ubuntu appx package
# Alternative: Use winget if available
try {
    winget install --id Canonical.Ubuntu.2204.LTS --silent --accept-package-agreements --accept-source-agreements
} catch {
    Write-Host "Winget not available, Ubuntu installation may need to be done manually"
    Write-Host "After first login, run: wsl --install -d Ubuntu"
}

# Configure Windows Firewall for RDP (if not already configured)
Write-Host "Configuring Windows Firewall..."
netsh advfirewall firewall add rule name="RDP" dir=in action=allow protocol=TCP localport=3389

# Set timezone (optional - adjust as needed)
Write-Host "Setting timezone..."
tzutil /s "UTC"

# Install Chocolatey (optional package manager)
Write-Host "Installing Chocolatey..."
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# Install useful tools via Chocolatey
Write-Host "Installing useful tools..."
choco install -y git openssh putty winscp -y

# Configure SSH server (optional - for SSH access to Windows)
Write-Host "Configuring OpenSSH Server..."
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service -Name sshd -StartupType 'Automatic'

# Create a log file
$logPath = "C:\Windows\Temp\bastion-setup.log"
Write-Host "Bastion setup completed. Log saved to: $logPath" | Out-File -FilePath $logPath -Append

# Note: WSL2 Ubuntu will need to be configured on first launch
# User will need to:
# 1. Open WSL2 Ubuntu
# 2. Create user account
# 3. Install SSH client if needed
# 4. Configure SSH keys for access to C2 servers

Write-Host "Bastion setup script completed!"
Write-Host "Note: WSL2 Ubuntu may need manual configuration on first use"
</powershell>

