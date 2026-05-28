<powershell>
# =============================================================================
# CCRTS Lab — AD-Joined Workstation First-Boot (ad-ws01)
# =============================================================================
# Renames, points DNS at the DC, joins ccrts.local with the supplied admin
# credentials, installs Sysmon. Domain-join retries because the DC promotion
# may still be finishing.
# =============================================================================
$ErrorActionPreference = "Continue"
$LogPath = "C:\ProgramData\ccrts-adws-init.log"
Start-Transcript -Path $LogPath -Append -Force | Out-Null

Write-Host "=== CCRTS AD Workstation first-boot $(Get-Date) ==="

$DesiredHostname = "${hostname}"
$Domain          = "${domain}"
$NetBIOS         = "${netbios}"
$AdminPassword   = "${admin_password}"
$DCPrivateIP     = "${dc_private_ip}"
$JoinUser        = "${join_user}"
$JoinPassword    = "${join_password}"

# -----------------------------------------------------------------------------
# Hostname
# -----------------------------------------------------------------------------
$CurrentHostname = $env:COMPUTERNAME
if ($CurrentHostname -ne $DesiredHostname) {
    Write-Host "Renaming computer: $CurrentHostname -> $DesiredHostname"
    Rename-Computer -NewName $DesiredHostname -Force -ErrorAction SilentlyContinue
}

# -----------------------------------------------------------------------------
# Local Administrator password
# -----------------------------------------------------------------------------
try {
    $SecurePassword = ConvertTo-SecureString $AdminPassword -AsPlainText -Force
    Get-LocalUser -Name "Administrator" | Set-LocalUser -Password $SecurePassword
    Enable-LocalUser -Name "Administrator"
} catch {
    Write-Host "Error setting admin password: $_"
}

# -----------------------------------------------------------------------------
# PSRemoting + WinRM HTTPS
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
# Enable RDP
# -----------------------------------------------------------------------------
try {
    Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -Name "fDenyTSConnections" -Value 0
    Enable-NetFirewallRule -DisplayGroup "Remote Desktop"
} catch {
    Write-Host "Error enabling RDP: $_"
}

# -----------------------------------------------------------------------------
# Point DNS at the DC
# -----------------------------------------------------------------------------
try {
    $IfIndex = (Get-NetAdapter | Where-Object { $_.Status -eq "Up" } | Select-Object -First 1).ifIndex
    if ($IfIndex) {
        Set-DnsClientServerAddress -InterfaceIndex $IfIndex -ServerAddresses ($DCPrivateIP)
        Write-Host "DNS pointed at DC: $DCPrivateIP"
    }
} catch {
    Write-Host "Error setting DNS: $_"
}

# -----------------------------------------------------------------------------
# Domain join — retry up to ~20 minutes because the DC promotion + reboot can
# take a while on first boot.
# -----------------------------------------------------------------------------
$IsJoined = ((Get-WmiObject Win32_ComputerSystem).PartOfDomain) -and ((Get-WmiObject Win32_ComputerSystem).Domain -eq $Domain)

if (-not $IsJoined) {
    $JoinSecure = ConvertTo-SecureString $JoinPassword -AsPlainText -Force
    $JoinCred   = New-Object System.Management.Automation.PSCredential ("$NetBIOS\$JoinUser", $JoinSecure)

    $Joined = $false
    for ($i = 0; $i -lt 40; $i++) {
        try {
            Add-Computer -DomainName $Domain -Credential $JoinCred -Force -ErrorAction Stop
            $Joined = $true
            Write-Host "Domain join succeeded on attempt $($i + 1)"
            break
        } catch {
            Write-Host "Domain join attempt $($i + 1) failed: $_"
            Start-Sleep -Seconds 30
        }
    }

    if (-not $Joined) {
        Write-Host "WARNING: Domain join did not succeed within retry window. Will retry on next boot."
    }
}

# -----------------------------------------------------------------------------
# Sysmon + SwiftOnSecurity
# -----------------------------------------------------------------------------
try {
    $SysmonZip = "$env:TEMP\Sysmon.zip"
    $SysmonDir = "C:\Program Files\Sysmon"
    $SysmonCfg = "$SysmonDir\sysmonconfig.xml"

    New-Item -ItemType Directory -Path $SysmonDir -Force | Out-Null
    Invoke-WebRequest -Uri "https://download.sysinternals.com/files/Sysmon.zip" -OutFile $SysmonZip -UseBasicParsing
    Expand-Archive -Path $SysmonZip -DestinationPath $SysmonDir -Force
    Invoke-WebRequest `
        -Uri "https://raw.githubusercontent.com/SwiftOnSecurity/sysmon-config/master/sysmonconfig-export.xml" `
        -OutFile $SysmonCfg -UseBasicParsing
    & "$SysmonDir\Sysmon64.exe" -accepteula -i $SysmonCfg 2>&1 | Out-Null
    Write-Host "Sysmon installed"
} catch {
    Write-Host "Error installing Sysmon: $_"
}

# -----------------------------------------------------------------------------
# Marker
# -----------------------------------------------------------------------------
New-Item -ItemType Directory -Path "C:\ProgramData\CCRTS" -Force | Out-Null
"ccrts-adws-init: ok $(Get-Date)" | Out-File -FilePath "C:\ProgramData\CCRTS\init.status" -Force

Write-Host "=== CCRTS AD Workstation first-boot complete $(Get-Date) ==="
Stop-Transcript | Out-Null

Restart-Computer -Force
</powershell>
<persist>true</persist>
