#!/usr/bin/env bash
# Instala os modos de desempenho do IA Stop-Motion Studio OS (requer sudo):
#   /usr/local/lib/ia-stop-motion/ia-sms-modo      helper que ajusta CPU/GPU/sched_ext
#   /usr/share/polkit-1/actions/org.iasms.modo.policy  permite trocar o modo sem senha
# DESTDIR=<dir> instala numa raiz alternativa (empacotamento/testes).
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="${DESTDIR:-}"

if [ -z "$ROOT" ] && [ "$(id -u)" -ne 0 ]; then
    exec sudo "$0" "$@"
fi

install -Dm755 "$HERE/system/ia-sms-modo" "$ROOT/usr/local/lib/ia-stop-motion/ia-sms-modo"
install -Dm644 "$HERE/system/org.iasms.modo.policy" "$ROOT/usr/share/polkit-1/actions/org.iasms.modo.policy"
echo "Modos instalados."

if [ -z "$ROOT" ]; then
    if [ -d /sys/kernel/sched_ext ]; then
        if command -v scxctl >/dev/null; then
            echo "sched_ext: ativo com scx_loader — o modo também troca o escalonador de CPU."
        else
            echo "sched_ext disponível no kernel. Para trocar o escalonador por modo, instale os"
            echo "escalonadores scx e o scx_loader (https://github.com/sched-ext/scx)."
        fi
    else
        echo "Kernel $(uname -r) sem sched_ext (precisa ≥ 6.12 com CONFIG_SCHED_CLASS_EXT)."
        echo "Os modos continuam ajustando RX 580, governor da CPU e prioridades."
    fi
fi
