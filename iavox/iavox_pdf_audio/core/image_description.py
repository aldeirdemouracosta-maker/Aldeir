"""
IAVOX Image Description
=========================
Gera audiodescrição textual de imagens extraídas do PDF, usando um modelo
de visão local via Ollama (ex: llava, moondream, bakllava, minicpm-v).

Se o Ollama não estiver disponível ou não tiver um modelo de visão instalado,
cai graciosamente para uma descrição genérica (placeholder), sem travar o
restante do fluxo de leitura.
"""
from __future__ import annotations

import base64
import logging

import requests

logger = logging.getLogger("iavox.image_description")

DEFAULT_VISION_MODEL = "llava:7b"
DEFAULT_OLLAMA_URL = "http://localhost:11434"

DESCRIBE_PROMPT_PT = (
    "Você está descrevendo uma imagem de um documento para uma pessoa cega "
    "que vai ouvir essa descrição em áudio. Descreva em português, em 1 a 3 "
    "frases, de forma objetiva e clara: o que a imagem mostra (foto, gráfico, "
    "diagrama, tabela, ícone etc.), os elementos principais e, se for um "
    "gráfico ou diagrama, a informação que ele transmite. Não comece com "
    "'A imagem mostra' — vá direto ao conteúdo."
)


class OllamaUnavailableError(RuntimeError):
    """Levantado quando o Ollama não responde ou não tem modelo de visão."""


class ImageDescriber:
    """
    Gera audiodescrição de imagens via modelo de visão local (Ollama).

    Uso:
        describer = ImageDescriber()
        if describer.is_available():
            texto = describer.describe(image_bytes)
    """

    def __init__(
        self,
        model: str = DEFAULT_VISION_MODEL,
        ollama_url: str = DEFAULT_OLLAMA_URL,
        timeout: int = 60,
    ):
        self.model = model
        self.ollama_url = ollama_url.rstrip("/")
        self.timeout = timeout

    def is_available(self) -> bool:
        """Checa se o Ollama está rodando e o modelo de visão está instalado."""
        try:
            resp = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            resp.raise_for_status()
            models = [m.get("name", "") for m in resp.json().get("models", [])]
            return any(self.model.split(":")[0] in m for m in models)
        except Exception as exc:  # noqa: BLE001
            logger.info("Ollama/modelo de visão indisponível: %s", exc)
            return False

    def describe(self, image_bytes: bytes) -> str:
        """
        Retorna uma audiodescrição em português para a imagem dada.
        Nunca levanta exceção para o chamador — em caso de falha, retorna
        uma descrição genérica de fallback.
        """
        try:
            b64 = base64.b64encode(image_bytes).decode("ascii")
            payload = {
                "model": self.model,
                "prompt": DESCRIBE_PROMPT_PT,
                "images": [b64],
                "stream": False,
            }
            resp = requests.post(
                f"{self.ollama_url}/api/generate", json=payload, timeout=self.timeout
            )
            resp.raise_for_status()
            text = resp.json().get("response", "").strip()
            return text or self._fallback_description()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao gerar audiodescrição via IA: %s", exc)
            return self._fallback_description()

    @staticmethod
    def _fallback_description() -> str:
        return (
            "Imagem presente no documento. A descrição automática não pôde ser "
            "gerada neste momento — verifique se o Ollama está rodando com um "
            "modelo de visão instalado, como llava."
        )
