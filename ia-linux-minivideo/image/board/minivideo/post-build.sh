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
# O pacote do Xorg instala /etc/init.d/S40xorg, que sobe um "Xorg :0 vt01" vazio no boot:
# ele ocupa o display e a tela (preta), e a sessão da entrada "Interface" falhava com
# "Server is already active for display 0" (run 36102231453). Quem inicia o X é a minivideo-sessao.
rm -f "${TARGET_DIR}/etc/init.d/S40xorg"
# Drivers do Xorg precisam de ligação preguiçosa: usam símbolos de módulos carregados
# depois (fbdevhw, glamoregl). Com BIND_NOW (RELRO completo) o Xorg diz "no screens found".
for so in "${TARGET_DIR}"/usr/lib/xorg/modules/drivers/*_drv.so; do
    [ -e "$so" ] || continue
    if readelf -d "$so" | grep -qE 'BIND_NOW|FLAGS.*NOW'; then
        echo "post-build: ${so#"${TARGET_DIR}"} ligado com -z now (use BR2_RELRO_PARTIAL)" >&2
        exit 1
    fi
done
# O xterm só usa UTF-8 se o Xlib aceitar o locale: C.UTF-8 aponta para en_US.UTF-8
X11L="${TARGET_DIR}/usr/share/X11/locale"
if [ -d "$X11L" ]; then
    test -f "$X11L/en_US.UTF-8/XLC_LOCALE" && grep -q "^en_US.UTF-8/XLC_LOCALE" "$X11L/locale.dir" \
        && grep -qE "^C.UTF-8[[:space:]]+en_US.UTF-8" "$X11L/locale.alias" || {
        echo "post-build: locale X11 en_US.UTF-8 ou locale.alias ausente (BR2_ENABLE_LOCALE_WHITELIST): acentos quebram no xterm" >&2
        exit 1
    }
fi
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
