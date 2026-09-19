#!/bin/sh
# validate-buildroot-configs.sh <caminho para a árvore Buildroot> —
# confere, de forma best-effort, se os símbolos BR2_* usados em
# buildroot/configs/*_defconfig existem na árvore Buildroot informada.
#
# Não substitui 'make menuconfig' / 'make savedefconfig': é uma checagem
# rápida para pegar nomes de opção digitados errado ou renomeados/
# removidos entre versões, ANTES de gastar tempo compilando. Ambiente de
# desenvolvimento deste projeto não tem acesso a buildroot.org, então os
# defconfigs em buildroot/configs/ foram escritos a partir da convenção de
# nomes do Buildroot, mas não foram confirmados símbolo-a-símbolo contra a
# árvore 2026.08 real — rode este script no seu host antes de compilar.
set -eu

BUILDROOT_DIR="${1:?uso: $0 <caminho para a árvore Buildroot>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IA_LINUX_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [ ! -d "${BUILDROOT_DIR}/package" ]; then
    echo "validate: '${BUILDROOT_DIR}' não parece ser uma árvore Buildroot (sem package/)" >&2
    exit 1
fi

WARN_FILE="$(mktemp)"
trap 'rm -f "${WARN_FILE}"' EXIT

for defconfig in "${IA_LINUX_ROOT}"/buildroot/configs/*_defconfig; do
    echo "== $(basename "${defconfig}") =="
    grep -oE '^(# )?BR2_[A-Za-z0-9_]+' "${defconfig}" | sed 's/^# //' | sort -u > "${WARN_FILE}.symbols"
    while IFS= read -r symbol; do
        short="${symbol#BR2_}"
        if ! grep -rq "config ${short}\b" \
            "${BUILDROOT_DIR}"/package/*/Config.in \
            "${BUILDROOT_DIR}"/Config.in \
            "${BUILDROOT_DIR}"/Config.in.legacy \
            "${BUILDROOT_DIR}"/arch/Config.in \
            "${BUILDROOT_DIR}"/fs/Config.in \
            "${BUILDROOT_DIR}"/boot/*/Config.in \
            "${BUILDROOT_DIR}"/linux/Config.in.host 2>/dev/null; then
            echo "  aviso: símbolo não encontrado: ${symbol}" | tee -a "${WARN_FILE}"
        fi
    done < "${WARN_FILE}.symbols"
    rm -f "${WARN_FILE}.symbols"
done

if [ -s "${WARN_FILE}" ]; then
    echo
    echo "validate: alguns símbolos não foram encontrados nesta árvore Buildroot."
    echo "Confira com 'make menuconfig' (nomes de opção mudam entre versões) antes de compilar."
    exit 1
fi

echo "validate: todos os símbolos BR2_* usados nos defconfigs foram encontrados."
