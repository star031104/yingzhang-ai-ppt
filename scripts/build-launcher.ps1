$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$compilerCandidates = @(
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'),
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe')
)
$compiler = $compilerCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $compiler) { throw 'The .NET Framework C# compiler was not found. Run this script on Windows with .NET Framework 4.x installed.' }
$output = Join-Path $root '启动映章.exe'
& $compiler /nologo /target:winexe /optimize+ /r:System.Windows.Forms.dll "/out:$output" (Join-Path $root 'launcher\Program.cs')
if ($LASTEXITCODE -ne 0) { throw 'Launcher compilation failed.' }
Write-Host "Built $output" -ForegroundColor Green
