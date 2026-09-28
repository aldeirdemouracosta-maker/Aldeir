#!/usr/bin/env bash
# Instala o Real-ESRGAN ncnn-vulkan (BSD-3) em ~/IA-StopMotion/ferramentas/realesrgan,
# onde o IA Stop-Motion Studio OS o encontra automaticamente. Roda na GPU via
# Vulkan (RADV na RX 580); requer mesa-vulkan-drivers.
set -euo pipefail

URL="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-ubuntu.zip"
BASE="${IA_SMS_HOME:-$HOME/IA-StopMotion}/ferramentas"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Baixando Real-ESRGAN ncnn-vulkan…"
curl -fL --retry 3 -o "$TMP/realesrgan.zip" "$URL"
mkdir -p "$TMP/realesrgan"
python3 -c "import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$TMP/realesrgan.zip" "$TMP/realesrgan"
rm -f "$TMP/realesrgan/"*.jpg "$TMP/realesrgan/"*.mp4

mkdir -p "$BASE"
rm -rf "$BASE/realesrgan"
mv "$TMP/realesrgan" "$BASE/realesrgan"
chmod +x "$BASE/realesrgan/realesrgan-ncnn-vulkan"
echo "Instalado em $BASE/realesrgan"
command -v vulkaninfo >/dev/null && vulkaninfo --summary 2>/dev/null | grep -E "deviceName" || true
