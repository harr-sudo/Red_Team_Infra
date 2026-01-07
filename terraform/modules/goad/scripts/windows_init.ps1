<powershell>
# =============================================================================
# GOAD Windows VM Initialization Script
# =============================================================================
# Sets up Windows Server for GOAD Active Directory lab
# Variables are passed via Terraform templatefile()
# =============================================================================

$ErrorActionPreference = "Continue"

# Variables from Terraform
$Username = "${username}"
$Password = "${password}"
$Domain = "${domain}"
$Hostname = "${hostname}"

# Logging
$LogFile = "C:\Windows\Temp\goad-init.log"
Start-Transcript -Path $LogFile -Append

Write-Host "=============================================="
Write-Host "GOAD Windows VM Initialization"
Write-Host "Started: $(Get-Date)"
Write-Host "Hostname: $Hostname"
Write-Host "Domain: $Domain"
Write-Host "=============================================="

# =============================================================================
# 1. Set Hostname
# =============================================================================
Write-Host "[1/5] Setting hostname to: $Hostname"
try {
    Rename-Computer -NewName $Hostname -Force -ErrorAction SilentlyContinue
    Write-Host "Hostname set successfully"
} catch {
    Write-Host "Note: Hostname may already be set or requires reboot"
}

# =============================================================================
# 2. Configure Administrator Account
# =============================================================================
Write-Host "[2/5] Configuring administrator account..."
try {
    $SecurePassword = ConvertTo-SecureString $Password -AsPlainText -Force
    Set-LocalUser -Name "Administrator" -Password $SecurePassword -PasswordNeverExpires $true
    Enable-LocalUser -Name "Administrator"
    Write-Host "Administrator account configured"
} catch {
    Write-Host "Error configuring administrator: $_"
}

# Create additional admin user if specified
if ($Username -ne "Administrator" -and $Username -ne "") {
    try {
        $UserExists = Get-LocalUser -Name $Username -ErrorAction SilentlyContinue
        if (-not $UserExists) {
            New-LocalUser -Name $Username -Password $SecurePassword -PasswordNeverExpires -AccountNeverExpires
            Add-LocalGroupMember -Group "Administrators" -Member $Username
            Write-Host "Created user: $Username"
        }
    } catch {
        Write-Host "Error creating user: $_"
    }
}

# =============================================================================
# 3. Configure WinRM for Ansible
# =============================================================================
Write-Host "[3/5] Configuring WinRM for Ansible..."
try {
    # Enable WinRM
    winrm quickconfig -q
    winrm set winrm/config/service '@{AllowUnencrypted="true"}'
    winrm set winrm/config/service/auth '@{Basic="true"}'
    winrm set winrm/config/winrs '@{MaxMemoryPerShellMB="1024"}'
    
    # Set WinRM to start automatically
    Set-Service -Name WinRM -StartupType Automatic
    Start-Service WinRM
    
    Write-Host "WinRM configured successfully"
} catch {
    Write-Host "Error configuring WinRM: $_"
}

# =============================================================================
# 4. Configure Firewall
# =============================================================================
Write-Host "[4/5] Configuring firewall..."
try {
    # Allow WinRM
    netsh advfirewall firewall add rule name="WinRM HTTP" dir=in action=allow protocol=TCP localport=5985
    netsh advfirewall firewall add rule name="WinRM HTTPS" dir=in action=allow protocol=TCP localport=5986
    
    # Allow RDP
    netsh advfirewall firewall add rule name="RDP" dir=in action=allow protocol=TCP localport=3389
    
    # Allow ICMP
    netsh advfirewall firewall add rule name="ICMP Allow" dir=in action=allow protocol=icmpv4
    
    Write-Host "Firewall rules configured"
} catch {
    Write-Host "Error configuring firewall: $_"
}

# =============================================================================
# 5. Enable RDP
# =============================================================================
Write-Host "[5/5] Enabling Remote Desktop..."
try {
    Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -Name "fDenyTSConnections" -Value 0
    Enable-NetFirewallRule -DisplayGroup "Remote Desktop"
    Write-Host "Remote Desktop enabled"
} catch {
    Write-Host "Error enabling RDP: $_"
}

# =============================================================================
# Create marker file
# =============================================================================
$MarkerFile = "C:\Windows\Temp\.goad-init-complete"
Set-Content -Path $MarkerFile -Value "Initialized: $(Get-Date)"

Write-Host ""
Write-Host "=============================================="
Write-Host "GOAD Windows VM Initialization Complete!"
Write-Host "Finished: $(Get-Date)"
Write-Host "=============================================="
Write-Host ""
Write-Host "VM Details:"
Write-Host "  Hostname: $Hostname"
Write-Host "  Domain: $Domain"
Write-Host "  Username: $Username"
Write-Host ""

Stop-Transcript
</powershell>

