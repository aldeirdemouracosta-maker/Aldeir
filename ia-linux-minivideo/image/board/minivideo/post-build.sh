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
         usr/bin/whisper-cli usr/bin/llama-server etc/init.d/S30minivideo usr/bin/minivideo-sessao \
         usr/bin/minivideo-prompts usr/bin/minivideo-atualizar usr/bin/minivideo-diagnostico \
         usr/bin/minivideo-preparar-disco usr/bin/minivideo-wifi usr/sbin/wpa_supplicant usr/sbin/iw usr/bin/openssl \
         usr/bin/Xorg usr/bin/xinit usr/bin/fluxbox usr/bin/startfluxbox usr/bin/pcmanfm usr/bin/xterm \
         usr/libexec/minivideo/sessao-grafica etc/minivideo/fluxbox/startup etc/minivideo/fluxbox/overlay; do
    if [ ! -e "${TARGET_DIR}/${f}" ]; then
        echo "post-build: faltando ${f} no rootfs" >&2
        exit 1
    fi
done
# O Fluxbox termina o rótulo no primeiro ")": "(Arquivos (PCManFM))" aparece cortado
if grep -nE '^[[:space:]]*\[[a-z]+\][[:space:]]*\([^)]*\(' "${TARGET_DIR}/etc/minivideo/fluxbox/menu" >&2; then
    echo "post-build: rótulo do menu do Fluxbox com parênteses dentro (acima)" >&2
    exit 1
fi

# Modelos pequenos embutidos (RIFE v4.6, Real-ESRGAN) — o binário do Real-ESRGAN
# exige "models" no caminho.
test -f "${TARGET_DIR}/usr/share/minivideo/modelos/rife/rife-v4.6/flownet.param"
ls "${TARGET_DIR}"/usr/share/minivideo/modelos/realesrgan/models/*.param >/dev/null

mkdir -p "${TARGET_DIR}/data"

# Variante de CPU no arquivo de versão: a tecla U escolhe o ISO novo da mesma variante
ARCH=$(sed -n 's/^BR2_GCC_TARGET_ARCH="\(.*\)"/\1/p' "${BR2_CONFIG}")
sed -i '/^CPU=/d' "${TARGET_DIR}/etc/minivideo-release"
echo "CPU=\"${ARCH}\"" >> "${TARGET_DIR}/etc/minivideo-release"
echo "post-build: rootfs do IA-Linux MiniVideo conferido"
