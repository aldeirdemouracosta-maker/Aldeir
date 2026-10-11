"""Cliente da API HTTP do ComfyUI: envia um workflow (formato API), espera e baixa as saídas.

O workflow é o JSON exportado pelo usuário em "Save (API Format)". Valores string que forem
exatamente "{{nome}}" são substituídos pelos parâmetros (mantendo o tipo: int, float, str).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .ollama import BackendError


def fill(node, params: dict):
    if isinstance(node, dict):
        return {k: fill(v, params) for k, v in node.items()}
    if isinstance(node, list):
        return [fill(v, params) for v in node]
    if isinstance(node, str) and node.startswith("{{") and node.endswith("}}"):
        key = node[2:-2].strip()
        if key in params:
            return params[key]
    return node


def _request(url: str, body: dict | None = None, timeout: float = 60) -> bytes:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except (urllib.error.URLError, OSError) as exc:
        raise BackendError(f"comfyui: {exc}") from exc


def run_workflow(base_url: str, workflow_path: str, params: dict, out_dir: str, *,
                 timeout: float = 1800, poll: float = 1.0) -> list[str]:
    with open(workflow_path, encoding="utf-8") as f:
        workflow = fill(json.load(f), params)
    resp = json.loads(_request(f"{base_url}/prompt", {"prompt": workflow, "client_id": uuid.uuid4().hex}))
    pid = resp.get("prompt_id")
    if not pid:
        raise BackendError(f"comfyui: workflow rejeitado: {resp}")

    deadline = time.monotonic() + timeout
    while True:
        hist = json.loads(_request(f"{base_url}/history/{pid}")).get(pid)
        if hist and hist.get("outputs"):
            break
        if time.monotonic() > deadline:
            raise BackendError(f"comfyui: timeout aguardando {pid}")
        time.sleep(poll)

    os.makedirs(out_dir, exist_ok=True)
    saved: list[str] = []
    for node_out in hist["outputs"].values():
        for item in (node_out.get("images", []) + node_out.get("gifs", []) + node_out.get("videos", [])):
            q = urllib.parse.urlencode({"filename": item["filename"], "subfolder": item.get("subfolder", ""),
                                        "type": item.get("type", "output")})
            # basename evita path traversal vindo de nomes de arquivo remotos
            dest = os.path.join(out_dir, os.path.basename(item["filename"]))
            with open(dest, "wb") as f:
                f.write(_request(f"{base_url}/view?{q}", timeout=300))
            saved.append(dest)
    if not saved:
        raise BackendError(f"comfyui: workflow {pid} terminou sem arquivos de saída")
    return saved


def free_memory(base_url: str) -> None:
    """Pede ao ComfyUI que descarregue modelos e libere VRAM."""
    _request(f"{base_url}/free", {"unload_models": True, "free_memory": True})
