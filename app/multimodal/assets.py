"""AssetStore: mídia só dentro de uma raiz, com limites de tamanho e validação por assinatura."""
from __future__ import annotations

from pathlib import Path

from app.core.models import SwarmError
from app.multimodal.media import sniff_audio, sniff_image
from app.terminal.workspace import Workspace

LIMITS = {"image": 10 * 2**20, "audio": 25 * 2**20, "text": 1 * 2**20}


class AssetError(SwarmError):
    pass


class AssetStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.ws = Workspace(self.root)  # reaproveita traversal/symlink/hardlink

    def path(self, rel: str, kind: str) -> Path:
        """Valida caminho, tamanho e tipo. Retorna o caminho seguro."""
        p = self.ws.resolve(rel)
        if not p.is_file():
            raise AssetError(f"não é arquivo: {rel}")
        if p.stat().st_size > LIMITS[kind]:
            raise AssetError(f"{kind} acima do limite de {LIMITS[kind]} bytes: {rel}")
        if kind == "text":
            return p
        with p.open("rb") as f:
            head = f.read(16)
        sniff = sniff_image if kind == "image" else sniff_audio
        if sniff(head) is None:
            raise AssetError(f"{rel} não é {kind} válido (PNG/JPEG)" if kind == "image"
                             else f"{rel} não é áudio reconhecido")
        return p

    def new_output(self, name: str, ext: str) -> Path:
        """Caminho novo em out/, sem sobrescrever nada."""
        out = self.root / "out"
        out.mkdir(exist_ok=True)
        safe = "".join(c for c in name if c.isalnum() or c in "-_")[:40] or "saida"
        for i in range(1000):
            p = out / f"{safe}{'' if i == 0 else f'-{i}'}.{ext}"
            if not p.exists():
                return p
        raise AssetError("muitos arquivos de saída com o mesmo nome")
