<#
.SYNOPSIS
    Chạy/điều khiển CHỈ hạ tầng phụ trợ (mock-ev-system, redis) bằng
    Docker, để backend FastAPI chạy trực tiếp bằng terminal (debug local).

.DESCRIPTION
    Dùng docker-compose.infra.yaml. Backend KHÔNG nằm trong stack này —
    bạn tự chạy `uvicorn src.main:app --reload` (hoặc `uv run ...`) sau khi
    hạ tầng đã lên.

.PARAMETER Action
    up      : build (nếu cần) + khởi động hạ tầng ở chế độ nền (mặc định)
    down    : dừng và xoá container (giữ volume dữ liệu)
    logs    : xem log realtime
    ps      : liệt kê trạng thái
    clean   : down + xoá luôn volume (mất dữ liệu redis + mock-ev)

.EXAMPLE
    ./scripts/infra-stack.ps1 up
    cd backend; uv run uvicorn src.main:app --reload --port 8000
#>
[CmdletBinding()]
param(
    [ValidateSet("up", "down", "logs", "ps", "clean")]
    [string]$Action = "up"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$ComposeFile = "docker-compose.infra.yaml"

function Write-Info($msg) { Write-Host "[INFO]  $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[OK]    $msg" -ForegroundColor Green }
function Write-Err($msg)  { Write-Host "[ERROR] $msg" -ForegroundColor Red }

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Err "Chưa cài Docker. Xem https://docs.docker.com/get-docker/"
    exit 1
}
# Check the exit code, not exceptions: `docker info` prints WARNING lines to
# stderr, which Windows PowerShell 5.1 turns into terminating errors under
# ErrorActionPreference=Stop even when the daemon is healthy.
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
docker info *> $null
$dockerExit = $LASTEXITCODE
$ErrorActionPreference = $prevEap
if ($dockerExit -ne 0) {
    Write-Err "Docker daemon is not running. Start Docker Desktop and try again."
    exit 1
}

$Compose = @("docker", "compose", "-f", $ComposeFile)

switch ($Action) {
    "up" {
        Write-Info "Build + khởi động hạ tầng (mock-ev-system, redis)..."
        & $Compose[0] $Compose[1..($Compose.Length-1)] up -d --build
        if ($LASTEXITCODE -ne 0) { Write-Err "Khởi động thất bại."; exit $LASTEXITCODE }
        Write-Ok "Hạ tầng đã chạy:"
        & $Compose[0] $Compose[1..($Compose.Length-1)] ps
        Write-Host ""
        Write-Ok "Mock EV system: http://localhost:8100/health"
        Write-Ok "Redis         : localhost:6379"
        Write-Host ""
        Write-Info "Bước tiếp theo — chạy backend bằng terminal (KHÔNG dùng Docker):"
        Write-Host "  1) copy .env.local-debug.example -> .env ở gốc repo (sửa OPENAI_API_KEY nếu cần)"
        Write-Host "  2) cd backend"
        Write-Host "  3) uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000"
        Write-Host "     (hoặc, dùng venv/pip: uvicorn src.main:app --reload --port 8000)"
    }
    "down" {
        Write-Info "Dừng và xoá container hạ tầng (giữ volume)..."
        & $Compose[0] $Compose[1..($Compose.Length-1)] down
        Write-Ok "Đã dừng."
    }
    "logs" {
        Write-Info "Log realtime (Ctrl+C để thoát)..."
        & $Compose[0] $Compose[1..($Compose.Length-1)] logs -f --tail=100
    }
    "ps" {
        & $Compose[0] $Compose[1..($Compose.Length-1)] ps
    }
    "clean" {
        Write-Info "Dừng + xoá volume (mất dữ liệu redis)..."
        & $Compose[0] $Compose[1..($Compose.Length-1)] down -v
        Write-Ok "Đã dọn sạch."
    }
}
