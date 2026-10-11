"""Cliente mínimo da API HTTP do Ollama."""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request


class BackendError(RuntimeError):
    pass


def _post(url: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise BackendError(f"ollama: {exc}") from exc


def generate(base_url: str, model: str, prompt: str, *, system: str | None = None,
             json_mode: bool = False, image_path: str | None = None, timeout: float = 600) -> str:
    body: dict = {"model": model, "prompt": prompt, "stream": False}
    if system:
        body["system"] = system
    if json_mode:
        body["format"] = "json"
    if image_path:
        with open(image_path, "rb") as f:
            body["images"] = [base64.b64encode(f.read()).decode()]
    out = _post(f"{base_url}/api/generate", body, timeout)
    if "response" not in out:
        raise BackendError(f"ollama: resposta sem 'response': {out}")
    return out["response"]


def unload(base_url: str, model: str, timeout: float = 60) -> None:
    """keep_alive=0 descarrega o modelo da VRAM."""
    _post(f"{base_url}/api/generate", {"model": model, "keep_alive": 0}, timeout)
