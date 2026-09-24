"""Sobe o llama-server local para o assistente (só quando o usuário pede).

Escuta apenas em 127.0.0.1; o processo pertence à interface e é encerrado
ao sair dela. Na RX 580 o llama.cpp usa Vulkan (-ngl 99 manda todas as
camadas para a GPU); sem GPU roda na CPU.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import time
import urllib.request
from typing import Optional

PORTA = 8089


def achar_gguf(pasta_modelos: str) -> Optional[str]:
    """Menor GGUF em Modelos/llm (o 1.7B antes do 8B, por exemplo)."""
    arquivos = glob.glob(os.path.join(pasta_modelos, "llm", "*.gguf"))
    return min(arquivos, key=os.path.getsize) if arquivos else None


class ServidorLocal:
    def __init__(self, gguf: str, porta: int = PORTA, binario: str = "llama-server"):
        self.gguf, self.porta, self.binario = gguf, porta, binario
        self.proc: Optional[subprocess.Popen] = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.porta}/v1"

    def iniciar(self, log_path: str, espera_s: float = 180) -> None:
        exe = shutil.which(self.binario)
        if not exe:
            raise RuntimeError(f"{self.binario} ausente")
        log = open(log_path, "ab")
        self.proc = subprocess.Popen(
            [exe, "-m", self.gguf, "--host", "127.0.0.1", "--port", str(self.porta), "-c", "4096", "-ngl", "99"],
            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        fim = time.time() + espera_s
        while time.time() < fim:
            if self.proc.poll() is not None:
                raise RuntimeError(f"llama-server saiu com código {self.proc.returncode} (ver {log_path})")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.porta}/health", timeout=2) as r:
                    if json.loads(r.read().decode() or "{}").get("status") == "ok":
                        return
            except (OSError, ValueError):
                pass
            time.sleep(1)
        self.parar()
        raise RuntimeError(f"llama-server não ficou pronto em {espera_s:.0f} s (ver {log_path})")

    def parar(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
