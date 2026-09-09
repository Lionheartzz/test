$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'runtime.ps1')
$testBasePython = Find-ManifoldPython
$testRoot = Join-Path $projectRoot ('output\runtime-tests\' + [guid]::NewGuid().ToString('N'))
$originalRoot = Join-Path $testRoot 'original'
$copiedRoot = Join-Path $testRoot 'copied project'
New-Item -ItemType Directory -Path $originalRoot,$copiedRoot -Force | Out-Null
& $testBasePython -m venv (Join-Path $originalRoot '.venv')
if ($LASTEXITCODE -ne 0) { throw 'Fixture venv creation failed.' }
Copy-Item -LiteralPath (Join-Path $originalRoot '.venv') -Destination (Join-Path $copiedRoot '.venv') -Recurse
if (Test-ManifoldVenv $copiedRoot) { throw 'A copied environment was incorrectly accepted.' }
# Reproduce an environment whose base interpreter belonged to another Windows user.
$configPath = Join-Path $copiedRoot '.venv\pyvenv.cfg'
$config = Get-Content -LiteralPath $configPath -Raw
$config = $config -replace '(?m)^home = .*$', 'home = C:\Users\Other-PC-User\MissingPython311'
$config = $config -replace '(?m)^executable = .*$', 'executable = C:\Users\Other-PC-User\MissingPython311\python.exe'
Set-Content -LiteralPath $configPath -Value $config -Encoding ASCII
if (Test-ManifoldVenv $copiedRoot) { throw 'A missing base interpreter was incorrectly accepted.' }
$created = Initialize-ManifoldVenv $copiedRoot $testBasePython
if (!$created -or !(Test-ManifoldVenv $copiedRoot)) { throw 'Copied environment was not repaired.' }
$backups = @(Get-ChildItem -LiteralPath (Join-Path $copiedRoot 'output\runtime-backups') -Directory)
if ($backups.Count -ne 1 -or !(Test-Path -LiteralPath (Join-Path $backups[0].FullName 'pyvenv.cfg'))) { throw 'Original copied environment was not preserved.' }
if (Initialize-ManifoldVenv $copiedRoot $testBasePython) { throw 'A healthy environment was unnecessarily replaced.' }

# Exercise the real uv discovery branch without installing uv or downloading Python.
function Invoke-TestUv { $script:testUvArgs=$args; $global:LASTEXITCODE=0; return $script:testBasePython }
function Get-Command {
    [CmdletBinding()]param([string]$Name)
    if ($Name -eq 'py.exe') { return $null }
    if ($Name -eq 'uv.exe') { return [pscustomobject]@{Source='Invoke-TestUv'} }
    return Microsoft.PowerShell.Core\Get-Command -Name $Name -ErrorAction SilentlyContinue
}
$fromUv = Find-ManifoldPython
if ($fromUv -ne $testBasePython -or ($testUvArgs -join ' ') -ne 'python find --system --no-python-downloads 3.11') { throw 'uv Python discovery did not select the installed 3.11 interpreter.' }
Remove-Item Function:\Get-Command
Remove-Item Function:\Invoke-TestUv
$nodeRuntime = Find-ManifoldNode
& $nodeRuntime.Executable $nodeRuntime.NpmCli --version
if ($LASTEXITCODE -ne 0) { throw 'npm did not run through the selected Node executable.' }
[pscustomobject]@{ Result='PASS'; CopiedVenvRebuilt=$true; OriginalPreserved=$true; UvDiscoveryBranch=$true; NodeAndNpm=$true; Evidence=$testRoot } | ConvertTo-Json
