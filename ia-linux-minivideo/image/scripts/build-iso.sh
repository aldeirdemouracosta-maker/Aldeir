#!/bin/sh
# build-iso.sh [--so-configurar] — gera o ISO do IA-Linux MiniVideo.
#
# Camadas (BR2_EXTERNAL):
#   1. IA Linux Minimal, fixado no commit IA_LINUX_MINIMAL_REF (kernel 6.18.52)
#   2. esta pasta (image/): vídeo, agentes e interface de pastas
# Resultado: $MINIVIDEO_WORK/output/images/rootfs.iso9660 (ISO híbrido BIOS + UEFI).
set -eu

IMG="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "${IMG}/../.." && pwd)"
# Fora da árvore de código: o pacote minivideo-tools copia ia-linux-minivideo/.
WORK="${MINIVIDEO_WORK:-${HOME}/minivideo-build}"
BR_VERSION="${BUILDROOT_VERSION:-2026.08}"
BR_URL="${BUILDROOT_GIT:-https://github.com/buildroot/buildroot}"
BASE_REF="${IA_LINUX_MINIMAL_REF:-cd7c7218dce738a68d16e0d225651e5116c94f79}"
DEFCONFIG=ia_minivideo_iso_x86_64_defconfig

# ---- ferramentas do host ----
missing=""
for t in git make gcc g++ unzip rsync bc cpio perl python3 file wget patch glslc; do
    command -v "$t" >/dev/null 2>&1 || missing="${missing} ${t}"
done
if [ -n "$missing" ]; then
    echo "build-iso: faltam ferramentas no host:${missing}" >&2
    echo "  Debian/Ubuntu: sudo apt install build-essential git unzip rsync bc cpio file wget glslc libelf-dev libssl-dev" >&2
    echo "  (glslc compila os shaders Vulkan do llama.cpp e do whisper.cpp)" >&2
    exit 1
fi
mkdir -p "$WORK"

# ---- camada 1: IA Linux Minimal (kernel já construído, sem alteração) ----
BASE="${IA_LINUX_MINIMAL_DIR:-${WORK}/ia-linux-minimal}"
if [ -z "${IA_LINUX_MINIMAL_DIR:-}" ] && [ ! -f "${BASE}/external.desc" ]; then
    echo "build-iso: extraindo IA Linux Minimal @ ${BASE_REF}"
    git -C "$REPO" cat-file -e "${BASE_REF}^{commit}" 2>/dev/null \
        || git -C "$REPO" fetch --depth 1 origin "$BASE_REF"
    mkdir -p "${WORK}/base-tmp"
    git -C "$REPO" archive "$BASE_REF" ia-linux-minimal | tar -x -C "${WORK}/base-tmp"
    mv "${WORK}/base-tmp/ia-linux-minimal" "$BASE"
    rmdir "${WORK}/base-tmp"
fi
test -f "${BASE}/kernel/config/ia_linux_x86_64.config"

# ---- Buildroot ----
BR="${WORK}/buildroot-${BR_VERSION}"
if [ ! -d "$BR" ]; then
    echo "build-iso: baixando Buildroot ${BR_VERSION} (${BR_URL})"
    git clone --depth 1 --branch "$BR_VERSION" "$BR_URL" "$BR"
fi

OUT="${WORK}/output"
make -C "$BR" O="$OUT" BR2_EXTERNAL="${BASE}:${IMG}" "$DEFCONFIG"
"${IMG}/scripts/validar-config.sh" "${OUT}/.config" "${IMG}/configs/${DEFCONFIG}"

if [ "${1:-}" = "--so-configurar" ]; then
    echo "build-iso: configurado em ${OUT} (sem compilar)"
    exit 0
fi

make -C "$BR" O="$OUT"
ISO="${OUT}/images/rootfs.iso9660"
test -f "$ISO"
cp "$ISO" "${WORK}/ia-linux-minivideo.iso"
( cd "$WORK" && sha256sum ia-linux-minivideo.iso > ia-linux-minivideo.iso.sha256 )
echo "build-iso: pronto — ${WORK}/ia-linux-minivideo.iso"
echo "  Teste antes em VM:  scripts/testar-qemu.sh"
