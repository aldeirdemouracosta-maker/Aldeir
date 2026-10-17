#!/usr/bin/env bash
# Roda dentro do emulador Android (reactivecircus/android-emulator-runner).
set -uo pipefail
PKG=br.com.aee.lumivox.debug
APK=Lumivox/app/build/outputs/apk/debug/app-debug.apk
OUT=emulator-out
mkdir -p "$OUT"

adb install -r "$APK" || { echo "FALHA: não instalou o APK"; exit 1; }
adb logcat -c
adb shell am start -n "$PKG/br.com.aee.lumivox.MainActivity"
sleep 15

PID=$(adb shell pidof "$PKG" | tr -d '\r')
echo "pid do app: ${PID:-<não está rodando>}"
if [ -z "$PID" ]; then
  adb logcat -d > "$OUT/logcat.txt"; tail -80 "$OUT/logcat.txt"; echo "FALHA: o app não ficou rodando"; exit 1
fi

adb exec-out screencap -p > "$OUT/tela-inicial.png"
SOCKET=$(adb shell cat /proc/net/unix | tr -d '\r' | grep -o "webview_devtools_remote_${PID}" | head -1)
echo "socket do DevTools: ${SOCKET:-<nenhum>}"
adb forward tcp:9222 "localabstract:${SOCKET}"

pip install --quiet websocket-client
python3 Lumivox/ci/emulator_test.py 9222 2>&1 | tee "$OUT/resultado.txt"
STATUS=${PIPESTATUS[0]}

adb exec-out screencap -p > "$OUT/tela-final.png"
adb logcat -d > "$OUT/logcat.txt"
if grep -q "FATAL EXCEPTION" "$OUT/logcat.txt"; then
  echo "FALHA: o app travou (FATAL EXCEPTION no logcat)"; grep -A12 "FATAL EXCEPTION" "$OUT/logcat.txt" | head -40; STATUS=1
fi
echo "--- erros do app no logcat (resumo) ---"
grep -E "chromium.*(ERROR|Uncaught)|lumivox" "$OUT/logcat.txt" | head -20 || true
exit $STATUS
