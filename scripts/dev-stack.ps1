<#
.SYNOPSIS
    Dựng/điều khiển stack backend local cho P-146 bằng docker-compose.dev.yaml.

.DESCRIPTION
    Quản lý 3 service: backend (FastAPI), mock-ev-system, redis.

.PARAMETER Action
    up      : build (nếu cần) + khởi động toàn bộ stack ở chế độ nền (mặc định)
    down    : dừng và xoá container (giữ nguyên volume dữ liệu)
    build   : chỉ build lại image, không chạy
    logs    : xem log realtime của tất cả service
    ps      : liệt kê trạng thái các service
    restart : khởi động lại toàn bộ stack
    clean   : down + xoá luôn volume (mất dữ liệu redis)

.EXAMPLE
    ./scripts/dev-stack.ps1 up
    ./scripts/dev-stack.ps1 logs
    ./scripts/dev-stack.ps1 down
#>
[CmdletBinding()]
param(
    [ValidateSet("up", "down", "build", "logs", "ps", "restart", "clean")]
    [string]$Action = "up"
)

$ErrorActionPreference = "Stop"

# Về thư mục gốc repo (script nằm trong scripts/)
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$ComposeFile = "docker-compose.dev.yaml"

function Write-Info($msg) { Write-Host "[INFO]  $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[OK]    $msg" -ForegroundColor Green }
function Write-Err($msg)  { Write-Host "[ERROR] $msg" -ForegroundColor Red }

# --- Kiểm tra Docker ---
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
if (-not (Test-Path (Join-Path $RepoRoot ".env"))) {
    Write-Err "Không tìm thấy file .env ở gốc repo. Copy từ .env.example rồi điền giá trị."
    exit 1
}

$Compose = @("docker", "compose", "-f", $ComposeFile)

switch ($Action) {
    "up" {
        Write-Info "Build + khởi động stack (backend, mock-ev-system, redis)..."
        & $Compose[0] $Compose[1..($Compose.Length-1)] up -d --build
        if ($LASTEXITCODE -ne 0) { Write-Err "Khởi động thất bại."; exit $LASTEXITCODE }
        Write-Ok "Stack đã chạy. Xem trạng thái:"
        & $Compose[0] $Compose[1..($Compose.Length-1)] ps
        Write-Host ""
        Write-Ok "Backend API   : http://localhost:8000/health   (docs: http://localhost:8000/docs)"
        Write-Ok "Mock EV system: http://localhost:8100/health   (docs: http://localhost:8100/docs)"
        Write-Ok "Redis         : localhost:6379"
    }
    "down" {
        Write-Info "Dừng và xoá container (giữ volume)..."
        & $Compose[0] $Compose[1..($Compose.Length-1)] down
        Write-Ok "Đã dừng stack."
    }
    "build" {
        Write-Info "Build lại image..."
        & $Compose[0] $Compose[1..($Compose.Length-1)] build
        Write-Ok "Build xong."
    }
    "logs" {
        Write-Info "Log realtime (Ctrl+C để thoát)..."
        & $Compose[0] $Compose[1..($Compose.Length-1)] logs -f --tail=100
    }
    "ps" {
        & $Compose[0] $Compose[1..($Compose.Length-1)] ps
    }
    "restart" {
        Write-Info "Khởi động lại stack..."
        & $Compose[0] $Compose[1..($Compose.Length-1)] restart
        Write-Ok "Đã restart."
    }
    "clean" {
        Write-Info "Dừng stack và xoá volume (mất dữ liệu redis)..."
        & $Compose[0] $Compose[1..($Compose.Length-1)] down -v
        Write-Ok "Đã dọn sạch."
    }
}
