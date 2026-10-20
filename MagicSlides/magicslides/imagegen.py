"""Geração de imagens por IA (alternativa às fotos da internet).

Provedores:
- "gemini": API nativa do Google (modelos de imagem do Gemini), com chave.
- "openai": qualquer servidor compatível com POST /images/generations
  (OpenAI, LocalAI e outros programas locais).
- "pollinations": serviço comunitário gratuito, sem chave.
- "automatic1111": Stable Diffusion rodando no seu computador (AUTOMATIC1111,
  Forge, SD.Next... iniciados com --api): POST /sdapi/v1/txt2img.

Todos devolvem os bytes da imagem, que são reduzidos e embutidos no projeto
como data URL (igual às fotos da internet).
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import __version__
from .images import ImageError, _check_public_url, encode_image

IMAGE_PROVIDERS = ("gemini", "openai", "pollinations", "automatic1111")
PROVIDER_LABELS = {"gemini": "Gemini (Google)", "openai": "API compatível com a da OpenAI",
                   "pollinations": "Pollinations (grátis, sem chave)",
                   "automatic1111": "Stable Diffusion local (WebUI --api)"}
USER_AGENT = f"MagicSlides/{__version__} (desktop presentation app)"
TIMEOUT = 120
LOCAL_TIMEOUT = 1800   # no seu computador, sem placa de vídeo, uma imagem pode levar muitos minutos
MAX_BYTES = 20 * 1024 * 1024


def build_prompt(query: str, title: str = "") -> str:
    """Pedido de imagem: assunto + estilo que funciona bem como ilustração de slide."""
    subject = " ".join((query or title or "").split())[:300]
    context = f" (illustrating a slide titled “{' '.join(title.split())[:120]}”)" if title and query and title != query else ""
    return (f"{subject}{context}. High quality, clean, well composed, widescreen 16:9 image for a presentation slide. "
            "No text, no letters, no logos, no watermarks.")


def _request(req: urllib.request.Request, label: str, timeout: float = TIMEOUT) -> bytes:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200]
        if exc.code in (401, 403):
            raise ImageError(f"{label}: chave inválida ou sem permissão para gerar imagens.") from exc
        if exc.code == 404:
            raise ImageError(f"{label}: modelo não encontrado. Confira o nome do modelo nas configurações.") from exc
        if exc.code == 429:
            raise ImageError(f"{label}: limite de uso atingido. Tente de novo em instantes.") from exc
        raise ImageError(f"{label} respondeu {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ImageError(f"{label}: não foi possível conectar ({getattr(exc, 'reason', exc)}).") from exc


def _json_post(url: str, headers: dict[str, str], body: dict[str, Any], label: str,
               timeout: float = TIMEOUT) -> dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": USER_AGENT, **headers})
    raw = _request(req, label, timeout)
    if len(raw) > MAX_BYTES:
        raise ImageError(f"{label}: resposta grande demais.")
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise ImageError(f"{label}: resposta inesperada.") from exc


def _gemini(prompt: str, cfg: dict[str, Any]) -> bytes:
    key = cfg.get("imagegen_api_key")
    if not key:
        raise ImageError("Gemini precisa de chave de API (Configurações > Imagens geradas por IA).")
    model = cfg.get("imagegen_model") or "gemini-3.1-flash-image-preview"
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{urllib.parse.quote(model, safe='')}:generateContent")
    data = _json_post(url, {"x-goog-api-key": key}, {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }, "Gemini")
    for cand in data.get("candidates") or []:
        for part in (cand.get("content") or {}).get("parts") or []:
            blob = part.get("inlineData") or part.get("inline_data")
            if blob and blob.get("data"):
                return base64.b64decode(blob["data"])
    raise ImageError("O Gemini não devolveu imagem (o modelo pode não gerar imagens ou bloqueou o pedido).")


def _openai(prompt: str, cfg: dict[str, Any]) -> bytes:
    base = (cfg.get("imagegen_base_url") or "").rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise ImageError("Endereço do servidor de imagens inválido (ex.: https://api.openai.com/v1).")
    model = cfg.get("imagegen_model") or ""
    if not model:
        raise ImageError("Informe o nome do modelo de imagem (ex.: gpt-image-1, dall-e-3).")
    body: dict[str, Any] = {"model": model, "prompt": prompt, "n": 1}
    if model.startswith("dall-e-3"):
        body["size"] = "1792x1024"
    elif model.startswith("gpt-image"):
        body["size"] = "1536x1024"
    headers = {"Authorization": f"Bearer {cfg['imagegen_api_key']}"} if cfg.get("imagegen_api_key") else {}
    data = _json_post(base + "/images/generations", headers, body, "Servidor de imagens")
    item = ((data.get("data") or [{}])[0]) or {}
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    if item.get("url"):
        url = item["url"]
        host = urllib.parse.urlparse(base).hostname or ""
        if host not in ("localhost", "127.0.0.1", "::1"):   # servidor local pode devolver links locais
            _check_public_url(url)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        return _request(req, "Servidor de imagens")
    raise ImageError("O servidor de imagens não devolveu uma imagem.")


def _pollinations(prompt: str, cfg: dict[str, Any]) -> bytes:
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt[:600], safe="") +
           "?width=1280&height=720&nologo=true")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*"})
    return _request(req, "Pollinations")


def local_size(cfg: dict[str, Any]) -> tuple[int, int]:
    """Largura x altura (múltiplos de 8, proporção 16:9) para o Stable Diffusion local."""
    try:
        width = int(float(cfg.get("imagegen_width") or 768))
    except (TypeError, ValueError):
        width = 768
    width = max(256, min(1536, width)) // 8 * 8
    return width, max(144, round(width * 9 / 16 / 8) * 8)


def _automatic1111(prompt: str, cfg: dict[str, Any]) -> bytes:
    base = (cfg.get("imagegen_base_url") or "").rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise ImageError("Endereço do Stable Diffusion local inválido (ex.: http://127.0.0.1:7860).")
    try:
        steps = max(1, min(80, int(float(cfg.get("imagegen_steps") or 20))))
    except (TypeError, ValueError):
        steps = 20
    width, height = local_size(cfg)
    body: dict[str, Any] = {
        "prompt": prompt,
        "negative_prompt": "text, letters, words, watermark, logo, signature, blurry, low quality, deformed, ugly",
        "steps": steps, "width": width, "height": height,
        "cfg_scale": 1.0 if steps <= 6 else 7.0,   # modelos "Turbo" (poucos passos) pedem cfg baixo
        "batch_size": 1, "n_iter": 1,
    }
    if cfg.get("imagegen_model"):
        body["override_settings"] = {"sd_model_checkpoint": cfg["imagegen_model"]}
    try:
        data = _json_post(base + "/sdapi/v1/txt2img", {}, body, "Stable Diffusion local", LOCAL_TIMEOUT)
    except ImageError as exc:
        if "conectar" in str(exc):
            raise ImageError(f"{exc} O Stable Diffusion está aberto e foi iniciado com --api?") from exc
        raise
    images = data.get("images") or []
    if not images or not isinstance(images[0], str):
        raise ImageError("O Stable Diffusion local não devolveu imagem.")
    return base64.b64decode(images[0].split(",", 1)[-1])


_BACKENDS = {"gemini": _gemini, "openai": _openai, "pollinations": _pollinations, "automatic1111": _automatic1111}


def credit_for(cfg: dict[str, Any]) -> str:
    provider = cfg.get("imagegen_provider") or "gemini"
    model = cfg.get("imagegen_model") if provider != "pollinations" else "Pollinations"
    return f"Imagem gerada por IA ({PROVIDER_LABELS.get(provider, provider)}{', ' + model if model else ''})"


def generate(prompt: str, cfg: dict[str, Any]) -> tuple[str, int, int]:
    """Gera uma imagem e devolve (data URL, largura, altura)."""
    provider = cfg.get("imagegen_provider") or "gemini"
    fn = _BACKENDS.get(provider)
    if not fn:
        raise ImageError("Escolha um provedor de imagens por IA em Configurações.")
    if not (prompt or "").strip():
        raise ImageError("Descreva a imagem que a IA deve criar.")
    raw = fn(prompt.strip(), cfg)
    if not raw or len(raw) > MAX_BYTES:
        raise ImageError("A IA devolveu uma imagem vazia ou grande demais.")
    return encode_image(raw, 1600)
