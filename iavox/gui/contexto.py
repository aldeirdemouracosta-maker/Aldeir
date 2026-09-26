"""Estado compartilhado entre as telas: configurações, voz, caderno e robô."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from iavox_pdf_audio.suite.caderno import MiniCaderno



def caminho_config() -> Path:
    return Path.home() / ".iavox" / "config.json"


@dataclass
class Config:
    feedback_sonoro: bool = True
    motor_voz: str = "automatico"
    modelo_whisper: str = "small"
    tesseract_cmd: str = ""
    poppler_path: str = ""
    espeak_binary_path: str = ""
    piper_model_path: str = ""
    kokoro_model_path: str = ""
    kokoro_voices_path: str = ""
    pdfs_recentes: list = field(default_factory=list)

    @classmethod
    def carregar(cls, path: Path | None = None) -> "Config":
        path = path or caminho_config()
        try:
            dados = json.loads(path.read_text(encoding="utf-8"))
            validos = {k: v for k, v in dados.items() if k in cls.__dataclass_fields__}
            return cls(**validos)
        except (OSError, ValueError, TypeError):
            return cls()

    def salvar(self, path: Path | None = None) -> None:
        path = path or caminho_config()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1), encoding="utf-8")

    def lembrar_pdf(self, caminho: str) -> None:
        self.pdfs_recentes = [caminho] + [p for p in self.pdfs_recentes if p != caminho]
        self.pdfs_recentes = self.pdfs_recentes[:8]
        self.salvar()


class Contexto:
    """Passado para todas as páginas. A janela principal preenche os ganchos."""

    def __init__(self, config: Config, falador, caderno: MiniCaderno | None = None):
        self.config = config
        self.falador = falador
        self.caderno = caderno or MiniCaderno()
        # ganchos definidos pela janela principal
        self.definir_estado = lambda estado: None
        self.navegar = lambda nome: None
        self.anunciar = lambda texto: None   # fala + mostra no balão/status
        self.caderno_mudou = lambda: None

    def registrar(self, modulo: str, texto: str) -> None:
        if texto.strip():
            self.caderno.registrar(modulo, texto)
            self.caderno_mudou()
