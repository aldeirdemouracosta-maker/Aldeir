#!/bin/sh
# post-build do IA-Linux MiniVideo: remove o que não é vídeo/IA e confere a imagem.
set -eu
TARGET_DIR="$1"

# O ISO é dedicado a vídeo: nenhum serviço da base IA Linux Minimal (ai-core,
# ia-shell) deve estar presente — o defconfig não seleciona esses pacotes.
for f in usr/bin/ai-core usr/bin/ia-shell; do
    if [ -e "${TARGET_DIR}/${f}" ]; then
        echo "post-build: ${f} não deveria estar no ISO de vídeo" >&2
        exit 1
    fi
done

for f in usr/bin/minivideo-ui usr/bin/minivideo-modelos usr/bin/llama-bench usr/bin/minivideo-agentes usr/bin/minivideo-guard usr/bin/minivideo-audit \
         usr/bin/ffmpeg usr/bin/ffprobe usr/bin/mpv usr/bin/auto-editor usr/bin/rife-ncnn-vulkan usr/bin/realesrgan-ncnn-vulkan \
         usr/bin/whisper-cli usr/bin/llama-server etc/init.d/S30minivideo usr/bin/minivideo-sessao; do
    if [ ! -e "${TARGET_DIR}/${f}" ]; then
        echo "post-build: faltando ${f} no rootfs" >&2
        exit 1
    fi
done

# Modelos pequenos embutidos (RIFE v4.6, Real-ESRGAN) — o binário do Real-ESRGAN
# exige "models" no caminho.
test -f "${TARGET_DIR}/usr/share/minivideo/modelos/rife/rife-v4.6/flownet.param"
ls "${TARGET_DIR}"/usr/share/minivideo/modelos/realesrgan/models/*.param >/dev/null

mkdir -p "${TARGET_DIR}/data"
echo "post-build: rootfs do IA-Linux MiniVideo conferido"
