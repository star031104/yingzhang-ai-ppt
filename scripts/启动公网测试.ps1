param([switch]$SkipBuild)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$projectRoot = Split-Path -Parent $PSScriptRoot
$shareRoot = Join-Path $projectRoot "runtime\share"
New-Item -ItemType Directory -Force -Path $shareRoot | Out-Null
Set-Location -LiteralPath $projectRoot

if (-not $SkipBuild) {
    Write-Host "正在构建映章网页…"
    & npm.cmd --prefix (Join-Path $projectRoot "apps\web") run build
    if ($LASTEXITCODE -ne 0) { throw "网页构建失败" }
}

$apiProcessIdPath = Join-Path $shareRoot "api.pid"
if (Test-Path -LiteralPath $apiProcessIdPath) {
    $oldApiPid = [int](Get-Content -LiteralPath $apiProcessIdPath -Raw)
    Stop-Process -Id $oldApiPid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 700
}
$occupied = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -ne $occupied) {
    $ownerPid = $occupied.OwningProcess
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$ownerPid" -ErrorAction SilentlyContinue
    $ownerCommand = [string]$owner.CommandLine
    $isYingzhang = ($null -ne $owner) -and ($ownerCommand -match '-m\s+uvicorn\s+app\.main:app') -and ($ownerCommand -match '--port\s+8000')
    if (-not $isYingzhang) { throw "8000 端口已被其他程序占用，请先关闭对应程序。" }
    Stop-Process -Id $ownerPid -Force -ErrorAction Stop
    $portReleased = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 250
        $remaining = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
        if ($null -eq $remaining) { $portReleased = $true; break }
    }
    if (-not $portReleased) { throw "旧的映章服务未能及时停止。" }
}

$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) { $pythonPath = "python" }
$apiOut = Join-Path $shareRoot "api-output.log"
$apiError = Join-Path $shareRoot "api-error.log"
$apiProcess = Start-Process -FilePath $pythonPath `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--app-dir", "apps/api", "--host", "127.0.0.1", "--port", "8000") `
    -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $apiOut -RedirectStandardError $apiError
$apiProcess.Id | Set-Content -LiteralPath (Join-Path $shareRoot "api.pid") -Encoding ascii

$healthy = $false
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    Start-Sleep -Milliseconds 500
    if ($apiProcess.HasExited) { break }
    try {
        $result = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8000/api/v1/health" -TimeoutSec 2
        $listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
        if ($result.StatusCode -eq 200 -and $listener.OwningProcess -eq $apiProcess.Id) { $healthy = $true; break }
    } catch {}
}
if (-not $healthy) { throw "映章服务启动失败，请查看 $apiError" }

& (Join-Path $PSScriptRoot "启动公网隧道.ps1")
