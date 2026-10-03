#!/bin/bash
# Remove o proxy de correção da Fábrica.  Uso:  sudo bash desinstalar.sh
# A Fábrica original (~/.local/bin/fabrica) não é tocada.
if [ "$(id -u)" -ne 0 ]; then
  echo "Rode com sudo:  sudo bash $0" >&2
  exit 1
fi
if [ -d /run/systemd/system ]; then
  systemctl disable --now fabrica-proxy 2>/dev/null || true
  rm -f /etc/systemd/system/fabrica-proxy.service
  systemctl daemon-reload
fi
rm -f /usr/local/bin/fabrica-segura
rm -rf /usr/local/lib/fabrica-correcoes
echo "✅ Proxy de correção removido. A Fábrica original continua instalada."
