"""Configuração por variáveis de ambiente. Serviço não configurado => tarefa fica simulada."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    ollama_url: str | None = None          # ex.: http://127.0.0.1:11434
    llm_model: str | None = None           # ex.: qwen2.5:7b-instruct
    vlm_model: str | None = None           # ex.: qwen2.5vl:7b
    comfy_url: str | None = None           # ex.: http://127.0.0.1:8188
    comfy_workflow_video: str | None = None  # JSON exportado em "Save (API Format)"
    comfy_workflow_image: str | None = None
    sd_bin: str | None = None              # binário `sd` do stable-diffusion.cpp (build Vulkan)
    sd_model: str | None = None
    output_dir: str = "data/projects"
    shots: int = 3


def load() -> Config:
    e = os.environ.get
    return Config(
        ollama_url=e("CINEFORJA_OLLAMA_URL"), llm_model=e("CINEFORJA_LLM_MODEL"),
        vlm_model=e("CINEFORJA_VLM_MODEL"), comfy_url=e("CINEFORJA_COMFY_URL"),
        comfy_workflow_video=e("CINEFORJA_COMFY_WORKFLOW_VIDEO"),
        comfy_workflow_image=e("CINEFORJA_COMFY_WORKFLOW_IMAGE"),
        sd_bin=e("CINEFORJA_SD_BIN"), sd_model=e("CINEFORJA_SD_MODEL"),
        output_dir=e("CINEFORJA_OUTPUT_DIR", "data/projects"),
        shots=int(e("CINEFORJA_SHOTS", "3")),
    )
