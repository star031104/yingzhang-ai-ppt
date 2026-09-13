param([switch]$Force)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$projectRoot = Split-Path -Parent $PSScriptRoot
$addressPath = Join-Path $projectRoot "runtime\share\公网地址.txt"
$startScript = Join-Path $PSScriptRoot "启动公网测试.ps1"
$tunnelScript = Join-Path $PSScriptRoot "启动公网隧道.ps1"

$healthy = $false
$publicUrl = ""
if ((-not $Force) -and (Test-Path -LiteralPath $addressPath)) {
    $publicUrl = (Get-Content -LiteralPath $addressPath -Raw).Trim()
    if ($publicUrl) {
        try {
            $check = Invoke-WebRequest -UseBasicParsing -Uri "$publicUrl/api/v1/health" -TimeoutSec 8
            $checkText = if ($check.Content -is [byte[]]) {
                [System.Text.Encoding]::UTF8.GetString($check.Content)
            } else { [string]$check.Content }
            $healthy = $check.StatusCode -eq 200 -and $checkText -match '"status"\s*:\s*"ok"'
        } catch {}
    }
}

if ($healthy) {
    Write-Host "公网服务正常：$publicUrl" -ForegroundColor Green
    exit 0
}

Write-Host "检测到公网隧道不可用，正在重建备用公网通道…" -ForegroundColor Yellow
try {
    $local = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8000/api/v1/health" -TimeoutSec 5
    if ($local.StatusCode -eq 200) {
        # 只恢复隧道，不终止正在生成的后端任务。
        & $tunnelScript
        exit $LASTEXITCODE
    }
} catch {}

& $startScript -SkipBuild
