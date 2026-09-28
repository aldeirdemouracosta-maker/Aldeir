#!/usr/bin/env bash
# Instala legendas automáticas (whisper.cpp) e narração (Piper) em
# ~/IA-StopMotion/ferramentas:
#   whisper/whisper-cli + ggml-small.bin   (compilado com Vulkan quando possível → RX 580)
#   piper/piper + vozes/pt_BR-faber-medium.onnx
# Requer: git, cmake, g++; para Vulkan: sudo apt install libvulkan-dev glslc spirv-headers
set -euo pipefail
BASE="${IA_SMS_HOME:-$HOME/IA-StopMotion}/ferramentas"
WHISPER_MODEL="${WHISPER_MODEL:-small}"   # tiny | base | small | medium
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$BASE/whisper" "$BASE/piper/vozes"

fetch() { # fetch <url> <destino>
    [ -s "$2" ] && { echo "✓ $(basename "$2")"; return 0; }
    echo "Baixando $(basename "$2")…"
    curl -fL --retry 3 -o "$2.part" "$1" && mv "$2.part" "$2"
}

# ── whisper.cpp ────────────────────────────────────────────────────────
if [ ! -x "$BASE/whisper/whisper-cli" ]; then
    echo "Compilando whisper.cpp…"
    git clone --depth 1 https://github.com/ggml-org/whisper.cpp "$TMP/whisper.cpp"
    VULKAN=OFF
    if command -v glslc >/dev/null && [ -e /usr/include/vulkan/vulkan.h ] &&
       find /usr/share /usr/lib -name 'SPIRV-HeadersConfig.cmake' -print -quit 2>/dev/null | grep -q .; then
        VULKAN=ON
    else
        echo "  (para usar a GPU: sudo apt install libvulkan-dev glslc spirv-headers)"
    fi
    echo "  Vulkan: $VULKAN"
    cmake -S "$TMP/whisper.cpp" -B "$TMP/whisper.cpp/build" -DCMAKE_BUILD_TYPE=Release \
        -DBUILD_SHARED_LIBS=OFF -DGGML_VULKAN=$VULKAN -DWHISPER_BUILD_TESTS=OFF >/dev/null
    cmake --build "$TMP/whisper.cpp/build" --target whisper-cli -j"$(nproc)"
    install -m755 "$TMP/whisper.cpp/build/bin/whisper-cli" "$BASE/whisper/whisper-cli"
fi
fetch "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-${WHISPER_MODEL}.bin" \
      "$BASE/whisper/ggml-${WHISPER_MODEL}.bin" \
    || { rm -f "$BASE/whisper/ggml-${WHISPER_MODEL}.bin.part"; echo "  aviso: modelo do whisper não baixado — legendas indisponíveis" >&2; }

# ── Piper ──────────────────────────────────────────────────────────────
if [ ! -x "$BASE/piper/piper" ]; then
    fetch "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz" "$TMP/piper.tar.gz"
    tar -xzf "$TMP/piper.tar.gz" -C "$TMP"
    cp -a "$TMP/piper/." "$BASE/piper/"
fi
VOICE="https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx"
if ! { fetch "$VOICE" "$BASE/piper/vozes/pt_BR-faber-medium.onnx" &&
       fetch "$VOICE.json" "$BASE/piper/vozes/pt_BR-faber-medium.onnx.json"; }; then
    rm -f "$BASE/piper/vozes/"*.part "$BASE/piper/vozes/pt_BR-faber-medium.onnx"
    echo "  aviso: voz do Piper não baixada — narração indisponível" >&2
fi

echo "Voz instalada em $BASE"
