#!/usr/bin/env bash
set -euo pipefail
gradle :app:assembleDebug :app:assembleRelease --stacktrace
mkdir -p dist
cp app/build/outputs/apk/debug/*.apk dist/Lumivox-Android-debug.apk
cp app/build/outputs/apk/release/*.apk dist/Lumivox-Android-release-assinado.apk
echo "APKs gerados em ./dist"
