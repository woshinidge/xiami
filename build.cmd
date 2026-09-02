@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"
pwsh.exe -NoProfile -NonInteractive -File "%ROOT%scripts\build.ps1" %*
exit /b %ERRORLEVEL%
