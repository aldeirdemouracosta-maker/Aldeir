#!/usr/bin/env bash
# Roda o MagicSlides a partir do código-fonte no Linux/macOS (abre no navegador).
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
fi
exec .venv/bin/python MagicSlides.py --browser "$@"
