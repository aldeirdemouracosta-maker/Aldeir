#!/bin/sh
# configure.sh <qemu|bios|uefi> — aplica o defconfig do alvo escolhido
# sobre a árvore Buildroot baixada por fetch-buildroot.sh, usando este
# diretório (buildroot/) como BR2_EXTERNAL.
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IA_LINUX_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILDROOT_VERSION="${BUILDROOT_VERSION:-2026.08}"
BUILDROOT_DIR="${IA_LINUX_ROOT}/.build/buildroot-${BUILDROOT_VERSION}"

TARGET="${1:-qemu}"

case "${TARGET}" in
    qemu) DEFCONFIG=ia_linux_qemu_x86_64_defconfig ;;
    bios) DEFCONFIG=ia_linux_bios_x86_64_defconfig ;;
    uefi) DEFCONFIG=ia_linux_uefi_x86_64_defconfig ;;
    *)
        echo "uso: $0 <qemu|bios|uefi>" >&2
        exit 1
        ;;
esac

if [ ! -d "${BUILDROOT_DIR}" ]; then
    echo "configure.sh: ${BUILDROOT_DIR} não existe — rode scripts/fetch-buildroot.sh primeiro" >&2
    exit 1
fi

mkdir -p "${BUILDROOT_DIR}/configs"
cp "${IA_LINUX_ROOT}/buildroot/configs/${DEFCONFIG}" "${BUILDROOT_DIR}/configs/${DEFCONFIG}"

make -C "${BUILDROOT_DIR}" BR2_EXTERNAL="${IA_LINUX_ROOT}/buildroot" "${DEFCONFIG}"

echo "configure.sh: configurado para alvo '${TARGET}' (${DEFCONFIG})"
