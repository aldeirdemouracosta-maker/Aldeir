@echo off
rem Atualiza o reversa: baixa o codigo novo, recompila e mostra a versao.
cd /d "%~dp0"
echo [1/3] baixando o codigo novo...
git pull
if errorlevel 1 goto erro
echo [2/3] compilando...
go build -o reversa.exe .\cmd\reversa
if errorlevel 1 goto erro
echo [3/3] versao instalada:
reversa.exe version
goto fim
:erro
echo.
echo ERRO: algum passo falhou. Copie a mensagem acima e envie.
:fim
echo.
pause
