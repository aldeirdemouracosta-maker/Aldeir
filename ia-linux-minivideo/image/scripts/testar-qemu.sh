#!/bin/sh
# testar-qemu.sh [iso] — boot do ISO em QEMU (BIOS, sem GPU real).
# Valida boot, initramfs, init, interface de pastas e ferramentas. NÃO valida
# RX 580, Vulkan RADV, VA-API nem sensores — isso só no hardware.
set -eu
IMG="$(cd "$(dirname "$0")/.." && pwd)"
ISO="${1:-${MINIVIDEO_WORK:-${HOME}/minivideo-build}/ia-linux-minivideo.iso}"
DADOS="${MINIVIDEO_WORK:-${HOME}/minivideo-build}/dados-teste.img"
if [ ! -f "$DADOS" ]; then
    truncate -s 4G "$DADOS"
    mkfs.ext4 -q -F -L MV_DADOS "$DADOS"
fi
exec qemu-system-x86_64 -m 6G -smp 4 -cpu SandyBridge \
    -cdrom "$ISO" -boot d \
    -drive file="$DADOS",format=raw,if=ide \
    -vga std -serial mon:stdio
