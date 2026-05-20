<powershell>
# =============================================================================
# Test Lab — Domain Controller First-Boot (tldc01)
# =============================================================================
# Minimal user-data. Just makes the host reachable so Ansible can do the heavy
# lifting (AD DS promotion, AD CS install, DNS config). Do NOT promote the DC
# here — that is the job of the testlab_dc.yml playbook.
# =============================================================================

$ErrorActionPreference = "Continue"
$LogPath = "C:\ProgramData\testlab-userdata.log"
Start-Transcript -Path $LogPath -Append -Force | Out-Null

Write-Host "=== Test Lab tldc01 first-boot ==="
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

# Allow Basic auth over HTTPS for Ansible
winrm set winrm/config/service/auth '@{Basic="true"}' | Out-Null
winrm set winrm/config/service '@{AllowUnencrypted="false"}' | Out-Null

New-NetFirewallRule -DisplayName "WinRM HTTPS" -Direction Inbound -LocalPort 5986 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null
New-NetFirewallRule -DisplayName "WinRM HTTP"  -Direction Inbound -LocalPort 5985 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null

# -----------------------------------------------------------------------------
# DNS — DC is its own DNS resolver once promoted; pre-seed loopback so first
# Ansible run can connect even before AD DS is installed. Ansible playbook
# will harden this later.
# -----------------------------------------------------------------------------
$IfIndex = (Get-NetAdapter | Where-Object { $_.Status -eq "Up" } | Select-Object -First 1).ifIndex
if ($IfIndex) {
    Set-DnsClientServerAddress -InterfaceIndex $IfIndex -ServerAddresses ("127.0.0.1","${dc_private_ip}") -ErrorAction SilentlyContinue
}

Write-Host "First-boot setup complete: $(Get-Date)"
Stop-Transcript | Out-Null

# Hostname rename requires a reboot to take effect; Ansible expects this host
# to be reachable as tldc01 so trigger it now.
if ($CurrentHostname -ne $DesiredHostname) {
    Restart-Computer -Force
}
</powershell>
<persist>true</persist>
