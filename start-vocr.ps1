param(
    [switch]$Console
)

$ErrorActionPreference = "Stop"

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
    & $venvPython -m pip install -e .
    & $venvPython -m vocr.main bootstrap --no-start

    if ($Console) {
        & $venvPython -m vocr.main start --console
    } else {
        & $venvPython -m vocr.main start
    }
} catch {
    Write-Host ""
    Write-Host "VOCR Start konnte nicht abgeschlossen werden:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Write-Host "Fallback: Starte .\Start-VOCR.bat oder fuehre .\install-vocr.ps1 erneut aus." -ForegroundColor Yellow
    exit 1
}
