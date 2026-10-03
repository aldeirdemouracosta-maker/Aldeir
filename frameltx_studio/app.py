"""Ponto de entrada do FrameLTX Studio.

Uso:
    python app.py                 # interface normal (requer ComfyUI rodando)
    python app.py --demo          # modo demonstração, sem GPU/ComfyUI
    python app.py --comfy http://127.0.0.1:8188 --port 7860
"""

from __future__ import annotations

import argparse
import logging
import sys

from frameltx.config import load_config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FrameLTX Studio — vídeos curtos com FramePack + LTX")
    parser.add_argument("--comfy", help="URL do ComfyUI (padrão: http://127.0.0.1:8188)")
    parser.add_argument("--port", type=int, help="Porta da interface (padrão: 7860)")
    parser.add_argument("--host", help="Endereço da interface (use 0.0.0.0 para acessar pela rede)")
    parser.add_argument("--profile", choices=["baixo", "medio", "alto", "ultra"], help="Força um perfil de qualidade")
    parser.add_argument("--demo", action="store_true", help="Modo demonstração (sem ComfyUI)")
    parser.add_argument("--debug", action="store_true", help="Logs detalhados")
    return parser.parse_args(argv)


def setup_logging(debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # Bibliotecas de rede são muito verbosas em INFO.
    for noisy in ("httpx", "urllib3", "websocket", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.debug)
    cfg = load_config()
    if args.comfy:
        cfg.comfy_url = args.comfy.rstrip("/")
    if args.port:
        cfg.server_port = args.port
    if args.host:
        cfg.server_host = args.host
    if args.profile:
        cfg.force_profile = args.profile
    if args.demo:
        cfg.demo_mode = True

    from frameltx.ui import launch  # importa o Gradio só depois de configurar logs

    launch(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
