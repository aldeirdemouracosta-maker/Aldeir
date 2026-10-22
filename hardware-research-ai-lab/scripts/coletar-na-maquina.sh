#!/bin/sh
# Coleta somente leitura na máquina onde está o hardware real. Não usa sudo. Escreve só dentro desta pasta.
set -u
cd "$(dirname "$0")/.." || exit 1
H=./hrail; [ -x "$H" ] || H=./bin/hrail
$H doctor
$H init
$H hardware inspect --salvar --saida reports/hardware_inspect.json
$H tools check
$H benchmark selftest
$H report generate
echo "Pronto. Envie reports/hardware_inspect.json e o relatório gerado para análise."
