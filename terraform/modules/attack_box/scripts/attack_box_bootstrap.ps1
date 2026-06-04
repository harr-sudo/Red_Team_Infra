<powershell>
# Attack Box Bootstrap - Downloads and executes main init script from S3
# This lightweight bootstrap stays under the 16KB EC2 user_data limit
$ErrorActionPreference = "Continue"

# Variables from Terraform templatefile()
$DeploymentBucket = "${deployment_bucket}"
$DeploymentId = "${deployment_id}"
$AwsRegion = "${aws_region}"
$ScriptKey = "$DeploymentId/scripts/attack_box_init.ps1"
$SshPublicKey = "${ssh_public_key}"

# Create logs directory -- use C:\ProgramData during bootstrap because
# C:\Users\Administrator\Desktop may not exist yet when EC2Launch runs
# the user_data script as SYSTEM before the first interactive logon.
# The init script will copy logs to the Desktop later.
$LogDir = "C:\ProgramData\AttackBoxBootstrap"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$BootstrapLog = "$LogDir\bootstrap.log"

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    "$timestamp - $Message" | Out-File -Append $BootstrapLog
    Write-Host $Message
}

Write-Log "=== Attack Box Bootstrap Started ==="
Write-Log "Deployment Bucket: $DeploymentBucket"
Write-Log "Script Key: $ScriptKey"
Write-Log "AWS Region: $AwsRegion"

