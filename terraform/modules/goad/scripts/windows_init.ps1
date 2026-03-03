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
Write-Host "[1/7] Setting hostname to: $Hostname"
try {
    Rename-Computer -NewName $Hostname -Force -ErrorAction SilentlyContinue
    Write-Host "Hostname set successfully"
} catch {
    Write-Host "Note: Hostname may already be set or requires reboot"
}

# =============================================================================
# 2. Configure Administrator Account (rename to goadmin per upstream GOAD)
# =============================================================================
Write-Host "[2/7] Configuring administrator account..."
try {
    $SecurePassword = ConvertTo-SecureString $Password -AsPlainText -Force
    Set-LocalUser -Name "Administrator" -Password $SecurePassword -PasswordNeverExpires $true
    Enable-LocalUser -Name "Administrator"

    # Rename Administrator to goadmin (upstream GOAD expects admin_user=goadmin)
    Rename-LocalUser -Name "Administrator" -NewName $Username
    Write-Host "Administrator renamed to: $Username"
} catch {
    Write-Host "Error configuring administrator: $_"
}

# =============================================================================
# 3. Create Ansible User (required for upstream GOAD Ansible playbooks)
# =============================================================================
Write-Host "[3/7] Creating ansible user for GOAD provisioning..."
try {
    $AnsibleExists = Get-LocalUser -Name "ansible" -ErrorAction SilentlyContinue
    if (-not $AnsibleExists) {
        net user ansible $Password /add /expires:never /y
        net localgroup administrators ansible /add
        Write-Host "Created ansible user (password same as admin)"
    } else {
        Write-Host "Ansible user already exists"
    }
} catch {
    Write-Host "Error creating ansible user: $_"
}

# =============================================================================
# 4. Configure WinRM for Ansible
# =============================================================================
Write-Host "[4/7] Configuring WinRM for Ansible..."
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
# 5. Configure Firewall
# =============================================================================
Write-Host "[5/7] Configuring firewall..."
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
# 6. Enable RDP
# =============================================================================
Write-Host "[6/7] Enabling Remote Desktop..."
try {
    Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -Name "fDenyTSConnections" -Value 0
    Enable-NetFirewallRule -DisplayGroup "Remote Desktop"
    Write-Host "Remote Desktop enabled"
} catch {
    Write-Host "Error enabling RDP: $_"
}

# =============================================================================
# 7. Configure DNS Suffix (for domain discovery by Ansible)
# =============================================================================
Write-Host "[7/7] Configuring DNS suffix..."
try {
    # Set connection-specific DNS suffix on the primary network adapter
    $Adapter = Get-NetAdapter | Where-Object { $_.Status -eq "Up" } | Select-Object -First 1
    if ($Adapter) {
        Set-DnsClient -InterfaceIndex $Adapter.ifIndex -ConnectionSpecificSuffix $Domain
        Write-Host "DNS suffix set to: $Domain on adapter $($Adapter.Name)"
    }
    Set-DnsClientGlobalSetting -SuffixSearchList @($Domain)
    Write-Host "DNS suffix search list configured"
} catch {
    Write-Host "Error configuring DNS suffix: $_"
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

