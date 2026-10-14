"""Backends de mídia por HTTP: o SWARM só fala com servidores locais, sem torch/transformers no núcleo.

- Vision: llama-server com --mmproj (entrada de imagem em /v1/chat/completions, via image_url).
- Speech/Voice: servidor compatível com OpenAI (/v1/audio/transcriptions e /v1/audio/speech),
  por exemplo Speaches. Contratos conferidos contra servidores simulados; NÃO contra os reais.

Todas as chamadas são bloqueantes (httpx.Client) e rodam em thread (MultimodalService usa to_thread).
"""
from __future__ import annotations

import array
import base64
import io
import time
import wave
from pathlib import Path
from collections.abc import Sequence

import httpx

from app.core.models import ProviderError, UnavailableError
from app.multimodal.media import sniff_image
from app.providers.base import strip_think

PROBE_TTL = 5.0  # a UI consulta a cada 3 s; não vale bater no servidor a cada consulta


class _Http:
    def __init__(self, base_url: str, timeout: float, client: httpx.Client | None) -> None:
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self._client = client or httpx.Client(timeout=timeout)
        self._probe: tuple[float, tuple[bool, str]] | None = None

    def probe(self) -> tuple[bool, str]:
        now = time.monotonic()
        if self._probe and now - self._probe[0] < PROBE_TTL:
            return self._probe[1]
        try:
            r = self._client.get(f"{self.base}/v1/models", timeout=min(2.0, self.timeout))
            result = (True, "ok") if r.status_code == 200 else (False, f"servidor respondeu HTTP {r.status_code}")
        except httpx.HTTPError as e:
            result = (False, f"servidor indisponível: {e}")
        self._probe = (now, result)
        return result

    def post(self, path: str, **kw) -> httpx.Response:
        try:
            r = self._client.post(f"{self.base}{path}", **kw)
        except httpx.HTTPError as e:
            raise ProviderError(f"servidor indisponível: {e}") from e
        if r.status_code >= 400:
            raise ProviderError(f"servidor respondeu HTTP {r.status_code}: {r.text[:200]}")
        return r


class LlamaServerVisionBackend:
    def __init__(self, base_url: str, model: str = "", timeout: float = 120.0,
                 client: httpx.Client | None = None) -> None:
        self.http, self.model = _Http(base_url, timeout, client), model

    def probe(self) -> tuple[bool, str]:
        return self.http.probe()

    def describe(self, image: Path, prompt: str) -> str:
        data = image.read_bytes()
        kind = sniff_image(data[:16])
        if kind is None:
            raise UnavailableError("imagem inválida")
        uri = f"data:image/{kind};base64,{base64.b64encode(data).decode()}"
        body = {"messages": [{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": uri}}]}],
                "stream": False, "max_tokens": 300}
        if self.model:
            body["model"] = self.model
        try:
            return strip_think(self.http.post("/v1/chat/completions", json=body).json()["choices"][0]["message"]["content"])
        except (KeyError, IndexError, ValueError) as e:
            raise ProviderError(f"resposta inesperada do servidor de visão: {e}") from e


class OpenAIAudioBackend:
    """Speech e Voice no mesmo servidor. Vozes: o contrato OpenAI não as lista; use SWARM_VOICE_LIST."""

    def __init__(self, base_url: str, stt_model: str = "", tts_model: str = "", voices: Sequence[str] = (),
                 timeout: float = 120.0, client: httpx.Client | None = None) -> None:
        self.http, self.stt_model, self.tts_model = _Http(base_url, timeout, client), stt_model, tts_model
        self._voices = list(voices)

    def probe(self) -> tuple[bool, str]:
        return self.http.probe()

    # --- Speech ---
    def transcribe(self, audio: Path) -> tuple[str, str]:
        files = {"file": (audio.name, audio.read_bytes())}
        data = {"response_format": "verbose_json"}
        if self.stt_model:
            data["model"] = self.stt_model
        try:
            r = self.http.post("/v1/audio/transcriptions", files=files, data=data)
        except ProviderError as e:
            if "HTTP 400" not in str(e) and "HTTP 422" not in str(e):
                raise
            data["response_format"] = "json"  # servidor sem verbose_json: só o texto, idioma desconhecido
            r = self.http.post("/v1/audio/transcriptions", files=files, data=data)
        try:
            j = r.json()
            return j["text"].strip(), str(j.get("language") or "und")
        except (KeyError, ValueError) as e:
            raise ProviderError(f"resposta inesperada da transcrição: {e}") from e

    # --- Voice ---
    def voices(self) -> list[str]:
        if not self._voices:
            raise UnavailableError("lista de vozes desconhecida: defina SWARM_VOICE_LIST (ex.: pf_dora,pm_alex)")
        return sorted(self._voices)

    def synthesize(self, text: str, voice: str) -> tuple[Sequence[float], int]:
        body = {"input": text, "voice": voice, "response_format": "wav"}
        if self.tts_model:
            body["model"] = self.tts_model
        raw = self.http.post("/v1/audio/speech", json=body).content
        if raw[:4] != b"RIFF":
            raise ProviderError("o servidor não devolveu WAV (response_format=wav não suportado?)")
        with wave.open(io.BytesIO(raw), "rb") as w:
            if w.getsampwidth() != 2 or w.getnchannels() != 1:
                raise ProviderError("WAV com formato não suportado (esperado PCM 16 bits mono)")
            pcm = array.array("h")
            pcm.frombytes(w.readframes(w.getnframes()))
            return [s / 32768 for s in pcm], w.getframerate()
