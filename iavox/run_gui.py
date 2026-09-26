#!/usr/bin/env python3
"""Ponto de entrada da interface gráfica do IAVOX."""
import os
import sys

# Sempre em modo UTF-8: se o idioma do sistema (LANG/LC_ALL) estiver mal
# configurado, o Python cai para ASCII e qualquer texto com acento quebra
# ("'ascii' codec can't decode byte 0xc3"). Reinicia com -X utf8 nesse caso.
if not sys.flags.utf8_mode and os.environ.get("IAVOX_UTF8") != "1":
    os.environ["IAVOX_UTF8"] = "1"
    os.execv(sys.executable, [sys.executable, "-X", "utf8", *sys.argv])

from gui.janela import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
