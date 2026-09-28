#!/usr/bin/env bash
# Instala a IA local do IA Stop-Motion Studio OS em ~/IA-StopMotion/ferramentas:
#   ia-python/      Python isolado com ONNX Runtime, NumPy e Pillow
#   ia-sms-ia.py    ferramenta chamada pelo app
#   ia-modelos/     isnet-general-use.onnx (fundo, ~170 MB), u2netp.onnx (fundo, leve)
#                   lama_fp32.onnx (preenchimento LaMa, ~200 MB)
# Requer: python3-venv (sudo apt install python3-venv).
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${IA_SMS_HOME:-$HOME/IA-StopMotion}/ferramentas"
MODELS="$BASE/ia-modelos"
mkdir -p "$BASE" "$MODELS"

if [ ! -x "$BASE/ia-python/bin/python" ]; then
    echo "Criando ambiente Python…"
    python3 -m venv "$BASE/ia-python"
fi
"$BASE/ia-python/bin/pip" install --quiet --upgrade onnxruntime numpy pillow
install -m755 "$HERE/system/ia-sms-ia.py" "$BASE/ia-sms-ia.py"

fetch() { # fetch <url> <arquivo> — pula se já existe
    if [ -s "$MODELS/$2" ]; then echo "✓ $2"; return 0; fi
    echo "Baixando $2…"
    if curl -fL --retry 3 -o "$MODELS/$2.part" "$1"; then
        mv "$MODELS/$2.part" "$MODELS/$2"
    else
        rm -f "$MODELS/$2.part"
        echo "  aviso: não foi possível baixar $2" >&2
        return 1
    fi
}
REMBG="https://github.com/danielgatis/rembg/releases/download/v0.0.0"
fetch "$REMBG/u2netp.onnx" u2netp.onnx
fetch "$REMBG/isnet-general-use.onnx" isnet-general-use.onnx || true
fetch "https://huggingface.co/Carve/LaMa-ONNX/resolve/main/lama_fp32.onnx" lama_fp32.onnx \
    || echo "  O preenchimento por IA fica indisponível; os outros modos de limpeza continuam funcionando."

"$BASE/ia-python/bin/python" -c "import onnxruntime as o; print('ONNX Runtime', o.__version__)"
echo "IA local instalada em $BASE"
