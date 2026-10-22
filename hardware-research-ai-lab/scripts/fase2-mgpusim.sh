#!/bin/sh
# Fase 2 (Linux): prepara e REVISA o MGPUSim. A aprovação e a execução são passos humanos explícitos.
set -eu
cd "$(dirname "$0")/.."
H=./hrail; [ -x "$H" ] || H=./bin/hrail
$H init
$H research verificar --online --clonar --id mgpusim --profundidade 50
$H simulation preparar
$H simulation revisar --amostra fir
cat <<'MSG'

Depois de LER a revisão acima, se concordar:
  hrail simulation aprovar --amostra fir --commit <commit mostrado acima> --por "seu nome"
  hrail simulation compilar --autorizo-codigo-terceiros      (baixa Go 1.27 e módulos; ~330 MB em data/_sim)
  hrail simulation rodar --autorizo-codigo-terceiros --repeticoes 3
MSG
