#!/bin/sh
set -eu
REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$REPO"
exec "$REPO/.venv/bin/python" -B -m interface.janela_principal "$@"
