# Shows the service status, its public URL, a health check result and the log group.
. "$PSScriptRoot\ecs-config.ps1"

$raw = aws ecs describe-express-gateway-service --service-arn $ServiceArn --region $Region
if ($LASTEXITCODE -ne 0) { throw "Service $ServiceName was not found in $Region. Run .\03-deploy.ps1 first." }

$service = ($raw | ConvertFrom-Json).service
Write-Host "Service: $($service.serviceName)"
Write-Host "Status:  $($service.status.statusCode) $($service.status.statusReason)"

$config = $service.activeConfigurations | Select-Object -First 1
if (-not $config) {
    Write-Host "No active configuration yet. Wait a minute and run this script again." -ForegroundColor Yellow
    return
}

foreach ($path in $config.ingressPaths) {
    $url = $path.endpoint
    if ($url -notmatch '^https?://') { $url = "https://$url" }
    Write-Host "URL:     $url   <- this is your BACKEND_URL for Amplify" -ForegroundColor Green
    try {
        $health = Invoke-RestMethod "$url$HealthPath" -TimeoutSec 20
        Write-Host "Health:  $($health | ConvertTo-Json -Compress)" -ForegroundColor Green
    } catch {
        Write-Host "Health:  no answer yet from $url$HealthPath ($($_.Exception.Message))" -ForegroundColor Yellow
    }
}

$logGroup = $config.primaryContainer.awsLogsConfiguration.logGroup
if ($logGroup) {
    Write-Host "Logs:    aws logs tail $logGroup --follow --region $Region"
}
