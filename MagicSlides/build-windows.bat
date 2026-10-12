@echo off
REM Gera dist\MagicSlides\MagicSlides.exe e, se o Inno Setup estiver instalado,
REM o instalador dist\MagicSlides-Setup-1.0.0.exe
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe call instalar-windows.bat
call .venv\Scripts\activate.bat
python -m pip install -r requirements-dev.txt || exit /b 1
python -m pytest -q || exit /b 1
pyinstaller packaging\MagicSlides.spec --noconfirm --distpath dist --workpath build || exit /b 1
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist %ISCC% (
  %ISCC% packaging\installer.iss || exit /b 1
) else (
  echo Inno Setup nao encontrado: pulei o instalador. Baixe em https://jrsoftware.org/isdl.php
)
echo.
echo Pronto: dist\MagicSlides\MagicSlides.exe
pause
