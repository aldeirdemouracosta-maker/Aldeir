"""Saída em UTF-8 mesmo quando o console/redirecionamento do Windows usa cp1252 ou OEM.

Sem isso, imprimir "→" (ou qualquer caractere fora da página de código) com a saída redirecionada
(`| Tee-Object`, `> arquivo`) derruba o programa com UnicodeEncodeError. `errors="replace"` nunca derruba.
"""
from __future__ import annotations

import sys


def utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):  # fluxos simulados (testes, CliRunner) podem não ter
            stream.reconfigure(encoding="utf-8", errors="replace")
