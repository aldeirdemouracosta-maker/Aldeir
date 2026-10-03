@echo off
REM Instala o FrameLTX Studio em um ambiente virtual (.venv). Windows.
cd /d "%~dp0"
python -c "import sys; assert sys.version_info >= (3, 10)" || (echo Instale o Python 3.10+ em python.org & pause & exit /b 1)
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
if not exist config.json copy config.example.json config.json
echo Instalado. Inicie o ComfyUI e depois rode run.bat
pause
