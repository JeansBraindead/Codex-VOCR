@echo off
setlocal
cd /d "%~dp0"

where powershell >nul 2>nul
if %ERRORLEVEL%==0 (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-vocr.ps1"
  exit /b %ERRORLEVEL%
)

if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 goto failed
)

".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m vocr.main bootstrap --no-start
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m vocr.main start
exit /b %ERRORLEVEL%

:failed
echo.
echo VOCR konnte nicht gestartet werden.
echo Pruefe Python 3.11+, Git und ob dieses Skript im Codex-VOCR-Repo liegt.
exit /b 1
