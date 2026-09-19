#!/bin/sh
# Executado pelo Buildroot após montar o rootfs, antes de gerar a imagem.
# Cria diretórios de dados persistentes e ajusta o prompt/release.
set -eu

TARGET_DIR="$1"
IA_LINUX_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# ia-hwdetect é instalado a partir de hardware/detect.sh (fonte canônica,
# fora do overlay para não duplicar conteúdo — ver hardware/*/README.md).
install -m 0755 "${IA_LINUX_ROOT}/hardware/detect.sh" "${TARGET_DIR}/usr/bin/ia-hwdetect"

mkdir -p "${TARGET_DIR}/data/models"
mkdir -p "${TARGET_DIR}/data/rag"
mkdir -p "${TARGET_DIR}/data/agents"
mkdir -p "${TARGET_DIR}/data/workspace"
mkdir -p "${TARGET_DIR}/data/sessions"
mkdir -p "${TARGET_DIR}/data/logs"
mkdir -p "${TARGET_DIR}/data/config"

# /data é montado em runtime pela unidade de init (ver rootfs-overlay/etc/inittab)
# a partir da partição DATA; os diretórios acima existem também dentro da
# imagem SYSTEM para que o sistema funcione mesmo sem DATA montada (modo
# recovery), evitando que ia-core falhe por diretório ausente.

if [ ! -e "${TARGET_DIR}/etc/ia-linux-release" ]; then
    echo "erro: rootfs-overlay/etc/ia-linux-release não foi copiado" >&2
    exit 1
fi

exit 0
