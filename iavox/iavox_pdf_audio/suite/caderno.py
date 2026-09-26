"""
Mini Caderno IAVOX
===================
Registro cronológico e leve de tudo o que o aluno fez nos módulos
(LeitorVox, FalaVox, OlhaVox, EstudaVox, Modo Atividade), para o professor
orientador acompanhar. Guarda só texto (sem mídia pesada), em JSON, e pode
ser lido em voz alta, salvo em TXT ou aberto no editor do DOSVOX.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

MAX_ITENS_NA_TELA = 30
LIMITE_TEXTO = 4000  # texto leve: corta respostas muito longas



def caminho_padrao() -> Path:
    return Path.home() / ".iavox" / "caderno.json"

# Editor de texto do DOSVOX. O nome oficial do programa é "edivox";
# aceitamos também "edvox" porque é como aparece em alguns materiais.
EDITORES_DOSVOX = [
    r"C:\winvox\edivox.exe",
    r"C:\winvox\edvox.exe",
    r"C:\Program Files (x86)\winvox\edivox.exe",
    r"C:\Program Files\winvox\edivox.exe",
]


@dataclass
class ItemCaderno:
    modulo: str      # LeitorVox, FalaVox, OlhaVox, EstudaVox, Atividade
    texto: str
    data_hora: str   # "24/05/2025 14:30"

    @property
    def resumo(self) -> str:
        """Primeira linha curta, para a lista na tela."""
        linha = " ".join(self.texto.split())
        return linha if len(linha) <= 90 else linha[:87] + "..."


class MiniCaderno:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else caminho_padrao()
        self.itens: list[ItemCaderno] = []
        self._carregar()

    # ------------------------------------------------------------ dados

    def _carregar(self) -> None:
        try:
            dados = json.loads(self.path.read_text(encoding="utf-8"))
            self.itens = [ItemCaderno(**d) for d in dados]
        except (OSError, ValueError, TypeError):
            self.itens = []

    def _salvar(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([asdict(i) for i in self.itens], ensure_ascii=False, indent=1),
            encoding="utf-8",
        )

    def registrar(self, modulo: str, texto: str, quando: datetime | None = None) -> ItemCaderno:
        texto = texto.strip()
        if len(texto) > LIMITE_TEXTO:
            texto = texto[:LIMITE_TEXTO] + " [...]"
        quando = quando or datetime.now()
        item = ItemCaderno(modulo=modulo, texto=texto, data_hora=quando.strftime("%d/%m/%Y %H:%M"))
        self.itens.append(item)
        self._salvar()
        return item

    def limpar(self) -> None:
        self.itens = []
        self._salvar()

    def itens_na_tela(self) -> list[ItemCaderno]:
        """Os mais recentes primeiro, no máximo 30."""
        return list(reversed(self.itens))[:MAX_ITENS_NA_TELA]

    # ------------------------------------------------------------ saídas

    def como_texto(self) -> str:
        if not self.itens:
            return "Mini Caderno vazio."
        partes = [f"{i.data_hora} - {i.modulo}\n{i.texto}" for i in self.itens]
        return "MINI CADERNO IAVOX\n\n" + "\n\n".join(partes) + "\n"

    def como_fala(self) -> str:
        """Versão para ler em voz alta: mais recentes primeiro."""
        itens = self.itens_na_tela()
        if not itens:
            return "O Mini Caderno está vazio."
        partes = [f"{i.modulo}, {i.data_hora}. {i.texto}" for i in itens]
        return f"Mini Caderno com {len(self.itens)} itens. " + " ... ".join(partes)

    def salvar_txt(self, destino: str | Path) -> Path:
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        # Windows: ANSI (cp1252) é o que o DOSVOX lê melhor; em outros sistemas, UTF-8.
        encoding = "cp1252" if platform.system() == "Windows" else "utf-8"
        destino.write_text(self.como_texto(), encoding=encoding, errors="replace")
        return destino


def encontrar_editor_dosvox() -> str | None:
    for caminho in EDITORES_DOSVOX:
        if Path(caminho).exists():
            return caminho
    return None


def abrir_no_editor(arquivo_txt: str | Path) -> str:
    """
    Abre o TXT no editor do DOSVOX (edivox). Se o DOSVOX não estiver
    instalado, abre no editor padrão do sistema. Retorna o nome do programa usado.
    """
    arquivo_txt = str(arquivo_txt)
    editor = encontrar_editor_dosvox()
    if editor:
        subprocess.Popen([editor, arquivo_txt])
        return "EDIVOX (DOSVOX)"
    if platform.system() == "Windows":
        os.startfile(arquivo_txt)  # type: ignore[attr-defined]
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", arquivo_txt])
    else:
        subprocess.Popen(["xdg-open", arquivo_txt])
    return "editor padrão do sistema"
