@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar-windows.ps1" %*
echo.
pause
