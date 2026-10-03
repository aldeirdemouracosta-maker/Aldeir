#!/usr/bin/env bash
# Instala o FrameLTX Studio em um ambiente virtual (.venv). Linux/macOS.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
"$PY" -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ é necessário"'
"$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
[ -f config.json ] || cp config.example.json config.json
echo "✅ Instalado. Inicie o ComfyUI e depois rode ./run.sh"
