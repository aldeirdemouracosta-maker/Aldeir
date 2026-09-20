#!/bin/sh
# compile.sh [alvo make] — compila a imagem já configurada por
# scripts/configure.sh. Sem argumentos, compila tudo ('all').
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IA_LINUX_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILDROOT_VERSION="${BUILDROOT_VERSION:-2026.08}"
BUILDROOT_DIR="${IA_LINUX_ROOT}/.build/buildroot-${BUILDROOT_VERSION}"

if [ ! -f "${BUILDROOT_DIR}/.config" ]; then
    echo "compile.sh: nenhuma configuração encontrada — rode scripts/configure.sh <qemu|bios|uefi> primeiro" >&2
    exit 1
fi

make -C "${BUILDROOT_DIR}" BR2_EXTERNAL="${IA_LINUX_ROOT}" "$@"

echo "compile.sh: build concluído. Imagens em ${BUILDROOT_DIR}/output/images/"
