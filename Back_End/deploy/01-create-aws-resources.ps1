# Step 1: creates the container repository (ECR) and the two IAM roles that ECS Express Mode needs.
# Safe to run more than once: anything that already exists is left alone.
. "$PSScriptRoot\ecs-config.ps1"
Write-Host "Account $AccountId, region $Region" -ForegroundColor Cyan

# ---- container repository ------------------------------------------------------
if (-not (Test-AwsOk { aws ecr describe-repositories --repository-names $RepoName --region $Region })) {
    aws ecr create-repository --repository-name $RepoName --image-scanning-configuration scanOnPush=true --region $Region | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not create the ECR repository." }
    Write-Host "Created ECR repository $RepoName"
} else {
    Write-Host "ECR repository $RepoName already exists"
}

# ---- trust policies (who may use each role) --------------------------------------
$execTrust = @'
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Principal": { "Service": "ecs-tasks.amazonaws.com" }, "Action": "sts:AssumeRole" }
  ]
}
'@
$infraTrust = @'
{
  "Version": "2012-10-17",
  "Statement": [
    { "Sid": "AllowAccessInfrastructureForECSExpressServices", "Effect": "Allow", "Principal": { "Service": "ecs.amazonaws.com" }, "Action": "sts:AssumeRole" }
  ]
}
'@
$execTrustFile  = Join-Path $TempDir "exec-trust.json"
$infraTrustFile = Join-Path $TempDir "infra-trust.json"
Save-Text $execTrust  $execTrustFile
Save-Text $infraTrust $infraTrustFile

function Ensure-Role($name, $trustFile) {
    if (-not (Test-AwsOk { aws iam get-role --role-name $name })) {
        aws iam create-role --role-name $name --assume-role-policy-document "file://$trustFile" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not create role $name" }
        Write-Host "Created role $name"
    } else {
        Write-Host "Role $name already exists"
    }
}

Ensure-Role $ExecRole  $execTrustFile
Ensure-Role $InfraRole $infraTrustFile

# ---- permissions -------------------------------------------------------------------
# The execution role pulls the image, writes logs, and (below) reads the secrets.
aws iam attach-role-policy --role-name $ExecRole --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
if ($LASTEXITCODE -ne 0) { throw "Could not attach the execution role policy." }

# The infrastructure role lets ECS build the load balancer, security groups and scaling for you.
aws iam attach-role-policy --role-name $InfraRole --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices
if ($LASTEXITCODE -ne 0) { throw "Could not attach the infrastructure role policy." }

$readSecrets = @"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["ssm:GetParameters", "ssm:GetParameter"],
      "Resource": "arn:aws:ssm:${Region}:${AccountId}:parameter${ParamPrefix}/*"
    }
  ]
}
"@
$readSecretsFile = Join-Path $TempDir "read-secrets.json"
Save-Text $readSecrets $readSecretsFile
aws iam put-role-policy --role-name $ExecRole --policy-name reviewlens-read-parameters --policy-document "file://$readSecretsFile"
if ($LASTEXITCODE -ne 0) { throw "Could not add the secrets policy." }

Write-Host ""
Write-Host "Done. New IAM roles can take about a minute to become usable." -ForegroundColor Green
Write-Host "Next: run .\02-store-secrets.ps1"
