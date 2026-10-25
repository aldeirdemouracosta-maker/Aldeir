#!/usr/bin/env bash
# REA-Laboratorio OS - esqueleto de build (Debian live-build). NAO TESTADO nesta fase.
# Roda somente em host Debian/Ubuntu (VM ou container privilegiado; NAO no Windows direto).
# Trabalha apenas em ./build-iso/ ; nunca toca discos nem particoes do host.
set -euo pipefail
[[ "${1:-}" == "--confirmo-build" ]] || { echo "Uso: $0 --confirmo-build   (veja docs/BUILD-ISO.md)"; exit 2; }
command -v lb >/dev/null || { echo "live-build ausente: sudo apt install live-build (veja docs/BUILD-ISO.md)"; exit 3; }
DIR="$(cd "$(dirname "$0")/.." && pwd)/build-iso"
mkdir -p "$DIR" && cd "$DIR"
# Validar as opcoes contra 'lb config --help' da versao instalada antes do 1o build.
lb config \
  --distribution trixie --architectures amd64 \
  --binary-images iso-hybrid --bootloaders "syslinux,grub-efi" \
  --debian-installer none --apt-recommends false --compression xz \
  --iso-volume "REA-LAB-OS" --bootappend-live "boot=live components noswap quiet"
echo "Configuracao gerada em $DIR. Adicione listas de pacotes em config/package-lists/ e rode: sudo lb build"
