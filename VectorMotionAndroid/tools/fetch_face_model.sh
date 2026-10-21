#!/bin/sh
# Baixa o modelo MediaPipe Face Landmarker para os assets do app (usado só no build com -PfaceSwap=true).
set -eu
DEST="$(dirname "$0")/../app/src/main/assets/face_landmarker.task"
URL="https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
mkdir -p "$(dirname "$DEST")"
curl -fL --retry 3 -o "$DEST" "$URL"
test "$(wc -c < "$DEST")" -gt 1000000 || { echo "download incompleto" >&2; exit 1; }
echo "ok: $DEST"
