#!/bin/sh
# build-iso.sh [--so-configurar] [--variante padrao|ivybridge] — gera o ISO do IA-Linux MiniVideo.
#
# Variantes de CPU:
#   padrao    corei7-avx (Sandy Bridge): roda no Xeon E5 v1 e v2 e em qualquer x86-64 mais nova
#   ivybridge Xeon E5 v2 ou mais nova: liga F16C (conversões fp16 do ggml), RDRND e FSGSBASE,
#             mas fica sem OpenBLAS (o Buildroot não o oferece para ivybridge).
#             NÃO roda no E5 v1 (Sandy Bridge). Qual é mais rápida: medir com llama-bench.
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
SO_CONFIGURAR=0
VARIANTE="${MINIVIDEO_VARIANTE:-padrao}"
while [ $# -gt 0 ]; do
    case "$1" in
        --so-configurar) SO_CONFIGURAR=1 ;;
        --variante) shift; VARIANTE="${1:?--variante precisa de um valor}" ;;
        *) echo "build-iso: opção desconhecida: $1" >&2; exit 2 ;;
    esac
    shift
done
case "$VARIANTE" in padrao|ivybridge) ;; *) echo "build-iso: variante inválida: $VARIANTE" >&2; exit 2 ;; esac

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

if [ "$VARIANTE" = padrao ]; then
    OUT="${WORK}/output"
    SUFIXO=""
    DEF="${IMG}/configs/${DEFCONFIG}"
else
    # mesma configuração, só muda a variante de CPU (um defconfig gerado, sem cópia manual)
    OUT="${WORK}/output-${VARIANTE}"
    SUFIXO="-${VARIANTE}"
    mkdir -p "$OUT"
    DEF="${OUT}/${VARIANTE}_defconfig"
    # O Buildroot não oferece OpenBLAS para ivybridge: essa variante troca OpenBLAS por F16C
    sed -e "s/^BR2_x86_corei7_avx=y$/BR2_x86_${VARIANTE}=y/" -e "/^BR2_PACKAGE_OPENBLAS=y$/d" \
        "${IMG}/configs/${DEFCONFIG}" > "$DEF"
    grep -q "^BR2_x86_${VARIANTE}=y$" "$DEF"
fi
make -C "$BR" O="$OUT" BR2_EXTERNAL="${BASE}:${IMG}" BR2_DEFCONFIG="$DEF" defconfig
"${IMG}/scripts/validar-config.sh" "${OUT}/.config" "$DEF"

if [ "$SO_CONFIGURAR" = 1 ]; then
    echo "build-iso: configurado em ${OUT} (sem compilar)"
    exit 0
fi

make -C "$BR" O="$OUT"
ISO="${OUT}/images/rootfs.iso9660"
test -f "$ISO"
NOME="ia-linux-minivideo${SUFIXO}.iso"
cp "$ISO" "${WORK}/${NOME}"
( cd "$WORK" && sha256sum "$NOME" > "${NOME}.sha256" )
echo "build-iso: pronto — ${WORK}/${NOME}"
echo "  Teste antes em VM:  scripts/testar-qemu.sh"
