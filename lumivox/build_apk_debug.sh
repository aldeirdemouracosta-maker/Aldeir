#!/usr/bin/env bash
set -euo pipefail
# Release assinado só com a chave no ambiente (LUMIVOX_KEYSTORE_PATH/_PASSWORD/_KEY_ALIAS/_KEY_PASSWORD); ela não está no Git.
if [ -n "${LUMIVOX_KEYSTORE_PATH:-}" ]; then
  gradle :app:assembleDebug :app:assembleRelease --stacktrace
else
  echo "LUMIVOX_KEYSTORE_PATH ausente: gerando apenas o APK debug."
  gradle :app:assembleDebug --stacktrace
fi
mkdir -p dist
cp app/build/outputs/apk/debug/*.apk dist/Lumivox-Android-debug.apk
if [ -n "${LUMIVOX_KEYSTORE_PATH:-}" ]; then
  cp app/build/outputs/apk/release/*.apk dist/Lumivox-Android-release-assinado.apk
fi
echo "APKs gerados em ./dist"
