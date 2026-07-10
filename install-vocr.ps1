param(
    [switch]$Tests,
    [switch]$NoStart,
    [string]$InstallDir = "Codex-VOCR",
    [string]$RepoUrl = "https://github.com/JeansBraindead/Codex-VOCR.git"
)

$ErrorActionPreference = "Stop"

function Write-Step($Message) {
    Write-Host "[VOCR] $Message" -ForegroundColor Cyan
}

function Invoke-Checked($Exe, $Arguments, $FailureMessage) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw $FailureMessage }
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
    if ($python) {
        & python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" *> $null
        if ($LASTEXITCODE -eq 0) { return @{ Exe = "python"; Args = @() } }
    }
    throw "Python 3.11+ wurde nicht gefunden. Installiere Python 3.11 oder neuer und starte den Installer erneut."
}

try {
    $repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
    Set-Location -LiteralPath $repoRoot

    if (-not (Test-Path "pyproject.toml")) {
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            throw "Hier liegt kein VOCR-Repo und Git wurde nicht gefunden. Installiere Git fuer Windows: https://git-scm.com/download/win"
        }
        $target = Join-Path $repoRoot $InstallDir
        if (Test-Path (Join-Path $target "pyproject.toml")) {
            Write-Step "Nutze vorhandenes Repo: $target"
        } elseif (Test-Path $target) {
            throw "Zielordner existiert bereits, ist aber kein VOCR-Repo: $target. Bitte gib mit -InstallDir einen leeren oder passenden Ordner an."
        } else {
            Write-Step "Kein VOCR-Repo gefunden. Klone nach: $target"
            Invoke-Checked -Exe "git" -Arguments @("clone", $RepoUrl, $target) -FailureMessage "Git clone ist fehlgeschlagen. Pruefe Repo-URL, Netzwerk und Git-Anmeldung."
        }
        Set-Location -LiteralPath $target
        $repoRoot = $target
    }

    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "Git wurde nicht gefunden. Installiere Git fuer Windows: https://git-scm.com/download/win"
    }

    $pythonCmd = Resolve-Python
    Write-Step "Repo: $repoRoot"

    if (-not (Test-Path ".venv")) {
        Write-Step "Lege .venv an"
        Invoke-Checked -Exe $pythonCmd.Exe -Arguments ($pythonCmd.Args + @("-m", "venv", ".venv")) -FailureMessage "Virtuelle Umgebung konnte nicht angelegt werden."
    } else {
        Write-Step "Nutze vorhandene .venv"
    }

    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        throw ".venv wurde gefunden, aber .venv\Scripts\python.exe fehlt. Bitte .venv pruefen oder neu anlegen."
    }

    Write-Step "Installiere VOCR editable"
    Invoke-Checked -Exe $venvPython -Arguments @("-m", "pip", "install", "-e", ".") -FailureMessage "pip install -e . ist fehlgeschlagen."

    $bootstrapArgs = @("bootstrap", "--no-start", "--write-scripts")
    if ($Tests) { $bootstrapArgs += "--tests" }

    Write-Step "Fuehre VOCR Bootstrap aus"
    Invoke-Checked -Exe $venvPython -Arguments (@("-m", "vocr.main") + $bootstrapArgs) -FailureMessage "VOCR Bootstrap ist fehlgeschlagen."

    if (-not $NoStart) {
        Write-Step "Starte VOCR Normalmodus"
        Invoke-Checked -Exe $venvPython -Arguments @("-m", "vocr.main", "start") -FailureMessage "VOCR Start ist fehlgeschlagen."
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
