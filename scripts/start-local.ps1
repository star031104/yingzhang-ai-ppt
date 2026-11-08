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

function Refresh-Path {
    $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = @($machinePath, $userPath) -join ';'
}

function Get-ToolPath([string]$Name, [string[]]$Fallbacks = @()) {
    $tool = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($tool) { return $tool.Source }
    foreach ($candidate in $Fallbacks) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return $null
}

function Install-WingetPackage([string]$PackageId, [string]$DisplayName) {
    $winget = Get-ToolPath 'winget.exe'
    if (-not $winget) {
        throw "Cannot install $DisplayName automatically because Windows Package Manager (winget) is unavailable. Install it from Microsoft Store as 'App Installer', then double-click this launcher again."
    }
    Write-Host "Installing $DisplayName. This first-run step needs an internet connection and may show a Windows permission prompt..." -ForegroundColor Cyan
    & $winget install --id $PackageId --exact --source winget --accept-package-agreements --accept-source-agreements --silent --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw "$DisplayName installation failed (winget exit code $LASTEXITCODE). Check your network, then retry." }
    Refresh-Path
}

$hash = [System.Security.Cryptography.SHA256]::Create()
$key = [BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($projectRoot.ToLowerInvariant()))).Replace('-', '')
$hash.Dispose()
$mutex = New-Object System.Threading.Mutex($false, "Local\YingzhangLauncher$key")
$acquired = $false

function Test-OurServer($processId) {
    # The listening socket can belong to the interpreter that the venv python.exe
    # redirector spawned, whose command line Windows may report differently. Walk up
    # a few parents and accept either our uvicorn command or our worker script.
    $worker = Join-Path $PSScriptRoot 'run-local-server.ps1'
    $current = $processId
    for ($depth = 0; $depth -lt 4 -and $current; $depth++) {
        $entry = Get-CimInstance Win32_Process -Filter "ProcessId=$current" -ErrorAction SilentlyContinue
        if (-not $entry) { return $false }
        $line = [string]$entry.CommandLine
        if ($line -like '*uvicorn*app.main:app*' -and $line.Contains($appDirectory) -and $line -match "--port\s+$Port(\s|$)") { return $true }
        if ($line.Contains($worker) -and $line -match "-Port\s+$Port(\s|$)") { return $true }
        $current = $entry.ParentProcessId
    }
    return $false
}

function Get-PortListeners {
    # Some Windows installs report listening sockets with owner PID 0 and return nothing
    # from Get-NetTCPConnection, so only use these results to know the port is taken.
    $found = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { [pscustomobject]@{ OwningProcess = [int]$_.OwningProcess } })
    if ($found.Count) { return $found }
    $pattern = "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$"
    return @(netstat.exe -ano -p TCP 2>$null | ForEach-Object {
        if ($_ -match $pattern) { [pscustomobject]@{ OwningProcess = [int]$Matches[1] } }
    })
}

function Get-OurServerProcess {
    # Find our uvicorn by command line instead of by socket owner.
    return @(Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" -ErrorAction SilentlyContinue | Where-Object {
        $line = [string]$_.CommandLine
        $line -like '*uvicorn*app.main:app*' -and $line.Contains($appDirectory) -and $line -match "--port\s+$Port(\s|$)"
    })
}

function Test-OurHealth {
    # Our server answers /health with a hash of this project path (same as $key below).
    try { $health = Invoke-RestMethod "$url/api/v1/health" -TimeoutSec 3 } catch { return $false }
    if ($health.status -ne 'ok') { return $false }
    if ($health.instance -and $health.instance -eq $key) { return $true }
    # Older servers lack the field, and a junction/OneDrive path can change the hash:
    # fall back to finding our uvicorn by its command line.
    return [bool](Get-OurServerProcess)
}

function Open-Website {
    Write-Host "YingZhang is ready: $url" -ForegroundColor Green
    Write-Host "Logs: $launchRoot"
    if (-not $NoBrowser) { Start-Process $url }
}

