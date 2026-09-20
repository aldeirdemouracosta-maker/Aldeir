#!/bin/sh
# Executado pelo Buildroot depois que as imagens de sistema de arquivos
# já existem em $BINARIES_DIR. Prepara o que genimage-bios.cfg/
# genimage-uefi.cfg esperam encontrar (system.ext4 com UUID fixo, e no
# modo UEFI também o conteúdo da partição EFI) e monta o disco final via
# genimage, escolhendo o layout BIOS ou UEFI conforme o argumento
# passado por BR2_ROOTFS_POST_IMAGE_SCRIPT_ARGS.
set -eu

BOARD_DIR="$(dirname "$0")"
# Buildroot sempre chama scripts de post-image como
# "<script> <BINARIES_DIR> <BR2_ROOTFS_POST_IMAGE_SCRIPT_ARGS...>" — o
# primeiro argumento é SEMPRE o BINARIES_DIR (que também chega via a
# variável de ambiente $BINARIES_DIR, já usada no resto deste script),
# nunca o nosso "bios"/"uefi". Esse argumento configurado em
# BR2_ROOTFS_POST_IMAGE_SCRIPT_ARGS chega em $2, não em $1 — bug
# confirmado no primeiro build real fora deste sandbox (ver
# CHANGELOG.md): "$1" continha o caminho de BINARIES_DIR, não "bios".
MODE="${2:-bios}"

# Mesmo UUID fixo gravado no ext4 da SYSTEM aqui e usado em grub.cfg —
# ver o comentário em grub.cfg para o porquê de ser fixo em vez de um
# placeholder substituído em algum passo de build.
SYSTEM_FS_UUID="11111111-1111-4111-8111-111111111111"

# Tamanho do filesystem de DATA gravado aqui — precisa bater com o
# "size" da partição "data" em genimage-bios.cfg/genimage-uefi.cfg
# (senão genimage preenche a partição com padding zerado além do
# filesystem, que fica menor do que a partição). Sem passo de template
# entre os dois lugares (mesma decisão de grub.cfg/SYSTEM_FS_UUID
# acima): os dois arquivos são a fonte da verdade e precisam ser
# editados juntos. Valor atual (96G) dimensionado para um SSD "de
# 110 GB" — ver comentário nos .cfg e docs/architecture.md.
DATA_FS_SIZE="96G"

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

# genimage-*.cfg espera um arquivo chamado "system.ext4" em
# $BINARIES_DIR, mas o nome que o Buildroot realmente dá à imagem ext2/
# ext3/ext4 do rootfs (via BR2_TARGET_ROOTFS_EXT2) varia entre versões
# e não foi confirmado contra a árvore 2026.08 real neste ambiente de
# desenvolvimento (ver docs/build.md) — por isso procuramos por
# qualquer "rootfs.ext*" em vez de assumir um nome fixo.
ROOTFS_IMAGE="$(find "${BINARIES_DIR}" -maxdepth 1 -name 'rootfs.ext*' -print -quit)"
if [ -z "${ROOTFS_IMAGE}" ]; then
    echo "post-image.sh: ERRO — não encontrei rootfs.ext2/ext3/ext4 em ${BINARIES_DIR}" >&2
    echo "  (esperado de BR2_TARGET_ROOTFS_EXT2). Confira se essa opção está" >&2
    echo "  habilitada no defconfig e se o nome de saída mudou na sua árvore Buildroot." >&2
    exit 1
fi
cp "${ROOTFS_IMAGE}" "${BINARIES_DIR}/system.ext4"
"${HOST_DIR}/sbin/tune2fs" -U "${SYSTEM_FS_UUID}" "${BINARIES_DIR}/system.ext4"

# ext4 de dados vazio; será preenchido pelo usuário/instalador
mkdir -p "${BINARIES_DIR}/data-empty"
"${HOST_DIR}/sbin/mkfs.ext4" -F -L IA_DATA -d "${BINARIES_DIR}/data-empty" "${BINARIES_DIR}/data.ext4" "${DATA_FS_SIZE}"
mkdir -p "${BINARIES_DIR}/recovery-empty"
"${HOST_DIR}/sbin/mkfs.ext4" -F -L IA_RECOVERY -d "${BINARIES_DIR}/recovery-empty" "${BINARIES_DIR}/recovery.ext4" 128M

if [ "${MODE}" = "bios" ]; then
    # genimage-bios.cfg embute o código de boot do GRUB (1º estágio,
    # boot.img, gravado no setor 0/MBR) diretamente no disk.img, fora da
    # tabela de partição. Sem isso, disk.img tem partições válidas mas
    # nenhum código executável no MBR — o BIOS não acha nada pra rodar
    # e cai pro próximo dispositivo de boot (confirmado num boot físico
    # de verdade: caía pra PXE/rede, ver CHANGELOG.md). Padrão idêntico
    # ao post-build.sh de referência do Buildroot (board/pc/), que copia
    # o mesmo arquivo do mesmo caminho.
    BOOT_IMG="${TARGET_DIR}/lib/grub/i386-pc/boot.img"
    if [ ! -f "${BOOT_IMG}" ]; then
        echo "post-image.sh: ERRO — não encontrei ${BOOT_IMG}" >&2
        echo "  (boot.img de 1º estágio do GRUB — sem ele, disk.img não tem" >&2
        echo "  código de boot no MBR e não bota fisicamente). Confira se" >&2
        echo "  BR2_TARGET_GRUB2_I386_PC está habilitado no defconfig." >&2
        exit 1
    fi
    cp -f "${BOOT_IMG}" "${BINARIES_DIR}/boot.img"
fi

if [ "${MODE}" = "uefi" ]; then
    # genimage-uefi.cfg monta efi.vfat a partir de $BINARIES_DIR/EFI —
    # ninguém cria esse diretório automaticamente, então montamos aqui:
    # localizamos o binário EFI do GRUB (produzido por
    # BR2_TARGET_GRUB2_X86_64_EFI + BR2_TARGET_GRUB2_BUILTIN_CONFIG, em
    # um caminho que também não foi confirmado contra a árvore real) e
    # o colocamos no caminho de fallback padrão da especificação UEFI
    # (EFI/BOOT/BOOTX64.EFI), que qualquer firmware reconhece ao dar
    # boot de um pendrive sem precisar de entrada prévia na NVRAM.
    EFI_BIN="$(find "${BINARIES_DIR}" -iname 'bootx64.efi' -print -quit)"
    if [ -z "${EFI_BIN}" ]; then
        echo "post-image.sh: ERRO — não encontrei o binário EFI do GRUB (bootx64.efi) em ${BINARIES_DIR}" >&2
        echo "  (esperado de BR2_TARGET_GRUB2_X86_64_EFI + BR2_TARGET_GRUB2_BUILTIN_CONFIG)." >&2
        echo "  Esse caminho não foi confirmado contra a árvore Buildroot 2026.08 real" >&2
        echo "  neste ambiente de desenvolvimento — ver docs/build.md." >&2
        exit 1
    fi
    rm -rf "${BINARIES_DIR}/EFI"
    mkdir -p "${BINARIES_DIR}/EFI/BOOT"
    cp "${EFI_BIN}" "${BINARIES_DIR}/EFI/BOOT/BOOTX64.EFI"
fi

genimage \
    --rootpath "${TARGET_DIR}" \
    --inputpath "${BINARIES_DIR}" \
    --outputpath "${BINARIES_DIR}" \
    --config "${GENIMAGE_CFG}"

echo "post-image.sh: disk.img gerado em ${BINARIES_DIR}/disk.img (modo ${MODE})"
