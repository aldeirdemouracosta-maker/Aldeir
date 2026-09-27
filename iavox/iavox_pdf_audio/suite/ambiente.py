"""
Detecção do ambiente para a barra de status do IAVOX:
DOSVOX, microfone, OCR e modelos locais (Ollama). Tudo verificado de verdade
na máquina — nada é marcado como OK sem checar.
"""
from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path

import requests

PASTAS_DOSVOX = [r"C:\winvox", r"C:\Program Files (x86)\winvox", r"C:\Program Files\winvox"]
TESSERACT_WINDOWS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]
OLLAMA_URL = "http://localhost:11434"


@dataclass
class Status:
    nome: str
    ok: bool
    detalhe: str

    @property
    def fala(self) -> str:
        return f"{self.nome}: {'disponível' if self.ok else 'indisponível'}. {self.detalhe}"


def checar_dosvox() -> Status:
    pasta = os.environ.get("DOSVOX_HOME")
    candidatas = ([pasta] if pasta else []) + PASTAS_DOSVOX
    for p in candidatas:
        if p and Path(p).is_dir():
            return Status("DOSVOX", True, f"encontrado em {p}")
    return Status("DOSVOX", False, "pasta C:\\winvox não encontrada")


def checar_ocr(tesseract_cmd: str = "") -> Status:
    candidatos = [tesseract_cmd] if tesseract_cmd else []
    candidatos += [shutil.which("tesseract") or ""] + (
        TESSERACT_WINDOWS if platform.system() == "Windows" else []
    )
    for c in candidatos:
        if c and Path(c).exists():
            return Status("OCR", True, f"Tesseract em {c}")
    return Status("OCR", False, "Tesseract não encontrado")


def checar_microfone() -> Status:
    try:
        import sounddevice as sd  # opcional
    except Exception:  # noqa: BLE001 - ImportError ou falta da PortAudio
        return Status("Microfone", False, "instale o pacote sounddevice para gravar")
    try:
        entradas = [d for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]
    except Exception as exc:  # noqa: BLE001
        return Status("Microfone", False, f"erro ao listar dispositivos: {exc}")
    if not entradas:
        return Status("Microfone", False, "nenhum microfone conectado")
    return Status("Microfone", True, entradas[0].get("name", "microfone"))


def checar_modelos_locais(url: str = OLLAMA_URL) -> Status:
    try:
        resp = requests.get(f"{url}/api/tags", timeout=2)
        resp.raise_for_status()
        modelos = [m.get("name", "") for m in resp.json().get("models", [])]
    except Exception:  # noqa: BLE001
        return Status("Modelos locais", False, "Ollama não está rodando")
    if not modelos:
        return Status("Modelos locais", False, "Ollama sem modelos instalados")
    return Status("Modelos locais", True, ", ".join(modelos[:4]))


def checar_tudo(tesseract_cmd: str = "") -> list[Status]:
    return [checar_dosvox(), checar_microfone(), checar_ocr(tesseract_cmd), checar_modelos_locais()]
