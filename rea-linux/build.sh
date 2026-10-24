#!/bin/bash
# Gera a ISO do REA Linux.
#
# Modo recomendado (qualquer Linux com Docker ou Podman, ex.: o PC H61 com Ubuntu):
#   sudo ./build.sh
# Ele roda o live-build dentro de um container Debian 13, que e o ambiente oficial.
#
# Modo direto (so em Debian 13 com live-build instalado):
#   sudo ./build.sh --direto
#
# Resultado: rea-linux-AAAAMMDD.iso nesta pasta.
set -euo pipefail

PASTA="$(cd "$(dirname "$0")" && pwd)"
DATA="$(date +%Y%m%d)"
ISO_FINAL="rea-linux-${DATA}.iso"

if [ "$(id -u)" -ne 0 ]; then
    echo "Rode com sudo: sudo ./build.sh" >&2
    exit 1
fi

construir() {
    cd "$PASTA"
    chmod +x auto/* config/hooks/normal/*.hook.chroot config/includes.chroot/usr/local/bin/*
    lb clean --purge || true
    lb config
    lb build
    local iso
    iso="$(ls -1 ./*.hybrid.iso 2>/dev/null | head -n1 || true)"
    if [ -z "$iso" ]; then
        echo "ERRO: a ISO nao foi gerada. Veja build.log" >&2
        exit 1
    fi
    mv -f "$iso" "$ISO_FINAL"
    sha256sum "$ISO_FINAL" > "${ISO_FINAL}.sha256"
    echo
    echo "ISO pronta: $PASTA/$ISO_FINAL ($(du -h "$ISO_FINAL" | cut -f1))"
}

if [ "${1:-}" = "--direto" ] || [ "${DENTRO_DO_CONTAINER:-0}" = "1" ]; then
    if ! command -v lb >/dev/null; then
        apt-get update
        apt-get install -y live-build debian-archive-keyring
    fi
    construir
    exit 0
fi

MOTOR=""
if command -v docker >/dev/null; then MOTOR=docker
elif command -v podman >/dev/null; then MOTOR=podman
fi
if [ -z "$MOTOR" ]; then
    echo "Docker/Podman nao encontrado. Instale (sudo apt install docker.io) ou use --direto num Debian 13." >&2
    exit 1
fi

echo "[..] Construindo dentro de container debian:trixie com $MOTOR (privilegiado, necessario para o live-build)"
"$MOTOR" run --rm --privileged \
    -v "$PASTA":/build -w /build \
    -e DENTRO_DO_CONTAINER=1 \
    debian:trixie \
    bash -c "apt-get update && apt-get install -y live-build debian-archive-keyring && ./build.sh"

# devolve os arquivos ao usuario que chamou o sudo
if [ -n "${SUDO_UID:-}" ]; then
    chown "$SUDO_UID:$SUDO_GID" "$PASTA"/rea-linux-*.iso* "$PASTA"/build.log 2>/dev/null || true
fi
