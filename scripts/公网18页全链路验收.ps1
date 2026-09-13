param(
    [string]$PublicUrl = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$projectRoot = Split-Path -Parent $PSScriptRoot
$shareRoot = Join-Path $projectRoot "runtime\share"
$materialRoot = Join-Path $projectRoot "test-materials\小模型规则编排测试"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$resultRoot = Join-Path $projectRoot "test-results\公网18页验收-$stamp"
New-Item -ItemType Directory -Force -Path $resultRoot | Out-Null

if (-not $PublicUrl) {
    $PublicUrl = (Get-Content -LiteralPath (Join-Path $shareRoot "公网地址.txt") -Raw).Trim()
}
$base = "$($PublicUrl.TrimEnd('/'))/api/v1"

$adminLine = Get-Content -LiteralPath (Join-Path $projectRoot ".env") |
    Where-Object { $_ -like "SLIDEFORGE_PUBLIC_ADMIN_PASSWORD=*" } |
    Select-Object -First 1
if (-not $adminLine) { throw "没有找到公网管理员测试密码。" }
$password = $adminLine.Substring($adminLine.IndexOf("=") + 1)
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
Invoke-RestMethod -Uri "$base/auth/login" -Method Post -ContentType "application/json" `
    -Body (@{ name = "自动验收"; password = $password } | ConvertTo-Json) -WebSession $session | Out-Null

$project = Invoke-RestMethod -Uri "$base/projects" -Method Post -ContentType "application/json" `
    -Body (@{ name = "公网18页全链路验收-$stamp" } | ConvertTo-Json) -WebSession $session
$project.id | Set-Content -LiteralPath (Join-Path $resultRoot "项目ID.txt") -Encoding utf8
$PublicUrl | Set-Content -LiteralPath (Join-Path $resultRoot "公网地址.txt") -Encoding utf8
Write-Host "已创建验收项目：$($project.id)"

$materials = @(
    "01_主报告.md",
    "02_实验结果.csv",
    "03_图表与页面素材说明.md",
    "04_答辩信息.md"
)
foreach ($name in $materials) {
    $path = Join-Path $materialRoot $name
    Invoke-RestMethod -Uri "$base/projects/$($project.id)/sources" -Method Post `
        -Form @{ file = Get-Item -LiteralPath $path } -WebSession $session | Out-Null
    Write-Host "材料已上传：$name"
}

$request = @{
    title = "基于证据契约的小模型移动应用合规分析系统"
    instructions = "根据材料制作本科毕业答辩 PPT，内容详细一点。"
    preset = "academic"
    slide_count = 18
    skill_ids = @()
    approval_mode = $false
    image_mode = "off"
}
$request | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $resultRoot "测试请求.json") -Encoding utf8
$outline = Invoke-RestMethod -Uri "$base/projects/$($project.id)/jobs/outline" -Method Post `
    -ContentType "application/json" -Body ($request | ConvertTo-Json -Depth 5) -WebSession $session
Write-Host "18 页规划任务已提交：$($outline.id)"

do {
    Start-Sleep -Seconds 3
    $outlineState = Invoke-RestMethod -Uri "$base/jobs/$($outline.id)" -WebSession $session
    Write-Host ("规划 {0}%：{1}" -f [math]::Round($outlineState.progress * 100), $outlineState.checkpoint.label)
} while ($outlineState.status -in @("queued", "running"))
if ($outlineState.status -notin @("completed", "succeeded")) { throw ($outlineState.error ?? "规划失败") }

$generation = Invoke-RestMethod -Uri "$base/projects/$($project.id)/jobs/generate" -Method Post `
    -ContentType "application/json" -Body "{}" -WebSession $session
Write-Host "演示生成任务已提交：$($generation.id)"
do {
    Start-Sleep -Seconds 3
    $generationState = Invoke-RestMethod -Uri "$base/jobs/$($generation.id)" -WebSession $session
    Write-Host ("生成 {0}%：{1}" -f [math]::Round($generationState.progress * 100), $generationState.checkpoint.label)
} while ($generationState.status -in @("queued", "running"))
if ($generationState.status -notin @("completed", "succeeded")) { throw ($generationState.error ?? "生成失败") }

Invoke-WebRequest -Uri "$base/projects/$($project.id)/export/pptx" -WebSession $session `
    -OutFile (Join-Path $resultRoot "presentation.pptx")
Invoke-WebRequest -Uri "$base/projects/$($project.id)/export/html" -WebSession $session `
    -OutFile (Join-Path $resultRoot "presentation.html")
Invoke-WebRequest -Uri "$base/projects/$($project.id)/export/pdf" -WebSession $session `
    -OutFile (Join-Path $resultRoot "presentation.pdf")
$validation = Invoke-RestMethod -Uri "$base/projects/$($project.id)/validate" -Method Post `
    -ContentType "application/json" -Body "{}" -WebSession $session
$validation | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $resultRoot "validation.json") -Encoding utf8

Write-Host ""
Write-Host "公网全链路验收完成：$resultRoot" -ForegroundColor Green
Write-Host ("通过={0}；页数=18；数字声明={1}/{2}；阻断错误={3}；警告={4}" -f `
    $validation.passed, $validation.supportedNumericClaims, $validation.checkedNumericClaims, `
    $validation.blockingErrors, $validation.warningCount)
