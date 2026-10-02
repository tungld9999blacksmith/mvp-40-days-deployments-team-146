<#
.SYNOPSIS
    Build (and optionally run / smoke-test) the images Railway deploys, so
    build errors show up locally before `railway up`:
      backend : services `backend` + `worker` (dockerfiles/Dockerfile.railway)
      mock    : service `mock-ev-system` (backend/mock-ev-system/Dockerfile.railway)

.DESCRIPTION
    See docs/deployments/RAILWAY_BACKEND_DEPLOYMENT.MD. Requires Docker running.
    `run` and `smoke` pass the repo-root .env to the backend container
    (--env-file) when it exists.

.PARAMETER Action
    build : build the image only
    run   : build + run (Ctrl+C to stop)
    smoke : build + run detached + GET /health + stop

.PARAMETER Target
    backend (default; tag p146-backend:railway, port 8000) or
    mock (tag p146-mock-ev-system:railway, port 8100).

.PARAMETER Port
    Host/container port (default: 8000 for backend, 8100 for mock).

.EXAMPLE
    ./scripts/build-backend-railway.ps1
    ./scripts/build-backend-railway.ps1 smoke
    ./scripts/build-backend-railway.ps1 smoke mock
#>
param(
    [ValidateSet("build", "run", "smoke")]
    [string]$Action = "build",
    [ValidateSet("backend", "mock")]
    [string]$Target = "backend",
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$EnvArgs = @()
if ($Target -eq "backend") {
    $Dockerfile = "dockerfiles/Dockerfile.railway"; $Context = "."
    $Tag = "p146-backend:railway"; $DefaultPort = 8000
    if (Test-Path ".env") { $EnvArgs = @("--env-file", ".env") }
} else {
    $Dockerfile = "backend/mock-ev-system/Dockerfile.railway"; $Context = "backend"
    $Tag = "p146-mock-ev-system:railway"; $DefaultPort = 8100
}
if ($Port -eq 0) { $Port = $DefaultPort }
$Container = "p146-$Target-railway-smoke"

function Info($msg) { Write-Host "[INFO]  $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "[OK]    $msg" -ForegroundColor Green }
function Err($msg)  { Write-Host "[ERROR] $msg" -ForegroundColor Red }

function Invoke-Build {
    docker info *> $null
    if ($LASTEXITCODE -ne 0) { Err "Docker is not running"; exit 1 }
    Info "Building $Tag from $Dockerfile (context: $Context)"
    docker build -f $Dockerfile -t $Tag $Context
    if ($LASTEXITCODE -ne 0) { Err "Build failed"; exit 1 }
    Ok "Built $Tag"
}

switch ($Action) {
    "build" {
        Invoke-Build
    }
    "run" {
        Invoke-Build
        Info "Running $Tag on http://localhost:$Port (Ctrl+C to stop)"
        docker run --rm -it -p "${Port}:${Port}" -e "PORT=$Port" @EnvArgs $Tag
    }
    "smoke" {
        Invoke-Build
        docker rm -f $Container *> $null
        try {
            docker run -d --name $Container -p "${Port}:${Port}" -e "PORT=$Port" @EnvArgs $Tag | Out-Null
            if ($LASTEXITCODE -ne 0) { Err "Could not start container"; exit 1 }
            Info "Waiting for http://localhost:$Port/health"
            for ($i = 0; $i -lt 30; $i++) {
                try {
                    $resp = Invoke-WebRequest "http://localhost:$Port/health" -UseBasicParsing -TimeoutSec 5
                    if ($resp.StatusCode -eq 200) { Ok "/health returned 200"; exit 0 }
                } catch {}
                if ((docker inspect -f "{{.State.Running}}" $Container 2>$null) -ne "true") { break }
                Start-Sleep -Seconds 2
            }
            Err "/health did not return 200 - container logs:"
            docker logs --tail 50 $Container
            exit 1
        } finally {
            docker rm -f $Container *> $null
        }
    }
}
