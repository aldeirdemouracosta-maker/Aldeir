#!/usr/bin/env bash
# Instala a interface desktop da fábrica local de IA no sistema: um
# comando (`fabrica-local-ia`), um ícone e uma entrada no menu de
# aplicativos. Roda como root — sudo ./instalar.sh.
#
# Não copia o código: o atalho instalado aponta para esta cópia do
# repositório, no lugar onde ela está agora. `git pull` + reinstalar
# não é necessário para pegar mudanças de código; só reinstale se
# mudou o próprio empacotamento (este script, o ícone, o .desktop).
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Rode como root: sudo ./instalar.sh" >&2
  exit 1
fi

DIR_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIR_REPO="$(cd "$DIR_SCRIPT/.." && pwd)"

if ! python3 -c "import PySide6" 2>/dev/null; then
  echo "Aviso: PySide6 não encontrado para este python3." >&2
  echo "Rode antes: pip install -r \"$DIR_REPO/requirements.txt\"" >&2
fi

BIN=/usr/local/bin/fabrica-local-ia
cat > "$BIN" <<EOF
#!/bin/sh
cd "$DIR_REPO" && exec python3 -m interface.janela_principal "\$@"
EOF
chmod 755 "$BIN"

ICONE_DIR=/usr/share/icons/hicolor/scalable/apps
mkdir -p "$ICONE_DIR"
cp "$DIR_SCRIPT/icone.svg" "$ICONE_DIR/fabrica-local-ia.svg"

DESKTOP=/usr/share/applications/fabrica-local-ia.desktop
cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Fábrica Local de IA
Comment=Interface desktop para desenvolvimento assistido por IA local
Exec=fabrica-local-ia
Icon=fabrica-local-ia
Terminal=false
Categories=Development;
EOF
chmod 644 "$DESKTOP"

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache /usr/share/icons/hicolor >/dev/null 2>&1 || true

echo "Instalado. Procure \"Fábrica Local de IA\" no menu de aplicativos,"
echo "ou rode o comando: fabrica-local-ia"
