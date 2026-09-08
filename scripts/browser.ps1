param([Parameter(ValueFromRemainingArguments=$true)][string[]]$CliArgs)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$env:PWTEST_DAEMON_SESSION_DIR = Join-Path $taskRoot 'output\playwright\daemon'
$bundledNode = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
$taskNode = if (Test-Path -LiteralPath $bundledNode) { $bundledNode } else { (Get-Command node.exe).Source }
Push-Location $taskRoot
try { & $taskNode 'node_modules\@playwright\cli\playwright-cli.js' '-s=pmc' @CliArgs; exit $LASTEXITCODE }
finally { Pop-Location }
