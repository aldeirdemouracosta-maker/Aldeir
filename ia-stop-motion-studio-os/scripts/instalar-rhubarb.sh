#!/usr/bin/env bash
# Instala o Rhubarb Lip Sync (MIT) em ~/IA-StopMotion/ferramentas/rhubarb,
# onde o IA Stop-Motion Studio OS o encontra automaticamente.
set -euo pipefail

VERSION="1.14.0"
BASE="${IA_SMS_HOME:-$HOME/IA-StopMotion}/ferramentas"
URL="https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v${VERSION}/Rhubarb-Lip-Sync-${VERSION}-Linux.zip"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Baixando Rhubarb Lip Sync ${VERSION}…"
curl -fL --retry 3 -o "$TMP/rhubarb.zip" "$URL"
python3 -c "import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$TMP/rhubarb.zip" "$TMP"

mkdir -p "$BASE"
rm -rf "$BASE/rhubarb"
mv "$TMP/Rhubarb-Lip-Sync-${VERSION}-Linux" "$BASE/rhubarb"
chmod +x "$BASE/rhubarb/rhubarb"
"$BASE/rhubarb/rhubarb" --version
echo "Instalado em $BASE/rhubarb"
