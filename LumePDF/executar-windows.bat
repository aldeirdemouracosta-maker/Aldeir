@echo off
cd /d "%~dp0"
if exist .venv\Scripts\pythonw.exe (
  start "" .venv\Scripts\pythonw.exe LumePDF.py
) else (
  echo Rode primeiro instalar-windows.bat
  pause
)
