#!/usr/bin/env bash
# RASCUNHO NAO TESTADO - validar com Claude Code.
# Gera ISO Debian 13 enxuta p/ IA local. Rodar como root em host Debian/Ubuntu.
set -euo pipefail
cd "$(dirname "$0")"
DESKTOP="${DESKTOP:-none}"       # minimal | none
PERFIL="${PERFIL:-minimo}"       # minimo (camadas 1 e 2) | completo (+ apps, Aether, Fabrica)
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
  --bootappend-live "boot=live components quiet locales=pt_BR.UTF-8 keyboard-layouts=br timezone=America/Sao_Paulo" \
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

# perfil completo: apps, Aether e proxy da Fabrica dentro da imagem
if [ "$PERFIL" = "completo" ]; then
  cp ../config/optional/completo.list.chroot config/package-lists/completo.list.chroot
  cp ../config/optional/0300-codice-apps.hook.chroot config/hooks/live/
  chmod +x config/hooks/live/*
  mkdir -p config/includes.chroot/opt/codice
  cp -a ../../aether config/includes.chroot/opt/codice/aether
  cp -a ../../fabrica-correcoes config/includes.chroot/opt/codice/fabrica-correcoes
  rm -rf config/includes.chroot/opt/codice/aether/tests
fi

# XanMod (opcional): sem a chave, a ISO sai so com o kernel do Debian
rm -f config/archives/xanmod.list.chroot config/archives/xanmod.list.binary
if curl -fsSL --retry 3 -A "Mozilla/5.0 (X11; Linux x86_64)" https://dl.xanmod.org/archive.key \
     -o config/archives/xanmod.key.chroot && [ -s config/archives/xanmod.key.chroot ]; then
  cp config/archives/xanmod.key.chroot config/archives/xanmod.key.binary
  echo "deb http://deb.xanmod.org trixie main" | tee config/archives/xanmod.list.chroot > config/archives/xanmod.list.binary
  cp ../config/optional/xanmod.list.chroot config/package-lists/xanmod.list.chroot
  echo "XanMod: ATIVADO"
else
  rm -f config/archives/xanmod.key.chroot
  echo "AVISO: nao consegui a chave do XanMod; ISO usara SOMENTE o kernel do Debian" >&2
fi

lb build 2>&1 | tee build.log
echo "ISO em: $(pwd)/*.iso"
