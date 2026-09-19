#!/bin/sh
# run-qemu.sh — sobe a imagem do alvo 'qemu' (CPU-only, ver
# docs/architecture.md sobre a decisão de não usar GPU virtual).
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IA_LINUX_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILDROOT_VERSION="${BUILDROOT_VERSION:-2026.08}"
IMAGES_DIR="${IA_LINUX_ROOT}/.build/buildroot-${BUILDROOT_VERSION}/output/images"

if [ ! -f "${IMAGES_DIR}/bzImage" ]; then
    echo "run-qemu.sh: bzImage não encontrado em ${IMAGES_DIR}" >&2
    echo "  rode: scripts/configure.sh qemu && scripts/compile.sh" >&2
    exit 1
fi

exec qemu-system-x86_64 \
    -kernel "${IMAGES_DIR}/bzImage" \
    -drive "file=${IMAGES_DIR}/rootfs.ext2,if=virtio,format=raw" \
    -append "root=/dev/vda rootfstype=ext4 console=ttyS0" \
    -m 2048 -smp 4 \
    -nographic
