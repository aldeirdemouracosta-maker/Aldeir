@echo off
REM Instala as dependências para rodar o MagicSlides a partir do código-fonte.
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% -m venv .venv || goto :erro
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt || goto :erro
echo.
echo Pronto! Agora execute: executar-windows.bat
pause
exit /b 0
:erro
echo.
echo Falha na instalacao. Instale o Python 3.10+ em https://www.python.org/downloads/ (marque "Add python.exe to PATH").
pause
exit /b 1
