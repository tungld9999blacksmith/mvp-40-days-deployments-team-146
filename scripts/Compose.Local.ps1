<#
.SYNOPSIS
    Build các image trong docker-compose.local.yaml (Windows 11 / PowerShell).

.DESCRIPTION
    - Kiểm tra Docker + Docker Compose và hiển thị phiên bản.
    - Validate cấu hình compose với file .env chỉ định.
    - -DryRun : chỉ kiểm tra, KHÔNG build (mặc định nếu không truyền gì).
    - -Build  : build thật, ghi log vào thư mục logs\ và hiển thị log khi build thành công.

    Lưu ý: script tự chuyển về thư mục chứa nó, nên đường dẫn tương đối
    (compose file, env file, logs) đều tính từ thư mục này.

.PARAMETER DryRun
    Chỉ kiểm tra môi trường và validate cấu hình, không build.

.PARAMETER Build
    Build thật.

.PARAMETER EnvFile
    File .env dùng cho compose. Mặc định: .infrastructure/.local.env

.PARAMETER ExtraArgs
    Các option truyền thêm cho "docker compose build", ví dụ: '--no-cache','--pull'

.EXAMPLE
    .\compose.local.ps1 -DryRun

.EXAMPLE
    .\compose.local.ps1 -Build

.EXAMPLE
    .\compose.local.ps1 -Build -EnvFile .infrastructure/.staging.env

.EXAMPLE
    .\compose.local.ps1 -Build -ExtraArgs '--no-cache','--pull'
#>
#Requires -Version 5.1
[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$Build,
    [string]$EnvFile = '.infrastructure/.local.env',
    [string[]]$ExtraArgs = @()
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

# Hiển thị tiếng Việt / output của docker đúng trên console
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

$ComposeFile = 'docker-compose.local.yaml'
$LogDir      = 'logs'

Set-Location -LiteralPath $PSScriptRoot

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
function Write-Info($Message) {
    Write-Host '[INFO]  ' -ForegroundColor Cyan -NoNewline
    Write-Host $Message
}

function Write-Ok($Message) {
    Write-Host '[OK]    ' -ForegroundColor Green -NoNewline
    Write-Host $Message
}

function Write-Warn($Message) {
    Write-Host '[WARN]  ' -ForegroundColor Yellow -NoNewline
    Write-Host $Message
}

function Stop-WithError($Message, [int]$Code = 1) {
    Write-Host '[ERROR] ' -ForegroundColor Red -NoNewline
    Write-Host $Message
    exit $Code
}

# Chạy lệnh native (docker...) và lấy về exit code + output.
# Tạm đặt ErrorActionPreference = Continue vì Windows PowerShell 5.1 sẽ coi mọi dòng
# stderr của lệnh native là lỗi (docker build ghi progress ra stderr).
function Invoke-Native {
    param(
        [string]$Exe,
        [string[]]$Arguments = @(),
        [switch]$StdoutOnly
    )
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        if ($StdoutOnly) {
            $lines = @(& $Exe @Arguments 2>$null | ForEach-Object { "$_" })
        } else {
            $lines = @(& $Exe @Arguments 2>&1 | ForEach-Object { "$_" })
        }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
    [pscustomobject]@{ ExitCode = $code; Output = $lines }
}

function Format-Command([string]$Exe, [string[]]$CmdArgs) {
    $parts = @($Exe) + $CmdArgs | ForEach-Object {
        if ($_ -match '\s') { '"{0}"' -f $_ } else { $_ }
    }
    $parts -join ' '
}

# ----------------------------------------------------------------------------
# Kiểm tra tham số
# ----------------------------------------------------------------------------
if ($DryRun -and $Build) {
    Stop-WithError 'Không thể dùng đồng thời -DryRun và -Build.'
}
$Mode = if ($Build) { 'build' } else { 'dry-run' }

# ----------------------------------------------------------------------------
# 1. Kiểm tra Docker & Docker Compose
# ----------------------------------------------------------------------------
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Stop-WithError 'Chưa cài Docker (hoặc chưa có trong PATH). Cài Docker Desktop: https://docs.docker.com/get-docker/'
}

$dockerVer = Invoke-Native 'docker' @('--version')
Write-Info ("Docker version  : " + ($dockerVer.Output -join ' '))

