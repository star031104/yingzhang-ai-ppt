param([string]$PythonPath, [int]$Port = 8000, [string]$NodeDirectory)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:SLIDEFORGE_PUBLIC_TEST_MODE = 'false'
$env:SLIDEFORGE_PRIVATE_ACCOUNTS_MODE = 'false'
$env:Path = "$NodeDirectory;$(Split-Path -Parent $PythonPath);$env:Path"
$logs = Join-Path $projectRoot 'runtime\launcher'
$arguments = '-m uvicorn app.main:app --app-dir "{0}" --host 127.0.0.1 --port {1}' -f (Join-Path $projectRoot 'apps\api'), $Port
$server = Start-Process -FilePath $PythonPath -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput (Join-Path $logs "server-$Port.log") -RedirectStandardError (Join-Path $logs "server-$Port-error.log")
exit $server.ExitCode
