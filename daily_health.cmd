@echo off
rem Double-click launcher for daily_health.ps1 (.ps1 files open in Notepad by default).
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0daily_health.ps1" %*
exit /b %ERRORLEVEL%
