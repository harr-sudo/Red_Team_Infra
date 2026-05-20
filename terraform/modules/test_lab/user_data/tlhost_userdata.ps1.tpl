<powershell>
# =============================================================================
# Test Lab — Generic Windows Host First-Boot (tlms01, tlws01)
# =============================================================================
# Minimal user-data: rename host, enable WinRM HTTPS, point DNS at tldc01.
# Domain-join, IIS, ADCS sub-features, Office trial, and macro context all
# come later via Ansible (testlab_join.yml + testlab_member.yml /
# testlab_workstation.yml).
# =============================================================================

$ErrorActionPreference = "Continue"
$LogPath = "C:\ProgramData\testlab-userdata.log"
Start-Transcript -Path $LogPath -Append -Force | Out-Null

Write-Host "=== Test Lab ${hostname} (role=${role}) first-boot ==="
Write-Host "Started: $(Get-Date)"

# -----------------------------------------------------------------------------
# Hostname
# -----------------------------------------------------------------------------
$DesiredHostname = "${hostname}"
$CurrentHostname = $env:COMPUTERNAME
if ($CurrentHostname -ne $DesiredHostname) {
    Write-Host "Renaming computer: $CurrentHostname -> $DesiredHostname"
    Rename-Computer -NewName $DesiredHostname -Force -ErrorAction SilentlyContinue
}

# -----------------------------------------------------------------------------
# Local Administrator password (LAB ONLY — intentionally weak)
# -----------------------------------------------------------------------------
$AdminPassword = ConvertTo-SecureString "${admin_password}" -AsPlainText -Force
Get-LocalUser -Name "Administrator" | Set-LocalUser -Password $AdminPassword
Enable-LocalUser -Name "Administrator"

# -----------------------------------------------------------------------------
# WinRM HTTPS — so Ansible can drive this host from the jumpbox.
# Self-signed cert is fine for the lab.
# -----------------------------------------------------------------------------
Write-Host "Configuring WinRM..."
winrm quickconfig -quiet -force | Out-Null

$Cert = New-SelfSignedCertificate `
    -DnsName $DesiredHostname, "$DesiredHostname.testlab.local" `
    -CertStoreLocation "Cert:\LocalMachine\My" `
    -NotAfter (Get-Date).AddYears(5)

$ListenerCmd = 'winrm create winrm/config/Listener?Address=*+Transport=HTTPS ' +
    "'@{Hostname=`"$DesiredHostname`"; CertificateThumbprint=`"$($Cert.Thumbprint)`"}'"
cmd /c $ListenerCmd 2>&1 | Out-Null

winrm set winrm/config/service/auth '@{Basic="true"}' | Out-Null
winrm set winrm/config/service '@{AllowUnencrypted="false"}' | Out-Null

New-NetFirewallRule -DisplayName "WinRM HTTPS" -Direction Inbound -LocalPort 5986 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null
New-NetFirewallRule -DisplayName "WinRM HTTP"  -Direction Inbound -LocalPort 5985 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null

# -----------------------------------------------------------------------------
# DNS — point at tldc01 so the domain-join playbook can resolve testlab.local.
# Before tldc01 is promoted this resolver will fail; that is fine, Ansible
# orchestrates the order.
# -----------------------------------------------------------------------------
$IfIndex = (Get-NetAdapter | Where-Object { $_.Status -eq "Up" } | Select-Object -First 1).ifIndex
if ($IfIndex) {
    Set-DnsClientServerAddress -InterfaceIndex $IfIndex -ServerAddresses ("${dc_private_ip}") -ErrorAction SilentlyContinue
}

Write-Host "First-boot setup complete: $(Get-Date)"
Stop-Transcript | Out-Null

if ($CurrentHostname -ne $DesiredHostname) {
    Restart-Computer -Force
}
</powershell>
<persist>true</persist>
