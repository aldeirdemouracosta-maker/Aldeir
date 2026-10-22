#!/bin/sh
# Verificação ONLINE e somente leitura das fontes (ls-remote, clone raso sem checkout, HEAD HTTP).
# Requer rede. Clones ficam em data/clones (ignorado pelo git). Nada do repositório é executado.
set -eu
cd "$(dirname "$0")/.."
H=./hrail; [ -x "$H" ] || H=./bin/hrail
$H init
$H research verificar --online --clonar --profundidade 50
$H research historico --fonte mgpusim --palavras polaris,gfx803,gfx8,gcn3,gcn4
$H research historico --fonte mesa --palavras polaris,gfx803,gfx8,radv,aco 2>/dev/null || true
$H research commits --revertidos
