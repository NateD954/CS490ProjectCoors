# Deletes the ECS service and the load balancer it created, so AWS stops charging for them.
# The container repository, IAM roles and stored secrets are left in place (see the notes at the end).
. "$PSScriptRoot\ecs-config.ps1"

$answer = Read-Host "Delete the ECS service '$ServiceName' and its load balancer? Type yes to continue"
if ($answer -ne "yes") { Write-Host "Cancelled."; return }

aws ecs delete-express-gateway-service --service-arn $ServiceArn --monitor-resources --region $Region
if ($LASTEXITCODE -ne 0) { throw "Delete failed." }

Write-Host "Service deleted." -ForegroundColor Green
Write-Host ""
Write-Host "Optional full clean-up:"
Write-Host "  aws ecr delete-repository --repository-name $RepoName --force --region $Region"
Write-Host "  aws ssm delete-parameters --names $(($SecretNames | ForEach-Object { "$ParamPrefix/$_" }) -join ' ') --region $Region"
