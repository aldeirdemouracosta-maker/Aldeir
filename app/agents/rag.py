"""Agente RAG: indexa documentos locais e busca trechos por similaridade, com referência."""
from __future__ import annotations

from typing import Any

from app.agents.base import Agent
from app.multimodal.service import MultimodalService


SLOW_CHUNKS = 5_000  # acima disto a busca passa de ~0,6 s (medido: 1k=136 ms, 5k=624 ms, 20k=2,6 s)


class RagAgent(Agent):
    name = "rag"
    actions = ("rag_index", "rag_search")
    description = "Indexação e busca semântica em documentos locais (SQLite)."

    def __init__(self, service: MultimodalService) -> None:
        self.service = service

    async def available(self) -> tuple[bool, str]:
        try:
            installed = await self.service.provider.list_models()
        except Exception as e:
            return False, str(e)
        if self.service.embed_model not in installed:
            return False, f"modelo de embeddings {self.service.embed_model!r} não instalado"
        return True, "ok"

    async def run(self, action: str, payload: dict[str, Any]) -> str:
        if action == "rag_index":
            path = payload.get("path")
            if not isinstance(path, str):
                raise ValueError("payload.path é obrigatório")
            r = await self.service.index_path(path)
            note = f"; {len(r['skipped'])} ignorado(s): {'; '.join(r['skipped'][:3])}" if r["skipped"] else ""
            slow = (f"; AVISO: {r['chunks']} trechos — a busca em Python puro leva ~{r['chunks'] * 0.13 / 1000:.1f} s "
                    f"(medido: 0,13 ms/trecho); considere o sqlite-vec" if r["chunks"] > SLOW_CHUNKS else "")
            return (f"{r['files']} arquivo(s), {r['new_chunks']} trecho(s) novos; "
                    f"índice: {r['documents']} docs / {r['chunks']} trechos{note}{slow}")
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("payload.text é obrigatório")
        k = payload.get("k", 5)
        if not isinstance(k, int):
            raise ValueError("payload.k deve ser inteiro")
        hits = await self.service.search(text, k)
        return "\n\n".join(f"{h['path']}:L{h['line_start']}-L{h['line_end']} (score {h['score']})\n{h['text'][:400]}"
                           for h in hits) or "índice vazio"
