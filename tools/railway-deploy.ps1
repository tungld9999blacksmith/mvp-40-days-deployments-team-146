<#
.SYNOPSIS
    Deploy backend / worker / mock-ev-system to Railway (staging) from a local
    machine - the same steps as the `deploy-backend` + `smoke-test` CI jobs.

.DESCRIPTION
    See docs/deployments/RAILWAY_BACKEND_DEPLOYMENT.MD (step 9). Requires the
    Railway CLI (>= 5.x), a prior `railway login` (or RAILWAY_API_TOKEN) and
    the repo root linked to the project (`railway link`).

.PARAMETER Action
    check  : verify CLI/login/link and the required variables of each service
    vars   : push infrastructure/backend/railway/.railway.env + Redis reference
             variables to `backend` and `worker` (no redeploy)
    deploy : check -> railway up (Target) -> smoke
    smoke  : GET /health + /api/v1/health/dependencies on the backend domain
    status : project status + recent deployments
    logs   : tail logs of one service (-Service, default backend)

.PARAMETER Target
    For `deploy`: app (default: backend + worker), backend, worker, mock,
    all (mock -> backend -> worker, like CI).

.PARAMETER Environment
    Railway environment (default: staging).

.PARAMETER Url
    Backend base URL for `smoke`. Default: https://<RAILWAY_PUBLIC_DOMAIN of backend>.

.PARAMETER SkipCheck
    `deploy` without the variable check.

.EXAMPLE
    ./scripts/railway-deploy.ps1 check
    ./scripts/railway-deploy.ps1 vars
    ./scripts/railway-deploy.ps1 deploy
    ./scripts/railway-deploy.ps1 deploy all
    ./scripts/railway-deploy.ps1 smoke
    ./scripts/railway-deploy.ps1 logs -Service worker
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("check", "vars", "deploy", "smoke", "status", "logs")]
    [string]$Action = "check",
    [Parameter(Position = 1)]
    [ValidateSet("app", "backend", "worker", "mock", "all")]
    [string]$Target = "app",
    [string]$Environment = "staging",
    [string]$Url,
    [ValidateSet("backend", "worker", "mock-ev-system", "Redis")]
    [string]$Service = "backend",
    [switch]$SkipCheck
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$BackendService = "backend"
$WorkerService = "worker"
$MockService = "mock-ev-system"
$RedisService = "Redis"
$EnvFile = "infrastructure/backend/railway/.railway.env"

# Redis comes from reference variables (private network), OEM_API_BASE_URL is
# set per service to the mock (step 5b) - never copied from .railway.env.
$SkipKeys = @("REDIS_URL", "REDIS_HOST", "REDIS_PORT", "REDIS_PASSWORD",
    "REDIS_BROKER_URL", "REDIS_BACKEND_URL", "OEM_API_BASE_URL")
$RedisRefs = [ordered]@{
    "REDIS_HOST"     = "`${{$RedisService.REDISHOST}}"
    "REDIS_PORT"     = "`${{$RedisService.REDISPORT}}"
    "REDIS_PASSWORD" = "`${{$RedisService.REDISPASSWORD}}"
}

function Write-Info($msg) { Write-Host "[INFO]  $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[OK]    $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[WARN]  $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "[ERROR] $msg" -ForegroundColor Red }

function Invoke-Railway {
    & railway @args
    if ($LASTEXITCODE -ne 0) {
        Write-Err "railway $($args -join ' ') failed (exit $LASTEXITCODE)."
        exit $LASTEXITCODE
    }
}

# Returns the resolved service variables as a hashtable (raw values).
function Get-ServiceVariables([string]$Name) {
    $json = & railway variable list --service $Name --environment $Environment --json
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Cannot read variables of service '$Name' ($Environment)."
        exit 1
    }
    $vars = @{}
    ($json | Out-String | ConvertFrom-Json).PSObject.Properties | ForEach-Object {
        $vars[$_.Name] = [string]$_.Value
    }
    return $vars
}

