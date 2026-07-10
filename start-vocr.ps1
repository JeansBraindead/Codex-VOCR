param(
    [switch]$Console
)

$ErrorActionPreference = "Stop"

function Invoke-Checked($Exe, $Arguments, $FailureMessage) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw $FailureMessage }
}

try {
    $repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
    Set-Location -LiteralPath $repoRoot

    if (-not (Test-Path "pyproject.toml")) {
        throw "Hier liegt kein VOCR-Repo: pyproject.toml fehlt. Starte dieses Skript aus dem geklonten Codex-VOCR-Ordner."
    }

    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        Write-Host "[VOCR] .venv fehlt, starte Installer zuerst." -ForegroundColor Yellow
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repoRoot "install-vocr.ps1") -NoStart
    }

    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    Invoke-Checked -Exe $venvPython -Arguments @("-m", "pip", "install", "-e", ".") -FailureMessage "pip install -e . ist fehlgeschlagen."
    Invoke-Checked -Exe $venvPython -Arguments @("-m", "vocr.main", "bootstrap", "--no-start") -FailureMessage "VOCR Bootstrap ist fehlgeschlagen."

    if ($Console) {
        Invoke-Checked -Exe $venvPython -Arguments @("-m", "vocr.main", "start", "--console") -FailureMessage "VOCR Start ist fehlgeschlagen."
    } else {
        Invoke-Checked -Exe $venvPython -Arguments @("-m", "vocr.main", "start") -FailureMessage "VOCR Start ist fehlgeschlagen."
    }
} catch {
    Write-Host ""
    Write-Host "VOCR Start konnte nicht abgeschlossen werden:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Write-Host "Fallback: Starte .\Start-VOCR.bat oder fuehre .\install-vocr.ps1 erneut aus." -ForegroundColor Yellow
    exit 1
}
