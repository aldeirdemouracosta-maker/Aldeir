#!/usr/bin/env bash
# RASCUNHO NAO TESTADO - validar com Claude Code.
# Gera ISO Debian 13 enxuta p/ IA local. Rodar como root em host Debian/Ubuntu.
set -euo pipefail
cd "$(dirname "$0")"
DESKTOP="${DESKTOP:-minimal}"   # minimal | none
# Tag estavel do llama.cpp (ex.: bNNNN). Confirme em github.com/ggml-org/llama.cpp/tags.
LLAMA_TAG="${LLAMA_TAG:?Defina LLAMA_TAG, ex.: sudo LLAMA_TAG=bNNNN ./build-iso.sh}"

[ "$(id -u)" -eq 0 ] || { echo "Rode como root: sudo ./build-iso.sh"; exit 1; }
if ! command -v lb >/dev/null; then
  apt-get update && apt-get install -y live-build debootstrap xorriso squashfs-tools curl gnupg debian-archive-keyring
fi

rm -rf work && mkdir work && cd work

lb config \
  --distribution trixie \
  --architectures amd64 \
  --archive-areas "main contrib non-free non-free-firmware" \
  --binary-images iso-hybrid \
  --bootappend-live "boot=live components quiet" \
  --debian-installer live \
  --debian-installer-gui false \
  --iso-volume "CODICE" \
  --apt-recommends false \
  --memtest none

# sobrepoe a configuracao do kit
cp -a ../config/. config/
if [ "$DESKTOP" = "minimal" ]; then
  cp ../config/optional/desktop-minimal.list.chroot config/package-lists/desktop-minimal.list.chroot
fi
rm -rf config/optional
chmod +x config/hooks/live/*
mkdir -p config/includes.chroot/usr/share/ia-local
echo "$LLAMA_TAG" > config/includes.chroot/usr/share/ia-local/llama-tag

# apps do Codice (Aether + proxy da Fabrica) dentro da imagem
mkdir -p config/includes.chroot/opt/codice
cp -a ../../aether config/includes.chroot/opt/codice/aether
cp -a ../../fabrica-correcoes config/includes.chroot/opt/codice/fabrica-correcoes
rm -rf config/includes.chroot/opt/codice/aether/tests

# chave do repositorio XanMod (URL citada em xanmod.org)
curl -fsSL https://dl.xanmod.org/archive.key -o config/archives/xanmod.key.chroot
cp config/archives/xanmod.key.chroot config/archives/xanmod.key.binary

lb build 2>&1 | tee build.log
echo "ISO em: $(pwd)/*.iso"
