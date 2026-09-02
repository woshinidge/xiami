@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"
pwsh.exe -NoProfile -NonInteractive -File "%ROOT%scripts\test.ps1" %*
exit /b %ERRORLEVEL%
