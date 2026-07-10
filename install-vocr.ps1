param(
    [switch]$Tests,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"

function Write-Step($Message) {
    Write-Host "[VOCR] $Message" -ForegroundColor Cyan
}

function Resolve-Python {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        try {
            & py -3.11 --version *> $null
            if ($LASTEXITCODE -eq 0) { return @{ Exe = "py"; Args = @("-3.11") } }
        } catch {}
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return @{ Exe = "python"; Args = @() } }
    throw "Python 3.11+ wurde nicht gefunden. Installiere Python 3.11 oder neuer und starte den Installer erneut."
}

try {
    $repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
    Set-Location -LiteralPath $repoRoot

    if (-not (Test-Path "pyproject.toml")) {
        throw "Hier liegt kein VOCR-Repo: pyproject.toml fehlt. Starte dieses Skript aus dem geklonten Codex-VOCR-Ordner."
    }

    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "Git wurde nicht gefunden. Installiere Git fuer Windows: https://git-scm.com/download/win"
    }

    $pythonCmd = Resolve-Python
    Write-Step "Repo: $repoRoot"

    if (-not (Test-Path ".venv")) {
        Write-Step "Lege .venv an"
        & $pythonCmd.Exe @($pythonCmd.Args) -m venv .venv
    } else {
        Write-Step "Nutze vorhandene .venv"
    }

    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        throw ".venv wurde gefunden, aber .venv\Scripts\python.exe fehlt. Bitte .venv pruefen oder neu anlegen."
    }

    Write-Step "Installiere VOCR editable"
    & $venvPython -m pip install -e .

    $bootstrapArgs = @("bootstrap", "--no-start", "--write-scripts")
    if ($Tests) { $bootstrapArgs += "--tests" }

    Write-Step "Fuehre VOCR Bootstrap aus"
    & $venvPython -m vocr.main @bootstrapArgs

    if (-not $NoStart) {
        Write-Step "Starte VOCR Normalmodus"
        & $venvPython -m vocr.main start
    } else {
        Write-Step "Installation fertig. Starte spaeter mit: .\start-vocr.ps1"
    }
} catch {
    Write-Host ""
    Write-Host "VOCR Installation konnte nicht abgeschlossen werden:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Write-Host "Naechste Schritte:" -ForegroundColor Yellow
    Write-Host "1. Pruefe, ob du im geklonten Codex-VOCR-Repo bist."
    Write-Host "2. Pruefe Python 3.11+: python --version"
    Write-Host "3. Pruefe Git: git --version"
    Write-Host "4. Wenn PowerShell blockiert, nutze Start-VOCR.bat."
    exit 1
}
