param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$portalRoot = $PSScriptRoot
$portalCandidates = @(
    (Join-Path $portalRoot '.venv/Scripts/python.exe'),
    (Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
)
$portalPython = $portalCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $portalPython) {
    $portalCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($portalCommand) { $portalPython = $portalCommand.Source }
}
if (-not $portalPython) {
    throw 'Can cai Python 3.11+ va openpyxl. Xem README.md.'
}
$env:PYTHONIOENCODING = 'utf-8'
Push-Location -LiteralPath $portalRoot
try { & $portalPython server.py --port $Port }
finally { Pop-Location }
