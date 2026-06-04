<powershell>
# =============================================================================
# CCRTS Lab — Domain Controller First-Boot (dc01.ccrts.local)
# =============================================================================
# Promotes this host to a domain controller for ccrts.local / CCRTS netbios,
# then creates the lab user accounts. Idempotent: if AD DS is already
# installed it skips promotion.
# =============================================================================
$ErrorActionPreference = "Continue"
$LogPath = "C:\ProgramData\ccrts-dc-init.log"
Start-Transcript -Path $LogPath -Append -Force | Out-Null

Write-Host "=== CCRTS DC first-boot $(Get-Date) ==="

$DesiredHostname  = "${hostname}"
$Domain           = "${domain}"
$NetBIOS          = "${netbios}"
$AdminPassword    = "${admin_password}"
$LowPrivPassword  = "${low_priv_password}"

# -----------------------------------------------------------------------------
# Hostname
# -----------------------------------------------------------------------------
$CurrentHostname = $env:COMPUTERNAME
if ($CurrentHostname -ne $DesiredHostname) {
    Write-Host "Renaming computer: $CurrentHostname -> $DesiredHostname"
    Rename-Computer -NewName $DesiredHostname -Force -ErrorAction SilentlyContinue
}

# -----------------------------------------------------------------------------
# Administrator password (used as DSRM password and as the domain
# administrator password once promoted)
# -----------------------------------------------------------------------------
try {
    $SecurePassword = ConvertTo-SecureString $AdminPassword -AsPlainText -Force
    Get-LocalUser -Name "Administrator" | Set-LocalUser -Password $SecurePassword
    Enable-LocalUser -Name "Administrator"
} catch {
    Write-Host "Error setting admin password: $_"
}

# -----------------------------------------------------------------------------
# Enable PSRemoting + WinRM HTTPS so Ansible / operator can drive this host
# -----------------------------------------------------------------------------
try {
    Enable-PSRemoting -Force -SkipNetworkProfileCheck | Out-Null
    winrm quickconfig -quiet -force | Out-Null
    winrm set winrm/config/service/auth '@{Basic="true"}' | Out-Null

    New-NetFirewallRule -DisplayName "WinRM HTTPS" -Direction Inbound -LocalPort 5986 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null
    New-NetFirewallRule -DisplayName "WinRM HTTP"  -Direction Inbound -LocalPort 5985 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null
} catch {
    Write-Host "Error configuring WinRM: $_"
}

# -----------------------------------------------------------------------------
# AD DS install + promotion
# -----------------------------------------------------------------------------
$ADInstalled = (Get-WindowsFeature AD-Domain-Services).Installed
if (-not $ADInstalled) {
    Write-Host "Installing AD DS role..."
    Install-WindowsFeature AD-Domain-Services -IncludeManagementTools | Out-Null
}

$IsPromoted = $false
try {
    Import-Module ADDSDeployment -ErrorAction Stop
    $IsPromoted = ((Get-WmiObject Win32_ComputerSystem).PartOfDomain) -and ($env:USERDOMAIN -eq $NetBIOS)
} catch {
    $IsPromoted = $false
}

if (-not $IsPromoted) {
    Write-Host "Promoting host to DC for $Domain ($NetBIOS)..."
    $DSRMPassword = ConvertTo-SecureString $AdminPassword -AsPlainText -Force
    try {
        Install-ADDSForest `
            -DomainName $Domain `
            -DomainNetbiosName $NetBIOS `
            -DomainMode "WinThreshold" `
            -ForestMode "WinThreshold" `
            -InstallDns:$true `
            -SafeModeAdministratorPassword $DSRMPassword `
            -NoRebootOnCompletion:$true `
            -Force:$true | Out-Null
        Write-Host "AD DS promotion staged. Reboot required."

        # Stage post-reboot user creation via RunOnce so we don't lose it on reboot.
        $UserCreateScript = @"
`$ErrorActionPreference = 'Continue'
Start-Transcript -Path 'C:\ProgramData\ccrts-dc-users.log' -Append -Force | Out-Null
Write-Host '=== CCRTS DC post-reboot user setup ==='

# Wait until AD Web Services is responsive
for (`$i = 0; `$i -lt 60; `$i++) {
    try {
        Get-ADDomain -ErrorAction Stop | Out-Null
        break
    } catch {
        Start-Sleep -Seconds 10
    }
}

`$LowPrivSecure = ConvertTo-SecureString '$LowPrivPassword' -AsPlainText -Force
if (-not (Get-ADUser -Filter "SamAccountName -eq 'jdoe'" -ErrorAction SilentlyContinue)) {
    New-ADUser -Name 'John Doe' `
               -SamAccountName 'jdoe' `
               -UserPrincipalName 'jdoe@$Domain' `
               -AccountPassword `$LowPrivSecure `
               -Enabled `$true `
               -PasswordNeverExpires `$true `
               -Description 'CCRTS lab low-privilege user'
    Write-Host 'Created CCRTS\jdoe'
}

New-Item -ItemType Directory -Path 'C:\ProgramData\CCRTS' -Force | Out-Null
"ccrts-dc-init: ok `$(Get-Date)" | Out-File 'C:\ProgramData\CCRTS\init.status' -Force

Stop-Transcript | Out-Null
"@
        $UserCreateScriptPath = "C:\ProgramData\ccrts-dc-post-reboot.ps1"
        $UserCreateScript | Out-File -FilePath $UserCreateScriptPath -Force -Encoding ASCII

        $RunOnceKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"
        Set-ItemProperty -Path $RunOnceKey -Name "CCRTSDCPostReboot" `
            -Value "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$UserCreateScriptPath`""
    } catch {
        Write-Host "Error during AD DS promotion: $_"
    }
} else {
    Write-Host "Already promoted, skipping AD DS install."
}

# -----------------------------------------------------------------------------
# Marker (intermediate — the post-reboot script overwrites with the final OK)
# -----------------------------------------------------------------------------
New-Item -ItemType Directory -Path "C:\ProgramData\CCRTS" -Force | Out-Null
"ccrts-dc-init: provision-staged $(Get-Date)" | Out-File -FilePath "C:\ProgramData\CCRTS\init.status" -Force

Write-Host "=== CCRTS DC first-boot complete $(Get-Date) ==="
Stop-Transcript | Out-Null

# Force the reboot so promotion finalizes.
Restart-Computer -Force
</powershell>
<persist>true</persist>
