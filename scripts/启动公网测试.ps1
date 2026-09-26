param([switch]$SkipBuild)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$projectRoot = Split-Path -Parent $PSScriptRoot
$shareRoot = Join-Path $projectRoot "runtime\share"
New-Item -ItemType Directory -Force -Path $shareRoot | Out-Null
Set-Location -LiteralPath $projectRoot

# The public tunnel must never inherit the unauthenticated local mode.
$env:SLIDEFORGE_PUBLIC_TEST_MODE = 'true'
$env:SLIDEFORGE_PRIVATE_ACCOUNTS_MODE = 'false'
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) { $pythonPath = "python" }
$configurationCheck = & $pythonPath -c "from app.config import settings; from app.security.public_access import validate_public_config; validate_public_config(); assert settings.public_test_mode and not settings.private_accounts_mode; print('ok')" 2>&1
if ($LASTEXITCODE -ne 0 -or ($configurationCheck -join "") -notmatch "ok") {
    throw "公网测试未启动：请在 .env 中配置不同的测试者/管理员密码、至少 32 位会话密钥，并确保 Python 依赖已安装。"
}

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

$publicSession = $null
try { $publicSession = Invoke-RestMethod -UseBasicParsing -Uri "http://127.0.0.1:8000/api/v1/auth/session" -TimeoutSec 3 } catch {}
if ($null -eq $publicSession -or -not $publicSession.publicMode -or $publicSession.privateMode -or $publicSession.authenticated) {
    Stop-Process -Id $apiProcess.Id -Force -ErrorAction SilentlyContinue
    throw "公网测试未启动：服务没有进入未登录的共享测试模式。"
}
$projectsRequireLogin = $false
try {
    $projectsProbe = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8000/api/v1/projects" -TimeoutSec 3
    $projectsRequireLogin = $projectsProbe.StatusCode -eq 401
} catch {
    if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 401) { $projectsRequireLogin = $true }
}
if (-not $projectsRequireLogin) {
    Stop-Process -Id $apiProcess.Id -Force -ErrorAction SilentlyContinue
    throw "公网测试未启动：项目接口未能证明会拒绝未登录请求。"
}

& (Join-Path $PSScriptRoot "启动公网隧道.ps1")
