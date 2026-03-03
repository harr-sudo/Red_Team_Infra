<powershell>
# Attack Box Bootstrap - Downloads and executes main init script from S3
# This lightweight bootstrap stays under the 16KB EC2 user_data limit
$ErrorActionPreference = "Continue"

# Variables from Terraform templatefile()
$DeploymentBucket = "${deployment_bucket}"
$DeploymentId = "${deployment_id}"
$AwsRegion = "${aws_region}"
$ScriptKey = "$DeploymentId/scripts/attack_box_init.ps1"

# Create logs directory
$LogDir = "C:\Users\Administrator\Desktop\Deployment-Logs-Scripts"
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

# Download the main initialization script from S3
$MainScriptPath = "$LogDir\attack_box_init_main.ps1"
Write-Log "Downloading main init script from S3..."

try {
    Import-Module AWSPowerShell -ErrorAction SilentlyContinue

    $maxRetries = 5
    $retryCount = 0
    $downloaded = $false

    while (-not $downloaded -and $retryCount -lt $maxRetries) {
        try {
            Write-Log "Download attempt $($retryCount + 1) of $maxRetries..."
            & aws s3 cp "s3://$DeploymentBucket/$ScriptKey" $MainScriptPath --region $AwsRegion

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
    exit 1
}
</powershell>