# Sets one variable without a redeploy. The value goes through stdin (from a
# temp file) so secrets stay off the command line and JSON quotes survive.
function Set-ServiceVariable([string]$Name, [string]$Key, [string]$Value) {
    $tmp = [System.IO.Path]::GetTempFileName()
    try {
        [System.IO.File]::WriteAllText($tmp, $Value)
        cmd /c "railway variable set $Key --stdin --service $Name --environment $Environment --skip-deploys < `"$tmp`"" | Out-Null
        if ($LASTEXITCODE -ne 0) { Write-Err "Failed to set $Key on '$Name'."; exit 1 }
    } finally {
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    }
}

# Parses KEY=VALUE lines of a .env file (comments/blank lines skipped, one
# pair of surrounding quotes stripped).
function Read-EnvFile([string]$Path) {
    $result = [ordered]@{}
    foreach ($line in Get-Content $Path -Encoding UTF8) {
        if ($line -match '^\s*(#|$)') { continue }
        if ($line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') { continue }
        $value = $Matches[2].Trim()
        if ($value.Length -ge 2 -and (($value[0] -eq "'" -and $value[-1] -eq "'") -or ($value[0] -eq '"' -and $value[-1] -eq '"'))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $result[$Matches[1]] = $value
    }
    return $result
}

function Test-Prerequisites {
    if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
        Write-Err "Railway CLI not found. Install: npm i -g @railway/cli"
        exit 1
    }
    & railway whoami *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Not logged in. Run 'railway login' (or set RAILWAY_API_TOKEN)."
        exit 1
    }
    & railway status *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Repo root is not linked. Run 'railway link' and pick the project + '$Environment'."
        exit 1
    }
}

# Returns the number of errors found for one service.
function Test-ServiceVariables([string]$Name, [hashtable]$Vars, [string[]]$Required) {
    $errors = 0
    foreach ($key in $Required) {
        if (-not $Vars[$key]) { Write-Err "${Name}: missing $key"; $errors++ }
    }
    if ($Name -eq $MockService) { return $errors }

    $redis = if ($Vars["REDIS_URL"]) { $Vars["REDIS_URL"] } else { $Vars["REDIS_HOST"] }
    if (-not $redis -or $redis -match "localhost|127\.0\.0\.1") {
        Write-Err "${Name}: Redis points to localhost (set REDIS_HOST/PORT/PASSWORD - run 'vars')"
        $errors++
    }
    if (-not $Vars["DATABASE_URL"] -and -not $Vars["DATABASE_PASSWORD"]) {
        Write-Err "${Name}: no DATABASE_URL / DATABASE_PASSWORD -> app falls back to SQLite"
        $errors++
    }
    if ($Vars["APP_ENV"] -ne "production") {
        Write-Err "${Name}: APP_ENV must be 'production' (is '$($Vars["APP_ENV"])')"
        $errors++
    }
    if (-not $Vars["QDRANT_URL"]) { Write-Warn "${Name}: no QDRANT_URL -> Qdrant uses local storage inside the container" }
    if (-not $Vars["FIREBASE_CREDENTIAL_JSON"]) { Write-Warn "${Name}: no FIREBASE_CREDENTIAL_JSON" }
    if ($Vars["OEM_API_BASE_URL"] -match "localhost") { Write-Warn "${Name}: OEM_API_BASE_URL points to localhost" }
    $local = @($Vars.Keys | Where-Object { $_ -notmatch "^(OEM_API_BASE_URL|REDIS_.*)$" -and $Vars[$_] -match "localhost" })
    if ($local.Count) { Write-Warn "${Name}: still 'localhost' in: $($local -join ', ')" }
    return $errors
}

function Invoke-Check {
    Test-Prerequisites
    Write-Info "Checking variables ($Environment)..."
    $errors = 0
    $errors += Test-ServiceVariables $BackendService (Get-ServiceVariables $BackendService) @("RAILWAY_DOCKERFILE_PATH", "PORT")
    $errors += Test-ServiceVariables $WorkerService (Get-ServiceVariables $WorkerService) @("RAILWAY_DOCKERFILE_PATH")
    $errors += Test-ServiceVariables $MockService (Get-ServiceVariables $MockService) @("RAILWAY_DOCKERFILE_PATH", "PORT")
    if ($errors) {
        Write-Err "$errors problem(s). Fix them (./scripts/railway-deploy.ps1 vars) or pass -SkipCheck."
        exit 1
    }
    Write-Ok "Variables look good."
}

function Get-BackendUrl {
    if ($Url) { return $Url.TrimEnd("/") }
    $domain = (Get-ServiceVariables $BackendService)["RAILWAY_PUBLIC_DOMAIN"]
    if (-not $domain) {
        Write-Err "Backend has no public domain. Generate one (Settings -> Networking) or pass -Url."
        exit 1
    }
    return "https://$domain"
}

function Invoke-Smoke {
    $base = Get-BackendUrl
    Write-Info "GET $base/health (waiting for the new deployment)..."
    $healthy = $false
    for ($i = 1; $i -le 10; $i++) {
        try {
            Invoke-RestMethod "$base/health" -TimeoutSec 15 | Out-Null
            $healthy = $true
            break
        } catch {
            Write-Host "  attempt $i/10 failed: $($_.Exception.Message)"
            Start-Sleep -Seconds 10
        }
    }
    if (-not $healthy) { Write-Err "/health did not return 200."; exit 1 }
    Write-Ok "/health OK"

    Write-Info "GET $base/api/v1/health/dependencies"
    try {
        $deps = Invoke-RestMethod "$base/api/v1/health/dependencies" -TimeoutSec 20
    } catch {
        # 503 when degraded - the body still has the per-dependency checks.
        if (-not $_.ErrorDetails.Message) { Write-Err $_.Exception.Message; exit 1 }
        $deps = $_.ErrorDetails.Message | ConvertFrom-Json
    }
    foreach ($p in $deps.checks.PSObject.Properties) {
        $c = $p.Value
        $line = "  {0,-9} {1,-5} {2,7} ms  {3}" -f $p.Name, $c.status.ToUpper(), $c.latencyMs, $(if ($c.error) { $c.error } else { $c.detail })
        if ($c.status -eq "up") { Write-Host $line -ForegroundColor Green } else { Write-Host $line -ForegroundColor Red }
    }
    if ($deps.checks.database.detail -eq "dialect=sqlite") { Write-Warn "Database is the SQLite fallback - set DATABASE_* (Supabase) on the service" }
    if ($deps.status -ne "ok") { Write-Err "Dependencies: $($deps.status)"; exit 1 }
    Write-Ok "Dependencies OK"
}

switch ($Action) {
    "check" {
        Invoke-Check
    }
    "vars" {
        Test-Prerequisites
        if (-not (Test-Path $EnvFile)) {
            Write-Err "$EnvFile not found. Copy .railway.example.env and fill it in (step 6.1)."
            exit 1
        }
        $envVars = Read-EnvFile $EnvFile
        if ($envVars["APP_ENV"] -and $envVars["APP_ENV"] -ne "production") {
            Write-Err "APP_ENV in $EnvFile is '$($envVars["APP_ENV"])' - must be 'production' on Railway."
            exit 1
        }
        $toSet = [ordered]@{}
        foreach ($key in $envVars.Keys) {
            if ($SkipKeys -contains $key -or -not $envVars[$key]) { continue }
            if ($envVars[$key] -match "localhost") { Write-Warn "$key contains 'localhost' - check it" }
            $toSet[$key] = $envVars[$key]
        }
        foreach ($key in $RedisRefs.Keys) { $toSet[$key] = $RedisRefs[$key] }

        foreach ($svc in @($BackendService, $WorkerService)) {
            Write-Info "Setting $($toSet.Count) variables on '$svc' ($Environment, no redeploy)..."
            foreach ($key in $toSet.Keys) { Set-ServiceVariable $svc $key $toSet[$key] }
            # REDIS_URL wins over REDIS_HOST in config.py - make sure it is gone.
            if ((Get-ServiceVariables $svc)["REDIS_URL"]) {
                Invoke-Railway variable delete REDIS_URL --service $svc --environment $Environment
            }
            Write-Ok "'$svc' done."
        }
        Write-Ok "Variables pushed. Deploy to apply: ./scripts/railway-deploy.ps1 deploy"
    }
    "deploy" {
        if ($SkipCheck) { Test-Prerequisites } else { Invoke-Check }
        $steps = switch ($Target) {
            "app"     { @($BackendService, $WorkerService) }
            "backend" { @($BackendService) }
            "worker"  { @($WorkerService) }
            "mock"    { @($MockService) }
            "all"     { @($MockService, $BackendService, $WorkerService) }
        }
        $commit = (git rev-parse --short HEAD 2>$null)
        foreach ($svc in $steps) {
            Write-Info "Deploying '$svc' ($Environment)..."
            if ($svc -eq $MockService) {
                # Mock is built with backend/ as root (uv workspace).
                Invoke-Railway up ./backend --path-as-root --ci --service $svc --environment $Environment --message "local deploy $commit"
            } else {
                Invoke-Railway up --ci --service $svc --environment $Environment --message "local deploy $commit"
            }
            Write-Ok "'$svc' built and deployed."
        }
        if ($steps -contains $BackendService) { Invoke-Smoke }
    }
    "smoke" {
        Test-Prerequisites
        Invoke-Smoke
    }
    "status" {
        Test-Prerequisites
        Invoke-Railway status
        foreach ($svc in @($BackendService, $WorkerService, $MockService)) {
            Write-Host ""
            Write-Info $svc
            Invoke-Railway deployment list --service $svc --environment $Environment --limit 3
        }
    }
    "logs" {
        Invoke-Railway logs --service $Service --environment $Environment
    }
}
