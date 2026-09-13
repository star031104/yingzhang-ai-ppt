param(
    [ValidateRange(1024, 65535)][int]$Port = 8000,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$launchRoot = Join-Path $projectRoot 'runtime\launcher'
New-Item -ItemType Directory -Force -Path $launchRoot | Out-Null
$url = "http://127.0.0.1:$Port"
$appDirectory = Join-Path $projectRoot 'apps\api'
$hash = [System.Security.Cryptography.SHA256]::Create()
$key = [BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($projectRoot.ToLowerInvariant()))).Replace('-', '')
$hash.Dispose()
$mutex = New-Object System.Threading.Mutex($false, "Local\YingzhangLauncher$key")
$acquired = $false

function Test-OurServer($processId) {
    $entry = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
    return $entry -and $entry.CommandLine -like '*uvicorn*app.main:app*' -and
        $entry.CommandLine.Contains($appDirectory) -and $entry.CommandLine -match "--port\s+$Port(\s|$)"
}

function Open-Website {
    Write-Host "YingZhang is ready: $url" -ForegroundColor Green
    Write-Host "Logs: $launchRoot"
    if (-not $NoBrowser) { Start-Process $url }
}

try {
    try { $acquired = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $acquired = $true }
    if (-not $acquired) { throw 'Another launcher is preparing this project. Please wait for it to finish.' }
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        if (-not (Test-OurServer $listener.OwningProcess)) {
            throw "Port $Port is used by another service. Close it or run this script with -Port 8001."
        }
        $health = Invoke-RestMethod "$url/api/v1/health" -TimeoutSec 5
        if ($health.status -ne 'ok') { throw 'The existing server is not healthy. Check its logs.' }
        Open-Website
        exit 0
    }

    $pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if (-not $pythonCommand) { throw 'Install Python 3.11 or later and add it to PATH, then try again.' }
        $pythonPath = $pythonCommand.Source
    }
    & $pythonPath -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or later is required.' }
    $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npmCommand -or -not (Get-Command node.exe -ErrorAction SilentlyContinue)) {
        throw 'Install Node.js 20 or later (including npm), then try again.'
    }
    & node.exe -e "process.exit(Number(process.versions.node.split('.')[0]) >= 20 ? 0 : 1)"
    if ($LASTEXITCODE -ne 0) { throw 'Node.js 20 or later is required.' }

    Write-Host 'Checking Python dependencies...'
    & $pythonPath -c "import importlib.util,sys; sys.exit(0 if all(importlib.util.find_spec(m) for m in 'fastapi uvicorn sqlalchemy alembic pydantic_settings httpx keyring cryptography pymupdf docx pptx openpyxl bs4 multipart PIL'.split()) else 1)"
    if ($LASTEXITCODE -ne 0) {
        & $pythonPath -m pip install -e .
        if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed. Check the output above.' }
    }
    if (-not (Test-Path 'node_modules\vite') -or -not (Test-Path 'node_modules\pptxgenjs')) {
        Write-Host 'Installing web and rendering dependencies...'
        & $npmCommand.Source ci
        if ($LASTEXITCODE -ne 0) { throw 'npm dependency installation failed.' }
    }
    & node.exe --input-type=module -e "import { chromium } from 'playwright'; import fs from 'node:fs'; process.exit(fs.existsSync(chromium.executablePath()) ? 0 : 1)"
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Installing the local slide-rendering browser...'
        & (Join-Path $projectRoot 'node_modules\.bin\playwright.cmd') install chromium
        if ($LASTEXITCODE -ne 0) { throw 'Rendering browser installation failed.' }
    }
    Write-Host 'Building the website...'
    & $npmCommand.Source run build
    if ($LASTEXITCODE -ne 0) { throw 'Website build failed. The server was not started.' }

    $stdout = Join-Path $launchRoot "server-$Port.log"
    $stderr = Join-Path $launchRoot "server-$Port-error.log"
    $arguments = '-m uvicorn app.main:app --app-dir "{0}" --host 127.0.0.1 --port {1}' -f $appDirectory, $Port
    # The desktop launcher always opens a personal workspace without an account.
    # Process-level values override legacy invitation settings in a local .env.
    $env:SLIDEFORGE_PUBLIC_TEST_MODE = 'false'
    $env:SLIDEFORGE_PRIVATE_ACCOUNTS_MODE = 'false'
    # WMI creates an independent hidden process, outside the launching terminal's job.
    $worker = Join-Path $PSScriptRoot 'run-local-server.ps1'
    $command = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -PythonPath "{1}" -Port {2} -NodeDirectory "{3}"' -f $worker, $pythonPath, $Port, (Split-Path -Parent (Get-Command node.exe).Source)
    $startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow = [uint16]0 }
    $created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $command; CurrentDirectory = $projectRoot; ProcessStartupInformation = $startup }
    if ($created.ReturnValue -ne 0) { throw "Could not start background service (code $($created.ReturnValue))." }
    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Milliseconds 500
        if (-not (Get-Process -Id $created.ProcessId -ErrorAction SilentlyContinue)) { break }
        try {
            $health = Invoke-RestMethod "$url/api/v1/health" -TimeoutSec 2
            $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($health.status -eq 'ok' -and $listener -and (Test-OurServer $listener.OwningProcess)) {
                $ready = $true
                break
            }
        } catch { }
    }
    if (-not $ready) {
        $failedListener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($failedListener -and (Test-OurServer $failedListener.OwningProcess)) { Stop-Process -Id $failedListener.OwningProcess }
        throw "Server startup failed. Read $stderr"
    }
    @{ processId = $listener.OwningProcess; port = $Port; url = $url; projectRoot = $projectRoot } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $launchRoot "server-$Port.json") -Encoding UTF8
    Open-Website
} catch {
    Write-Host "Startup failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if ($acquired) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
