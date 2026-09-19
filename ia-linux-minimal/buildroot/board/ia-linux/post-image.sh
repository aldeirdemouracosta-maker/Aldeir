#!/bin/sh
# Executado pelo Buildroot depois que as imagens de sistema de arquivos
# (system.ext4 etc.) já existem em $BINARIES_DIR. Monta o disco final via
# genimage, escolhendo o layout BIOS ou UEFI conforme o argumento passado
# por BR2_ROOTFS_POST_IMAGE_SCRIPT_ARGS.
set -eu

BOARD_DIR="$(dirname "$0")"
MODE="${1:-bios}"

case "${MODE}" in
    bios) GENIMAGE_CFG="${BOARD_DIR}/genimage-bios.cfg" ;;
    uefi) GENIMAGE_CFG="${BOARD_DIR}/genimage-uefi.cfg" ;;
    *)
        echo "post-image.sh: modo desconhecido '${MODE}' (use bios|uefi)" >&2
        exit 1
        ;;
esac

if ! command -v genimage >/dev/null 2>&1; then
    echo "post-image.sh: 'genimage' não encontrado no host; pulando geração de disk.img" >&2
    echo "post-image.sh: instale genimage (https://github.com/pengutronix/genimage) e rode:" >&2
    echo "  genimage --rootpath \"\${TARGET_DIR}\" --inputpath \"\${BINARIES_DIR}\" --outputpath \"\${BINARIES_DIR}\" --config \"${GENIMAGE_CFG}\"" >&2
    exit 0
fi

# ext4 de dados vazio; será preenchido pelo usuário/instalador
mkdir -p "${BINARIES_DIR}/data-empty"
"${HOST_DIR}/sbin/mkfs.ext4" -L IA_DATA -d "${BINARIES_DIR}/data-empty" "${BINARIES_DIR}/data.ext4" 512M
mkdir -p "${BINARIES_DIR}/recovery-empty"
"${HOST_DIR}/sbin/mkfs.ext4" -L IA_RECOVERY -d "${BINARIES_DIR}/recovery-empty" "${BINARIES_DIR}/recovery.ext4" 128M

genimage \
    --rootpath "${TARGET_DIR}" \
    --inputpath "${BINARIES_DIR}" \
    --outputpath "${BINARIES_DIR}" \
    --config "${GENIMAGE_CFG}"

echo "post-image.sh: disk.img gerado em ${BINARIES_DIR}/disk.img (modo ${MODE})"
