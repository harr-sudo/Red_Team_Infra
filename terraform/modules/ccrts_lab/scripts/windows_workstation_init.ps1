<powershell>
# =============================================================================
# CCRTS Lab — Windows Workstation (CREST AMI) First-Boot
# =============================================================================
# CREST AMI ships with most tooling pre-baked. This script:
#   - Renames the host
#   - Sets the local Administrator password from the tfvar
#   - Enables PowerShell Remoting + WinRM HTTPS
#   - Installs Sysmon + the SwiftOnSecurity config
# Domain-join is NOT done here — this workstation (windows-ws) stays
# workgroup-only. The AD-joined workstation (ad-ws01) is a separate host
# provisioned via ad_ws_init.ps1.
# =============================================================================
$ErrorActionPreference = "Continue"
$LogPath = "C:\ProgramData\ccrts-ws-init.log"
Start-Transcript -Path $LogPath -Append -Force | Out-Null

Write-Host "=== CCRTS Windows Workstation first-boot $(Get-Date) ==="

$DesiredHostname = "${hostname}"
$AdminPassword   = "${admin_password}"

# -----------------------------------------------------------------------------
# Hostname
# -----------------------------------------------------------------------------
$CurrentHostname = $env:COMPUTERNAME
if ($CurrentHostname -ne $DesiredHostname) {
    Write-Host "Renaming computer: $CurrentHostname -> $DesiredHostname"
    Rename-Computer -NewName $DesiredHostname -Force -ErrorAction SilentlyContinue
}

# -----------------------------------------------------------------------------
# Administrator password
# -----------------------------------------------------------------------------
try {
    $SecurePassword = ConvertTo-SecureString $AdminPassword -AsPlainText -Force
    Get-LocalUser -Name "Administrator" | Set-LocalUser -Password $SecurePassword
    Enable-LocalUser -Name "Administrator"
    Write-Host "Administrator password set"
} catch {
    Write-Host "Error setting admin password: $_"
}

# -----------------------------------------------------------------------------
# Enable PowerShell Remoting + WinRM HTTPS
# -----------------------------------------------------------------------------
try {
    Enable-PSRemoting -Force -SkipNetworkProfileCheck | Out-Null
    winrm quickconfig -quiet -force | Out-Null

    $Cert = New-SelfSignedCertificate `
        -DnsName $DesiredHostname `
        -CertStoreLocation "Cert:\LocalMachine\My" `
        -NotAfter (Get-Date).AddYears(5)

    $ListenerCmd = 'winrm create winrm/config/Listener?Address=*+Transport=HTTPS ' +
        "'@{Hostname=`"$DesiredHostname`"; CertificateThumbprint=`"$($Cert.Thumbprint)`"}'"
    cmd /c $ListenerCmd 2>&1 | Out-Null

    winrm set winrm/config/service/auth '@{Basic="true"}' | Out-Null
    winrm set winrm/config/service '@{AllowUnencrypted="false"}' | Out-Null

    New-NetFirewallRule -DisplayName "WinRM HTTPS" -Direction Inbound -LocalPort 5986 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null
    New-NetFirewallRule -DisplayName "WinRM HTTP"  -Direction Inbound -LocalPort 5985 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null

    Write-Host "PSRemoting + WinRM HTTPS configured"
} catch {
    Write-Host "Error configuring WinRM: $_"
}

# -----------------------------------------------------------------------------
# Enable RDP
# -----------------------------------------------------------------------------
try {
    Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -Name "fDenyTSConnections" -Value 0
    Enable-NetFirewallRule -DisplayGroup "Remote Desktop"
} catch {
    Write-Host "Error enabling RDP: $_"
}

# -----------------------------------------------------------------------------
# Sysmon + SwiftOnSecurity config — ships telemetry to the ELK host
# -----------------------------------------------------------------------------
try {
    $SysmonZip   = "$env:TEMP\Sysmon.zip"
    $SysmonDir   = "C:\Program Files\Sysmon"
    $SysmonCfg   = "$SysmonDir\sysmonconfig.xml"

    New-Item -ItemType Directory -Path $SysmonDir -Force | Out-Null

    Invoke-WebRequest -Uri "https://download.sysinternals.com/files/Sysmon.zip" -OutFile $SysmonZip -UseBasicParsing
    Expand-Archive -Path $SysmonZip -DestinationPath $SysmonDir -Force

    Invoke-WebRequest `
        -Uri "https://raw.githubusercontent.com/SwiftOnSecurity/sysmon-config/master/sysmonconfig-export.xml" `
        -OutFile $SysmonCfg -UseBasicParsing

    & "$SysmonDir\Sysmon64.exe" -accepteula -i $SysmonCfg 2>&1 | Out-Null
    Write-Host "Sysmon installed with SwiftOnSecurity config"
} catch {
    Write-Host "Error installing Sysmon: $_"
}

# -----------------------------------------------------------------------------
# Marker
# -----------------------------------------------------------------------------
New-Item -ItemType Directory -Path "C:\ProgramData\CCRTS" -Force | Out-Null
"ccrts-ws-init: ok $(Get-Date)" | Out-File -FilePath "C:\ProgramData\CCRTS\init.status" -Force

Write-Host "=== CCRTS Windows Workstation first-boot complete $(Get-Date) ==="
Stop-Transcript | Out-Null

if ($CurrentHostname -ne $DesiredHostname) {
    Restart-Computer -Force
}
</powershell>
<persist>true</persist>
