# Dot-sourceable runtime discovery and repair; never trust a copied virtual environment.
function Invoke-ManifoldPythonProbe {
    param([string]$Executable, [string[]]$PrefixArgs = @())
    if (!$Executable) { return $null }
    try {
        $code = "import json,sys,struct; print(json.dumps(dict(executable=sys.executable,prefix=sys.prefix,base=sys.base_prefix,base_executable=getattr(sys,'_base_executable',sys.executable),version=list(sys.version_info[:3]),bits=struct.calcsize('P')*8)))"
        $result = & $Executable @PrefixArgs -I -c $code 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        $probe = ($result -join "`n") | ConvertFrom-Json
        if ($probe.version[0] -eq 3 -and $probe.version[1] -eq 11 -and $probe.bits -eq 64 -and (Test-Path -LiteralPath $probe.base_executable)) { return $probe }
    } catch {}
    return $null
}

function Find-ManifoldPython {
    param([string]$Python = '')
    if ($Python) {
        $probe = Invoke-ManifoldPythonProbe $Python
        if (!$probe) { throw 'The specified -Python must be a working Python 3.11 x64 executable.' }
        return $probe.base_executable
    }
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        $probe = Invoke-ManifoldPythonProbe $launcher.Source @('-3.11')
        if ($probe) { return $probe.base_executable }
    }
    $uvCandidates = @()
    $uvCommand = Get-Command uv.exe -ErrorAction SilentlyContinue
    if ($uvCommand) { $uvCandidates += $uvCommand.Source }
    foreach ($relative in @('.local\bin\uv.exe', '.cargo\bin\uv.exe')) {
        $candidate = Join-Path $env:USERPROFILE $relative
        if (Test-Path -LiteralPath $candidate) { $uvCandidates += $candidate }
    }
    foreach ($uvExecutable in $uvCandidates | Select-Object -Unique) {
        try {
            $found = & $uvExecutable python find --system --no-python-downloads 3.11 2>$null
            if ($LASTEXITCODE -eq 0 -and $found) {
                $probe = Invoke-ManifoldPythonProbe (($found -join "`n").Trim())
                if ($probe) { return $probe.base_executable }
            }
        } catch {}
    }
    $candidates = @()
    foreach ($name in @('python3.11.exe', 'python.exe', 'python3.exe')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) { $candidates += $command.Source }
    }
    foreach ($root in @((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311'), 'C:\Python311', (Join-Path $env:ProgramFiles 'Python311'))) { $candidates += Join-Path $root 'python.exe' }
    foreach ($root in @($env:UV_PYTHON_INSTALL_DIR, (Join-Path $env:APPDATA 'uv\python'), (Join-Path $env:LOCALAPPDATA 'uv\python'))) {
        if ($root -and (Test-Path -LiteralPath $root)) { $candidates += Get-ChildItem -LiteralPath $root -Directory -Filter 'cpython-3.11*-windows-*' | ForEach-Object { Join-Path $_.FullName 'python.exe' } }
    }
    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (!(Test-Path -LiteralPath $candidate)) { continue }
        $probe = Invoke-ManifoldPythonProbe $candidate
        if ($probe) { return $probe.base_executable }
    }
    throw 'Python 3.11 x64 was not found. Install it with Python.org or uv python install 3.11, or pass -Python "C:\path\python.exe". No source edits are needed.'
}

function Test-ManifoldVenv {
    param([string]$Root)
    $environment = [IO.Path]::GetFullPath((Join-Path $Root '.venv'))
    $probe = Invoke-ManifoldPythonProbe (Join-Path $environment 'Scripts\python.exe')
    if (!$probe -or [IO.Path]::GetFullPath($probe.prefix).TrimEnd('\') -ine $environment.TrimEnd('\')) { return $false }
    $config = Join-Path $environment 'pyvenv.cfg'
    if (!(Test-Path -LiteralPath $config)) { return $false }
    $command = Get-Content -LiteralPath $config | Where-Object { $_ -like 'command = *' }
    if ($command -and $command -notlike ('*' + $environment + '*')) { return $false }
    return $true
}

function Backup-ManifoldVenv {
    param([string]$Root)
    $workspace = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $source = [IO.Path]::GetFullPath((Join-Path $workspace '.venv'))
    if ($source -ine ($workspace + '\.venv')) { throw 'Environment path is outside the project.' }
    if (!(Test-Path -LiteralPath $source)) { return }
    $item = Get-Item -LiteralPath $source -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'The .venv directory is a link. Choose a regular project environment before automatic repair.' }
    $folder = [IO.Path]::GetFullPath((Join-Path $workspace 'output\runtime-backups'))
    if (!$folder.StartsWith($workspace + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Backup path is outside the project.' }
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
    $destination = Join-Path $folder ('venv-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8))
    Move-Item -LiteralPath $source -Destination $destination
    Write-Host 'Preserved the copied/invalid environment under output/runtime-backups; rebuilding .venv for this computer.'
}

function Initialize-ManifoldVenv {
    param([string]$Root, [string]$Python)
    if (Test-ManifoldVenv $Root) { return $false }
    $basePython = Find-ManifoldPython $Python
    Backup-ManifoldVenv $Root
    $environment = Join-Path $Root '.venv'
    & $basePython -m venv $environment
    if ($LASTEXITCODE -ne 0 -or !(Test-ManifoldVenv $Root)) { throw 'Python environment creation failed; the previous environment remains in output/runtime-backups.' }
    return $true
}

function Find-ManifoldNode {
    param([string]$Node = '')
    $candidates = @()
    if ($Node) { $candidates += $Node } else {
        $command = Get-Command node.exe -ErrorAction SilentlyContinue
        if ($command) { $candidates += $command.Source }
        $candidates += Join-Path $env:ProgramFiles 'nodejs\node.exe'
        $candidates += Join-Path $env:LOCALAPPDATA 'Programs\nodejs\node.exe'
    }
    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (!(Test-Path -LiteralPath $candidate)) { continue }
        try {
            $data = & $candidate -p 'JSON.stringify({version:process.versions.node,platform:process.platform,arch:process.arch})' 2>$null
            if ($LASTEXITCODE -ne 0) { continue }
            $probe = $data | ConvertFrom-Json
            $version = [version]$probe.version
            $npmCli = Join-Path (Split-Path -Parent $candidate) 'node_modules\npm\bin\npm-cli.js'
            if ((($version.Major -eq 22 -and $version.Minor -ge 12) -or $version.Major -ge 24) -and (Test-Path -LiteralPath $npmCli)) { return [pscustomobject]@{ Executable=$candidate; NpmCli=$npmCli; Version=$probe.version; Platform=$probe.platform; Architecture=$probe.arch } }
        } catch {}
    }
    throw 'Install Node.js 22.12+ or 24+ with npm, or pass -Node "C:\path\node.exe". Copied node_modules is not a Node runtime.'
}
