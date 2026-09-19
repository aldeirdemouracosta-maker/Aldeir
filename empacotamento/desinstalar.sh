#!/usr/bin/env bash
# Remove o que instalar.sh instalou. Roda como root — sudo ./desinstalar.sh.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Rode como root: sudo ./desinstalar.sh" >&2
  exit 1
fi

rm -f /usr/local/bin/fabrica-local-ia
rm -f /usr/share/icons/hicolor/scalable/apps/fabrica-local-ia.svg
rm -f /usr/share/applications/fabrica-local-ia.desktop

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database /usr/share/applications || true

echo "Desinstalado."
