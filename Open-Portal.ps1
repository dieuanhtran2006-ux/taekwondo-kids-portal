param(
    [ValidateRange(1024,65535)][int]$Port = 8765,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$portalRoot = $PSScriptRoot
$portalUrl = 'http://127.0.0.1:' + $Port
$portalServer = Join-Path $portalRoot 'server.py'
$portalDatabase = Join-Path $portalRoot 'data/portal.sqlite3'

function Test-PortalHealth {
    try {
        $portalHealth = Invoke-RestMethod -Uri ($portalUrl + '/api/health') -TimeoutSec 2 -ErrorAction Stop
        return ($portalHealth.app -eq 'taekwondo-kids-portal' -and $portalHealth.status -eq 'ok')
    } catch { return $false }
}

$portalMutex = [Threading.Mutex]::new($false, ('Local\TaekwondoKidsPortal-' + $Port))
$portalLocked = $false
try {
    $portalLocked = $portalMutex.WaitOne(15000)
    if (-not $portalLocked) { throw 'Another portal launcher is busy. Please retry.' }
    $portalStarted = $false
    if (-not (Test-PortalHealth)) {
        $portalListener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($portalListener) { throw ('Port ' + $Port + ' is occupied by another or older server. No process was stopped.') }
        $portalCandidates = @(
            (Join-Path $portalRoot '.venv/Scripts/python.exe'),
            (Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
        )
        $portalPython = $portalCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        if (-not $portalPython) {
            $portalCommand = Get-Command python -ErrorAction SilentlyContinue
            if ($portalCommand) { $portalPython = $portalCommand.Source }
        }
        if (-not $portalPython) { throw 'Python 3.11+ and openpyxl are required. See README.md.' }
        $portalLogs = Join-Path $portalRoot 'data/logs'
        [IO.Directory]::CreateDirectory($portalLogs) | Out-Null
        $portalStamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
        $portalStdout = Join-Path $portalLogs ('server-' + $Port + '-' + $portalStamp + '.stdout.log')
        $portalStderr = Join-Path $portalLogs ('server-' + $Port + '-' + $portalStamp + '.stderr.log')
        $portalArguments = @('-X','utf8','-u',('"' + $portalServer + '"'),'--host','127.0.0.1','--port',"$Port",'--db',('"' + $portalDatabase + '"'))
        $portalProcess = Start-Process -FilePath $portalPython -ArgumentList $portalArguments -WorkingDirectory $portalRoot -WindowStyle Hidden -RedirectStandardOutput $portalStdout -RedirectStandardError $portalStderr -PassThru
        $portalDeadline = [DateTime]::UtcNow.AddSeconds(12)
        do {
            if (Test-PortalHealth) { $portalStarted = $true; break }
            $portalProcess.Refresh()
            if ($portalProcess.HasExited) { throw ('Server stopped during startup. Read: ' + $portalStderr) }
            Start-Sleep -Milliseconds 250
        } while ([DateTime]::UtcNow -lt $portalDeadline)
        if (-not $portalStarted) { throw ('Server did not become ready. Read: ' + $portalStderr) }
    }
    $portalListener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    Write-Output ('Portal ready: ' + $portalUrl)
    if ($portalListener) { Write-Output ('Server PID: ' + $portalListener.OwningProcess) }
} finally {
    if ($portalLocked) { $portalMutex.ReleaseMutex() }
    $portalMutex.Dispose()
}
if (-not $NoBrowser) { Start-Process -FilePath $portalUrl }
