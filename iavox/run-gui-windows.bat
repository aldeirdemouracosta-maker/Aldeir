@echo off
REM Executa a interface grafica do IAVOX no Windows.
REM Tenta o launcher "py" primeiro (mais confiavel no Windows), com
REM fallback para "python", ja que em algumas instalacoes o comando
REM "python" fica preso no atalho da Microsoft Store.
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel%==0 (
    set PYCMD=py
) else (
    set PYCMD=python
)

echo Verificando dependencias...
%PYCMD% -m pip show PyQt5 >nul 2>&1
set NEED_GUI=%errorlevel%
%PYCMD% -m pip show pdfplumber >nul 2>&1
set NEED_CORE=%errorlevel%

if not %NEED_GUI%==0 goto :install
if not %NEED_CORE%==0 goto :install
goto :run

:install
echo Instalando dependencias (primeira execucao, pode demorar um pouco)...
%PYCMD% -m pip install -r requirements.txt -r requirements-gui.txt
if errorlevel 1 (
    echo.
    echo Falha ao instalar as dependencias. Verifique sua conexao com a
    echo internet e tente rodar manualmente:
    echo     py -m pip install -r requirements.txt -r requirements-gui.txt
    pause
    exit /b 1
)

:run
%PYCMD% run_gui.py
if errorlevel 1 (
    echo.
    echo ==========================================================
    echo Nao foi possivel iniciar com "%PYCMD%".
    echo Tente abrir o Prompt de Comando nesta pasta e rodar:
    echo     py run_gui.py
    echo Se der o mesmo erro, va em: Configuracoes ^> Aplicativos ^>
    echo Configuracoes avancadas do aplicativo ^> Aliases de execucao
    echo do aplicativo, e desative "python.exe" e "python3.exe".
    echo ==========================================================
    pause
)
