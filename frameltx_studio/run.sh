#!/usr/bin/env bash
# Inicia a interface. Argumentos extras são repassados (ex.: ./run.sh --demo).
cd "$(dirname "$0")"
exec .venv/bin/python app.py "$@"
