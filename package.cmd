@echo off
setlocal
set "ROOT=%~dp0"
pwsh.exe -NoProfile -NonInteractive -File "%ROOT%scripts\package.ps1" %*
exit /b %ERRORLEVEL%