# =============================================================================
# INSTALL OPENSSH SERVER -- guarantees SSH access for debugging
# regardless of whether the main init script succeeds or fails
# =============================================================================
Write-Log "Installing OpenSSH Server (early install for SSH access)..."
try {
    # Install OpenSSH via GitHub portable ZIP.
    # Why not Windows Capability (Add-WindowsCapability -Online)?
    #   - Even with -LimitAccess, the CBS servicing stack hangs on fresh Windows Server 2022
    #   - Blocks the entire bootstrap for 10+ minutes with no timeout
    # Why not Install-WindowsFeature?
    #   - OpenSSH-Server feature doesn't exist on Windows Server 2022 (it's a Capability, not a Feature)
    # The GitHub ZIP method is fast, reliable, and only needs NAT gateway internet.
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $sshInstalled = $false
    $sshZipUrl = "https://github.com/PowerShell/Win32-OpenSSH/releases/latest/download/OpenSSH-Win64.zip"
    $sshZip = "$env:TEMP\OpenSSH-Win64.zip"
    $sshInstallDir = "C:\Program Files\OpenSSH-Win64"

    Write-Log "Downloading OpenSSH portable ZIP from GitHub..."
    try {
        (New-Object System.Net.WebClient).DownloadFile($sshZipUrl, $sshZip)
    } catch {
        Write-Log "Download failed: $($_.Exception.Message)"
        # Retry once with explicit redirect handling
        try {
            $wc = New-Object System.Net.WebClient
            $wc.Headers.Add("User-Agent", "PowerShell")
            $wc.DownloadFile($sshZipUrl, $sshZip)
        } catch {
            Write-Log "Retry also failed: $($_.Exception.Message)"
        }
    }

    if (Test-Path $sshZip) {
        $zipSize = (Get-Item $sshZip).Length
        Write-Log "Downloaded OpenSSH ZIP ($zipSize bytes)"

        if ($zipSize -lt 1000) {
            Write-Log "ERROR: Downloaded file too small -- likely an error page, not the ZIP"
            $content = Get-Content $sshZip -Raw -ErrorAction SilentlyContinue
            Write-Log "File content: $($content.Substring(0, [Math]::Min(200, $content.Length)))"
        } else {
            # Extract to Program Files
            Expand-Archive -Path $sshZip -DestinationPath "C:\Program Files" -Force
            Remove-Item $sshZip -Force -ErrorAction SilentlyContinue

            if (Test-Path "$sshInstallDir\install-sshd.ps1") {
                # Register sshd as a Windows service
                Write-Log "Registering sshd service..."
                & powershell.exe -ExecutionPolicy Bypass -File "$sshInstallDir\install-sshd.ps1" 2>&1 | ForEach-Object { Write-Log "  install-sshd: $_" }

                # Add to system PATH
                $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
                if ($machinePath -notlike "*OpenSSH-Win64*") {
                    [System.Environment]::SetEnvironmentVariable("Path", "$machinePath;$sshInstallDir", "Machine")
                }
                $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine")

                if (Get-Service sshd -ErrorAction SilentlyContinue) {
                    $sshInstalled = $true
                    Write-Log "OpenSSH installed via GitHub portable ZIP"
                } else {
                    Write-Log "ERROR: sshd service not found after install-sshd.ps1"
                }
            } else {
                Write-Log "ERROR: install-sshd.ps1 not found in extracted ZIP"
                Write-Log "Listing C:\Program Files\OpenSSH*:"
                Get-ChildItem "C:\Program Files\OpenSSH*" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 15 | ForEach-Object { Write-Log "  $($_.FullName)" }
            }
        }
    } else {
        Write-Log "ERROR: OpenSSH ZIP download failed (file not found at $sshZip)"
    }

    if ($sshInstalled) {
        # Ensure Windows Firewall allows SSH
        New-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -DisplayName "OpenSSH Server (sshd)" -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -ErrorAction SilentlyContinue

        # Generate host keys if missing (portable ZIP doesn't auto-generate them)
        $hostKeyDir = "C:\ProgramData\ssh"
        New-Item -ItemType Directory -Path $hostKeyDir -Force | Out-Null
        if (-not (Test-Path "$hostKeyDir\ssh_host_ed25519_key")) {
            Write-Log "Generating SSH host keys..."
            & ssh-keygen -A 2>&1 | Out-Null
        }

        # Fix host key permissions -- ssh-keygen -A creates keys with inherited
        # permissions that are "too open" for sshd. Must remove ALL inherited ACEs
        # and grant only SYSTEM + Administrators group.
        # NOTE: Use cmd /c to avoid PowerShell interpreting (F) and (R) as expressions
        Get-ChildItem "$hostKeyDir\ssh_host_*_key" -ErrorAction SilentlyContinue | ForEach-Object {
            $keyFile = $_.FullName
            cmd /c "icacls `"$keyFile`" /inheritance:r /remove Administrator /remove `"Authenticated Users`" /remove Users /grant SYSTEM:(F) /grant Administrators:(R)" 2>&1 | Out-Null
        }
        Write-Log "Host key permissions fixed"

        # Start sshd service
        Start-Service sshd -ErrorAction Stop
        Set-Service -Name sshd -StartupType Automatic
        Write-Log "sshd service started successfully"

        # Configure SSH: key-only auth, no passwords
        $sshdConfig = "$hostKeyDir\sshd_config"
        if (Test-Path $sshdConfig) {
            $content = Get-Content $sshdConfig -Raw
            $content = $content -replace '#PubkeyAuthentication yes','PubkeyAuthentication yes'
            $content = $content -replace '#PasswordAuthentication yes','PasswordAuthentication no'
            $content = $content -replace 'PasswordAuthentication yes','PasswordAuthentication no'
            Set-Content -Path $sshdConfig -Value $content
        }

        # Add user's SSH public key to administrators_authorized_keys
        # Use ASCII encoding (no BOM) -- OpenSSH rejects UTF-8 BOM in authorized_keys
        if ($SshPublicKey -and $SshPublicKey -ne "") {
            $authKeysFile = "$hostKeyDir\administrators_authorized_keys"
            [System.IO.File]::WriteAllText($authKeysFile, $SshPublicKey.Trim() + "`n")
            # Windows OpenSSH requires strict permissions on this file
            icacls $authKeysFile /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F" 2>&1 | Out-Null
            Write-Log "SSH authorized key configured (password auth disabled)"
        } else {
            Write-Log "Warning: No SSH public key provided -- password auth remains enabled"
        }

        Restart-Service sshd
        Write-Log "OpenSSH Server running on port 22 (key-only auth)"
    } else {
        Write-Log "ERROR: All OpenSSH installation methods failed -- SSH will not be available"
    }
} catch {
    Write-Log "Warning: OpenSSH install failed: $($_.Exception.Message)"
    Write-Log "Stack: $($_.Exception.StackTrace)"
}

# =============================================================================
# LOAD AWS CREDENTIALS (needed for S3 download + debug log upload)
# =============================================================================
Import-Module AWSPowerShell -ErrorAction SilentlyContinue
Set-DefaultAWSRegion -Region $AwsRegion

