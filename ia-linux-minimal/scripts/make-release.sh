#!/bin/sh
# make-release.sh [versao] — roda os gates de qualidade (os mesmos
# rodados manualmente em cada etapa 0.x deste projeto: cargo
# test/clippy/fmt, shellcheck) e monta os artefatos de uma release:
# checksums das imagens e o relatório de conformidade de licenças
# (`make legal-info` do Buildroot, ver docs/licenses.md).
#
# Sem argumento, a versão é lida de ai-core/Cargo.toml. A compilação de
# imagens em si (scripts/compile.sh) é um pré-requisito, não algo que
# este script refaz — ele empacota o que já foi compilado.
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IA_LINUX_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILDROOT_VERSION="${BUILDROOT_VERSION:-2026.08}"
BUILDROOT_DIR="${IA_LINUX_ROOT}/.build/buildroot-${BUILDROOT_VERSION}"
RELEASE_DIR="${IA_LINUX_ROOT}/.release"

VERSION="${1:-}"
if [ -z "${VERSION}" ]; then
    VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "${IA_LINUX_ROOT}/ai-core/Cargo.toml" | head -n1)"
fi

echo "make-release.sh: preparando release ${VERSION}"
echo

echo "== gate 1/4: cargo test =="
(cd "${IA_LINUX_ROOT}/ai-core" && cargo test)
echo

echo "== gate 2/4: cargo clippy -- -D warnings =="
(cd "${IA_LINUX_ROOT}/ai-core" && cargo clippy -- -D warnings)
echo

echo "== gate 3/4: cargo fmt --check =="
(cd "${IA_LINUX_ROOT}/ai-core" && cargo fmt --check)
echo

echo "== gate 4/4: shellcheck em todos os scripts do projeto =="
if command -v shellcheck >/dev/null 2>&1; then
    cd "${IA_LINUX_ROOT}"
    # Mesma lista de caminhos usada manualmente na validação de cada
    # etapa deste projeto (build.sh, scripts/, board files, overlay).
    shellcheck -x -s sh -S warning \
        build.sh scripts/*.sh \
        buildroot/board/ia-linux/post-build.sh buildroot/board/ia-linux/post-image.sh \
        hardware/detect.sh \
        rootfs-overlay/etc/init.d/* \
        rootfs-overlay/usr/bin/* \
        rootfs-overlay/usr/lib/ia-linux/common.sh
    cd "${SCRIPT_DIR}"
else
    echo "make-release.sh: shellcheck não encontrado — pulando gate 4 (rode-o manualmente antes de publicar)" >&2
fi
echo

echo "== todos os gates de qualidade passaram =="
echo

mkdir -p "${RELEASE_DIR}"

if [ -d "${BUILDROOT_DIR}" ]; then
    echo "== legal-info: relatório de conformidade de licenças =="
    make -C "${BUILDROOT_DIR}" BR2_EXTERNAL="${IA_LINUX_ROOT}" legal-info
    if [ -d "${BUILDROOT_DIR}/output/legal-info" ]; then
        rm -rf "${RELEASE_DIR}/legal-info"
        cp -r "${BUILDROOT_DIR}/output/legal-info" "${RELEASE_DIR}/legal-info"
    fi
    echo

    IMAGES_DIR="${BUILDROOT_DIR}/output/images"
    if [ -d "${IMAGES_DIR}" ] && [ -n "$(ls -A "${IMAGES_DIR}" 2>/dev/null)" ]; then
        echo "== copiando imagens e gerando checksums =="
        mkdir -p "${RELEASE_DIR}/images"
        find "${IMAGES_DIR}" -maxdepth 1 -type f -exec cp {} "${RELEASE_DIR}/images/" \;
        if command -v sha256sum >/dev/null 2>&1; then
            (cd "${RELEASE_DIR}/images" && sha256sum -- * >SHA256SUMS)
            echo "checksums em ${RELEASE_DIR}/images/SHA256SUMS"
        else
            echo "make-release.sh: sha256sum não encontrado — imagens copiadas sem checksums" >&2
        fi
    else
        echo "make-release.sh: aviso — nenhuma imagem em ${IMAGES_DIR}; rode scripts/compile.sh primeiro" >&2
    fi
else
    echo "make-release.sh: aviso — ${BUILDROOT_DIR} não existe; pulando legal-info e empacotamento de imagens" >&2
    echo "  (rode scripts/fetch-buildroot.sh + scripts/configure.sh + scripts/compile.sh para uma release completa)" >&2
fi

echo
echo "make-release.sh: release ${VERSION} preparada em ${RELEASE_DIR}"
