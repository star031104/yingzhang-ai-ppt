$projectRoot = Split-Path -Parent $PSScriptRoot
$shareRoot = Join-Path $projectRoot "runtime\share"
foreach ($name in @("localhost-run.pid", "pinggy.pid", "cloudflared.pid", "api.pid")) {
    $pidFile = Join-Path $shareRoot $name
    if (Test-Path -LiteralPath $pidFile) {
        $processId = [int](Get-Content -LiteralPath $pidFile -Raw)
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    }
}
Write-Host "映章公网测试服务已停止。"
