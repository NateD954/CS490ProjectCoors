# Shared settings for the ECS deploy scripts. Edit the names here if you like.
# The other scripts load this file; you do not run it by itself.

$Region        = "us-east-2"
$ServiceName   = "reviewlens-backend"
$RepoName      = "reviewlens-backend"
$ExecRole      = "reviewlens-ecs-execution-role"
$InfraRole     = "reviewlens-ecs-infrastructure-role"
$ParamPrefix   = "/reviewlens"
$ContainerPort = 8000
$HealthPath    = "/health"
$SecretNames   = @("SUPABASE_URL", "SUPABASE_SECRET_KEY", "CLERK_SECRET_KEY", "GEMINI_API_KEY", "OPENWEBNINJA_API_KEY")

$AccountId = aws sts get-caller-identity --query Account --output text --region $Region
if ($LASTEXITCODE -ne 0 -or -not $AccountId) {
    throw "Not signed in to AWS. Run 'aws login' (or 'aws configure'), then try again."
}
$AccountId  = "$AccountId".Trim()
$ServiceArn = "arn:aws:ecs:${Region}:${AccountId}:service/default/$ServiceName"

# Writes text to a file as UTF-8 WITHOUT a byte-order mark (the AWS CLI rejects a BOM).
function Save-Text($text, $path) {
    [System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($false)))
}

function Save-Json($object, $path) {
    Save-Text ($object | ConvertTo-Json -Depth 10) $path
}

# Runs a command and returns $true if it succeeded. Output is hidden.
function Test-AwsOk([scriptblock]$Command) {
    & $Command 2>&1 | Out-Null
    return ($LASTEXITCODE -eq 0)
}

$TempDir = Join-Path $env:TEMP "reviewlens-ecs"
New-Item -ItemType Directory -Force -Path $TempDir | Out-Null