try {
    try { $acquired = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $acquired = $true }
    if (-not $acquired) { throw 'Another launcher is preparing this project. Please wait for it to finish.' }
    $listener = Get-PortListeners | Select-Object -First 1
    if ($listener) {
        if (-not (Test-OurHealth)) {
            throw "Port $Port is used by another service (or an unhealthy YingZhang server). Close it or run this script with -Port 8001."
        }
        Open-Website
        exit 0
    }

    $uv = Get-ToolPath 'uv.exe' @((Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\uv.exe'))
    if (-not $uv) {
        Install-WingetPackage 'astral-sh.uv' 'uv (Python environment manager)'
        $uv = Get-ToolPath 'uv.exe' @((Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\uv.exe'))
    }
    if (-not $uv) { throw 'uv installation completed but uv.exe is not available. Restart Windows and try again.' }

    $nodeFallbacks = @('C:\Program Files\nodejs\node.exe', (Join-Path $env:ProgramFiles 'nodejs\node.exe'))
    $nodePath = Get-ToolPath 'node.exe' $nodeFallbacks
    $npmPath = Get-ToolPath 'npm.cmd' @('C:\Program Files\nodejs\npm.cmd', (Join-Path $env:ProgramFiles 'nodejs\npm.cmd'))
    if (-not $nodePath -or -not $npmPath) {
        Install-WingetPackage 'OpenJS.NodeJS.LTS' 'Node.js LTS (includes npm)'
        $nodePath = Get-ToolPath 'node.exe' $nodeFallbacks
        $npmPath = Get-ToolPath 'npm.cmd' @('C:\Program Files\nodejs\npm.cmd', (Join-Path $env:ProgramFiles 'nodejs\npm.cmd'))
    }
    if (-not $nodePath -or -not $npmPath) { throw 'Node.js installation completed but node/npm are not available. Restart Windows and try again.' }
    & $nodePath -e "process.exit(Number(process.versions.node.split('.')[0]) >= 20 ? 0 : 1)"
    if ($LASTEXITCODE -ne 0) { throw 'Node.js 20 or later is required. Update Node.js LTS and retry.' }

    Write-Host 'Preparing the locked Python environment (Python itself is downloaded automatically if needed)...'
    & $uv sync --locked --python 3.12
    if ($LASTEXITCODE -ne 0) { throw 'Python environment setup failed. Check your internet connection and try again.' }
    $pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'uv finished without creating the project Python environment.' }
    & $pythonPath (Join-Path $PSScriptRoot 'repair-local-database.py')
    if ($LASTEXITCODE -ne 0) { throw 'Local database validation or repair failed. Review the error above before retrying.' }

    $lockFile = Join-Path $projectRoot 'package-lock.json'
    $npmStamp = Join-Path $launchRoot 'npm-lock.sha256'
    $lockHash = (Get-FileHash -LiteralPath $lockFile -Algorithm SHA256).Hash
    $installedHash = if (Test-Path -LiteralPath $npmStamp) { (Get-Content -LiteralPath $npmStamp -Raw).Trim() } else { '' }
    if (-not (Test-Path 'node_modules\vite') -or -not (Test-Path 'node_modules\pptxgenjs') -or $installedHash -ne $lockHash) {
        Write-Host 'Installing locked web and rendering dependencies...'
        & $npmPath ci
        if ($LASTEXITCODE -ne 0) { throw 'npm dependency installation failed. Check your internet connection and try again.' }
        Set-Content -LiteralPath $npmStamp -Value $lockHash -Encoding ASCII
    }
    & $nodePath --input-type=module -e "import { chromium } from 'playwright'; import fs from 'node:fs'; process.exit(fs.existsSync(chromium.executablePath()) ? 0 : 1)"
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Installing the local slide-rendering browser...'
        & (Join-Path $projectRoot 'node_modules\.bin\playwright.cmd') install chromium
        if ($LASTEXITCODE -ne 0) { throw 'Rendering browser installation failed. Check your internet connection and try again.' }
    }
    Write-Host 'Building the website...'
    & $npmPath run build
    if ($LASTEXITCODE -ne 0) { throw 'Website build failed. The server was not started.' }

    $stdout = Join-Path $launchRoot "server-$Port.log"
    $stderr = Join-Path $launchRoot "server-$Port-error.log"
    $arguments = '-m uvicorn app.main:app --app-dir "{0}" --host 127.0.0.1 --port {1}' -f $appDirectory, $Port
    $env:YINGZHANG_PUBLIC_TEST_MODE = 'false'
    $env:YINGZHANG_PRIVATE_ACCOUNTS_MODE = 'false'
    $worker = Join-Path $PSScriptRoot 'run-local-server.ps1'
    $command = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -PythonPath "{1}" -Port {2} -NodeDirectory "{3}"' -f $worker, $pythonPath, $Port, (Split-Path -Parent $nodePath)
    $startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow = [uint16]0 }
    $created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $command; CurrentDirectory = $projectRoot; ProcessStartupInformation = $startup }
    if ($created.ReturnValue -ne 0) { throw "Could not start background service (code $($created.ReturnValue))." }
    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Milliseconds 500
        if (-not (Get-Process -Id $created.ProcessId -ErrorAction SilentlyContinue)) { break }
        if (Test-OurHealth) { $ready = $true; break }
    }
    if (-not $ready) {
        Get-OurServerProcess | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
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
