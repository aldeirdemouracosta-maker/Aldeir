@echo off
REM Inicia a interface. Ex.: run.bat --demo
cd /d "%~dp0"
.venv\Scripts\python app.py %*
pause
