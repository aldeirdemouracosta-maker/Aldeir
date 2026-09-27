"""
IAVOX Text Summarizer
======================
Resume ou reescreve o texto extraído do PDF, em português, usando um modelo
de linguagem local via Ollama. Suporta 3 níveis de densidade, alinhados ao
mesmo conceito usado no SlideForge (curto / médio / detalhado).
"""
from __future__ import annotations

import logging

import requests

logger = logging.getLogger("iavox.summarizer")

DEFAULT_TEXT_MODEL = "llama3.2:3b"
DEFAULT_OLLAMA_URL = "http://localhost:11434"

DENSITY_PROMPTS = {
    "curto": (
        "Resuma o texto abaixo em português, em um parágrafo curto (3 a 5 frases), "
        "mantendo só as ideias essenciais, de forma clara para ser ouvida em áudio."
    ),
    "medio": (
        "Resuma o texto abaixo em português, em dois ou três parágrafos, mantendo "
        "as ideias principais e os pontos de apoio mais importantes, de forma "
        "clara para ser ouvida em áudio."
    ),
    "detalhado": (
        "Reescreva o texto abaixo em português de forma clara e bem organizada "
        "para leitura em áudio, mantendo todos os detalhes e informações "
        "importantes do original, apenas simplificando frases muito longas ou "
        "estruturas visuais (como tabelas) que não fazem sentido faladas."
    ),
}

VALID_DENSITIES = tuple(DENSITY_PROMPTS.keys())


class TextSummarizer:
    """
    Resume/reescreve texto via LLM local (Ollama).

    Uso:
        summarizer = TextSummarizer()
        texto_curto = summarizer.summarize(texto_completo, density="curto")
    """

    def __init__(
        self,
        model: str = DEFAULT_TEXT_MODEL,
        ollama_url: str = DEFAULT_OLLAMA_URL,
        timeout: int = 120,
    ):
        self.model = model
        self.ollama_url = ollama_url.rstrip("/")
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            resp = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            resp.raise_for_status()
            models = [m.get("name", "") for m in resp.json().get("models", [])]
            return any(self.model.split(":")[0] in m for m in models)
        except Exception as exc:  # noqa: BLE001
            logger.info("Ollama indisponível para resumo: %s", exc)
            return False

    def summarize(self, text: str, density: str = "medio") -> str:
        if density not in DENSITY_PROMPTS:
            raise ValueError(
                f"Densidade inválida: {density!r}. Use uma de {VALID_DENSITIES}"
            )
        if not text.strip():
            return ""

        prompt = f"{DENSITY_PROMPTS[density]}\n\nTexto original:\n{text}"
        try:
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            result = resp.json().get("response", "").strip()
            return result or text
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao resumir via IA (%s) — devolvendo texto original.", exc)
            return text

    def summarize_long_text(self, text: str, density: str, chunk_size: int = 6000) -> str:
        """
        Para textos muito longos (livros, PDFs grandes), resume em blocos e
        depois consolida, para não estourar o contexto do modelo local.
        """
        if len(text) <= chunk_size:
            return self.summarize(text, density)

        chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
        partials = [self.summarize(c, density="detalhado") for c in chunks]
        combined = "\n\n".join(partials)
        return self.summarize(combined, density)
