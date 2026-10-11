"""Executores reais por tipo de tarefa. Só existem para serviços configurados."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Callable

from ..config import Config
from .backends import comfyui, ollama, sdcpp
from .backends.ollama import BackendError

Executor = Callable[[dict], dict]


def _out_dir(cfg: Config, payload: dict) -> str:
    """out_dir precisa ficar dentro de cfg.output_dir (evita escrita fora do projeto)."""
    root = os.path.realpath(cfg.output_dir)
    target = os.path.realpath(os.path.join(root, payload.get("project_id", "tmp"), payload.get("sub", "")))
    if os.path.commonpath([root, target]) != root:
        raise BackendError("project_id inválido")
    return target


VIDEO_EXT = {".mp4", ".webm", ".mov", ".mkv", ".gif", ".webp"}


def _still_frame(path: str) -> str:
    """O VLM só lê imagens: de vídeos, extrai o frame central com ffmpeg."""
    if os.path.splitext(path)[1].lower() not in VIDEO_EXT:
        return path
    if not shutil.which("ffmpeg"):
        raise BackendError("ffmpeg não encontrado (necessário para extrair frame do vídeo)")
    out = path + ".frame.png"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-vf", "select=eq(n\\,0)", "-frames:v", "1", out]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if r.returncode != 0 or not os.path.exists(out):
        raise BackendError(f"ffmpeg falhou: {r.stderr[-200:]}")
    return out


def _score(text: str) -> float:
    m = re.search(r"\d+(?:[.,]\d+)?", text)
    if not m:
        raise BackendError(f"VLM não retornou nota: {text[:80]!r}")
    return min(max(float(m.group().replace(",", ".")) / 10.0, 0.0), 1.0)


def build(cfg: Config) -> dict[str, Executor]:
    ex: dict[str, Executor] = {}
    if cfg.ollama_url and cfg.llm_model:
        ex["llm"] = lambda p: {"text": ollama.generate(
            cfg.ollama_url, cfg.llm_model, p["prompt"], system=p.get("system"), json_mode=bool(p.get("json")))}
    if cfg.ollama_url and cfg.vlm_model:
        def consistency(p: dict) -> dict:
            if not p.get("image") or not os.path.isfile(p["image"]):
                raise BackendError("consistency: imagem ausente")
            q = ("Nota de 0 a 10 para a consistência visual desta imagem com a descrição: "
                 f"{p['prompt']}\nResponda apenas com o número.")
            img = _still_frame(p["image"])
            return {"score": _score(ollama.generate(cfg.ollama_url, cfg.vlm_model, q, image_path=img))}
        ex["consistency"] = consistency
    if cfg.comfy_url and cfg.comfy_workflow_video:
        ex["video"] = lambda p: {"files": comfyui.run_workflow(
            cfg.comfy_url, cfg.comfy_workflow_video, {"prompt": p["prompt"], "seed": p.get("seed", 42)}, _out_dir(cfg, p))}
    if cfg.comfy_url and cfg.comfy_workflow_image:
        ex["heavy_image"] = lambda p: {"files": comfyui.run_workflow(
            cfg.comfy_url, cfg.comfy_workflow_image, {"prompt": p["prompt"], "seed": p.get("seed", 42)}, _out_dir(cfg, p))}
    if cfg.sd_bin and cfg.sd_model:
        ex["light_image"] = lambda p: {"files": [sdcpp.generate(
            cfg.sd_bin, cfg.sd_model, p["prompt"], os.path.join(_out_dir(cfg, p), p.get("name", "image.png")),
            seed=p.get("seed", 42))]}
    return ex


def model_name(task: str, cfg: Config) -> str | None:
    """Identificador do modelo residente para o slot (None = tarefa sem modelo residente)."""
    return {"llm": f"ollama:{cfg.llm_model}", "consistency": f"ollama:{cfg.vlm_model}",
            "video": "comfyui", "heavy_image": "comfyui", "light_image": "sdcpp"}.get(task)


class GpuBackend:
    """Backend de slot real: descarregar = liberar a VRAM no serviço dono do modelo."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def load(self, model: str) -> None:  # o serviço carrega sob demanda na primeira requisição
        pass

    def unload(self, model: str) -> None:
        import sys
        try:
            if model.startswith("ollama:") and self.cfg.ollama_url:
                ollama.unload(self.cfg.ollama_url, model[len("ollama:"):])
            elif model == "comfyui" and self.cfg.comfy_url:
                comfyui.free_memory(self.cfg.comfy_url)
        except BackendError as exc:  # não trava a fila; avisa que a VRAM pode não ter sido liberada
            print(f"AVISO: falha ao descarregar {model}: {exc}", file=sys.stderr, flush=True)
