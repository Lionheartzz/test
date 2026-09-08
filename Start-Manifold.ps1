param([switch]$Setup, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if ($Setup -or !(Test-Path -LiteralPath $pythonPath)) {
    if (!(Test-Path -LiteralPath $pythonPath)) {
        & py -3.11 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.11 x64, then run Start-Manifold.ps1 -Setup again.' }
    }
    & $pythonPath -m pip install -r requirements-lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    & npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw 'Node dependency installation failed. Use Node.js 22.12+ or 24 LTS.' }
}
if (!(Test-Path -LiteralPath 'node_modules')) { throw 'Run .\Start-Manifold.ps1 -Setup first.' }
$existing = $null
try { $existing = Invoke-RestMethod 'http://127.0.0.1:8765/api/state' -TimeoutSec 2 } catch {}
if ($existing -and $existing.revision -and $existing.design.schema_version -eq 1) {
    Write-Host 'PMC is already running at http://127.0.0.1:8765'
    if (!$NoBrowser) { Start-Process 'http://127.0.0.1:8765' }
    return
}
& $pythonPath -m manifold init
if ($LASTEXITCODE -ne 0) { throw 'Project initialization failed.' }
& npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw 'Web console build failed.' }
& $pythonPath -m manifold build
if ($LASTEXITCODE -ne 0) { Write-Warning 'Model did not pass. Open the console to inspect the report or check the terminal error.' }
if (!$NoBrowser) {
    $browserScript = Join-Path $PSScriptRoot 'scripts\open-browser.ps1'
    Start-Process powershell.exe -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $browserScript + '"')) -WindowStyle Hidden
}
Write-Host 'PMC console: http://127.0.0.1:8765 - Ctrl+C stops the local service.'
& $pythonPath -m manifold serve
