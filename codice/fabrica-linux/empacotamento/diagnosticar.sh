#!/bin/sh
set -eu
REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$REPO"
PYTHON=python3
if [ -x "$REPO/.venv/bin/python" ]; then PYTHON="$REPO/.venv/bin/python"; fi
exec "$PYTHON" -B -m empacotamento.usuario diagnosticar "$@"