Write-Log "Fetching IAM role credentials from instance metadata (IMDSv2)..."
try {
    $imdsToken = Invoke-RestMethod -Uri "http://169.254.169.254/latest/api/token" -Method PUT -Headers @{"X-aws-ec2-metadata-token-ttl-seconds"="300"} -TimeoutSec 5
    $roleName = Invoke-RestMethod -Uri "http://169.254.169.254/latest/meta-data/iam/security-credentials/" -Headers @{"X-aws-ec2-metadata-token"=$imdsToken} -TimeoutSec 5
    $creds = Invoke-RestMethod -Uri "http://169.254.169.254/latest/meta-data/iam/security-credentials/$roleName" -Headers @{"X-aws-ec2-metadata-token"=$imdsToken} -TimeoutSec 5
    Set-AWSCredential -AccessKey $creds.AccessKeyId -SecretKey $creds.SecretAccessKey -SessionToken $creds.Token
    Write-Log "IAM credentials loaded for role: $roleName"
} catch {
    Write-Log "Warning: Could not fetch IMDSv2 credentials: $($_.Exception.Message)"
    Write-Log "Falling back to default credential chain..."
}

# Upload bootstrap log to S3 for remote debugging (in case SSH fails)
try {
    Write-S3Object -BucketName $DeploymentBucket -Key "$DeploymentId/logs/bootstrap.log" -File $BootstrapLog -Region $AwsRegion
    Write-Log "Debug log uploaded to S3: $DeploymentId/logs/bootstrap.log"
} catch {
    Write-Log "Warning: Could not upload debug log to S3: $($_.Exception.Message)"
}

# =============================================================================
# DOWNLOAD AND RUN MAIN INIT SCRIPT FROM S3
# =============================================================================
$MainScriptPath = "$LogDir\attack_box_init_main.ps1"
Write-Log "Downloading main init script from S3..."

try {
    # Credentials already loaded above in the AWS CREDENTIALS section
    $maxRetries = 5
    $retryCount = 0
    $downloaded = $false

    while (-not $downloaded -and $retryCount -lt $maxRetries) {
        try {
            Write-Log "Download attempt $($retryCount + 1) of $maxRetries..."
            Read-S3Object -BucketName $DeploymentBucket -Key $ScriptKey -File $MainScriptPath -Region $AwsRegion

            if (Test-Path $MainScriptPath) {
                $fileSize = (Get-Item $MainScriptPath).Length
                Write-Log "Successfully downloaded script ($fileSize bytes)"
                $downloaded = $true
            } else {
                throw "File not found after download"
            }
        }
        catch {
            $retryCount++
            Write-Log "Download failed: $($_.Exception.Message)"
            if ($retryCount -lt $maxRetries) {
                Write-Log "Retrying in 10 seconds..."
                Start-Sleep -Seconds 10
            }
        }
    }

    if (-not $downloaded) {
        throw "Failed to download script after $maxRetries attempts"
    }

    # Execute the main initialization script
    Write-Log "Executing main initialization script..."
    & PowerShell.exe -ExecutionPolicy Bypass -File $MainScriptPath

    Write-Log "Main initialization script completed"
    Write-Log "=== Attack Box Bootstrap Finished Successfully ==="
}
catch {
    Write-Log "FATAL ERROR: $($_.Exception.Message)"
    Write-Log "Stack Trace: $($_.Exception.StackTrace)"
    Write-Log "=== Attack Box Bootstrap Failed ==="
    "Bootstrap failed: $($_.Exception.Message)" | Out-File "$LogDir\bootstrap_error.txt"
}

# Copy bootstrap logs to Administrator Desktop (if profile exists now)
$desktopLogDir = "C:\Users\Administrator\Desktop\Deployment-Logs-Scripts"
if (Test-Path "C:\Users\Administrator\Desktop") {
    New-Item -ItemType Directory -Path $desktopLogDir -Force | Out-Null
    Copy-Item "$LogDir\*" $desktopLogDir -Force -ErrorAction SilentlyContinue
    Write-Log "Bootstrap logs copied to $desktopLogDir"
}

# Upload final bootstrap log to S3
try {
    Write-S3Object -BucketName $DeploymentBucket -Key "$DeploymentId/logs/bootstrap_final.log" -File $BootstrapLog -Region $AwsRegion
} catch { }
</powershell>
