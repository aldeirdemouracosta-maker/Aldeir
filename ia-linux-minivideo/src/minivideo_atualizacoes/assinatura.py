"""Assinatura Ed25519 do SHA256SUMS dos lançamentos do ISO (via openssl ≥ 3).

Como no APT, uma única assinatura protege uma corrente de hashes:
SHA256SUMS.sig → SHA256SUMS → sha256 de cada ISO. A chave pública fica no
próprio ISO (/usr/share/minivideo/chave-publica.pem); a privada só no
secret MINIVIDEO_ASSINATURA_CHAVE do GitHub Actions.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Dict, Optional

CHAVE_PUBLICA = "/usr/share/minivideo/chave-publica.pem"


def chave_publica() -> Optional[str]:
    caminho = os.environ.get("MINIVIDEO_CHAVE_PUBLICA", CHAVE_PUBLICA)
    return caminho if os.path.isfile(caminho) else None


def verificar(arquivo: str, assinatura: str, chave: str) -> bool:
    if not shutil.which("openssl"):
        raise RuntimeError("openssl ausente: não dá para conferir a assinatura")
    r = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", chave, "-rawin",
                        "-in", arquivo, "-sigfile", assinatura],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return r.returncode == 0


def ler_somas(texto: str) -> Dict[str, str]:
    out = {}
    for linha in texto.splitlines():
        m = re.match(r"([0-9a-fA-F]{64})\s+\*?(\S+)$", linha.strip())
        if m:
            out[os.path.basename(m.group(2))] = m.group(1).lower()
    return out
