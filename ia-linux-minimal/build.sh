#!/bin/sh
# build.sh [qemu|bios|uefi] — atalho para o fluxo completo:
# fetch-buildroot -> configure -> compile. Alvo padrão: qemu.
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="${1:-qemu}"

"${SCRIPT_DIR}/scripts/fetch-buildroot.sh"
"${SCRIPT_DIR}/scripts/configure.sh" "${TARGET}"
"${SCRIPT_DIR}/scripts/compile.sh"

echo "build.sh: concluído para o alvo '${TARGET}'."
if [ "${TARGET}" = "qemu" ]; then
    echo "Rode: scripts/run-qemu.sh"
fi
