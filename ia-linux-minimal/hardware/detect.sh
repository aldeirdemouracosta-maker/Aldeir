#!/bin/sh
# hardware/detect.sh — sonda de hardware independente do ai-core.
#
# Instalada como /usr/bin/ia-hwdetect (ver buildroot/board/ia-linux/post-build.sh).
# Existe para o modo RECOVERY (ai-core não iniciou, ou o operador quer
# conferir hardware antes de o daemon subir) e como referência legível por
# humanos do que hardware.rs faz em Rust — ver ai-core/src/hardware.rs.
set -e

echo "=== IA Linux Minimal — detecção de hardware (modo standalone) ==="
echo

echo "-- CPU --"
if [ -r /proc/cpuinfo ]; then
    model="$(sed -n 's/^model name[[:space:]]*:[[:space:]]*//p' /proc/cpuinfo | head -n1)"
    threads="$(grep -c '^processor' /proc/cpuinfo)"
    echo "Modelo   : ${model:-desconhecido}"
    echo "Threads  : ${threads:-0}"
else
    echo "/proc/cpuinfo indisponível"
fi
echo

echo "-- RAM --"
if [ -r /proc/meminfo ]; then
    total_kb="$(sed -n 's/^MemTotal:[[:space:]]*\([0-9]*\).*/\1/p' /proc/meminfo)"
    if [ -n "${total_kb}" ]; then
        awk -v kb="${total_kb}" 'BEGIN { printf "Total    : %.1f GiB\n", kb/1024/1024 }'
    fi
else
    echo "/proc/meminfo indisponível"
fi
echo

echo "-- GPU --"
found_gpu=0
if [ -d /sys/class/drm ]; then
    for card in /sys/class/drm/card*; do
        [ -e "${card}/device/vendor" ] || continue
        vendor="$(cat "${card}/device/vendor" 2>/dev/null)"
        case "${vendor}" in
            0x1002)
                echo "AMD (vendor ${vendor}) em ${card} — driver esperado: amdgpu"
                found_gpu=1
                ;;
            0x10de)
                echo "NVIDIA (vendor ${vendor}) em ${card} — sem suporte nesta versão (ver hardware/nvidia/README.md)"
                found_gpu=1
                ;;
            0x8086)
                echo "Intel (vendor ${vendor}) em ${card} — sem backend Vulkan dedicado nesta versão (ver hardware/intel/README.md)"
                found_gpu=1
                ;;
        esac
    done
fi
[ "${found_gpu}" -eq 0 ] && echo "nenhuma GPU compatível detectada — backend será CPU"
echo

echo "-- Armazenamento --"
if command -v lsblk >/dev/null 2>&1; then
    lsblk -o NAME,SIZE,TYPE,MOUNTPOINT 2>/dev/null || true
else
    echo "lsblk indisponível"
fi