$composeCheck = Invoke-Native 'docker' @('compose', 'version')
if ($composeCheck.ExitCode -eq 0) {
    $ComposeExe    = 'docker'
    $ComposePrefix = @('compose')                      # Compose v2 (plugin)
    $composeVer    = $composeCheck.Output | Select-Object -First 1
}
elseif (Get-Command docker-compose -ErrorAction SilentlyContinue) {
    $ComposeExe    = 'docker-compose'
    $ComposePrefix = @()                               # Compose v1 (standalone)
    $composeVer    = (Invoke-Native 'docker-compose' @('version')).Output | Select-Object -First 1
    Write-Warn 'Đang dùng docker-compose v1 (đã lỗi thời), nên nâng cấp lên Compose v2.'
}
else {
    Stop-WithError "Không tìm thấy Docker Compose (cả 'docker compose' lẫn 'docker-compose')."
}
Write-Info "Compose version : $composeVer"

# ----------------------------------------------------------------------------
# 2. Kiểm tra file đầu vào
# ----------------------------------------------------------------------------
if (-not (Test-Path -LiteralPath $ComposeFile -PathType Leaf)) {
    Stop-WithError "Không tìm thấy compose file: $(Join-Path $PSScriptRoot $ComposeFile)"
}
if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
    Stop-WithError "Không tìm thấy env file: $EnvFile"
}

Write-Info "Chế độ          : $Mode"
Write-Info "Compose file    : $ComposeFile"
Write-Info "Env file        : $EnvFile"

$BaseArgs  = @($ComposePrefix) + @('--env-file', $EnvFile, '-f', $ComposeFile)
$BuildArgs = $BaseArgs + @('build') + $ExtraArgs

# ----------------------------------------------------------------------------
# 3. Validate cấu hình compose (thay biến từ env file, kiểm tra cú pháp YAML)
# ----------------------------------------------------------------------------
Write-Info 'Đang validate cấu hình compose...'
$cfg = Invoke-Native $ComposeExe ($BaseArgs + @('config', '--quiet'))
if ($cfg.ExitCode -ne 0) {
    $cfg.Output | ForEach-Object { Write-Host "    $_" }
    Stop-WithError "Cấu hình compose không hợp lệ. Kiểm tra lại $ComposeFile và $EnvFile."
}
Write-Ok 'Cấu hình compose hợp lệ.'

# ----------------------------------------------------------------------------
# 4. Dry-run: dừng tại đây
# ----------------------------------------------------------------------------
if ($Mode -eq 'dry-run') {
    $svc = Invoke-Native $ComposeExe ($BaseArgs + @('config', '--services')) -StdoutOnly
    Write-Info 'Các service sẽ được xử lý:'
    $svc.Output | ForEach-Object { Write-Host "    - $_" }
    Write-Info 'Lệnh sẽ chạy khi build thật:'
    Write-Host ('    ' + (Format-Command $ComposeExe $BuildArgs))
    Write-Ok 'DRY-RUN hoàn tất, không có image nào được build.'
    exit 0
}

# ----------------------------------------------------------------------------
# 5. Build thật
# ----------------------------------------------------------------------------
$dockerInfo = Invoke-Native 'docker' @('info') -StdoutOnly
if ($dockerInfo.ExitCode -ne 0) {
    Stop-WithError "Docker daemon chưa chạy. Hãy mở Docker Desktop, đợi trạng thái 'Engine running' rồi chạy lại."
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ('compose-build-{0}.log' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))

Write-Info "Đang build... (log: $LogFile)"
$sw = [System.Diagnostics.Stopwatch]::StartNew()

$prev = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & $ComposeExe @BuildArgs 2>&1 |
        ForEach-Object { "$_" } |
        Out-File -LiteralPath $LogFile -Encoding utf8
    $exitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $prev
}

$sw.Stop()
$secs = [int]$sw.Elapsed.TotalSeconds
$fullLogPath = Join-Path $PSScriptRoot $LogFile

if ($exitCode -eq 0) {
    Write-Ok "BUILD THÀNH CÔNG sau ${secs}s."
    Write-Host ''
    Write-Host '================= BUILD LOG ================='
    Get-Content -LiteralPath $LogFile -Encoding UTF8
    Write-Host '============================================='
    Write-Info "Log đã lưu tại: $fullLogPath"
}
else {
    Write-Host ''
    Write-Host "[ERROR] BUILD THẤT BẠI (exit code $exitCode) sau ${secs}s. 50 dòng log cuối:" -ForegroundColor Red
    Write-Host '--------------------------------------------'
    Get-Content -LiteralPath $LogFile -Tail 50 -Encoding UTF8
    Write-Host '--------------------------------------------'
    Write-Info "Xem log đầy đủ tại: $fullLogPath"
    exit $exitCode
}