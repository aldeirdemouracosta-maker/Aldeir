#!/bin/sh
# fetch-buildroot.sh — baixa e verifica o tarball do Buildroot 2026.08
# (plataforma de referência da série 0.x — ver README.md). Roda no HOST,
# não dentro do IA Linux Minimal.
set -eu

BUILDROOT_VERSION="${BUILDROOT_VERSION:-2026.08}"
BUILDROOT_TARBALL="buildroot-${BUILDROOT_VERSION}.tar.gz"
BUILDROOT_URL="https://buildroot.org/downloads/${BUILDROOT_TARBALL}"
SHA256SUMS_URL="https://buildroot.org/downloads/sha256sums"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IA_LINUX_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORK_DIR="${IA_LINUX_ROOT}/.build"
mkdir -p "${WORK_DIR}"
cd "${WORK_DIR}"

if [ -d "buildroot-${BUILDROOT_VERSION}" ]; then
    echo "fetch-buildroot.sh: buildroot-${BUILDROOT_VERSION}/ já existe, pulando download"
    exit 0
fi

echo "fetch-buildroot.sh: baixando ${BUILDROOT_URL}"
curl -fLO "${BUILDROOT_URL}"

echo "fetch-buildroot.sh: verificando checksum via ${SHA256SUMS_URL}"
if curl -fsSL "${SHA256SUMS_URL}" -o sha256sums.txt; then
    if grep "${BUILDROOT_TARBALL}" sha256sums.txt | sha256sum -c -; then
        echo "fetch-buildroot.sh: checksum OK"
    else
        echo "fetch-buildroot.sh: FALHA na verificação de checksum — abortando" >&2
        rm -f "${BUILDROOT_TARBALL}"
        exit 1
    fi
else
    echo "fetch-buildroot.sh: aviso — não foi possível baixar sha256sums.txt;" >&2
    echo "  verifique manualmente a assinatura PGP do tarball antes de compilar" >&2
    echo "  (https://buildroot.org/download.html#legacy)." >&2
fi

tar xf "${BUILDROOT_TARBALL}"
echo "fetch-buildroot.sh: pronto em ${WORK_DIR}/buildroot-${BUILDROOT_VERSION}"
