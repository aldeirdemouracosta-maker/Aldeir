"""
EstudaVox (F4) — resumo e perguntas de estudo sobre um texto.

Usa o mesmo Ollama local do resumo do leitor de PDF. Sem Ollama, cai para
um resumo simples (primeiras frases) e perguntas montadas a partir das
frases do texto, para o módulo nunca ficar sem resposta.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import requests

from ..core.summarizer import DEFAULT_OLLAMA_URL, DEFAULT_TEXT_MODEL, TextSummarizer

PROMPT_PERGUNTAS = (
    "Você é um professor ajudando um aluno com deficiência visual a estudar. "
    "Com base no texto abaixo, escreva {n} perguntas de estudo em português, "
    "curtas e claras para serem ouvidas em áudio, uma por linha, numeradas "
    "(1., 2., ...). Não escreva as respostas.\n\nTexto:\n{texto}"
)


@dataclass
class Estudo:
    resumo: str
    perguntas: list[str] = field(default_factory=list)
    usou_ia: bool = False

    def como_fala(self) -> str:
        partes = [f"Resumo. {self.resumo}"]
        if self.perguntas:
            partes.append("Perguntas para estudar.")
            partes += [f"Pergunta {i}. {p}" for i, p in enumerate(self.perguntas, 1)]
        return " ".join(partes)

    def como_texto(self) -> str:
        linhas = ["RESUMO", self.resumo, "", "PERGUNTAS"]
        linhas += [f"{i}. {p}" for i, p in enumerate(self.perguntas, 1)]
        return "\n".join(linhas)


def _frases(texto: str) -> list[str]:
    texto = " ".join(texto.split())
    return [f.strip() for f in re.split(r"(?<=[.!?])\s+", texto) if len(f.strip()) > 20]


def resumo_simples(texto: str, max_frases: int = 4) -> str:
    frases = _frases(texto)
    return " ".join(frases[:max_frases]) if frases else texto.strip()[:600]


def perguntas_simples(texto: str, n: int = 5) -> list[str]:
    """Sem IA: transforma frases do texto em perguntas de 'explique'."""
    perguntas = []
    for frase in _frases(texto)[: n * 2]:
        frase = frase.rstrip(".!?")
        palavras = frase.split()
        if len(palavras) < 5:
            continue
        tema = " ".join(palavras[:6])
        perguntas.append(f"Explique com suas palavras: {tema}...?")
        if len(perguntas) >= n:
            break
    return perguntas


def _parse_perguntas(resposta: str) -> list[str]:
    perguntas = []
    for linha in resposta.splitlines():
        m = re.match(r"\s*\d+[.)\-]\s*(.+)", linha)
        if m and m.group(1).strip():
            perguntas.append(m.group(1).strip())
    return perguntas


class EstudaVox:
    def __init__(self, model: str = DEFAULT_TEXT_MODEL, ollama_url: str = DEFAULT_OLLAMA_URL, timeout: int = 120):
        self.summarizer = TextSummarizer(model=model, ollama_url=ollama_url, timeout=timeout)
        self.model = model
        self.ollama_url = ollama_url.rstrip("/")
        self.timeout = timeout

    def estudar(self, texto: str, densidade: str = "medio", n_perguntas: int = 5) -> Estudo:
        texto = texto.strip()
        if not texto:
            raise ValueError("O texto está vazio — nada para estudar.")

        if not self.summarizer.is_available():
            return Estudo(resumo_simples(texto), perguntas_simples(texto, n_perguntas), usou_ia=False)

        resumo = self.summarizer.summarize_long_text(texto, densidade)
        perguntas: list[str] = []
        try:
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": PROMPT_PERGUNTAS.format(n=n_perguntas, texto=texto[:6000]),
                    "stream": False,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            perguntas = _parse_perguntas(resp.json().get("response", ""))[:n_perguntas]
        except Exception:  # noqa: BLE001
            perguntas = []
        return Estudo(resumo, perguntas or perguntas_simples(texto, n_perguntas), usou_ia=True)


def ler_texto_de_arquivo(caminho: str | Path) -> str:
    """Aceita PDF (usa o extrator com OCR) ou TXT."""
    caminho = Path(caminho)
    if caminho.suffix.lower() == ".pdf":
        from ..core.extractor import PDFExtractor

        extractor = PDFExtractor()
        extractor.extract_images = False
        return extractor.extract(caminho).full_text
    for enc in ("utf-8", "cp1252"):
        try:
            return caminho.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return caminho.read_text(encoding="utf-8", errors="replace")
