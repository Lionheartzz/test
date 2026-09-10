param([switch]$Setup, [switch]$NoBrowser, [switch]$LAN, [switch]$CheckEnvironment, [string]$Python = '', [string]$Node = '')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
. (Join-Path $PSScriptRoot 'scripts\runtime.ps1')
if ($CheckEnvironment) {
    $basePython = Find-ManifoldPython $Python
    $nodeRuntime = Find-ManifoldNode $Node
    [pscustomobject]@{ Python311=$basePython; VenvHealthy=(Test-ManifoldVenv $PSScriptRoot); Node=$nodeRuntime.Executable; NodeVersion=$nodeRuntime.Version }
    return
}
$existing = $null
try { $existing = Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 2 } catch {}
if ($existing -and $existing.service -eq 'pmc-manifold' -and !$Setup) {
    if ($LAN -and $existing.network.mode -ne 'lan') { throw 'PMC is already running in local mode. Stop its console (Ctrl+C), then run Start-Manifold-LAN.cmd.' }
    Write-Host 'PMC is already running at http://127.0.0.1:8765'
    if (!$NoBrowser) { Start-Process 'http://127.0.0.1:8765' }
    return
}
$nodeRuntime = Find-ManifoldNode $Node
$recreated = Initialize-ManifoldVenv $PSScriptRoot $Python
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$pythonHealthy = $false
try { & $pythonPath -c 'from manifold.cad import cq; import fastapi,uvicorn' 2>$null; $pythonHealthy = $LASTEXITCODE -eq 0 } catch {}
if ($Setup -or $recreated -or !$pythonHealthy) {
    & $pythonPath -m pip install -r (Join-Path $PSScriptRoot 'requirements-lock.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed. Retry -Setup; the previous environment backup is preserved.' }
}
$nodeHealthy = $false
try { & $nodeRuntime.Executable --input-type=module -e "await import('vite')" 2>$null; $nodeHealthy = $LASTEXITCODE -eq 0 } catch {}
$stampPath = Join-Path $PSScriptRoot 'node_modules\.pmc-runtime.json'
$stamp = @{ root=$PSScriptRoot; node=$nodeRuntime.Version; platform=$nodeRuntime.Platform; arch=$nodeRuntime.Architecture; lock=(Get-FileHash -LiteralPath 'package-lock.json' -Algorithm SHA256).Hash }
$changedRuntime = $false
if (Test-Path -LiteralPath $stampPath) {
    try { $prior = Get-Content -LiteralPath $stampPath -Raw | ConvertFrom-Json; foreach ($key in $stamp.Keys) { if ($prior.$key -ne $stamp[$key]) { $changedRuntime=$true } } } catch { $changedRuntime=$true }
}
if ($Setup -or !$nodeHealthy -or $changedRuntime) {
    & $nodeRuntime.Executable $nodeRuntime.NpmCli ci
    if ($LASTEXITCODE -ne 0) { throw 'Node dependency installation failed. Retry -Setup with a supported Node runtime.' }
}
$stamp | ConvertTo-Json | Set-Content -LiteralPath $stampPath -Encoding UTF8
& $nodeRuntime.Executable $nodeRuntime.NpmCli run build
if ($LASTEXITCODE -ne 0) { throw 'Web console build failed.' }
if ($existing) { Write-Host 'Setup completed. Restart the existing PMC console to load this runtime.'; return }
if (!$NoBrowser) {
    $browserScript = Join-Path $PSScriptRoot 'scripts\open-browser.ps1'
    Start-Process powershell.exe -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $browserScript + '"')) -WindowStyle Hidden
}
Write-Host 'PMC: http://127.0.0.1:8765 - Ctrl+C stops the service.'
if ($LAN) {
    Write-Host 'LAN mode: use a URL printed below. Allow TCP 8765 on the Windows Private network profile if prompted.'
    & $pythonPath -m manifold serve --lan
} else { & $pythonPath -m manifold serve }
if ($LASTEXITCODE -ne 0) { throw 'PMC service stopped with an error.' }
