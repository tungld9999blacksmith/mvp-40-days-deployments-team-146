<#
.SYNOPSIS
    Deploy/manage dev infra (Redis + mock-ev-system) on Railway so the core
    backend can run locally in a terminal (debug mode, see
    docs/RUN_LOCAL_BACKEND_RAILWAY.md).

.DESCRIPTION
    Wraps the Railway CLI (>= 5.x). Run `railway login` once before using it.

.PARAMETER Action
    init     : create a new Railway project and link the repo root to it
    link     : link the repo root to an existing Railway project (teammates)
    setup    : create the Redis database + the empty mock-ev-system service
    deploy   : upload backend/ and (re)deploy mock-ev-system
    domain   : generate the public HTTPS domain for mock-ev-system
    webhook  : set MOCK_WEBHOOK_URL (pass -Url <public base URL>, "" to disable)
    env      : print the .env (repo root) lines for the Railway infra
    status   : show project status + mock-ev-system deployments
    logs     : tail mock-ev-system logs

.PARAMETER ProjectName
    Railway project name for `init` (default: p146-dev-infra).

.PARAMETER Url
    Public base URL of the local backend (ngrok/cloudflared tunnel) for
    `webhook`, e.g. https://abc.trycloudflare.com. Empty string disables webhooks.

.PARAMETER Slot
    Developer slot (0-4) for `env`. Each slot gets its own Redis DB numbers so
    teammates sharing one Redis do not consume each other's Celery tasks.

.PARAMETER WebhookSecret
    HMAC secret for `setup`. Default: OEM_WEBHOOK_SECRET from .env (repo root),
    otherwise a newly generated random value.

.EXAMPLE
    ./scripts/railway-infra.ps1 init
    ./scripts/railway-infra.ps1 setup
    ./scripts/railway-infra.ps1 deploy
    ./scripts/railway-infra.ps1 domain
    ./scripts/railway-infra.ps1 env -Slot 0
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("init", "link", "setup", "deploy", "domain", "webhook", "env", "status", "logs")]
    [string]$Action = "status",
    [string]$ProjectName = "p146-dev-infra",
    [string]$Url,
    [ValidateRange(0, 4)]
    [int]$Slot = 0,
    [string]$WebhookSecret
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$MockService = "mock-ev-system"
$RedisService = "Redis"
$WebhookPath = "/api/v1/integrations/oem/webhooks"

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

# Returns the service variables as a hashtable (raw values).
function Get-ServiceVariables([string]$Service) {
    $json = & railway variable list --service $Service --json
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Cannot read variables of service '$Service'. Did you run 'setup'?"
        exit 1
    }
    $vars = @{}
    ($json | Out-String | ConvertFrom-Json).PSObject.Properties | ForEach-Object {
        $vars[$_.Name] = $_.Value
    }
    return $vars
}

# Reads KEY from .env (repo root) (returns $null when missing).
function Get-BackendEnvValue([string]$Key) {
    $envFile = Join-Path $RepoRoot ".env"
    if (-not (Test-Path $envFile)) { return $null }
    $line = Get-Content $envFile | Where-Object { $_ -match "^\s*$Key\s*=" } | Select-Object -First 1
    if (-not $line) { return $null }
    $value = ($line -split "=", 2)[1].Trim().Trim("'").Trim('"')
    if ($value) { return $value } else { return $null }
}

if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
    Write-Err "Railway CLI not found. Install: npm i -g @railway/cli"
    exit 1
}

