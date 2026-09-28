#!/usr/bin/env bash
# Compila e instala o escalonador sched_ext próprio do IA Stop-Motion Studio OS:
#   /usr/local/lib/ia-stop-motion/scx_studio   + serviço systemd scx-studio
# Requer kernel com sched_ext (Linux ≥ 6.12, CONFIG_SCHED_CLASS_EXT=y) para rodar;
# compila em qualquer Ubuntu 24.04 com: sudo apt install clang libelf-dev zlib1g-dev git make
# Versões fixadas (testadas juntas):
SCX_COMMIT="76a7c4b59a0ea9ee35a49d5a4cb2483aea72d5b7"      # github.com/sched-ext/scx
BPFTOOL_COMMIT="9aec6f05f9974d2bc58707e5b3899aad892f0785"  # github.com/libbpf/bpftool (traz libbpf)
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="${DESTDIR:-}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fetch_commit() { # fetch_commit <url> <commit> <dir>
    git init -q "$3"
    git -C "$3" fetch -q --depth 1 "$1" "$2"
    git -C "$3" checkout -q FETCH_HEAD
}

echo "Baixando scx e bpftool/libbpf…"
fetch_commit https://github.com/sched-ext/scx "$SCX_COMMIT" "$TMP/scx"
fetch_commit https://github.com/libbpf/bpftool "$BPFTOOL_COMMIT" "$TMP/bpftool"
git -C "$TMP/bpftool" submodule update -q --init --depth 1 libbpf

echo "Compilando bpftool e libbpf (o Ubuntu 24.04 traz versões antigas)…"
make -s -C "$TMP/bpftool/src" -j"$(nproc)" >/dev/null
make -s -C "$TMP/bpftool/libbpf/src" -j"$(nproc)" BUILD_STATIC_ONLY=1 \
    OBJDIR="$TMP/libbpf-obj" DESTDIR="$TMP/libbpf" install >/dev/null

echo "Compilando scx_studio…"
cp -r "$HERE/system/scx_studio" "$TMP/build"
make -s -C "$TMP/build" SCX="$TMP/scx" LIBBPF="$TMP/libbpf/usr" BPFTOOL="$TMP/bpftool/src/bpftool"

if [ -z "$ROOT" ] && [ "$(id -u)" -ne 0 ]; then
    echo "Instalando (sudo)…"
    SUDO=sudo
else
    SUDO=
fi
$SUDO install -Dm755 "$TMP/build/scx_studio" "$ROOT/usr/local/lib/ia-stop-motion/scx_studio"
$SUDO install -Dm755 "$TMP/bpftool/src/bpftool" "$ROOT/usr/local/lib/ia-stop-motion/bpftool"
$SUDO install -Dm644 "$HERE/system/scx_studio/scx-studio.service" "$ROOT/etc/systemd/system/scx-studio.service"

if [ -z "$ROOT" ]; then
    if [ -d /sys/kernel/sched_ext ]; then
        $SUDO systemctl daemon-reload
        $SUDO systemctl enable --now scx-studio.service
        echo "scx_studio ativo: $(cat /sys/kernel/sched_ext/root/ops 2>/dev/null || echo '?')"
    else
        echo "Kernel $(uname -r) sem sched_ext: o serviço fica instalado e só inicia em um kernel ≥ 6.12."
    fi
fi
echo "Pronto."
