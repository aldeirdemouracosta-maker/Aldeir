#!/usr/bin/env bash
# Instala a geração de cenários por IA em ~/IA-StopMotion/ferramentas/sd:
#   sd-cli    stable-diffusion.cpp compilado com Vulkan (roda na RX 580)
#   modelo    Stable Diffusion 1.5 (fp16, ~2 GB) — leve o bastante para 8 GB de VRAM
# Troque o modelo com SD_MODEL_URL=<url de um .safetensors/.gguf SD 1.5>.
# Requer: git, cmake, g++, libvulkan-dev, glslc, spirv-headers.
set -euo pipefail
BASE="${IA_SMS_HOME:-$HOME/IA-StopMotion}/ferramentas/sd"
MODEL_URL="${SD_MODEL_URL:-https://huggingface.co/Comfy-Org/stable-diffusion-v1-5-archive/resolve/main/v1-5-pruned-emaonly-fp16.safetensors}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$BASE"

if [ ! -x "$BASE/sd-cli" ]; then
    echo "Compilando stable-diffusion.cpp…"
    git clone --depth 1 https://github.com/leejet/stable-diffusion.cpp "$TMP/sd"
    git -C "$TMP/sd" submodule update --init --depth 1 ggml
    VULKAN=OFF
    if command -v glslc >/dev/null && [ -e /usr/include/vulkan/vulkan.h ] &&
       find /usr/share /usr/lib -name 'SPIRV-HeadersConfig.cmake' -print -quit 2>/dev/null | grep -q .; then
        VULKAN=ON
    else
        echo "  aviso: sem Vulkan (sudo apt install libvulkan-dev glslc spirv-headers) — vai rodar na CPU, bem mais lento"
    fi
    echo "  Vulkan: $VULKAN"
    cmake -S "$TMP/sd" -B "$TMP/sd/build" -DCMAKE_BUILD_TYPE=Release -DSD_VULKAN=$VULKAN \
        -DSD_WEBP=OFF -DSD_WEBM=OFF >/dev/null
    cmake --build "$TMP/sd/build" --target sd-cli -j"$(nproc)"
    install -m755 "$TMP/sd/build/bin/sd-cli" "$BASE/sd-cli"
fi

MODEL="$BASE/$(basename "${MODEL_URL%%\?*}")"
if [ ! -s "$MODEL" ]; then
    echo "Baixando o modelo ($(basename "$MODEL"))…"
    if curl -fL --retry 3 -o "$MODEL.part" "$MODEL_URL"; then
        mv "$MODEL.part" "$MODEL"
    else
        rm -f "$MODEL.part"
        echo "  aviso: modelo não baixado — coloque um modelo SD 1.5 (.safetensors/.gguf) em $BASE" >&2
    fi
fi
echo "Cenários por IA instalados em $BASE"