switch ($Action) {
    "init" {
        Write-Info "Creating Railway project '$ProjectName' and linking the repo root..."
        Invoke-Railway init --name $ProjectName
        Write-Ok "Linked. Next: ./scripts/railway-infra.ps1 setup"
    }
    "link" {
        Write-Info "Linking the repo root to an existing Railway project..."
        Invoke-Railway link
    }
    "setup" {
        if (-not $WebhookSecret) { $WebhookSecret = Get-BackendEnvValue "OEM_WEBHOOK_SECRET" }
        if (-not $WebhookSecret -or $WebhookSecret -eq "change-me") {
            $bytes = New-Object byte[] 32
            [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
            $WebhookSecret = -join ($bytes | ForEach-Object { $_.ToString("x2") })
            Write-Warn "Generated a new webhook secret. Put it in .env (repo root):"
            Write-Host "  OEM_WEBHOOK_SECRET=$WebhookSecret"
        }

        Write-Info "Adding Redis database..."
        Invoke-Railway add --database redis

        Write-Info "Adding empty service '$MockService'..."
        Invoke-Railway add --service $MockService `
            --variables "RAILWAY_DOCKERFILE_PATH=mock-ev-system/Dockerfile.railway" `
            --variables "PORT=8100" `
            --variables "MOCK_WEBHOOK_SECRET=$WebhookSecret" `
            --variables "MOCK_WEBHOOK_USAGE_MIN_INTERVAL_SECONDS=300"

        Write-Ok "Done. Next: ./scripts/railway-infra.ps1 deploy ; then domain"
    }
    "deploy" {
        Write-Info "Uploading backend/ and deploying '$MockService'..."
        Invoke-Railway up ./backend --path-as-root --service $MockService --detach `
            --message "mock-ev-system dev deploy"
        Write-Ok "Deploy started. Follow with: ./scripts/railway-infra.ps1 logs"
    }
    "domain" {
        Invoke-Railway domain --service $MockService --port 8100
    }
    "webhook" {
        if (-not $PSBoundParameters.ContainsKey("Url")) {
            Write-Err "Pass -Url <public base URL of your local backend> (or -Url '' to disable)."
            exit 1
        }
        if ($Url) {
            $target = $Url.TrimEnd("/") + $WebhookPath
            Write-Info "Setting MOCK_WEBHOOK_URL=$target (triggers a redeploy)..."
            Invoke-Railway variable set "MOCK_WEBHOOK_URL=$target" --service $MockService
        } else {
            Write-Info "Removing MOCK_WEBHOOK_URL (webhooks disabled, triggers a redeploy)..."
            Invoke-Railway variable delete MOCK_WEBHOOK_URL --service $MockService
        }
        Write-Ok "Done."
    }
    "env" {
        $redis = Get-ServiceVariables $RedisService
        $mock = Get-ServiceVariables $MockService

        $publicUrl = $redis["REDIS_PUBLIC_URL"]
        if (-not $publicUrl) {
            Write-Err "REDIS_PUBLIC_URL is empty. Enable Redis -> Settings -> Networking -> TCP Proxy (port 6379)."
            exit 1
        }
        $uri = [System.Uri]$publicUrl
        $password = [System.Uri]::UnescapeDataString(($uri.UserInfo -split ":", 2)[1])

        $mockDomain = $mock["RAILWAY_PUBLIC_DOMAIN"]
        if ($mockDomain) {
            $oemUrl = "https://$mockDomain"
        } else {
            $oemUrl = "<run: ./scripts/railway-infra.ps1 domain>"
            Write-Warn "mock-ev-system has no public domain yet."
        }

        # Slot N uses DBs 3N (broker), 3N+1 (result backend), 3N+2 (app cache).
        $brokerDb = 3 * $Slot
        $backendDb = $brokerDb + 1
        $appDb = $brokerDb + 2

        Write-Ok "Paste these into .env (repo root) (slot $Slot):"
        Write-Host ""
        Write-Host "OEM_API_BASE_URL=$oemUrl"
        Write-Host "OEM_WEBHOOK_SECRET=$($mock['MOCK_WEBHOOK_SECRET'])"
        Write-Host "REDIS_URL="
        Write-Host "REDIS_HOST=$($uri.Host)"
        Write-Host "REDIS_PORT=$($uri.Port)"
        Write-Host "REDIS_PASSWORD='$password'"
        Write-Host "REDIS_DB=$appDb"
        Write-Host "CELERY_BROKER_DB=$brokerDb"
        Write-Host "CELERY_BACKEND_DB=$backendDb"
        Write-Host "REDIS_KEY_PREFIX=p146-dev$Slot"
        Write-Host "REDIS_BROKER_URL="
        Write-Host "REDIS_BACKEND_URL="
    }
    "status" {
        Invoke-Railway status
        Write-Host ""
        Invoke-Railway deployment list --service $MockService --limit 5
    }
    "logs" {
        Invoke-Railway logs --service $MockService
    }
}
