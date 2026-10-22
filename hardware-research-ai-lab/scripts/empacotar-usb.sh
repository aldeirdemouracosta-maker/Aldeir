#!/bin/sh
# Gera um pacote portátil do HRAIL (binário estático + configs + catálogos + scripts) em DESTINO.
# Uso: scripts/empacotar-usb.sh /media/usuario/PENDRIVE/hrail
set -eu
dest="${1:?uso: $0 DIRETORIO_DESTINO}"
cd "$(dirname "$0")/.."
CGO_ENABLED=0 go build -trimpath -o bin/hrail ./cmd/hrail
mkdir -p "$dest/configs" "$dest/data" "$dest/reports" "$dest/scripts"
cp bin/hrail "$dest/hrail"
cp configs/hrail.json "$dest/configs/"
cp scripts/coletar-na-maquina.sh "$dest/scripts/"
echo "Pacote em $dest. Na máquina alvo: cd $dest && ./scripts/coletar-na-maquina.sh"
