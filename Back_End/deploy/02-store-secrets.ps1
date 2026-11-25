# Step 2: stores the backend's secrets in AWS Systems Manager Parameter Store (encrypted).
# You are asked for each value. Typing is hidden, and nothing is saved in a file.
# Press Enter on a prompt to keep the value that is already stored.
. "$PSScriptRoot\ecs-config.ps1"

foreach ($name in $SecretNames) {
    $secure = Read-Host "Value for $name" -AsSecureString
    $bstr   = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }

    if ([string]::IsNullOrWhiteSpace($plain)) {
        Write-Host "  skipped $name (empty)" -ForegroundColor Yellow
        continue
    }

    # The value goes through a short-lived temp file so special characters survive the command line.
    $tmp = Join-Path $TempDir "value.txt"
    [System.IO.File]::WriteAllText($tmp, $plain.Trim(), (New-Object System.Text.UTF8Encoding($false)))
    aws ssm put-parameter --name "$ParamPrefix/$name" --type SecureString --value "file://$tmp" --overwrite --region $Region | Out-Null
    $ok = ($LASTEXITCODE -eq 0)
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    if (-not $ok) { throw "Could not store $name" }
    Write-Host "  stored $ParamPrefix/$name" -ForegroundColor Green
}

Write-Host ""
Write-Host "Check what is stored (names only):"
aws ssm get-parameters-by-path --path $ParamPrefix --query "Parameters[].Name" --output table --region $Region
Write-Host "Next: run .\03-deploy.ps1"
