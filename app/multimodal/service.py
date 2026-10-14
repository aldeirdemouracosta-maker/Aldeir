"""MultimodalService: coordena AssetStore, backends opcionais e índice RAG. Execução bloqueante em thread."""
from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.models import UnavailableError
from app.multimodal.assets import AssetStore
from app.multimodal.documents import DocumentIndex
from app.multimodal.media import write_wav

TEXT_EXT = {".txt", ".md", ".py", ".rst", ".json", ".yaml", ".yml", ".toml", ".csv"}
MAX_FILES = 200


class MultimodalService:
    def __init__(self, assets: AssetStore, index: DocumentIndex, provider, embed_model: str,
                 vision=None, speech=None, voice=None) -> None:
        self.assets, self.index, self.provider, self.embed_model = assets, index, provider, embed_model
        self.vision, self.speech, self.voice = vision, speech, voice

    @staticmethod
    def _need(backend, label: str):
        if backend is None:
            raise UnavailableError(f"{label} não configurado")
        ok, why = backend.probe()
        if not ok:
            raise UnavailableError(f"{label} indisponível: {why}")
        return backend

    async def describe_image(self, rel: str, prompt: str) -> str:
        be = self._need(self.vision, "vision")
        p = self.assets.path(rel, "image")
        return await asyncio.to_thread(be.describe, p, prompt or "Descreva a imagem.")

    async def transcribe(self, rel: str) -> str:
        be = self._need(self.speech, "speech")
        p = self.assets.path(rel, "audio")
        text, lang = await asyncio.to_thread(be.transcribe, p)
        return f"[{lang}] {text}"

    async def list_voices(self) -> list[str]:
        return await asyncio.to_thread(self._need(self.voice, "voice").voices)

    async def speak(self, text: str, voice: str) -> str:
        be = self._need(self.voice, "voice")
        if len(text) > 2000:
            raise ValueError("texto acima de 2000 caracteres")
        samples, rate = await asyncio.to_thread(be.synthesize, text, voice)
        out = self.assets.new_output(f"voz-{voice}", "wav")
        write_wav(out, samples, rate)
        return out.relative_to(self.assets.root).as_posix()

    async def _embed(self, text: str) -> list[float]:
        return await self.provider.embed(self.embed_model, text)

    async def index_path(self, rel: str) -> dict:
        target = self.assets.ws.resolve(rel)
        files = [target] if target.is_file() else [
            f for f in self.assets.ws.files() if f.suffix.lower() in TEXT_EXT and target in f.parents
        ][:MAX_FILES]
        done = chunks = 0
        for f in files:
            r = self.assets.ws.rel(f)
            text = self.assets.ws.read(r)  # limites, binário, symlink: mesmas regras do workspace
            chunks += await self.index.index_text(r, text, self._embed, self.embed_model)
            done += 1
        return {"files": done, "new_chunks": chunks, **self.index.stats()}

    async def search(self, query: str, k: int) -> list[dict]:
        return self.index.search(await self._embed(query), k)
