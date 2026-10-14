"""MultimodalService: coordena AssetStore, backends opcionais e índice RAG. Execução bloqueante em thread."""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from app.core.models import SwarmError, UnavailableError
from app.multimodal.assets import AssetStore
from app.multimodal.convert import DOC_EXT, convert_to_text
from app.multimodal.documents import DocumentIndex
from app.multimodal.media import write_wav

TEXT_EXT = {".txt", ".md", ".py", ".rst", ".json", ".yaml", ".yml", ".toml", ".csv"}
INDEX_EXT = TEXT_EXT | DOC_EXT
IMAGE_EXT = {".png", ".jpg", ".jpeg"}
MAX_FILES = 200


class MultimodalService:
    def __init__(self, assets: AssetStore, index: DocumentIndex, provider, embed_model: str,
                 vision=None, speech=None, voice=None, ocr=None, clip=None) -> None:
        self.assets, self.index, self.provider, self.embed_model = assets, index, provider, embed_model
        self.vision, self.speech, self.voice, self.ocr, self.clip = vision, speech, voice, ocr, clip

    @staticmethod
    async def _need(backend, label: str):
        if backend is None:
            raise UnavailableError(f"{label} não configurado")
        ok, why = await asyncio.to_thread(backend.probe)  # probe pode ser HTTP: nunca no loop de eventos
        if not ok:
            raise UnavailableError(f"{label} indisponível: {why}")
        return backend

    async def describe_image(self, rel: str, prompt: str) -> str:
        be = await self._need(self.vision, "vision")
        p = self.assets.path(rel, "image")
        return await asyncio.to_thread(be.describe, p, prompt or "Descreva a imagem.")

    async def read_text(self, rel: str) -> str:
        be = await self._need(self.ocr, "ocr")
        lines = await asyncio.to_thread(be.read, self.assets.path(rel, "image"))
        return "\n".join(lines) or "(nenhum texto encontrado)"

    async def transcribe(self, rel: str) -> str:
        be = await self._need(self.speech, "speech")
        p = self.assets.path(rel, "audio")
        text, lang = await asyncio.to_thread(be.transcribe, p)
        return f"[{lang}] {text}"

    async def list_voices(self) -> list[str]:
        be = await self._need(self.voice, "voice")
        return await asyncio.to_thread(be.voices)

    async def speak(self, text: str, voice: str) -> str:
        be = await self._need(self.voice, "voice")
        if len(text) > 2000:
            raise ValueError("texto acima de 2000 caracteres")
        samples, rate = await asyncio.to_thread(be.synthesize, text, voice)
        out = self.assets.new_output(f"voz-{voice}", "wav")
        write_wav(out, samples, rate)
        return out.relative_to(self.assets.root).as_posix()

    async def _embed(self, text: str) -> list[float]:
        return await self.provider.embed(self.embed_model, text)

    async def _text_of(self, f, r: str) -> str:
        if f.suffix.lower() in DOC_EXT:
            return await asyncio.to_thread(convert_to_text, self.assets.ws.resolve(r))  # resolve: symlink/hardlink
        return self.assets.ws.read(r)  # limites, binário, symlink: mesmas regras do workspace

    async def index_path(self, rel: str) -> dict:
        target = self.assets.ws.resolve(rel)
        files = [target] if target.is_file() else [
            f for f in self.assets.ws.files() if f.suffix.lower() in INDEX_EXT and target in f.parents
        ][:MAX_FILES]
        done = chunks = 0
        skipped: list[str] = []
        for f in files:
            r = self.assets.ws.rel(f)
            try:
                text = await self._text_of(f, r)
            except SwarmError as e:
                if f == target:
                    raise  # arquivo pedido diretamente: o erro é a resposta
                skipped.append(f"{r}: {e}")  # em pasta, um arquivo ruim não bloqueia os outros
                continue
            chunks += await self.index.index_text(r, text, self._embed, self.embed_model)
            done += 1
        return {"files": done, "new_chunks": chunks, "skipped": skipped, **self.index.stats()}

    async def search(self, query: str, k: int) -> list[dict]:
        return self.index.search(await self._embed(query), k)

    async def index_images(self, rel: str) -> dict:
        be = await self._need(self.clip, "retrieval")
        target = self.assets.ws.resolve(rel)
        files = [target] if target.is_file() else [
            f for f in self.assets.ws.files() if f.suffix.lower() in IMAGE_EXT and target in f.parents][:MAX_FILES]
        new, done = 0, 0
        skipped: list[str] = []
        for f in files:
            r = self.assets.ws.rel(f)
            try:
                p = self.assets.path(r, "image")  # limites e assinatura
            except SwarmError as e:
                if f == target:
                    raise
                skipped.append(f"{r}: {e}")
                continue
            sha = hashlib.sha256(p.read_bytes()).hexdigest()
            emb = await asyncio.to_thread(be.embed_image, p)
            new += self.index.index_image(r, sha, emb)
            done += 1
        return {"files": done, "new": new, "skipped": skipped, **self.index.stats()}

    async def search_images(self, query: str, k: int) -> list[dict]:
        be = await self._need(self.clip, "retrieval")
        return self.index.search_images(await asyncio.to_thread(be.embed_text, query), k)
