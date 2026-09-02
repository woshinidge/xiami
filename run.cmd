@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"
pwsh.exe -NoProfile -NonInteractive -WindowStyle Hidden -File "%ROOT%scripts\run.ps1" %*
exit /b %ERRORLEVEL%
