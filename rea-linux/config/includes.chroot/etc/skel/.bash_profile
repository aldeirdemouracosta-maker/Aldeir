# shellcheck shell=bash
# Carrega o .bashrc e, no terminal 1, abre a interface grafica (Openbox + Painel REA).
[ -f "$HOME/.bashrc" ] && . "$HOME/.bashrc"
if [ -z "${DISPLAY:-}" ] && [ "$(tty)" = "/dev/tty1" ]; then
    exec startx -- -nolisten tcp >/dev/null 2>&1
fi
