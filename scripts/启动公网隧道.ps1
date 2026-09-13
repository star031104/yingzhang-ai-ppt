param()

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$projectRoot = Split-Path -Parent $PSScriptRoot
$shareRoot = Join-Path $projectRoot "runtime\share"
New-Item -ItemType Directory -Force -Path $shareRoot | Out-Null

foreach ($pidName in @("localhost-run.pid", "pinggy.pid", "cloudflared.pid")) {
    $pidPath = Join-Path $shareRoot $pidName
    if (Test-Path -LiteralPath $pidPath) {
        $oldPid = [int](Get-Content -LiteralPath $pidPath -Raw)
        Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
    }
}
Start-Sleep -Milliseconds 500

$cloudflaredPath = (Get-Command cloudflared -ErrorAction Stop).Source
$tunnelOut = Join-Path $shareRoot "cloudflared-output.log"
$tunnelError = Join-Path $shareRoot "cloudflared-error.log"
Set-Content -LiteralPath $tunnelOut -Value "" -Encoding utf8
Set-Content -LiteralPath $tunnelError -Value "" -Encoding utf8

# 没有自有域名时使用 Cloudflare Quick Tunnel。它会分配随机的
# *.trycloudflare.com HTTPS 地址；前端会在 SSE 不可用时自动降级轮询。
$arguments = @(
    "tunnel",
    "--url", "http://127.0.0.1:8000",
    "--no-autoupdate",
    "--protocol", "http2"
)
$tunnelProcess = Start-Process -FilePath $cloudflaredPath -ArgumentList $arguments `
    -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $tunnelOut -RedirectStandardError $tunnelError
$tunnelProcess.Id | Set-Content -LiteralPath (Join-Path $shareRoot "cloudflared.pid") -Encoding ascii

$publicUrl = $null
for ($attempt = 0; $attempt -lt 120; $attempt++) {
    Start-Sleep -Milliseconds 500
    if ($tunnelProcess.HasExited) { break }
    $logs = ""
    if (Test-Path -LiteralPath $tunnelOut) { $logs += Get-Content -LiteralPath $tunnelOut -Raw }
    if (Test-Path -LiteralPath $tunnelError) { $logs += Get-Content -LiteralPath $tunnelError -Raw }
    $candidate = [regex]::Match($logs, 'https://[a-z0-9-]+\.trycloudflare\.com').Value
    if ($candidate) {
        try {
            $probe = Invoke-WebRequest -UseBasicParsing -Uri "$candidate/api/v1/health" -TimeoutSec 8
            $probeText = if ($probe.Content -is [byte[]]) {
                [System.Text.Encoding]::UTF8.GetString($probe.Content)
            } else { [string]$probe.Content }
            if ($probe.StatusCode -eq 200 -and $probeText -match '"status"\s*:\s*"ok"') {
                $publicUrl = $candidate
                break
            }
        } catch {}
    }
}
if (-not $publicUrl) {
    Stop-Process -Id $tunnelProcess.Id -Force -ErrorAction SilentlyContinue
    throw "Cloudflare 公网隧道创建失败，请查看 $tunnelError"
}

$successfulChecks = 0
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Seconds 1
    if ($tunnelProcess.HasExited) { break }
    try {
        $check = Invoke-WebRequest -UseBasicParsing -Uri "$publicUrl/api/v1/health" -TimeoutSec 8
        if ($check.StatusCode -eq 200) { $successfulChecks++ } else { $successfulChecks = 0 }
        if ($successfulChecks -ge 3) { break }
    } catch { $successfulChecks = 0 }
}
if ($successfulChecks -lt 3) {
    Stop-Process -Id $tunnelProcess.Id -Force -ErrorAction SilentlyContinue
    throw "Cloudflare 地址已分配但未通过连续健康检查，请查看 $tunnelError"
}

$publicUrl | Set-Content -LiteralPath (Join-Path $shareRoot "公网地址.txt") -Encoding utf8
@{
    url = $publicUrl
    checkedAt = (Get-Date).ToString("o")
    provider = "cloudflare-quick-tunnel"
    transport = "http2"
    consecutiveChecks = $successfulChecks
    sseFallback = "polling"
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $shareRoot "公网状态.json") -Encoding utf8

Write-Host ""
Write-Host "映章 Cloudflare 公网测试已启动：$publicUrl" -ForegroundColor Green
Write-Host "测试账号见：$(Join-Path $shareRoot '测试账号.txt')"
