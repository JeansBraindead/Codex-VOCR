param([switch]$Console)

$ErrorActionPreference = 'Stop'
function Pause-OnInteractiveError {
    if ($Host.Name -eq 'ConsoleHost' -and [Environment]::UserInteractive -and -not $env:CI -and -not $env:VOCR_NO_PAUSE_ON_ERROR) {
        try { Read-Host 'Druecke Enter zum Schliessen' | Out-Null } catch {}
    }
}

function Invoke-Checked($Exe, $Arguments, $FailureMessage) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw $FailureMessage }
}

try {
    Set-Location -LiteralPath $PSScriptRoot
    if (-not (Test-Path 'pyproject.toml')) { throw 'Hier liegt kein VOCR-Repo: pyproject.toml fehlt. Starte dieses Skript aus dem geklonten Codex-VOCR-Ordner.' }
    if (-not (Test-Path '.venv\Scripts\python.exe')) {
        Write-Host '[VOCR] .venv fehlt, starte Installer zuerst.' -ForegroundColor Yellow
        Invoke-Checked -Exe 'powershell' -Arguments @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path (Get-Location) 'install-vocr.ps1'), '-NoStart') -FailureMessage 'VOCR Installer ist fehlgeschlagen.'
    }
    $venvPython = Join-Path (Get-Location) '.venv\Scripts\python.exe'
    Invoke-Checked -Exe $venvPython -Arguments @('-m', 'pip', 'install', '-e', '.') -FailureMessage 'pip install -e . ist fehlgeschlagen.'
    Invoke-Checked -Exe $venvPython -Arguments @('-m', 'vocr.main', 'bootstrap', '--no-start') -FailureMessage 'VOCR Bootstrap ist fehlgeschlagen.'
    if ($Console) { Invoke-Checked -Exe $venvPython -Arguments @('-m', 'vocr.main', 'start', '--console') -FailureMessage 'VOCR Start ist fehlgeschlagen.' }
    else { Invoke-Checked -Exe $venvPython -Arguments @('-m', 'vocr.main', 'start') -FailureMessage 'VOCR Start ist fehlgeschlagen.' }
} catch {
    Write-Host ''
    Write-Host 'VOCR Start konnte nicht abgeschlossen werden:' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ''
    Write-Host 'Fallback: Starte .\Start-VOCR.bat oder fuehre .\install-vocr.ps1 erneut aus.' -ForegroundColor Yellow
    Pause-OnInteractiveError
    exit 1
}
