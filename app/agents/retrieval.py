"""Agente RETRIEVAL: busca de imagens por texto (embeddings imagem-texto). Referência: Chinese-CLIP."""
from __future__ import annotations

from typing import Any

from app.agents.multimodal import MediaAgent


class RetrievalAgent(MediaAgent):
    name = "retrieval"
    actions = ("retrieval_index", "retrieval_search")
    description = "Indexa imagens locais e as encontra por descrição em texto."
    backend_attr = "clip"

    async def run(self, action: str, payload: dict[str, Any]) -> str:
        if action == "retrieval_index":
            path = payload.get("path")
            if not isinstance(path, str):
                raise ValueError("payload.path é obrigatório")
            r = await self.service.index_images(path)
            note = f"; {len(r['skipped'])} ignorada(s): {'; '.join(r['skipped'][:3])}" if r["skipped"] else ""
            return f"{r['files']} imagem(ns), {r['new']} nova(s); índice: {r['images']} imagens{note}"
        text = payload.get("text")
        k = payload.get("k", 5)
        if not isinstance(text, str) or not text.strip() or not isinstance(k, int):
            raise ValueError("payload.text (texto) e payload.k (inteiro) são obrigatórios")
        hits = await self.service.search_images(text, k)
        return "\n".join(f"{h['path']} (score {h['score']})" for h in hits) or "índice de imagens vazio"
