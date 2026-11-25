# Step 3: builds the backend image, pushes it to ECR, then creates the ECS Express Mode service
# (first run) or updates it (every run after that). Needs Docker Desktop running.
param([string]$Tag = (Get-Date -Format "yyyyMMdd-HHmmss"))

. "$PSScriptRoot\ecs-config.ps1"
$BackendDir = Split-Path -Parent $PSScriptRoot
$Registry   = "$AccountId.dkr.ecr.$Region.amazonaws.com"
$Image      = "${Registry}/${RepoName}:$Tag"

docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker is not running. Start Docker Desktop, wait until it says it is running, and try again." }

Write-Host "Logging in to ECR..." -ForegroundColor Cyan
aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin $Registry
if ($LASTEXITCODE -ne 0) { throw "ECR login failed." }

Write-Host "Building $Image ..." -ForegroundColor Cyan
docker build --platform linux/amd64 -t $Image $BackendDir
if ($LASTEXITCODE -ne 0) { throw "docker build failed." }

Write-Host "Pushing the image..." -ForegroundColor Cyan
docker push $Image
if ($LASTEXITCODE -ne 0) { throw "docker push failed." }

# The container: image, port, and each secret read from Parameter Store when the task starts.
$secrets = @()
foreach ($n in $SecretNames) {
    $secrets += @{ name = $n; valueFrom = "arn:aws:ssm:${Region}:${AccountId}:parameter${ParamPrefix}/$n" }
}
$container = @{ image = $Image; containerPort = $ContainerPort; secrets = $secrets }

$exists = Test-AwsOk { aws ecs describe-express-gateway-service --service-arn $ServiceArn --region $Region }
$requestFile = Join-Path $TempDir "express-service.json"

if (-not $exists) {
    Write-Host "Creating the ECS Express Mode service (this takes several minutes)..." -ForegroundColor Cyan
    Save-Json @{
        serviceName           = $ServiceName
        executionRoleArn      = "arn:aws:iam::${AccountId}:role/$ExecRole"
        infrastructureRoleArn = "arn:aws:iam::${AccountId}:role/$InfraRole"
        healthCheckPath       = $HealthPath
        primaryContainer      = $container
    } $requestFile
    aws ecs create-express-gateway-service --cli-input-json "file://$requestFile" --monitor-resources --region $Region
    if ($LASTEXITCODE -ne 0) {
        Write-Host "If the error mentions assuming a role, wait a minute for the new IAM roles and run this script again." -ForegroundColor Yellow
        throw "Creating the service failed."
    }
} else {
    Write-Host "Updating the existing service with the new image..." -ForegroundColor Cyan
    Save-Json @{
        serviceArn       = $ServiceArn
        healthCheckPath  = $HealthPath
        primaryContainer = $container
    } $requestFile
    aws ecs update-express-gateway-service --cli-input-json "file://$requestFile" --monitor-resources --region $Region
    if ($LASTEXITCODE -ne 0) { throw "Updating the service failed." }
}

Write-Host ""
& "$PSScriptRoot\04-status.ps1"
